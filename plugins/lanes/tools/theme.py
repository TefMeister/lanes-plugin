#!/usr/bin/env python3
"""theme.py - the look the plugin ships with: an old green monitor, a faint starburst behind the
text and a light that slowly runs down the screen (0.41.0, 2026-10-01, user-directed).

    python theme.py apply [--force] [--no-font]   put the look on the Windows Terminal profile Claude
                                                  Code is running in (or add a "Green Monitor Claude"
                                                  profile when not run from Windows Terminal)
    python theme.py restore                       put back exactly what was there before
    python theme.py status                        what was done, and where the backup is

Exit 0 = done or nothing to do, 1 = could not (the reason is printed), 2 = not applicable here.

WHY
  The plugin's author wanted everyone who installs it to get the same screen they work in: the
  green-monitor-starburst style from the terminal-themes repo. The first session after the install
  applies it by itself (hooks/theme-apply) and says so in one line. Everything it touches is written
  down so `restore` can undo it, and the terminal's settings file is backed up first.

WHAT IT CHANGES
  1. Copies the style (shader, picture, font, icon, Claude theme) to <state dir>/theme/, a folder
     that does not move when the plugin updates (the plugin's own folder is versioned and does).
  2. Installs the Share Tech Mono font for this user only (no administrator rights): the file goes
     to the user's Windows fonts folder and one registry value under HKCU points at it.
  3. Backs up Windows Terminal's settings.json next to itself (settings.json.lanes-backup), then on
     the profile Claude runs in sets the colour scheme, font, cursor, padding, icon and the two
     pixel-shader paths. Every previous value is kept in the state file.
  4. Writes the RobCo theme for Claude Code (its own messages on a hidden marker colour the shader
     turns yellow-green) and selects it in Claude Code's settings.json. Takes effect after restart.

WHAT IT NEVER DOES
  Replace a look someone already chose: a profile that already has a pixel shader is left alone
  unless --force is given. Touch any profile but the one it was started from (or the one it adds).
  Run on a PC without Windows Terminal: it says so once and stops.

Tests set LANES_STATE_DIR, LANES_WT_SETTINGS (the settings file), LANES_CLAUDE_DIR (Claude Code's
folder) and --no-font so nothing real is touched.
"""
import json
import os
import re
import shutil
import sys
import uuid
from datetime import datetime

HOME = os.path.expanduser("~")
LOCALAPPDATA = os.environ.get("LOCALAPPDATA", os.path.join(HOME, "AppData", "Local"))
STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(HOME, ".claude", "lanes")
STATE_FILE = os.path.join(STATE_DIR, "theme-state.json")
CLAUDE_DIR = os.environ.get("LANES_CLAUDE_DIR") or os.path.join(HOME, ".claude")
STYLE = "green-monitor-starburst"
STYLE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "theme", STYLE)
PROFILE_NAME = "Green Monitor Claude"
SCHEME_NAME = "RobCo"
FONT_FACE = "Share Tech Mono"
FONT_FILE = "ShareTechMono-Regular.ttf"
FONT_REG_NAME = "Share Tech Mono (TrueType)"
FONT_SIZE = 14
CLAUDE_THEME = "robco"
BACKUP_SUFFIX = ".lanes-backup"
# where Windows Terminal keeps its settings: the Store build, the Preview build, the unpackaged build
WT_SETTINGS_CANDIDATES = (
    os.path.join(LOCALAPPDATA, "Packages", "Microsoft.WindowsTerminal_8wekyb3d8bbwe", "LocalState", "settings.json"),
    os.path.join(LOCALAPPDATA, "Packages", "Microsoft.WindowsTerminalPreview_8wekyb3d8bbwe", "LocalState", "settings.json"),
    os.path.join(LOCALAPPDATA, "Microsoft", "Windows Terminal", "settings.json"),
)
PROFILE_KEYS = ("colorScheme", "font", "cursorShape", "padding", "icon",
                "experimental.pixelShaderPath", "experimental.pixelShaderImagePath")
SHADER_KEY = "experimental.pixelShaderPath"
IMAGE_KEY = "experimental.pixelShaderImagePath"


def start_folder():
    """Where a NEW profile opens. Without this Windows Terminal starts Claude in system32, which is
    no use to anyone (0.41.1). The Desktop, if there is one (asked for 2026-10-01); the home folder
    otherwise."""
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    return desktop if os.path.isdir(desktop) else os.path.expanduser("~")


def say(text):
    print("THEME: " + text)


def fwd(path):
    """Windows Terminal wants forward slashes in its paths."""
    return os.path.abspath(path).replace("\\", "/")


def wt_settings_path():
    p = os.environ.get("LANES_WT_SETTINGS")
    if p:
        return p if os.path.isfile(p) else None
    for c in WT_SETTINGS_CANDIDATES:
        if os.path.isfile(c):
            return c
    return None


def load_jsonc(path):
    """Windows Terminal's file may carry // comment lines and trailing commas."""
    with open(path, encoding="utf-8-sig") as f:
        text = f.read()
    text = re.sub(r"^\s*//.*$", "", text, flags=re.M)
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return json.loads(text)


def save_json(path, data, indent=4):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)
        f.write("\n")


def read_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_state(state):
    os.makedirs(STATE_DIR, exist_ok=True)
    save_json(STATE_FILE, state, indent=2)


def copy_style():
    """The style's files, at a path that survives plugin updates."""
    dest = os.path.join(STATE_DIR, "theme", STYLE)
    os.makedirs(dest, exist_ok=True)
    for name in os.listdir(STYLE_DIR):
        src = os.path.join(STYLE_DIR, name)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(dest, name)
        if not os.path.isfile(dst) or os.path.getsize(dst) != os.path.getsize(src):
            shutil.copyfile(src, dst)
    return dest


def install_font(style_home):
    """Per-user font install on Windows: a copy in the user's fonts folder and one HKCU value.
    Returns what happened, in words."""
    if os.name != "nt":
        return "skipped (not Windows)"
    try:
        import winreg
    except ImportError:
        return "skipped (no registry access)"
    key_path = r"Software\Microsoft\Windows NT\CurrentVersion\Fonts"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as k:
            winreg.QueryValueEx(k, FONT_REG_NAME)
            return "already installed"
    except OSError:
        pass
    fonts_dir = os.path.join(LOCALAPPDATA, "Microsoft", "Windows", "Fonts")
    try:
        os.makedirs(fonts_dir, exist_ok=True)
        target = os.path.join(fonts_dir, FONT_FILE)
        shutil.copyfile(os.path.join(style_home, FONT_FILE), target)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as k:
            winreg.SetValueEx(k, FONT_REG_NAME, 0, winreg.REG_SZ, target)
        return "installed for this user"
    except OSError as e:
        return "could not be installed (%s)" % e


def find_profile(data, guid):
    for p in data.get("profiles", {}).get("list", []):
        if guid and p.get("guid", "").lower() == guid.lower():
            return p
    return None


def apply(force=False, with_font=True):
    state = read_state()
    if state and not force:
        say("nothing to do - " + ("the look is already on" if state.get("applied") else state.get("reason", "it was looked at before")))
        return 0
    path = wt_settings_path()
    if not path:
        write_state({"applied": False, "reason": "no Windows Terminal on this PC", "when": now()})
        say("the plugin's look needs Windows Terminal (the shader and the rolling light run there). Not found on this PC, so nothing was changed.")
        return 2
    try:
        data = load_jsonc(path)
        profiles = data.setdefault("profiles", {})
        plist = profiles.setdefault("list", []) if isinstance(profiles, dict) else None
        if plist is None:
            raise ValueError("profiles is not an object")
    except (OSError, ValueError) as e:
        say("could not read the terminal's settings file (%s); nothing was changed." % e)
        return 1

    guid = os.environ.get("WT_PROFILE_ID", "")
    profile = find_profile(data, guid)
    created = False
    if profile is None:
        profile = next((p for p in plist if p.get("name") == PROFILE_NAME), None)
    if profile is None:
        profile = {"name": PROFILE_NAME, "guid": "{%s}" % uuid.uuid4(), "commandline": "claude",
                   "startingDirectory": fwd(start_folder())}
        plist.append(profile)
        created = True
    if profile.get(SHADER_KEY) and not force and not created:
        write_state({"applied": False, "reason": "this profile already had a look of its own, which was kept",
                     "when": now(), "profile_guid": profile.get("guid")})
        say("this terminal profile already has a look of its own, so it was kept. `python theme.py apply --force` replaces it.")
        return 0

    style_home = copy_style()
    font = install_font(style_home) if with_font else "skipped"
    backup = path + BACKUP_SUFFIX
    if not os.path.isfile(backup):
        shutil.copyfile(path, backup)
    previous = {k: profile.get(k) for k in PROFILE_KEYS}
    profile["colorScheme"] = SCHEME_NAME
    profile["font"] = {"face": FONT_FACE, "size": FONT_SIZE}
    profile["cursorShape"] = "filledBox"
    profile["padding"] = "16"
    profile["icon"] = fwd(os.path.join(style_home, "matrix-claude.png"))
    profile[SHADER_KEY] = fwd(os.path.join(style_home, "starburst.hlsl"))
    profile[IMAGE_KEY] = fwd(os.path.join(style_home, "starburst.png"))
    schemes = data.setdefault("schemes", [])
    scheme_added = False
    if not any(s.get("name") == SCHEME_NAME for s in schemes):
        with open(os.path.join(style_home, "profile-snippet.json"), encoding="utf-8") as f:
            schemes.append(json.load(f)["scheme"])
        scheme_added = True
    try:
        save_json(path, data)
    except OSError as e:
        say("could not write the terminal's settings file (%s); nothing was changed." % e)
        return 1

    claude_prev, claude_note = set_claude_theme(style_home)
    write_state({"applied": True, "when": now(), "settings": path, "backup": backup,
                 "profile_guid": profile.get("guid"), "profile_created": created, "scheme_added": scheme_added,
                 "previous": previous, "claude_theme_previous": claude_prev, "font": font, "style_home": style_home})
    if created:
        say("the plugin comes with one look, and it was added to Windows Terminal as a tab type called \"%s\" (this session is not running in Windows Terminal, so no open tab was changed). To see it: open Windows Terminal, click the small down arrow next to the + on the tab bar, and pick it. It opens on the Desktop." % PROFILE_NAME)
    else:
        say("this terminal profile now has the plugin's look: green monitor, starburst, rolling light. Font: %s." % font)
    say(claude_note)
    say("backup of the terminal's settings: %s. `python theme.py restore` puts everything back." % os.path.basename(backup))
    return 0


def set_claude_theme(style_home):
    """Claude Code's own colours: the RobCo theme and its selection in settings.json."""
    themes = os.path.join(CLAUDE_DIR, "themes")
    try:
        os.makedirs(themes, exist_ok=True)
        dst = os.path.join(themes, CLAUDE_THEME + ".json")
        if not os.path.isfile(dst):
            shutil.copyfile(os.path.join(style_home, "claude-theme-robco.json"), dst)
    except OSError as e:
        return None, "Claude Code's own theme could not be written (%s)." % e
    settings = os.path.join(CLAUDE_DIR, "settings.json")
    data = {}
    if os.path.isfile(settings):
        try:
            with open(settings, encoding="utf-8-sig") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return None, "Claude Code's settings.json could not be read, so its theme was left alone; pick RobCo with /theme."
    prev = data.get("theme")
    want = "custom:" + CLAUDE_THEME
    if prev == want:
        return prev, "Claude Code already uses the RobCo theme."
    data["theme"] = want
    try:
        save_json(settings, data, indent=2)
    except OSError as e:
        return None, "Claude Code's settings.json could not be written (%s); pick RobCo with /theme." % e
    return prev, "Claude Code's own colours switch to RobCo when it is next restarted."


def restore():
    state = read_state()
    if not state:
        say("nothing to restore - the look was never applied on this PC.")
        return 0
    if not state.get("applied"):
        remove_state()
        say("nothing to restore - nothing had been changed.")
        return 0
    path = state.get("settings", "")
    if not os.path.isfile(path):
        say("the terminal's settings file is gone (%s); the backup is %s." % (os.path.basename(path), state.get("backup")))
        remove_state()
        return 1
    try:
        data = load_jsonc(path)
    except (OSError, ValueError) as e:
        say("could not read the terminal's settings file (%s). Backup: %s" % (e, state.get("backup")))
        return 1
    plist = data.get("profiles", {}).get("list", [])
    profile = find_profile(data, state.get("profile_guid", ""))
    if profile is not None:
        if state.get("profile_created"):
            plist.remove(profile)
        else:
            for k, v in state.get("previous", {}).items():
                if v is None:
                    profile.pop(k, None)
                else:
                    profile[k] = v
    if state.get("scheme_added"):
        data["schemes"] = [s for s in data.get("schemes", []) if s.get("name") != SCHEME_NAME]
    try:
        save_json(path, data)
    except OSError as e:
        say("could not write the terminal's settings file (%s)." % e)
        return 1
    settings = os.path.join(CLAUDE_DIR, "settings.json")
    try:
        with open(settings, encoding="utf-8-sig") as f:
            cdata = json.load(f)
        prev = state.get("claude_theme_previous")
        if prev is None:
            cdata.pop("theme", None)
        else:
            cdata["theme"] = prev
        save_json(settings, cdata, indent=2)
    except (OSError, ValueError):
        pass
    remove_state()
    say("the terminal profile and Claude Code's theme are back as they were. The font stays installed (it is harmless); the backup %s stays too." % os.path.basename(state.get("backup", "")))
    return 0


def remove_state():
    try:
        os.remove(STATE_FILE)
    except OSError:
        pass


def status():
    state = read_state()
    if not state:
        say("not applied on this PC (the first session after installing does it; `python theme.py apply` does it now).")
        return 0
    if state.get("applied"):
        say("on since %s; backup %s; `python theme.py restore` puts it back." % (state.get("when"), state.get("backup")))
    else:
        say("not applied: %s (%s)." % (state.get("reason"), state.get("when")))
    return 0


def now():
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %z")


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    cmd = argv[0] if argv else "status"
    if cmd == "apply":
        return apply(force="--force" in argv, with_font="--no-font" not in argv)
    if cmd == "restore":
        return restore()
    if cmd == "status":
        return status()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
