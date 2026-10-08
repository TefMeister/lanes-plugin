"""shortcut.py - a desktop shortcut named "Lanes" that opens Claude Code in the plugin's look (0.53.0, 2026-10-09,
user-directed: "make the first install and update of Lanes now offer to create a shortcut on the user's desktop named
Lanes, with this exact way of printing things out, the fonts, the background as it is").

    python shortcut.py create [--folder <dir>] [--dry-run]   put Lanes.lnk on the Desktop: Windows Terminal, the profile
                                                             the plugin's look is on, Claude Code started in <folder>
                                                             (default: the folder this session runs in)
    python shortcut.py remove                                take the shortcut away again (only one this tool made)
    python shortcut.py decline                               remember that the person said no, so it is not offered again
    python shortcut.py status                                is there one, where, and which folder it opens

Exit 0 = done or nothing to do, 1 = could not (the reason is printed), 2 = not applicable here.

WHAT IT DOES
  The look (theme.py) lives on ONE Windows Terminal profile: the one Claude Code was running in when the plugin was
  installed, or the "Green Monitor Claude" profile the plugin added. A shortcut that opens THAT profile with `claude`
  as its command gives the same screen every time: the font, the colours, the banner behind the text, the rolling
  light, and Claude Code's own colours (its theme is selected in its settings, not per window). The shortcut is a
  normal Windows .lnk, made through Windows Script Host, pointing at wt.exe with
      -p "<profile guid>" -d "<folder>" claude
  and carrying the look's icon (lanes.ico, made from the look's tab icon). Nothing else on the PC is touched.

WHAT IT NEEDS
  Windows, Windows Terminal, and the look applied on this PC (theme-state.json says which profile). Without the look
  it says so and does nothing: there is no "exact way of printing things" to open yet.

Tests set LANES_STATE_DIR (where theme-state.json and shortcut-state.json live), LANES_DESKTOP (the folder that stands
in for the Desktop), LANES_WT_EXE (stands in for wt.exe) and --dry-run (print what would be made, make nothing).
"""
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime

HOME = os.path.expanduser("~")
LOCALAPPDATA = os.environ.get("LOCALAPPDATA", os.path.join(HOME, "AppData", "Local"))
STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(HOME, ".claude", "lanes")
THEME_STATE = os.path.join(STATE_DIR, "theme-state.json")
STATE_FILE = os.path.join(STATE_DIR, "shortcut-state.json")
STYLE = "green-monitor-lanes"
ICON_FILE = "lanes.ico"
STYLE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "theme", STYLE)
NAME = "Lanes"
WT_CANDIDATES = (
    os.path.join(LOCALAPPDATA, "Microsoft", "WindowsApps", "wt.exe"),
)


def say(text):
    print("SHORTCUT: " + text)


def now():
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %z")


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_state(state):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def desktop():
    env = os.environ.get("LANES_DESKTOP")
    if env:
        return env
    # Ask Windows: a Desktop moved into OneDrive is not ~/Desktop
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"],
                             capture_output=True, text=True, timeout=20).stdout.strip()
        if out:
            return out
    except (OSError, subprocess.SubprocessError):
        pass
    return os.path.join(HOME, "Desktop")


def find_wt():
    env = os.environ.get("LANES_WT_EXE")
    if env:
        return env
    for c in WT_CANDIDATES:
        if os.path.exists(c):
            return c
    try:
        out = subprocess.run(["where", "wt.exe"], capture_output=True, text=True, timeout=10).stdout.strip().splitlines()
        if out:
            return out[0]
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def ps_quote(s):
    return "'" + s.replace("'", "''") + "'"


def create(folder=None, dry_run=False):
    if os.name != "nt" and not dry_run:
        say("a desktop shortcut to Windows Terminal only makes sense on Windows; nothing was made.")
        write_state({"applicable": False, "reason": "not Windows", "when": now()})
        return 2
    theme = read_json(THEME_STATE)
    if not theme or not theme.get("applied") or not theme.get("profile_guid"):
        say("the plugin's look is not on this PC yet (theme-state.json), so there is no look to open; "
            "`python theme.py apply` first, then `python shortcut.py create`.")
        return 1
    guid = theme["profile_guid"]
    wt = find_wt() or ("wt.exe" if dry_run else None)
    if not wt:
        say("Windows Terminal (wt.exe) was not found, so no shortcut was made.")
        return 1
    folder = os.path.abspath(folder or os.getcwd())
    style_home = theme.get("style_home") or os.path.join(STATE_DIR, "theme", STYLE)
    icon = os.path.join(style_home, ICON_FILE)
    if not os.path.isfile(icon) and not dry_run:
        try:
            os.makedirs(style_home, exist_ok=True)
            shutil.copyfile(os.path.join(STYLE_DIR, ICON_FILE), icon)
        except OSError:
            icon = ""   # a shortcut without an icon still works
    link = os.path.join(desktop(), NAME + ".lnk")
    args = '-p "%s" -d "%s" claude' % (guid, folder)
    say("target %s" % wt)
    say("arguments %s" % args)
    say("icon %s" % (icon or "(none)"))
    say("shortcut %s" % link)
    if dry_run:
        say("dry run: nothing was made.")
        return 0
    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut(%s); " % ps_quote(link) +
        "$s.TargetPath = %s; " % ps_quote(wt) +
        "$s.Arguments = %s; " % ps_quote(args) +
        "$s.WorkingDirectory = %s; " % ps_quote(folder) +
        ("$s.IconLocation = %s; " % ps_quote(icon + ",0") if icon else "") +
        "$s.Description = %s; " % ps_quote("Lanes: Claude Code in the plugin's look") +
        "$s.Save()"
    )
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        say("could not run PowerShell to make the shortcut (%s)." % e)
        return 1
    if r.returncode != 0 or not os.path.isfile(link):
        say("the shortcut could not be made: %s" % (r.stderr.strip() or r.stdout.strip() or "no file appeared"))
        return 1
    write_state({"created": True, "path": link, "folder": folder, "profile_guid": guid, "target": wt, "when": now()})
    say("made: a shortcut named %s on the Desktop opens Claude Code in the plugin's look, in %s." % (NAME, folder))
    return 0


def remove():
    state = read_json(STATE_FILE) or {}
    link = state.get("path")
    if not link:
        say("no shortcut made by this tool is on record; nothing to remove.")
        return 0
    try:
        if os.path.isfile(link):
            os.remove(link)
    except OSError as e:
        say("could not remove %s (%s)." % (link, e))
        return 1
    try:
        os.remove(STATE_FILE)
    except OSError:
        pass
    say("removed %s." % link)
    return 0


def decline():
    write_state({"created": False, "declined": True, "when": now()})
    say("noted: no desktop shortcut; it will not be offered again (`python shortcut.py create` makes one any time).")
    return 0


def status():
    state = read_json(STATE_FILE)
    if not state:
        say("no shortcut yet; the first session after the look goes on offers one, or `python shortcut.py create`.")
        return 0
    if state.get("created"):
        there = os.path.isfile(state.get("path", ""))
        say("%s (%s) opens Claude Code in %s; made %s." % (state.get("path"), "present" if there else "MISSING - make it again",
                                                         state.get("folder"), state.get("when")))
    elif state.get("declined"):
        say("declined on %s; `python shortcut.py create` makes one any time." % state.get("when"))
    else:
        say("not applicable here: %s (%s)." % (state.get("reason"), state.get("when")))
    return 0


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    cmd = argv[0] if argv else "status"
    if cmd == "create":
        folder = None
        if "--folder" in argv:
            i = argv.index("--folder")
            folder = argv[i + 1] if i + 1 < len(argv) else None
        return create(folder=folder, dry_run="--dry-run" in argv)
    if cmd == "remove":
        return remove()
    if cmd == "decline":
        return decline()
    if cmd == "status":
        return status()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
