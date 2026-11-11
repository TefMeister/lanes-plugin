#!/usr/bin/env python3
"""scan_priority.py - the full scan goes first: every other session on this PC saves, stops and waits until it has
finished (0.110.0, 2026-11-11, feature `scan_priority`).

The maintainer, 2026-11-11: "add a guard to the fullscan command and all the commands it has in it, to have priority
- so that when a session is already working on something on Keeper pc and Developer pc is modding stuff, then Keeper
pc will save safely what it's working on, but then stop and let the fullscan run until it's finished before starting
work again". And for the other PC: "it should be safe for Developer pc to just queue up saved files for Keeper pc,
without Keeper PC doing anything with them until fullscan has finished."

The clash guard (tools/clash.py) already keeps two scans, or a scan and one of its own parts, from running at once.
It says nothing to a session that is simply at work (writing a tool, a Keeper's round) when the scan starts, and the
scan tidies, saves and publishes the same files. This is that missing half.

    python scan_priority.py status           exit 0 = a full scan (or one of its parts) holds this PC; one line says which
    python scan_priority.py wait [--session <id>]
                                             return when it has ended. Run it as a BACKGROUND command: the session is
                                             called back when it returns, and carries on where it stopped
    python scan_priority.py lift             the PERSON's word: let the other sessions work beside this run after all
    python scan_priority.py beat <session>   (the hook) the session that runs the scan is alive

HOW IT HOLDS (hooks/scan-priority.py, run with the other tool guards)
  The scan's own session passes, and each of its tool calls is a heartbeat. Any OTHER session on this PC:
  1. at its first tool call after the scan started it is told, once: finish the step you are in, save it, say in one
     line that you wait, start `wait` in the background, do nothing more;
  2. GRACE_MIN minutes later every edit and every command that is not a save is refused until the scan has ended.
  Hand-overs from the other PC wait too: parcel.py answers "not yet" and takes them when the scan has ended, in order.
  The other PC itself is not held: it keeps working and handing over.

WHEN THE SCAN'S WINDOW DIES. Its lock on this PC would last STALE_H hours. Here it counts as ended once the scan's
session has made no tool call for QUIET_MIN minutes, so a crashed scan never freezes the PC for long.

WHICH RUNS HAVE PRIORITY. `scan_priority_jobs = fullscan, gd, gr, sr, od, gu, ch, gs` in lanes.conf (that is the
default: the full scan and every command it runs inside itself, also when one of them is run alone).
Tests set LANES_STATE_DIR and LANES_CONFIG. Never fails closed: an error here lets everything through.
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "lanes")
DIR = os.path.join(STATE_DIR, "scan-priority")
BEAT = os.path.join(DIR, "beat.json")
LIFT = os.path.join(DIR, "lift.json")
DEFAULT_JOBS = ("fullscan", "gd", "gr", "sr", "od", "gu", "ch", "gs")
GRACE_MIN = 10              # how long a working session has to finish its step and save, once told
QUIET_MIN = 45              # the scan's session silent this long = its window died; the hold ends
WAIT_POLL_S = 15            # how often `wait` looks
WAIT_MAX_H = 12             # `wait` gives up after this (the lock itself is stale by then)
REMIND_MIN = 4              # a told session that keeps working is told again this often, until the grace is over


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def priority_jobs(c):
    raw = (c or {}).get("scan_priority_jobs", "")
    names = [x.strip() for x in raw.split(",") if x.strip()] if raw else list(DEFAULT_JOBS)
    return set(names)


def lock_id(rec):
    """what tells one run from the next: the same job started again later is a new run"""
    return "%s|%s|%s|%s" % (rec.get("job"), rec.get("project"), rec.get("session"), rec.get("since"))


def beat(session, now=None):
    if session:
        _write(BEAT, {"session": session, "at": now or time.time()})


def lift(rec, now=None):
    _write(LIFT, {"lock": lock_id(rec), "at": now or time.time()})


def running(session="", c=None, now=None):
    """the lock of the priority run that holds this PC against `session`, or None.
    None when the run is this session's own, was lifted by the person, or its window died."""
    import clash
    import fullscan_lock as FL
    c = FL.conf() if c is None else c
    now = now or time.time()
    wanted = priority_jobs(c)
    lifted = _read(LIFT).get("lock")
    b = _read(BEAT)
    for rec in clash.local_locks():
        if rec.get("job") not in wanted or not rec.get("session") or rec["session"].startswith("tool-"):
            continue                                    # a lock with no session belongs to no window: nothing to wait for
        if clash.age_h(rec.get("when")) >= clash.STALE_H:
            continue
        if session and rec["session"] == session:
            continue
        if lock_id(rec) == lifted:
            continue
        started = rec["when"].timestamp() if rec.get("when") else now
        last = b.get("at", 0) if b.get("session") == rec["session"] else 0
        if now - max(started, last) > QUIET_MIN * 60:
            continue                                    # its window died without giving the lock back
        return rec
    return None


def is_holder(session, c=None):
    """whether `session` holds a priority run on this PC, however long it has been quiet (its next call is a
    heartbeat again: a scan may sit in one long step for longer than QUIET_MIN)"""
    import clash
    import fullscan_lock as FL
    if not session:
        return False
    wanted = priority_jobs(FL.conf() if c is None else c)
    return any(r.get("job") in wanted and r.get("session") == session and clash.age_h(r.get("when")) < clash.STALE_H
               for r in clash.local_locks())


def label(rec):
    import clash
    j = clash.JOBS.get(rec.get("job"), {})
    since = rec["when"].strftime("%H:%M") if rec.get("when") else "an unknown time"
    return "%s (started %s)" % (j.get("label", rec.get("job")), since)


def holding_line():
    """for programs that are no session (the hand-over receiver, the doorman): one plain line while a priority run
    holds this PC and the extra is on, else "". Never raises."""
    try:
        import features
        if not features.is_on("scan_priority"):
            return ""
        rec = running("")
        return ("%s is running on the Keeper; it takes this when the scan has ended" % label(rec)) if rec else ""
    except Exception:  # noqa: BLE001 - a hand-over must never be lost to an error here
        return ""


def marker_path(session):
    return os.path.join(DIR, "told-%s.json" % re.sub(r"[^\w.-]", "_", session or "none"))


def stage(session, rec, now=None):
    """('tell' | 'remind' | 'grace' | 'hold', minutes left of the grace) for a session that is not the scan's.
    'tell' exactly once per run; 'remind' now and then while the grace lasts; 'hold' once it is over."""
    now = now or time.time()
    path = marker_path(session)
    m = _read(path)
    if m.get("lock") != lock_id(rec):
        _write(path, {"lock": lock_id(rec), "told": now, "reminded": now})
        return "tell", GRACE_MIN
    left = GRACE_MIN - (now - m.get("told", now)) / 60.0
    if left <= 0:
        return "hold", 0
    if now - m.get("reminded", now) >= REMIND_MIN * 60:
        m["reminded"] = now
        _write(path, m)
        return "remind", left
    return "grace", left


def tidy(session):
    """the run ended: forget what this session was told, so the next run tells it afresh"""
    try:
        os.remove(marker_path(session))
    except OSError:
        pass


def main(argv):
    verb = argv[0] if argv else "status"
    session = ""
    if "--session" in argv:
        i = argv.index("--session")
        session = argv[i + 1] if i + 1 < len(argv) else ""
    if verb == "beat":
        beat(argv[1] if len(argv) > 1 else "")
        return 0
    if verb == "status":
        rec = running(session)
        print("SCAN PRIORITY: %s holds this PC; other sessions save and wait." % label(rec) if rec
              else "SCAN PRIORITY: no full scan is running on this PC.")
        return 0 if rec else 1
    if verb == "lift":
        rec = running("")
        if not rec:
            print("SCAN PRIORITY: nothing to lift, no full scan is running on this PC.")
            return 1
        lift(rec)
        print("SCAN PRIORITY: lifted for %s. Other sessions may work beside it; the next run holds again."
              % label(rec))
        return 0
    if verb == "wait":
        end = time.time() + WAIT_MAX_H * 3600
        waited = False
        while time.time() < end:
            if not running(session):
                tidy(session)
                print("SCAN PRIORITY: the full scan has ended%s. Carry on where you stopped: pull first, the scan may "
                      "have changed and uploaded files." % ("" if waited else " (or none was running)"))
                return 0
            waited = True
            time.sleep(WAIT_POLL_S)
        print("SCAN PRIORITY: still held after %d h; ask the person." % WAIT_MAX_H)
        return 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
