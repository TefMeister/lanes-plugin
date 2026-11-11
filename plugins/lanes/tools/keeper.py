#!/usr/bin/env python3
"""keeper.py - the Keeper: one session builds, the Keeper keeps GitHub right (0.108.0, 2026-11-11).

Asked for by the maintainer: the PC that builds "can work on mods uninterrupted", while the Keeper is "responsible
only for maintaining the neatness and correctness of github" and does all the uploading; then: "this needs to go
into lanes as a two pc option or a 1 pc option - where opening one session works on modding and another ones are
being opened and closed when needed". On or off: `keeper` (features.py). PROTOCOL section 47, docs/TWO-PCS.md.

THE SETTINGS (lanes.conf)
    keeper       = on
    keeper_mode  = other_pc | this_pc     other_pc: the Keeper is another PC (the doorman, parcels through the
                                          synced transfer folder). this_pc: one PC; uploads run in the background and
                                          a Keeper SESSION is opened on this PC only while there is a job for it.
    keeper_role  = developer | keeper     which side THIS PC is (other_pc only; a this_pc PC is both)

THE SESSION THAT BUILDS (the developer side)
    python keeper.py brief            session start: is the Keeper there (said loudly when it is OFF), which of the
                                      Keeper's regular jobs are due (with the exact thing to type), what was refused
    python keeper.py ask "<job>" [--project <name>]
                                      put a job in the Keeper's queue and make sure a Keeper session is open; prints
                                      the session's name so this session can message it
    python keeper.py close            this_pc only: politely close the Keeper sessions this tool opened (they are idle)
    python keeper.py due              the regular jobs that are due (exit 1 when any is)

THE KEEPER (a session on the Keeper PC, or the Keeper session on this PC): /lanes:keeper runs these
    python keeper.py round [--mark]   the work list: queued jobs, what was uploaded since the last round (with each
                                      hand-over's note), regular jobs due. --mark: this round is done
    python keeper.py finish <file>    a queued job is done (moved to queue/done, saved)
    python keeper.py done <job>       a regular job was done today (the reminders stop until it is due again)
    python keeper.py jobs             the regular jobs, when each was last done, when it is due
    python keeper.py jobs add <name> <every days> "<what to type>" "<what it is>"

WHERE: `<board>/keeper/` when lanes.conf names a board repo (both PCs read it; every change is committed and
pushed, only its own files staged), else the Lanes state folder. jobs.tsv = the regular jobs, done.tsv = when each
was done (append-only), queue/ = jobs handed over by the session that builds (create-only; done/ when finished).

Tests set LANES_CONFIG and LANES_STATE_DIR.
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import doorman as D  # noqa: E402
import parcel as P  # noqa: E402

STATE_FILE = os.path.join(D.STATE_DIR, "keeper-state.json")
LOCAL_SESSION_NAME = "Keeper"
DEFAULT_JOBS = [("fullscan", 7, "/lanes:fullscan", "the weekly check-up of everything on GitHub and on this PC")]
GIT_TIMEOUT_S = 120
ROUND_SHOWS_DAYS = 14


def conf():
    return D.conf()


def mode():
    return conf().get("keeper_mode", "other_pc").strip().lower()


def role():
    return "both" if mode() == "this_pc" else conf().get("keeper_role", "developer").strip().lower()


def keeper_word():
    return "the Keeper session" if mode() == "this_pc" else "the Keeper PC"


def state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(st):
    os.makedirs(D.STATE_DIR, exist_ok=True)
    with open(STATE_FILE + ".tmp", "w", encoding="utf-8") as f:
        json.dump(st, f, indent=1)
    os.replace(STATE_FILE + ".tmp", STATE_FILE)


# ----- the Keeper's folder (on the board when there is one) -----
def board():
    b = conf().get("board", "")
    b = D.expand(b) if b else ""
    return b if b and os.path.isdir(os.path.join(b, ".git")) else ""


def home():
    d = os.path.join(board() or D.STATE_DIR, "keeper")
    os.makedirs(os.path.join(d, "queue", "done"), exist_ok=True)
    return d


def git(args):
    return subprocess.run(["git", "-C", board()] + args, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=GIT_TIMEOUT_S)


def refresh():
    if board():
        git(["pull", "-q", "--rebase"])


def keep(paths, message):
    """save the Keeper's own files on the board: only these paths, then level with GitHub, then pushed"""
    if not board():
        return
    git(["add", "--"] + paths)
    if git(["commit", "-q", "-m", message, "--"] + paths).returncode == 0:
        git(["pull", "-q", "--rebase"])
        git(["push", "-q"])


# ----- the regular jobs -----
def jobs_file():
    return os.path.join(home(), "jobs.tsv")


def read_jobs():
    path = jobs_file()
    if not os.path.isfile(path):
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("# job\tevery (days)\twhat to type\twhat it is\n")
            for row in DEFAULT_JOBS:
                f.write("%s\t%d\t%s\t%s\n" % row)
        keep([path], "Keeper: the regular jobs list")
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 4 and not line.startswith("#") and parts[1].strip().isdigit():
                out.append({"name": parts[0].strip(), "every": int(parts[1]), "type": parts[2].strip(),
                            "what": parts[3].strip()})
    return out


def last_done():
    out = {}
    try:
        with open(os.path.join(home(), "done.tsv"), encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) >= 2 and not line.startswith("#"):
                    out[parts[0]] = max(out.get(parts[0], ""), parts[1])
    except OSError:
        pass
    return out


def due_jobs(today=None):
    today = today or date.today()
    done, out = last_done(), []
    for j in read_jobs():
        last = done.get(j["name"], "")
        late = (today - datetime.strptime(last, "%Y-%m-%d").date()).days - j["every"] if last else 0
        if not last or late >= 0:
            out.append(dict(j, last=last, late=late))
    return out


def due_lines():
    where = "In a Keeper session" if mode() == "this_pc" else "On the Keeper PC"
    lines = []
    for j in due_jobs():
        when = "never done" if not j["last"] else ("due today" if j["late"] == 0 else "%d day(s) late" % j["late"])
        lines.append("KEEPER JOB DUE (%s): %s. %s type:  %s   Say this in your first reply with exactly that "
                     "command, and again every session until it is done (the person asked to be reminded until "
                     "then)." % (when, j["what"], where, j["type"]))
    return lines


def cmd_due():
    refresh()
    lines = due_lines()
    print("\n".join(lines) if lines else "no regular Keeper job is due")
    return 1 if lines else 0


def cmd_done(name):
    refresh()
    if name not in [j["name"] for j in read_jobs()]:
        print("keeper: no regular job is called %s (see `keeper.py jobs`)" % name)
        return 1
    path = os.path.join(home(), "done.tsv")
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write("%s\t%s\t%s\n" % (name, date.today().isoformat(), conf().get("machine_name", "")))
    keep([path], "Keeper: %s done %s" % (name, date.today().isoformat()))
    print("keeper: %s marked done today; the reminders stop until it is due again" % name)
    return 0


def cmd_jobs(args):
    refresh()
    if args[:1] == ["add"] and len(args) >= 5 and args[2].isdigit():
        read_jobs()
        with open(jobs_file(), "a", encoding="utf-8", newline="\n") as f:
            f.write("%s\t%s\t%s\t%s\n" % (args[1], args[2], args[3], args[4]))
        keep([jobs_file()], "Keeper: regular job %s added" % args[1])
    done = last_done()
    for j in read_jobs():
        print("  %-14s every %2d days   last done %-10s   type: %-18s %s" % (
            j["name"], j["every"], done.get(j["name"], "never"), j["type"], j["what"]))
    return 0


# ----- the link (the session that builds, at its start) -----
def link_lines():
    if mode() != "other_pc" or role() != "developer":
        return []
    st = state()
    r = D.call("/status")
    if not r.get("ok"):
        if not st.get("off_since"):
            st["off_since"] = time.strftime("%Y-%m-%d %H:%M")
            save_state(st)
        return ["THE KEEPER PC IS OFF or cannot be reached (first noticed %s). Tell the person so in ONE line at the "
                "top of your first reply (it is normally always on). Carry on with the work: hand-overs wait in the "
                "transfer folder and nothing is lost." % st["off_since"]]
    lines = []
    if st.pop("off_since", None):
        save_state(st)
        lines.append("The Keeper PC is back.")
    if not r.get("sessions"):
        o = D.call("/open", {"name": ""})
        lines.append("The Keeper PC had no Claude session open; one was opened (%s)." % (o.get("name") or "unnamed")
                     if o.get("ok") else "The Keeper PC is there but a session could not be opened: %s" % o.get("error"))
    if r.get("parcels_waiting"):
        lines.append("The Keeper PC has %d hand-over(s) not uploaded yet." % r["parcels_waiting"])
    return lines


def cmd_brief():
    refresh()
    lines = link_lines()
    if role() in ("developer", "both"):
        lines += due_lines()
        f = P.folders()
        for _, r in P.labels(f["receipts"]):
            if r.get("status") == P.REFUSED and os.path.isfile(os.path.join(f["outbox"], r["id"] + ".json")):
                lines.append("A HAND-OVER WAS REFUSED: %s: %s. Put it right (usually pull, then `parcel.py send` "
                             "again); never force it." % (r["repo"], r.get("why", "?")))
    if lines:
        print("KEEPER (lanes, %s):\n  " % ("one PC" if mode() == "this_pc" else "two PCs") + "\n  ".join(lines))
    return 0


# ----- jobs handed to the Keeper session -----
def keeper_session_name():
    return LOCAL_SESSION_NAME if mode() == "this_pc" else D.clean_name(conf().get("doorman_name", D.DEFAULT_NAME))


def cmd_ask(args):
    project = ""
    if "--project" in args:
        i = args.index("--project")
        project = " ".join(args[i + 1:i + 2])
        args = args[:i] + args[i + 2:]
    job = " ".join(args).strip()
    if not job:
        print("keeper: say what the job is")
        return 2
    refresh()
    slug = re.sub(r"[^a-z0-9]+", "-", job.lower())[:50].strip("-") or "job"
    path = os.path.join(home(), "queue", "%s-%s.md" % (time.strftime("%Y-%m-%d-%H%M%S"), slug))
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("# A job for the Keeper\n\nAsked: %s by %s\nProject: %s\n\n%s\n" % (
            time.strftime("%Y-%m-%d %H:%M"), conf().get("machine_name", "the session that builds"),
            project or "-", job))
    keep([path], "Keeper queue: " + job[:60])
    name = keeper_session_name()
    if mode() == "this_pc":
        mine = [s for s in D.list_sessions() if s["by_doorman"] and s["name"].startswith(LOCAL_SESSION_NAME)]
        if mine:
            name = mine[0]["name"]
        else:
            o = D.open_session(LOCAL_SESSION_NAME)
            if not o.get("ok"):
                print("keeper: the job is queued (%s) but a Keeper session could not be opened: %s" % (
                    os.path.basename(path), o.get("error")))
                return 1
            name = o.get("name") or name
    else:
        r = D.call("/status")
        if not r.get("ok"):
            print("keeper: the job is queued (%s); the Keeper PC is not reachable now, it will find it at its next "
                  "round" % os.path.basename(path))
            return 1
        if not r.get("sessions"):
            D.call("/open", {"name": ""})
    print('keeper: job queued (%s). Now message the session named "%s": "a job is in the Keeper\'s queue; run '
          '/lanes:keeper".' % (os.path.basename(path), name))
    return 0


def cmd_finish(name):
    refresh()
    src = os.path.join(home(), "queue", os.path.basename(name))
    if not os.path.isfile(src):
        print("keeper: no such queued job: " + os.path.basename(name))
        return 1
    dst = os.path.join(home(), "queue", "done", os.path.basename(name))
    os.replace(src, dst)
    keep([src, dst], "Keeper: done, " + os.path.basename(name))
    print("keeper: %s finished" % os.path.basename(name))
    return 0


def cmd_round(mark):
    refresh()
    st = state()
    since = st.get("last_round", "")
    print("THE KEEPER'S ROUND (%s%s)" % ("one PC" if mode() == "this_pc" else "two PCs",
                                         ", last round " + since if since else ", first round"))
    queue = sorted(n for n in os.listdir(os.path.join(home(), "queue")) if n.endswith(".md"))
    print("\n1. Jobs handed over (%d):" % len(queue))
    for n in queue:
        with open(os.path.join(home(), "queue", n), encoding="utf-8") as f:
            body = [l.strip() for l in f.read().splitlines() if l.strip() and not l.startswith("#")]
        print("   - %s\n       %s" % (n, "\n       ".join(body[:6])))
    f = P.folders()
    cutoff = time.time() - ROUND_SHOWS_DAYS * 86400
    ups = [r for p, r in P.labels(f["receipts"]) if r.get("status") == P.ON_GITHUB and r.get("when", "") > since
           and os.path.getmtime(p) > cutoff]
    print("\n2. Uploaded since the last round (%d):" % len(ups))
    for r in ups:
        print("   - %s, %d step(s), %s" % (r["repo"], r.get("steps", 0), r.get("when", "")[:16]))
        print("       moved forward: " + (r.get("note") or "(no note: nothing to say on the front page)"))
        for s in r.get("subjects", [])[:4]:
            print("       . " + s)
    refused = [r for _, r in P.labels(f["receipts"]) if r.get("status") == P.REFUSED
               and os.path.isfile(os.path.join(f["outbox"], r["id"] + ".json"))]
    print("\n3. Refused hand-overs still waiting for the session that builds (%d):" % len(refused))
    for r in refused:
        print("   - %s: %s" % (r["repo"], r.get("why", "?")))
    due = due_jobs()
    print("\n4. Regular jobs due (%d):" % len(due))
    for j in due:
        print("   - %s: type %s  (%s)" % (j["name"], j["type"], j["what"]))
    if mark:
        st["last_round"] = time.strftime("%Y-%m-%d %H:%M:%S")
        save_state(st)
        print("\nround marked done.")
    return 0


def cmd_close():
    if mode() != "this_pc":
        print("keeper: only the one-PC mode closes Keeper sessions from here; on two PCs use doorman.py close <pid>")
        return 1
    mine = [s for s in D.list_sessions() if s["by_doorman"] and s["name"].startswith(LOCAL_SESSION_NAME)]
    worst = 0
    for s in mine:
        r = D.close_session(s["pid"])
        print("keeper: %s %s" % (s["name"], "closed" if r.get("ok") else "NOT closed: " + r.get("error", "?")))
        worst = max(worst, 0 if r.get("ok") else 1)
    if not mine:
        print("keeper: no Keeper session is open")
    return worst


def main(argv):
    verb = argv[0] if argv else ""
    if verb == "brief":
        return cmd_brief()
    if verb == "due":
        return cmd_due()
    if verb == "done" and len(argv) > 1:
        return cmd_done(argv[1])
    if verb == "jobs":
        return cmd_jobs(argv[1:])
    if verb == "ask":
        return cmd_ask(argv[1:])
    if verb == "finish" and len(argv) > 1:
        return cmd_finish(argv[1])
    if verb == "round":
        return cmd_round("--mark" in argv)
    if verb == "close":
        return cmd_close()
    if verb == "mode":
        print("%s (%s)" % (mode(), role()))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
