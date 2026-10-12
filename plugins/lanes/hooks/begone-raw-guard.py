"""begone-raw-guard.py - keep a session from reading BeG0nE's raw numbers by accident (0.62.0).

Wired as PreToolUse on Read, Grep, Bash and PowerShell (see hooks/hooks.json).

WHY THIS EXISTS
  Asked for by the maintainer, 2026-10-12: "is there a way for you to make it impossible to read the raw numbers
  that would possibly fill the session by accident?" One filed jitter session's summary.json is 600 KB; the raw
  recordings are bigger. Read whole, one of them spends most of a session. Everything a session needs from them
  comes out of `tools/begone.py report` (a paragraph) and `tools/begone.py ask` (capped answers), so opening the raw
  files is refused, with the way round in the message.

WHAT IT REFUSES
  Read of a raw recording (any tool's log extension, from its tool.json) or of a summary.json inside a BeG0nE home
  or a tool's data folder; Grep pointed at one of those, or at a BeG0nE data/log folder without a glob limiting it
  to .md or .csv; Bash / PowerShell commands that name one of those AND use a reading command (cat, head, tail,
  type, Get-Content, grep, python -c, ...). Commands that run the BeG0nE tools themselves always pass.

  NOT AIRTIGHT, and says so: a script written on purpose to print the numbers gets through. The aim is to stop
  the accident, the way the reader guard stops one shape of write and no more.

  Unreadable input, any exception -> exit 0, silent. THIS GUARD MUST NEVER FAIL CLOSED.
"""
import json
import os
import re
import sys

HOOKS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HOOKS), "begone"))

READERS = re.compile(r"\b(cat|head|tail|less|more|type|gc|get-content|select-string|sls|findstr|grep|rg|egrep|sed|awk|"
                     r"jq|strings|od|xxd|hexdump|python[0-9.]*\s+-c|py\s+-c|open\()", re.I)
OUR_TOOLS = re.compile(r"(begone\.py|rider\.py|ride\.py|file_jitter\.py|jitter_log_check\.py|ghost_hand_check\.py|"
                       r"knowledge\.py|\bgit\b)", re.I)
MESSAGE = ("BeG0nE RAW-NUMBER LOCK: {what} holds raw recorded numbers; reading it can fill the session.\n"
           "Use instead:  python <plugin>/tools/begone.py report <tool> latest   (the short report)\n"
           "              python <plugin>/tools/begone.py ask <tool> latest <question>   (capped answers)\n"
           "Asked for by the maintainer so raw numbers are never read by accident. PROTOCOL section 20.\n")


def norm(p):
    return str(p or "").replace("\\", "/").lower()


def setup():
    import begone_common as bc
    exts, roots = set(), []
    for t in bc.tools():
        if t.get("log_ext"):
            exts.add(t["log_ext"].lower())
        roots.append(norm(bc.data_dir(t)) + "/")
        if bc.log_dir(t):
            roots.append(norm(bc.log_dir(t)) + "/")
    roots.append(norm(bc.LOCAL) + "/")
    return exts, roots


def raw_path(p, exts, roots):
    """Is this one path a raw file? A summary.json counts when it sits in a BeG0nE data folder (or any folder
    named for a tool's data, so another clone of the same home is covered too)."""
    n = norm(p).strip("\"' ")
    if not n:
        return False
    if any(n.endswith(e) for e in exts):
        return True
    if n.endswith("summary.json"):
        if any(n.startswith(r) for r in roots):
            return True
        if re.search(r"/(camera-jitter|ghost-hand|occlusion-drift)/data/", n):
            return True
    return False


def under_root(p, roots):
    n = norm(p).strip("\"' ").rstrip("/") + "/"
    return any(n.startswith(r) for r in roots) or bool(re.search(r"/(camera-jitter|ghost-hand)/data/", n))


def check(tool, inp, exts, roots):
    if tool == "Read":
        p = inp.get("file_path", "")
        return p if raw_path(p, exts, roots) else None
    if tool == "Grep":
        p = inp.get("path", "")
        if raw_path(p, exts, roots):
            return p
        glob = str(inp.get("glob") or "")
        if p and under_root(p, roots) and not (glob.endswith(".md") or glob.endswith(".csv")):
            return p + " (a BeG0nE data folder; add glob '*.md' to search the reports)"
        return None
    if tool in ("Bash", "PowerShell"):
        cmd = str(inp.get("command", ""))
        if OUR_TOOLS.search(cmd) or not READERS.search(cmd):
            return None
        for tok in re.split(r"[\s;|&<>()]+", cmd):
            if raw_path(tok, exts, roots):
                return tok
        if re.search(r"summary\.json", cmd, re.I) and re.search(r"(camera-jitter|ghost-hand|begone)", cmd, re.I):
            return "summary.json"
    return None


def main():
    try:
        data = json.load(sys.stdin)
        if data.get("hook_event_name", "PreToolUse") != "PreToolUse":
            return 0
        exts, roots = setup()
        hit = check(data.get("tool_name", ""), data.get("tool_input") or {}, exts, roots)
    except Exception:
        return 0
    if not hit:
        return 0
    sys.stderr.write(MESSAGE.format(what=hit))
    return 2


if __name__ == "__main__":
    sys.exit(main())
