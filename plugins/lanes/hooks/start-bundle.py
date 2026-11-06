"""SessionStart hook: the small start-up checks, run ONE AFTER ANOTHER in one hook instead of side by side (0.104.0).

Run 6 (2026-11-06): about 30 start-up checks (24 of them Lanes') started at the same moment, and on the low-powered dev
PC even a one-line rule took 7-18 s to come back; 6 to 15 of them ran past their time limit and were cut off, so the
session started without them. The rules and reminders below are tiny, so running them in a row costs a few seconds,
and it takes nine programs out of the start-up crowd.

Each part is the same script it always was (still runnable on its own); this hook runs each with bash, gathers the
text it hands the session (its additionalContext, or plain text), and passes all of it on as one. A part that fails
or runs out of its own time is skipped and the rest still run. Never blocks a session: any error -> exit 0.
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# (script, its own arguments) in the order their text should appear
PARTS = [("name-rule", []), ("repo-rule", []), ("talk-rule", []), ("straight-talk", []), ("tools-rule", []),
         ("setup-nudge", []), ("gu-nudge", []), ("gd-shelve", ["nudge"]), ("shortcut-offer", [])]
PART_TIMEOUT_S = 15        # one part; the whole hook has 60 in hooks.json
TOTAL_BUDGET_S = 50        # stop starting new parts after this, so the hook itself is never cut off

# The SLOW group (0.105.0, 2026-11-06; audit proposal P3), run as `start-bundle.py slow` from its own hooks.json
# entry: the checks that read GitHub or the board and take several seconds. Under the start-up crowd they were cut
# off by their own limits (owed-brief 16 of 16 recent starts on the dev PC, privacy-rule 14, ideas-brief 8,
# update-nudge 5); alone they take 3-8 s each. After them, every `start_part = <command>` line in lanes.conf runs
# (with bash, the same hook input on stdin), so a PC's own start-up scripts join the queue instead of the crowd.
SLOW_PARTS = [("owed-brief", []), ("privacy-rule", []), ("ideas-brief", []), ("update-nudge", [])]
SLOW_PART_TIMEOUT_S = 25
SLOW_TOTAL_BUDGET_S = 105  # the slow entry has 120 in hooks.json


def conf_start_parts():
    """The raw commands of every `start_part = ...` line in lanes.conf (case and # kept: they are commands)."""
    path = os.environ.get("LANES_CONFIG") or os.path.expanduser("~/.claude/lanes.conf")
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                key, sep, val = line.partition("=")
                if sep and key.strip() == "start_part" and val.strip():
                    out.append(val.strip())
    except OSError:
        pass
    return out


def bash():
    for cand in (os.environ.get("BASH"), r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe",
                 "bash"):
        if cand and (cand == "bash" or os.path.isfile(cand)):
            return cand
    return "bash"


def text_of(out):
    out = (out or "").strip()
    if not out:
        return ""
    try:
        d = json.loads(out)
    except ValueError:
        return out
    if isinstance(d, dict):
        return ((d.get("hookSpecificOutput") or {}).get("additionalContext") or d.get("additionalContext")
                or d.get("systemMessage") or "").strip()
    return ""


def main():
    try:
        data = sys.stdin.buffer.read()
    except Exception:  # noqa: BLE001
        data = b""
    texts, began, sh = [], time.time(), bash()
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)   # no window for each part (Windows only)
    slow = sys.argv[1:2] == ["slow"]
    if slow:
        jobs = [[sh, os.path.join(HERE, s)] + a for s, a in SLOW_PARTS if os.path.isfile(os.path.join(HERE, s))]
        jobs += [[sh, "-c", c] for c in conf_start_parts()]
        part_s, budget_s = SLOW_PART_TIMEOUT_S, SLOW_TOTAL_BUDGET_S
    else:
        jobs = [[sh, os.path.join(HERE, s)] + a for s, a in PARTS if os.path.isfile(os.path.join(HERE, s))]
        part_s, budget_s = PART_TIMEOUT_S, TOTAL_BUDGET_S
    for cmd in jobs:
        if time.time() - began > budget_s:
            break
        try:
            r = subprocess.run(cmd, input=data, capture_output=True, timeout=part_s,
                               creationflags=flags)
            t = text_of(r.stdout.decode("utf-8", errors="replace"))
        except Exception:  # noqa: BLE001 - one part never stops the others
            t = ""
        if t:
            texts.append(t)
    if texts:
        sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                            "additionalContext": "\n".join(texts)}}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        sys.exit(0)
