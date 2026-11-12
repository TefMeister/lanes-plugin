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

BARE = re.compile(r"(?<![\w./\\-])shutdown(?:\.exe)?\s+(?:[/-](?:s|r|p|g|sg|h|hybrid)\b)"
                  r"|\b(?:stop|restart)-computer\b|\bsystemctl\s+(?:poweroff|reboot|halt)\b", re.I)


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8-sig", errors="replace") or "{}")
    except Exception:  # noqa: BLE001
        return
    if data.get("tool_name") not in ("Bash", "PowerShell"):
        return
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if not BARE.search(cmd):
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
        "has finished and saved, and waits for them if needed:\n"
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
