"""uninstall.py - take Lanes off this PC in one go (0.61.0), leaving every piece of the person's own work alone.

    python uninstall.py            (= plan) list what Lanes put on this PC, and what would be taken away
    python uninstall.py do         take it all away (the session asks the person first: /lanes:uninstall)
    python uninstall.py do --keep-settings    the same, but keep lanes.conf (name, PC name, folders) for a reinstall
    python uninstall.py do --keep-plugin      everything except removing the plugin from Claude Code

WHAT IT TAKES AWAY, in this order (each one only if it is there):
  1. BeG0nE's background rider is stopped (BeG0nE itself, a separate project, stays where it is)
  2. the automatic OBS recorder is taken out of Windows' Startup folder and stopped (obs-autorec.py uninstall)
  3. the "Lanes" Desktop shortcut (shortcut.py remove)
  4. the terminal look: the terminal profile and Claude Code's theme go back as they were (theme.py restore)
  5. Lanes' own state folder (~/.claude/lanes: theme files, setup answers, update checks) and the reader log
  6. the Inspector's session folder, when it is the default one (~/.claude/lanes-inspector)
  7. lanes.conf, renamed to lanes.conf.uninstalled-<date> rather than deleted (unless --keep-settings)
  8. the plugin itself, LAST: `claude plugin uninstall lanes@lanes-plugin`, then `claude plugin marketplace remove
     lanes-plugin`. Last on purpose: until the plugin is gone its session-start hooks would put the look back.
     The session that runs this keeps the plugin loaded until Claude Code is restarted.

WHAT IT NEVER TOUCHES: any repo, board, note, build archive, recording or transfer folder; game folders; the tools
setup installed (Git, Python, Blender ... they are listed, with how to remove them, and left in place); the
terminal font (harmless, and other things may use it: Windows Settings -> Fonts removes it).

Tests set LANES_STATE_DIR, LANES_CONFIG, LANES_INSPECTOR_HOME and LANES_UNINSTALL_DRY_TOOLS=1 (no other tool, and no
`claude` command, is run).
"""
import datetime
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(HOME, ".claude", "lanes")
CONF = os.environ.get("LANES_CONFIG") or os.path.join(HOME, ".claude", "lanes.conf")
DEFAULT_INSPECTOR = os.environ.get("LANES_INSPECTOR_HOME") or os.path.join(HOME, ".claude", "lanes-inspector")
READER_LOG = os.path.join(os.path.dirname(CONF), "lanes-reader-refusals.log")
STARTUP_LNK = os.path.join(os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"),
                           "OBS auto-record games.lnk")
RIDER = os.path.join("camera-jitter", "ride-along", "ride.py")
DRY_TOOLS = os.environ.get("LANES_UNINSTALL_DRY_TOOLS") == "1"
TOOL_TIMEOUT_S = 60
PLUGIN_ID = "lanes@lanes-plugin"
MARKETPLACE = "lanes-plugin"


def say(text):
    print(text, flush=True)


def conf_get(key):
    try:
        with open(CONF, encoding="utf-8", errors="replace") as f:
            for line in f:
                s = line.strip()
                if s.startswith("#") or "=" not in s:
                    continue
                k, v = s.split("=", 1)
                if k.strip() == key:
                    return v.split(" #", 1)[0].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def run_tool(args):
    """Run one of Lanes' own tools (or BeG0nE's rider); return (ok, last line)."""
    if DRY_TOOLS:
        return True, "(test: not run) " + " ".join(os.path.basename(a) for a in args)
    try:
        r = subprocess.run([sys.executable] + args, capture_output=True, text=True, timeout=TOOL_TIMEOUT_S)
        out = (r.stdout + r.stderr).strip().splitlines()
        return r.returncode == 0, out[-1] if out else ""
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)


def run_claude(args):
    """`claude plugin ...`; return (ok, last line)."""
    if DRY_TOOLS:
        return True, "(test: not run) claude " + " ".join(args)
    exe = shutil.which("claude") or shutil.which("claude.cmd") or shutil.which("claude.exe")
    if not exe:
        return False, "Claude Code's command line was not found; type /plugin uninstall %s instead" % PLUGIN_ID
    try:
        r = subprocess.run([exe] + args, capture_output=True, text=True, timeout=TOOL_TIMEOUT_S)
        out = (r.stdout + r.stderr).strip().splitlines()
        return r.returncode == 0, out[-1] if out else ""
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)


def items():
    """What Lanes put on this PC: (key, present, what it is, what removing it does)."""
    begone = conf_get("begone")
    shortcut = (read_json(os.path.join(STATE_DIR, "shortcut-state.json")) or {}).get("path", "")
    theme = read_json(os.path.join(STATE_DIR, "theme-state.json")) or {}
    insp = conf_get("inspector_home")
    return [
        ("rider", bool(begone) and os.path.isfile(os.path.join(begone, RIDER)),
         "BeG0nE's background rider (started by Lanes each session)", "stopped; BeG0nE itself stays"),
        ("autorec", os.path.isfile(STARTUP_LNK), "the automatic OBS recorder in Windows' Startup folder",
         "taken out of Startup and stopped"),
        ("shortcut", bool(shortcut) and os.path.isfile(shortcut), "the 'Lanes' Desktop shortcut", "deleted"),
        ("theme", bool(theme.get("applied")), "the green-monitor terminal look",
         "the terminal and Claude Code's theme go back to how they were"),
        ("state", os.path.isdir(STATE_DIR), "Lanes' own state folder (%s)" % STATE_DIR, "deleted"),
        ("readerlog", os.path.isfile(READER_LOG), "the reader guard's log", "deleted"),
        ("inspector", os.path.isdir(DEFAULT_INSPECTOR) and (not insp or os.path.normcase(os.path.abspath(insp))
                                                         == os.path.normcase(os.path.abspath(DEFAULT_INSPECTOR))),
         "the Inspector's session folder (%s)" % DEFAULT_INSPECTOR, "deleted"),
        ("conf", os.path.isfile(CONF), "the settings file (%s)" % CONF,
         "renamed to lanes.conf.uninstalled-<date>, so nothing reads it (kept with --keep-settings)"),
    ]


def setup_tools():
    choices = (read_json(os.path.join(STATE_DIR, "setup-state.json")) or {}).get("choices", {})
    return sorted(t for t, how in choices.items() if how == "installed-by-claude")


def plan():
    say("LANES UNINSTALL - what Lanes put on this PC:")
    for key, present, what, does in items():
        say("  %s  %s%s" % ("yes" if present else " - ", what, (" -> " + does) if present else " (not here)"))
    custom = conf_get("inspector_home")
    if custom and os.path.normcase(os.path.abspath(custom)) != os.path.normcase(os.path.abspath(DEFAULT_INSPECTOR)):
        say("  kept  the Inspector folder you chose (%s): it is yours; delete it by hand if you want" % custom)
    tools = setup_tools()
    if tools:
        say("  kept  tools setup installed for you: %s. Remove any of them in Windows Settings -> Apps (or "
            "`winget uninstall <name>`)." % ", ".join(tools))
    say("  kept  every repo, board, note, build, recording and game folder, and the terminal font.")
    say("  last  the plugin itself is removed from Claude Code (and its source list), after everything above.")
    return 0


def do(keep_settings, keep_plugin):
    present = {k: p for k, p, _, _ in items()}
    problems = 0

    def step(label, ok, detail):
        nonlocal problems
        if not ok:
            problems += 1
        say("  %s  %s%s" % ("done" if ok else "FAILED", label, (": " + detail) if detail else ""))

    say("LANES UNINSTALL:")
    if present["rider"]:
        step("BeG0nE rider stopped", *run_tool([os.path.join(conf_get("begone"), RIDER), "stop"]))
    if present["autorec"]:
        step("OBS auto-recorder out of Startup", *run_tool([os.path.join(HERE, "obs-autorec.py"), "uninstall"]))
    if present["shortcut"]:
        step("Desktop shortcut removed", *run_tool([os.path.join(HERE, "shortcut.py"), "remove"]))
    if present["theme"]:
        step("terminal look put back", *run_tool([os.path.join(HERE, "theme.py"), "restore"]))
    if present["state"]:
        try:
            shutil.rmtree(STATE_DIR)
            step("state folder deleted", True, STATE_DIR)
        except OSError as e:
            step("state folder deleted", False, str(e))
    if present["readerlog"]:
        try:
            os.remove(READER_LOG)
            step("reader log deleted", True, "")
        except OSError as e:
            step("reader log deleted", False, str(e))
    if present["inspector"]:
        try:
            shutil.rmtree(DEFAULT_INSPECTOR)
            step("Inspector session folder deleted", True, DEFAULT_INSPECTOR)
        except OSError as e:
            step("Inspector session folder deleted", False, str(e))
    if present["conf"] and not keep_settings:
        dest = CONF + ".uninstalled-" + datetime.date.today().isoformat()
        try:
            os.replace(CONF, dest)
            step("settings put aside", True, dest)
        except OSError as e:
            step("settings put aside", False, str(e))
    elif present["conf"]:
        say("  kept  lanes.conf (--keep-settings)")
    if keep_plugin:
        say("  kept  the plugin in Claude Code (--keep-plugin); its next session start puts the look back.")
    else:
        step("plugin removed from Claude Code", *run_claude(["plugin", "uninstall", PLUGIN_ID]))
        step("plugin source removed", *run_claude(["plugin", "marketplace", "remove", MARKETPLACE]))
        say("Restart Claude Code to finish: this window still has Lanes loaded until then.")
    say("Nothing of your own work was touched.")
    return 1 if problems else 0


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    cmd = argv[0] if argv else "plan"
    if cmd == "plan":
        return plan()
    if cmd == "do":
        return do("--keep-settings" in argv, "--keep-plugin" in argv)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
