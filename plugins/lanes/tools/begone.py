"""begone.py - BeG0nE rides every session (0.52.0): start its background rider, and say in one line what it holds.

    python begone.py brief      start the rider if it is not running; print one line for the session start
    python begone.py status     the same line, for a person

BeG0nE (a separate, public repo) collects, while a game runs in VR, what a VR mod did with the headset pose, the
camera and the controllers, and keeps a knowledge base of what jittery and smooth cameras look like in the numbers.
Its code is updated on its own; this plugin only knows where the clone is (`begone = ...` in lanes.conf, or
$LANES_BEGONE) and starts its rider once per session. The rider idles until a mod starts a VR session, so it costs
nothing during ordinary work. With no clone configured, this says nothing.

Nothing printed here names a path, a machine or a person: project names and counts only.
"""
import csv
import json
import os
import re
import subprocess
import sys

START_TIMEOUT_S = 20
RIDER = os.path.join("camera-jitter", "ride-along", "ride.py")
INDEX = os.path.join("camera-jitter", "data", "INDEX.csv")
PATTERNS = os.path.join("camera-jitter", "knowledge", "patterns.json")


def conf_path():
    return os.environ.get("LANES_CONFIG") or os.path.join(os.path.expanduser("~"), ".claude", "lanes.conf")


def read_conf():
    conf = {}
    try:
        with open(conf_path(), encoding="utf-8") as f:
            for line in f:
                m = re.match(r"^\s*([A-Za-z_]+)\s*=\s*(.*?)\s*(#.*)?$", line)
                if m and not line.lstrip().startswith("#"):
                    conf[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    except OSError:
        pass
    return conf


def clone():
    c = os.environ.get("LANES_BEGONE") or read_conf().get("begone", "")
    return c if c and os.path.isfile(os.path.join(c, RIDER)) else None


def rider_running(root):
    try:
        r = subprocess.run([sys.executable, os.path.join(root, RIDER), "status"], capture_output=True, text=True,
                           timeout=START_TIMEOUT_S)
        return "rider: running" in r.stdout
    except (OSError, subprocess.SubprocessError):
        return False


def start_rider(root):
    try:
        subprocess.run([sys.executable, os.path.join(root, RIDER), "start"], capture_output=True, text=True,
                       timeout=START_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError):
        pass
    return rider_running(root)


def held(root):
    """(sessions on file, patterns, last session's game and verdict) - counts and project names only."""
    sessions, last = 0, None
    try:
        with open(os.path.join(root, INDEX), newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        sessions = len(rows)
        if rows:
            r = max(rows, key=lambda r: (r.get("date", ""), r.get("time", "")))
            last = f"{r.get('game', '?')} on {r.get('date', '?')}: {(r.get('verdict') or '')[:90]}"
    except (OSError, csv.Error):
        pass
    patterns = 0
    try:
        with open(os.path.join(root, PATTERNS), encoding="utf-8") as f:
            patterns = len(json.load(f).get("patterns", {}))
    except (OSError, ValueError):
        pass
    return sessions, patterns, last


def line(start=True):
    root = clone()
    if not root:
        return ""
    running = rider_running(root) or (start and start_rider(root))
    sessions, patterns, last = held(root)
    state = "running" if running else "NOT running (python ride.py start in the BeG0nE clone)"
    out = f"BeG0nE rider {state}: {sessions} VR sessions on file, {patterns} behaviour patterns."
    if last:
        out += f" Last: {last}"
    if not sessions:
        out += " It idles until a mod wired to jitterlog.h starts a VR session."
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] in ("brief", "status"):
        s = line(start=(a[0] == "brief"))
        if s:
            print(s)
    else:
        sys.exit(__doc__)
