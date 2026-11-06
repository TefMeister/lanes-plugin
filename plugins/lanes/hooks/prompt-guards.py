"""UserPromptSubmit hook: the prompt guards and the rest reminder in ONE Python process (0.105.0, 2026-11-06; P5).

Replaces three hooks.json entries. Order matters: the /pd lock, then the live claim, then the clash guard (each can
refuse the prompt; the first refusal stops the rest), then the rest reminder, which only adds a line of context.
"""
import sys

import guard_runner as G

GUARDS = [("pd-guard.py", []), ("lane-claim-guard.py", []), ("clash-guard.py", []), ("rest-reminder.py", [])]


def main():
    raw = G.read_input()
    return G.run(GUARDS, raw, "UserPromptSubmit", plain_text_is_context=True)


if __name__ == "__main__":
    try:
        code = main()
    except Exception:  # noqa: BLE001 - never fail closed
        code = 0
    sys.exit(code)
