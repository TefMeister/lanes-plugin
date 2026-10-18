"""repo-guard.py -- new GitHub repos are PRIVATE unless the person said otherwise.

Wired as PreToolUse on Bash|PowerShell (see hooks/hooks.json), with the session-start rule in
hooks/repo-rule. Asked for by the maintainer, 2026-10-11: "create all new repos on github as private as
a default, and ask the user if any of the repos you are about to create should be public."

WHAT IT DOES
  `gh repo create` with --private ............ passes, silent.
  `gh repo create` with no visibility flag .... refused (exit 2) with the fix: add --private, or ask the
                                                person first and use --public.
  `gh repo create --public` / `--internal` .... the person is ASKED (permissionDecision "ask"), so a
                                                public repo can never appear without them seeing it.
  `gh repo edit ... --visibility public` ...... asked, the same way.
  `estate.py project <name> --public` ......... asked, the same way (0.78.0): the tool calls gh itself.
  `gh api` creating a repo (POST user/repos or orgs/<org>/repos) without private=true ... refused;
                                                with private=false or visibility=public ... asked.
  Anything else ............................... passes, silent.

  `new_repos = public` in lanes.conf (or LANES_NEW_REPOS=public) switches the guard off for someone who
  wants public repos by default. Read from $LANES_CONFIG when set, else ~/.claude/lanes.conf.

  Best effort, like every Bash guard here: it reads the command text, so a repo made some other way
  (the web page, a script file) is not seen. THIS GUARD MUST NEVER FAIL CLOSED: bad input or any error
  -> exit 0, silent.
"""
import json
import os
import re
import sys

ASK_PUBLIC = ("Lanes: this would make a PUBLIC GitHub repo. New repos are private by default. "
              "Allow it only if you asked for this repo to be public.")
REFUSE = ("Lanes: new GitHub repos are private by default. Add --private to the command. "
          "If the person might want this one public, ask them first (name each repo you are about to "
          "create and ask which, if any, should be public), then use --public only for those.")
REFUSE_API = ("Lanes: new GitHub repos are private by default. Add -F private=true to this API call, "
              "or ask the person first if they want it public.")


def new_repos_setting(path):
    """The `new_repos = ...` value in one lanes.conf, lower-cased, or '' when unset or unreadable."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return ""
    m = re.search(r"^\s*new_repos\s*=\s*(\S+)", text, re.M)
    return m.group(1).strip().lower() if m else ""


def conf_says_public():
    if (os.environ.get("LANES_NEW_REPOS") or "").strip().lower() == "public":
        return True
    path = os.environ.get("LANES_CONFIG") or os.path.expanduser("~/.claude/lanes.conf")
    return new_repos_setting(path) == "public"


def ask(reason):
    sys.stdout.write(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "ask",
        "permissionDecisionReason": reason}}))
    sys.exit(0)


def refuse(reason):
    sys.stderr.write(reason + "\n")
    sys.exit(2)


def judge(cmd):
    """Return ('ask'|'refuse'|None, reason) for one command line."""
    for m in re.finditer(r"\bestate\.py['\"]?\s+project\b([^;&|\n]*)", cmd):
        if re.search(r"--public\b", m.group(1)):
            return "ask", ASK_PUBLIC
    # Each `gh repo create` is judged with the text up to the next command separator.
    for m in re.finditer(r"\bgh(?:\.exe)?\s+repo\s+create\b([^;&|\n]*)", cmd):
        args = m.group(1)
        if re.search(r"--public\b|--internal\b|--visibility[ =](public|internal)", args):
            return "ask", ASK_PUBLIC
        if not re.search(r"--private\b|--visibility[ =]private", args):
            return "refuse", REFUSE
    for m in re.finditer(r"\bgh(?:\.exe)?\s+repo\s+edit\b([^;&|\n]*)", cmd):
        if re.search(r"--visibility[ =]['\"]?(public|internal)", m.group(1)):
            return "ask", ASK_PUBLIC
    for m in re.finditer(r"\bgh(?:\.exe)?\s+api\b([^;&|\n]*)", cmd):
        args = m.group(1)
        if not re.search(r"(?:^|\s|['\"/])(user|orgs/[^/\s'\"]+)/repos(?:['\"\s]|$)", args):
            continue
        if re.search(r"private=false|visibility=(public|internal)", args):
            return "ask", ASK_PUBLIC
        posting = re.search(r"(-X|--method)\s*['\"]?POST", args, re.I) or re.search(r"\s-[fF]\s|--field|--raw-field", args)
        if posting and not re.search(r"private=true|visibility=private", args):
            return "refuse", REFUSE_API
    return None, ""


def main():
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return
    if data.get("tool_name") not in ("Bash", "PowerShell"):
        return
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if ("gh" not in cmd and "estate.py" not in cmd) or conf_says_public():
        return
    verdict, reason = judge(cmd)
    if verdict == "ask":
        ask(reason)
    if verdict == "refuse":
        refuse(reason)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        pass
    sys.exit(0)
