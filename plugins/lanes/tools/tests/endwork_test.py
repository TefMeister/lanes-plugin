"""endwork_test.py - the end helper's turn file, and a start-up check that waits for its fresh result (0.107.0).

1. endwork.py: only one end runs at a time on a PC, kept by a turn file. Found 2026-11-10 on the dev PC: the file was
   never removed on Windows (it was deleted while still open, which Windows refuses), and "is an end running" asked
   only whether the program number in it is alive; Windows hands a finished program's number to the next program, so
   a four-hour-old end read as "still running" and a real end behind it would have waited ten minutes and been skipped.
2. briefcache.py show --wait-s: a slow start-up check prints its fresh result when it comes in time, and otherwise its
   last result, marked with its age (the session used to get nothing when the check ran past its time limit).
Everything happens in a temp folder. Exit 0 = pass."""
import json
import os
import subprocess
import sys
import tempfile
import time

T = tempfile.mkdtemp(prefix="endwork-")
os.environ["LANES_STATE_DIR"] = T
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
import endwork as E  # noqa: E402

fails = 0
SLOW_S = 6           # the pretend slow check
SHORT_WAIT_S = 1
LONG_WAIT_S = 60


def check(ok, what):
    global fails
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        fails += 1


def turn_file():
    check(E.take_turn(), "an end takes its turn")
    check(os.path.isfile(E.RUNNING) and E.running_pid() == os.getpid(), "while it runs, the turn file names it")
    E.give_turn()
    check(not os.path.exists(E.RUNNING), "when it is done the turn file is gone (Windows: closed first, then deleted)")

    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        with open(E.RUNNING, "w", encoding="utf-8") as f:
            json.dump({"pid": child.pid, "since": time.time()}, f)
        check(E.running_pid() == child.pid, "a turn file of a moment ago whose program is alive: an end is running")
        with open(E.RUNNING, "w", encoding="utf-8") as f:
            json.dump({"pid": child.pid, "since": time.time() - E.TURN_MAX_AGE_S - 60}, f)
        check(E.running_pid() == 0, "an old turn file is left over, even when its number belongs to a live program")
        check(E.take_turn(), "and the next end takes its turn at once instead of waiting behind it")
        E.give_turn()
    finally:
        child.kill()
    with open(E.RUNNING, "w", encoding="utf-8") as f:
        json.dump({"pid": 999999, "since": time.time()}, f)
    check(E.running_pid() == 0, "a turn file whose program is gone is left over")
    os.remove(E.RUNNING)


def show(name, wait_s, code):
    r = subprocess.run([sys.executable, os.path.join(TOOLS, "briefcache.py"), "show", name, "--own",
                        "--wait-s=%d" % wait_s, "--", sys.executable, "-c", code],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=LONG_WAIT_S + 60)
    return r.stdout.strip()


def waiting_check():
    out = show("quick", LONG_WAIT_S, "print('fresh result one')")
    check(out == "fresh result one", "a check that answers in time is shown fresh, with no 'last result' line")
    began = time.time()
    out = show("slow", SHORT_WAIT_S, "import time; time.sleep(%d); print('slow result')" % SLOW_S)
    check("no recent result is kept" in out and time.time() - began < SLOW_S,
          "a check that is too slow, with nothing kept: one line saying so, and the hook is not held up")
    deadline = time.time() + LONG_WAIT_S
    kept = os.path.join(T, "brief-slow.txt")
    while time.time() < deadline and not os.path.isfile(kept):
        time.sleep(0.5)
    check(os.path.isfile(kept), "the slow check still finishes in the background and its result is kept")
    out = show("slow", SHORT_WAIT_S, "import time; time.sleep(%d); print('slow result')" % SLOW_S)
    check("this is its last result" in out and "slow result" in out,
          "the next time it is too slow, the kept result is shown, marked as the last one")
    time.sleep(SLOW_S + 3)     # let the last background run end before the temp folder goes


def main():
    turn_file()
    waiting_check()
    print("endwork: %s" % ("all checks pass" if not fails else "%d check(s) FAILED" % fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
