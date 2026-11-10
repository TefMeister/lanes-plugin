#!/usr/bin/env python3
"""endwork.py - a session's end steps, done by a program that outlives the window (lanes 0.103.0).

Why: Claude Code gives a plugin's SessionEnd hooks 1.5 seconds in all, whatever time the hooks ask for (the default
budget only counts hooks in settings files; measured from the 2026-11-06 build). Anything that talks to GitHub takes
longer, so on both PCs the end report and the giving back of clash locks were cut off at every close, in real
windows too (Run 5, 2026-11-06): the other PC saw the session as never ended, and its job stayed blocked for 12 h.

So the end hook only starts this program and returns. It hands itself on once more before it works ("hop"): a closing
Claude Code ends the hook and whatever it started, but not a program whose parent has already gone (measured
2026-11-06, n=1: a twice-started helper finished 12 s after the window, a once-started one did not).

    python endwork.py spawn [--session=ID]   the SessionEnd hook: start the end steps in the background, return at once
    python endwork.py run [--session=ID]     the end steps themselves, in order (what spawn starts)
    python endwork.py finish                 session start: whatever an earlier end left undone (left-over locks)
    python endwork.py status                 is an end running now, and how the last one went

The end steps, in order (each only when its extra is on): give back this PC's clash locks on GitHub (clash.py sweep),
report the end on the board (handover.py end --write), look at GitHub again (handover.py refresh), bring copies that
are only behind level with it (handover.py level), shelve logs for Gold Digger (gd.py shelve --all --quiet).
Only one end runs at a time on a PC (two windows closing together queue up). Every line goes to endwork.log.
Never raises; a failed step is logged and the next one still runs.
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "lanes")
LOG = os.path.join(STATE_DIR, "endwork.log")
RUNNING = os.path.join(STATE_DIR, "endwork.running")
LOG_KEEP_LINES = 400
WAIT_FOR_OTHER_S = 600          # a second window closing waits this long for the first one's end steps
STEP_TIMEOUT_S = 300            # one end step (the save scan of ~300 repos takes about half a minute)
TURN_MAX_AGE_S = 45 * 60        # no end takes this long (five steps of at most 300 s): an older turn file is left over
DETACHED, NEW_GROUP, NO_WINDOW = 0x8, 0x200, 0x08000000


def log(line):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        try:
            with open(LOG, encoding="utf-8") as f:
                kept = f.read().splitlines()[-LOG_KEEP_LINES:]
        except OSError:
            kept = []
        kept.append("%s %s" % (datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), line))
        with open(LOG, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(kept) + "\n")
    except OSError:
        pass


def session_arg(argv):
    for a in argv:
        if a.startswith("--session="):
            return a[len("--session="):]
    return os.environ.get("CLAUDE_CODE_SESSION_ID", "")


def start_detached(args, script=None):
    """start `script args` (default: this file) in the background, with no window, not waiting for it"""
    kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
    if os.name == "nt":
        kw["creationflags"] = DETACHED | NEW_GROUP | NO_WINDOW
    else:
        kw["start_new_session"] = True
    subprocess.Popen([sys.executable, os.path.abspath(script or __file__)] + list(args), **kw)


def hide_child_windows():
    """Every program this helper starts runs with a hidden window. The helper itself is started with no console at all
    (that is what lets it outlive a closing window), and Windows gives a console program started from such a process
    a NEW, visible window: Run 6 (2026-11-06), a black bash window popped up at session start. A child started with
    CREATE_NO_WINDOW gets a hidden console instead, and its own children share it. Windows only; harmless twice."""
    if os.name != "nt" or getattr(subprocess.Popen, "_lanes_hidden", False):
        return
    plain = subprocess.Popen

    class Hidden(plain):
        _lanes_hidden = True

        def __init__(self, *a, **kw):
            flags = kw.get("creationflags", 0) or 0
            if not flags & DETACHED:
                kw["creationflags"] = flags | NO_WINDOW
            super().__init__(*a, **kw)
    subprocess.Popen = Hidden


def outlive(script, args):
    """run `script args` so it outlives the window that asked for it: through a helper that starts it and exits"""
    start_detached(["relay", os.path.abspath(script)] + list(args))


def alive(pid):
    try:
        import clash
        return clash.pid_alive(pid)
    except Exception:
        return False


def running_pid():
    """the program number of an end that is running now, else 0. A turn file older than TURN_MAX_AGE_S is left over
    whatever its number says: Windows hands a finished program's number to the next program that starts, so "is that
    number alive" alone called a four-hour-old end "still running" (dev PC, 2026-11-10: the number had gone to a
    Windows search helper), and a real end behind it would have waited ten minutes and then been skipped."""
    try:
        with open(RUNNING, encoding="utf-8") as f:
            d = json.load(f)
        pid, since = int(d.get("pid", 0)), float(d.get("since", 0))
    except (OSError, ValueError, AttributeError, TypeError):
        return 0
    if time.time() - since > TURN_MAX_AGE_S:
        return 0
    return pid if pid and alive(pid) else 0


def take_turn():
    """True when this end may run now; waits for another PC-local end that is still running."""
    deadline = time.time() + WAIT_FOR_OTHER_S
    while True:
        try:
            fd = os.open(RUNNING, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"pid": os.getpid(), "since": time.time()}, f)
            return True
        except FileExistsError:
            if not running_pid():          # left by an end that was killed: take it over
                try:
                    os.remove(RUNNING)
                except OSError:
                    pass
                continue
            if time.time() > deadline:
                return False
            time.sleep(2)
        except OSError:
            return True                     # cannot keep the turn file: run anyway rather than skip the end


def give_turn():
    """Take the turn file away when it is this program's. Read first, CLOSE, then delete: Windows refuses to delete a
    file that is still open, so until 0.107.0 the file was never removed there and every end left its number behind."""
    try:
        with open(RUNNING, encoding="utf-8") as f:
            mine = int(json.load(f).get("pid", 0)) == os.getpid()
        if mine:
            os.remove(RUNNING)
    except (OSError, ValueError, AttributeError):
        pass


def feature_on(name):
    try:
        import features
        return features.is_on(name)
    except Exception:
        return True


def step(label, args):
    try:
        r = subprocess.run([sys.executable] + args, capture_output=True, text=True, timeout=STEP_TIMEOUT_S,
                           encoding="utf-8", errors="replace")
        tail = " | ".join(l.strip() for l in (r.stdout or "").splitlines()[-2:] if l.strip())
        log("%s: exit %d%s" % (label, r.returncode, (" - " + tail[:300]) if tail else ""))
    except Exception as e:  # noqa: BLE001
        log("%s: FAILED (%s)" % (label, type(e).__name__))


def conf_exists():
    return os.path.isfile(os.environ.get("LANES_CONFIG") or os.path.join(os.path.expanduser("~"), ".claude", "lanes.conf"))


def run(session):
    if not conf_exists():
        return 0
    if not take_turn():
        log("end of %s: another end was still running after %d s; skipped (the next start gives back left-over locks)"
            % (session or "?", WAIT_FOR_OTHER_S))
        return 1
    try:
        log("end of %s: started" % (session or "?"))
        if feature_on("clash_guard"):
            try:   # this PC's files first, in case the clash guard's own end hook was cut off too
                import clash
                for line in clash.release_session(clash.FL.conf(), session, local_only=True):
                    log("lock file here: " + line)
            except Exception as e:  # noqa: BLE001
                log("lock files here: FAILED (%s)" % type(e).__name__)
            step("locks given back", [os.path.join(HERE, "clash.py"), "sweep"])
        if os.environ.get("LANES_HANDOVER", "1") != "0":
            step("end reported", [os.path.join(HERE, "handover.py"), "end", "--write", "--session=" + session])
        if os.environ.get("LANES_HANDOVER", "1") != "0":
            # after the end report, never before it: the box's "SAVED" is only as fresh as each copy's last look (Run 5 D7)
            step("GitHub looked at again", [os.path.join(HERE, "handover.py"), "refresh"])
        if os.environ.get("LANES_HANDOVER", "1") != "0" and feature_on("keep_level"):
            # after the look at GitHub: copies that are only behind are fast-forwarded (0.107.0; handover.py level)
            step("copies brought level", [os.path.join(HERE, "handover.py"), "level"])
        if feature_on("gold_digger"):
            step("logs shelved", [os.path.join(HERE, "gd.py"), "shelve", "--all", "--quiet"])
        log("end of %s: done" % (session or "?"))
    finally:
        give_turn()
    return 0


def finish():
    """Session start: an end that is running now is left to finish; otherwise give back left-over locks."""
    if running_pid():
        print("END STEPS: the last session's end steps are still running in the background (they finish by themselves).")
        return 0
    if not feature_on("clash_guard"):
        return 0
    try:
        import clash
        lines = clash.sweep(clash.FL.conf())
    except Exception:  # noqa: BLE001
        return 0
    for line in lines:
        print(line)
        log("start: " + line)
    return 0


def status():
    pid = running_pid()
    print("END STEPS: running now (program %d)." % pid if pid else "END STEPS: none running.")
    try:
        with open(LOG, encoding="utf-8") as f:
            tail = f.read().splitlines()[-6:]
        print("\n".join("  " + l for l in tail))
    except OSError:
        print("  (no end has run on this PC yet)")
    return 0


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    cmd = argv[0] if argv else "status"
    if cmd in ("relay", "run", "finish"):   # the background ones: nothing they start may open a window
        hide_child_windows()
    if cmd == "relay" and len(argv) > 1:     # the middle helper of outlive(): start the real one and exit
        try:
            start_detached(argv[2:], script=argv[1])
        except Exception:  # noqa: BLE001
            pass
        return 0
    session = session_arg(argv[1:])
    try:
        if cmd == "spawn":
            start_detached(["hop", "--session=" + session])
            return 0
        if cmd == "hop":
            start_detached(["run", "--session=" + session])
            return 0
        if cmd == "run":
            return run(session)
        if cmd == "finish":
            return finish()
        if cmd == "status":
            return status()
    except Exception as e:  # noqa: BLE001 - nothing here may stop a session from ending or starting
        log("%s: FAILED (%s)" % (cmd, type(e).__name__))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
