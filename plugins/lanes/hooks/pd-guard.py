"""pd-guard.py -- how many /pd sessions may run at once on this machine.

Wired as two hooks (see hooks/hooks.json):
  UserPromptSubmit : if the prompt starts with "/pd", check the lock. Full -> exit 2 (the prompt is blocked and the
                     reason is shown). Otherwise this session is added to the lock.
  SessionEnd       : take this session off the lock.

SEVERAL /pd AT ONCE (0.106.0, 2026-11-06, Tefa: "can you also set up the system where home pc can work on multiple pd
sessions but only one live game at the time?"). Until 0.105 this was a one-holder lock: two /pd runs shared one
working tree and fought over git. Now:
  * up to `pd_parallel` /pd sessions (lanes.conf, default 3; 1 = the old one-at-a-time) may run on this PC at once;
  * each works its OWN game: the live claim on the board (lane-claim.sh and lane-claim-guard.py) still refuses a
    second session on a claimed game, and a bare /pd's auto-pick skips claimed games;
  * a sweep over many games (`/pd skip:<name> ...`) still runs alone: it would walk into the others' games;
  * saves to the shared repos wait their turn: hooks/git-queue.py lets one git write run at a time on this PC, so
    two sessions never commit into each other's index.

The lock is a small JSON file {"holders": {session: {...}}}. A holder counts while younger than STALE_HOURS, so a
session that died without SessionEnd (power loss, killed terminal) does not wedge /pd forever. Override for a real
emergency: delete the lock file, or type "/pd force ..." -- the word "force" right after /pd clears the other holders
and says so out loud.

Scope: THIS MACHINE only. Another machine has its own copy and its own lock; across machines the live claim on the
board keeps two sessions off one game.
"""
import json
import os
import re
import sys
import time

# $LANES_PD_LOCK exists so the tests can never touch a live session's lock.
LOCK = os.environ.get("LANES_PD_LOCK") or os.path.join(
    os.path.expanduser("~"), ".claude", "pd-session.lock")
STALE_HOURS = 6
DEFAULT_PARALLEL = 3


def conf_parallel():
    """the `pd_parallel = N` value in lanes.conf, or None"""
    path = os.environ.get("LANES_CONFIG") or os.path.join(os.path.expanduser("~"), ".claude", "lanes.conf")
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return None
    found = re.findall(r"^\s*pd_parallel\s*=\s*(\d+)", text, re.M)
    return found[-1] if found else None


def parallel():
    """`pd_parallel = N` in lanes.conf ($LANES_PD_PARALLEL for the tests); default 3, never below 1"""
    v = os.environ.get("LANES_PD_PARALLEL") or conf_parallel()
    try:
        return max(1, int(v)) if v is not None else DEFAULT_PARALLEL
    except ValueError:
        return DEFAULT_PARALLEL


def read_holders():
    """{session: record} of the lock; the pre-0.106 one-holder file reads as one holder"""
    try:
        with open(LOCK, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    if isinstance(data, dict) and isinstance(data.get("holders"), dict):
        return data["holders"]
    if isinstance(data, dict) and data.get("session_id"):
        return {data["session_id"]: data}
    return {}


def write_holders(holders):
    try:
        if not holders:
            if os.path.exists(LOCK):
                os.remove(LOCK)
            return
        os.makedirs(os.path.dirname(LOCK), exist_ok=True)
        with open(LOCK, "w", encoding="utf-8") as f:
            json.dump({"holders": holders}, f, indent=1)
    except Exception:
        # A guard that cannot write its lock must not block work.
        pass


def live(holders, now):
    return {s: r for s, r in holders.items() if (now - r.get("started", 0)) / 3600.0 < STALE_HOURS}


def is_sweep(prompt):
    return any(w.startswith("skip:") for w in prompt.split()[1:])


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8-sig", "replace"))  # a BOM (PowerShell pipe) must not open the guard
    except Exception:
        return 0
    event = data.get("hook_event_name", "")
    sid = data.get("session_id", "")

    if event == "SessionEnd":
        holders = read_holders()
        if sid in holders:
            holders.pop(sid)
            write_holders(holders)
        return 0

    if event != "UserPromptSubmit":
        return 0
    prompt = (data.get("prompt") or "").strip()
    # "/lanes:pd" is the same command as "/pd"; until 0.25.1 the long form skipped this lock.
    if prompt.startswith("/lanes:pd"):
        prompt = "/" + prompt[len("/lanes:"):]
    if not (prompt == "/pd" or prompt.startswith("/pd ")):
        return 0

    now = time.time()
    force = prompt.split()[1:2] == ["force"]
    sweep = is_sweep(prompt)
    holders = live(read_holders(), now)
    others = {s: r for s, r in holders.items() if s != sid}
    limit = parallel()
    stolen = []
    if others and force:
        stolen = sorted(others)
        others = {}
    elif others:
        why = None
        other_sweep = [r for r in others.values() if r.get("sweep")]
        if sweep:
            why = ("a /pd sweep over many games (skip:) runs alone, and %d other /pd session(s) are working"
                   % len(others))
        elif other_sweep:
            why = "a /pd sweep over many games is running (started %s)" % other_sweep[0].get("started_iso")
        elif len(others) >= limit:
            why = ("%d /pd sessions already run on this machine, the most it allows (pd_parallel = %d in lanes.conf)"
                   % (len(others), limit))
        if why:
            sys.stderr.write(
                "PD GUARD: %s. Finish or close one first, or run '/pd force <projects>' to clear the others, or "
                "delete %s.\n" % (why, LOCK))
            return 2
    others[sid] = {"session_id": sid, "started": now, "started_iso": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "pid": os.getppid(), "prompt": prompt[:200], "sweep": sweep}
    write_holders(others)
    n = len(others)
    note = "PD GUARD: this session is on the /pd lock (%s); %d /pd session(s) on this PC now." % (LOCK, n)
    if n > 1:
        note += (" Others are working other games: stay on your own game (the live claim keeps them apart) and "
                 "stage only your own paths; saves queue one at a time.")
    if stolen:
        note += " You cleared %d other session(s) with 'force'." % len(stolen)
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                             "additionalContext": note}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
