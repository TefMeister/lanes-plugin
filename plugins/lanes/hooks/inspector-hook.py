"""inspector-hook.py -- run the Inspector after a code edit, and hold a commit until its findings
have verdicts.

Wired twice (see hooks/hooks.json):
  PostToolUse on Write|Edit|MultiEdit   inspects the edited file; anything new is written to the
                                        project's INSPECTOR.md and put in front of the session.
  PreToolUse on Bash|PowerShell         a `git commit` is refused (exit 2) while a finding for a
                                        staged file has no verdict, or says `fix now` and is still
                                        there. The staged files are inspected first, so code
                                        changed through the shell is caught too.

  SessionStart                          findings carried over by an emergency save are put in front
                                        of the new session, to be judged first.

The verdict step is not skippable (the author's decision, 2026-09-26: "if usage is low, just get
less done, but no cost to quality of work"). The one exception is the emergency save at the END of
a session: a commit message saying `inspector: carry over` goes through, and the findings carry
over. `inspector = off` in lanes.conf switches it off for a machine; `inspector_repos` limits it
to named repos while it is being tested in-house.

Finding the repo of a commit is best effort: `cd <dir>`, `Set-Location <dir>` and `git -C <dir>`
are followed, else the hook's own cwd. Anything it cannot work out, and any exception at all,
lets the call through. THIS HOOK MUST NEVER FAIL CLOSED on its own errors: a broken guard that
blocks every commit is worse than no guard.
"""
import json
import os
import re
import shlex
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

EDIT_TOOLS = ("Write", "Edit", "MultiEdit")
SEGMENT_SPLIT = re.compile(r"&&|\|\||;|\n")
COMMIT_RE = re.compile(r"\bgit\b.*\bcommit\b")
CD_RE = re.compile(r"^\s*(?:cd|Set-Location|pushd)\s+(.+?)\s*$", re.I)
GIT_C_RE = re.compile(r"\bgit\s+-C\s+(\"[^\"]+\"|'[^']+'|\S+)")
ALL_FLAG_RE = re.compile(r"\scommit\b.*\s-(?:a\w*|\w*a)\b|\s--all\b")


def unquote(s):
    s = s.strip()
    try:
        parts = shlex.split(s, posix=True)
        s = parts[0] if parts else s
    except ValueError:
        s = s.strip("\"'")
    return os.path.expanduser(s)


def to_native(path):
    """Git bash hands us /c/Users/...; Python on Windows wants C:/Users/..."""
    m = re.match(r"^/([a-zA-Z])/(.*)$", path)
    if m and os.name == "nt":
        return f"{m.group(1).upper()}:/{m.group(2)}"
    return path


PUSH_RE = re.compile(r"\bgit\b(?:\s+-C\s+\S+)?\s+push\b")


def commits(command, cwd, pattern=None):
    """(repo dir, include unstaged) for every `git commit` in a shell command (or every match of
    `pattern`, e.g. PUSH_RE)."""
    here, out = cwd, []
    for seg in SEGMENT_SPLIT.split(command):
        m = CD_RE.match(seg)
        if m:
            target = to_native(unquote(m.group(1)))
            here = target if os.path.isabs(target) else os.path.join(here, target)
            continue
        if pattern is not None:
            hit = pattern.search(seg)
        else:
            hit = COMMIT_RE.search(seg) and not re.search(r"\bcommit-tree\b|\blog\b", seg)
        if hit:
            g = GIT_C_RE.search(seg)
            d = here
            if g:
                target = to_native(unquote(g.group(1)))
                d = target if os.path.isabs(target) else os.path.join(here, target)
            out.append((d, bool(ALL_FLAG_RE.search(seg))))
    return out


def post_edit(data):
    import inspector
    path = (data.get("tool_input") or {}).get("file_path")
    if not path or not os.path.isfile(path):
        return 0
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        inspector.cmd_check([path], session=data.get("session_id") or None)
    text = buf.getvalue().strip()
    if text:
        sys.stdout.write(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PostToolUse", "additionalContext": text}}))
    return 0


RELEASE_RE = re.compile(r"lane-claim\.sh\"?\s+release\s+(\S+)\s+([^;&|\n]+)")


def pre_release(data, command):
    """End of a lane session: `lane-claim.sh release <lane> <project...>` is held until the project's
    notes are answered and committed (inspector_mode end, and each)."""
    import inspector
    m = RELEASE_RE.search(command)
    if not m:
        return 0
    names = [n for n in m.group(2).split() if not n.startswith("-") and not n.startswith("#")]
    cwd = data.get("cwd") or os.getcwd()
    here = inspector.repo_of(cwd) if os.path.isdir(cwd) else None
    roots = [os.path.dirname(here) if here else cwd] + inspector.scan_roots()
    carry = bool(inspector.CARRY_RE.search(command))
    for root in dict.fromkeys(os.path.normpath(r) for r in roots):
        msg = inspector.final_gate(root, names, carry=carry)
        if msg:
            sys.stderr.write(msg + "\n")
            return 2
    return 0


def pre_commit(data):
    import inspector
    tool_input = data.get("tool_input") or {}
    command = str(tool_input.get("command", ""))
    if "lane-claim" in command and "release" in command:
        rc = pre_release(data, command)
        if rc:
            return rc
    cwd = data.get("cwd") or os.getcwd()
    carry = bool(inspector.CARRY_RE.search(command))
    if "push" in command:
        for d, _ in commits(command, cwd, PUSH_RE):
            repo = inspector.repo_of(d) if os.path.isdir(d) else None
            msg = inspector.push_gate(repo, carry=carry, commits_first=bool(COMMIT_RE.search(command))) \
                if repo else None
            if msg:
                sys.stderr.write(msg + "\n")
                return 2
    if "commit" not in command:
        return 0
    for d, include_all in commits(command, cwd):
        repo = inspector.repo_of(d) if os.path.isdir(d) else None
        if not repo:
            continue
        msg = inspector.gate(repo, include_all, carry=bool(inspector.CARRY_RE.search(command)))
        if msg:
            sys.stderr.write(msg + "\n")
            return 2
    return 0


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    try:
        import inspector
        if not inspector.enabled():
            return 0
        event, tool = data.get("hook_event_name", ""), data.get("tool_name", "")
        if event == "PostToolUse" and tool in EDIT_TOOLS:
            return post_edit(data)
        if event == "PreToolUse" and tool in ("Bash", "PowerShell"):
            return pre_commit(data)
        if event == "SessionStart":
            text = inspector.brief(data.get("session_id") or None)
            if text:
                sys.stdout.write(json.dumps({"hookSpecificOutput": {
                    "hookEventName": "SessionStart", "additionalContext": text}}))
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
