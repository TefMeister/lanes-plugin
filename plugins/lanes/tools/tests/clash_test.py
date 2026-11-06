"""clash_test.py - the clash guard keeps apart what must not run at the same time (lanes-next, 2026-11-05).
In a temp folder: a pretend GitHub (bare repo), two board clones and two Lanes state folders (PC1 HOME, PC2 DEV).
Checks: the table's audit; a full scan on one PC stops a full scan and its parts on the other, but its own session's
parts pass; a same-PC-only job (a Lanes update) is stopped on its own PC and not on the other; research on two
different projects is fine, on the same project (or the whole sweep) is not; a left-over lock and a dead program's lock
do not block; the old full-scan lock and this one agree; a session's end gives back its locks; the hook refuses with
one line and lets "force" through; the board clone's working tree is never touched. Exit 0 = pass."""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta

T = tempfile.mkdtemp(prefix="clash-")
os.environ["LANES_STATE_DIR"] = os.path.join(T, "state-pc1")
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
import clash as C  # noqa: E402
import fullscan_lock as L  # noqa: E402

fails = 0


def check(ok, what):
    global fails
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        fails += 1


def git(repo, *a):
    return subprocess.run(["git", "-C", repo] + list(a), capture_output=True, text=True).stdout.rstrip()


def on(pc):
    """act as that PC: its own Lanes state folder (the board clone is in its conf)"""
    C.LOCAL_DIR = os.path.join(T, "state-" + pc, "clash")


def main():
    bare = os.path.join(T, "remote.git")
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", bare], check=True)
    clones = {}
    for name in ("pc1", "pc2"):
        c = os.path.join(T, name)
        subprocess.run(["git", "clone", "-q", bare, c], check=True, capture_output=True)
        for k, v in (("user.name", "t"), ("user.email", "t@example.invalid"), ("core.hooksPath", os.path.join(T, "nohooks"))):
            git(c, "config", k, v)
        clones[name] = c
    a = clones["pc1"]
    with open(os.path.join(a, "README.md"), "w") as f:
        f.write("board\n")
    git(a, "add", "README.md"); git(a, "commit", "-q", "-m", "start"); git(a, "push", "-q", "-u", "origin", "main")
    git(clones["pc2"], "pull", "-q")
    c1 = {"role": "HOME", "machine_name": "PC1", "board": clones["pc1"]}
    c2 = {"role": "DEV", "machine_name": "PC2", "board": clones["pc2"]}

    problems = C.audit()
    check(not problems, "every command, hook, tool and extra has a row, and every job is enforced"
          + ("" if not problems else ": " + "; ".join(problems[:3])))
    import features as F
    F.FEATURES["pretend_new_extra"] = {"label": "x", "set": "everyday", "what": "x", "link": "https://example.invalid"}
    try:
        check(any("pretend_new_extra" in p for p in C.audit()) and any("pretend_new_extra" in p for p in F.lint()),
              "a new extra with no row is refused (the audit, and features.py lint that release runs)")
    finally:
        del F.FEATURES["pretend_new_extra"]
    check(C.reach("fullscan") == C.EVERY and C.reach("update") == C.PC, "the full scan is held on GitHub, an update on the PC only")
    check(C.scope("gr", "village", "gr", "re2") is None and C.scope("gr", "all", "gr", "re2") == C.EVERY,
          "research on two projects is fine; the whole sweep beside one project is not")

    with open(os.path.join(clones["pc2"], "README.md"), "w") as f:
        f.write("a session is editing this\n")
    on("pc2")
    ok, line = C.take(c2, "fullscan", session="S2")
    check(ok, "PC2 starts a full scan: " + line)
    check(git(clones["pc1"], "fetch", "-q") == "" and "machine = PC2" in git(clones["pc1"], "show", "origin/main:" + L.LOCK_REL),
          "its lock is on GitHub where the old full-scan lock lives")
    on("pc1")
    ok, line = C.take(c1, "fullscan", session="S1")
    check(not ok and "PC2" in line, "PC1 may not start a second full scan: " + line)
    ok, line = C.take(c1, "gr", session="S1")
    check(not ok, "nor one of its parts (/gr) on the other PC")
    check(L.take(c1) == 1, "the old full-scan lock tool sees the same claim")
    ok, line = C.take(c1, "theme", session="S1")
    check(ok, "something that does not clash (the terminal look) starts fine")
    on("pc2")
    ok, line = C.take(c2, "gr", session="S2")
    check(ok, "the full scan's own session runs its /gr part")
    ok, line = C.take(c2, "gu", session="OTHER")
    check(not ok, "another session on PC2 may not start /gu during the full scan")
    check(open(os.path.join(clones["pc2"], "README.md")).read() == "a session is editing this\n"
          and git(clones["pc2"], "rev-parse", "--abbrev-ref", "HEAD") == "main", "the board clone's working tree is untouched")

    gone = C.release_session(c2, "S2")
    check(len(gone) == 2, "the session's end gives back both its locks (%d)" % len(gone))
    git(clones["pc1"], "fetch", "-q")
    check(git(clones["pc1"], "ls-tree", "-r", "--name-only", "origin/main", "handover") == "", "and GitHub holds none")

    # research per project
    on("pc1")
    check(C.take(c1, "gr", "village", session="S1")[0], "PC1 researches Village")
    on("pc2")
    check(C.take(c2, "gr", "re2", session="S2")[0], "PC2 researches RE2 at the same time")
    check(not C.take(c2, "gr", "village", session="S3")[0], "a second Village research run is refused")
    check(not C.take(c2, "gr", session="S3")[0], "and so is the whole sweep")
    on("pc1"); C.release(c1, "gr", "village")
    on("pc2"); C.release(c2, "gr", "re2")

    # a same-PC-only job
    on("pc1")
    check(C.take(c1, "update", session="S1")[0], "PC1 updates Lanes")
    check(not C.take(c1, "update", session="S9")[0], "a second update on PC1 is refused")
    check(not C.take(c1, "setup", session="S9")[0], "so is setup on PC1 during the update")
    on("pc2")
    check(C.take(c2, "update", session="S2")[0], "PC2 may update at the same time (its own install)")
    C.release(c2, "update")
    on("pc1"); C.release(c1, "update")

    # left-over locks
    old = (datetime.now().astimezone() - timedelta(hours=C.STALE_H + 1)).strftime(C.TIME_FMT)
    os.makedirs(C.LOCAL_DIR, exist_ok=True)
    with open(os.path.join(C.LOCAL_DIR, "update.lock"), "w") as f:
        f.write(C.lock_text({"machine": "PC1", "since": old, "job": "update", "project": "all", "session": "X"}))
    check(C.take(c1, "update", session="S1")[0], "a lock over %d h old does not block" % C.STALE_H)
    C.release(c1, "update")
    with open(os.path.join(C.LOCAL_DIR, "menu.lock"), "w") as f:
        f.write(C.lock_text({"machine": "PC1", "since": C.now_text(), "job": "menu", "project": "all",
                             "session": "tool-999999"}))
    check(C.take(c1, "menu", session="tool-%d" % os.getpid())[0], "a program that is gone holds nothing")
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        check(not C.take(c1, "menu", session="tool-%d" % child.pid)[0],
              "while this program holds the keys, another program on the PC may not press them")
    finally:
        child.kill()
    C.release(c1, "menu")

    # the hook
    conf = os.path.join(T, "pc2.conf")
    with open(conf, "w") as f:
        f.write("machine_name = PC2\nrole = DEV\nboard = %s\nclash_guard = on\n" % clones["pc2"].replace("\\", "/"))
    env = dict(os.environ, LANES_CONFIG=conf, LANES_STATE_DIR=os.path.join(T, "state-pc2"))
    on("pc1")
    C.take(c1, "fullscan", session="S1")
    hook = os.path.join(os.path.dirname(TOOLS), "hooks", "clash-guard.py")

    def run(payload):
        return subprocess.run([sys.executable, hook], input=json.dumps(payload), capture_output=True, text=True, env=env)

    r = run({"hook_event_name": "UserPromptSubmit", "prompt": "/fullscan", "session_id": "H"})
    check(r.returncode == 2 and "PC1" in r.stderr, "the hook refuses a typed /fullscan on PC2 with one line")
    r = run({"hook_event_name": "PreToolUse", "tool_name": "Skill", "tool_input": {"skill": "lanes:gu"}, "session_id": "H"})
    check(r.returncode == 2, "and Claude starting the /gu skill itself")
    r = run({"hook_event_name": "UserPromptSubmit", "prompt": "please look at the logs", "session_id": "H"})
    check(r.returncode == 0, "an ordinary prompt passes")
    r = run({"hook_event_name": "UserPromptSubmit", "prompt": "/lanes:gr force", "session_id": "H"})
    check(r.returncode == 0, "\"force\" starts it anyway")
    r = run({"hook_event_name": "SessionEnd", "session_id": "H"})
    check(r.returncode == 0 and not os.listdir(os.path.join(T, "state-pc2", "clash")), "its end gives the forced lock back")
    on("pc1"); C.release(c1, "fullscan")

    print("clash guard: %s" % ("all checks pass" if not fails else "%d check(s) FAILED" % fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
