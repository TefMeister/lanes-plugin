#!/usr/bin/env python3
"""remote-control.py - every Claude Code session on this PC starts with Remote Control on (0.87.0, 2026-10-26).

    python remote-control.py on       every new session starts with Remote Control on, named after this PC
    python remote-control.py off      sessions start without it (the default); /remote-control still turns it on
    python remote-control.py status   prints on / off, and what Claude Code's settings say
    python remote-control.py apply    makes Claude Code's settings follow the extra (setup runs this)

Remote Control is Claude Code's own: a session with it on can be seen and typed into from the Claude phone app or
claude.ai/code, and a session on another PC of the same account can send it a job. Typing /remote-control (short:
/rc) in a session turns it on for that session only. This tool switches it on for every session, by writing
`remoteControlAtStartup` into the user's Claude Code settings (a repo's own settings cannot switch it on), and names
the sessions after this PC's Lanes name (machine-name.py), never after the computer's real name, which is what Claude
Code would use otherwise. It takes effect from the next session.

Asked for by the maintainer: "remote control toggled on at every session start by default, and have that as an
option in Lanes as well - ask user if remote control should be on by default and tell them the slash command if they
want it enabled manually". The extra is `remote_control` (features.py); it is asked once, also on PCs that had Lanes
before, because it changes how every session starts.

The settings file is backed up once (settings.json.lanes-before-remote-control) before the first change, and only
the two values this tool owns are touched. LANES_CLAUDE_SETTINGS points the tests at another file.
"""
import json
import os
import shutil
import subprocess
import sys

HOME = os.path.expanduser("~")
HERE = os.path.dirname(os.path.abspath(__file__))
KEY = "remote_control"
SETTING = "remoteControlAtStartup"
PREFIX_ENV = "CLAUDE_REMOTE_CONTROL_SESSION_NAME_PREFIX"
BACKUP_SUFFIX = ".lanes-before-remote-control"
NAME_TIMEOUT_S = 20


def settings_file():
    return os.environ.get("LANES_CLAUDE_SETTINGS") or os.path.join(HOME, ".claude", "settings.json")


def features(*args):
    return subprocess.run([sys.executable, os.path.join(HERE, "features.py"), *args], capture_output=True, text=True)


def pc_name():
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, "machine-name.py")], capture_output=True, text=True,
                           timeout=NAME_TIMEOUT_S)
        name = "".join(ch for ch in r.stdout.strip() if ch.isalnum() or ch in "._-")
        return name or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def load():
    try:
        with open(settings_file(), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save(d):
    p = settings_file()
    if os.path.exists(p) and not os.path.exists(p + BACKUP_SUFFIX):
        shutil.copy2(p, p + BACKUP_SUFFIX)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".lanes-tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, p)


def set_settings(on):
    try:
        d = load()
    except ValueError:
        print(f"Claude Code's settings file is not valid JSON, so it was left alone: {settings_file()}")
        return False
    if on:
        d[SETTING] = True
        name = pc_name()
        if name:
            d.setdefault("env", {})[PREFIX_ENV] = name
    else:
        d.pop(SETTING, None)
        env = d.get("env")
        if isinstance(env, dict):
            env.pop(PREFIX_ENV, None)
    save(d)
    return True


def state():
    try:
        d = load()
    except ValueError:
        return None, None
    return d.get(SETTING) is True, (d.get("env") or {}).get(PREFIX_ENV)


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "status"
    if cmd in ("on", "off"):
        features(cmd, KEY)
        if not set_settings(cmd == "on"):
            return 1
        if cmd == "on":
            print("Remote Control: on for every new session on this PC, from the next one. "
                  "Sessions are named after this PC's Lanes name.")
        else:
            print("Remote Control: off at session start. Type /remote-control (or /rc) in a session to turn it on there.")
        return 0
    if cmd == "apply":
        want = features("is-on", KEY).returncode == 0
        on, _ = state()
        if on == want:
            print(f"Remote Control already {'on' if want else 'off'} at session start")
            return 0
        return 0 if set_settings(want) else 1
    if cmd == "status":
        on, prefix = state()
        if on is None:
            print(f"unknown: Claude Code's settings file is not valid JSON ({settings_file()})")
            return 1
        print(("on" if on else "off") + (f" (sessions named {prefix}-...)" if on and prefix else ""))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
