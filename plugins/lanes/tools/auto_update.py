#!/usr/bin/env python3
"""auto_update.py - Lanes updates itself, with no question (0.117.0, 2026-11-15, extra `auto_update`).

Asked for by the maintainer, 2026-11-15: "can you now update lanes automatically, without asking me". Until now a
session told the person a new version was out and waited for a yes (/lanes:update); the other PC then sat a version
or two behind until someone said yes there.

    python auto_update.py start [--wait] [--skill]
                                           (the session-start hook) when a newer Lanes is published and nothing on this
                                           PC stops it, start the update in the background and say so in one line per
                                           version; also report how the last update went. --wait: run it here (tests).
                                           --skill: called by /lanes:update, which holds the clash guard's `update`
                                           lock itself, so that lock is not read as "an update is running" (0.121.1)
    python auto_update.py run              (started by `start`) run the update commands, check the version, keep the
                                           result for the next session start
    python auto_update.py status           the last result, in plain words

WHAT STOPS IT (it waits, and tries again at the next session start):
  - a hold on Lanes updates (tools/hold.py: a test is running);
  - a game running on this PC (the collector's list), or a game session, VR Bench or a release holding its lock
    (tools/clash.py: live, bench, release, update);
  - an update already running (one at a time; a run cut off frees itself after RUN_STALE_MIN minutes).
  It never forces anything: a failed update is reported in plain words with its error, and the old version stays.
  A new version takes effect in sessions started after it is installed (restart Claude Code); running sessions keep
  the version they started with.
Test overrides: AUTO_UPDATE_TEST_CHECK (a file standing in for update-check.py --json), AUTO_UPDATE_TEST_GAMES
(comma-separated running games), LANES_STATE_DIR.
"""
import json
import os
import subprocess
import sys
import time
sys.path.append(os.path.dirname(os.path.abspath(__file__)))  # hidden.py sits beside this file
import hidden  # noqa: E402  the one way Lanes starts a program: never a black window (0.125.1)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "lanes")
DIR = os.path.join(STATE_DIR, "auto-update")
RESULT = os.path.join(DIR, "result.json")
RUNNING = os.path.join(DIR, "running.lock")
LOG = os.path.join(DIR, "log.txt")

# ---- settings (named numbers, one place) --------------------------------------------------------
RUN_STALE_MIN = 30              # a running.lock older than this was left by a run that was cut off
COMMAND_TIMEOUT_S = 300         # each update command gets this long
CHECK_TIMEOUT_S = 60
BLOCKING_JOBS = ("live", "bench", "release", "update")
CHANGES_SHOWN = 8
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, path)


def log(line):
    try:
        os.makedirs(DIR, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("%s  %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), line))
    except OSError:
        pass


def check(force=False):
    """update-check.py --json (or the test's stand-in): {installed, latest, newer, held, changes, update_commands}"""
    fake = os.environ.get("AUTO_UPDATE_TEST_CHECK")
    if fake:
        return _read(fake)
    args = [sys.executable, os.path.join(HERE, "update-check.py"), "--json"] + (["--force"] if force else [])
    try:
        r = hidden.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=CHECK_TIMEOUT_S)
        return json.loads(r.stdout) if r.stdout.strip() else {}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {}


def blockers(own_lock=False):
    """plain reasons the update must wait now; [] = go. own_lock: the caller (/lanes:update) holds the `update` lock
    itself; until 0.121.1 it read its own lock as "a Lanes update is running" and never installed (Workshop U1)."""
    out = []
    fake = os.environ.get("AUTO_UPDATE_TEST_GAMES")
    if fake is not None:
        out += ["%s is running" % g.strip() for g in fake.split(",") if g.strip()]
    else:
        try:
            import handover
            out += ["%s is running" % g for g in handover.games_running()]
        except Exception:  # noqa: BLE001 - no collector here: nothing to say
            pass
    try:
        import clash
        for rec in clash.local_locks():
            if own_lock and rec.get("job") == "update":
                continue
            if rec.get("job") in BLOCKING_JOBS and not clash.dead_tool_lock(rec) \
                    and clash.age_h(rec.get("when")) < clash.STALE_H:
                out.append("%s is running (since %s)" % (clash.JOBS.get(rec["job"], {}).get("label", rec["job"]),
                                                         rec.get("since", "?")))
    except Exception:  # noqa: BLE001
        pass
    return out


def running_now():
    try:
        return time.time() - os.path.getmtime(RUNNING) < RUN_STALE_MIN * 60
    except OSError:
        return False


def changes_text(info):
    lines = ["%s: %s" % (v, s.rstrip(".")) for v, s in (info.get("changes") or [])[:CHANGES_SHOWN]]
    more = len(info.get("changes") or []) - CHANGES_SHOWN
    return "; ".join(lines) + (" (+%d more)" % more if more > 0 else "")


def installed_plugins_version(market=None):
    """The Lanes version Claude Code itself lists as installed (installed_plugins.json), newest entry; None if unknown.

    0.121.1 (Workshop, 2026-11-21): the after-check ran update-check.py from the OLD version's folder, which reads its
    own plugin.json, so a good update 0.120.0 -> 0.120.1 was marked FAILED. Claude Code's own list is what counts."""
    path = os.environ.get("AUTO_UPDATE_TEST_INSTALLED") or os.path.join(
        os.path.expanduser("~"), ".claude", "plugins", "installed_plugins.json")
    data = _read(path)
    best = None
    for key, entries in (data.get("plugins") or {}).items():
        name, _, mk = key.partition("@")
        if name != "lanes" or (market and mk != market):
            continue
        for e in entries if isinstance(entries, list) else [entries]:
            v = e.get("version") if isinstance(e, dict) else None
            if v and (best is None or vtuple(v) > vtuple(best)):
                best = v
    return best


def vtuple(v):
    out = []
    for part in str(v or "0").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out)


def newest_of(*versions):
    vs = [v for v in versions if v]
    return max(vs, key=vtuple) if vs else None


def report_last(info=None):
    """one line about the last update, once: how it went"""
    r = _read(RESULT)
    if not r or r.get("reported"):
        return ""
    r["reported"] = time.strftime("%Y-%m-%d %H:%M")
    if not r.get("ok"):
        # 0.121.1 (Workshop U2): a failure a later update has since put right is old news, not a fault: this PC already
        # has the version that "failed" (or newer), so the line is dropped instead of being printed again.
        have = newest_of((info or {}).get("installed"), installed_plugins_version((info or {}).get("marketplace")))
        if have and r.get("latest") and vtuple(have) >= vtuple(r.get("latest")):
            r["superseded_by"] = have
            _write(RESULT, r)
            return ""
    _write(RESULT, r)
    if r.get("ok"):
        return ("LANES UPDATED ITSELF (auto_update): %s -> %s at %s. Sessions started from now on run it; say so in "
                "one plain line." % (r.get("from", "?"), r.get("to", "?"), r.get("when", "?")))
    return ("LANES COULD NOT UPDATE ITSELF (auto_update) from %s to %s at %s: %s. The old version still works. Say so "
            "in one plain line and put it on the fault list; the next session start tries again."
            % (r.get("from", "?"), r.get("latest", "?"), r.get("when", "?"), r.get("error", "no reason given")))


def cmd_start(wait=False, skill=False):
    lines = []
    info = check()
    last = report_last(info)
    if last:
        lines.append(last)
    if info.get("newer") and running_now():
        lines.append("Lanes %s is being installed in the background already." % info.get("latest"))
    elif info.get("newer") and info.get("held"):
        lines.append("Lanes %s is out; it installs by itself once the update hold on this PC is lifted (%s)."
                     % (info.get("latest"), (info.get("hold") or {}).get("why", "a test is running")))
    elif info.get("newer"):
        why = blockers(own_lock=skill)
        if why:
            lines.append("Lanes %s is out; it installs by itself at a session start when nothing stops it (now: %s)."
                         % (info.get("latest"), "; ".join(why)))
        elif not info.get("update_commands"):
            lines.append("Lanes %s is out, but this PC's install could not be found to update it: run /lanes:update."
                         % info.get("latest"))
        else:
            if wait:
                cmd_run(own_lock=skill)
            else:
                flags = CREATE_NO_WINDOW if os.name == "nt" else 0  # 2026-11-24: NO_WINDOW alone (with DETACHED, git and every other console child opened its own black window: Tefa saw them in the headset)
                hidden.Popen([sys.executable, os.path.abspath(__file__), "run"], creationflags=flags,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 close_fds=True)
            lines.append("LANES IS UPDATING ITSELF (auto_update, no question asked: Tefa's wish of 2026-11-15) from %s "
                         "to %s in the background. What each version adds: %s. Tell the person in plain words, one "
                         "line per version, and that it takes effect in sessions started after it is in (restart "
                         "Claude Code). Do not ask about it, and do not run /lanes:update."
                         % (info.get("installed"), info.get("latest"), changes_text(info)))
    if lines:
        print("\n".join(lines))
    return 0


def cmd_run(own_lock=False):
    if running_now():
        return 0
    os.makedirs(DIR, exist_ok=True)
    with open(RUNNING, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    try:
        info = check(force=True)
        if not info.get("newer"):
            return 0
        why = blockers(own_lock=own_lock)
        if why or info.get("held"):
            log("waited: " + "; ".join(why or ["held"]))
            return 0
        frm, latest = info.get("installed"), info.get("latest")
        log("updating %s -> %s" % (frm, latest))
        error = ""
        for cmd in info.get("update_commands", []):
            try:
                r = hidden.run(cmd, shell=True, capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", timeout=COMMAND_TIMEOUT_S)
                out = (r.stdout + r.stderr).strip()
                log("%s -> %d %s" % (cmd, r.returncode, out[-300:].replace("\n", " / ")))
                if r.returncode:
                    error = "%s failed: %s" % (cmd.split()[0], (out.splitlines() or ["no output"])[-1][:300])
                    break
            except (OSError, subprocess.TimeoutExpired) as e:
                error = "%s did not finish (%s)" % (cmd.split()[0], e.__class__.__name__)
                break
        after = check(force=True) if not error else {}
        # the newest of what the check says and what Claude Code's own list says (the check may run from the OLD copy)
        now_v = newest_of(after.get("installed"), installed_plugins_version(info.get("marketplace"))) if not error else None
        if not error and now_v != latest:
            error = "the installer finished but this PC still has %s" % now_v
        _write(RESULT, {"when": time.strftime("%Y-%m-%d %H:%M"), "from": frm, "latest": latest, "to": now_v,
                        "ok": not error, "error": error})
        log("done: %s" % (error or "now %s" % now_v))
        return 0 if not error else 1
    finally:
        try:
            os.remove(RUNNING)
        except OSError:
            pass


def cmd_status():
    r = _read(RESULT)
    if not r:
        print("auto_update: Lanes has not updated itself on this PC yet")
        return 0
    print("auto_update: %s, %s -> %s: %s" % (r.get("when"), r.get("from"), r.get("to") or r.get("latest"),
                                              "done" if r.get("ok") else "FAILED: " + r.get("error", "")))
    return 0


def main(argv):
    verb = argv[0] if argv else ""
    if verb == "start":
        return cmd_start(wait="--wait" in argv, skill="--skill" in argv)
    if verb == "run":
        return cmd_run()
    if verb == "status":
        return cmd_status()
    print(__doc__)
    return 2


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:  # noqa: BLE001 - a session start is never broken by this
        log("error: %r" % e)
        sys.exit(0)
