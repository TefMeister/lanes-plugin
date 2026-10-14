#!/usr/bin/env python3
"""gu.py - /lanes:gu, keep everything we rely on fresh (0.67.0, 2026-10-14).

Asked for by the maintainer: "/gs just checks; /gu could only check things that might need updates and then
update them when a newer version is on the PC, or add new info for the tools to use." One run looks at four things
and CHANGES NOTHING by itself; the session does the updating, on the person's yes where it installs something.

  1. OUR OWN APPS AND TOOLS: the lanes plugin and Hand Freeze (newer release out?), and every `ours = <clone>` repo
     (behind GitHub = pull it; ahead or unsaved = push it).
  2. TWINS: `twin = <A> | <B>`, two copies of the same file or folder (A is the master copy). Says which files
     differ and which side changed most recently.
  3. OUTSIDE TOOLS: `watch = <name> | <owner/repo>`, a tool from someone else on GitHub. Says when a release came
     out that we have not noted yet, with its title.
  4. LESSONS: lines added under "## Tool ideas" in each app's KNOWN.md (`routes = <folder>`) since the last run.

    python gu.py scan [--json]          the report
    python gu.py seen <name> <tag>      note that a watched tool's release has been looked at / installed
    python gu.py done                   stamp this run (the nudge counts days from here)
    python gu.py nudge                  one line at session start when the last run is NUDGE_DAYS old; else silent

Settings in lanes.conf (each may repeat): twin, watch, ours, routes. State: <state dir>/gu.json, per PC.
Never commits, never installs. Exit 0 always for nudge (a start-up check must never open a session with an error).
Tests set LANES_CONFIG, LANES_STATE_DIR, LANES_GU_FAKE_RELEASES (a JSON file: {"owner/repo": {release}}) and
LANES_GU_NO_NET=1.
"""
import datetime
import json
import os
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "lanes")
STATE_FILE = os.path.join(STATE_DIR, "gu.json")
NUDGE_DAYS = 7               # the habit: once a week
NET_TIMEOUT_S = 15
GIT_TIMEOUT_S = 30
SKIP_NAMES = {"__pycache__", ".git", ".pytest_cache"}
SKIP_SUFFIXES = (".pyc", ".bak")


# ---- settings and state ---------------------------------------------------------------------------------------

def conf_files():
    if os.environ.get("LANES_CONFIG"):
        return [os.environ["LANES_CONFIG"]]
    return [os.path.expanduser("~/.claude/lanes.conf"), os.path.expanduser("~/.config/lanes/lanes.conf")]


def conf_values(key):
    """Every value of a (repeatable) key; a ' #' note after the value is not part of it."""
    out = []
    for c in conf_files():
        try:
            for line in open(c, encoding="utf-8"):
                if line.lstrip().startswith("#"):
                    continue
                k, sep, v = line.partition("=")
                if sep and k.strip() == key:
                    v = v.split(" #")[0].strip().strip('"')
                    if v:
                        out.append(os.path.expandvars(os.path.expanduser(v)) if "|" not in v else v)
        except OSError:
            pass
    return out


def pair(value):
    a, _, b = value.partition("|")
    return a.strip(), b.strip()


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)


def today():
    fake = os.environ.get("LANES_GU_TODAY")
    return datetime.date.fromisoformat(fake) if fake else datetime.date.today()


# ---- 1. our own apps and tools --------------------------------------------------------------------------------

def run_json(script, *args):
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, script), *args], capture_output=True, text=True,
                           timeout=NET_TIMEOUT_S * 3)
        text = r.stdout.strip()
        return json.loads(text[text.index("{"):])
    except Exception as e:  # offline, tool missing: say so, never guess
        return {"error": str(e)}


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=GIT_TIMEOUT_S)
    return r.returncode, r.stdout.strip()


def clone_state(repo):
    """Behind / ahead of GitHub, and unsaved files, for one of our clones."""
    name = os.path.basename(os.path.normpath(repo))
    if not os.path.isdir(os.path.join(repo, ".git")):
        return {"name": name, "error": "not a git clone"}
    if not os.environ.get("LANES_GU_NO_NET"):
        git(repo, "fetch", "-q", "origin")
    rc, counts = git(repo, "rev-list", "--left-right", "--count", "HEAD...@{upstream}")
    if rc != 0:
        return {"name": name, "error": "no upstream branch"}
    ahead, behind = (int(x) for x in counts.split())
    _, dirty = git(repo, "status", "--porcelain")
    return {"name": name, "ahead": ahead, "behind": behind, "unsaved": len(dirty.splitlines()) if dirty else 0}


def our_apps():
    rows = []
    if not os.environ.get("LANES_GU_NO_NET"):
        lanes = run_json("update-check.py", "--json")
        rows.append({"name": "lanes plugin", "have": lanes.get("installed"), "newest": lanes.get("latest"),
                     "newer": bool(lanes.get("newer")), "error": lanes.get("error")})
        hf = run_json("hand-freeze.py", "status", "--json")
        if hf.get("installed"):
            rows.append({"name": "Hand Freeze", "have": hf.get("installed_release"), "newest": hf.get("latest_release"),
                         "newer": bool(hf.get("newer")), "error": hf.get("error")})
    clones = [clone_state(r) for r in conf_values("ours")]
    return rows, clones


# ---- 2. twins -------------------------------------------------------------------------------------------------

def files_under(root):
    if os.path.isfile(root):
        return {"": root}
    out = {}
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_NAMES]
        for f in files:
            if f.endswith(SKIP_SUFFIXES) or f in SKIP_NAMES:
                continue
            p = os.path.join(d, f)
            out[os.path.relpath(p, root).replace(os.sep, "/")] = p
    return out


def same_text(p, q):
    """Equal, ignoring Windows/Unix line endings (git turns one into the other)."""
    with open(p, "rb") as f, open(q, "rb") as g:
        return f.read().replace(b"\r\n", b"\n") == g.read().replace(b"\r\n", b"\n")


def compare_twin(a, b):
    if not os.path.exists(a) or not os.path.exists(b):
        return {"a": a, "b": b, "error": "missing: " + (a if not os.path.exists(a) else b)}
    fa, fb = files_under(a), files_under(b)
    differ, only_a, only_b = [], sorted(set(fa) - set(fb)), sorted(set(fb) - set(fa))
    newer_a = newer_b = 0
    for rel in sorted(set(fa) & set(fb)):
        if not same_text(fa[rel], fb[rel]):
            differ.append(rel or os.path.basename(a))
            if os.path.getmtime(fa[rel]) >= os.path.getmtime(fb[rel]):
                newer_a += 1
            else:
                newer_b += 1
    return {"a": a, "b": b, "differ": differ, "only_a": only_a, "only_b": only_b,
            "newer": "a" if newer_a > newer_b else ("b" if newer_b > newer_a else None)}


# ---- 3. outside tools -----------------------------------------------------------------------------------------

def latest_release(repo):
    fake = os.environ.get("LANES_GU_FAKE_RELEASES")
    if fake:
        with open(fake, encoding="utf-8") as f:
            return json.load(f).get(repo) or {}
    if os.environ.get("LANES_GU_NO_NET"):
        return {}
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases/latest",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "lanes-plugin"})
    with urllib.request.urlopen(req, timeout=NET_TIMEOUT_S) as r:
        return json.load(r)


def outside_tools(state):
    seen = state.get("seen", {})
    rows = []
    for value in conf_values("watch"):
        name, repo = pair(value)
        try:
            rel = latest_release(repo)
            tag, err = rel.get("tag_name", ""), None
        except Exception as e:
            rel, tag, err = {}, "", str(e)
        rows.append({"name": name, "repo": repo, "newest": tag or None, "title": rel.get("name") or "",
                     "date": (rel.get("published_at") or "")[:10], "noted": seen.get(name),
                     "new": bool(tag) and seen.get(name) != tag, "error": err})
    return rows


# ---- 4. lessons -----------------------------------------------------------------------------------------------

def lessons(since):
    out = []
    for root in conf_values("routes"):
        if not os.path.isdir(root):
            continue
        for app in sorted(os.listdir(root)):
            p = os.path.join(root, app, "KNOWN.md")
            if not os.path.isfile(p):
                continue
            section = ""
            for line in open(p, encoding="utf-8"):
                if line.startswith("## "):
                    section = line[3:].strip()
                elif section == "Tool ideas" and line.startswith("- "):
                    date = line[2:12]
                    if not since or date >= since:
                        out.append({"app": app, "line": line[2:].strip()})
    return out


# ---- commands -------------------------------------------------------------------------------------------------

def scan(as_json):
    state = load_state()
    apps, clones = our_apps()
    report = {"last_run": state.get("last_run"), "apps": apps, "clones": clones,
              "twins": [compare_twin(*pair(v)) for v in conf_values("twin")],
              "outside": outside_tools(state), "lessons": lessons(state.get("last_run"))}
    if as_json:
        print(json.dumps(report, indent=1))
        return 0
    print(f"Last /gu on this PC: {report['last_run'] or 'never'}")
    print("1. Our apps and tools")
    for a in apps:
        word = f"newer release out: {a['newest']}" if a["newer"] else "up to date"
        print(f"   {a['name']}: {a['have'] or '?'}, {word}" + (f" (could not check: {a['error']})" if a.get("error") else ""))
    for c in clones:
        if c.get("error"):
            print(f"   {c['name']}: {c['error']}")
            continue
        bits = [f"{c['behind']} new on GitHub" if c["behind"] else "", f"{c['ahead']} not pushed" if c["ahead"] else "",
                f"{c['unsaved']} unsaved" if c["unsaved"] else ""]
        print(f"   {c['name']}: " + (", ".join(b for b in bits if b) or "in step with GitHub"))
    print("2. Two copies of the same thing")
    for t in report["twins"]:
        if t.get("error"):
            print(f"   {t['a']} | {t['b']}: {t['error']}")
        elif not (t["differ"] or t["only_a"] or t["only_b"]):
            print(f"   {os.path.basename(t['a'].rstrip('/'))}: both copies match")
        else:
            side = {"a": "the master copy", "b": "the second copy"}.get(t["newer"], "neither side clearly")
            print(f"   {os.path.basename(t['a'].rstrip('/'))}: {len(t['differ'])} differ, {len(t['only_a'])} only in "
                  f"the master, {len(t['only_b'])} only in the copy; changed last: {side}")
    print("3. Outside tools")
    for o in report["outside"]:
        if o["error"]:
            print(f"   {o['name']}: could not check ({o['error']})")
        elif o["new"]:
            print(f"   {o['name']}: {o['newest']} ({o['date']}) {o['title']} - not noted yet"
                  + (f", last noted {o['noted']}" if o["noted"] else ""))
        else:
            print(f"   {o['name']}: {o['newest'] or 'no releases'}, already noted")
    print("4. Lessons for the tools since the last run")
    for l in report["lessons"]:
        print(f"   {l['app']}: {l['line']}")
    if not report["lessons"]:
        print("   none")
    return 0


def nudge():
    try:
        configured = any(conf_values(k) for k in ("twin", "watch", "ours", "routes"))
        last = load_state().get("last_run")
        if last:
            days = (today() - datetime.date.fromisoformat(last)).days
            if days >= NUDGE_DAYS:
                print(f"LANES /gu: the weekly tool check last ran {days} days ago on this PC. Mention it in one line "
                      f"(the person types /lanes:gu, or /gu, when it suits); do not run it unasked.")
        elif configured:
            print("LANES /gu: the weekly tool check has never run on this PC. Mention it in one line "
                  "(the person types /lanes:gu, or /gu, when it suits); do not run it unasked.")
    except Exception:
        pass
    return 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd = argv[0]
    if cmd == "scan":
        return scan("--json" in argv)
    if cmd == "seen" and len(argv) == 3:
        state = load_state()
        state.setdefault("seen", {})[argv[1]] = argv[2]
        save_state(state)
        print(f"noted: {argv[1]} {argv[2]}")
        return 0
    if cmd == "done":
        state = load_state()
        state["last_run"] = today().isoformat()
        save_state(state)
        print(f"/gu run stamped {state['last_run']}")
        return 0
    if cmd == "nudge":
        return nudge()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
