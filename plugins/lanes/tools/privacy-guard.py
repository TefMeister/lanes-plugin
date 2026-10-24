#!/usr/bin/env python3
"""privacy-guard.py - refuses a commit that would put this PC's login, a home-folder path, the person's e-mail address
or a never-publish word on GitHub (0.86.0, 2026-10-25).

The maintainer, after finding the home PC's login and a home-folder path in published notes: "please see to it
that these are never added and if possible, make an iron rule in Lanes and in general to not add any of the actual
home pc username or file paths anywhere. only name Tefa is fine". The naming rule had said so since 0.40, and the
release scan (scrub-scan.py) checked the plugin itself, but nothing checked an ordinary commit: 27 repos had collected
the login in notes and old scripts, one by one, written by sessions that could see the rule. A rule a model applies
is behavioural; a git hook is not.

    python privacy-guard.py install       every git repository on this PC checks each commit (machine-wide hooks)
    python privacy-guard.py uninstall     puts the machine-wide hook setting back as it was
    python privacy-guard.py status        installed or not, and what is checked
    python privacy-guard.py staged        (pre-commit) check what is about to be committed; exit 1 = refused
    python privacy-guard.py message FILE  (commit-msg) check the commit message; exit 1 = refused
    python privacy-guard.py text [--public] < file   check any text (tests, and the gh-command hook)

WHAT IS REFUSED
  Everywhere, private repos too:
  - this PC's login name (unless it is the display name the person chose, lanes.conf display_name);
  - a home-folder path naming anyone but the display name or a placeholder: C:\\Users\\<user>, C:/Users/<user>,
    /c/Users/<user>, /home/<user>, /Users/<user> -- write ~ instead, or look the folder up when the code runs;
  - the e-mail address in this PC's git settings (git config user.email), unless it is a noreply address.
  In PUBLIC repos (or when the visibility cannot be found) also:
  - every word in ~/.claude/lanes/never-publish.txt (machine names and the like; that list never leaves the PC).
  Private repos may keep machine names: some tools file their records by computer name.
  Only ADDED lines are checked, so an old line elsewhere in a file never blocks an unrelated commit.
  A line holding "privacy-guard:allow" or "scrub-scan:allow" is skipped (deliberate test fixtures).

HOW IT HOOKS IN
  `install` makes ~/.claude/lanes/githooks/ and points git's machine-wide core.hooksPath at it. Every hook there
  first runs this check (pre-commit, commit-msg), then hands over to whatever machine-wide hook folder was set
  before (remembered in .previous, e.g. a push guard), else to the repository's own hook. A repository with its own
  core.hooksPath setting skips machine-wide hooks; `status` lists the ones it can see in the Lanes roots.
"""
import getpass
import json
import os
import re
import subprocess
import sys

HOME = os.path.expanduser("~")
STATE = os.environ.get("LANES_STATE_DIR") or os.path.join(HOME, ".claude", "lanes")
HOOKDIR = os.path.join(STATE, "githooks")
NEVER = os.path.join(STATE, "never-publish.txt")
CONF = os.environ.get("LANES_CONFIG") or os.path.join(HOME, ".claude", "lanes.conf")
HOOK_NAMES = ("pre-commit", "commit-msg", "prepare-commit-msg", "post-commit", "post-checkout", "post-merge",
              "post-rewrite", "pre-rebase", "pre-push", "reference-transaction")
ALLOW_MARKS = ("privacy-guard:allow", "scrub-scan:allow")
PLACEHOLDERS = {"user", "username", "you", "yourname", "your-name", "name", "someone", "example", "me", "x", "xx",
                "test", "runner", "ci", "home", "root", "admin", "public", "default", "all users", "default user",
                "%username%", "$user", "$username", "${user}", "${username}", "$env:username", "..."}
HOME_PATH = re.compile(r"(?:\b[A-Za-z]:(?:\\\\|\\|/)+Users(?:\\\\|\\|/)+|(?<![\w.])/[cC]/[Uu]sers/|(?<![\w.])/home/"
                       r"|(?<![\w.~])/Users/)([^\\/\s\"'`<>*|:;,)\]]+)")
MAX_SHOWN = 12


def conf_value(key):
    try:
        for line in open(CONF, encoding="utf-8"):
            k, _, v = line.partition("=")
            if k.strip() == key:
                return v.split("#")[0].strip()
    except OSError:
        pass
    return ""


def git(*args, cwd=None):
    r = subprocess.run(["git"] + list(args), capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=cwd)
    return r.stdout if r.returncode == 0 else ""


def words(public):
    """(word, why) pairs to refuse, lower-case."""
    display = conf_value("display_name").lower()
    out = []
    for login in {os.environ.get("USERNAME", ""), os.environ.get("USER", ""), safe_getuser()}:
        login = login.strip().lower()
        if len(login) >= 3 and login != display and login not in PLACEHOLDERS:
            out.append((login, "this PC's login name"))
    email = git("config", "--global", "user.email").strip().lower()
    if email and "noreply" not in email:
        out.append((email, "the e-mail address in git's settings"))
    if public:
        try:
            for line in open(NEVER, encoding="utf-8"):
                w = line.strip()
                if w and not w.startswith("#"):
                    out.append((w.lower(), "a never-publish word"))
        except OSError:
            pass
    return out


def safe_getuser():
    try:
        return getpass.getuser()
    except Exception:
        return ""


def check_line(line, ws, display):
    """Reasons this one line may not be published."""
    if any(m in line for m in ALLOW_MARKS):
        return []
    low = line.lower()
    why = [w_why for w, w_why in ws if w in low]
    for m in HOME_PATH.finditer(line):
        name = m.group(1).strip().lower()
        if name and name != display and name not in PLACEHOLDERS and not name.startswith(("<", "$", "%", "{")):
            why.append("a home-folder path (%s...)" % m.group(0)[:12].replace("\\\\", "\\"))
    return sorted(set(why))


def visibility():
    """public / private / unknown, cached per repository in its own git settings."""
    v = git("config", "--local", "lanes.visibility").strip()
    if v in ("public", "private"):
        return v
    url = git("remote", "get-url", "origin").strip()
    m = re.search(r"github\.com[:/]+([^/]+/[^/]+?)(?:\.git)?/?$", url)
    if not m:
        return "private" if not url else "unknown"   # no remote at all: nothing is published from here
    try:
        r = subprocess.run(["gh", "repo", "view", m.group(1), "--json", "visibility", "-q", ".visibility"],
                           capture_output=True, text=True, timeout=20)
        v = r.stdout.strip().lower()
    except Exception:
        v = ""
    if v in ("public", "private"):
        git("config", "--local", "lanes.visibility", v)
        return v
    return "unknown"


def report(findings, what):
    if not findings:
        return 0
    sys.stderr.write("\nPRIVACY GUARD (lanes): this %s would put something personal on GitHub.\n" % what)
    for where, why in findings[:MAX_SHOWN]:
        sys.stderr.write("  %s: %s\n" % (where, ", ".join(why)))
    if len(findings) > MAX_SHOWN:
        sys.stderr.write("  ... and %d more\n" % (len(findings) - MAX_SHOWN))
    sys.stderr.write("Fix: write ~ for the home folder (or look it up when the code runs: os.path.expanduser('~'),\n"
                     "$HOME, %USERPROFILE%), name people only by the display name, and leave machine names out.\n"
                     "Then stage the fix and commit again. Never skip this check (no --no-verify).\n\n")
    return 1


def cmd_staged():
    public = visibility() != "private"
    ws, display = words(public), conf_value("display_name").lower()
    findings = []
    for name in git("diff", "--cached", "--name-only", "--diff-filter=AR", "-z").split("\0"):
        if name:
            why = check_line(name, ws, display)
            if why:
                findings.append((name + " (the file's name)", why))
    cur, line_no = "", 0
    for line in git("diff", "--cached", "-U0", "--no-color", "--no-ext-diff").splitlines():
        if line.startswith("+++ "):
            cur = line[6:] if line.startswith("+++ b/") else line[4:]
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            line_no = int(m.group(1)) if m else 0
        elif line.startswith("+"):
            why = check_line(line[1:], ws, display)
            if why:
                findings.append(("%s:%d" % (cur, line_no), why))
            line_no += 1
    return report(findings, "commit")


def cmd_message(path):
    public = visibility() != "private"
    ws, display = words(public), conf_value("display_name").lower()
    findings = []
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return 0
    for i, line in enumerate(text.splitlines(), 1):
        if line.startswith("#"):
            continue
        why = check_line(line, ws, display)
        if why:
            findings.append(("commit message line %d" % i, why))
    return report(findings, "commit message")


def cmd_text(public):
    ws, display = words(public), conf_value("display_name").lower()
    findings = []
    for i, line in enumerate(sys.stdin.read().splitlines(), 1):
        why = check_line(line, ws, display)
        if why:
            findings.append(("line %d" % i, why))
    return report(findings, "text")


HOOK = """#!/bin/sh
# Lanes privacy guard (tools/privacy-guard.py install): checks a commit, then hands over to the hook that was here
# before (a machine-wide one remembered in .previous, else the repository's own).
name=$(basename "$0")
case "$name" in
  pre-commit) @@PY@@ "@@TOOL@@" staged || exit 1 ;;
  commit-msg) @@PY@@ "@@TOOL@@" message "$1" || exit 1 ;;
esac
prev=$(cat "$(dirname "$0")/.previous" 2>/dev/null)
if [ -n "$prev" ] && [ -x "$prev/$name" ]; then exec "$prev/$name" "$@"; fi
gd=$(git rev-parse --git-dir 2>/dev/null)
if [ -z "$prev" ] && [ -n "$gd" ] && [ -x "$gd/hooks/$name" ]; then exec "$gd/hooks/$name" "$@"; fi
exit 0
"""


def cmd_install():
    os.makedirs(HOOKDIR, exist_ok=True)
    py = sys.executable.replace("\\", "/")
    # the hooks copy this file next to them, so a plugin update that moves the plugin folder never breaks commits
    here = os.path.join(HOOKDIR, "privacy-guard.py")
    if os.path.abspath(here) != os.path.abspath(__file__):
        with open(__file__, encoding="utf-8") as src, open(here, "w", encoding="utf-8", newline="\n") as dst:
            dst.write(src.read())
    tool = here.replace("\\", "/")
    for n in HOOK_NAMES:
        p = os.path.join(HOOKDIR, n)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(HOOK.replace("@@PY@@", '"%s"' % py).replace("@@TOOL@@", tool))
        os.chmod(p, 0o755)
    cur = git("config", "--global", "--get", "core.hooksPath").strip()
    mine = HOOKDIR.replace("\\", "/")
    if cur and os.path.normcase(os.path.abspath(os.path.expanduser(cur))) != os.path.normcase(os.path.abspath(HOOKDIR)):
        with open(os.path.join(HOOKDIR, ".previous"), "w", encoding="utf-8", newline="\n") as f:
            f.write(cur.replace("\\", "/"))
    subprocess.run(["git", "config", "--global", "core.hooksPath", mine])
    print("privacy guard installed: every commit on this PC is checked.%s"
          % (" (It hands over to the hooks that were set before: %s)" % cur if cur and cur != mine else ""))
    return 0


def cmd_uninstall():
    prev = ""
    try:
        prev = open(os.path.join(HOOKDIR, ".previous"), encoding="utf-8").read().strip()
    except OSError:
        pass
    if prev:
        subprocess.run(["git", "config", "--global", "core.hooksPath", prev])
    else:
        subprocess.run(["git", "config", "--global", "--unset", "core.hooksPath"])
    print("privacy guard removed; machine-wide hooks are %s again" % (prev or "unset"))
    return 0


def installed():
    cur = git("config", "--global", "--get", "core.hooksPath").strip()
    return bool(cur) and os.path.normcase(os.path.abspath(os.path.expanduser(cur))) == os.path.normcase(
        os.path.abspath(HOOKDIR)) and os.path.isfile(os.path.join(HOOKDIR, "pre-commit"))


def cmd_status(as_json):
    st = {"installed": installed(), "hooks": HOOKDIR, "never_publish_words": len(words(True)) - len(words(False)),
          "checks": ["login", "home-folder paths", "git e-mail", "never-publish words (public repos)"]}
    if as_json:
        print(json.dumps(st))
    else:
        print("privacy guard: %s" % ("ON, every commit on this PC is checked" if st["installed"] else "NOT installed"))
    return 0 if st["installed"] else 1


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    c = argv[0]
    if c == "staged":
        return cmd_staged()
    if c == "message" and len(argv) > 1:
        return cmd_message(argv[1])
    if c == "text":
        return cmd_text("--public" in argv)
    if c == "install":
        return cmd_install()
    if c == "uninstall":
        return cmd_uninstall()
    if c == "status":
        return cmd_status("--json" in argv)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
