"""skill-lane-guard.py -- the same two lane checks a typed /pd, /lm or /ms gets, when Claude starts the skill itself.

Wired as PreToolUse on the Skill tool (hooks/hooks.json). Found in the two-PC test, 2026-11-02: the prompt guards
(pd-guard.py, lane-claim-guard.py) only read what the person TYPES. When the prompt is not a slash command ("do a pd",
or a path the shell mangled) Claude opens the skill with the Skill tool, and neither guard ran: a second /pd on one PC,
or an /lm on a job another session holds, went ahead.

So when the Skill tool is about to start pd, lm or ms (with or without "lanes:"), this hook builds the prompt the
person would have typed ("/pd <args>") and asks both guards, exactly as at the prompt, with this session's id: the
/pd lock (pd only) and the live claim on the board. A refusal from either is passed on (exit 2, its reason). A pass
from pd-guard takes the lock for this session, as a typed /pd does. Every other skill passes untouched.

Never fails closed on its own errors: bad input, a missing guard or any exception -> exit 0, silent.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LANE_SKILLS = ("pd", "lm", "ms")
GUARD_TIMEOUT_S = 15


def ask(guard, payload):
    """(exit code, stderr text) from one prompt guard run on a made-up UserPromptSubmit."""
    r = subprocess.run([sys.executable, os.path.join(HERE, guard)], input=json.dumps(payload), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=GUARD_TIMEOUT_S)
    return r.returncode, (r.stderr or "").strip()


def main():
    try:
        # bytes, decoded utf-8-sig: input piped from PowerShell starts with a BOM, which made json fail -> let through
        data = json.loads(sys.stdin.buffer.read().decode("utf-8-sig", errors="replace") or "{}")
    except Exception:
        return 0
    if data.get("tool_name") != "Skill":
        return 0
    tin = data.get("tool_input") or {}
    name = str(tin.get("skill") or "").strip().lstrip("/")
    if name.startswith("lanes:"):
        name = name[len("lanes:"):]
    if name not in LANE_SKILLS:
        return 0
    args = str(tin.get("args") or "").strip()
    prompt = "/" + name + (" " + args if args else "")
    payload = {"hook_event_name": "UserPromptSubmit", "prompt": prompt, "session_id": data.get("session_id", ""),
               "cwd": data.get("cwd", "")}
    guards = (["pd-guard.py"] if name == "pd" else []) + ["lane-claim-guard.py"]
    for guard in guards:
        if not os.path.isfile(os.path.join(HERE, guard)):
            continue
        rc, why = ask(guard, payload)
        if rc == 2:
            sys.stderr.write("Lanes: starting the %s skill counts as typing %s, and that is refused:\n%s\n"
                             % (name, prompt, why))
            return 2
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception:
        code = 0
    sys.exit(code)
