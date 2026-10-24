"""privacy-hook.py -- text sent to GitHub by a `gh` command never carries this PC's login, a home-folder path, the
person's e-mail address or a never-publish word (0.86.0, 2026-10-25).

Wired as PreToolUse on Bash|PowerShell (see hooks/hooks.json), beside the git hooks that tools/privacy-guard.py
installs. Those check every commit; an issue, a pull request, a release note, a gist or a repo description goes up
through `gh` without any commit, so this reads the command text the same way. Optional (features.py privacy_guard).

  `gh issue|pr|release|gist|repo create|repo edit|api ...` with something personal in it ... refused (exit 2), with
                                                                                      what was found and the fix.
  Anything else ................................................................... passes, silent.

Best effort: a body read from a file (--body-file, -F) is not opened. THIS GUARD MUST NEVER FAIL CLOSED: bad input
or any error -> exit 0, silent.
"""
import importlib.util
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(os.path.dirname(HERE), "tools")
PUBLISHING = re.compile(r"\bgh(?:\.exe)?\s+(?:issue|pr|release|gist|repo\s+(?:create|edit)|api)\b")


def main():
    try:
        data = json.load(sys.stdin)
        cmd = (data.get("tool_input") or {}).get("command") or ""
    except Exception:
        return 0
    if not PUBLISHING.search(cmd):
        return 0
    try:
        r = subprocess.run([sys.executable, os.path.join(TOOLS, "features.py"), "is-on", "privacy_guard"],
                           capture_output=True, timeout=15)
        if r.returncode != 0:
            return 0
        spec = importlib.util.spec_from_file_location("privacy_guard", os.path.join(TOOLS, "privacy-guard.py"))
        pg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pg)
        ws, display = pg.words(True), pg.conf_value("display_name").lower()
        found = sorted({why for line in cmd.splitlines() for why in pg.check_line(line, ws, display)})
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
