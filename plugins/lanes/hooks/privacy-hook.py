"""privacy-hook.py -- text sent to GitHub by a `gh` command never carries this PC's login, a home-folder path, the
person's e-mail address or a never-publish word (0.86.0, 2026-10-25).

Wired as PreToolUse on Bash|PowerShell (see hooks/hooks.json), beside the git hooks that tools/privacy-guard.py
installs. Those check every commit; an issue, a pull request, a release note, a gist or a repo description goes up
through `gh` without any commit, so this reads the command text the same way. Optional (features.py privacy_guard).

  `gh issue|pr|release|gist|repo create|repo edit|api ...` with something personal in it ... refused (exit 2), with
                                                                                      what was found and the fix.
  Anything else ................................................................... passes, silent.

Files count too (0.99.0, release audit 2026-11-02): every word of the command that names a file on this PC (a
--body-file, -F, --notes-file, --input, @file, a gist or release-upload file, `cat file | gh ...`) is opened and its text
checked the same way; a .zip is checked member by member (names and text). Until then a body kept in a file went up
unread. THIS GUARD MUST NEVER FAIL CLOSED: bad input or any error -> exit 0, silent.
"""
import importlib.util
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(os.path.dirname(HERE), "tools")
PUBLISHING = re.compile(r"\bgh(?:\.exe)?\s+(?:issue|pr|release|gist|label|variable|repo\s+(?:create|edit)|api)\b")
# Skipping git's hooks skips the commit and push checks (0.99.0, release audit 2026-11-02): --no-verify on a commit or
# push, `commit -n` (alone or in a cluster such as -nm), or pointing core.hooksPath somewhere else for one command.
SKIP_HOOKS = re.compile(r"\bgit\b[^;&|\n]*?(?:\s(?:commit|push|merge|rebase|am|cherry-pick)\b[^;&|\n]*?\s--no-verify\b"
                        r"|\scommit\b[^;&|\n]*?\s-[a-zA-Z]*n[a-zA-Z]*(?=\s|$)|\s-c\s+core\.hookspath\s*=)", re.I)
# 0.103.0 (Run 5): only the gh command itself is read, from `gh` to the end of its part of the line, never a `cd` in
# front of it (a read-only `gh api` after a cd into the home folder was refused); a gh command that only reads passes.
GH_PART = re.compile(r"""\bgh(?:\.exe)?\s+(?:"[^"]*"|'[^']*'|[^;&|\n"'])*""")
READ_VERBS = re.compile(r"^gh(?:\.exe)?\s+(?:issue|pr|release|gist|label|variable|repo)\s+"
                        r"(?:list|view|status|download|diff|checks|ls)\b")
API_WRITES = re.compile(r"""\s(?:-X|--method)\s*['"]?(?:POST|PATCH|PUT|DELETE)\b|\s(?:-f|-F|--field|--raw-field|--input)(?=[\s=])""",
                        re.I)
# Text filled in when the command runs, which can turn into a home-folder path or the login (Run 5 C5): the guard reads
# the command as written, so it cannot see what these become. Inside single quotes nothing is filled in, and a ~ inside
# any quotes stays a plain ~ (which is the right way to write the home folder).
RUNTIME_HOME = re.compile(r"\$\(\s*(?:cygpath|pwd|whoami)|`\s*(?:cygpath|pwd|whoami)|\$\{?(?:HOME|USERPROFILE|USER|USERNAME|"
                          r"PWD|LOGNAME)\b|%(?:USERPROFILE|USERNAME|HOMEPATH)%|\$env:(?:USERPROFILE|USERNAME|HOMEPATH)\b",
                          re.I)
FILE_FLAG_BEFORE = re.compile(r"(?:--body-file|--notes-file|--input|--file|-F)[\s=]+$")


def fills_in_home(text):
    """whether text, as the shell runs it, fills in something that can become a home-folder path or the login"""
    quote, i, word_start = "", 0, True
    while i < len(text):
        ch = text[i]
        if quote == "'":
            if ch == "'":
                quote = ""
        else:
            if ch == "\\" and i + 1 < len(text):
                i += 2
                word_start = False
                continue
            if ch in "\"'" and (quote == "" or ch == quote):
                quote = "" if quote else ch
            elif ch == "~" and quote == "" and word_start and not FILE_FLAG_BEFORE.search(text[:i]):
                return True   # (a ~ that names a file to read is fine: the file's own text is checked below)
            elif ch in "$`%" and RUNTIME_HOME.match(text, i):
                return True
        word_start = (ch.isspace() or ch == "=") and quote == ""
        i += 1
    return False


FILE_MAX_BYTES = 8 * 1024 * 1024  # a file bigger than this is not read (a build zip of a few MB still is)
TOKEN = re.compile(r"""[^\s"'`|;&<>()=]+""")


def named_files(cmd, cwd):
    """Every word of the command that names an existing file (after @, --flag=, a Git Bash /c/ path)."""
    seen = []
    for tok in TOKEN.findall(cmd):
        tok = tok.lstrip("@")
        if len(tok) < 2 or tok.startswith("-"):
            continue
        m = re.match(r"^/([a-zA-Z])/(.*)$", tok)
        cand = os.path.expanduser((m.group(1) + ":/" + m.group(2)) if m else tok)
        if not os.path.isabs(cand) and cwd:
            cand = os.path.join(cwd, cand)
        try:
            if os.path.isfile(cand) and cand not in seen:
                seen.append(cand)
        except (OSError, ValueError):
            continue
    return seen


def file_findings(path, pg, ws, display):
    """Reasons one named file may not go up: text line by line; a picture, a program or a zip (members, zips inside
    zips) through the privacy guard's binary check (0.99.1)."""
    if os.path.getsize(path) > FILE_MAX_BYTES:
        return set()
    with open(path, "rb") as f:
        data = f.read()
    if b"\0" in data[:8000] or data[:4] == b"PK\x03\x04":
        return set(pg.check_binary(data, ws, display))
    return {why for line in data.decode("utf-8", "ignore").splitlines() for why in pg.check_line(line, ws, display)}


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8-sig", "replace"))  # a BOM (PowerShell pipe) must not open the guard
        cmd = (data.get("tool_input") or {}).get("command") or ""
    except Exception:
        return 0
    skipping = SKIP_HOOKS.search(cmd)
    if not PUBLISHING.search(cmd) and not skipping:
        return 0
    sends = [g.group(0) for g in GH_PART.finditer(cmd) if PUBLISHING.match(g.group(0))
             and not READ_VERBS.match(g.group(0))
             and not (re.match(r"^gh(?:\.exe)?\s+api\b", g.group(0)) and not API_WRITES.search(" " + g.group(0)))]
    if not sends and not skipping:
        return 0
    first_gh = cmd.find(sends[0]) if sends else -1
    pipe_in = cmd[:first_gh] if first_gh > 0 and "|" in cmd[:first_gh] else ""   # `cat file | gh ...` sends that file
    try:
        r = subprocess.run([sys.executable, os.path.join(TOOLS, "features.py"), "is-on", "privacy_guard"],
                           capture_output=True, timeout=15)
        if r.returncode != 0:
            return 0
        if skipping:
            sys.stderr.write("Lanes privacy guard: %r would skip git's checks, and with them the privacy guard that "
                             "keeps personal details off GitHub. Run it without that, and fix whatever the check "
                             "finds instead.\n" % skipping.group(0).strip()[:60])
            return 2
        spec = importlib.util.spec_from_file_location("privacy_guard", os.path.join(TOOLS, "privacy-guard.py"))
        pg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pg)
        ws, display = pg.words(True), pg.conf_value("display_name").lower()
        sent = "\n".join(sends)
        found = {why for line in sent.splitlines() for why in pg.check_line(line, ws, display)}
        if fills_in_home(sent):
            found.add("text filled in when the command runs (a home-folder path or the login can hide in it)")
        for path in named_files(sent + "\n" + pipe_in, data.get("cwd") or os.getcwd()):
            try:
                found |= file_findings(path, pg, ws, display)
            except Exception:
                continue
        found = sorted(found)
    except Exception:
        return 0
    if not found:
        return 0
    sys.stderr.write("Lanes privacy guard: this gh command would put %s on GitHub. Write ~ for the home folder, name "
                     "people only by the display name, leave machine names and e-mail addresses out, then run it "
                     "again.\n" % ", ".join(found))
    return 2


if __name__ == "__main__":
    sys.exit(main())
