#!/usr/bin/env python3
"""switch_off.py - the shutdown guard: switch this PC off only when every session on it has finished and saved
(0.112.0, 2026-11-12, extra `shutdown_guard`).

    python switch_off.py check [--session ID]           what still stops a switch-off (exit 0 = nothing, 1 = something)
    python switch_off.py now [--session ID] [--wait MIN] [--restart]
                                                         switch off now when nothing stops it; with --wait, a small
                                                         program left behind looks again every few minutes and switches
                                                         off as soon as nothing does, or gives up after MIN minutes
    python switch_off.py status                          a switch-off waiting? since when, for whom, until when
    python switch_off.py cancel                          take a waiting switch-off back (also stops a countdown)

WHY. On 2026-11-12 the Developer PC was switched off by a session (a bare `shutdown`) four minutes after its own job
ended. Another window had not run its end steps and held a clash-guard lock, and the builds store held a build that
was never pushed, so the next start read NOT SAVED. The person: "i did ask you to shut down the pc when you're
finished, might have shut down too early and have to put some sort of a guard in place to prevent that in the future".

WHAT STOPS IT (each named in plain words, never a folder path):
  - work on this PC that is not on GitHub: the save check (`handover.py check`); on a PC that hands its work to a
    Keeper PC, the light line instead (`parcel.py light`): a refused or never-handed-over step, or changes in no saved
    step, stop it, while a hand-over only waiting for the Keeper does not (the Keeper uploads it later by itself)
  - a game running (the collector's open run cards)
  - a live claim on the board held by this PC (/pd, /lm, /ms)
  - a clash-guard lock held on this PC by another session (a full scan, a release, a recording ...)
  - another session that wrote into a project in the last three hours and has not ended (the project guard's holds)
  - the asking session's own close-out not run yet (0.113.7): its end steps (the save, the board, the end report)
    happen in the close-out, and a PC switched off before them left the next start saying "the last session ended
    without its end steps" (2026-11-13 02:14, through this guard). With --wait it waits for the close-out too.
The asking session's own lock and holds never stop it (pass --session, or it is read from CLAUDE_CODE_SESSION_ID).
The guard never switches off by force: when the wait runs out it gives up and leaves a line in its log.
The hook hooks/switch-off-guard.py refuses a bare shutdown typed by a session and points here.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

HOME = os.path.expanduser("~")
STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(HOME, ".claude", "lanes")
REQUEST = os.path.join(STATE_DIR, "switch-off.json")
LOG = os.path.join(STATE_DIR, "switch-off.log")

# ---- settings (named numbers, one place) --------------------------------------------------------
POLL_S = 180                    # the waiting program looks again this often
DEFAULT_WAIT_MIN = 120          # `now --wait` with no number
COUNTDOWN_S = 60                # Windows' own warning before it switches off (shutdown /a stops it)
HELD_H = 3                      # same as hooks/project-guard.py and handover.py
CHECK_TIMEOUT_S = 300           # the save check reads every copy on the PC
SHOWN = 6                       # lines of a save check shown per reason
SMALL_TIMEOUT_S = 30            # a quick command (a game list, `shutdown /a`)
MIN_S = 60                      # seconds in a minute
HOUR_S = 3600                   # seconds in an hour
DETACHED = 0x00000008 | 0x00000200 | 0x08000000   # DETACHED_PROCESS | NEW_PROCESS_GROUP | NO_WINDOW


def log(line):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), line))


def skip(part):
    """tests only: LANES_SWITCH_OFF_SKIP=board,games leaves out the parts a pretend world cannot have"""
    return part in os.environ.get("LANES_SWITCH_OFF_SKIP", "").split(",")


def feature_on(name):
    try:
        import features
        return features.is_on(name)
    except Exception:  # noqa: BLE001 - features.py missing: treat the extra as off
        return False


def run(cmd, timeout=CHECK_TIMEOUT_S):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                           shell=isinstance(cmd, str))
        return r.returncode, (r.stdout + r.stderr).strip()
    except (subprocess.TimeoutExpired, OSError) as e:
        return 2, "could not run (%s)" % e.__class__.__name__


# ---- what stops it -----------------------------------------------------------------------------
def save_reasons():
    fake = os.environ.get("LANES_SWITCH_OFF_SAVE_CMD")            # tests: a command standing in for the save check
    if fake:
        code, out = run(fake)
        return ["not saved: " + out] if code else []
    if feature_on("keeper"):
        import keeper
        if keeper.role() == "developer":
            code, out = run([sys.executable, os.path.join(HERE, "parcel.py"), "light"])
            if code or "changes in no saved step" in out:
                return ["work not handed over yet: " + out.lstrip("\U0001F4E6 ")]
            return []
    code, out = run([sys.executable, os.path.join(HERE, "handover.py"), "check"])
    if code == 0:
        return []
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    if code == 2 or not lines:
        return ["the save check could not run: " + (lines[0] if lines else "no answer")]
    repos = [ln for ln in lines if not ln.startswith("HANDOVER:")] or lines
    more = ["... and %d more not on GitHub" % (len(repos) - SHOWN)] if len(repos) > SHOWN else []
    return ["not on GitHub: " + ln for ln in repos[:SHOWN]] + more


def game_reasons():
    if skip("games"):
        return []
    try:
        import handover
        return ["a game is still running: " + g for g in handover.games_running()]
    except Exception:  # noqa: BLE001 - no collector here: nothing to say
        return []


def claim_reasons():
    if skip("board"):
        return []
    try:
        import handover
        c = handover.read_conf()
        board, me = c.get("board", ""), c.get("machine_name") or c.get("role") or "PC"
        if not board or not os.path.isdir(board):
            return []
        handover.fetch_board(board)
        return ["a live claim on the board: " + h + " (the session's end steps give it back)"
                for h in handover.claims_held(board, me)]
    except Exception:  # noqa: BLE001
        return []


def lock_reasons(session):
    try:
        import clash
    except Exception:  # noqa: BLE001
        return []
    out = []
    for rec in clash.local_locks():
        if session and rec.get("session") == session:
            continue
        if clash.dead_tool_lock(rec) or clash.age_h(rec.get("when")) >= clash.STALE_H:
            continue
        what = rec.get("job", "?") + ("" if rec.get("project") in ("", clash.ALL) else " " + rec["project"])
        out.append("still running on this PC: %s (since %s)" % (what, rec.get("since", "?")))
    return out


def hold_reasons(session):
    folder = os.path.join(STATE_DIR, "projects-held")
    out = []
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return out
    for n in names:
        try:
            with open(os.path.join(folder, n), encoding="utf-8") as f:
                d = json.load(f)
            last = float(d.get("last", 0))
        except (OSError, ValueError, AttributeError, TypeError):
            continue
        if time.time() - last >= HELD_H * HOUR_S or (session and d.get("session") == session):
            continue
        mins = int((time.time() - last) // MIN_S)
        out.append("another session is working on %s (last change %d min ago) and has not ended"
                   % (n[:-5] if n.endswith(".json") else n, mins))
    return out


def own_end_reasons(session):
    """The asking session has not reached the end of its close-out (handover.py close writes 'done <session>' into
    the end log). No session named, or no end log on this PC yet (no clone roots set up): nothing to ask for."""
    if not session or skip("own_end"):
        return []
    try:
        import handover
        with open(handover.end_log_path(), encoding="utf-8") as f:
            lines = f.read().splitlines()
    except Exception:  # noqa: BLE001 - no end log yet: this PC has never written one
        return []
    sid = re.sub(r"[^\w\-]", "_", session)
    if any(ln.split()[:2] == ["done", sid] for ln in lines):
        return []
    return ["this session's own close-out has not run yet (its end steps: the save, the board, the end report): "
            "run it first (handover.py close), then the switch-off goes ahead"]


def reasons(session):
    return (game_reasons() + lock_reasons(session) + hold_reasons(session) + claim_reasons()
            + own_end_reasons(session) + save_reasons())


# ---- switching off -----------------------------------------------------------------------------
def switch_off(restart=False):
    fake = os.environ.get("LANES_SWITCH_OFF_CMD")                 # tests: never the real thing
    if fake:
        return run(fake)[0] == 0
    if os.name != "nt":
        cmd = ["shutdown", "-r" if restart else "-h", "+1"]
    else:
        cmd = ["shutdown", "/r" if restart else "/s", "/t", str(COUNTDOWN_S), "/c",
               "Lanes: every session has finished and saved. Switching off in a minute (shutdown /a stops it)."]
    return run(cmd, timeout=SMALL_TIMEOUT_S)[0] == 0


def read_request():
    try:
        with open(REQUEST, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_request(d):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = REQUEST + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f)
    os.replace(tmp, REQUEST)


def drop_request(rid=None):
    d = read_request()
    if d and (rid is None or d.get("id") == rid):
        try:
            os.remove(REQUEST)
        except OSError:
            pass


def say(found):
    for r in found:
        print("  - " + r)


def cmd_check(a):
    found = reasons(a.session)
    if not found:
        print("SWITCH-OFF: nothing stops it - every session here has finished and saved")
        return 0
    print("SWITCH-OFF: NOT YET - %d thing(s) stop it:" % len(found))
    say(found)
    return 1


def cmd_now(a):
    found = reasons(a.session)
    word = "restart" if a.restart else "switch-off"
    if not found:
        log("%s now, asked by session %s: nothing stops it" % (word, a.session or "?"))
        if switch_off(a.restart):
            print("SWITCH-OFF: nothing stops it; the PC %s in %d s (`shutdown /a` stops it)"
                  % ("restarts" if a.restart else "switches off", COUNTDOWN_S))
            return 0
        print("SWITCH-OFF: nothing stops it, but Windows refused the switch-off")
        return 2
    if a.wait is None:
        print("SWITCH-OFF: NOT done - %d thing(s) stop it:" % len(found))
        say(found)
        print("  `switch_off.py now --wait %d` leaves a small program that switches off as soon as they are done."
              % DEFAULT_WAIT_MIN)
        return 1
    minutes = a.wait or DEFAULT_WAIT_MIN
    rid = "%d-%d" % (int(time.time()), os.getpid())
    write_request({"id": rid, "session": a.session, "since": time.strftime("%Y-%m-%d %H:%M"),
                   "until": time.time() + minutes * MIN_S, "until_text": time.strftime(
                       "%H:%M", time.localtime(time.time() + minutes * MIN_S)), "restart": bool(a.restart)})
    log("%s asked by session %s, waiting up to %d min for: %s" % (word, a.session or "?", minutes, " | ".join(found)))
    if os.environ.get("LANES_SWITCH_OFF_INLINE"):                 # tests: watch in this process
        return watch(rid)
    args = [sys.executable, os.path.abspath(__file__), "_watch", rid]
    kw = {"creationflags": DETACHED} if os.name == "nt" else {"start_new_session": True}
    subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     close_fds=True, **kw)
    print("SWITCH-OFF: waiting (up to %d min, until %s) for:" % (minutes, time.strftime(
        "%H:%M", time.localtime(time.time() + minutes * MIN_S))))
    say(found)
    print("  It switches off by itself once they are done; it never forces. `switch_off.py cancel` takes it back.")
    return 0


def watch(rid):
    poll = float(os.environ.get("LANES_SWITCH_OFF_POLL_S") or POLL_S)
    while True:
        d = read_request()
        if not d or d.get("id") != rid:
            log("switch-off %s taken back" % rid)
            return 0
        found = reasons(d.get("session", ""))
        if not found:
            drop_request(rid)
            log("switch-off %s: nothing stops it any more, switching off" % rid)
            return 0 if switch_off(d.get("restart")) else 2
        if time.time() >= float(d.get("until", 0)):
            drop_request(rid)
            log("switch-off %s GAVE UP, the PC stays on; still: %s" % (rid, " | ".join(found)))
            return 1
        time.sleep(poll)


def cmd_status(_a):
    d = read_request()
    if not d:
        print("SWITCH-OFF: none waiting")
        return 0
    print("SWITCH-OFF: waiting since %s (asked by session %s), gives up at %s"
          % (d.get("since", "?"), d.get("session") or "?", d.get("until_text", "?")))
    return 0


def cmd_cancel(_a):
    had = read_request()
    drop_request()
    if os.name == "nt" and not os.environ.get("LANES_SWITCH_OFF_CMD"):
        run(["shutdown", "/a"], timeout=SMALL_TIMEOUT_S)                         # a countdown already started: stop it too
    log("cancelled by hand")
    print("SWITCH-OFF: taken back" if had else "SWITCH-OFF: none was waiting (any countdown stopped)")
    return 0


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("check", cmd_check), ("now", cmd_now)):
        p = sub.add_parser(name)
        p.add_argument("--session", default=os.environ.get("CLAUDE_CODE_SESSION_ID", ""))
        p.set_defaults(fn=fn)
        if name == "now":
            p.add_argument("--wait", type=int, nargs="?", const=0, default=None,
                           help="minutes to keep looking (default %d)" % DEFAULT_WAIT_MIN)
            p.add_argument("--restart", action="store_true")
    for name, fn in (("status", cmd_status), ("cancel", cmd_cancel)):
        sub.add_parser(name).set_defaults(fn=fn)
    p = sub.add_parser("_watch")
    p.add_argument("rid")
    p.set_defaults(fn=lambda a: watch(a.rid))
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))
