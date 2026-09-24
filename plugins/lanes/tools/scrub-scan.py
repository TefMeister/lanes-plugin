#!/usr/bin/env python3
"""scrub-scan - does anything in this folder carry a real person's identifiers?

    python scrub-scan.py [path]        human-readable report; exit 1 if anything is found
    python scrub-scan.py --json [path] machine-readable

Read-only. Never edits a file.

WHY THIS EXISTS (2026-09-18)
  The release checklist has always had a bar B2, "no personal data anywhere - no project names,
  machine names, account names, paths", and the way to check it was "grep the whole plugin folder".
  Nobody did, for six weeks. The first real audit found a spec file holding the author's Windows
  username, their home-directory layout, their working directory, two session UUIDs and a verbatim
  excerpt of their personal settings.json - committed, and one repo-visibility toggle from public.

  None of that came from the plugin's design. It came from writing documentation with real captured
  output pasted into it, which is the natural thing to do and is invisible afterwards. A checklist
  line cannot catch that. A command can.

  !! WHAT THIS CANNOT DO: it scans the working tree. It does not rewrite git HISTORY, and history is
  what publishing a repo actually publishes. A clean scan on a repo whose past commits carry the
  same data means the files are clean and the repo is not. Deciding that is a person's job.

WHAT IT LOOKS FOR
  Four things, chosen because each is mechanical and near-zero false positives. Deliberately NOT a
  general secret scanner - it answers one question, "is a human identifiable from this folder".
"""
import argparse
import json
import os
import re
import socket
import subprocess
import sys

# Placeholders that are meant to be there. A finding matching one of these is not a finding.
SAFE_NAMES = {
    "user", "username", "you", "yourname", "your-name", "someone", "example",
    "x", "xx", "test", "fixture", "runner", "ci", "home", "root", "admin",
    "<user>", "<username>", "<you>", "<name>", "me",
}
SAFE_EMAIL_DOMAINS = ("example.invalid", "example.com", "example.org", "noreply.github.com")
SAFE_EMAIL_LOCAL = ("noreply", "fixture", "test")
# The placeholder UUIDs the scrubbed payload capture uses. Any OTHER uuid is suspect.
SAFE_UUIDS = {
    "11111111-1111-4111-8111-111111111111",
    "22222222-2222-4222-8222-222222222222",
    "00000000-0000-0000-0000-000000000000",
}

HOME_RE = re.compile(
    r"(?:C:\\{1,2}Users\\{1,2}|/home/|/Users/)"          # a home-directory root
    r"([A-Za-z0-9_.\-<>]+)",                              # whatever is named as the user
    re.IGNORECASE)
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
                     re.IGNORECASE)

SKIP_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".zip", ".dll", ".exe", ".pyc")
SKIP_DIRS = {".git", "__pycache__", "fixture-board", "build", "node_modules"}


def tracked_files(root):
    """Prefer git's own list: anything untracked is not going to be published."""
    try:
        out = subprocess.run(["git", "-C", root, "ls-files"], capture_output=True, text=True,
                             timeout=30, encoding="utf-8", errors="replace")
        if out.returncode == 0 and out.stdout.strip():
            return [os.path.join(root, p) for p in out.stdout.splitlines() if p.strip()]
    except (OSError, subprocess.TimeoutExpired):
        pass
    found = []
    for base, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        found += [os.path.join(base, n) for n in names]
    return found


# A line carrying this marker is skipped, and the skip is COUNTED and reported. Some identifiers
# are there on purpose - a security contact address is the obvious one - and a check with no way to
# say so gets switched off entirely, which is worse. The count is printed on a clean run so an
# allowlist cannot grow quietly into the thing it was meant to prevent.
ALLOW_MARKER = "scrub-scan:allow"

NAMES_FILE = "never-publish.txt"


def names_path():
    """The PRIVATE word list: on this machine only, never inside the plugin (0.22.0).

    Until 0.22.0 this list was a file shipped in the plugin itself - so publishing the plugin
    published the very words it listed. It now lives beside the plugin's other per-machine state.
    """
    state = os.environ.get("LANES_STATE_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "lanes")
    return os.path.join(state, NAMES_FILE)


def forbidden_names(path=None):
    """Extra words this machine's owner never wants published - a nickname, another PC's name.

    The four built-in checks all work off SHAPE: a home path, an email, a UUID, the running
    machine's name. A person's first name has no shape; it is just a word, and only its owner
    knows which words are theirs. So those are declared, privately, not detected.
    """
    path = path or names_path()
    names = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    names.append(line)
    except OSError:
        pass
    return names


def findings_in(path, text, hostname, names=()):
    if ALLOW_MARKER in text:
        return []
    out = []

    for name in names:
        # Whole words only, so a declared name that is also an ordinary word does not fire on
        # every ordinary use of it.
        for m in re.finditer(r"(?<![A-Za-z0-9_-])%s(?![A-Za-z0-9_-])" % re.escape(name),
                             text, re.IGNORECASE):
            out.append(("declared name", m.group(0),
                        "on this machine's private never-publish list; use 'User' or the "
                        "chosen display name (tools/display-name.py)"))

    for m in HOME_RE.finditer(text):
        name = m.group(1)
        if name.lower().strip("<>") in SAFE_NAMES:
            continue
        out.append(("home path", m.group(0),
                    "names a real account; use C:\\Users\\<user> or /home/<user>"))

    for m in EMAIL_RE.finditer(text):
        addr = m.group(0)
        local, _, domain = addr.partition("@")
        if domain.lower().endswith(SAFE_EMAIL_DOMAINS) or local.lower().startswith(SAFE_EMAIL_LOCAL):
            continue
        out.append(("email", addr, "a real address; use one at example.invalid"))

    for m in UUID_RE.finditer(text):
        if m.group(0).lower() in SAFE_UUIDS:
            continue
        out.append(("uuid", m.group(0),
                    "session and agent ids identify a real run; use a placeholder"))

    # The machine's own name, whatever it happens to be - so this check works for whoever runs it,
    # not only for the person whose leak prompted it.
    if hostname and len(hostname) >= 4:
        for m in re.finditer(re.escape(hostname), text, re.IGNORECASE):
            out.append(("hostname", m.group(0), "this machine's name; use <DEV-HOST> or similar"))

    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", nargs="?", default=None,
                    help="folder to scan (default: the plugin this script is in)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--hostname", default=None, help="override, for tests")
    ap.add_argument("--names", default=None,
                    help="private never-publish word list (default: ~/.claude/lanes/never-publish.txt)")
    args = ap.parse_args()

    root = os.path.abspath(args.path or os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    hostname = args.hostname if args.hostname is not None else (socket.gethostname() or "")
    names = forbidden_names(args.names)

    results, allowed = [], []
    for path in sorted(set(tracked_files(root))):
        if path.lower().endswith(SKIP_SUFFIXES) or not os.path.isfile(path):
            continue
        if any(part in SKIP_DIRS for part in path.replace("\\", "/").split("/")):
            continue
        if os.path.abspath(path) == os.path.abspath(__file__):
            continue          # this file names the patterns it looks for
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
        except OSError:
            continue
        rel = os.path.relpath(path, root).replace("\\", "/")
        for n, line in enumerate(lines, 1):
            # The marker covers its OWN line and the one after it. Markdown and JSON have no
            # inline comment, so the only place to put it is the line above the thing it excuses.
            prev = lines[n - 2] if n >= 2 else ""
            if ALLOW_MARKER in line or ALLOW_MARKER in prev:
                if ALLOW_MARKER in line:
                    allowed.append("%s:%d" % (rel, n))
                continue
            for kind, value, why in findings_in(path, line, hostname, names):
                results.append({"file": rel, "line": n, "kind": kind,
                                "value": value, "why": why})

    if args.json:
        print(json.dumps({"root": root, "hostname": hostname, "findings": results,
                          "allowed": allowed}, indent=2))
        return 1 if results else 0

    if not results:
        print("scrub-scan: clean - nothing in %s identifies a person." % root)
        if names:
            print("  %d private word(s) enforced from this machine's %s." % (len(names), NAMES_FILE))
        if allowed:
            print("  %d line(s) carry an explicit allow marker:" % len(allowed))
            for a in allowed:
                print("    %s" % a)
        # ASCII only, deliberately: a Windows console defaults to cp1252 and raises
        # UnicodeEncodeError on a warning sign. That crashed this tool on a CLEAN result -
        # turning a pass into a stack trace and exit 1, which is the worst possible direction
        # for a checker to fail in.
        print("  !! This is the working tree only. Git history is what publishing publishes,")
        print("     and this cannot see it: check that separately before making a repo public.")
        return 0

    print("scrub-scan: %d finding(s) in %s\n" % (len(results), root))
    for r in results:
        print("  %-9s %s:%d" % (r["kind"], r["file"], r["line"]))
        print("            %s  -- %s" % (r["value"], r["why"]))
    print("\nEach of these would be published if this repo were made public.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
