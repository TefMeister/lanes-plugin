"""uninstall.py - take Lanes off this PC in one go (0.61.0), leaving every piece of the person's own work alone.

    python uninstall.py            (= plan) list what Lanes put on this PC, and what would be taken away
    python uninstall.py do         take it all away (the session asks the person first: /lanes:uninstall)
    python uninstall.py do --keep-settings    the same, but keep lanes.conf (name, PC name, folders) for a reinstall
    python uninstall.py do --keep-plugin      everything except removing the plugin from Claude Code

WHAT IT TAKES AWAY, in this order (each one only if it is there):
  1. BeG0nE's background rider is stopped (BeG0nE itself, a separate project, stays where it is)
  2. the old automatic OBS recorder's Startup shortcut, if an older Lanes left one (the recorder was retired in 0.105.0)
  3. the "Lanes" Desktop shortcut (shortcut.py remove)
  4. the terminal look: the terminal profile and Claude Code's theme go back as they were (theme.py restore)
  5. Lanes' own state folder (~/.claude/lanes: theme files, setup answers, update checks) and the reader log
  6. the Inspector's session folder, when it is the default one (~/.claude/lanes-inspector)
  7. lanes.conf, renamed to lanes.conf.uninstalled-<date> rather than deleted (unless --keep-settings)
  8. the plugin itself, LAST: `claude plugin uninstall lanes@lanes-plugin`, then `claude plugin marketplace remove
     lanes-plugin`. Last on purpose: until the plugin is gone its session-start hooks would put the look back.
     The session that runs this keeps the plugin loaded until Claude Code is restarted.

  0.120.0 (from the first uninstall test on a real PC): also the look left on terminal profiles by an older install
  (theme.py sweep), the doorman and its Startup shortcut, the quiet-install task, the sessions' saved state, the
  settings backups (put aside), and Claude Code's own cache and data copies of the plugin. The doorman's firewall rule
  needs an administrator window: the exact line is printed. The full conversation logs (lanes-transcripts) are the
  person's records: listed with their size and kept.

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
# 0.62.0: the rider ships in the plugin; its pid file is where the old BeG0nE ride.py kept one too.
RIDER = os.path.join(os.path.dirname(HERE), "begone", "rider.py")
RIDER_PID = os.path.join(os.environ.get("LOCALAPPDATA") or HOME, "BeG0nE", "ride.pid")
DRY_TOOLS = os.environ.get("LANES_UNINSTALL_DRY_TOOLS") == "1"
TOOL_TIMEOUT_S = 60
CLAUDE_HOME = os.path.dirname(CONF)                # ~/.claude, or the test's scratch folder
# 0.120.0 (the Workshop's uninstall test): what the first uninstall left behind
DOORMAN_LNK = os.path.join(os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"),
                           "Lanes doorman.lnk")
DOORMAN_RULE = "Lanes doorman - private link only"
QUIET_FOLDER = os.environ.get("LANES_QUIET_ROOT") or os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"),
                                                                   "LanesQuietInstall")
SESSION_FILES = ("lanes-sessions", "lanes-tandem.json")   # beside lanes.conf: each session's saved state
TRANSCRIPTS = os.path.join(CLAUDE_HOME, "lanes-transcripts")
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


KEEP_IN_STATE = ("never-publish.txt", "private-words.txt")   # the person's own lists: never deleted


def hooks_path_is_ours():
    """True when git's machine-wide hook setting points into Lanes' state folder (privacy-guard.py install)."""
    try:
        r = subprocess.run(["git", "config", "--global", "core.hooksPath"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    hp = r.stdout.strip().replace("\\", "/").lower()
    return bool(hp) and hp.startswith(STATE_DIR.replace("\\", "/").lower())


def doorman_rule():
    """the doorman's firewall rule is there (removing it needs an administrator window)"""
    if DRY_TOOLS:
        return os.environ.get("LANES_UNINSTALL_FAKE_RULE") == "1"
    try:
        r = subprocess.run(["netsh", "advfirewall", "firewall", "show", "rule", "name=" + DOORMAN_RULE],
                           capture_output=True, text=True, timeout=20)
        return r.returncode == 0 and DOORMAN_RULE in r.stdout
    except (OSError, subprocess.SubprocessError):
        return False


def plugin_leftovers():
    """Claude Code's own copies of the plugin it keeps after `plugin uninstall`: the download cache and data folders"""
    base = os.path.join(CLAUDE_HOME, "plugins")
    out = []
    cache = os.path.join(base, "cache", MARKETPLACE)
    if os.path.isdir(cache):
        out.append(cache)
    data = os.path.join(base, "data")
    if os.path.isdir(data):
        out += [os.path.join(data, n) for n in sorted(os.listdir(data)) if n.lower().startswith("lanes")]
    return out


def conf_backups():
    try:
        return sorted(os.path.join(CLAUDE_HOME, n) for n in os.listdir(CLAUDE_HOME)
                      if n.startswith("lanes.conf.bak"))
    except OSError:
        return []


def folder_mb(path):
    total = 0
    for dirpath, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return total // (1024 * 1024)


def look_left():
    if os.environ.get("LANES_UNINSTALL_FAKE_LOOK"):
        return os.environ["LANES_UNINSTALL_FAKE_LOOK"] == "1"
    try:
        sys.path.insert(0, HERE)
        import theme
        return bool(theme.leftovers()) or theme.claude_theme_left()
    except Exception:  # noqa: BLE001 - when the check cannot run, the state file still decides
        return False


def items():
    """What Lanes put on this PC: (key, present, what it is, what removing it does)."""
    shortcut = (read_json(os.path.join(STATE_DIR, "shortcut-state.json")) or {}).get("path", "")
    theme = read_json(os.path.join(STATE_DIR, "theme-state.json")) or {}
    insp = conf_get("inspector_home")
    return [
        ("rider", os.path.isfile(RIDER_PID),
         "the BeG0nE rider (started by Lanes each session)", "stopped and out of Startup; its reports stay"),
        ("autorec", os.path.isfile(STARTUP_LNK), "an older Lanes' automatic OBS recorder shortcut in Windows' Startup folder",
         "taken out of Startup"),
        ("shortcut", bool(shortcut) and os.path.isfile(shortcut), "the 'Lanes' Desktop shortcut", "deleted"),
        ("theme", bool(theme.get("applied")), "the green-monitor terminal look",
         "the terminal and Claude Code's theme go back to how they were"),
        ("look", look_left(), "Lanes' look files still used by a terminal profile, or Claude Code's RobCo colours "
         "(an older install, or a look made from Lanes' files)",
         "taken off those profiles (the profiles stay) and the files deleted; a backup of the terminal settings first"),
        ("doorman", os.path.isfile(DOORMAN_LNK), "the doorman (the Keeper's link program) in Windows' Startup folder",
         "stopped and taken out of Startup"),
        ("firewall", doorman_rule(), "the doorman's firewall rule",
         "listed for you: removing it needs an administrator window (the exact line is printed)"),
        ("quiet", os.path.isdir(QUIET_FOLDER), "the 'Lanes quiet install' Windows task and its folder",
         "taken off (Windows asks one Yes click)"),
        ("sessions", any(os.path.exists(os.path.join(CLAUDE_HOME, n)) for n in SESSION_FILES),
         "the sessions' saved state (%s)" % ", ".join(SESSION_FILES), "deleted"),
        ("confbaks", bool(conf_backups()), "%d backup(s) of the settings file (lanes.conf.bak...)" % len(conf_backups()),
         "put aside with the settings file, not deleted"),
        ("plugincache", bool(plugin_leftovers()), "Claude Code's own download and data copies of the plugin",
         "deleted after the plugin itself is removed"),
        ("privacy", hooks_path_is_ours(), "the privacy guard's machine-wide git hooks",
         "git's hook setting goes back to how it was"),
        ("state", os.path.isdir(STATE_DIR), "Lanes' own state folder (%s)" % STATE_DIR,
         "deleted, except your private word lists (%s), which stay for a reinstall" % ", ".join(KEEP_IN_STATE)),
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
    if os.path.isdir(TRANSCRIPTS):
        say("  kept  your full conversation logs (%s, %d MB): they are your records; delete the folder by hand if you "
            "do not want them" % (TRANSCRIPTS, folder_mb(TRANSCRIPTS)))
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
        step("BeG0nE rider stopped", *run_tool([RIDER, "uninstall"]))
    if present["autorec"]:
        # 0.105.0: obs-autorec.py is retired, so its Startup shortcut is removed here directly
        try:
            if not DRY_TOOLS:
                os.remove(STARTUP_LNK)
            step("old OBS auto-recorder shortcut out of Startup", True, "(test: not removed)" if DRY_TOOLS else "")
        except OSError as e:
            step("old OBS auto-recorder shortcut out of Startup", False, str(e))
    if present["shortcut"]:
        step("Desktop shortcut removed", *run_tool([os.path.join(HERE, "shortcut.py"), "remove"]))
    if present["theme"]:
        step("terminal look put back", *run_tool([os.path.join(HERE, "theme.py"), "restore"]))
    if present["look"]:
        step("Lanes look taken off the terminal profiles", *run_tool([os.path.join(HERE, "theme.py"), "sweep"]))
    if present["doorman"]:
        step("doorman stopped and out of Startup", *run_tool([os.path.join(HERE, "doorman.py"), "uninstall"]))
    if present["quiet"]:
        step("quiet-install task taken off", *run_tool([os.path.join(HERE, "quiet_install.py"), "uninstall"]))
    if present["sessions"]:
        try:
            for n in SESSION_FILES:
                p = os.path.join(CLAUDE_HOME, n)
                if os.path.isdir(p) and not os.path.islink(p):
                    shutil.rmtree(p)
                elif os.path.exists(p):
                    os.remove(p)
            step("sessions' saved state deleted", True, "")
        except OSError as e:
            step("sessions' saved state deleted", False, str(e))
    if present["privacy"]:
        step("privacy guard's git hooks switched off", *run_tool([os.path.join(HERE, "privacy-guard.py"), "uninstall"]))
    if present["state"]:
        # 0.99.0 (release audit): the person's own never-publish and private-word lists stay. Deleting them meant a
        # reinstall ran the privacy guard without them, and they are the person's words, not Lanes' state.
        try:
            for name in os.listdir(STATE_DIR):
                if name in KEEP_IN_STATE:
                    continue
                p = os.path.join(STATE_DIR, name)
                if os.path.isdir(p) and not os.path.islink(p):
                    shutil.rmtree(p)
                else:
                    os.remove(p)
            if not os.listdir(STATE_DIR):
                os.rmdir(STATE_DIR)
            step("state folder emptied", True, STATE_DIR + (" (kept: your private word lists)"
                                                            if os.path.isdir(STATE_DIR) else ""))
        except OSError as e:
            step("state folder emptied", False, str(e))
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
    if present["confbaks"] and not keep_settings:
        aside = os.path.join(CLAUDE_HOME, "lanes.conf-backups.uninstalled-" + datetime.date.today().isoformat())
        try:
            os.makedirs(aside, exist_ok=True)
            for b in conf_backups():
                os.replace(b, os.path.join(aside, os.path.basename(b)))
            step("settings backups put aside", True, aside)
        except OSError as e:
            step("settings backups put aside", False, str(e))
    elif present["conf"]:
        say("  kept  lanes.conf (--keep-settings)")
    if keep_plugin:
        say("  kept  the plugin in Claude Code (--keep-plugin); its next session start puts the look back.")
    else:
        step("plugin removed from Claude Code", *run_claude(["plugin", "uninstall", PLUGIN_ID]))
        step("plugin source removed", *run_claude(["plugin", "marketplace", "remove", MARKETPLACE]))
        if present["plugincache"]:
            try:
                for d in plugin_leftovers():
                    shutil.rmtree(d)
                step("Claude Code's copies of the plugin deleted", True, "")
            except OSError as e:
                step("Claude Code's copies of the plugin deleted", False, str(e))
        say("Restart Claude Code to finish: this window still has Lanes loaded until then.")
    if present["firewall"]:
        say("  FOR YOU  the doorman's firewall rule: in an administrator window type")
        say('           netsh advfirewall firewall delete rule name="%s"' % DOORMAN_RULE)
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
