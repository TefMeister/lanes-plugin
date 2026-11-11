"""scan_priority_test.py - the full scan goes first: other sessions are told, given time, then held; hand-overs wait
(0.110.0, 2026-11-11).

In a temp folder: a pretend state folder with the scan's lock in it, the hook fed pretend tool calls, and a pretend
GitHub with two PCs for the hand-over half. No network, no window. Exit 0 = pass."""
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta

T = tempfile.mkdtemp(prefix="scanprio-")
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
HOOK = os.path.join(os.path.dirname(TOOLS), "hooks", "scan-priority.py")
SP = os.path.join(TOOLS, "scan_priority.py")
PARCEL = os.path.join(TOOLS, "parcel.py")
TIME_FMT = "%Y-%m-%d %H:%M %z"
fails = 0


def check(ok, what):
    global fails
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        fails += 1


def p(*parts):
    return os.path.join(T, *parts).replace("\\", "/")


def sh(args, cwd=None, env=None, stdin=None):
    r = subprocess.run(args, cwd=cwd, env=env, input=stdin, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def git(args, cwd):
    return sh(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "core.autocrlf=false"] + args, cwd)


def side(name, **settings):
    conf = p(name + ".conf")
    with open(conf, "w", encoding="utf-8") as f:
        f.write("".join("%s = %s\n" % kv for kv in settings.items()))
    os.makedirs(p("state-" + name), exist_ok=True)
    return dict(os.environ, LANES_CONFIG=conf, LANES_STATE_DIR=p("state-" + name), LANES_CONF=conf)


def lock(env, job="fullscan", session="scan-1", minutes_ago=0):
    d = os.path.join(env["LANES_STATE_DIR"], "clash")
    os.makedirs(d, exist_ok=True)
    since = (datetime.now().astimezone() - timedelta(minutes=minutes_ago)).strftime(TIME_FMT)
    with open(os.path.join(d, job + ".lock"), "w", encoding="utf-8") as f:
        f.write("machine = B\nsince = %s\njob = %s\nproject = all\nsession = %s\n" % (since, job, session))


def unlock(env, job="fullscan"):
    try:
        os.remove(os.path.join(env["LANES_STATE_DIR"], "clash", job + ".lock"))
    except OSError:
        pass


def hook(env, session, tool="Bash", command="echo hi", event="PreToolUse"):
    data = {"hook_event_name": event, "session_id": session, "tool_name": tool, "tool_input": {"command": command},
            "prompt": "hello"}
    return sh([sys.executable, HOOK], env=env, stdin=json.dumps(data))


def age_marker(env, session, minutes):
    path = os.path.join(env["LANES_STATE_DIR"], "scan-priority", "told-%s.json" % session)
    m = json.load(open(path, encoding="utf-8"))
    m["told"] -= minutes * 60
    m["reminded"] -= minutes * 60
    json.dump(m, open(path, "w", encoding="utf-8"))


ON = side("on", machine_name="B", scan_priority="on")
OFF = side("off", machine_name="B", scan_priority="off")

# ----- nothing runs -----
rc, out, err = hook(ON, "work-1")
check(rc == 0 and not out and not err, "no scan running: a working session is left alone, silently")
check(sh([sys.executable, SP, "status"], env=ON)[0] == 1, "status says no scan is running (exit 1)")

# ----- a scan starts in another session -----
lock(ON)
check(sh([sys.executable, SP, "status"], env=ON)[0] == 0, "status says a scan holds this PC (exit 0)")
rc, out, err = hook(ON, "scan-1")
check(rc == 0 and not out, "the scan's own session passes untouched")
check(os.path.isfile(os.path.join(ON["LANES_STATE_DIR"], "scan-priority", "beat.json")), "and its call is its heartbeat")
rc, out, err = hook(ON, "work-1", "Edit")
check(rc == 0 and "FULL SCAN PRIORITY" in out and "BACKGROUND" in out and "work-1" in out,
      "another session's first call passes, with the notice (save, say you wait, start the wait)")
rc, out, err = hook(ON, "work-1", "Edit")
check(rc == 0 and not out, "inside the grace its calls pass without the notice again")
age_marker(ON, "work-1", 5)
rc, out, err = hook(ON, "work-1", "Edit")
check(rc == 0 and "FULL SCAN PRIORITY" in out, "a session that keeps working is reminded now and then")
age_marker(ON, "work-1", 11)
rc, out, err = hook(ON, "work-1", "Edit")
check(rc == 2 and "was not run" in err, "after the grace an edit is refused")
rc, out, err = hook(ON, "work-1", "Bash", "python build.py && echo done")
check(rc == 2, "after the grace a command that is not a save is refused")
rc, out, err = hook(ON, "work-1", "Bash", 'git -C "D:/x" commit -m "save" && git push')
check(rc == 0, "after the grace a save still passes (git commit, push)")
rc, out, err = hook(ON, "work-1", "Bash", "git pull --rebase && git push")
check(rc == 2, "but not a command that also brings changes in (git pull)")
rc, out, err = hook(ON, "work-1", "PowerShell", 'python "x/tools/scan_priority.py" wait --session work-1')
check(rc == 0, "and the wait itself passes")
rc, out, err = hook(ON, "work-1", "Read", "")
check(rc == 0, "reading is never refused")
rc, out, err = hook(ON, "work-2", event="UserPromptSubmit")
check(rc == 0 and "FULL SCAN PRIORITY" in out, "a typed message in another session gets one line of context")
rc, out, err = hook(OFF, "work-1", "Edit")
lock(OFF)
check(hook(OFF, "work-1", "Edit")[0:2] == (0, ""), "the extra switched off: nothing is held")

# ----- the wait returns when the scan ends -----
w = subprocess.Popen([sys.executable, SP, "wait", "--session", "work-1"], env=ON, stdout=subprocess.PIPE, text=True)
time.sleep(1.5)
check(w.poll() is None, "the wait keeps waiting while the scan runs")
unlock(ON)
try:
    out = w.communicate(timeout=40)[0]
except subprocess.TimeoutExpired:
    w.kill()
    out = ""
check("has ended" in out and w.returncode == 0, "the wait returns once the scan has ended")
rc, out, err = hook(ON, "work-1", "Edit")
check(rc == 0 and not out, "afterwards the session works as before")
lock(ON, session="scan-2")
rc, out, err = hook(ON, "work-1", "Edit")
check(rc == 0 and "FULL SCAN PRIORITY" in out, "the next scan tells it afresh")

# ----- the person lifts it; a part run alone; a dead window -----
check(sh([sys.executable, SP, "lift"], env=ON)[0] == 0 and hook(ON, "work-3", "Edit")[0:2] == (0, ""),
      "lift (the person's word) lets the others work beside this run")
unlock(ON)
lock(ON, job="gu", session="gu-1")
check("FULL SCAN PRIORITY" in hook(ON, "work-4", "Edit")[1], "a part of the scan run alone (/gu) has priority too")
unlock(ON, "gu")
NARROW = side("narrow", machine_name="B", scan_priority="on", scan_priority_jobs="fullscan")
lock(NARROW, job="gu", session="gu-1")
check(hook(NARROW, "work-4", "Edit")[0:2] == (0, ""), "scan_priority_jobs narrows which runs have priority")
lock(ON, session="scan-3", minutes_ago=120)
check(hook(ON, "work-5", "Edit")[0:2] == (0, ""), "a scan whose window died (no call for 45 min) holds nobody")
hook(ON, "scan-3")
check("FULL SCAN PRIORITY" in hook(ON, "work-5", "Edit")[1], "a long scan that is still making calls does hold")
unlock(ON)
lock(ON, session="")
check(hook(ON, "work-6", "Edit")[0:2] == (0, ""), "a lock that belongs to no session holds nobody")
unlock(ON)

# ----- hand-overs from the other PC wait, then go up in order -----
for d in ("dev", "keeper", "transfer"):
    os.makedirs(p(d))
git(["init", "-q", "--bare", "-b", "main", p("proj.git")], T)
git(["clone", "-q", p("proj.git"), p("dev", "proj")], T)
git(["checkout", "-q", "-b", "main"], p("dev", "proj"))
open(p("dev", "proj", "a.txt"), "w").write("one\n")
git(["add", "a.txt"], p("dev", "proj"))
git(["commit", "-q", "-m", "first"], p("dev", "proj"))
git(["push", "-q", "-u", "origin", "main"], p("dev", "proj"))
git(["clone", "-q", p("proj.git"), p("keeper", "proj")], T)
DEV = side("dev", machine_name="A", root=p("dev"), transfer=p("transfer"), keeper_mode="other_pc",
           keeper_role="developer")
KEEP = side("keeper", machine_name="B", root=p("nowhere"), parcel_root=p("keeper"), transfer=p("transfer"),
            keeper_mode="other_pc", keeper_role="keeper", scan_priority="on")
open(p("dev", "proj", "a.txt"), "a").write("two\n")
git(["commit", "-q", "-am", "second step"], p("dev", "proj"))
check(sh([sys.executable, PARCEL, "send", "proj"], env=DEV)[0] == 0, "the other PC hands a step over")
lock(KEEP)
rc, out, err = sh([sys.executable, PARCEL, "receive"], env=KEEP)
steps = git(["rev-list", "--count", "main"], p("proj.git"))[1]
check(rc == 0 and "wait" in out and steps == "1", "while the scan runs the Keeper leaves the parcel alone")
rc, out, err = sh([sys.executable, PARCEL, "status"], env=DEV)
check("full scan" in out and "waiting" in out, "the other PC's status says it waits for the full scan")
rc, out, err = sh([sys.executable, PARCEL, "light"], env=DEV)
check("waiting for the Keeper: proj (" in out and "full scan" in out, "and so does its light line")
n = len(os.listdir(p("transfer", "parcels", "receipts")))
sh([sys.executable, PARCEL, "receive"], env=KEEP)
check(len(os.listdir(p("transfer", "parcels", "receipts"))) == n, "looking again writes no second answer")
unlock(KEEP)
rc, out, err = sh([sys.executable, PARCEL, "receive"], env=KEEP)
steps = git(["rev-list", "--count", "main"], p("proj.git"))[1]
check(rc == 0 and "on GitHub" in out and steps == "2", "when the scan has ended the parcel is uploaded")
rc, out, err = sh([sys.executable, PARCEL, "light"], env=DEV)
check("everything this PC saved is on GitHub" in out, "and the light line is plain again")

print("scan_priority_test: %s" % ("all passed" if not fails else "%d FAILED" % fails))
sys.exit(1 if fails else 0)
