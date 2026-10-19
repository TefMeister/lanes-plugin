"""unlock.py - the "unlock everything first" setting (0.81.0, docs/PROTOCOL.md section 28).

    python unlock.py on        sessions look for a way to unlock everything in each game before modding it
    python unlock.py off       they do not (the default)
    python unlock.py status    prints on / off

When it is on, the first sessions on a game look for a developer mode, a cheat or console command, a setting, a
command-line switch or a file that makes every weapon and item available from the start, so nobody has to play
through the game to unlock them before the modding can begin: /pd from the game's files without running it, /lm
on the first run. What was found, and how sure it is, goes on the project's board and into its notes.
Writes `unlock_all = yes|no` in lanes.conf. LANES_CONFIG points the tests at another file.
"""
import os
import sys

HOME = os.path.expanduser("~")
KEY = "unlock_all"


def conf_file():
    if os.environ.get("LANES_CONFIG"):
        return os.environ["LANES_CONFIG"]
    for c in (os.path.join(HOME, ".claude", "lanes.conf"), os.path.join(HOME, ".config", "lanes", "lanes.conf")):
        if os.path.exists(c):
            return c
    return os.path.join(HOME, ".claude", "lanes.conf")


def value():
    try:
        for line in open(conf_file(), encoding="utf-8"):
            k, _, v = line.partition("=")
            if k.strip() == KEY:
                return v.split(" #")[0].strip().strip('"').lower()
    except OSError:
        pass
    return None


def set_value(v):
    p = conf_file()
    try:
        lines = open(p, encoding="utf-8").read().splitlines()
    except OSError:
        lines = []
    out, done = [], False
    for line in lines:
        if line.partition("=")[0].strip() == KEY:
            out.append(f"{KEY} = {v}")
            done = True
        else:
            out.append(line)
    if not done:
        out.append(f"{KEY} = {v}   # look for a way to unlock every weapon and item before modding a game (unlock.py, 0.81.0)")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "status"
    if cmd in ("on", "off"):
        set_value("yes" if cmd == "on" else "no")
        print(f"{KEY} = {'yes' if cmd == 'on' else 'no'} in {conf_file()}")
        return 0
    if cmd == "status":
        print("on" if value() == "yes" else "off")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
