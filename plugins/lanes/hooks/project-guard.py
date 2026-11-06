"""project-guard.py -- one session edits a game's files at a time on this PC, whatever kind of session it is (0.106.1).

Why (2026-11-06, home PC): two sessions worked The Darkness at once, an ordinary one and a /pd-style one, with no
claim held (only /pd, /lm and /ms take the live claim), both building in the one source folder; the second copied
its build over the first's b016 program. Nothing warned. With several /pd sessions allowed at once (0.106.0) this
gap matters more.

How: the first time a session WRITES a file inside a project's folder (any path with a folder named like a project
of the games record: its clone in any lane root, its builds folder ...), it holds that project on this PC, quietly.
Another session that then writes into the same project is refused with one line naming the holder. Reads never are.
The hold ends when its session ends, or HOLD_H hours after its last write (a window closed without its end steps).
The person takes it over by typing "take over <project>" (their word, never the model's).

Wired: PreToolUse Write|Edit|MultiEdit|NotebookEdit (via tool-guards.py), UserPromptSubmit (via prompt-guards.py,
for "take over"), SessionEnd (hooks.json). Shell commands are not read (a build or copy is fuzzy to tell from text):
the source edits that come first are what it catches. Only with the extra `project_guard` on. Never fails closed.
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))

STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "lanes")
HOLD_DIR = os.path.join(STATE_DIR, "projects-held")
HOLD_H = 3
REFRESH_S = 60          # the hold's "last write" time is rewritten at most once a minute
SECONDS_PER_MINUTE = 60  # for the refusal's "last edit N min ago"
EDITS = ("Write", "Edit", "MultiEdit", "NotebookEdit")


def conf(key):
    path = os.environ.get("LANES_CONFIG") or os.path.join(os.path.expanduser("~"), ".claude", "lanes.conf")
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return ""
    found = re.findall(r"^\s*" + re.escape(key) + r"\s*=\s*(.*?)\s*(?:\s#.*)?$", text, re.M)
    return found[-1].strip().strip('"') if found else ""


def projects():
    """every project name in the games record (games.tsv)"""
    rec = os.environ.get("LANES_GAMES_RECORD") or conf("games_record")
    try:
        with open(os.path.join(rec, "games.tsv"), encoding="utf-8") as f:
            return {ln.split("\t")[0].strip().lower() for ln in f if ln.strip() and not ln.startswith("#")}
    except OSError:
        return set()


def project_of(path, names):
    for seg in re.split(r"[\\/]+", path or ""):
        if seg.lower() in names:
            return seg.lower()
    return None


def hold_file(project):
    return os.path.join(HOLD_DIR, project + ".json")


def read_hold(project):
    try:
        with open(hold_file(project), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def write_hold(project, sid, since=None):
    try:
        os.makedirs(HOLD_DIR, exist_ok=True)
        now = time.time()
        with open(hold_file(project), "w", encoding="utf-8") as f:
            json.dump({"session": sid, "since": since or now, "last": now,
                       "since_iso": time.strftime("%Y-%m-%d %H:%M", time.localtime(since or now))}, f)
    except OSError:
        pass


def release_session(sid):
    try:
        names = os.listdir(HOLD_DIR)
    except OSError:
        return
    for n in names:
        h = read_hold(n[:-5]) if n.endswith(".json") else None
        if h and h.get("session") == sid:
            try:
                os.remove(os.path.join(HOLD_DIR, n))
            except OSError:
                pass


def on_edit(data, sid):
    tin = data.get("tool_input") or {}
    path = tin.get("file_path") or tin.get("notebook_path") or ""
    names = projects()
    project = project_of(path, names) if names else None
    if not project:
        return 0
    now = time.time()
    h = read_hold(project)
    if h and h.get("session") != sid and now - h.get("last", 0) < HOLD_H * 3600:
        mins = int((now - h.get("last", 0)) / SECONDS_PER_MINUTE)
        sys.stderr.write(
            "PROJECT GUARD: another session on this PC is working on %s (since %s, last edit %d min ago). Two "
            "sessions editing one game overwrite each other's files (The Darkness b016, 2026-11-06). Work on another "
            "game, or ask the person: typing \"take over %s\" hands it to this session.\n"
            % (project, h.get("since_iso", "?"), mins, project))
        return 2
    if not h or h.get("session") != sid:
        write_hold(project, sid)
    elif now - h.get("last", 0) > REFRESH_S:
        write_hold(project, sid, since=h.get("since"))
    return 0


def on_prompt(data, sid):
    m = re.search(r"\btake over ([A-Za-z0-9._-]+)", data.get("prompt") or "", re.I)
    if not m:
        return 0
    project = m.group(1).lower()
    if project not in projects():
        return 0
    old = read_hold(project)
    write_hold(project, sid)
    note = "PROJECT GUARD: this session now holds %s on this PC (the person said \"take over\")." % project
    if old and old.get("session") != sid:
        note += " The session that held it may still be open: tell the person it should stop editing %s." % project
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": note}}))
    return 0


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8-sig", "replace"))
    except Exception:
        return 0
    try:
        import features
        if not features.is_on("project_guard"):
            return 0
    except Exception:
        pass
    event = data.get("hook_event_name", "")
    sid = data.get("session_id", "") or "unknown"
    if event == "SessionEnd":
        release_session(sid)
        return 0
    if event == "UserPromptSubmit":
        return on_prompt(data, sid)
    if event == "PreToolUse" and data.get("tool_name") in EDITS:
        return on_edit(data, sid)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        sys.exit(0)
