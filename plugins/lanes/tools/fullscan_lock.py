"""fullscan_lock.py - the full scan runs on ONE PC, and never twice at once (0.101.0, 2026-11-05, feature `fullscan_guard`).

The maintainer, 2026-11-05: "what happens if Fullscan is ran on both PCs at the same time? ... can you set up a guard that
prevents that from happening. and really the way i wish it could work and be set up is to have the need to run fullscan
only on the dev pc". Two runs at once double the research, rewrite the same notes, front pages and descriptions against
each other, dig the same shelves twice, and could publish one download twice.

    python fullscan_lock.py here       exit 0 = this PC may run the full scan; 1 = not here (one line says why)
    python fullscan_lock.py take       claim the run on the board (GitHub). exit 0 = ours; 1 = another run holds it
    python fullscan_lock.py release    give the claim back (only this PC's own)
    python fullscan_lock.py status     who holds it, since when

WHICH PC. Any PC (the maintainer, 2026-11-05: the full scan "may run on the home PC; it is only blocked while another
run is going anywhere"). `fullscan_here = no` in lanes.conf keeps it off one PC for good.
The general clash guard (tools/clash.py, 2026-11-05) now takes this lock for the full scan, through the same file and
the same push; `here` and this file's own take/release still work. The switch is `clash_guard` (was `fullscan_guard`).

THE LOCK. One file on the board, `handover/fullscan.lock` (machine, when). It is committed straight onto the board's
origin/main through a throwaway index and pushed, so the working tree, the index and the local branch of the board clone
are never touched (another session may have work in progress there). A push is all-or-nothing on GitHub, so two PCs
taking it at the same moment cannot both win: the loser's push is refused, it fetches, sees the other's claim and stops.
A claim older than STALE_H counts as left over from a run that was cut off, and may be taken over (said so).
"""
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

LOCK_REL = "handover/fullscan.lock"
STALE_H = 12
TIME_FMT = "%Y-%m-%d %H:%M %z"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def conf_path():
    if os.environ.get("LANES_CONFIG"):
        return os.environ["LANES_CONFIG"]
    for p in (os.path.expanduser("~/.claude/lanes.conf"), os.path.expanduser("~/.config/lanes/lanes.conf")):
        if os.path.isfile(p):
            return p
    return ""


def conf():
    out, p = {}, conf_path()
    if not p:
        return out
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.match(r"^\s*([A-Za-z0-9_.]+)\s*=\s*(.*?)\s*(?:\s#.*)?$", line.rstrip("\r\n"))
                if m and not line.lstrip().startswith("#"):
                    out.setdefault(m.group(1), m.group(2).strip().strip('"').strip("'"))
    except OSError:
        pass
    return out


def git(repo, *args, env=None, timeout=60):
    try:
        r = subprocess.run(["git", "-C", repo] + list(args), capture_output=True, text=True, timeout=timeout,
                           env=env, creationflags=NO_WINDOW, encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    return r.returncode == 0, (r.stdout or "").strip() if r.returncode == 0 else (r.stderr or r.stdout or "").strip()


def me(c):
    return c.get("machine_name") or c.get("role") or "this PC"


def here(c=None):
    """(may_run, reason)"""
    c = conf() if c is None else c
    v = c.get("fullscan_here", "").lower()
    if v in ("yes", "on", "true", "1"):
        return True, "fullscan_here = yes"
    if v in ("no", "off", "false", "0"):
        return False, "the full scan is switched off on this PC (fullscan_here = no in lanes.conf)"
    # 2026-11-05, the same day: the maintainer changed the job. Any PC may run it; the only block is another run going
    # anywhere (the lock below). `fullscan_here = no` remains for a PC that should never run it.
    return True, "any PC may run it"


def board(c):
    b = c.get("board", "")
    return b if b and os.path.isdir(os.path.join(b, ".git")) else ""


def read_lock(b):
    """(machine, when-datetime or None) from GitHub's copy, or (None, None) when nobody holds it"""
    ok, text = git(b, "show", "origin/main:" + LOCK_REL)
    if not ok:
        return None, None
    who = re.search(r"^machine = (.+)$", text, re.M)
    when = re.search(r"^since = (.+)$", text, re.M)
    try:
        t = datetime.strptime(when.group(1).strip(), TIME_FMT) if when else None
    except ValueError:
        t = None
    return (who.group(1).strip() if who else "another PC"), t


def age_h(t):
    return (datetime.now(timezone.utc) - t).total_seconds() / 3600 if t else 1e9


def push_change(b, content, message, rel=None):
    """commit one change to `rel` (LOCK_REL by default) on top of origin/main without touching the clone, and push.
    content None = remove. The clash guard (tools/clash.py) uses it for every lock both PCs must see."""
    rel = rel or LOCK_REL
    ok, _ = git(b, "rev-parse", "-q", "--verify", "origin/main")
    if not ok:
        return False
    with tempfile.TemporaryDirectory() as t:
        env = dict(os.environ, GIT_INDEX_FILE=os.path.join(t, "index"))
        if not git(b, "read-tree", "origin/main", env=env)[0]:
            return False
        if content is None:
            git(b, "update-index", "--force-remove", rel, env=env)
        else:
            p = os.path.join(t, "lock")
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
            ok, blob = git(b, "hash-object", "-w", p)
            if not ok or not git(b, "update-index", "--add", "--cacheinfo", "100644,%s,%s" % (blob, rel), env=env)[0]:
                return False
        ok, tree = git(b, "write-tree", env=env)
        if not ok:
            return False
        ok, commit = git(b, "commit-tree", tree, "-p", "origin/main", "-m", message)
        if not ok:
            return False
    ok, _ = git(b, "push", "-q", "origin", commit + ":refs/heads/main", timeout=60)
    git(b, "fetch", "-q", "origin")
    return ok


def take(c):
    b = board(c)
    if not b:
        print("FULLSCAN LOCK: no board clone (board = in lanes.conf), so no lock could be taken; carrying on without one.")
        return 0
    for _attempt in range(3):
        if not git(b, "fetch", "-q", "origin", timeout=60)[0]:
            print("FULLSCAN LOCK: GitHub could not be reached, so it cannot be checked that no other full scan is running. "
                  "Stop, and try again when GitHub answers.")
            return 1
        who, t = read_lock(b)
        if who and who != me(c) and age_h(t) < STALE_H:
            print("FULLSCAN LOCK: a full scan is already running on %s (since %s). Not starting a second one."
                  % (who, t.strftime("%H:%M") if t else "an unknown time"))
            return 1
        note = ""
        if who and who != me(c):
            note = " (took over a claim of %s that was over %d h old: that run was cut off)" % (who, STALE_H)
        body = ("# Written by the lanes plugin (tools/fullscan_lock.py). One full scan at a time; removed when it ends.\n"
                "machine = %s\nsince = %s\n" % (me(c), datetime.now().astimezone().strftime(TIME_FMT)))
        if push_change(b, body, "fullscan: %s starts a full scan (lock)" % me(c)):
            print("FULLSCAN LOCK: taken by %s%s. Release it at the end: python fullscan_lock.py release" % (me(c), note))
            return 0
    print("FULLSCAN LOCK: could not push the claim to GitHub. Stop, and try again in a minute.")
    return 1


def release(c):
    b = board(c)
    if not b:
        return 0
    git(b, "fetch", "-q", "origin", timeout=60)
    who, _t = read_lock(b)
    if not who:
        print("FULLSCAN LOCK: nobody held it.")
        return 0
    if who != me(c):
        print("FULLSCAN LOCK: held by %s, not this PC; left alone." % who)
        return 1
    ok = push_change(b, None, "fullscan: %s finished the full scan (lock released)" % me(c))
    print("FULLSCAN LOCK: released." if ok else "FULLSCAN LOCK: could NOT be released (GitHub?); it counts as left over "
          "after %d h, or run this again." % STALE_H)
    return 0 if ok else 1


def status(c):
    b = board(c)
    if b:
        git(b, "fetch", "-q", "origin", timeout=60)
    who, t = read_lock(b) if b else (None, None)
    ok, why = here(c)
    print("FULLSCAN: %s here (%s)." % ("may run" if ok else "does not run", why))
    print("FULLSCAN LOCK: " + ("held by %s since %s%s" % (who, t.strftime("%Y-%m-%d %H:%M") if t else "?",
                                                         " (left over)" if age_h(t) >= STALE_H else "")
                               if who else "free"))
    return 0


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    cmd = argv[1] if len(argv) > 1 else "status"
    c = conf()
    if cmd == "here":
        ok, why = here(c)
        if not ok:
            print("FULLSCAN: not on this PC - %s." % why)
        return 0 if ok else 1
    if cmd == "take":
        return take(c)
    if cmd == "release":
        return release(c)
    if cmd == "status":
        return status(c)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
