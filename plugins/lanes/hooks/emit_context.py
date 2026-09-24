"""Wrap stdin as a SessionStart context-injection payload.

Kept in Python rather than hand-rolled in the shell because the escaping is the
only fiddly part, and json.dumps cannot get it wrong. Silent on empty input:
nothing to say means say nothing.
"""
import json
import os
import sys

text = sys.stdin.read().strip()
if not text:
    sys.exit(0)

if os.environ.get("CLAUDE_PLUGIN_ROOT") and not os.environ.get("COPILOT_CLI"):
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": text,
        }
    }
else:
    payload = {"additionalContext": text}

sys.stdout.write(json.dumps(payload))
