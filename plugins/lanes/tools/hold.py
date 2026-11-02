#!/usr/bin/env python3
"""hold - keep Lanes itself from being updated, reinstalled or switched to another build while a test runs.

    python hold.py on "<why>" [--hours N]   put a hold on (default 12 h, at most 72 h); says who and why
    python hold.py off                      take it off
    python hold.py status [--json]          is a hold on, why, until when (exit 0 = on, 1 = off)

WHY (2026-11-01, the maintainer, during the second two-PC test)
  "please see if you can build a guard around it instead, so something cannot overwrite something else"
  A two-PC test compares the installed Lanes on both PCs. If any session updates or reinstalls it halfway
  (the weekly tool check, /lanes:update, a full scan, a second session), the PCs are no longer running what
  the test is about, and nothing says so. Remembering to type `skip:gu` is the kind of rule that is forgotten.

HOW IT HOLDS
  The hold is one small file on this PC (~/.claude/lanes/update-hold.json). The guard hook
  (hooks/update-hold-guard.py) refuses, while it is on, every command that would change the installed
  Lanes: `claude plugin update|install|uninstall|enable|disable lanes...`, `claude plugin marketplace
  update|add|remove` for the Lanes marketplace (or every marketplace), and /lanes:uninstall. The refusal
  names the hold, its reason and the way to lift it. update-check.py still says a new version exists, but
  as waiting behind the hold instead of offering it. Everything else /gu and /fullscan do goes on as usual.

  A hold ends by itself at its time limit, so a session that forgets `off` cannot freeze Lanes for good.
  It is per PC: hold both PCs for a two-PC test.

  On or off: `update_hold` (features.py; only an explicit `update_hold = off` in lanes.conf switches the
  guard off, since a hold exists only because someone put it on). Test override: LANES_STATE_DIR.
"""
import json
import os
import sys
import time

HOME = os.path.expanduser("~")
STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(HOME, ".claude", "lanes")
HOLD_FILE = os.path.join(STATE_DIR, "update-hold.json")
DEFAULT_HOURS = 12
MAX_HOURS = 72
MIN_HOURS = 0.1  # six minutes: the shortest hold worth writing down


def read_hold():
    """The active hold as a dict, or None. An expired or unreadable hold counts as none."""
    try:
        with open(HOLD_FILE, encoding="utf-8") as f:
            h = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(h, dict) or float(h.get("until", 0)) <= time.time():
        return None
    return h


def machine_name():
    """This PC's Lanes name from lanes.conf (machine_name =), never the computer's own name."""
    conf = os.environ.get("LANES_CONFIG") or os.path.join(HOME, ".claude", "lanes.conf")
    try:
        with open(conf, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return "this PC"
    found = [v.split(" #")[0].strip() for k, _, v in (ln.partition("=") for ln in lines) if k.strip() == "machine_name"]
    return (found[-1] if found else "") or "this PC"


def describe(h):
    left_h = max(0.0, (float(h["until"]) - time.time()) / 3600.0)
    return "Lanes updates are HELD on %s since %s: %s (lifts by itself at %s, in %.1f h; or: hold.py off)" % (
        h.get("by", "this PC"), h.get("since_iso", "?"), h.get("why", "no reason given"),
        h.get("until_iso", "?"), left_h)


def cmd_on(args):
    hours = DEFAULT_HOURS
    if "--hours" in args:
        i = args.index("--hours")
        try:
            hours = float(args[i + 1])
        except (IndexError, ValueError):
            print("hold: --hours needs a number"); return 2
        del args[i:i + 2]
    hours = max(MIN_HOURS, min(hours, MAX_HOURS))
    why = " ".join(args).strip()
    if not why:
        print('hold: say why, e.g.  hold.py on "two-PC test, round 3"'); return 2
    now = time.time()
    h = {"why": why, "by": machine_name(), "since": now, "until": now + hours * 3600,
         "since_iso": time.strftime("%Y-%m-%d %H:%M", time.localtime(now)),
         "until_iso": time.strftime("%Y-%m-%d %H:%M", time.localtime(now + hours * 3600))}
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(HOLD_FILE, "w", encoding="utf-8") as f:
        json.dump(h, f, indent=1)
    print(describe(h))
    return 0


def cmd_off():
    had = read_hold()
    try:
        os.remove(HOLD_FILE)
    except OSError:
        pass
    print("Lanes updates are no longer held on this PC." if had else "No hold was on.")
    return 0


def cmd_status(as_json):
    h = read_hold()
    if as_json:
        print(json.dumps({"held": bool(h), "hold": h}, indent=1))
    else:
        print(describe(h) if h else "No hold: Lanes can be updated on this PC.")
    return 0 if h else 1


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__); return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "on":
        return cmd_on(rest)
    if cmd == "off":
        return cmd_off()
    if cmd == "status":
        return cmd_status("--json" in rest)
    print("hold: unknown command %r (on, off, status)" % cmd); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
