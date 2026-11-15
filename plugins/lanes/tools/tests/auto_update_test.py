"""auto_update_test.py - Lanes updates itself with no question, waits while a game, a test or a hold is on, and says
how it went at the next session start (0.117.0, 2026-11-15).

A pretend update check (AUTO_UPDATE_TEST_CHECK) whose update commands only write marker files in a temp folder:
nothing is installed and Claude Code is never called. Exit 0 = pass."""
import json
import os
import subprocess
import sys
import tempfile
import time

T = tempfile.mkdtemp(prefix="autoupd-")
HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(HERE), "auto_update.py")
STATE = os.path.join(T, "state")
CHECK = os.path.join(T, "check.json")
MARK = os.path.join(T, "ran.txt").replace("\\", "/")
INSTALL = os.path.join(T, "pretend_install.py").replace("\\", "/")
with open(INSTALL, "w", encoding="utf-8") as f:
    f.write("import os, shutil\nopen(%r, 'a').write('x')\nif os.path.exists(%r):\n    shutil.copy(%r, %r)\n"
            % (MARK, CHECK + ".after", CHECK + ".after", CHECK))
fails = 0


def check(ok, what):
    global fails
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        fails += 1


def pretend(newer=True, installed="0.115.0", latest="0.117.0", held=False, ok=True, after=None):
    """the update check; `after` = what it says once the update commands ran (the marker file exists)"""
    py = sys.executable.replace("\\", "/")
    cmd = '"%s" "%s"' % (py, INSTALL)          # the pretend install: the marker, and the new version installed
    fail = '"%s" -c "import sys; print(\'network down\'); sys.exit(1)"' % py
    d = {"installed": installed, "latest": latest, "newer": newer, "held": held,
         "hold": {"why": "a headset test"} if held else None,
         "changes": [["0.116.0", "the full scan checks network safety."], ["0.117.0", "Lanes updates itself."]],
         "update_commands": [cmd if ok else fail]}
    json.dump(d, open(CHECK, "w", encoding="utf-8"))
    if after:
        json.dump(dict(d, **after), open(CHECK + ".after", "w", encoding="utf-8"))
    elif os.path.exists(CHECK + ".after"):
        os.remove(CHECK + ".after")


def run(*args, games=""):
    env = dict(os.environ, LANES_STATE_DIR=STATE, AUTO_UPDATE_TEST_CHECK=CHECK, AUTO_UPDATE_TEST_GAMES=games)
    r = subprocess.run([sys.executable, TOOL] + list(args), env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout + r.stderr).strip()


# up to date: silent
pretend(newer=False, installed="0.117.0")
rc, out = run("start", "--wait")
check(rc == 0 and out == "", "up to date: the session start says nothing")

# a game is running: waits, one line, nothing run
pretend()
rc, out = run("start", "--wait", games="re8.exe")
check("installs by itself" in out and "re8.exe is running" in out and not os.path.exists(MARK),
      "while a game runs it waits, says why in one line, and runs nothing")

# a hold is on: waits
pretend(held=True)
rc, out = run("start", "--wait")
check("update hold" in out and "headset test" in out and not os.path.exists(MARK), "while a hold is on it waits")

# a game session's lock: waits
os.makedirs(os.path.join(STATE, "clash"), exist_ok=True)
since = time.strftime("%Y-%m-%d %H:%M ") + time.strftime("%z")
lock = os.path.join(STATE, "clash", "live.lock")
open(lock, "w", encoding="utf-8").write("machine = A\nsince = %s\njob = live\nproject = re8\nsession = s-1\n" % since)
pretend()
rc, out = run("start", "--wait")
check("installs by itself" in out and not os.path.exists(MARK), "while a game session holds its lock it waits")
os.remove(lock)

# clear: it updates with no question, and says what each version adds
pretend(after={"installed": "0.117.0", "newer": False})

rc, out = run("start", "--wait")
check(os.path.exists(MARK), "with nothing in the way it runs the update commands, no question asked")
check("UPDATING ITSELF" in out and "0.116.0: the full scan" in out and "0.117.0: Lanes updates itself" in out,
      "and tells the session what each version adds, one line per version")
check("ASK" not in out.replace("Do not ask", "") and "Would you like" not in out, "it never asks")
res = json.load(open(os.path.join(STATE, "auto-update", "result.json"), encoding="utf-8"))
check(res.get("ok") and res.get("to") == "0.117.0", "the result is kept: done, now 0.117.0")
pretend(newer=False, installed="0.117.0")
rc, out = run("start", "--wait")
check("UPDATED ITSELF" in out and "0.115.0 -> 0.117.0" in out, "the next session start says it updated itself")
rc, out = run("start", "--wait")
check(out == "", "and says it only once")

# a failed update: reported, old version kept, tried again next time
os.remove(MARK)
pretend(ok=False)
rc, out = run("start", "--wait")
pretend(newer=True)
rc, out = run("start", "--wait", games="x.exe")
check("COULD NOT UPDATE ITSELF" in out and "network down" in out, "a failed update is said in plain words with why")
check("old version still works" in out and "fault list" in out, "with what it means and where it goes")

# one at a time
open(os.path.join(STATE, "auto-update", "running.lock"), "w").write("1")
pretend()
rc, out = run("start", "--wait")
check("being installed in the background already" in out and not os.path.exists(MARK), "never two updates at once")
os.remove(os.path.join(STATE, "auto-update", "running.lock"))

rc, out = run("status")
check(rc == 0 and "auto_update:" in out, "status says how the last one went")

print()
print("auto_update_test.py: %s" % ("all passed" if not fails else "%d FAILED" % fails))
sys.exit(1 if fails else 0)
