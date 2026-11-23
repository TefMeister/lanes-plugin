"""UserPromptSubmit guard: a new window has started on its hand-on prompt (0.118.0, 2026-11-16; tools/handon.py).

When the first message is the hand-on pointer ("LANES HAND-ON <id>: read the hand-on prompt at ..."), this leaves the
'started' mark the old window waits for before it closes, and (0.123.0) hands the old window's held games to this one,
saying so. It never refuses. Errors -> silent.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))


def main():
    data = json.loads(sys.stdin.read() or "{}")
    prompt = data.get("prompt") or ""
    if "LANES HAND-ON" not in prompt:
        return 0
    import handon
    handon.mark_started(prompt, data.get("session_id", ""))
    if handon.LAST_HANDED:   # 0.123.0: the old window's games came with the job (the project guard)
        note = ("PROJECT GUARD: this session now holds %s on this PC, handed on with the job by the window that wrote it "
                "(no \"take over\" needed)." % ", ".join(handon.LAST_HANDED))
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": note}}))
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception:  # noqa: BLE001
        code = 0
    sys.exit(code)
