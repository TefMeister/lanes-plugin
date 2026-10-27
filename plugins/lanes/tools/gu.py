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
  Since 0.94.0 everything about GitHub itself (texts behind the work, downloads behind the program, the skills page,
  what Lanes offers) is /lanes:od (od.py), which runs before /gu. The checks below the "texts" and "coverage" lines
  stay here because od.py calls them:
  - TEXTS ON GITHUB (0.69.0): repo descriptions and front pages that have fallen behind the work (gu_texts.py).
  - LANES AND THE SKILLS PAGE KEEP UP (0.93.0): a public `ours =` tool that Lanes does not offer (tools/ours.py),
    and, with `skills = <repo>/<file>`, MCP servers and plugins in use on this PC that the page never names, or a
    page left unchanged for SKILLS_STALE_DAYS. `lanes_skip =` and `skills_skip =` silence one name.

    python gu.py scan [--json]          the report
    python gu.py seen <name> <tag>      note that a watched tool's release has been looked at / installed
    python gu.py done                   stamp this run (the nudge counts days from here)
    python gu.py nudge                  one line at session start when the last run is NUDGE_DAYS old; else silent

Settings in lanes.conf (each may repeat): twin, watch, ours, routes, texts (+ texts_owner), catalog, skills,
lanes_skip, skills_skip. State: <state dir>/gu.json, per PC.
Never commits, never installs. Exit 0 always for nudge (a start-up check must never open a session with an error).
Tests set LANES_CONFIG, LANES_STATE_DIR, LANES_GU_FAKE_RELEASES (a JSON file: {"owner/repo": {release}}) and
LANES_GU_NO_NET=1.
"""
import datetime
import json
import os
import re
import subprocess
import sys
import urllib.request

import gu_texts

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "lanes")
STATE_FILE = os.path.join(STATE_DIR, "gu.json")
GIST_CHARS = 220             # how much of a release's notes the install question shows
NUDGE_DAYS = 7               # the habit: once a week
NET_TIMEOUT_S = 15
GIT_TIMEOUT_S = 30
SKIP_NAMES = {"__pycache__", ".git", ".pytest_cache"}
SKIP_SUFFIXES = (".pyc", ".bak")
OFFERED_ELSEWHERE = ("lanes-plugin", "hand-freeze-vr", "vr-bench")   # shipped or installed by Lanes' own tools
SKILLS_STALE_DAYS = 45       # a skills page untouched this long gets read again


# ---- settings and state ---------------------------------------------------------------------------------------

def conf_files():
    if os.environ.get("LANES_CONFIG"):
        return [os.environ["LANES_CONFIG"]]
    return [os.path.expanduser("~/.claude/lanes.conf"), os.path.expanduser("~/.config/lanes/lanes.conf")]


def conf_lines(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [line for line in f if not line.lstrip().startswith("#")]
    except OSError:
        return []


def conf_values(key):
    """Every value of a (repeatable) key; a ' #' note after the value is not part of it."""
    out = []
    for c in conf_files():
        for line in conf_lines(c):
            k, sep, v = line.partition("=")
            v = v.split(" #")[0].strip().strip('"')
            if not (sep and k.strip() == key and v):
                continue
            out.append(os.path.expandvars(os.path.expanduser(v)) if "|" not in v else v)
    return out


def pair(value):
    a, _, b = value.partition("|")
    return a.strip(), b.strip()


def asks():
    """False when the person said /gu may update without asking (gu_ask = no)."""
    return (conf_values("gu_ask") or ["yes"])[-1].lower() not in ("no", "false", "off", "0")


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
    """Equal, ignoring Windows/Unix line endings (git turns one into the other) and the display name written as
    "the maintainer" (a copy shipped in Lanes is rewritten that way on purpose; code health, 2026-10-27)."""
    names = [n.encode("utf-8") for n in conf_values("display_name") if n.lower() != "user"]

    def norm(data):
        data = data.replace(b"\r\n", b"\n")
        for n in names:
            data = data.replace(n, b"the maintainer")
        return data
    with open(p, "rb") as f, open(q, "rb") as g:
        return norm(f.read()) == norm(g.read())


def changed_at(path):
    """When this file last changed: its last commit if it is in git and unchanged since, else the file's date.
    File dates alone mislead: a fresh clone stamps every file with the clone time (seen on the first real run)."""
    d = os.path.dirname(path)
    try:
        _, dirty = git(d, "status", "--porcelain", "--", os.path.basename(path))
        rc, ct = git(d, "log", "-1", "--format=%ct", "--", os.path.basename(path))
        if rc == 0 and ct and not dirty:
            return int(ct)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    return os.path.getmtime(path)


def compare_twin(a, b):
    if not os.path.exists(a) or not os.path.exists(b):
        return {"a": a, "b": b, "error": "missing: " + (a if not os.path.exists(a) else b)}
    fa, fb = files_under(a), files_under(b)
    differ, only_a, only_b = [], sorted(set(fa) - set(fb)), sorted(set(fb) - set(fa))
    newer_a = newer_b = 0
    for rel in sorted(set(fa) & set(fb)):
        if not same_text(fa[rel], fb[rel]):
            differ.append(rel or os.path.basename(a))
            if changed_at(fa[rel]) >= changed_at(fb[rel]):
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


def release_gist(body, limit=GIST_CHARS):
    """The first plain sentence or two of a release's notes, for the install question (0.88.0)."""
    lines = []
    for line in body.splitlines():
        if line.lstrip().startswith("#"):          # a heading, not news
            continue
        line = re.sub(r"[#*`>_]|\[([^\]]*)\]\([^)]*\)", lambda m: m.group(1) or "", line).strip(" -")
        if line and not line.lower().startswith(("full changelog", "what's changed", "**full")):
            lines.append(line)
        if sum(len(x) for x in lines) >= limit:
            break
    text = "; ".join(x.rstrip(".;") for x in lines)
    return text if len(text) <= limit else text[:limit - 3].rsplit(" ", 1)[0] + "..."


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
                     "new": bool(tag) and seen.get(name) != tag, "error": err,
                     "url": rel.get("html_url") or (f"https://github.com/{repo}/releases/tag/{tag}" if tag else ""),
                     "notes": release_gist(rel.get("body") or "")})
    return rows


# ---- 4. lessons -----------------------------------------------------------------------------------------------

def tool_ideas(path, since):
    """The '- YYYY-MM-DD: ...' lines under '## Tool ideas' in one KNOWN.md, from `since` on."""
    out, section = [], ""
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("## "):
                section = line[3:].strip()
            elif section == "Tool ideas" and line.startswith("- ") and (not since or line[2:12] >= since):
                out.append(line[2:].strip())
    return out


def lessons(since):
    out = []
    for root in conf_values("routes"):
        apps = sorted(os.listdir(root)) if os.path.isdir(root) else []
        for app in apps:
            p = os.path.join(root, app, "KNOWN.md")
            if os.path.isfile(p):
                out += [{"app": app, "line": line} for line in tool_ideas(p, since)]
    return out


# ---- 5. texts on GitHub ----------------------------------------------------------------------------------------

def installed_apps():
    """every app of ours that any PC has noted as installed (<board>/installed/<PC>.json, installed.py)"""
    import installed
    b = installed.board()
    folder = os.path.join(b, installed.FOLDER) if b else ""
    names = set()
    for name in (os.listdir(folder) if os.path.isdir(folder) else []):
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                names.update(json.load(f))
        except (OSError, ValueError):
            pass
    return sorted(names)


def texts_report():
    roots, owner = conf_values("texts"), (conf_values("texts_owner") or [""])[-1]
    if not roots and not owner:
        return None
    return gu_texts.scan(roots, owner, today(), catalogs=conf_values("catalog"), ours=conf_values("ours"),
                         apps=installed_apps())


# ---- 6. Lanes and the skills page keep up with what we use (0.93.0) ---------------------------------------------

def squash(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def not_offered(owner):
    """public repos of ours (`ours =`) that Lanes neither ships, installs nor downloads (tools/ours.py)"""
    import ours
    offered = {t["repo"].split("/")[-1].lower() for t in ours.TOOLS.values()} | set(OFFERED_ELSEWHERE)
    skip = {s.lower() for s in conf_values("lanes_skip")}
    names = sorted({os.path.basename(c.rstrip("/\\")) for c in conf_values("ours")})
    names = [n for n in names if n.lower() not in offered | skip]
    if not names:
        return [], ""
    try:
        public = {r["name"].lower() for r in gu_texts.repo_list(owner)
                  if str(r.get("visibility", "")).upper() == "PUBLIC" and not r.get("isArchived")}
    except Exception as e:
        return [], f"could not ask GitHub which repos are public ({e})"
    return [n for n in names if n.lower() in public], ""


def connectors_here():
    """MCP servers registered with Claude Code for this user, and installed Claude Code plugins"""
    out = []
    try:
        with open(os.environ.get("LANES_CLAUDE_JSON") or os.path.expanduser("~/.claude.json"), encoding="utf-8") as f:
            out += [("MCP server", n) for n in (json.load(f).get("mcpServers") or {})]
    except (OSError, ValueError):
        pass
    plugins = os.environ.get("LANES_CLAUDE_PLUGINS") or os.path.expanduser("~/.claude/plugins/installed_plugins.json")
    try:
        with open(plugins, encoding="utf-8") as f:
            out += [("plugin", n.split("@")[0]) for n in (json.load(f).get("plugins") or {})]
    except (OSError, ValueError):
        pass
    return out


def skills_page():
    """`skills = <repo>/<file>`: connectors and plugins in use here that the page never names, and a page left
    unchanged for SKILLS_STALE_DAYS"""
    spec = (conf_values("skills") or [""])[-1]
    if not spec:
        return None
    path = next((os.path.join(r, spec) for r in conf_values("texts") if os.path.isfile(os.path.join(r, spec))), "")
    if not path:
        return {"page": spec, "flags": ["not found in any texts = folder"]}
    with open(path, encoding="utf-8", errors="replace") as f:
        text = squash(f.read())
    skip = {squash(s) for s in conf_values("skills_skip")}
    flags = [f"{kind} '{name}' is in use on this PC and the page never names it: add it once it has proven itself on "
             f"a real task (a private one stays off a public page: skills_skip = {name})"
             for kind, name in connectors_here() if squash(name) not in text and squash(name) not in skip]
    try:
        _, last = git(os.path.dirname(path), "log", "-1", "--format=%cs", "--", os.path.basename(path))
        days = (today() - datetime.date.fromisoformat(last)).days if last else 0
    except (OSError, subprocess.TimeoutExpired, ValueError):
        days = 0
    if days >= SKILLS_STALE_DAYS:
        flags.append(f"unchanged for {days} days: read it once against what is in use now")
    return {"page": spec, "flags": flags}


def coverage_report():
    owner = (conf_values("texts_owner") or [""])[-1]
    missing, err = not_offered(owner) if owner else ([], "")
    return {"not_offered": missing, "error": err, "skills": skills_page()}


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
    print("Ask before installing: " + ("no (gu_ask = no): update and report" if not asks() else "yes, one question for all"))
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
            if o.get("notes"):
                print(f"      what is in it: {o['notes']}")
            if o.get("url"):
                print(f"      from: {o['url']}")
        else:
            print(f"   {o['name']}: {o['newest'] or 'no releases'}, already noted")
    print("4. Lessons for the tools since the last run")
    for l in report["lessons"]:
        print(f"   {l['app']}: {l['line']}")
    if not report["lessons"]:
        print("   none")
    print("5. GitHub pages, downloads and the skills page: /lanes:od (od.py scan), run before this check")
    return 0


def nudge():
    try:
        configured = any(conf_values(k) for k in ("twin", "watch", "ours", "routes", "texts"))
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
