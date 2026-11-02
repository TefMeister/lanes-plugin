"""Wrap stdin as a SessionStart context-injection payload.

Kept in Python rather than hand-rolled in the shell because the escaping is the
only fiddly part, and json.dumps cannot get it wrong. Silent on empty input:
nothing to say means say nothing.
"""
import json
import os
import sys


def read_text():
    """stdin as text, read as UTF-8 first.

    The tools that feed this write UTF-8, but on Windows sys.stdin decodes with the ANSI code page (cp1252), so a
    warning sign arrived as mojibake in every session start on both PCs (two-PC test, Run 2, 2026-11-01). Read
    the bytes and decode them ourselves; fall back to the code page only for input that is not valid UTF-8.
    """
    raw = sys.stdin.buffer.read()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        import locale
        return raw.decode(locale.getpreferredencoding(False) or "cp1252", errors="replace")


text = read_text().strip()
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
