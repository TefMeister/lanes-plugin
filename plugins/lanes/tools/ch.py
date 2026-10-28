#!/usr/bin/env python3
"""ch.py - Code health: a full re-read of our own tools, looking for what can be tidied without breaking anything
(0.89.0, 2026-10-27).

Asked for by the maintainer, 2026-10-27, after the first hand-run pass over BeG0nE, the o-matiC tools and Lanes:
"it's been months of adding stuff and maybe a complete re-read of the code is in order, but at the same time i hope
this is not going to break things that actually work right now, so please save a working copy of everything", then
"if this is useful to do on a more regular basis, please make a slash command /ch for Code health and also add this
slash command to the /fullscan function". /lanes:ch follows this tool; PROTOCOL section 37.

    python ch.py repos                 the repos it looks after (lanes.conf `ch_repo =`, else every `ours =`)
    python ch.py backup                the working copy, BEFORE any change: a `pre-ch-<date>` tag in every repo,
                                       pushed to GitHub, and a bundle of each repo's full history in the backup
                                       folder (lanes.conf `ch_backup =`, else <transfer>/Code health backups,
                                       else ~/Lanes code health backups)
    python ch.py scan [--json]         the read-only look, in plain words: possible errors, code with no caller left
                                       anywhere (tests and docs count as callers), settings that are named but never
                                       used, twin copies that drifted apart, and leftovers taking space on this PC
    python ch.py done                  stamp the run (for the weekly full scan's report)

WHAT THE FIRST PASS TAUGHT (2026-10-27), built in so the next one does not repeat it
  - "Unused" from a checker is a lead, not a verdict: a helper only the tests call (changed_region) was removed and
    put back the same hour. So a name is reported as having no caller only when it appears ONCE in the whole repo,
    counting tests, docs and command files.
  - A setting that is named but never read can be a safety limit that was planned and never wired in (VR Bench's
    STAGE_TIMEOUT_S): that is a job for a board row, never something to delete.
  - Two copies of one script drift: BeG0nE's Village grip had a 2026-10-24 fix the Lanes copy never got. The twins
    check (shared with /lanes:gu) reads the display name and "the maintainer" as the same word, since the Lanes copy
    is rewritten that way on purpose.

Python checks use ruff and vulture when installed (`pip install ruff vulture`); without them the scan says so and
carries on. Never edits code: the session decides, from the scan and the Inspector's notes, what to change.
Tests set LANES_CONFIG, LANES_STATE_DIR and LANES_CH_TODAY.
"""
import datetime
import glob
import json
import os
import re
import subprocess
import sys

import gu

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "lanes")
STATE_FILE = os.path.join(STATE_DIR, "ch.json")
TOOL_TIMEOUT_S = 300          # one ruff or vulture run over one repo
GIT_TIMEOUT_S = 120           # a tag push or a bundle of one repo
VERSION_ASK_TIMEOUT_S = 30    # asking whether ruff or vulture is installed
GREP_TIMEOUT_S = 60           # counting one name across a repo
VULTURE_CONFIDENCE = 60       # vulture's own scale; below this it guesses too much
KEEP_PLUGIN_VERSIONS = 2      # newest cached plugin versions that are never called leftovers
# Errors and leftovers only; style rules (quote style, % formatting) are not health.
RUFF_RULES = "F401,F541,F811,F821,F841,E9,F63,F7,B006,UP020"
RUFF_SKIP = "archive,old-text-banner"
VULTURE_SKIP = "*/tests/*,*test_*,*/archive/*,*/old-*/*"
SETTINGS_FILE_HINT = re.compile(r"(settings|_settings|conf|config)\.py$")
NAME_IN_HIT = re.compile(r"unused (function|variable|class|method|property|import) '([^']+)'")
STRUCT_FIELD = re.compile(r"unused attribute '(b[A-Z]|cb[A-Z]|dw[A-Z]|w[A-Z])")  # ctypes structure fields


def today():
    fake = os.environ.get("LANES_CH_TODAY")
    return datetime.date.fromisoformat(fake) if fake else datetime.date.today()


def repos():
    own = gu.conf_values("ch_repo") or gu.conf_values("ours")
    return [r for r in own if os.path.isdir(os.path.join(r, ".git"))]


def backup_dir():
    own = gu.conf_values("ch_backup")
    if own:
        return own[-1]
    t = gu.conf_values("transfer")
    return os.path.join(t[-1], "Code health backups") if t else os.path.join(os.path.expanduser("~"),
                                                                           "Lanes code health backups")


def run(cmd, cwd=None, timeout=TOOL_TIMEOUT_S):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout)
        return p.returncode, p.stdout + p.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return -1, str(e)


def has_module(name):
    return run([sys.executable, "-m", name, "--version"], timeout=VERSION_ASK_TIMEOUT_S)[0] == 0


# ---- backup ---------------------------------------------------------------------------------------------------

def backup():
    tag = "pre-ch-" + today().isoformat()
    dest = os.path.join(backup_dir(), tag)
    os.makedirs(dest, exist_ok=True)
    lines, bad = [], 0
    for r in repos():
        name = os.path.basename(r.rstrip("/\\"))
        rc, out = run(["git", "-C", r, "tag", "-a", tag, "-m", "Working copy before a code health pass"],
                      timeout=GIT_TIMEOUT_S)
        made = rc == 0 or "already exists" in out
        pushed = run(["git", "-C", r, "push", "-q", "origin", tag], timeout=GIT_TIMEOUT_S)[0] == 0 if made else False
        bundled = run(["git", "-C", r, "bundle", "create", os.path.join(dest, name + ".bundle"), "--all"],
                      timeout=GIT_TIMEOUT_S)[0] == 0
        ok = made and pushed and bundled
        bad += not ok
        lines.append(f"  {'ok ' if ok else 'NO '} {name}: tag {'pushed' if pushed else 'NOT pushed'}, "
                     f"bundle {'saved' if bundled else 'NOT saved'}")
    lines.insert(0, f"Working copy {tag}: {len(lines)} repo(s), bundles in {dest}")
    lines.append("Every repo saved." if not bad else f"{bad} repo(s) NOT fully saved: fix that before changing code.")
    return "\n".join(lines), bad == 0


# ---- the scan -------------------------------------------------------------------------------------------------

def ruff_findings(repo):
    rc, out = run([sys.executable, "-m", "ruff", "check", "--select", RUFF_RULES, "--output-format", "concise",
                   "--no-cache", "--extend-exclude", RUFF_SKIP, "."], cwd=repo)
    return [line for line in out.splitlines() if re.match(r"^\S.*:\d+:\d+: [A-Z]+\d+", line)]


def mentions(repo, name, code_only=False):
    """How many times `name` appears as a word in the repo's tracked text files (code, tests, docs, commands).
    code_only leaves out Markdown: a plan that names a setting is not code that reads it."""
    spec = ["--", ".", ":!*.md"] if code_only else []
    rc, out = run(["git", "-C", repo, "grep", "-c", "-w", "-I", "-e", name] + spec, timeout=GREP_TIMEOUT_S)
    return sum(int(line.rsplit(":", 1)[1]) for line in out.splitlines() if line.rsplit(":", 1)[-1].isdigit())


def vulture_findings(repo):
    """(no caller anywhere, settings never read): vulture's leads, kept only when the name appears once."""
    rc, out = run([sys.executable, "-m", "vulture", ".", "--min-confidence", str(VULTURE_CONFIDENCE),
                   "--exclude", VULTURE_SKIP], cwd=repo)
    dead, unread = [], []
    for line in out.splitlines():
        m = NAME_IN_HIT.search(line)
        if not m or STRUCT_FIELD.search(line):
            continue
        is_setting = m.group(1) == "variable" and (m.group(2).isupper() or SETTINGS_FILE_HINT.search(line))
        if mentions(repo, m.group(2), code_only=bool(is_setting)) > 1:
            continue
        (unread if is_setting else dead).append(line.strip())
    return dead, unread


def twins():
    out = []
    for v in gu.conf_values("twin"):
        t = gu.compare_twin(*gu.pair(v))
        if t.get("error") or t["differ"] or t["only_a"] or t["only_b"]:
            out.append(t)
    return out


def plugin_leftovers():
    """Old cached Lanes versions beyond the newest few, with their size in MB."""
    base = os.path.join(os.path.expanduser("~"), ".claude", "plugins", "cache", "lanes-plugin", "lanes")
    vers = sorted((d for d in glob.glob(os.path.join(base, "*")) if os.path.isdir(d)),
                  key=lambda d: [int(x) if x.isdigit() else 0 for x in os.path.basename(d).split(".")])
    old = vers[:-KEEP_PLUGIN_VERSIONS] if len(vers) > KEEP_PLUGIN_VERSIONS else []
    size = 0
    for d in old:
        for root, _, files in os.walk(d):
            size += sum(os.path.getsize(os.path.join(root, f)) for f in files)
    return [os.path.basename(d) for d in old], round(size / 1e6, 1)


def command_leftovers():
    """Files in ~/.claude/commands that are not commands: temp files of an interrupted copy, old .bak copies."""
    d = os.path.join(os.path.expanduser("~"), ".claude", "commands")
    try:
        return sorted(f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f)) and not f.endswith(".md"))
    except OSError:
        return []


def scan():
    tools = {m: has_module(m) for m in ("ruff", "vulture")}
    report = {"date": today().isoformat(), "tools": tools, "repos": {}}
    for r in repos():
        row = {"errors": ruff_findings(r) if tools["ruff"] else None}
        row["no_caller"], row["never_read"] = vulture_findings(r) if tools["vulture"] else (None, None)
        report["repos"][os.path.basename(r.rstrip("/\\"))] = row
    report["twins"] = twins()
    report["old_plugin_versions"], report["old_plugin_mb"] = plugin_leftovers()
    report["command_leftovers"] = command_leftovers()
    return report


def show(report):
    lines = [f"CODE HEALTH {report['date']}"]
    missing = [m for m, ok in report["tools"].items() if not ok]
    if missing:
        lines.append(f"  (not installed, skipped: {', '.join(missing)}; `pip install {' '.join(missing)}`)")
    for name, row in report["repos"].items():
        lines.append(f"\n== {name}")
        for key, title in (("errors", "possible errors and unused imports (ruff)"),
                           ("no_caller", "no caller left anywhere, tests and docs included"),
                           ("never_read", "settings named but never read: a planned limit never wired in?")):
            items = row[key]
            if items is None:
                continue
            lines.append(f"  {title}: {len(items) or 'none'}")
            lines += ["    " + i for i in items]
    lines.append(f"\n== twin copies that differ: {len(report['twins']) or 'none'}")
    for t in report["twins"]:
        if t.get("error"):
            lines.append(f"  {t['error']}")
            continue
        newer = {"a": "the first (master)", "b": "the second"}.get(t["newer"], "neither clearly")
        lines.append(f"  {t['a']}\n   vs {t['b']}\n   differ: {', '.join(t['differ']) or '-'}; only in first: "
                     f"{len(t['only_a'])}; only in second: {len(t['only_b'])}; newer: {newer}")
    old, mb = report["old_plugin_versions"], report["old_plugin_mb"]
    lines.append(f"\n== on this PC: {len(old)} old cached Lanes version(s), {mb} MB"
                 + (f" ({old[0]} to {old[-1]})" if old else ""))
    cl = report["command_leftovers"]
    lines.append(f"   files in ~/.claude/commands that are not commands: {len(cl) or 'none'}"
                 + (f" ({', '.join(cl)})" if cl else ""))
    return "\n".join(lines)


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "scan"
    if cmd == "repos":
        print("\n".join(repos()) or "No repos: add `ch_repo = <clone>` (or `ours =`) lines to lanes.conf.")
    elif cmd == "backup":
        text, ok = backup()
        print(text)
        return 0 if ok else 1
    elif cmd == "scan":
        report = scan()
        print(json.dumps(report, indent=2) if "--json" in argv else show(report))
    elif cmd == "done":
        os.makedirs(STATE_DIR, exist_ok=True)
        state = load_state()
        state["last_run"] = today().isoformat()
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        print("Code health run stamped " + state["last_run"])
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):   # a character the console cannot show prints as ? (0.94.2)
        try:
            _stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv))
