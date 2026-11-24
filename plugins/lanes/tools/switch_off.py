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
    python switch_off.py audit                           session start: a switch-off since the last look that did
                                                         NOT come through this guard (Windows' own log), said once

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
BEFORE WINDOWS IS TOLD (0.118.2, 2026-11-20): the asking session's end steps (endwork.py run: locks given back, the
end report on the board, logs shelved) are run here and waited for, because a switched-off PC never closes the window
whose end hook would run them (2026-11-19 22:27: no end steps at all). Then a three-minute countdown, not one.
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
COUNTDOWN_S = 180               # Windows' own warning before it switches off (shutdown /a stops it); 60 until 0.118.2
ENDWORK_TIMEOUT_S = 1800        # the asking session's end steps (endwork.py: five steps of at most 300 s each)
AUDIT_FIRST_DAYS = 3            # the first audit on a PC looks this far back
AUDIT_EVENTS = 30               # Windows' last switch-off records read per audit
LANES_MARK = "Lanes:"           # how this guard's own switch-offs start their comment in Windows' log
HELD_H = 3                      # same as hooks/project-guard.py and handover.py
CHECK_TIMEOUT_S = 300           # the save check reads every copy on the PC
SHOWN = 6                       # lines of a save check shown per reason
SMALL_TIMEOUT_S = 30            # a quick command (a game list, `shutdown /a`)
MIN_S = 60                      # seconds in a minute
HOUR_S = 3600                   # seconds in an hour
DETACHED = 0x00000200 | 0x08000000   # NEW_PROCESS_GROUP | NO_WINDOW (2026-11-24: DETACHED_PROCESS dropped: with it every console child opened a window)


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
def end_steps(session):
    """The asking session's end steps, run and waited for before Windows is told (0.118.2). Its window never closes
    on its own before the PC goes off, so its SessionEnd hook would never start them. Never stops the switch-off."""
    if not session or skip("endwork"):
        return
    fake = os.environ.get("LANES_SWITCH_OFF_ENDWORK_CMD")         # tests: a command standing in for the end steps
    cmd = fake or [sys.executable, os.path.join(HERE, "endwork.py"), "run", "--session=" + session]
    code, _out = run(cmd, timeout=ENDWORK_TIMEOUT_S)
    log("end steps for session %s before the switch-off: %s" % (session, "done" if code == 0 else "exit %d" % code))


def switch_off(restart=False, session=""):
    end_steps(session)
    fake = os.environ.get("LANES_SWITCH_OFF_CMD")                 # tests: never the real thing
    if fake:
        return run(fake)[0] == 0
    if os.name != "nt":
        cmd = ["shutdown", "-r" if restart else "-h", "+%d" % max(1, COUNTDOWN_S // MIN_S)]
    else:
        cmd = ["shutdown", "/r" if restart else "/s", "/t", str(COUNTDOWN_S), "/c",
               LANES_MARK + " every session has finished and saved. Switching off in %d minutes (shutdown /a stops it)."
               % (COUNTDOWN_S // MIN_S)]
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
        if switch_off(a.restart, a.session):
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
            return 0 if switch_off(d.get("restart"), d.get("session", "")) else 2
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


# ---- the audit: switch-offs that did not come through this guard (0.118.2) --------------------------------------
AUDIT_STATE = os.path.join(STATE_DIR, "switch-off-audit.json")
EVENT = re.compile(r"<Event[ >].*?</Event>", re.S)


def _field(ev, name):
    m = re.search(r"<Data Name='%s'>(.*?)</Data>" % name, ev, re.S)
    return (m.group(1) if m else "").strip()


def switch_off_events():
    """Windows' last switch-off records (event 1074), newest first, as dicts. A test passes a file of them."""
    fake = os.environ.get("LANES_SWITCH_OFF_EVENTS_FILE")
    if fake:
        try:
            with open(fake, encoding="utf-8") as f:
                xml = f.read()
        except OSError:
            return []
    elif os.name == "nt":
        code, xml = run(["wevtutil", "qe", "System", "/q:*[System[(EventID=1074)]]", "/c:%d" % AUDIT_EVENTS,
                         "/rd:true", "/f:xml"], timeout=SMALL_TIMEOUT_S)
        if code:
            return []
    else:
        return []
    out = []
    for ev in EVENT.findall(xml):
        rid = re.search(r"<EventRecordID>(\d+)</EventRecordID>", ev)
        when = re.search(r"SystemTime='([^']+)'", ev)
        out.append({"id": int(rid.group(1)) if rid else 0, "when": when.group(1) if when else "",
                    "process": _field(ev, "param1"), "kind": _field(ev, "param5"), "comment": _field(ev, "param6")})
    return out


def bypassed(ev):
    """A switch-off typed by a session or a script (shutdown.exe) that is not this guard's own."""
    return "shutdown.exe" in ev["process"].lower() and not ev["comment"].startswith(LANES_MARK)


def local_time(iso):
    try:
        from datetime import datetime, timezone
        dt = datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).astimezone()
        return dt.strftime("%Y-%m-%d %H:%M"), dt.timestamp()
    except (ValueError, OverflowError, OSError):
        return iso[:16], 0.0


def cmd_audit(_a):
    events = switch_off_events()
    try:
        with open(AUDIT_STATE, encoding="utf-8") as f:
            last = int(json.load(f).get("last_id", 0))
    except (OSError, ValueError, AttributeError, TypeError):
        last = None
    found = []
    for ev in events:
        text, stamp = local_time(ev["when"])
        new = ev["id"] > last if last is not None else stamp >= time.time() - AUDIT_FIRST_DAYS * 24 * HOUR_S
        if new and bypassed(ev):
            found.append((text, ev))
    if events:
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            with open(AUDIT_STATE, "w", encoding="utf-8") as f:
                json.dump({"last_id": max(e["id"] for e in events), "checked": time.strftime("%Y-%m-%d %H:%M")}, f)
        except OSError:
            pass
    for text, ev in reversed(found):
        print("SWITCH-OFF NOT THROUGH THE GUARD: this PC was switched off (%s) at %s by a bare shutdown, comment: "
              "\"%s\". The guarded switch-off (switch_off.py) and its checks were skipped, so a session may have ended "
              "without its end steps. If a session did it, that is a Lanes fault: add a row to the fault list "
              "(FAULTS.md) naming the time, and raise it for the Keeper." % (ev["kind"] or "off", text,
                                                                            ev["comment"] or "none"))
        log("audit: switch-off at %s not through the guard (comment: %s)" % (text, ev["comment"] or "none"))
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
    for name, fn in (("status", cmd_status), ("cancel", cmd_cancel), ("audit", cmd_audit)):
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
