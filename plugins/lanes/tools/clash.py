#!/usr/bin/env python3
"""clash.py - the clash guard: what must not run at the same time, on one PC, across both PCs, or both
(lanes-next, 2026-11-05, feature `clash_guard`).

The maintainer, 2026-11-05: "we would ideally need something built into lanes that knows what cannot run at the same
time on either different PCs or at the same time on the same PC, or both, so it looks for things that are already
installed and checks newly added features for it too, instead of going through these things individually like with the
Fullscan right now." Then, the same day: "can you build the guard system that prevents from 2 Lanes features that
should not be working at the same time to work at the same time".

    python clash.py check <job> [project]     exit 0 = free to start; 1 = something it clashes with is running (one line)
    python clash.py take <job> [project]      check, then hold it (on this PC, and on GitHub when it clashes across PCs)
    python clash.py release <job> [project] [--stale]   give it back (this PC's own; --stale: the other PC's, once
                                              it is STALE_H old)
    python clash.py sweep                     give back this PC's GitHub locks whose window closed before its end steps
    python clash.py status                    what is held, where, since when
    python clash.py table                     the whole table in plain words
    python clash.py doc [--check]             write docs/CLASHES.md from the table (--check: exit 1 when stale)
    python clash.py audit                     every command, hook, tool and extra of the plugin has a row (exit 1 if not)

THE TABLE. JOBS says, for each thing that can clash: `alone` (two of it at once clash: "pc" = on one PC, "everywhere" =
on one PC or across both), `clashes` (other jobs it must not run beside, and where), `per_project` (two runs on
DIFFERENT projects are fine), `parts` (jobs it runs inside itself: its own session may start them while it holds the
lock), and `by` when an older guard already does the job (the live claims of /pd, /lm and /ms). A clash is
symmetrical: written once on either side is enough. "everywhere" is the stronger word and wins.
ROWS says, for every command, hook, tool and extra in the plugin, which job it is, or why it needs none ("free"), or
which job it is a part of. `audit` fails on anything without a row, so a new command, hook, tool or extra cannot be
added without saying whether it clashes (features.py lint and release.sh both run it).

THE LOCKS. On this PC: one small file per held job in the Lanes state folder (clash/). Across PCs: the same claim
pushed to the board on GitHub (handover/locks/<job>.lock; the full scan keeps its older handover/fullscan.lock so
fullscan_lock.py and this agree). A push is all-or-nothing, so two PCs taking one at the same moment cannot both win.
A lock older than STALE_H counts as left over from a run that was cut off. The hook hooks/clash-guard.py takes the lock
when a guarded command is typed or its skill is started (with the session's id, so its own parts pass), and gives back
everything that session held when it ends; commands also release at their own end. "force" right after the command
name starts it anyway (the person's word, never the model's).
"""
import os
import re
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fullscan_lock as FL  # noqa: E402  (the GitHub half: fetch, read, push without touching the clone)

PLUGIN = os.path.dirname(HERE)
CLASHES_DOC = os.path.join(PLUGIN, "docs", "CLASHES.md")
STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "lanes")
LOCAL_DIR = os.path.join(STATE_DIR, "clash")
REMOTE_DIR = "handover/locks"
LEGACY_REMOTE = {"fullscan": FL.LOCK_REL}       # kept where fullscan_lock.py looks for it
STALE_H = FL.STALE_H
TIME_FMT = FL.TIME_FMT
EVERY, PC = "everywhere", "pc"
GIT_TIMEOUT_S = 60          # a fetch or push to GitHub; a slow network must not hang a command
TAKE_ATTEMPTS = 3           # pushes refused because the other PC pushed first, before giving up
ORPHAN_MIN_AGE_S = 180      # a GitHub lock of this PC with no file here is left over only once it is this old: a take
                            # writes the file here first and pushes after, so a younger one may still be on its way
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000   # Windows: enough rights to ask whether a program still runs
STILL_ACTIVE = 259          # Windows: the exit code of a program that has not ended
ALL = "all"

# ---------------------------------------------------------------------------------------------------------------------
# THE TABLE. Plain reasons: they are printed to the person when something is refused.
FULLSCAN_PARTS = ["gd", "gr", "sr", "od", "gu", "ch", "gs"]
JOBS = {
    "fullscan": {"label": "the full scan", "alone": EVERY, "parts": FULLSCAN_PARTS,
                 "clashes": {p: EVERY for p in FULLSCAN_PARTS},
                 "why": "two would double the research, rewrite the same notes and pages against each other, dig the "
                        "same shelves twice and could publish one download twice"},
    "gd": {"label": "Gold Digger", "alone": EVERY,
           "why": "two would read the same shelves and hand the same facts to the notes twice"},
    "gr": {"label": "game research (/gr)", "alone": EVERY, "per_project": True,
           "why": "two on one project would rewrite the same research notes against each other"},
    "sr": {"label": "the cross-project research sweep (/sr)", "alone": EVERY,
           "why": "both would rewrite the one shared library"},
    "od": {"label": "Out of Date (/od)", "alone": EVERY, "clashes": {"gu": EVERY, "release": EVERY},
           "why": "it rewrites front pages and descriptions and publishes downloads; two at once could publish twice"},
    "gu": {"label": "the weekly tool check (/gu)", "alone": EVERY, "clashes": {"ch": EVERY, "update": PC, "setup": PC},
           "why": "it puts tool copies back in step and installs updates; beside another it could undo the other's work"},
    "ch": {"label": "code health (/ch)", "alone": EVERY, "clashes": {"release": EVERY},
           "why": "it tidies our tools' code; a release or a second tidy at the same time would ship or tidy half of it"},
    "gs": {"label": "the GitHub sweep (/gs)", "alone": EVERY,
           "why": "two would file the same notes into the inboxes twice"},
    "ideas": {"label": "filing ideas", "alone": EVERY,
              "why": "two would file the same ideas twice and clear the phone page under each other"},
    "save": {"label": "a save (/sp)", "alone": PC, "stale_h": 1,
             "outside": "a /sp command of the person's own, outside Lanes: the hook takes the lock when /sp is typed, "
                        "and /sp gives it back as its last step (clash.py release save); else after an hour",
             "why": "two saves at once in one clone root sweep each other's unsaved files into their commits"},
    "release": {"label": "a Lanes release", "alone": EVERY,
                "why": "two releases at once would number and publish over each other"},
    "update": {"label": "a Lanes update", "alone": PC, "clashes": {"setup": PC, "uninstall": PC},
               "why": "two installs of the plugin on one PC at once leave it half one version, half the other"},
    "setup": {"label": "Lanes setup", "alone": PC, "clashes": {"uninstall": PC},
              "why": "it writes this PC's settings and installs programs; two at once write over each other"},
    "uninstall": {"label": "taking Lanes off", "alone": PC, "clashes": {"theme": PC},
                  "why": "it removes what the others are writing"},
    "theme": {"label": "the terminal look", "alone": PC,
              "why": "both write the terminal's one settings file"},
    "menu": {"label": "Menu-o-matiC / Move-o-matiC", "alone": PC, "clashes": {"bench": PC},
             "why": "both press keys into the window in front; two at once press into each other's game"},
    "bench": {"label": "VR Bench", "alone": PC,
              "why": "there is one pretend headset and one set of pretend hands on a PC"},
    "obs_clip": {"label": "a recording asked for by hand", "alone": PC, "clashes": {"begone_record": PC},
                 "by": "obs-rec.py start refuses while OBS is already recording",
                 "why": "OBS records one thing at a time; a second start would take over the first one's recording"},
    "begone_record": {"label": "the automatic BeG0nE recording", "alone": PC,
                      "by": "the BeG0nE helper never starts one while OBS is recording",
                      "why": "OBS records one thing at a time"},
    "rider": {"label": "the BeG0nE helper (and the collector in it)", "alone": PC,
              "by": "rider.py start: one helper per PC (a running one is kept, or restarted when its code is older)",
              "why": "two would file every report and every game run twice"},
    "live": {"label": "a game session (/lm or /ms)", "alone": PC,
             "why": "a PC runs one game at a time: two game sessions would fight over the screen, the keys, the headset and the frame-time numbers (Tefa, 2026-11-06: several /pd at once, only one live game)"},
    "lane": {"label": "/pd, /lm or /ms on one project", "alone": EVERY, "per_project": True,
             "by": "the live claim on the board (lane-claim.sh, the /pd lock and their hooks)",
             "why": "two sessions changing one game's mod at once undo each other's work"},
}
# Commands whose hook-held lock is taken from what is typed: the command name -> its job.
COMMAND_JOBS = {"fullscan": "fullscan", "gd": "gd", "gr": "gr", "sr": "sr", "od": "od", "gu": "gu", "ch": "ch",
                "gs": "gs", "ideas": "ideas", "update": "update", "setup": "setup", "uninstall": "uninstall",
                "theme": "theme", "sp": "save", "lm": "live", "ms": "live"}
# Menu-o-matiC and VR Bench are not here: the tools hold their own job while they press keys or run, since a lock
# taken when the command is typed would also stop the session's own tool.


def free(why):
    return ("free", why)


def part(job):
    return ("part", job)


def job(name):
    return ("job", name)


READ_ONLY = free("only reads, or prints a line; nothing to collide with")
PER_SESSION = free("works on this session's own files only")
LIBRARY = free("a helper other tools import; it does nothing on its own")
PLUMBING = free("starts the other hooks; does nothing on its own")
RULE = free("adds a line of instructions at session start")

ROWS = {
    # commands
    "command:fullscan": job("fullscan"), "command:gd": job("gd"), "command:gr": job("gr"), "command:sr": job("sr"),
    "command:od": job("od"), "command:gu": job("gu"), "command:ch": job("ch"), "command:gs": job("gs"),
    "command:ideas": job("ideas"), "command:update": job("update"), "command:setup": job("setup"),
    "command:uninstall": job("uninstall"), "command:theme": job("theme"), "command:bench": job("bench"),
    "command:menu": job("menu"), "command:pd": job("lane"), "command:lm": job("lane"), "command:ms": job("lane"),
    "command:gates": READ_ONLY, "command:gate-watch": READ_ONLY,
    # hooks
    "hook:begone-raw-guard.py": READ_ONLY, "hook:board-brief": READ_ONLY, "hook:builds-brief": READ_ONLY,
    "hook:games-brief": READ_ONLY, "hook:gu-nudge": READ_ONLY, "hook:handover-brief": READ_ONLY,
    "hook:ideas-brief": READ_ONLY, "hook:owed-brief": READ_ONLY, "hook:setup-nudge": READ_ONLY,
    "hook:update-nudge": READ_ONLY, "hook:shortcut-offer": READ_ONLY, "hook:version-line": READ_ONLY,
    "hook:name-rule": RULE, "hook:repo-rule": RULE, "hook:talk-rule": RULE, "hook:straight-talk": RULE,
    "hook:tools-rule": RULE, "hook:privacy-rule": RULE,
    "hook:taskbar-flash": free("only blinks this window's taskbar button"),
    "hook:run-hook.cmd": PLUMBING, "hook:py-hook": PLUMBING, "hook:emit_context.py": LIBRARY,
    "hook:hooks.json": PLUMBING,
    "hook:begone-ride": job("rider"),
    "hook:gd-shelve": free("a file already shelved is never copied twice (gd.py compares contents), so two sessions "
                           "shelving at once only skip each other's files"),
    "hook:handover-end": free("each PC writes only its own line on the board"),
    "hook:end-work.py": free("only starts tools/endwork.py, which takes its own turn"),
    "hook:session-name.py": free("only reads which Claude Code windows run, and names this one"),
    "hook:start-bundle.py": free("runs the small rule and reminder checks one after another; each only prints text"),
    "tool:briefcache.py": free("each refresh writes a new file and swaps it in whole"),
    "tool:endwork.py": free("one end at a time per PC (its own turn file); each step is safe twice"),
    "hook:theme-apply": free("acts once, the first session after an install, and not at all when the look is on"),
    "hook:compact-hook.py": PER_SESSION, "hook:inspector-hook.py": PER_SESSION,
    "hook:pd-guard.py": free("is itself a guard (the /pd lock)"),
    "hook:git-queue.py": free("is itself a guard (one git write at a time on a PC)"),
    "hook:project-guard.py": free("is itself a guard (one session writes into a game's files at a time)"),
    "hook:lane-claim-guard.py": free("is itself a guard (the live claim)"),
    "hook:skill-lane-guard.py": free("is itself a guard (the same checks when a skill is started)"),
    "hook:update-hold-guard.py": free("is itself a guard (holds Lanes updates during a test)"),
    "hook:clash-guard.py": free("is itself a guard (this one)"),
    "hook:reader-guard.py": free("is itself a guard (the /lm helper reads, never writes)"),
    "hook:repo-guard.py": free("is itself a guard (new repos private)"),
    "hook:privacy-hook.py": free("is itself a guard (no login, home paths or e-mail on GitHub)"),
    "hook:guard_runner.py": LIBRARY,
    "hook:tool-guards.py": free("runs the tool guards one after another in one process; each is itself a guard"),
    "hook:prompt-guards.py": free("runs the prompt guards one after another in one process; each is itself a guard"),
    "hook:rest-reminder.py": free("only adds a line of context, once per session (its own marker file)"),
    "hook:reply-check.py": PER_SESSION,
    # tools
    "tool:clash.py": free("is itself the guard"), "tool:fullscan_lock.py": free("is itself a guard (the full scan's)"),
    "tool:hold.py": free("is itself a guard (holds Lanes updates)"), "tool:lane-claim.sh": job("lane"),
    "tool:privacy-guard.py": free("is itself a guard; only reads what is about to be committed"),
    "tool:release.sh": job("release"), "tool:scrub-scan.py": part("release"),
    "tool:update-check.py": part("update"), "tool:uninstall.py": part("uninstall"), "tool:theme.py": part("theme"),
    "tool:gd.py": part("gd"), "tool:gu.py": part("gu"), "tool:gu_guard.py": part("gu"), "tool:gu_texts.py": part("gu"),
    "tool:od.py": part("od"), "tool:frontpage-scan.sh": part("od"), "tool:ch.py": part("ch"),
    "tool:gs-scan.sh": part("gs"), "tool:rule-reach-scan.py": part("gs"), "tool:inbox-correction-scan.py": part("gs"),
    "tool:ideas.py": part("ideas"),
    "tool:setup-scan.py": part("setup"), "tool:estate.py": part("setup"), "tool:display-name.py": part("setup"),
    "tool:machine-name.py": part("setup"), "tool:shortcut.py": part("setup"), "tool:remote-control.py": part("setup"),
    "tool:engine-mcp.py": part("setup"), "tool:openxr-sim.py": part("setup"), "tool:hand-freeze.py": part("setup"),
    "tool:ours.py": part("setup"), "tool:outside.py": part("setup"), "tool:thanks.py": part("setup"),
    "tool:offers.py": free("each offer is one line in this PC's own record"),
    "tool:menu-o-matic": job("menu"), "tool:vrbench": job("bench"),
    "tool:obs-rec.py": job("obs_clip"),
    "tool:builds.py": part("lane"), "tool:builds_vanilla.py": part("lane"), "tool:unlock.py": part("lane"),
    "tool:proxy-gen": part("lane"), "tool:code-shape-scan.py": READ_ONLY,
    "tool:games.py": free("each PC writes only its own games record"),
    "tool:handover.py": free("each PC writes only its own line on the board"),
    "tool:owed.sh": free("each reminder is its own file"),
    "tool:installed.py": free("each PC writes only its own record"),
    "tool:root-sync.sh": free("each clone root belongs to one kind of session, and GitHub is the only meeting point"),
    "tool:begone.py": READ_ONLY, "tool:gate-scan.sh": READ_ONLY, "tool:git_leftovers.py": READ_ONLY,
    "tool:features.py": free("each switch is one line in this PC's lanes.conf"),
    "tool:inspector.py": PER_SESSION, "tool:inspector_checks.py": LIBRARY, "tool:inspector_store.py": PER_SESSION,
    "tool:compact.py": PER_SESSION, "tool:session-log.py": PER_SESSION, "tool:run-log.sh": PER_SESSION,
    "tool:lanes_common.py": LIBRARY, "tool:taskbar_flash.py": PER_SESSION, "tool:lanes_version.py": LIBRARY,
    # the BeG0nE helper's own files
    "begone:rider.py": job("rider"), "begone:collector.py": part("rider"), "begone:video_tidy.py": part("rider"),
    "begone:autosave.py": free("commits only its own new report files, and tries again when GitHub refuses a push"),
    "begone:begone_common.py": LIBRARY,
    # extras (features.py)
    "feature:theme": job("theme"), "feature:collector": part("rider"), "feature:begone_ride": job("rider"),
    "feature:begone_record": job("begone_record"), "feature:begone_video_tidy": part("rider"),
    "feature:begone_autosave": free("commits only its own new report files"),
    "feature:fullscan": READ_ONLY, "feature:gu_nudge": READ_ONLY, "feature:version_line": READ_ONLY,
    "feature:clash_guard": free("is itself the guard"), "feature:git_queue": free("is itself a guard"),
    "feature:project_guard": free("is itself a guard"),
    "feature:keep_level": free("only fast-forwards a copy with no work of its own and no session writing into it; "
                               "the end helper runs one end at a time on a PC"),
    "feature:keeper": free("hand-overs are one sealed file each and are taken one at a time (parcel.py holds a "
                           "lock while it receives); the Keeper alone writes the front page, the index and the "
                           "activity log while the extra is on"),
    "hook:keeper-brief": READ_ONLY,
    "command:keeper": free("the Keeper's round: one Keeper, and receiving holds its own lock"),
    "tool:keeper.py": free("each queued job is its own file; the jobs list is appended to, one line a time"),
    "tool:parcel.py": free("one sealed file per hand-over; receiving holds a lock, so two never unpack at once"),
    "tool:doorman.py": free("opens and closes windows; its uploads go through parcel.py's lock"),
    "feature:update_hold": free("is itself a guard"), "feature:privacy_guard": free("is itself a guard"),
    "feature:update_safety": part("gu"), "feature:gold_digger": part("gd"), "feature:code_health": part("ch"),
    "feature:out_of_date": part("od"),
    "feature:talk_rule": RULE, "feature:straight_talk": RULE, "feature:tools_rule": RULE,
    "feature:reply_check": PER_SESSION, "feature:rest_reminder": free("only adds a line of context, once per session"),
    "feature:vr_effects_off": RULE, "feature:games_check": free("each PC writes only its own games record"),
    "feature:remote_control": free("a setting each session starts with"),
    "feature:keep_transcripts": PER_SESSION,
    "feature:taskbar_flash": free("only blinks this window's taskbar button"),
}
# A folder of the plugin's tools that counts as one tool (its files work together).
TOOL_FOLDERS = ("menu-o-matic", "vrbench", "proxy-gen")


def row_of(item):
    """the row for one item; the extras of other people's and our own apps are installers, set up like setup's"""
    if item in ROWS:
        return ROWS[item]
    if item.startswith("feature:"):
        try:
            import ours
            import outside
            name = item[len("feature:"):]
            if name in {ours.feature_name(n) for n in ours.TOOLS} | {outside.feature_name(n) for n in outside.TOOLS}:
                return part("setup")
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------------------------------------------------
# WHO CLASHES WITH WHOM

def stronger(a, b):
    return EVERY if EVERY in (a, b) else (a or b)


def scope(job_a, proj_a, job_b, proj_b):
    """None, PC or EVERY: whether job_a on proj_a clashes with job_b on proj_b, and where"""
    a, b = JOBS.get(job_a, {}), JOBS.get(job_b, {})
    if job_a == job_b:
        s = a.get("alone")
        if s and a.get("per_project") and ALL not in (proj_a, proj_b) and proj_a != proj_b:
            return None
        return s
    return stronger((a.get("clashes") or {}).get(job_b), (b.get("clashes") or {}).get(job_a))


def reach(name):
    """the widest place this job's lock must be seen: EVERY means it is also pushed to GitHub"""
    j = JOBS[name]
    out = j.get("alone")
    for other in JOBS:
        if other != name:
            out = stronger(out, scope(name, ALL, other, ALL))
    return out


# ---------------------------------------------------------------------------------------------------------------------
# THE LOCKS

def key(name, project):
    project = project or ALL
    return name if not JOBS[name].get("per_project") or project == ALL else "%s@%s" % (name, re.sub(r"[^\w.-]", "_", project))


def now_text():
    return datetime.now().astimezone().strftime(TIME_FMT)


def parse_time(t):
    try:
        return datetime.strptime(t.strip(), TIME_FMT)
    except (ValueError, AttributeError):
        return None


def age_h(t):
    return (datetime.now(timezone.utc) - t).total_seconds() / 3600 if t else 1e9


def lock_text(rec):
    return ("# Written by the lanes plugin (tools/clash.py): something that must not run twice at once.\n"
            + "".join("%s = %s\n" % (k, rec[k]) for k in ("machine", "since", "job", "project", "session")))


def parse_lock(text):
    rec = dict(re.findall(r"^(\w+) = (.*)$", text or "", re.M))
    rec.setdefault("job", "fullscan")
    rec.setdefault("project", ALL)
    rec.setdefault("session", "")
    rec["when"] = parse_time(rec.get("since", ""))
    return rec


def read_local(path):
    """one lock file on this PC, or None when it cannot be read (a half-written or vanished file)"""
    try:
        with open(path, encoding="utf-8") as f:
            rec = parse_lock(f.read())
    except OSError:
        return None
    rec.update(where="this PC", file=path)
    return rec


def local_locks():
    if not os.path.isdir(LOCAL_DIR):
        return []
    found = (read_local(os.path.join(LOCAL_DIR, n)) for n in sorted(os.listdir(LOCAL_DIR)) if n.endswith(".lock"))
    return [r for r in found if r]


def remote_rel(name, k):
    return LEGACY_REMOTE.get(k) or "%s/%s.lock" % (REMOTE_DIR, k)


def remote_locks(b):
    out = []
    if not b:
        return out
    ok, listing = FL.git(b, "ls-tree", "--name-only", "origin/main", REMOTE_DIR + "/")
    rels = (listing.splitlines() if ok else []) + list(LEGACY_REMOTE.values())
    for rel in rels:
        ok, text = FL.git(b, "show", "origin/main:" + rel)
        if ok:
            rec = parse_lock(text)
            rec.update(where="GitHub", rel=rel)
            out.append(rec)
    return out


def pid_alive(pid):
    """whether a process still runs (a tool's lock dies with its program). Never os.kill(pid, 0): on Windows signal 0
    is CTRL_C_EVENT."""
    try:
        import psutil
        return psutil.pid_exists(pid)
    except ImportError:
        pass
    if os.name == "nt":
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return code.value == STILL_ACTIVE
    return os.path.exists("/proc/%d" % pid)


def dead_tool_lock(rec):
    m = re.match(r"^tool-(\d+)$", rec.get("session", ""))
    return bool(m) and rec["where"] == "this PC" and not pid_alive(int(m.group(1)))


def blockers(c, name, project, session, remote):
    """the held locks that stop `name` on `project` from starting now (stale ones and this session's own are skipped)"""
    me = FL.me(c)
    found = []
    for rec in local_locks() + remote:
        if rec["job"] not in JOBS or age_h(rec["when"]) >= JOBS[rec["job"]].get("stale_h", STALE_H) or dead_tool_lock(rec):
            continue
        s = scope(name, project, rec["job"], rec["project"])
        if not s:
            continue
        on_this_pc = rec["where"] == "this PC" or rec.get("machine") == me
        if s == PC and not on_this_pc:
            continue
        if session and rec.get("session") == session:
            continue    # this session's own lock: running its own parts, or starting it again
        if on_this_pc and rec["where"] == "GitHub" and any(
                l["job"] == rec["job"] and l["project"] == rec["project"] for l in local_locks()):
            continue    # the GitHub copy of a lock already counted from this PC's own file
        found.append(rec)
    return found


def say_blocked(c, name, project, recs):
    r = recs[0]
    j = JOBS[r["job"]]
    where = "this PC" if r["where"] == "this PC" or r.get("machine") == FL.me(c) else r.get("machine", "the other PC")
    what = j["label"] + ("" if r["project"] in ("", ALL) else " on " + r["project"])
    since = r["when"].strftime("%H:%M") if r["when"] else "an unknown time"
    me_label = JOBS[name]["label"] + ("" if project in ("", ALL, None) else " on " + project)
    clear = "clash.py release %s %s" % (r["job"], r["project"] or ALL)
    how = ("run on this PC: %s" % clear) if where == "this PC" else \
        ("run on %s: %s (only the PC that holds it can, until it is %d h old)" % (where, clear, STALE_H))
    return ("CLASH GUARD: %s is running on %s (since %s), so %s does not start now: %s. Wait for it to finish; if it "
            "was cut off, its lock runs out after %d h, or %s."
            % (what, where, since, me_label, j["why"] if r["job"] == name else JOBS[name]["why"], STALE_H, how))


def check(c, name, project=ALL, session="", fetch=True):
    """(free_to_start, line)"""
    if name not in JOBS:
        return True, "CLASH GUARD: '%s' is not in the table; nothing to check." % name
    j = JOBS[name]
    if j.get("by"):
        return True, "CLASH GUARD: %s is guarded by %s." % (j["label"], j["by"])
    b = FL.board(c)
    remote = []
    if reach(name) == EVERY and b:
        if fetch and not FL.git(b, "fetch", "-q", "origin", timeout=GIT_TIMEOUT_S)[0]:
            return False, ("CLASH GUARD: GitHub could not be reached, so it cannot be checked that %s is not running on "
                           "the other PC. Try again when GitHub answers." % j["label"])
        remote = remote_locks(b)
    recs = blockers(c, name, project or ALL, session, remote)
    return (False, say_blocked(c, name, project, recs)) if recs else (True, "CLASH GUARD: %s is free to start." % j["label"])


def take(c, name, project=ALL, session="", force=False):
    """(ok, line). Holds it on this PC, and on GitHub when it clashes across PCs. force = the person said so."""
    if name not in JOBS:
        return False, "CLASH GUARD: unknown job '%s'. Known: %s" % (name, ", ".join(JOBS))
    if JOBS[name].get("by"):
        return check(c, name, project, session)
    project = project or ALL
    k = key(name, project)
    for rec in local_locks():
        if rec["job"] == name and rec["project"] == project and age_h(rec["when"]) < STALE_H:
            # The same session again, or its own command step (which carries the session's id since 0.103.0). A lock
            # taken with no session belongs to no session: it lets through only another call with no session (Run 5 B1:
            # it used to count as "this run" for every window on the PC).
            if rec.get("session", "") == (session or ""):
                return True, "CLASH GUARD: %s is already held on this PC by this run." % JOBS[name]["label"]
    rec = {"machine": FL.me(c), "since": now_text(), "job": name, "project": project, "session": session or ""}
    b = FL.board(c)
    local = os.path.join(LOCAL_DIR, k + ".lock")
    if reach(name) == EVERY and b:
        for _attempt in range(TAKE_ATTEMPTS):
            ok, line = (True, "") if force else check(c, name, project, session)
            if not ok:
                return False, line
            write_local(local, rec)   # here first: a GitHub lock of this PC with no file here counts as left over
            if FL.push_change(b, lock_text(rec), "clash guard: %s starts %s" % (rec["machine"], k), rel=remote_rel(name, k)):
                break
            drop_local(local)
        else:
            return False, "CLASH GUARD: could not put the lock on GitHub. Try again in a minute."
    else:
        if not force:
            ok, line = check(c, name, project, session, fetch=False)
            if not ok:
                return False, line
        write_local(local, rec)
    note = " (also on GitHub, so the other PC sees it)" if reach(name) == EVERY and b else ""
    return True, "CLASH GUARD: %s held by %s%s." % (JOBS[name]["label"], rec["machine"], note)


def write_local(path, rec):
    os.makedirs(LOCAL_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(lock_text(rec))


def drop_local(path):
    try:
        os.remove(path)
    except OSError:
        pass


def release(c, name, project=ALL, local_only=False, stale_ok=False):
    """local_only: only this PC's file (the SessionEnd hook, which Claude Code gives 1.5 s; the GitHub half is done by
    endwork.py, or by the next sweep). stale_ok: a lock of the OTHER PC may go once it is STALE_H old."""
    if name not in JOBS:
        return False, "CLASH GUARD: unknown job '%s'." % name
    k = key(name, project or ALL)
    p = os.path.join(LOCAL_DIR, k + ".lock")
    had = os.path.isfile(p)
    if had:
        drop_local(p)
    b = FL.board(c)
    if reach(name) == EVERY and b and not local_only:
        FL.git(b, "fetch", "-q", "origin", timeout=GIT_TIMEOUT_S)
        rel = remote_rel(name, k)
        ok, text = FL.git(b, "show", "origin/main:" + rel)
        if ok:
            rec = parse_lock(text)
            if rec.get("machine") != FL.me(c) and not (stale_ok and age_h(rec["when"]) >= STALE_H):
                return False, ("CLASH GUARD: the lock for %s is %s's, not this PC's; left alone (run the same command "
                               "on %s, or add --stale here once it is %d h old)."
                               % (k, rec.get("machine"), rec.get("machine"), STALE_H))
            if not FL.push_change(b, None, "clash guard: %s finished %s" % (FL.me(c), k), rel=rel):
                return False, "CLASH GUARD: could NOT remove the lock on GitHub; it runs out after %d h." % STALE_H
            had = True
    return True, "CLASH GUARD: %s %s." % (k, "released" if had else "was not held")


class hold:
    """`with clash.hold("menu"):` around a tool's own work: the tool holds its job for as long as it runs (the lock
    carries the program's id, so one that crashed holds nothing). Blocked: prints the one line and exits 1. The guard
    switched off, or broken: the tool just runs (never fails closed on its own error)."""

    def __init__(self, name, project=ALL):
        self.name, self.project, self.held = name, project, False

    def __enter__(self):
        try:
            import features
            if not features.is_on("clash_guard"):
                return self
            c = FL.conf()
            ok, line = take(c, self.name, self.project, "tool-%d" % os.getpid())
        except Exception:
            return self
        if not ok:
            print(line)
            sys.exit(1)
        self.held = True
        return self

    def __exit__(self, *_exc):
        if self.held:
            try:
                release(FL.conf(), self.name, self.project)
            except Exception:
                pass
        return False


def step(name, project=ALL):
    """A guarded job's own tool step holds the job itself (0.103.0, Run 5 B8): asked for in plain words, or done by
    hand without the skill, the job used to pass the prompt guard and run beside another. Inside a session (its id is
    in the environment) it holds the job for that session, as the typed command's hook would have, and passes at once
    when the hook already did; outside one it holds only while the tool runs. Blocked: prints the one line, exits 1.
    The guard switched off or broken: the tool just runs."""
    try:
        import features
        if not features.is_on("clash_guard"):
            return
        session = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
        if not session:
            h = hold(name, project)
            h.__enter__()
            import atexit
            atexit.register(h.__exit__)
            return
        ok, line = take(FL.conf(), name, project, session)
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        return
    if not ok:
        print(line)
        sys.exit(1)


def release_session(c, session, local_only=False):
    """everything one session held (its end: the SessionEnd hook, local_only; the GitHub half follows by sweep)"""
    out = []
    for rec in local_locks():
        if session and rec.get("session") == session and rec["job"] in JOBS:
            out.append(release(c, rec["job"], rec["project"], local_only=local_only)[1])
    return out


def sweep(c, fetch=True):
    """Give back this PC's GitHub locks whose file here is gone: the window that held them closed before its end
    steps reached GitHub (Run 5 B3b/B7/A1, real windows too). Run by endwork.py after every session end and at every
    session start. Never touches the other PC's locks, nor one younger than ORPHAN_MIN_AGE_S."""
    b = FL.board(c)
    if not b:
        return []
    if fetch and not FL.git(b, "fetch", "-q", "origin", timeout=GIT_TIMEOUT_S)[0]:
        return ["CLASH GUARD: GitHub could not be reached; left-over locks not checked."]
    me, out = FL.me(c), []
    # A lock past its time stops nothing, but nothing took it away either (0.107.0): the home PC's full scan of
    # 2026-11-07 left three on GitHub for three days, because its files were still on that PC and the sweep only
    # looked for GitHub locks WITHOUT a file. This PC's own run-out files go first, so their GitHub copies follow.
    for rec in local_locks():
        if rec["job"] in JOBS and age_h(rec["when"]) >= JOBS[rec["job"]].get("stale_h", STALE_H):
            drop_local(os.path.join(LOCAL_DIR, key(rec["job"], rec["project"]) + ".lock"))
    here = {(r["job"], r["project"]) for r in local_locks()}
    for rec in remote_locks(b):
        if rec["job"] not in JOBS:
            continue
        k = key(rec["job"], rec["project"])
        if rec.get("machine") != me:
            # the other PC's: only once it has run out (it blocks nothing by then), so the list stays readable
            if rec["when"] and age_h(rec["when"]) >= STALE_H and FL.push_change(
                    b, None, "clash guard: %s clears %s's run-out lock %s" % (me, rec.get("machine", "?"), k),
                    rel=rec["rel"]):
                out.append("CLASH GUARD: %s of %s had run out (over %d h old); cleared on GitHub."
                           % (k, rec.get("machine", "the other PC"), STALE_H))
            continue
        if (rec["job"], rec["project"]) in here:
            continue
        if rec["when"] and age_h(rec["when"]) * 3600 < ORPHAN_MIN_AGE_S:
            continue
        ok = FL.push_change(b, None, "clash guard: %s gives back %s (its window closed first)" % (me, k), rel=rec["rel"])
        out.append("CLASH GUARD: %s %s." % (k, "given back on GitHub: its window closed before its end steps did"
                                            if ok else "is left over on GitHub and could NOT be removed now"))
    return out


# ---------------------------------------------------------------------------------------------------------------------
# THE AUDIT: every command, hook, tool and extra has a row

def items():
    out = []
    for n in sorted(os.listdir(os.path.join(PLUGIN, "commands"))):
        if n.endswith(".md"):
            out.append("command:" + n[:-3])
    for n in sorted(os.listdir(os.path.join(PLUGIN, "hooks"))):
        if not n.startswith((".", "__")) and os.path.isfile(os.path.join(PLUGIN, "hooks", n)):
            out.append("hook:" + n)
    for n in sorted(os.listdir(HERE)):
        p = os.path.join(HERE, n)
        if (os.path.isfile(p) and n.endswith((".py", ".sh"))) or (os.path.isdir(p) and n in TOOL_FOLDERS):
            out.append("tool:" + n)
        elif os.path.isdir(p) and not n.startswith((".", "__")) and n != "tests":
            out.append("tool:" + n)     # a new folder of tools must get a row (or join TOOL_FOLDERS)
    bg = os.path.join(PLUGIN, "begone")
    for n in sorted(os.listdir(bg)) if os.path.isdir(bg) else []:
        if n.endswith(".py"):
            out.append("begone:" + n)
    try:
        import features
        out += ["feature:" + n for n in features.FEATURES]
    except Exception as e:
        out.append("feature:<features.py would not load: %s>" % e)
    return out


def guarded_in_command(name):
    """the commands whose file calls the guard for this job, or whose hook-held lock covers it"""
    return [cmd for cmd, j in COMMAND_JOBS.items() if j == name and os.path.isfile(os.path.join(PLUGIN, "commands", cmd + ".md"))]


def audit():
    problems = []
    for it in items():
        r = row_of(it)
        if r is None:
            problems.append("%s has no row in tools/clash.py (say which job it is, or why it needs none)" % it)
        elif r[0] in ("job", "part") and r[1] not in JOBS:
            problems.append("%s points at '%s', which is not a job in the table" % (it, r[1]))
    names = set(items())
    for it in ROWS:
        if it not in names:
            problems.append("%s has a row but is not in the plugin any more (take the row out)" % it)
    for n, j in JOBS.items():
        for other, s in (j.get("clashes") or {}).items():
            if other not in JOBS:
                problems.append("%s clashes with '%s', which is not a job" % (n, other))
            if s not in (PC, EVERY):
                problems.append("%s -> %s: '%s' must be pc or everywhere" % (n, other, s))
        if j.get("alone") not in (None, PC, EVERY):
            problems.append("%s: alone must be pc, everywhere or nothing" % n)
        for p in j.get("parts") or []:
            if p not in JOBS:
                problems.append("%s: part '%s' is not a job" % (n, p))
        if not j.get("why") or not j.get("label"):
            problems.append("%s: no label or no reason" % n)
        # a job nothing enforces is a promise, not a guard
        if not j.get("by") and not j.get("outside") and not guarded_in_command(n) and not [i for i, r in ROWS.items() if r == job(n) and
                                                                    i.startswith("tool:")]:
            problems.append("%s: nothing takes its lock (no command, tool or older guard)" % n)
    # a tool that IS a job must really ask the guard (its code names clash.py), unless an older guard does the job
    for it, r in ROWS.items():
        if r[0] == "job" and it.startswith("tool:") and not JOBS[r[1]].get("by") and not mentions_clash(it[5:]):
            problems.append("%s is the job '%s' but never asks the guard (no clash.py in its code)" % (it, r[1]))
    return problems


def mentions_clash(name):
    p = os.path.join(HERE, name)
    files = [os.path.join(d, f) for d, _s, fs in os.walk(p) for f in fs if f.endswith((".py", ".sh"))] \
        if os.path.isdir(p) else [p]
    for f in files:
        try:
            if "clash.py" in open(f, encoding="utf-8", errors="replace").read():
                return True
        except OSError:
            pass
    return False


# ---------------------------------------------------------------------------------------------------------------------
# PLAIN WORDS

def place(s):
    return {PC: "on the same PC", EVERY: "on either PC"}.get(s, "")


def table_lines():
    out = []
    for n, j in JOBS.items():
        bits = []
        if j.get("alone"):
            bits.append("never two at once %s%s" % (place(j["alone"]), " (on one project)" if j.get("per_project") else ""))
        cl = {}
        for other in JOBS:
            if other != n:
                s = scope(n, ALL, other, ALL)
                if s:
                    cl.setdefault(s, []).append(JOBS[other]["label"])
        for s in (EVERY, PC):
            if cl.get(s):
                bits.append("not beside %s %s" % (", ".join(cl[s]), place(s)))
        if j.get("parts"):
            bits.append("its own parts may run inside it")
        out.append("- **%s** (`%s`): %s. Why: %s.%s" % (j["label"], n, "; ".join(bits) or "no clash", j["why"],
                                                      " Guarded by: %s." % j["by"] if j.get("by") else ""))
    return out


def doc_text():
    free_rows = sum(1 for r in ROWS.values() if r[0] == "free")
    return "\n".join(
        ["# What must not run at the same time", "",
         "The clash guard (`tools/clash.py`, extra `clash_guard`) keeps these apart. \"On the same PC\" is checked with a",
         "small file on this PC; \"on either PC\" is also held on GitHub, so the other PC sees it. A lock left by a run that",
         "was cut off runs out after %d hours. Written by `tools/clash.py doc`; edit the table there, not here." % STALE_H, ""]
        + table_lines()
        + ["", "Every other command, hook, tool and extra of the plugin (%d of them) has a row saying why it needs no guard;"
           % free_rows, "`clash.py audit` refuses a new one without a row.", ""])


def status(c):
    b = FL.board(c)
    if b:
        FL.git(b, "fetch", "-q", "origin", timeout=GIT_TIMEOUT_S)
    recs = local_locks() + remote_locks(b)
    if not recs:
        print("CLASH GUARD: nothing held.")
    for r in recs:
        label = JOBS.get(r["job"], {}).get("label", r["job"])
        print("CLASH GUARD: %s%s held on %s by %s since %s%s" % (
            label, "" if r["project"] in ("", ALL) else " (" + r["project"] + ")", r["where"], r.get("machine", "?"),
            r["when"].strftime("%Y-%m-%d %H:%M") if r["when"] else "?",
            " (left over: runs out)" if age_h(r["when"]) >= STALE_H else ""))
    return 0


def main(argv):
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    a = argv[1:]
    cmd = a[0] if a else "status"
    c = FL.conf()
    words = [w for w in a if not w.startswith("--")]
    # A command's own step runs inside its session, whose id Claude Code puts in the environment: so the step counts as
    # the same run as the hook that took the lock, and nothing else on the PC does (Run 5 B1).
    session = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if cmd in ("check", "take", "release") and len(words) > 1:
        name, project = words[1], (words[2] if len(words) > 2 else ALL)
        if cmd == "check":
            ok, line = check(c, name, project, session)
        elif cmd == "take":
            ok, line = take(c, name, project, session)
        else:
            ok, line = release(c, name, project, stale_ok="--stale" in a)
        print(line)
        return 0 if ok else 1
    if cmd == "sweep":
        lines = sweep(c)
        print("\n".join(lines) if lines else "CLASH GUARD: no left-over locks of this PC on GitHub.")
        return 0
    if cmd == "status":
        return status(c)
    if cmd == "table":
        print("\n".join(table_lines()))
        return 0
    if cmd == "doc":
        text = doc_text()
        try:
            same = open(CLASHES_DOC, encoding="utf-8").read() == text
        except OSError:
            same = False
        if "--check" in a:
            print("docs/CLASHES.md is up to date" if same else "docs/CLASHES.md is stale: run clash.py doc")
            return 0 if same else 1
        with open(CLASHES_DOC, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print("wrote docs/CLASHES.md")
        return 0
    if cmd == "audit":
        p = audit()
        print("\n".join(p) if p else "CLASH GUARD: all %d commands, hooks, tools and extras have a row; every job is "
                                     "enforced somewhere." % len(items()))
        return 1 if p else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
