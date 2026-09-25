#!/usr/bin/env python3
"""machine-name - what this PC is called in anything the lanes write down.

    python machine-name.py             print this PC's name; if none is set yet, take the next free
                                       PC1, PC2, ... and save it
    python machine-name.py suggest     print the name that would be taken, and change nothing
    python machine-name.py set NAME    call this PC NAME instead

WHY (0.24.0)
  A live claim and a "this machine owes" reminder both say which PC wrote them, because two
  sessions on one PC share one keyboard and must know it. Until 0.24.0 they wrote the computer's
  real name - into the board and into commit messages - against the plugin's own naming rule. An
  outside audit found it. Now every PC has a plain name: one the person picks in /lanes:setup, or
  simply PC1, PC2 and so on.

HOW NAMES STAY DIFFERENT
  The board keeps `machines.txt`, one name per line. A new name is added there and pushed (only that
  file is committed), and the next free number is read from it, so a second PC becomes PC2 rather
  than a second PC1. With no board, the name is still saved on this PC.

The name lives as `machine_name = ...` in lanes.conf. Letters, digits and . _ - only, up to 24
characters, and never the computer's real name.
"""
import os
import re
import socket
import subprocess
import sys

KEY = "machine_name"
PREFIX = "PC"
REGISTRY = "machines.txt"
VALID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,23}$")
PAT = re.compile(r"^\s*" + re.escape(KEY) + r"\s*=\s*(.*?)\s*$")
REGISTRY_HEAD = ("# One name per PC that uses this board, written by the lanes plugin (tools/machine-name.py).\n"
                 "# Names only, never a computer's real name.\n")


def conf_candidates():
    if os.environ.get("LANES_CONFIG"):
        return [os.environ["LANES_CONFIG"]]
    return [os.path.expanduser("~/.claude/lanes.conf"), os.path.expanduser("~/.config/lanes/lanes.conf")]


def conf_get(key):
    pat = re.compile(r"^\s*" + re.escape(key) + r"\s*=\s*(.*?)\s*$")
    for path in conf_candidates():
        if os.path.isfile(path):
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    m = pat.match(line.rstrip("\r\n"))
                    if m and not line.lstrip().startswith("#"):
                        return m.group(1).strip().strip('"').strip("'")
    return ""


def conf_set(value):
    cands = conf_candidates()
    path = next((p for p in cands if os.path.isfile(p)), cands[0])
    lines = open(path, encoding="utf-8").read().splitlines() if os.path.isfile(path) else []
    out, done = [], False
    for line in lines:
        if PAT.match(line):
            if not done:
                out.append("%s = %s" % (KEY, value))
            done = True
            continue
        out.append(line)
    if not done:
        if out and out[-1].strip():
            out.append("")
        out += ["# What this PC is called in claims and reminders (set by /lanes:setup).", "%s = %s" % (KEY, value)]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")


def real_names():
    names = {socket.gethostname(), os.environ.get("COMPUTERNAME", "")}
    return {n.lower() for n in names if n}


def board():
    b = os.environ.get("LANES_BOARD", "") or conf_get("board")
    return b if b and os.path.isdir(b) else ""


def registered(b):
    f = os.path.join(b, REGISTRY) if b else ""
    if not f or not os.path.isfile(f):
        return []
    return [l.strip() for l in open(f, encoding="utf-8") if l.strip() and not l.startswith("#")]


def next_free(taken):
    low = {t.lower() for t in taken}
    n = 1
    while ("%s%d" % (PREFIX, n)).lower() in low:
        n += 1
    return "%s%d" % (PREFIX, n)


def git(b, *args):
    return subprocess.run(["git", "-C", b] + list(args), capture_output=True, text=True, timeout=60).returncode == 0


def register(new, old=""):
    """Add NEW to the board's list (dropping OLD) and push that one file. Best effort: a PC with no
    board, no network or a busy clone still gets its name; the list catches up on the next push."""
    b = board()
    if not b:
        return "saved on this PC only (no board set)"
    git(b, "pull", "-q", "--rebase")
    names = [n for n in registered(b) if n.lower() != old.lower() and n.lower() != new.lower()] + [new]
    with open(os.path.join(b, REGISTRY), "w", encoding="utf-8", newline="\n") as f:
        f.write(REGISTRY_HEAD + "\n".join(names) + "\n")
    if not git(b, "add", "--", REGISTRY) or not git(b, "commit", "-q", "-m", "machines: %s" % new, "--", REGISTRY):
        return "added to the board's %s, but could not commit it" % REGISTRY
    if git(b, "push", "-q"):
        return "added to the board's %s and pushed" % REGISTRY
    return "added to the board's %s and committed; it goes out with the next push" % REGISTRY


def current():
    v = conf_get(KEY)
    return v if VALID.match(v or "") and v.lower() not in real_names() else ""


def main(argv):
    cmd = argv[0] if argv else "get"
    if cmd == "get":
        name = current()
        if not name:
            b = board()
            if b:
                git(b, "pull", "-q", "--rebase")
            name = next_free(registered(b))
            conf_set(name)
            register(name)
        print(name)
        return 0
    if cmd == "suggest":
        print(current() or next_free(registered(board())))
        return 0
    if cmd == "set" and len(argv) == 2:
        new, old = argv[1].strip(), current()
        if not VALID.match(new):
            print("refused: a PC name is 1-24 letters, digits or . _ - (no spaces)", file=sys.stderr)
            return 2
        if new.lower() in real_names():
            print("refused: that is the computer's real name, which the lanes never write down", file=sys.stderr)
            return 2
        if new.lower() != old.lower() and new.lower() in {n.lower() for n in registered(board())}:
            print("refused: another PC on this board is already called %s" % new, file=sys.stderr)
            return 2
        conf_set(new)
        print("this PC is now %s; %s" % (new, register(new, old)))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
