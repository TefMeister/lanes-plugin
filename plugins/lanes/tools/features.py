#!/usr/bin/env python3
"""features.py - the built-in extras a NEW install chooses at setup (0.82.0, 2026-10-23, asked for by the maintainer:
"see if there are any features of Lanes plugin that are not optional right now, but can be made optional at the
first install. no need to make them optional for people updating the plugin as they already have these features").

    python features.py status [--json]       each extra: on or off, and why
    python features.py on <name>|all         switch one on (written to lanes.conf)
    python features.py off <name>|all        switch one off
    python features.py is-on <name>          exit 0 = on, 1 = off (what hooks and commands ask)
    python features.py pending               the extras a new install has not answered yet (exit 1 = none)

THE EXTRAS (each one was on for everybody, with no question, before 0.82.0)
  theme             the green-monitor look put on the terminal at the first session
  talk_rule         the session never says "you are right" before checking (a session-start rule)
  begone_ride       the BeG0nE rider at every session start, and early VR mods wired to its recorders
  vr_effects_off    VR sessions switch off every blur and screen effect in a game (PROTOCOL section 19)
  gu_nudge          the one-line reminder when the weekly tool check is a week old
  keep_transcripts  every conversation's full log copied out of Claude Code's 30-day clean-up

HOW A NEW INSTALL IS TOLD FROM AN UPDATE
  The first time anything asks, this PC is sorted once and for all into features-state.json:
  - "update": lanes.conf, or anything else of Lanes in the state folder, was already there (older than five
    minutes, because the other session-start hooks run at the same moment and may have just made theirs). Everything stays on, as
    it was; nobody is asked.
  - "new": nothing of Lanes was on this PC. Every extra is off until /lanes:setup asks (one question, all six);
    the answer is written to lanes.conf. Skipping setup leaves them off; `on <name>` switches one on any time.
  An explicit `<name> = on|off` in lanes.conf always wins, on either kind of PC.
Tests set LANES_STATE_DIR and LANES_CONFIG.
"""
import json
import os
import sys
import time

HOME = os.path.expanduser("~")
STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(HOME, ".claude", "lanes")
STATE_FILE = os.path.join(STATE_DIR, "features-state.json")
VERSION = "0.82.0"
FRESH_WINDOW_S = 300

FEATURES = {
    "theme": "the green-monitor look on the terminal",
    "talk_rule": "never \"you are right\" before checking",
    "begone_ride": "the BeG0nE rider and its VR recorders",
    "vr_effects_off": "blur and screen effects off in VR games",
    "gu_nudge": "a reminder when the weekly tool check is due",
    "keep_transcripts": "full conversation logs kept past 30 days",
}
ON_WORDS, OFF_WORDS = ("on", "yes", "true", "1"), ("off", "no", "false", "0")


def conf_file():
    if os.environ.get("LANES_CONFIG"):
        return os.environ["LANES_CONFIG"]
    for c in (os.path.join(HOME, ".claude", "lanes.conf"), os.path.join(HOME, ".config", "lanes", "lanes.conf")):
        if os.path.exists(c):
            return c
    return os.path.join(HOME, ".claude", "lanes.conf")


def conf_value(key):
    try:
        for line in open(conf_file(), encoding="utf-8"):
            k, _, v = line.partition("=")
            if k.strip() == key:
                return v.split("#")[0].strip().strip('"').lower()
    except OSError:
        pass
    return None


def set_conf(key, value, note):
    p = conf_file()
    try:
        lines = open(p, encoding="utf-8").read().splitlines()
    except OSError:
        lines = []
    out, done = [], False
    for line in lines:
        if line.partition("=")[0].strip() == key:
            out.append(f"{key} = {value}")
            done = True
        else:
            out.append(line)
    if not done:
        out.append(f"{key} = {value}   # {note} (features.py, 0.82.0)")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")


def kind():
    """'new' or 'update', decided the first time and kept."""
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)["kind"]
    except (OSError, ValueError, KeyError):
        pass
    # Session-start hooks run side by side, so another hook may have written its first file a moment ago: only
    # files older than that count as Lanes having been here before.
    cutoff = time.time() - FRESH_WINDOW_S
    old = [conf_file()] + ([os.path.join(STATE_DIR, n) for n in os.listdir(STATE_DIR)
                            if n != os.path.basename(STATE_FILE)] if os.path.isdir(STATE_DIR) else [])
    had_lanes = any(os.path.exists(p) and os.path.getmtime(p) < cutoff for p in old)
    k = "update" if had_lanes else "new"
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"kind": k, "since": VERSION}, f)
    return k


def why(name):
    v = conf_value(name)
    if v in ON_WORDS:
        return True, "switched on"
    if v in OFF_WORDS:
        return False, "switched off"
    if kind() == "update":
        return True, "on, as before this version"
    return False, "not chosen yet (setup asks)"


def is_on(name):
    return why(name)[0]


def pending():
    if kind() != "new":
        return []
    return [n for n in FEATURES if conf_value(n) not in ON_WORDS + OFF_WORDS]


def names(arg):
    if arg == "all":
        return list(FEATURES)
    if arg in FEATURES:
        return [arg]
    raise SystemExit(f"Unknown extra '{arg}'. Known: {', '.join(FEATURES)}")


def main(argv):
    a = argv[1:]
    cmd = a[0] if a else "status"
    if cmd == "status":
        rows = {n: dict(zip(("on", "why"), why(n)), what=FEATURES[n]) for n in FEATURES}
        if "--json" in a:
            print(json.dumps({"kind": kind(), "features": rows}, indent=1))
        else:
            for n, r in rows.items():
                print(f"{n:17} {'ON ' if r['on'] else 'off'}  {r['what']}  ({r['why']})")
        return 0
    if cmd in ("on", "off") and len(a) > 1:
        for n in names(a[1]):
            set_conf(n, cmd, FEATURES[n])
        print(f"{a[1]}: {cmd} (in {conf_file()})")
        return 0
    if cmd == "is-on" and len(a) > 1:
        return 0 if is_on(names(a[1])[0]) else 1
    if cmd == "pending":
        p = pending()
        print("\n".join(p) if p else "none")
        return 0 if p else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
