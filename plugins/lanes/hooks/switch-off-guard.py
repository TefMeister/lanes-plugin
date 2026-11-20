"""PreToolUse (Bash, PowerShell): a bare shutdown or restart typed by a session is refused and pointed at the shutdown
guard (0.112.0, 2026-11-12, extra `shutdown_guard`).

Why: on 2026-11-12 a session on the Developer PC switched it off with `shutdown` four minutes after its own job ended,
while another window had not run its end steps and a build was never pushed. tools/switch_off.py switches off only
when every session has finished and saved, and can wait for them. `shutdown /a` (stop a countdown) is let through.
Never fails closed: any error lets the command through.
"""
import json
import os
import re
import sys

# 0.113.7: the shutdown word anywhere a command starts (a full path, `Start-Process shutdown`, `cmd /c`), and a
# switch-off flag anywhere after it in the same command: `shutdown /t 60 /s` and `shutdown /f /s` were let through
# (only a FIRST flag of /s /r ... was looked at), and on 2026-11-14 02:26 a session switched the Developer PC off
# that way, its end steps never run.
SHUTDOWN = re.compile(r"(?:^|(?<=[\s\"'&|;(\\/]))shutdown(?:\.exe)?(?=[\s\"']|$)([^;&|\n]*)", re.I)
# 0.118.2: Git Bash turns a lone `/s` into a folder path, so sessions there type `shutdown //s //t 90`: the doubled
# slash got past every check (three switch-offs on the Developer PC, 2026-11-11, 11-19 01:19 and 22:27, all through
# the Bash tool, none through switch_off.py). Now one or two slashes or dashes, and flags written together (`/s/t`).
POWER_FLAG = re.compile(r"(?:^|(?<=[\s\"'/,(]))(?:/{1,2}|-{1,2})(?:s|r|p|g|sg|h|hybrid|fw)(?=[\s\"'/,)]|$)", re.I)
# 0.118.2: the switch-off program STARTED as a command (not a word in a search or a message) with a flag that cannot
# be read from the text (a variable, `%VAR%`, `@(...)`, `$(...)`): refused too, since the flag may be /s.
AT_COMMAND = re.compile(r"(?:^|[;&|(\n]|\bcmd(?:\.exe)?\s+/{1,2}c|\bStart-Process(?:\s+-FilePath)?|\biex|\bInvoke-Expression"
                        r"|\bexec|\bcall)\s*[\"']?(?:[\w:.$%{}\\/ -]*[\\/])?shutdown(?:\.exe)?(?=[\s\"']|$)([^;&|\n]*)",
                        re.I)
HIDDEN_FLAG = re.compile(r"(?:^|\s)[\"']?(?:\$|%\w|@\()")
OTHER = re.compile(r"\b(?:stop|restart)-computer\b|\bsystemctl\s+(?:poweroff|reboot|halt)\b"
                   r"|\bwin32shutdown(?:tracker)?\b|\bInitiateSystemShutdown(?:Ex)?\b|\bExitWindowsEx\b", re.I)
# 0.118.2: a script file the command runs (`powershell -File off.ps1`, `off.bat`, `python off.py`) is read too
SCRIPT = re.compile(r"""(?:"([^"\n]+\.(?:ps1|bat|cmd|py|pyw|vbs|sh|js))"|'([^'\n]+\.(?:ps1|bat|cmd|py|pyw|vbs|sh|js))'"""
                    r"""|([^\s"';&|<>()]+\.(?:ps1|bat|cmd|py|pyw|vbs|sh|js)))(?=[\s"';&|)]|$)""", re.I)
SCRIPT_MAX_BYTES = 1024 * 1024
SCRIPTS_LOOKED_AT = 10


def is_bare(cmd):
    if OTHER.search(cmd):
        return True
    if any(POWER_FLAG.search(m.group(1)) for m in SHUTDOWN.finditer(cmd)):
        return True
    return any(HIDDEN_FLAG.search(m.group(1)) for m in AT_COMMAND.finditer(cmd))


def ours(path):
    """Lanes' own files (the guarded switch-off itself, its tests) are never refused for naming a switch-off."""
    norm = os.path.realpath(path).replace("\\", "/").lower()
    return "/plugins/lanes/" in norm or os.path.basename(norm) == "switch_off.py"


def scripts_with_switch_off(cmd, cwd):
    out = []
    seen = 0
    for m in SCRIPT.finditer(cmd):
        name = next(g for g in m.groups() if g)
        path = os.path.expanduser(os.path.expandvars(name))
        if not os.path.isabs(path):
            path = os.path.join(cwd or os.getcwd(), path)
        seen += 1
        if seen > SCRIPTS_LOOKED_AT:
            break
        try:
            if not os.path.isfile(path) or ours(path) or os.path.getsize(path) > SCRIPT_MAX_BYTES:
                continue
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        if any(is_bare(line) for line in text.splitlines()):
            out.append(os.path.basename(path))
    return out


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8-sig", errors="replace") or "{}")
    except Exception:  # noqa: BLE001
        return
    if data.get("tool_name") not in ("Bash", "PowerShell"):
        return
    cmd = (data.get("tool_input") or {}).get("command") or ""
    bare = is_bare(cmd)
    scripts = [] if bare else scripts_with_switch_off(cmd, data.get("cwd") or "")
    if not bare and not scripts:
        return
    try:
        tools = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
        sys.path.insert(0, tools)
        import features
        if not features.is_on("shutdown_guard"):
            return
    except Exception:  # noqa: BLE001
        return
    what = ("a bare shutdown or restart" if bare else
            "a script that switches the PC off (%s)" % ", ".join(scripts))
    sys.stderr.write(
        "Lanes shutdown guard: %s is not used here, in any spelling (`//s`, `/s/t`, a flag in a variable, a script "
        "file): a PC was switched off on 2026-11-12, 11-14 and 11-19 while a session had not run its end steps. Use the "
        "guarded one, which runs this session's end steps, switches off only once every session on this PC has "
        "finished and saved, and waits for them if needed. Run this session's close-out first, then:\n"
        "  python \"${CLAUDE_PLUGIN_ROOT}/tools/switch_off.py\" now --wait\n"
        "(`check` says what still stops it; `--restart` restarts instead; `cancel` takes it back.) Never work around "
        "this; if the person wants the PC off regardless, they switch it off themselves.\n" % what)
    sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        pass
    sys.exit(0)
