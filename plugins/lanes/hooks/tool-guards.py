"""PreToolUse hook: every Lanes tool guard in ONE Python process (0.105.0, 2026-11-06; audit proposals P5 and P6).

Replaces eight separate hooks.json entries. Which guards run depends on the tool, exactly as their old matchers did;
guard_runner.py says how their answers are read. The reader guard runs only when the call comes from a background
agent (the payload carries agent_id): without one it always let the call through, so running it was pure cost.
"""
import sys

import guard_runner as G

EDITS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
SHELLS = ("Bash", "PowerShell")


def guards_for(data):
    tool = data.get("tool_name", "")
    out = [("scan-priority.py", [])]   # FIRST (0.110.0): the full scan goes first; it is also the scan's heartbeat
    if data.get("agent_id") and (tool in EDITS or tool == "Bash"):
        out.append(("reader-guard.py", []))
    if tool in SHELLS:
        out += [("inspector-hook.py", []), ("repo-guard.py", []), ("update-hold-guard.py", []),
                ("privacy-hook.py", [])]
    if tool in EDITS:
        out.append(("project-guard.py", []))   # one session edits a game's files at a time (0.106.1)
    if tool in ("Read", "Grep") or tool in SHELLS:
        out.append(("begone-raw-guard.py", []))
    if tool in SHELLS:
        # LAST (0.106.0): it holds the git queue until PostToolUse, so a command another guard refuses never holds it
        out.append(("git-queue.py", []))
    if tool == "Skill":
        out += [("skill-lane-guard.py", []), ("clash-guard.py", [])]
    return out


def main():
    raw = G.read_input()
    data = G.parse(raw)
    if data.get("hook_event_name", "PreToolUse") != "PreToolUse":
        return 0
    return G.run(guards_for(data), raw, "PreToolUse")


if __name__ == "__main__":
    try:
        code = main()
    except Exception:  # noqa: BLE001 - never fail closed
        code = 0
    sys.exit(code)
