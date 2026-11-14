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
POWER_FLAG = re.compile(r"(?:^|(?<=[\s\"']))[/-](?:s|r|p|g|sg|h|hybrid|fw)(?=[\s\"']|$)", re.I)
OTHER = re.compile(r"\b(?:stop|restart)-computer\b|\bsystemctl\s+(?:poweroff|reboot|halt)\b"
                   r"|\bwin32shutdown(?:tracker)?\b|\bInitiateSystemShutdown(?:Ex)?\b|\bExitWindowsEx\b", re.I)


def is_bare(cmd):
    if OTHER.search(cmd):
        return True
    return any(POWER_FLAG.search(m.group(1)) for m in SHUTDOWN.finditer(cmd))


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8-sig", errors="replace") or "{}")
    except Exception:  # noqa: BLE001
        return
    if data.get("tool_name") not in ("Bash", "PowerShell"):
        return
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if not is_bare(cmd):
        return
    try:
        tools = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
        sys.path.insert(0, tools)
        import features
        if not features.is_on("shutdown_guard"):
            return
    except Exception:  # noqa: BLE001
        return
    sys.stderr.write(
        "Lanes shutdown guard: a bare shutdown or restart is not used here (a PC was switched off on 2026-11-12 while "
        "another session had not saved). Use the guarded one, which switches off only once every session on this PC "
        "has finished and saved, and waits for them if needed. Run this session's close-out first (its end steps), "
        "then:\n"
        "  python \"${CLAUDE_PLUGIN_ROOT}/tools/switch_off.py\" now --wait\n"
        "(`check` says what still stops it; `--restart` restarts instead; `cancel` takes it back.) Never work around "
        "this; if the person wants the PC off regardless, they switch it off themselves.\n")
    sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        pass
    sys.exit(0)
