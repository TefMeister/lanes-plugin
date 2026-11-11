"""scan-priority.py -- the full scan goes first (0.110.0, 2026-11-11; tools/scan_priority.py has the reasons).

Run with the other tool guards (PreToolUse, hooks/tool-guards.py) and the prompt guards (UserPromptSubmit).
While a full scan, or one of its parts, runs in ANOTHER session on this PC:
  the first tool call   passes, with a notice: finish this step, save, say you wait, start the wait, do nothing more
  during the grace      passes; the notice is repeated now and then
  after the grace       an edit, or a command that is not a save, is refused (exit 2) until the scan has ended
  a typed message       gets one line of context saying the scan is running
The scan's own session passes untouched, and each of its calls is its heartbeat.
Only when the extra `scan_priority` is on. Never fails closed: bad input or any exception -> exit 0, silent.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(os.path.dirname(HERE), "tools")
sys.path.insert(0, TOOLS)

EDITS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
SHELLS = ("Bash", "PowerShell")
# What a waiting session may still run: saving, handing over, looking, and the wait itself. Best effort, like every
# command guard here: it reads the command text.
SAVE_OK = re.compile(
    r"\bgit(?:\.exe)?\b[^;&|\n]*\b(status|diff|log|show|add|commit|push|fetch|stash|rev-parse|branch|remote)\b"
    r"|(?:scan_priority|parcel|handover|clash|owed|keeper)\.(?:py|sh)\b", re.I)
CHANGES = re.compile(r"\bgit(?:\.exe)?\b[^;&|\n]*\b(pull|merge|rebase|reset|checkout|switch|restore|clean)\b", re.I)


def wait_command():
    return 'python "%s" wait --session <this session>' % os.path.join(TOOLS, "scan_priority.py").replace("\\", "/")


def notice(what, minutes, session):
    cmd = wait_command().replace("<this session>", session or "none")
    return ("FULL SCAN PRIORITY: %s is running on this PC and goes first. Do not start anything new. Finish the step "
            "you are in, save it (commit, then upload or hand over as this PC does), tell the person in ONE line that "
            "you are waiting for the full scan, then start this as a BACKGROUND command and end your turn:  %s\n"
            "You are called back when it returns; then pull and carry on where you stopped. In about %d minute(s) every "
            "edit and every command that is not a save is refused until the scan has ended. Only the person may let "
            "you work beside it (scan_priority.py lift)." % (what, cmd, max(1, int(round(minutes)))))


def guard(data):
    import features
    if not features.is_on("scan_priority"):
        return 0
    import scan_priority as SP
    session = data.get("session_id", "")
    event = data.get("hook_event_name", "PreToolUse")
    rec = SP.running(session)
    if not rec:
        if SP.is_holder(session):                   # the scan's own session: its call is the scan's heartbeat
            SP.beat(session)
        return 0
    what = SP.label(rec)
    if event == "UserPromptSubmit":
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": (
            "FULL SCAN PRIORITY: %s is running on this PC. This session may answer, look and save, but must not start "
            "work or change files until it has ended (the person may lift that: scan_priority.py lift). To be called "
            "back when it ends, start in the background:  %s"
            % (what, wait_command().replace("<this session>", session or "none")))}}))
        return 0
    tool = data.get("tool_name", "")
    if tool not in EDITS and tool not in SHELLS:
        return 0
    cmd = (data.get("tool_input") or {}).get("command") or ""
    step, left = SP.stage(session, rec)
    if step in ("tell", "remind"):
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                 "additionalContext": notice(what, left, session)}}))
        return 0
    if step == "grace":
        return 0
    if tool in SHELLS and SAVE_OK.search(cmd) and not CHANGES.search(cmd):
        return 0
    sys.stderr.write(
        "FULL SCAN PRIORITY: %s is running on this PC, and this session's time to finish its step is over, so this "
        "was not run. Saving still works (git add / commit / push, a hand-over). Then tell the person in one line "
        "that you are waiting, start this in the BACKGROUND and end your turn:  %s\nDo not work around it. Only the "
        "person may let you work beside the scan: scan_priority.py lift\n"
        % (what, wait_command().replace("<this session>", session or "none")))
    return 2


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8-sig", errors="replace") or "{}")
    except Exception:
        return 0
    return guard(data)


if __name__ == "__main__":
    try:
        code = main()
    except Exception:
        code = 0
    sys.exit(code)
