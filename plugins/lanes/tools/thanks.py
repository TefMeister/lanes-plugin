"""thanks.py - star and follow, on GitHub, the people whose work yours is built on (0.75.0, 2026-10-17, asked for by the
maintainer: "add a star and a follow to anyone who provides even the smallest nugget of useful information or a tool,
mod we can look at, anything like that"). Optional: offered once, at setup or on the update that brings it.

    python thanks.py status [--json]     is it on, is GitHub's command-line tool logged in, may it follow people
    python thanks.py on                  switch it on (thanks = yes in lanes.conf)
    python thanks.py off                 switch it off (thanks = no); nothing already starred is undone
    python thanks.py credits [--dry-run] star the projects Lanes itself is built on (thanks-list.txt) and follow
                                         their owners
    python thanks.py add <owner/repo | owner> [--why "<words>"] [--dry-run]
                                         star that project and follow its owner (an owner alone: follow only).
                                         Does nothing while it is off. Sessions run this the moment a tool, a mod or
                                         even one useful fact is found on someone's GitHub (PROTOCOL section 25).

Exit 0 = done (or nothing to do), 1 = could not (the reason is printed, with the one command that fixes it),
2 = switched off or not set up.

Everything is logged to ~/.claude/lanes/thanks-log.tsv (date, who, what, why). LANES_CONFIG and LANES_STATE_DIR move
the config and the log, for tests; LANES_GH stands in for the gh command.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime

HOME = os.path.expanduser("~")
HERE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(HOME, ".claude", "lanes")
LOG = os.path.join(STATE_DIR, "thanks-log.tsv")
LIST = os.path.join(HERE, "thanks-list.txt")
GH = os.environ.get("LANES_GH") or "gh"
GH_TIMEOUT_S = 60        # one gh call; a star or a follow answers in about a second
SCOPE_FIX = "gh auth refresh -h github.com -s user:follow"
NAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})(?:/[A-Za-z0-9._-]+)?$")


def conf_file():
    if os.environ.get("LANES_CONFIG"):
        return os.environ["LANES_CONFIG"]
    for c in (os.path.join(HOME, ".claude", "lanes.conf"), os.path.join(HOME, ".config", "lanes", "lanes.conf")):
        if os.path.exists(c):
            return c
    return os.path.join(HOME, ".claude", "lanes.conf")


def conf_value():
    try:
        for line in open(conf_file(), encoding="utf-8"):
            k, _, v = line.partition("=")
            if k.strip() == "thanks":
                return v.split(" #")[0].strip().strip('"').lower()
    except OSError:
        pass
    return None


def set_conf(value):
    p = conf_file()
    try:
        lines = open(p, encoding="utf-8").read().splitlines()
    except OSError:
        lines = []
    out, done = [], False
    for line in lines:
        if line.partition("=")[0].strip() == "thanks":
            out.append(f"thanks = {value}")
            done = True
        else:
            out.append(line)
    if not done:
        out.append(f"thanks = {value}   # star + follow the people whose work yours uses (thanks.py, 0.75.0)")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")


def gh(*args):
    try:
        r = subprocess.run([GH, *args], capture_output=True, text=True, timeout=GH_TIMEOUT_S)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, str(e)


def gh_state():
    """(logged_in, may_follow, words)"""
    code, out = gh("auth", "status")
    if code == 127:
        return False, False, "GitHub's command-line tool (gh) is not installed"
    if "Logged in" not in out and code != 0:
        return False, False, "gh is not logged in"
    m = re.search(r"Token scopes:\s*(.*)", out)
    scopes = m.group(1) if m else ""
    return True, ("user:follow" in scopes or "'user'" in scopes), scopes.strip()


def log(who, what, why):
    os.makedirs(STATE_DIR, exist_ok=True)
    new = not os.path.exists(LOG)
    with open(LOG, "a", encoding="utf-8", newline="\n") as f:
        if new:
            f.write("date\twho\twhat\twhy\n")
        f.write(f"{datetime.now().isoformat(timespec='seconds')}\t{who}\t{what}\t{why}\n")


def thank(target, why, dry):
    """star owner/repo (if a repo is given) and follow the owner; returns a list of failures"""
    owner = target.split("/")[0]
    fails = []
    steps = ([("star", target, ("api", "-X", "PUT", f"user/starred/{target}"))] if "/" in target else []) + \
            [("follow", owner, ("api", "-X", "PUT", f"user/following/{owner}"))]
    for what, who, args in steps:
        if dry:
            print(f"  would {what} {who}")
            continue
        code, out = gh(*args)
        if code == 0:
            log(who, what, why)
        else:
            fails.append(f"{what} {who}: " + ("not found on GitHub" if "404" in out else out.strip().splitlines()[0][:100]))
    return fails


def ready():
    if conf_value() != "yes":
        print("switched off: `python thanks.py on` switches it on (thanks = yes in lanes.conf).")
        return 2
    logged, may_follow, words = gh_state()
    if not logged:
        print(f"cannot: {words}. Log in with `gh auth login`, then run this again.")
        return 1
    if not may_follow:
        print(f"cannot follow yet: GitHub has not given this PC permission to follow people. Run once: `! {SCOPE_FIX}`")
        return 1
    return 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    dry = "--dry-run" in rest
    if cmd == "status":
        logged, may_follow, words = gh_state()
        st = {"on": conf_value() == "yes", "setting": conf_value(), "gh_logged_in": logged, "may_follow": may_follow,
              "fix": None if may_follow else (SCOPE_FIX if logged else "gh auth login")}
        if "--json" in rest:
            print(json.dumps(st))
        else:
            print(("on" if st["on"] else "off") + "; gh " + ("logged in" if logged else "not logged in")
                  + ("; may follow people" if may_follow else f"; to follow people run once: {st['fix']}"))
        return 0
    if cmd in ("on", "off"):
        set_conf("yes" if cmd == "on" else "no")
        print("on: sessions star and follow the people whose work yours uses." if cmd == "on"
              else "off: nothing new is starred or followed; what already is stays.")
        return 0
    if cmd == "credits":
        r = 0 if dry else ready()
        if r:
            return r
        targets = [l.split("#")[0].strip() for l in open(LIST, encoding="utf-8")]
        targets = [t for t in targets if t and NAME.match(t)]
        fails = []
        for t in targets:
            fails += thank(t, "Lanes is built on it", dry)
        print(f"{len(targets) - len(fails)} done" + (f"; could not: {'; '.join(fails)}" if fails else ""))
        return 0
    if cmd == "add" and rest and not rest[0].startswith("-"):
        target = rest[0].strip().rstrip("/")
        target = re.sub(r"^(https?://)?github\.com/", "", target)
        target = "/".join(target.split("/")[:2])
        if not NAME.match(target):
            print(f"not a GitHub name: {rest[0]}")
            return 1
        why = rest[rest.index("--why") + 1] if "--why" in rest and rest.index("--why") + 1 < len(rest) else ""
        r = 0 if dry else ready()
        if r:
            return r
        fails = thank(target, why, dry)
        print("could not: " + "; ".join(fails) if fails else f"thanked {target}")
        return 1 if fails else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):   # a character the console cannot show prints as ? (0.94.2)
        try:
            _stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))
