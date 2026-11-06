"""SessionEnd hook: start this session's end steps in a program that outlives the window, and return at once.

Claude Code gives a plugin's end hooks 1.5 s in all (Run 5, 2026-11-06): too short for anything that talks to GitHub.
tools/endwork.py does the end report, gives back clash locks and shelves logs, after the window has gone.
Never blocks a session from ending: any error -> exit 0.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8-sig", errors="replace") or "{}")
    except Exception:  # noqa: BLE001
        data = {}
    try:
        import endwork
        endwork.start_detached(["hop", "--session=" + str(data.get("session_id") or "")])
    except Exception:  # noqa: BLE001
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
