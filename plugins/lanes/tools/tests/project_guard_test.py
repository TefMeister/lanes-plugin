"""project_guard_test.py - one session writes into a game's files at a time (hooks/project-guard.py, 0.106.1).

The fault it stops (2026-11-06, home PC): two sessions worked The Darkness at once with no claim held, and the second
overwrote the first's b016 program. Run: python project_guard_test.py   (exit 0 = all passed)
"""
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "..", "..", "hooks", "project-guard.py")
T = tempfile.mkdtemp(prefix="lanes-project-guard-")
REC = os.path.join(T, "record")
os.makedirs(REC)
with open(os.path.join(REC, "games.tsv"), "w", encoding="utf-8") as f:
    f.write("# project\tstore\tid\ttitle\nthe-darkness-vr\tfolder\t\tThe Darkness\nvisceral-re8-vr\tsteam\t1\tVillage\n")
with open(os.path.join(T, "lanes.conf"), "w", encoding="utf-8") as f:
    f.write("project_guard = on\n")
ENV = dict(os.environ, LANES_STATE_DIR=os.path.join(T, "state"), LANES_GAMES_RECORD=REC,
           LANES_CONFIG=os.path.join(T, "lanes.conf"))
fails = 0


def run(payload):
    r = subprocess.run([sys.executable, HOOK], input=json.dumps(payload).encode(), capture_output=True, env=ENV)
    return r.returncode, r.stdout.decode(errors="replace") + r.stderr.decode(errors="replace")


def edit(sid, path):
    return run({"hook_event_name": "PreToolUse", "tool_name": "Edit", "session_id": sid,
                "tool_input": {"file_path": path}})


def check(what, ok):
    global fails
    fails += 0 if ok else 1
    print(("ok    " if ok else "FAIL  ") + what)


DARK = "D:/clones/github-backups-pd/the-darkness-vr/src/vr.cpp"
check("session A edits The Darkness: passes and holds it", edit("A", DARK)[0] == 0)
rc, out = edit("B", "E:/builds/the-darkness-vr/b016/game.exe")
check("session B writing into The Darkness's builds is refused", rc == 2 and "the-darkness-vr" in out)
check("session B may work another game", edit("B", "D:/clones/visceral-re8-vr/lua/grip.lua")[0] == 0)
check("a file outside every project passes", edit("C", "D:/clones/claude-memory/status/the-darkness-vr.md")[0] == 0)
check("session A keeps working its own game", edit("A", DARK)[0] == 0)
rc, out = run({"hook_event_name": "UserPromptSubmit", "session_id": "B", "prompt": "please take over the-darkness-vr"})
check("the person's \"take over\" hands it to B", rc == 0 and "now holds the-darkness-vr" in out)
check("now B may edit it", edit("B", DARK)[0] == 0)
check("and A is refused", edit("A", DARK)[0] == 2)
run({"hook_event_name": "SessionEnd", "session_id": "B"})
check("B's end gives back what it held (A may edit again)", edit("A", DARK)[0] == 0)
# a hold whose last write is older than HOLD_H counts as left over
hold = os.path.join(T, "state", "projects-held", "the-darkness-vr.json")
with open(hold, "w", encoding="utf-8") as f:
    json.dump({"session": "GONE", "since": 0, "last": time.time() - 4 * 3600, "since_iso": "old"}, f)
check("a hold untouched for over 3 hours does not block", edit("D", DARK)[0] == 0)
check("bad input passes (never fails closed)",
      subprocess.run([sys.executable, HOOK], input=b"not json", capture_output=True, env=ENV).returncode == 0)
sys.exit(1 if fails else 0)
