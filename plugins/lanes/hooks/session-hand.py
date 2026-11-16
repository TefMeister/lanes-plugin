"""Stop hook: the fresh-session nudge and the hand-on close (0.118.0, 2026-11-16; tools/handon.py says why and how).

After every reply: (1) when a close was asked for this window by `handon.py start` (the next job has its own window
now), close this one if it is safe, or say in one line why it stays open; (2) otherwise, with the extra fresh_nudge
on, show one line when a job has just ended and the session has grown expensive. Lines go to the person
(systemMessage); nothing is handed back to Claude. Any error -> silent, exit 0.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))


def main():
    raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
    data = json.loads(raw or "{}")
    import handon
    records = handon.read_records(data.get("transcript_path") or "")
    line = ""
    if handon.is_on("hand_on"):
        line = handon.close_if_safe(records)
    if not line and handon.is_on("fresh_nudge") and not data.get("stop_hook_active"):
        line = handon.nudge(data.get("session_id", ""), records)
    if line:
        print(json.dumps({"systemMessage": line}))
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception:  # noqa: BLE001 - never stands in the way of a reply
        code = 0
    sys.exit(code)
