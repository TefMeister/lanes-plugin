#!/usr/bin/env python3
"""installed.py - which of our own apps each PC has, so one PC knows what the other already has (0.65.0, 2026-10-14).

Why: Hand Freeze was installed and tested on one PC, and the other PC never found out. Its reminder to install it
was still open a day later, and a session there planned work around it as if it were missing. The maintainer asked
for "knowledge sharing" between the PCs so that cannot happen again.

    python installed.py record <app> <release>   note that THIS PC now has <app> at <release> (install tools call it)
    python installed.py scan                     look at this PC, and update its note if anything changed
    python installed.py brief                    scan, then one line per difference with the other PCs; silent if none
    python installed.py list                     every PC's apps, read from GitHub's copy of the board

WHERE: <board>/installed/<PC name>.json, one file per PC, so two PCs can never write the same file. The PC name comes
from machine-name.py (PC1, PC2 or a name the person chose), never the computer's real name. Other PCs' notes are read
from origin/main, after a quick fetch, because a note written elsewhere arrives only through git.

Like owed.sh, this NEVER commits: it writes one file and the close-out box reports it as unsaved until the session
saves the board. Exit 0 always for brief/scan (a start-up check must never be why a session opens with an error).

APPS it can find by itself (scan): Hand Freeze, VR Bench. A new app of ours adds one line to APPS.
Tests set LANES_BOARD, LANES_CONFIG, LANES_HANDFREEZE_DIR and LANES_VRBENCH_LAYER_DIR.
"""
import datetime
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOCALAPPDATA = os.environ.get("LOCALAPPDATA", os.path.join(os.path.expanduser("~"), "AppData", "Local"))
FOLDER = "installed"
FETCH_TIMEOUT_S = 8


def handfreeze_found():
    d = os.environ.get("LANES_HANDFREEZE_DIR") or os.path.join(LOCALAPPDATA, "Programs", "HandFreeze")
    if not os.path.isfile(os.path.join(d, "HandFreeze.exe")):
        return None
    try:
        with open(os.path.join(d, "lanes-release.txt"), encoding="utf-8") as f:
            return f.read().strip() or "release unknown"
    except OSError:
        return "release unknown"


def vrbench_found():
    """VR Bench's layer (0.74.0), where its install.ps1 put it"""
    d = os.environ.get("LANES_VRBENCH_LAYER_DIR") or os.path.join(LOCALAPPDATA, "Programs", "VRBench")
    if not any(os.path.isfile(os.path.join(d, f)) for f in ("vrbench_layer.dll", "vrbench_layer32.dll")):
        return None
    try:
        with open(os.path.join(d, "lanes-release.txt"), encoding="utf-8") as f:
            return f.read().strip() or "release unknown"
    except OSError:
        return "release unknown"


# app name -> how to find it on this PC (returns the release, or None when absent)
APPS = {"Hand Freeze": handfreeze_found, "VR Bench": vrbench_found}


def conf_files():
    if os.environ.get("LANES_CONFIG"):
        return [os.environ["LANES_CONFIG"]]
    return [os.path.expanduser("~/.claude/lanes.conf"), os.path.expanduser("~/.config/lanes/lanes.conf")]


def board():
    if os.environ.get("LANES_BOARD"):
        return os.environ["LANES_BOARD"]
    for c in conf_files():
        try:
            for line in open(c, encoding="utf-8"):
                k, _, v = line.partition("=")
                if k.strip() == "board" and v.strip():
                    return v.split(" #")[0].strip().strip('"')
        except OSError:
            pass
    return None


def pc_name():
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, "machine-name.py")], capture_output=True, text=True,
                           timeout=FETCH_TIMEOUT_S)
        name = "".join(ch for ch in r.stdout.strip() if ch.isalnum() or ch in "._-")
        return name or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def git(b, *args, timeout=FETCH_TIMEOUT_S):
    try:
        return subprocess.run(["git", "-C", b, *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None


def mine_path(b, me):
    return os.path.join(b, FOLDER, me + ".json")


def read_mine(b, me):
    try:
        with open(mine_path(b, me), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write_mine(b, me, data):
    os.makedirs(os.path.join(b, FOLDER), exist_ok=True)
    with open(mine_path(b, me), "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def record(b, me, app, release):
    data = read_mine(b, me)
    if data.get(app, {}).get("release") == release:
        return False
    data[app] = {"release": release, "since": datetime.date.today().isoformat()}
    write_mine(b, me, data)
    return True


def scan(b, me):
    data, changed = read_mine(b, me), False
    for app, find in APPS.items():
        rel = find()
        if rel is None and app in data:
            del data[app]
            changed = True
        elif rel is not None and data.get(app, {}).get("release") != rel:
            # keep a known release rather than overwrite it with "release unknown"
            if not (rel == "release unknown" and data.get(app, {}).get("release")):
                data[app] = {"release": rel, "since": datetime.date.today().isoformat()}
                changed = True
    if changed:
        write_mine(b, me, data)
    return changed


def others(b, me):
    """{pc: {app: {...}}} for every OTHER pc, from origin/main (falls back to this disk if there is no remote)."""
    git(b, "fetch", "-q", "origin", "main")
    r = git(b, "rev-parse", "--verify", "-q", "origin/main")
    ref = "origin/main" if r and r.returncode == 0 else "HEAD"
    r = git(b, "ls-tree", "--name-only", f"{ref}:{FOLDER}")
    names = [n for n in (r.stdout.split() if r and r.returncode == 0 else []) if n.endswith(".json")]
    out = {}
    for n in names:
        pc = n[:-5]
        if pc == me:
            continue
        s = git(b, "show", f"{ref}:{FOLDER}/{n}")
        try:
            out[pc] = json.loads(s.stdout) if s and s.returncode == 0 else {}
        except ValueError:
            out[pc] = {}
    return out


def brief(b, me):
    scan(b, me)
    mine = read_mine(b, me)
    lines = []
    for pc, apps in sorted(others(b, me).items()):
        for app, info in sorted(apps.items()):
            rel = info.get("release", "?")
            have = mine.get(app, {}).get("release")
            if have is None:
                lines.append(f"{pc} has {app} ({rel}, since {info.get('since', '?')}); this PC does not.")
            elif have != rel and "unknown" not in (have + rel):
                lines.append(f"{app}: {pc} has {rel}, this PC has {have}.")
    if lines:
        print("OUR APPS ON YOUR OTHER PCs (installed.py; their own notes, so trust them over older reminders):")
        for line in lines:
            print("  " + line)
    if scan_note_unsaved(b, me):
        print(f"This PC's app note ({FOLDER}/{me}.json) changed: it is saved with the board at the end of the session.")


def scan_note_unsaved(b, me):
    r = git(b, "status", "--porcelain", "--", f"{FOLDER}/{me}.json")
    return bool(r and r.stdout.strip())


def main(argv):
    if not argv or argv[0] not in ("record", "scan", "brief", "list"):
        print(__doc__)
        return 1
    b, me = board(), pc_name()
    if not b or not os.path.isdir(b) or not me:
        if argv[0] in ("record", "list"):
            print("No board or no PC name set up, so there is nowhere to keep the note.")
        return 0
    cmd = argv[0]
    if cmd == "record":
        if len(argv) < 3:
            print("record needs an app and a release")
            return 1
        if record(b, me, argv[1], argv[2]):
            print(f"Noted for the other PCs: {me} has {argv[1]} {argv[2]}. Saved with the board at the session's end.")
        return 0
    if cmd == "scan":
        scan(b, me)
        return 0
    if cmd == "brief":
        try:
            brief(b, me)
        except Exception:  # a start-up check stays silent rather than break the session
            pass
        return 0
    allpcs = others(b, me)
    allpcs[me + " (this PC)"] = read_mine(b, me)
    for pc, apps in sorted(allpcs.items()):
        print(pc + ": " + (", ".join(f"{a} {i.get('release', '?')}" for a, i in sorted(apps.items())) or "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
