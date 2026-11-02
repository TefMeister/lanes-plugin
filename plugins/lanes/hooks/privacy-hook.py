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
FILE_MAX_BYTES = 8 * 1024 * 1024  # a file bigger than this is not read (a build zip of a few MB still is)
ZIP_MEMBER_MAX_BYTES = 2 * 1024 * 1024
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


def file_texts(path):
    """The file's text, or for a zip each member's name and text."""
    import zipfile
    if os.path.getsize(path) > FILE_MAX_BYTES:
        return []
    if zipfile.is_zipfile(path):
        out = []
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                out.append(info.filename)
                if info.file_size <= ZIP_MEMBER_MAX_BYTES and not info.is_dir():
                    out.append(z.read(info).decode("utf-8", "ignore"))
        return out
    with open(path, "rb") as f:
        return [f.read().decode("utf-8", "ignore")]


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8-sig", "replace"))  # a BOM (PowerShell pipe) must not open the guard
        cmd = (data.get("tool_input") or {}).get("command") or ""
    except Exception:
        return 0
    skipping = SKIP_HOOKS.search(cmd)
    if not PUBLISHING.search(cmd) and not skipping:
        return 0
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
        found = {why for line in cmd.splitlines() for why in pg.check_line(line, ws, display)}
        for path in named_files(cmd, data.get("cwd") or os.getcwd()):
            try:
                for text in file_texts(path):
                    found |= {why for line in text.splitlines() for why in pg.check_line(line, ws, display)}
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
