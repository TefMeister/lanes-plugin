#!/usr/bin/env python3
"""display-name - the ONE name sessions may write for the person using this machine.

    python display-name.py            print it ("User" until one is chosen)
    python display-name.py set NAME   save NAME to lanes.conf (creates the file if needed)
    python display-name.py clear      go back to "User"
    python display-name.py rule       print the naming rule, filled in, for the session-start hook

THE RULE (0.22.0)
  Nothing the plugin's sessions write down - notes, boards, commit messages, READMEs, issues,
  file names - carries the name of the person at the keyboard. They are "User", unless they
  choose a display name during /lanes:setup (or with `set` above); then they are that, and only
  that. Their real name, login, e-mail, machine names and home-folder paths are never written.

  One plain rule, applied to every session by a session-start hook, replaces the old per-word
  guard lists: a list of words that must never be published is itself a list of those words.

  Chatting with the person is not affected: this is about what gets SAVED, where others may read it.

The name is stored as `display_name = ...` in the same lanes.conf every other tool reads.
Read-only unless given `set` or `clear`.
"""
import os
import re
import sys

DEFAULT = "User"
KEY = "display_name"
# A display name is shown in public files, so keep it to something that reads as a name or a handle:
# letters, digits, spaces and . _ - only, 1 to 40 characters. Anything else is refused, not mangled.
VALID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._\-]{0,39}$")


def conf_candidates():
    # $LANES_CONFIG, when set, is the ONLY file: a test pointed at a scratch file must never read
    # or write the real one (found 2026-09-24, when a test run wrote to the author's real config).
    if os.environ.get("LANES_CONFIG"):
        return [os.environ["LANES_CONFIG"]]
    return [os.path.expanduser("~/.claude/lanes.conf"),
            os.path.expanduser("~/.config/lanes/lanes.conf")]


def conf_path_for_write():
    """The file a write goes to: $LANES_CONFIG if set, else the first that exists, else
    ~/.claude/lanes.conf."""
    cands = conf_candidates()
    for p in cands:
        if os.path.isfile(p):
            return p
    return cands[0]


PAT = re.compile(r"^\s*" + re.escape(KEY) + r"\s*=\s*(.*?)\s*$")


def get():
    for path in conf_candidates():
        if not path or not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    m = PAT.match(line.rstrip("\r\n"))
                    if m:
                        value = m.group(1).strip().strip('"').strip("'")
                        return value if value and VALID.match(value) else DEFAULT
        except OSError:
            continue
    return DEFAULT


def write(value):
    path = conf_path_for_write()
    lines = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    new = "%s = %s" % (KEY, value) if value else None
    out, done = [], False
    for line in lines:
        if PAT.match(line):
            if new and not done:
                out.append(new)
            done = True
            continue
        out.append(line)
    if new and not done:
        if out and out[-1].strip():
            out.append("")
        out += ["# The name sessions use for you in notes and on GitHub (set by /lanes:setup).", new]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    return path


def rule(name):
    chosen = name != DEFAULT
    who = ('"%s" - the display name they chose' % name) if chosen else '"User"'
    return (
        "NAMING RULE (lanes plugin) - applies to everything you SAVE or PUBLISH: notes, boards, "
        "commit messages, READMEs, issues, file and folder names. Refer to the person using this "
        "machine only as %s. Never write their real name, login or account name, e-mail address, "
        "machine or host names, or home-folder paths, even if you can see them. Other people: only "
        "a public handle they themselves published (for example in credits for their tool), never a "
        "private name you came across. Talking to the person in this chat is not affected. "
        "%s"
        % (who, "" if chosen else
           "No display name is set; they can choose one with /lanes:setup, and until then it is User.")
    ).strip()


def main(argv):
    if not argv:
        print(get())
        return 0
    cmd = argv[0]
    if cmd == "rule":
        print(rule(get()))
        return 0
    if cmd == "clear":
        print("display name cleared (now %s) in %s" % (DEFAULT, write(None)))
        return 0
    if cmd == "set" and len(argv) >= 2:
        value = " ".join(argv[1:]).strip()
        if not VALID.match(value):
            print("refused: a display name is 1-40 characters of letters, digits, spaces and . _ -",
                  file=sys.stderr)
            return 2
        print("display name set to %s in %s" % (value, write(value)))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
