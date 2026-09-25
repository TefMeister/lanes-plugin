"""pd-guard.py -- stop two /pd sessions from running at once on this machine.

Wired as two hooks (see hooks/hooks.json):
  UserPromptSubmit : if the prompt starts with "/pd", check the lock. Held by a
                     LIVE other session -> exit 2 (the prompt is blocked and the
                     reason is shown). Otherwise take the lock for this session.
  SessionEnd       : release the lock if this session holds it.

WHY THIS EXISTS
  Clone roots partition lanes, not sessions. Two /pd sessions land in the same
  working tree and the same git index, so they fight over pull, over index.lock,
  and over every shared file. It is slower, not faster. Nothing is lost when it
  happens -- but ten minutes each is, and a stranger's session cannot be assumed
  to back off as carefully as a practised one.

  A lock was considered and rejected for the CROSS-MACHINE case, because it adds
  a stale-lock failure mode to prevent something that costs minutes and loses
  nothing. This lock is the cheap half of that trade: same machine only, and it
  expires on its own.

The lock is a small JSON file. It is considered live while its session is younger
than STALE_HOURS, so a session that died without SessionEnd (power loss, killed
terminal) does not wedge /pd forever. Override for a real emergency: delete the
lock file, or type "/pd force ..." -- the word "force" right after /pd steals the
lock and says so out loud.

Scope: THIS MACHINE only. Another machine has its own copy and its own lock; a
cross-machine guard is what the live claim in lane-claim.sh does instead, and it
serialises one job rather than a whole lane.
"""
import json
import os
import sys
import time

# $LANES_PD_LOCK exists so the tests can never touch a live session's lock.
# Without it a test run on a working machine briefly moves the real lock aside,
# and a /pd prompt landing in that window gets the wrong answer.
LOCK = os.environ.get("LANES_PD_LOCK") or os.path.join(
    os.path.expanduser("~"), ".claude", "pd-session.lock")
STALE_HOURS = 6


def read_lock():
    try:
        with open(LOCK, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def write_lock(sid, prompt):
    try:
        os.makedirs(os.path.dirname(LOCK), exist_ok=True)
        with open(LOCK, "w", encoding="utf-8") as f:
            json.dump({"session_id": sid, "started": time.time(),
                       "started_iso": time.strftime("%Y-%m-%d %H:%M:%S"),
                       "pid": os.getppid(), "prompt": prompt[:200]}, f, indent=1)
    except Exception:
        # A guard that cannot write its lock must not block work.
        pass


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    event = data.get("hook_event_name", "")
    sid = data.get("session_id", "")

    if event == "SessionEnd":
        lock = read_lock()
        if lock and lock.get("session_id") == sid:
            try:
                os.remove(LOCK)
            except OSError:
                pass
        return 0

    if event != "UserPromptSubmit":
        return 0
    prompt = (data.get("prompt") or "").strip()
    # "/lanes:pd" is the same command as "/pd"; until 0.25.1 the long form skipped this lock.
    if prompt.startswith("/lanes:pd"):
        prompt = "/" + prompt[len("/lanes:"):]
    if not (prompt == "/pd" or prompt.startswith("/pd ")):
        return 0

    force = prompt.split()[1:2] == ["force"]
    lock = read_lock()
    if lock and lock.get("session_id") != sid:
        age_h = (time.time() - lock.get("started", 0)) / 3600.0
        if age_h < STALE_HOURS and not force:
            sys.stderr.write(
                "PD GUARD: another /pd session already holds the lock on this machine "
                "(started %s, %.1f h ago, session %s...). Two /pd runs share one working tree "
                "and fight over git. Finish or close that session first, or run "
                "'/pd force <projects>' to steal the lock, or delete %s.\n"
                % (lock.get("started_iso"), age_h, str(lock.get("session_id"))[:8], LOCK))
            return 2
    write_lock(sid, prompt)
    note = "PD GUARD: lock taken for this session (%s)." % LOCK
    if force and lock:
        note += " You stole it from session %s... with 'force'." % str(lock.get("session_id"))[:8]
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                             "additionalContext": note}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
