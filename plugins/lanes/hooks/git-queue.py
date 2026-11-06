"""git-queue.py -- one git write at a time on this PC (0.106.0, 2026-11-06).

Why: several /pd sessions may now run at once on one PC (hooks/pd-guard.py, `pd_parallel`), each on its own game,
but they share the clones of the shared repos (the board, staging, the front page). Two sessions running `git add` /
`git commit` / `git pull` in one clone at the same moment fight over git's index lock, or one commit sweeps in what
the other had just staged. Tefa, 2026-11-06: everything goes into the game's own folder first "and then gets uploaded
to github one after another". This is the "one after another".

Wired two ways:
  PreToolUse  (Bash, PowerShell; run by tool-guards.py): a command that writes with git (add, commit, push, pull,
              rebase, merge, stash, reset, checkout, switch, cherry-pick, am, rm, mv, restore) waits until no other
              session on this PC holds the queue (up to WAIT_S), then holds it. Reads (status, log, diff, fetch) pass.
  PostToolUse (Bash, PowerShell; hooks.json): the session that held it gives it back.
A hold older than HOLD_MAX_S counts as left over (a window closed mid-command) and is taken over. After WAIT_S the
command goes ahead anyway, with a note: a slow queue must never stop work. Only when the extra `git_queue` is on.
Never fails closed: bad input or any exception -> exit 0, silent.
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))

STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "lanes")
QUEUE = os.path.join(STATE_DIR, "git-queue.json")
WAIT_S = float(os.environ.get("LANES_GIT_QUEUE_WAIT_S", "75"))   # tool-guards.py has 90 s for every guard together
POLL_S = 0.5
HOLD_MAX_S = 120          # a denied or interrupted command never reaches PostToolUse; its hold expires
GIT_WRITE = re.compile(r"\bgit(?:\.exe)?\b[^;&|\n]*?\b(add|commit|push|pull|rebase|merge|stash|reset|checkout|switch|"
                       r"cherry-pick|am|rm|mv|restore)\b", re.I)


def read():
    try:
        with open(QUEUE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def try_take(sid, cmd):
    """True when this session now holds the queue"""
    rec = {"session": sid, "since": time.time(), "command": cmd[:120]}
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        fd = os.open(QUEUE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(rec, f)
        return True
    except FileExistsError:
        cur = read()
        if cur is None or cur.get("session") == sid or time.time() - cur.get("since", 0) > HOLD_MAX_S:
            try:
                with open(QUEUE, "w", encoding="utf-8") as f:
                    json.dump(rec, f)
                return True
            except OSError:
                return False
        return False
    except OSError:
        return False


def release(sid):
    cur = read()
    if cur and cur.get("session") == sid:
        try:
            os.remove(QUEUE)
        except OSError:
            pass


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8-sig", "replace"))
    except Exception:
        return 0
    try:
        import features
        if not features.is_on("git_queue"):
            return 0
    except Exception:
        pass
    event = data.get("hook_event_name", "")
    sid = data.get("session_id", "") or "unknown"
    if event == "PostToolUse":
        release(sid)
        return 0
    if event != "PreToolUse":
        return 0
    cmd = str((data.get("tool_input") or {}).get("command") or "")
    if not GIT_WRITE.search(cmd):
        return 0
    start = time.time()
    while not try_take(sid, cmd):
        if time.time() - start > WAIT_S:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext":
                  "GIT QUEUE: another session on this PC held the git queue for over %d s; this command went ahead "
                  "anyway. If git says a lock file exists, wait a moment and run it again." % WAIT_S}}))
            return 0
        time.sleep(POLL_S)
    waited = time.time() - start
    if waited >= 2:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext":
              "GIT QUEUE: waited %.0f s for another session's git command on this PC to finish." % waited}}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        sys.exit(0)
