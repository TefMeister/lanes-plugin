#!/usr/bin/env python3
"""briefcache.py - a slow start-up check, shown from its last result at once and refreshed in the background (0.103.0).

Why: the board summary takes over a minute on a busy PC (75 s measured 2026-11-06) and a start-up hook gets 20 s, so in
Run 5 it was cut off in every fresh window (3 of 3) and sessions started with no board summary at all.

    python briefcache.py show <name> [--max-age-h=N] -- <command...>
        prints the last result of <command> (with how old it is), then starts a refresh in the background that
        outlives the window; the next session start shows that. Nothing kept yet: says so (the refresh is started).
    python briefcache.py refresh <name> -- <command...>    run <command> now and keep its output (what show starts)

    python briefcache.py show <name> --wait-s=N [--own] -- <command...>      (0.107.0)
        the same, but waits up to N seconds for the fresh result and prints THAT when it arrives in time (no "from the
        last check" line); only when it does not, the last result is printed with its age. For checks a session
        should see fresh when the PC allows it (the save light, the reminders that read GitHub): on a busy start-up
        they were cut off by their time limit and the session saw nothing at all (dev PC, 2026-11-10: the save light
        ran past 90 s and the "11 jobs wait for this PC" reminder never arrived, though both take 20-40 s alone).
        --own: this window always starts its own run (for a check that also records something for this session).

Kept in the Lanes state folder as brief-<name>.txt. A result older than --max-age-h (default 24) is not shown.
Never raises; any failure prints nothing.
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "lanes")
REFRESH_TIMEOUT_S = 600
DEFAULT_MAX_AGE_H = 24


def path_of(name):
    return os.path.join(STATE_DIR, "brief-%s.txt" % "".join(ch for ch in name if ch.isalnum() or ch in "-_"))


def age_words(seconds):
    m = int(seconds // 60)
    if m < 1:
        return "just now"
    if m < 60:
        return "%d min ago" % m
    return "%d h ago" % (m // 60)


def refresh(name, cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=REFRESH_TIMEOUT_S)
    except Exception:  # noqa: BLE001
        return 1
    out = (r.stdout or "").rstrip("\n")
    if not out:
        return 1
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = path_of(name) + ".new"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(out + "\n")
    os.replace(tmp, path_of(name))
    return 0


FRESH_ENOUGH_S = 300            # several windows opened together start one refresh between them, not one each


def start_refresh(name, cmd, own=False):
    """start the background run; returns the time the run that is now under way began (this one, or another
    window's started a moment ago)"""
    marker = path_of(name) + ".started"
    try:
        began = os.path.getmtime(marker)
        if not own and time.time() - began < FRESH_ENOUGH_S:
            return began
    except OSError:
        pass
    began = time.time()
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(marker, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    import endwork   # its twice-started helper is the one that outlives a closing window
    endwork.outlive(os.path.abspath(__file__), ["refresh", name, "--"] + cmd)
    return began


POLL_S = 0.5


def show_waiting(name, cmd, max_age_h, wait_s, own):
    """the fresh result when it arrives within wait_s, else the last one with its age (see the module text)"""
    p = path_of(name)
    try:
        before = os.path.getmtime(p)
    except OSError:
        before = 0.0
    try:
        began = start_refresh(name, cmd, own)
    except Exception:  # noqa: BLE001
        began = time.time()
    deadline = time.time() + wait_s
    fresh = False
    while time.time() < deadline:
        try:
            m = os.path.getmtime(p)
            if m > before and m >= began - 1:
                fresh = True
                break
        except OSError:
            pass
        time.sleep(POLL_S)
    try:
        age = time.time() - os.path.getmtime(p)
        with open(p, encoding="utf-8") as f:
            text = f.read().rstrip("\n")
    except OSError:
        age, text = None, ""
    if fresh and text:
        print(text)
    elif text and age is not None and age <= max_age_h * 3600:
        print("(this check was still running after %d s, so this is its last result, from %s; the fresh one is kept "
              "for the next session)" % (wait_s, age_words(age)))
        print(text)
    else:
        print("(this check was still running after %d s and no recent result is kept; it finishes in the background "
              "for the next session)" % wait_s)
    return 0


def show(name, cmd, max_age_h):
    p = path_of(name)
    try:
        age = time.time() - os.path.getmtime(p)
        with open(p, encoding="utf-8") as f:
            text = f.read().rstrip("\n")
    except OSError:
        age, text = None, ""
    if text and age is not None and age <= max_age_h * 3600:
        print("(from the last check, %s; a fresh one is running in the background for the next session)" % age_words(age))
        print(text)
    else:
        print("(no recent result kept yet: a fresh check is running in the background for the next session)")
    try:
        start_refresh(name, cmd)
    except Exception:  # noqa: BLE001
        pass
    return 0


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    if len(argv) < 2 or "--" not in argv:
        print(__doc__)
        return 2
    cut = argv.index("--")
    head, cmd = argv[:cut], argv[cut + 1:]
    mode, name = head[0], head[1]
    max_age_h, wait_s, own = DEFAULT_MAX_AGE_H, 0.0, "--own" in head[2:]
    for a in head[2:]:
        try:
            if a.startswith("--max-age-h="):
                max_age_h = float(a.split("=", 1)[1])
            if a.startswith("--wait-s="):
                wait_s = float(a.split("=", 1)[1])
        except ValueError:
            pass
    if not cmd:
        return 2
    sys.path.insert(0, HERE)
    try:
        if mode == "show":
            return show_waiting(name, cmd, max_age_h, wait_s, own) if wait_s > 0 else show(name, cmd, max_age_h)
        if mode == "refresh":
            import endwork
            endwork.hide_child_windows()   # started with no console: bash would open a visible window (Run 6)
            return refresh(name, cmd)
    except Exception:  # noqa: BLE001
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
