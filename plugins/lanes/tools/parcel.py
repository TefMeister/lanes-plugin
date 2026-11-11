#!/usr/bin/env python3
"""parcel.py - the session that builds hands its saved work to the Keeper, which uploads it (0.108.0, 2026-11-11).

Asked for by the maintainer: the PC that builds "doesn't have to spend time" uploading; the Keeper "must be the
one responsible for uploading anything, so files must be saved into the transfer ... folder". On or off: `keeper`.

TWO MODES (`keeper_mode` in lanes.conf):
  other_pc  the Keeper is another PC. A parcel (one sealed file per project per save) goes into the synced transfer
            folder; the Keeper's doorman takes it by itself: check, upload, receipt.
  this_pc   one PC. `send` starts the upload in the background from the working copy itself and writes the same
            receipt; the session does not wait for it and never sees its output unless it was refused.

A working folder is never put into a syncing program's folder (it breaks git folders with half-written files). The
Developer PC saves its steps on its own disk as usual (git commit, no push) and this tool seals the new steps of
one project into ONE file, a parcel (a git bundle), in the transfer folder. The Keeper unpacks it into its own
copy, pushes it (its push checks run there: the privacy guard and the rest) and writes a receipt back.

ON THE DEVELOPER PC
    python parcel.py send <project> [<project> ...] [--note "<what moved forward, one sentence>"]
                                                      seal each project's steps that are not on GitHub yet; the note
                                                      tells the Keeper what to write on the front page (leave it out
                                                      when nothing moved forward: a tidy-up, a test)
    python parcel.py send --all                       the same for every project in the clone root that has any
    python parcel.py status                           one line per parcel: waiting / on GitHub / refused (and why)
    python parcel.py light                            ONE line for the end of a write-up: everything on GitHub /
                                                      what waits for the Keeper / what was refused / what was never
                                                      handed over (saved steps with no parcel, changes in no step)

ON THE KEEPER PC
    python parcel.py receive                          take every parcel that has fully arrived: check, push, receipt

WHERE (inside `transfer = <folder>` from lanes.conf, a folder a syncing program keeps the same on both PCs; each PC
has its own path to it. One PC: the Lanes state folder, nothing is synced):
    parcels/outbox/<id>.bundle + <id>.json    a parcel and its label; the label is written LAST and carries the
                                              bundle's fingerprint, so a half-synced bundle is never opened
    parcels/receipts/<id>.json                the Keeper's answer
    parcels/done/                             parcels that are on GitHub (kept; nothing is deleted)
  The projects are looked for in `parcel_root = <folder>` (lanes.conf), else in `root`. The Keeper sets parcel_root
  to its normal working root: its `root` may be a read-only sweep lane's. `parcel_skip = <project>, ...` names
  projects that never go by parcel (the board repo, which both PCs use live, is never in the clone root anyway).

RULES
  - Only saved steps travel (commits). Changes not yet saved in a step stay behind; `send` says how many.
  - The Keeper only fast-forwards. If its copy holds steps the Developer PC has not got, the parcel is REFUSED with
    that reason; the Developer PC pulls and sends again. Nothing is ever forced or rewritten.
  - A push that fails (a check refused it, no network) is undone on the Keeper's copy and reported in the receipt.

Exit 0 = done or nothing to do, 1 = something was refused or could not be done (the reason is printed).
"""
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

HOME = os.path.expanduser("~")
CONF = os.environ.get("LANES_CONFIG") or os.path.join(HOME, ".claude", "lanes.conf")
STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(HOME, ".claude", "lanes")
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
GIT_TIMEOUT_S = 600
RECEIPT_SHOWN_DAYS = 2
RECEIVE_LOCK_STALE_S = 1800               # a receive lock older than this was left by a cut-off run
ON_GITHUB = "on GitHub"
REFUSED = "refused"
NOT_YET = "not yet"


def conf():
    out = {}
    try:
        with open(CONF, encoding="utf-8") as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                if "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip()
    except OSError:
        pass
    return out


def expand(p):
    return os.path.normpath(os.path.expandvars(os.path.expanduser(p)))


def this_pc():
    return conf().get("keeper_mode", "other_pc").strip().lower() == "this_pc"


def folders():
    if this_pc() and not os.environ.get("PARCEL_DIR"):
        base = os.path.join(STATE_DIR, "parcels")                  # one PC: nothing leaves it, no transfer folder
    else:
        t = os.environ.get("PARCEL_DIR") or conf().get("transfer", "")
        if not t or not os.path.isdir(expand(t)):
            sys.exit("parcel: the transfer folder is not set or not there (`transfer = ...` in lanes.conf)")
        base = os.path.join(expand(t), "parcels")
    out = {k: os.path.join(base, k) for k in ("outbox", "receipts", "done")}
    for d in out.values():
        os.makedirs(d, exist_ok=True)
    return out


def root():
    # parcel_root first: on the Keeper `root` is the read-only sweep lane's folder (found 2026-11-11), and
    # parcels must go into the Keeper's normal working copies
    r = os.environ.get("PARCEL_ROOT") or conf().get("parcel_root", "") or conf().get("root", "")
    if not r or not os.path.isdir(expand(r)):
        sys.exit("parcel: the clone root is not set or not there (`root = ...` in lanes.conf)")
    return expand(r)


def git(args, repo):
    p = subprocess.run(["git", "-C", repo] + args, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=GIT_TIMEOUT_S)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, data):
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, path)


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def labels(folder):
    out = []
    for p in sorted(glob.glob(os.path.join(folder, "*.json"))):
        d = read_json(p)
        if d:
            out.append((p, d))
    return out


# ----- the Developer PC -----
def send_one(repo_name, f, quiet_when_nothing=False, note=""):
    repo = os.path.join(root(), repo_name)
    if not os.path.isdir(os.path.join(repo, ".git")):
        print("parcel: %s is not a project in the clone root" % repo_name)
        return 1
    ok, branch = git(["branch", "--show-current"], repo)
    ok2, upstream = git(["rev-parse", "--abbrev-ref", "@{u}"], repo)
    if not (ok and branch and ok2):
        print("parcel: %s is on no branch that follows GitHub; nothing sent" % repo_name)
        return 1
    _, count = git(["rev-list", "--count", upstream + "..HEAD"], repo)
    if not count.isdigit() or int(count) == 0:
        if not quiet_when_nothing:
            print("parcel: %s has no saved step that is not on GitHub already" % repo_name)
        return 0
    _, tip = git(["rev-parse", "HEAD"], repo)
    _, base = git(["rev-parse", upstream], repo)
    for label_path, d in labels(f["outbox"]):
        if d.get("repo") != repo_name:
            continue
        answer = read_json(os.path.join(f["receipts"], d["id"] + ".json")) or {}
        if answer.get("status") == REFUSED:                       # answered and refused: put away, a new one follows
            done(f, label_path, label_path[:-5] + ".bundle")
        elif d.get("tip") == tip:
            print("parcel: %s is already handed over (waiting for the Keeper): %s" % (repo_name, d["id"]))
            return 0
    _, loose = git(["status", "--porcelain"], repo)
    pid = "%s__%s__%s__%s" % (repo_name, branch.replace("/", "-"), time.strftime("%Y%m%d-%H%M%S"), tip[:10])
    _, subjects = git(["log", "--format=%s", "%s..HEAD" % upstream], repo)
    c = conf()
    label = {"id": pid, "repo": repo_name, "branch": branch, "tip": tip, "base": base, "steps": int(count),
             "subjects": subjects.splitlines()[:50], "from": c.get("machine_name", ""), "note": note,
             "sent": time.strftime("%Y-%m-%d %H:%M:%S")}
    extra = "; %d change(s) not saved in a step yet stay behind" % len(loose.splitlines()) if loose else ""
    if this_pc():
        label["direct"] = True
        write_json(os.path.join(f["outbox"], pid + ".json"), label)
        flags = (CREATE_NO_WINDOW | DETACHED_PROCESS) if os.name == "nt" else 0
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "_push", pid], creationflags=flags,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        print("parcel: %s handed over, %s step(s); uploading in the background%s" % (repo_name, count, extra))
        return 0
    bundle = os.path.join(f["outbox"], pid + ".bundle")
    ok, out = git(["bundle", "create", bundle + ".part", "%s..%s" % (upstream, branch)], repo)
    if not ok:
        print("parcel: could not seal %s: %s" % (repo_name, out.splitlines()[-1] if out else "?"))
        return 1
    os.replace(bundle + ".part", bundle)
    label.update(sha256=sha256(bundle), bytes=os.path.getsize(bundle))
    write_json(os.path.join(f["outbox"], pid + ".json"), label)
    print("parcel: %s handed over, %s step(s), %.1f MB%s" % (repo_name, count, os.path.getsize(bundle) / 1e6, extra))
    return 0


def push_direct(pid):
    """one PC: upload a handed-over project from its working copy, in the background, and write the receipt"""
    f = folders()
    label_path = os.path.join(f["outbox"], pid + ".json")
    d = read_json(label_path)
    if not d:
        return 1
    repo = os.path.join(root(), d["repo"])
    ok, out = git(["push", "origin", "%s:%s" % (d["tip"], d["branch"])], repo)
    if ok:
        done(f, label_path, label_path[:-5] + ".bundle")
        receipt(f, d, ON_GITHUB)
        return 0
    tail = " / ".join(l.strip() for l in out.splitlines()[-6:]
                      if l.strip() and "failed to push some refs" not in l and not l.startswith("To "))
    receipt(f, d, REFUSED, "the upload was refused or failed: " + tail[:600])
    return 1


def send(names):
    f = folders()
    note = ""
    if "--note" in names:
        i = names.index("--note")
        note = " ".join(names[i + 1:i + 2]).strip()
        names = names[:i] + names[i + 2:]
    skip = {x.strip() for x in conf().get("parcel_skip", "").split(",") if x.strip()}
    if names == ["--all"]:
        names = sorted(n for n in os.listdir(root())
                       if n not in skip and os.path.isdir(os.path.join(root(), n, ".git")))
        return max([send_one(n, f, quiet_when_nothing=True, note=note) for n in names] or [0])
    if not names:
        print(__doc__)
        return 2
    return max(send_one(n, f, note=note) for n in names)


def status():
    f = folders()
    me = conf().get("machine_name", "")
    lines = []
    for _, d in labels(f["outbox"]):
        if d.get("from") == me or not me:
            r = read_json(os.path.join(f["receipts"], d["id"] + ".json"))
            if r and r.get("status") == NOT_YET:
                lines.append("⏳ %s: waiting, the Keeper could not take it yet (%s)" % (d["repo"], r.get("why", "")))
            elif not r:
                lines.append("⏳ %s: handed over %s, waiting for the Keeper (%d step(s))" % (d["repo"], d["sent"][5:16], d["steps"]))
    cutoff = time.time() - RECEIPT_SHOWN_DAYS * 86400
    newest = {}                                                    # per project only its newest answer is shown
    for p, r in labels(f["receipts"]):
        if os.path.getmtime(p) < cutoff or r.get("status") == NOT_YET or (me and r.get("from") != me):
            continue
        if r["repo"] not in newest or r.get("when", "") >= newest[r["repo"]].get("when", ""):
            newest[r["repo"]] = r
    for r in newest.values():
        if r.get("status") == ON_GITHUB:
            repo = os.path.join(root(), r["repo"])
            if os.path.isdir(repo):
                git(["fetch", "-q", "origin"], repo)             # so this PC's own view of GitHub is up to date
            lines.append("✅ %s: on GitHub (%s, %d step(s))" % (r["repo"], r.get("when", "")[5:16], r.get("steps", 0)))
        else:
            lines.append("🔴 %s: REFUSED by the Keeper: %s" % (r["repo"], r.get("why", "?")))
    print("\n".join(lines) if lines else "parcel: nothing handed over lately")
    return 1 if any(l.startswith("🔴") for l in lines) else 0


def light():
    f = folders()
    sent = {(d.get("repo"), d.get("tip")): d for _, d in labels(f["outbox"])}
    refused, waiting, unsent, loose = [], [], [], []
    skip = {x.strip() for x in conf().get("parcel_skip", "").split(",") if x.strip()}
    for name in sorted(os.listdir(root())):
        repo = os.path.join(root(), name)
        if name in skip or not os.path.isdir(os.path.join(repo, ".git")):
            continue
        ok, count = git(["rev-list", "--count", "@{u}..HEAD"], repo)
        if ok and count.isdigit() and int(count):
            _, tip = git(["rev-parse", "HEAD"], repo)
            d = sent.get((name, tip))
            answer = read_json(os.path.join(f["receipts"], d["id"] + ".json")) if d else None
            if answer and answer.get("status") == REFUSED:
                refused.append("%s (%s)" % (name, answer.get("why", "?")))
            elif d:
                waiting.append(name)
            else:
                git(["fetch", "-q", "origin"], repo)               # perhaps uploaded since: look again, level
                _, count = git(["rev-list", "--count", "@{u}..HEAD"], repo)
                if count.isdigit() and int(count):
                    unsent.append(name)
        _, changed = git(["status", "--porcelain", "--untracked-files=no"], repo)
        if changed:
            loose.append(name)
    parts = []
    if refused:
        parts.append("\U0001F534 REFUSED by the Keeper: " + "; ".join(refused))
    if unsent:
        parts.append("\U0001F7E0 saved but not handed over: " + ", ".join(unsent))
    if waiting:
        parts.append("\u23F3 waiting for the Keeper: " + ", ".join(waiting))
    if loose:
        parts.append("\u270F\uFE0F changes in no saved step yet: " + ", ".join(loose))
    print("\U0001F4E6 " + (" \u00B7 ".join(parts) if parts else "everything this PC saved is on GitHub"))
    return 1 if refused or unsent else 0


# ----- the Keeper PC -----
def receipt(f, d, state, why="", **more):
    data = {"id": d["id"], "repo": d["repo"], "branch": d["branch"], "tip": d["tip"], "steps": d.get("steps", 0),
            "from": d.get("from", ""), "note": d.get("note", ""), "subjects": d.get("subjects", [])[:10],
            "status": state, "why": why, "when": time.strftime("%Y-%m-%d %H:%M:%S"),
            "by": conf().get("machine_name", "")}
    data.update(more)
    write_json(os.path.join(f["receipts"], d["id"] + ".json"), data)
    print("parcel: %s -> %s%s" % (d["id"], state, (": " + why) if why else ""))


def receive_one(label_path, d, f):
    if d.get("direct"):
        return 0                                                   # one PC: its own background upload answers it
    bundle = label_path[:-5] + ".bundle"
    if not os.path.isfile(bundle) or os.path.getsize(bundle) != d.get("bytes") or sha256(bundle) != d.get("sha256"):
        print("parcel: %s is still arriving (the file is not complete yet); left for the next run" % d["id"])
        return 0
    repo = os.path.join(root(), d["repo"])
    branch = d["branch"]
    if not os.path.isdir(os.path.join(repo, ".git")):
        receipt(f, d, NOT_YET, "the Keeper has no copy of this project in its clone root")
        return 1
    _, now_branch = git(["branch", "--show-current"], repo)
    _, changed = git(["status", "--porcelain", "--untracked-files=no"], repo)
    if now_branch != branch or changed:
        receipt(f, d, NOT_YET, "the Keeper's copy is on another branch or has unsaved changes")
        return 1
    ok, out = git(["fetch", "-q", "origin"], repo)
    if not ok:
        receipt(f, d, NOT_YET, "the Keeper could not reach GitHub")
        return 1
    git(["merge", "-q", "--ff-only", "origin/" + branch], repo)
    ok, out = git(["bundle", "verify", bundle], repo)
    if not ok:
        receipt(f, d, REFUSED, "the parcel does not fit the Keeper's copy (it builds on steps the Keeper has not got)")
        return 1
    ref = "refs/parcels/" + d["id"]
    ok, out = git(["fetch", "-q", bundle, "refs/heads/%s:%s" % (branch, ref)], repo)
    _, got = git(["rev-parse", ref], repo)
    if not ok or got != d["tip"]:
        receipt(f, d, REFUSED, "the parcel's content is not what its label says")
        return 1
    if git(["merge-base", "--is-ancestor", d["tip"], "origin/" + branch], repo)[0]:
        done(f, label_path, bundle)
        receipt(f, d, ON_GITHUB, "it was there already")
        return 0
    _, before = git(["rev-parse", "HEAD"], repo)
    ok, out = git(["merge", "-q", "--ff-only", ref], repo)
    if not ok:
        _, ahead = git(["rev-list", "--count", "%s..HEAD" % d["tip"]], repo)
        receipt(f, d, REFUSED, "GitHub has %s step(s) the Developer PC has not got; pull there and hand over again" % ahead)
        return 1
    ok, out = git(["push", "origin", branch], repo)
    if not ok:
        git(["reset", "-q", "--keep", before], repo)               # the Keeper's copy goes back to where it was
        tail = " / ".join(l.strip() for l in out.splitlines()[-6:]        # the reason, without addresses or paths
                          if l.strip() and "failed to push some refs" not in l and not l.startswith("To "))
        receipt(f, d, REFUSED, "the upload was refused or failed: " + tail[:600])
        return 1
    git(["update-ref", "-d", ref], repo)
    done(f, label_path, bundle)
    receipt(f, d, ON_GITHUB)
    return 0


def done(f, label_path, bundle):
    for p in (bundle, label_path):
        if os.path.isfile(p):
            shutil.move(p, os.path.join(f["done"], os.path.basename(p)))


def receive():
    f = folders()
    todo = labels(f["outbox"])
    if not todo:
        print("parcel: no parcel is waiting")
        return 0
    lock = os.path.join(os.path.dirname(f["outbox"]), "receive.lock")
    try:
        if os.path.isfile(lock) and time.time() - os.path.getmtime(lock) > RECEIVE_LOCK_STALE_S:
            os.remove(lock)                                        # left behind by a receive that was cut off
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
    except OSError:
        print("parcel: another receive is running; it takes these too")
        return 0
    worst = 0
    try:
        for label_path, d in todo:
            prior = read_json(os.path.join(f["receipts"], d["id"] + ".json"))
            if prior and prior.get("status") == REFUSED:
                continue                                           # answered already; the sender sends a new one
            worst = max(worst, receive_one(label_path, d, f))
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass
    return worst


def main(argv):
    verb = argv[0] if argv else ""
    if verb == "send":
        return send(argv[1:])
    if verb == "_push" and len(argv) > 1:                          # the background upload of the one-PC mode
        return push_direct(argv[1])
    if verb == "status":
        return status()
    if verb == "light":
        return light()
    if verb == "receive":
        return receive()
    print(__doc__)
    return 2


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
