"""update-hold-guard.py -- while a hold is on (tools/hold.py), nothing may change the installed Lanes.

Wired as PreToolUse on Bash|PowerShell (hooks/hooks.json). Asked for by the maintainer, 2026-11-01, during the
second two-PC test: "please see if you can build a guard around it instead, so something cannot overwrite
something else".

WHAT IT REFUSES (exit 2, with the hold's reason and how to lift it), only while a hold is on:
  claude plugin update|install|i|uninstall|remove|enable|disable  ... naming lanes
  claude plugin marketplace update|add|remove|rm                  ... naming the Lanes marketplace, or
  claude plugin marketplace update                                    with no name (that updates every one)
  uninstall.py (/lanes:uninstall)
  git pull|merge|reset|checkout|switch|rebase|am|cherry-pick|restore|clean|stash pop|stash apply
                                                                  ... run in the folder this Lanes is loaded from
      (0.103.0, Run 5: a PC that loads Lanes straight from a git folder updates it with a pull, which passed the hold)
Anything else passes, silent. No hold (or an expired one) -> silent.

Best effort, like every Bash guard here: it reads the command text. THIS GUARD MUST NEVER FAIL CLOSED on its
own errors: bad input or any exception -> exit 0, silent.
"""
import json
import os
import re
import sys
import time

STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "lanes")
HOLD_FILE = os.path.join(STATE_DIR, "update-hold.json")
SEP = r"[^;&|\n]*"
CLAUDE = r"\bclaude(?:\.exe|\.cmd)?\s+plugins?\s+"
PLUGIN_CHANGE = re.compile(CLAUDE + r"(update|install|i|uninstall|remove|rm|enable|disable)\b(" + SEP + ")", re.I)
MARKET_CHANGE = re.compile(CLAUDE + r"marketplace\s+(update|add|remove|rm)\b(" + SEP + ")", re.I)
# 0.105.0: only RUNNING the uninstaller counts (python <flags> <...>uninstall.py), not a command that merely names the
# file: a read-only grep or a compile check of it was refused twice while 0.105.0 was built.
UNINSTALL = re.compile(r"(?<![\w.\\-])(?:python3?|pythonw|py)(?:\.exe)?[\"']?\s+(?:-[A-Za-z0-9.]+\s+)*"
                       r"(?:\"[^\"]*uninstall\.py\"|'[^']*uninstall\.py'|[^\s;&|]*uninstall\.py)", re.I)
GIT_CHANGE = re.compile(r"\bgit(?:\.exe)?((?:\s+-[Cc]\s+(?:\"[^\"]*\"|'[^']*'|\S+))*)\s+"
                        r"(pull|merge|reset|checkout|switch|rebase|am|cherry-pick|restore|clean|stash\s+(?:pop|apply))\b",
                        re.I)
CD = re.compile(r"(?:^|[;&|(]\s*)(?:cd|pushd|Set-Location)\s+(\"[^\"]*\"|'[^']*'|\S+)", re.I)
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def norm_path(p):
    p = (p or "").strip().strip("\"'").replace("\\", "/").rstrip("/").lower()
    m = re.match(r"^/([a-z])/(.*)$", p)            # git-bash style /d/... -> d:/...
    return ("%s:/%s" % (m.group(1), m.group(2))) if m else p


def lanes_folder():
    """the top of the git folder this Lanes is loaded from, or '' when it is not one (a normal plugin install)"""
    d = PLUGIN_ROOT
    for _ in range(4):
        if os.path.isdir(os.path.join(d, ".git")) or os.path.isfile(os.path.join(d, ".git")):
            return norm_path(d)
        d = os.path.dirname(d)
    return ""


def git_in_lanes(cmd, cwd):
    """the git command that would change the folder Lanes is loaded from, or ''"""
    root = lanes_folder()
    if not root:
        return ""
    for m in GIT_CHANGE.finditer(cmd):
        before = cmd[:m.start()]
        cds = CD.findall(before)
        where = re.findall(r"-[Cc]\s+(\"[^\"]*\"|'[^']*'|\S+)", m.group(1))
        target = norm_path(where[-1]) if where else (norm_path(cds[-1]) if cds else norm_path(cwd))
        if target == root or target.startswith(root + "/"):
            return m.group(0).strip()
    return ""


def active_hold():
    try:
        with open(HOLD_FILE, encoding="utf-8") as f:
            h = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(h, dict) or float(h.get("until", 0)) <= time.time():
        return None
    return h


def touches_lanes(cmd):
    """The first part of cmd that would change the installed Lanes, or ''."""
    for m in PLUGIN_CHANGE.finditer(cmd):
        if re.search(r"\blanes\b", m.group(2), re.I):
            return m.group(0).strip()
    for m in MARKET_CHANGE.finditer(cmd):
        verb, args = m.group(1).lower(), m.group(2)
        if re.search(r"lanes", args, re.I) or (verb == "update" and not args.strip()):
            return m.group(0).strip()
    m = UNINSTALL.search(cmd)
    return m.group(0) if m else ""


def main():
    try:
        # bytes, decoded utf-8-sig: input piped from PowerShell starts with a BOM, which made json fail -> let through
        data = json.loads(sys.stdin.buffer.read().decode("utf-8-sig", errors="replace") or "{}")
    except Exception:
        return
    if data.get("tool_name") not in ("Bash", "PowerShell"):
        return
    cmd = (data.get("tool_input") or {}).get("command") or ""
    low = cmd.lower()
    if "claude" not in low and "uninstall" not in low and "git" not in low:
        return
    hit = touches_lanes(cmd) or git_in_lanes(cmd, data.get("cwd") or "")
    if not hit:
        return
    h = active_hold()
    if not h:
        return
    try:  # switched off by name in lanes.conf -> the hold is ignored. Only an explicit "off" counts: a hold
        # exists only because someone put it on, so "not chosen yet" must not silently disable it.
        import importlib.util
        tools = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
        spec = importlib.util.spec_from_file_location("lanes_features", os.path.join(tools, "features.py"))
        ft = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ft)
        if ft.conf_value("update_hold") in ft.OFF_WORDS:
            return
    except Exception:
        pass
    sys.stderr.write(
        "Lanes: this would change the installed Lanes (%s), and Lanes updates are HELD on %s since %s: %s. "
        "The hold lifts by itself at %s. Do not work around it; tell the person what is waiting. Only they may lift "
        "it early: python \"${CLAUDE_PLUGIN_ROOT}/tools/hold.py\" off\n"
        % (hit[:80], h.get("by", "this PC"), h.get("since_iso", "?"), h.get("why", "no reason given"),
           h.get("until_iso", "?")))
    sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        pass
    sys.exit(0)
