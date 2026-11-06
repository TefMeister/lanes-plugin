"""clash-guard.py -- the clash guard's hook (lanes-next, 2026-11-05; tools/clash.py has the table and the reasons).

Wired three ways (hooks/hooks.json):
  UserPromptSubmit  a typed /fullscan, /gr, /gu ... (with or without "lanes:"): refused with one plain line when
                    something it clashes with is running on this PC or the other; otherwise its lock is taken for this
                    session, so the command's own parts (the full scan's /gr, /gu ...) pass.
  PreToolUse Skill  the same when Claude starts that skill itself (a typed command that also opens its skill is
                    the same session taking its own lock again, which passes).
  SessionEnd        everything this session still held is given back.
"force" right after the command name starts it anyway: the person's word, never the model's.
Only when the extra `clash_guard` is on. Never fails closed on its own errors: bad input or any exception -> exit 0.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(os.path.dirname(HERE), "tools")
sys.path.insert(0, TOOLS)


def parse(prompt):
    """(command, args) of a typed slash command, or (None, [])"""
    words = (prompt or "").strip().split()
    if not words or not words[0].startswith("/"):
        return None, []
    name = words[0][1:]
    if name.startswith("lanes:"):
        name = name[len("lanes:"):]
    return name, words[1:]


def project_of(job, args):
    for a in args:
        if a != "force" and not a.startswith(("-", "skip:")):
            return a
    return "all"


def guard(data):
    import clash
    import features
    if not features.is_on("clash_guard"):
        return 0
    event = data.get("hook_event_name", "")
    session = data.get("session_id", "")
    c = clash.FL.conf()
    if event == "SessionEnd":
        # Only this PC's files: Claude Code gives a plugin's end hooks 1.5 s, too short for GitHub. The GitHub half is
        # given back by endwork.py, started by the end-work hook, which outlives the window (Run 5, 2026-11-06).
        clash.release_session(c, session, local_only=True)
        return 0
    if event == "PreToolUse":
        tin = data.get("tool_input") or {}
        prompt = "/" + str(tin.get("skill") or "").strip().lstrip("/") + " " + str(tin.get("args") or "")
    else:
        prompt = data.get("prompt", "")
    name, args = parse(prompt)
    job = clash.COMMAND_JOBS.get(name or "")
    if not job:
        return 0
    ok, line = clash.take(c, job, project_of(job, args), session, force=bool(args[:1] == ["force"]))
    if ok:
        return 0
    sys.stderr.write(line + "\n(Typing \"force\" right after the command starts it anyway.)\n")
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
