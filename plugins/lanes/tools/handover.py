#!/usr/bin/env python3
"""handover.py - the handover light: is it safe to carry on from the other PC?

    python handover.py check            SAVED / NOT SAVED: is every clone on this PC fully on GitHub?
    python handover.py start [--write]  the same, plus when each OTHER PC last saved and how it ended;
                                        --write also reports this PC on the board (at most once an hour)
    python handover.py end   [--write]  the same check at the end of a session; --write reports it on
                                        the board every time, so the other PC is told how this one ended
    python handover.py fresh [ROOT]     fetch every repo in one clone root and say which are behind GitHub
                                        (--pull brings them up to date; fast-forward only)
    python handover.py close            the close-out box that ends every lane's write-up (0.40.0): one
                                        table - SAVED / NOT SAVED as its headline, a row per repo this
                                        session pushed, the Inspector's count, any claim still held, and
                                        when the other PC last saved. Paste it unchanged.

Exit 0 = green, 1 = red (something is not on GitHub, or a repo is behind), 2 = could not run.
--session=<id> names the Claude Code session for start/close (default: $CLAUDE_CODE_SESSION_ID).

WHY (0.39.0, 2026-10-01)
  Two PCs share one GitHub account and hand work back and forth. GitHub is the only meeting point, and
  git never overwrites anything quietly - but two things rest on nobody forgetting: a file that was
  never added, and a clone that was read before it was pulled. On 2026-10-01 five helper scripts turned
  out to exist on one disk only, and a session summary had earlier blamed the other PC for being away
  when it was this PC's own copy that was behind. This tool prints the three lines that settle it:

    HANDOVER: SAVED - everything on this PC is on GitHub (62 repos in 5 folders).
    HANDOVER: PC1 (HOME) last saved 2026-09-30 21:33, 21 h ago, and ended SAVED.
    HANDOVER: FRESH - this folder has everything GitHub has.       (fresh mode only)

  It runs by itself at the start of every session (hooks/handover-brief) and at the end
  (hooks/handover-end), and every lane's write-up ends with the close-out box. No box, no trust.

THE CLOSE-OUT BOX (0.40.0, 2026-10-01, user-directed)
  The write-up used to end with three pieces in three styles: a hand-written save table, the
  Inspector's sentence and the HANDOVER line in capitals. Now one table, printed from facts so no row
  can be faked, in the same shape as the gate/model box above it:

    | 🔦 **SAVED** | **EVERYTHING ON THIS PC IS ON GITHUB** |
    | --- | --- |
    | 📦 lanes-plugin | pushed · 2 new commits |
    | 📦 the other 61 repos | nothing to push |
    | 🔍 Inspector | 3 found · 3 fixed · 0 kept · 0 for later · 0 unanswered |
    | 🔒 Claim | none held |
    | 🖥️ PC1 (HOME) | last saved 21 h ago, ended SAVED |

  The headline word is the signal: it prints after EVERY session, green means the whole PC is on
  GitHub, red names the repo and means "save first, then end". "Pushed" rows come from a snapshot
  of every repo's HEAD that `start` writes per session (lanes-sessions/ beside lanes.conf): a repo
  whose HEAD moved since and is clean was pushed by this session.

WHAT COUNTS AS NOT SAVED
  In every clone of every root: a file never added, a change not committed, a commit on no remote
  branch at all. The Inspector's local notes (an `inspector/` folder) and Python caches are the two
  things kept on one PC on purpose, so they do not count.

WHAT IT NEVER DOES
  It never pulls, merges or resets anything in `check`, `start` or `end`. The one write is one small
  file on the board, `handover/<machine>.txt`, committed on its own and pushed; a refused push is
  reported, never forced. Output names repos, roots by lane and PCs by their plugin names only.
"""
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

STATUS_WORKERS = 8                                  # clones read at once; git status is disk-bound
SECONDS_PER_MINUTE, SECONDS_PER_HOUR, SECONDS_PER_DAY = 60, 3600, 86400
AGE_IN_HOURS_UP_TO_H = 48                           # "21 h ago" up to two days, then "3 days ago"
STATE_MAX_CHARS = 300                               # the NOT SAVED detail kept in the board file

# the lane roots beside the live one (PROTOCOL section 3); -gu and -gd (the tool check and Gold Digger) were missing
# until 0.95.0, so 24 clones on the maintainer's dev PC were never checked and the light said SAVED without them
ROOT_SUFFIXES = ("-pd", "-gr", "-sr", "-gs", "-gu", "-gd")
IGNORED_PATH_PARTS = ("inspector/", "__pycache__/")  # kept on one PC on purpose
IGNORED_SUFFIXES = (".pyc",)
HEARTBEAT_DIR = "handover"
SNAPSHOT_DIR = "lanes-sessions"                     # beside lanes.conf: where each session's HEADs are kept
LIVE_RE = re.compile(r"^[^:]+:status/([^:]+)\.md:LIVE:\s+(/\w+)\s+\S+\s+\S+\s+(\S+)")
START_WRITE_MIN_AGE_S = 3600                        # a start report at most once an hour (fewer commits)
GIT_TIMEOUT_S = 30
FETCH_TIMEOUT_S = 90
PUSH_TIMEOUT_S = 60
TIME_FMT = "%Y-%m-%d %H:%M %z"
ENDS_MISSING_DAYS = 2                               # another PC starting sessions this long with no end reported
PROFILE_TITLE_CHARS = 40                            # a front-page row's title, shortened in the box
END_LOG = "end-log.txt"                             # beside the snapshots: which sessions reached their end report
END_LOG_KEEP_LINES = 200


def conf_path():
    # LANES_CONFIG, when set, is the whole answer: a missing file there means "no plugin setup",
    # never "fall back to the real one" (the fixture relies on it; so does anyone testing on a copy).
    p = os.environ.get("LANES_CONFIG")
    if p:
        return p
    return os.path.join(os.path.expanduser("~"), ".claude", "lanes.conf")


def read_conf():
    conf = {}
    try:
        with open(conf_path(), encoding="utf-8") as f:
            for line in f:
                m = re.match(r"^\s*([A-Za-z_]+)\s*=\s*(.*?)\s*(#.*)?$", line)
                if m and not line.lstrip().startswith("#"):
                    conf[m.group(1)] = m.group(2).strip()
    except OSError:
        pass
    return conf


def git(args, cwd, timeout=GIT_TIMEOUT_S):
    """Run git; return (ok, stdout). Never raises."""
    try:
        r = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
        return r.returncode == 0, (r.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        return False, ""


def norm(p):
    return os.path.normcase(os.path.normpath(os.path.abspath(p)))


def roots_from(conf):
    """Every clone root on this PC: the live one (the board's parent), the lane roots beside it,
    plus `root` and `lane_roots` from lanes.conf."""
    found = []
    board = conf.get("board", "")
    if board and os.path.isdir(board):
        live = os.path.dirname(os.path.abspath(board))
        found.append(live)
        for s in ROOT_SUFFIXES:
            if os.path.isdir(live + s):
                found.append(live + s)
    for key in ("root", "lane_roots", "gd_root"):
        for p in re.split(r"[,\s]+", conf.get(key, "")):
            if p and os.path.isdir(p):
                found.append(p)
    out, seen = [], set()
    for p in found:
        if norm(p) not in seen:
            seen.add(norm(p))
            out.append(os.path.abspath(p))
    return out


def root_label(root):
    base = os.path.basename(root.rstrip("\\/"))
    for s in ROOT_SUFFIXES:
        if base.endswith(s):
            return "/" + s[1:] + " root"
    return "live root"


def repos_in(root):
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return []
    return [os.path.join(root, n) for n in names
            if os.path.isdir(os.path.join(root, n)) and os.path.exists(os.path.join(root, n, ".git"))]


def ignored(path):
    p = path.replace("\\", "/")
    if any(part in p for part in IGNORED_PATH_PARTS):
        return True
    return p.endswith(IGNORED_SUFFIXES)


def side_branch_commits(repo):
    """Commits on the OTHER local branches that GitHub does not hold (0.95.0). Only HEAD was counted before, so work
    on a side branch (a split branch, a worktree) left the light green while it lived on this PC only. A branch whose
    every commit GitHub already holds as an equal change (an old copy from before a history clean-up, which rewrote
    the commit ids) has nothing to save and is not counted; privacy-guard.py audit names those, since they still
    carry the old details."""
    ok, cur = git(["rev-parse", "--abbrev-ref", "HEAD"], repo)
    ok2, heads = git(["for-each-ref", "--format=%(refname:short)", "refs/heads"], repo)
    if not ok2:
        return 0
    total = 0
    for b in heads.splitlines():
        if not b or b == cur:
            continue
        ok, n = git(["rev-list", "--count", b, "--not", "--remotes"], repo)
        if not (ok and n.isdigit() and int(n)):
            continue
        up = "origin/" + b
        if not git(["rev-parse", "-q", "--verify", up], repo)[0]:
            up = "HEAD"
        ok, cherry = git(["cherry", up, b], repo)
        new = sum(1 for l in cherry.splitlines() if l.startswith("+")) if ok else int(n)
        total += new
    return total


def repo_state(repo):
    """(untracked, changed, unpushed, note, head) for one clone; note is a reason it could not be read."""
    ok, head = git(["rev-parse", "HEAD"], repo)
    head = head if ok else ""
    # --untracked-files=all: a new folder is otherwise listed collapsed ("dev-archive/"), and the
    # Inspector's notes inside it would count as a file never added
    ok, status = git(["--no-optional-locks", "status", "--porcelain=v1", "--untracked-files=all"], repo)
    if not ok:
        return 0, 0, 0, "could not read", head
    untracked = changed = 0
    for line in status.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        if ignored(path):
            continue
        if line.startswith("??"):
            untracked += 1
        else:
            changed += 1
    # commits on no remote branch at all: catches a branch that was never pushed, not only a stale upstream
    ok, n = git(["rev-list", "--count", "HEAD", "--not", "--remotes"], repo)
    unpushed = int(n) if ok and n.isdigit() else 0
    if ok:
        unpushed += side_branch_commits(repo)
    if ok:
        note = ""
    else:
        # 0.41.2: a clone that HAS a remote but cannot count against it is damaged (a fetch that died
        # half-way left a ref pointing at a commit that never arrived - seen 2026-10-01), and
        # "no remote" sent the reader looking in the wrong place
        has_remote, remotes = git(["remote"], repo)
        note = "damaged clone (run git fsck in it, or clone it afresh)" if has_remote and remotes.strip() else "no remote"
    return untracked, changed, unpushed, note, head


def scan_roots(roots):
    """One dict per clone in every root. The clones are read in parallel: 60 clones one after another
    took 63 s on 2026-10-01, far past a session-start hook's patience."""
    jobs = [(root, repo) for root in roots for repo in repos_in(root)]
    with ThreadPoolExecutor(max_workers=STATUS_WORKERS) as pool:
        states = list(pool.map(lambda j: repo_state(j[1]), jobs))
    rows = []
    for (root, repo), (u, c, p, note, head) in zip(jobs, states):
        rows.append({"root": root, "repo": repo, "name": os.path.basename(repo), "untracked": u,
                     "changed": c, "unpushed": p, "note": note, "head": head,
                     "problem": bool(u or c or p or note)})
    return rows


def plural(n, one, many):
    return "%d %s" % (n, one if n == 1 else many)


def problem_text(row, short=False):
    """What is wrong with one clone. The long form keeps the 0.39.0 wording the check line prints."""
    parts = []
    if row["untracked"]:
        parts.append(plural(row["untracked"], "file never added", "files never added") if short
                     else "%d file(s) never added" % row["untracked"])
    if row["changed"]:
        parts.append(plural(row["changed"], "change not committed", "changes not committed") if short
                     else "%d change(s) not committed" % row["changed"])
    if row["unpushed"]:
        parts.append(plural(row["unpushed"], "commit not pushed", "commits not pushed") if short
                     else "%d commit(s) not pushed" % row["unpushed"])
    if row["note"]:
        parts.append(row["note"])
    return ", ".join(parts)


def saved_report(roots, rows=None):
    """Returns (green, lines, repo_count)."""
    if rows is None:
        rows = scan_roots(roots)
    problems = ["  %s (%s): %s" % (r["name"], root_label(r["root"]), problem_text(r)) for r in rows if r["problem"]]
    count = len(rows)
    if not roots:
        return False, ["HANDOVER: could not run - no clone root found (is `board = ...` set in lanes.conf?)"], 0
    if not problems:
        return True, ["HANDOVER: SAVED - everything on this PC is on GitHub (%d repos in %d folder%s)."
                      % (count, len(roots), "" if len(roots) == 1 else "s")], count
    head = "HANDOVER: NOT SAVED - %d repo(s) hold work that is not on GitHub:" % len(problems)
    return False, [head] + problems, count


def snapshot_path(session):
    return os.path.join(os.path.dirname(os.path.abspath(conf_path())), SNAPSHOT_DIR,
                        "handover-" + re.sub(r"[^\w\-]", "_", session) + ".json")


def snapshot_write(session, rows):
    """Where every repo stood when the session started, so `close` can say what it pushed."""
    if not session:
        return
    heads = {norm(r["repo"]): r["head"] for r in rows if r["head"]}
    try:
        p = snapshot_path(session)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(heads, f)
    except OSError:
        pass


def snapshot_read(session):
    if not session:
        return None
    try:
        with open(snapshot_path(session), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def end_log_path():
    return os.path.join(os.path.dirname(snapshot_path("x")), END_LOG)


def end_log(word, session):
    """'began' / 'done' for a session's end report, so the next session can tell an end that was cut off from one
    that never started (0.94.2). Kept short; never raises."""
    sid = re.sub(r"[^\w\-]", "_", session or "-")
    try:
        p = end_log_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        try:
            with open(p, encoding="utf-8") as f:
                kept = f.read().splitlines()[-END_LOG_KEEP_LINES:]
        except OSError:
            kept = []
        kept.append("%s %s %s" % (word, sid, datetime.now().astimezone().strftime(TIME_FMT)))
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(kept) + "\n")
    except OSError:
        pass


def last_session_end(current):
    """How this PC's previous session ended, as one line, or "" when it reported its end in full. The previous session
    is the newest start snapshot that is not this one's."""
    folder = os.path.dirname(snapshot_path("x"))
    mine = os.path.basename(snapshot_path(current)) if current else ""
    try:
        snaps = [n for n in os.listdir(folder) if n.startswith("handover-") and n.endswith(".json") and n != mine]
    except OSError:
        return ""
    if not snaps:
        return ""
    prev = max(snaps, key=lambda n: os.path.getmtime(os.path.join(folder, n)))[len("handover-"):-len(".json")]
    try:
        with open(end_log_path(), encoding="utf-8") as f:
            words = [l.split()[0] for l in f.read().splitlines() if len(l.split()) > 1 and l.split()[1] == prev]
    except OSError:
        return ""    # no end has been logged on this PC yet (the first session after 0.94.2): nothing to compare
    if "done" in words:
        return ""
    if "began" in words:
        return ("HANDOVER: the last session on this PC began its end report but was closed before it finished, so the "
                "other PC was not told how it ended.")
    return ("HANDOVER: the last session on this PC ended without its end steps (the window was closed or the PC "
            "switched off). Whatever it left undone at the end - the save, notes, the front-page rows - is still "
            "undone: check them first.")


def board_ref(board):
    return "origin/main" if git(["rev-parse", "--verify", "-q", "origin/main"], board)[0] else "origin/HEAD"


def claims_held(board, me):
    """The LIVE claims on origin/main that carry this PC's label, as ['/pd demo', ...]."""
    if not board or not os.path.isdir(board):
        return []
    ok, out = git(["grep", "-H", "-e", "^LIVE: ", board_ref(board), "--", "status/"], board)
    held = []
    for line in (out.splitlines() if ok else []):
        m = LIVE_RE.match(line)
        if m and m.group(3) == me:
            held.append("%s %s" % (m.group(2), m.group(1)))
    return held


def age_text(when):
    s = (datetime.now(timezone.utc) - when.astimezone(timezone.utc)).total_seconds()
    if s < 0:
        s = 0
    if s < SECONDS_PER_HOUR:
        return "%d min ago" % (s // SECONDS_PER_MINUTE)
    if s < AGE_IN_HOURS_UP_TO_H * SECONDS_PER_HOUR:
        return "%d h ago" % (s // SECONDS_PER_HOUR)
    return "%d days ago" % (s // SECONDS_PER_DAY)


FETCH_REASON = ""   # "" / "unreachable" / "damaged", set by fetch_board (0.41.2)
LS_REMOTE_TIMEOUT_S = 20


def fetch_board(board):
    """Fetch the board. When that fails, say whether GitHub was unreachable or this PC's own copy is
    damaged (GitHub answers a plain listing, yet the fetch dies): the first is a network blip, the second
    stays red until someone repairs the clone, and the two were reported in the same words until 0.41.2."""
    global FETCH_REASON
    fetched, _ = git(["fetch", "-q", "origin"], board, timeout=FETCH_TIMEOUT_S)
    if fetched:
        FETCH_REASON = ""
    else:
        answers, _ = git(["ls-remote", "--exit-code", "--heads", "origin"], board, timeout=LS_REMOTE_TIMEOUT_S)
        FETCH_REASON = "damaged" if answers else "unreachable"
    return fetched, FETCH_REASON


def fetch_failed_line():
    if FETCH_REASON == "damaged":
        return ("HANDOVER: (GitHub answers, but this PC's copy of the board could not fetch: the clone is "
                "probably damaged. Run git fsck in it, or clone it afresh; the line above may be old)")
    return "HANDOVER: (GitHub could not be reached just now; the line above may be old)"


def parse_heartbeat(text):
    out = {}
    for line in text.splitlines():
        m = re.match(r"^\s*([a-z_]+)\s*=\s*(.*?)\s*$", line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def others(board, me, fetched=None):
    """What every other PC wrote on the board, read from GitHub (origin/main), never from this disk.
    Returns (fetched, [dict per other PC]); a dict with 'error' could not be read."""
    if fetched is None:
        fetched, _ = fetch_board(board)
    ref = board_ref(board)
    ok, listing = git(["ls-tree", "--name-only", ref, HEARTBEAT_DIR + "/"], board)
    names = [l for l in listing.splitlines() if l.endswith(".txt")] if ok else []
    out = []
    for path in names:
        machine = os.path.basename(path)[:-4]
        if machine == me:
            continue
        ok, text = git(["show", ref + ":" + path], board)
        hb = parse_heartbeat(text) if ok else {}
        try:
            when = datetime.strptime(hb.get("last_saved", ""), TIME_FMT)
        except ValueError:
            out.append({"machine": machine, "error": "has a report on the board that could not be read"})
            continue
        role = hb.get("role", "")
        # the file holds only the newest report, so the last END is read from the board's history (0.94.2)
        ok, last = git(["log", "-1", "--format=%cI", "--grep=^handover: .* end, ", ref, "--", path], board)
        ok2, every = git(["log", "--format=%cI", ref, "--", path], board)
        try:
            last_end = datetime.fromisoformat(last.strip()) if ok and last.strip() else None
            first = datetime.fromisoformat(every.splitlines()[-1].strip()) if ok2 and every.strip() else None
        except ValueError:
            last_end = first = None
        out.append({"machine": machine, "who": "%s (%s)" % (machine, role) if role else machine,
                    "when": when, "state": hb.get("state", "unknown"), "event": hb.get("event", ""),
                    "last_end": last_end, "first": first})
    return fetched, out


def pc_text(pc):
    """How another PC last reported, in words that do not call a session START an ending (they did until 0.94.2:
    "ended NOT SAVED" was printed for a PC whose sessions had not reported an end for 18 days)."""
    if pc.get("event") == "end":
        return "last session ended %s, %s" % (age_text(pc["when"]), pc["state"])
    state = pc["state"].replace("NOT SAVED:", "NOT SAVED at that point:", 1) if pc["state"].startswith("NOT SAVED") \
        else pc["state"] + " at that point"
    return "last seen starting a session %s, %s" % (age_text(pc["when"]), state)


def ends_missing(pc):
    """A warning when another PC keeps starting sessions but none of them reports an end: its sessions stop with the
    window closed or the PC switched off, so whatever a session does last (the save, the front page, the notes) is
    skipped there. Found 2026-10-28: the home PC, 41 starts and 0 ends in 18 days, and its project rows weeks behind."""
    last_end = pc.get("last_end") or pc.get("first")    # a PC new to the board is measured from its first report
    if pc.get("event") == "end" or not last_end:
        return ""
    if (pc["when"] - last_end).total_seconds() < ENDS_MISSING_DAYS * SECONDS_PER_DAY:
        return ""
    last_end = pc.get("last_end")
    since = "since %s" % last_end.strftime("%Y-%m-%d") if last_end else "on the board yet"
    return ("%s has not reported a session end %s: its sessions stop without their end steps (window closed or PC "
            "off), so check its saves, notes and front-page rows" % (pc["machine"], since))


def others_report(board, me):
    if not board or not os.path.isdir(board):
        return ["HANDOVER: no board to read the other PC from."]
    fetched, pcs = others(board, me)
    lines = []
    for pc in pcs:
        if "error" in pc:
            lines.append("HANDOVER: %s %s." % (pc["machine"], pc["error"]))
        else:
            lines.append("HANDOVER: %s %s (%s)." % (pc["who"], pc_text(pc), pc["when"].strftime("%Y-%m-%d %H:%M")))
            if ends_missing(pc):
                lines.append("HANDOVER: ⚠️ " + ends_missing(pc) + ".")
    if not lines:
        lines.append("HANDOVER: no other PC has reported on the board yet.")
    if not fetched:
        lines.append(fetch_failed_line())
    return lines


def inspector_cell(session):
    """The Inspector's own short count for this session (tools/inspector.py), or why there is none."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        import inspector
        return inspector.session_cells(session)
    except Exception:  # noqa: BLE001 - the box must print whatever the Inspector's state
        return "not available on this PC"


def close_box(conf, session):
    """The close-out box: one markdown table that ends every lane's write-up. Returns (green, lines)."""
    roots = roots_from(conf)
    board = conf.get("board", "")
    me = conf.get("machine_name") or conf.get("role") or "PC"
    rows = scan_roots(roots)
    green, _, count = saved_report(roots, rows)
    problems = [r for r in rows if r["problem"]]
    if not roots:
        head = "| 🔦 **UNKNOWN** | **NO CLONE ROOT FOUND (IS `board = ...` SET IN lanes.conf?)** |"
    elif green:
        head = "| 🔦 **SAVED** | **EVERYTHING ON THIS PC IS ON GITHUB** |"
    elif len(problems) == 1:
        head = "| 🔦 **NOT SAVED** | **%s: %s** |" % (problems[0]["name"].upper(), problem_text(problems[0], short=True).upper())
    else:
        head = "| 🔦 **NOT SAVED** | **%d REPOS HOLD WORK THAT IS NOT ON GITHUB** |" % len(problems)
    lines = [head, "| --- | --- |"]

    def shown(r):
        return r["name"] if root_label(r["root"]) == "live root" else "%s (%s)" % (r["name"], root_label(r["root"]))

    snap = snapshot_read(session)
    pushed = []
    for r in rows:
        before = (snap or {}).get(norm(r["repo"]))
        if r["problem"] or not before or before == r["head"]:
            continue
        # the handover light's own board reports are not this session's work, so they are not counted
        ok, n = git(["rev-list", "--count", "--invert-grep", "--grep=^handover: ", before + ".." + r["head"]], r["repo"])
        n = int(n) if ok and n.isdigit() else 0
        if ok and n == 0:
            continue
        pushed.append(r)
        lines.append("| 📦 %s | pushed%s |" % (shown(r), " · " + plural(n, "new commit", "new commits") if n else ""))
    for r in problems:
        lines.append("| 📦 %s | ⚠️ %s |" % (shown(r), problem_text(r, short=True)))
    rest = count - len(pushed) - len(problems)
    if roots and rest > 0:
        word = "the other" if (pushed or problems) else "all"
        lines.append("| 📦 %s %s | nothing to push |" % (word, plural(rest, "repo", "repos")))
    profile = profile_cell(conf, pushed, snap)
    if profile:
        lines.append("| 🪧 Front page | %s |" % profile)
    lines.append("| 🔍 Inspector | %s |" % inspector_cell(session))
    has_board = bool(board) and os.path.isdir(board)
    fetched = fetch_board(board)[0] if has_board else False
    held = claims_held(board, me) if has_board else []
    lines.append("| 🔒 Claim | %s |" % (", ".join(h + " still held" for h in held) + " ⚠️" if held else "none held"))
    if has_board:
        fetched, pcs = others(board, me, fetched)
        for pc in pcs:
            if "error" in pc:
                lines.append("| 🖥️ %s | %s |" % (pc["machine"], pc["error"]))
            else:
                lines.append("| 🖥️ %s | %s |" % (pc["who"], pc_text(pc)))
                if ends_missing(pc):
                    lines.append("| 🖥️ %s | ⚠️ %s |" % (pc["machine"], ends_missing(pc)))
        if not pcs:
            lines.append("| 🖥️ Other PC | has not reported yet |")
        if not fetched:
            if FETCH_REASON == "damaged":
                lines.append("| 🖥️ GitHub | answers, but this PC's copy of the board could not fetch: probably a damaged clone (git fsck) |")
            else:
                lines.append("| 🖥️ GitHub | could not be reached just now, the row above may be old |")
    else:
        lines.append("| 🖥️ Other PC | no board to read it from |")
    if green and roots and not early_summary_on():
        # 0.63.0: without the early summary nothing keeps the conversation short, so say when it is safe
        lines.append("| 🧹 Clear | SAVED - safe to /clear |")
    return green, lines


def profile_rows(page):
    """[(repo, folder, 'MM-DD', title)] of the front page's table rows: each links to a repo (or a folder of one)
    and carries the day it was last refreshed"""
    link = re.compile(r"\]\(https://github\.com/[\w.-]+/([\w.-]+)(?:/tree/[^/)]+/([^)#]+))?\)", re.I)
    out = []
    try:
        with open(page, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return out
    for line in lines:
        m = link.search(line)
        if not line.startswith("| ") or not m:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        mmdd = next((c for c in cells if re.fullmatch(r"\d\d-\d\d", c)), None)
        if mmdd:
            out.append((m.group(1).lower(), (m.group(2) or "").strip("/"), mmdd, cells[0].strip("*")))
    return out


def profile_cell(conf, pushed, snap):
    """The close-out box's front-page row (0.94.2): a repo this session pushed real work to, whose front-page row is
    not dated today. The rule says to refresh the row after any commit; nothing checked it, a check at session END
    never ran on a PC whose sessions stop with the window closed, and on 2026-10-28 rows were found weeks behind
    their projects. The box is printed in every write-up, so this is where it is caught. "" when nothing applies."""
    page = os.environ.get("LANES_FRONTPAGE") or conf.get("frontpage", "")
    if not page or not pushed:
        return ""
    folder = page if os.path.isdir(page) else os.path.dirname(page)
    rows = profile_rows(os.path.join(folder, "README.md"))
    if not rows:
        return ""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from gu_texts import NOT_WORK
    except ImportError:
        NOT_WORK = ()
    today = datetime.now().strftime("%m-%d")
    behind, fine = [], 0
    for r in pushed:
        before = (snap or {}).get(norm(r["repo"]))
        for repo, sub, mmdd, title in rows:
            if repo != r["name"].lower():
                continue
            spec = ["--", sub or "."] + [":(exclude,glob)%s" % p for p in NOT_WORK]
            ok, n = git(["rev-list", "--count", "--invert-grep", "--grep=^handover: ", before + ".." + r["head"]]
                        + spec, r["repo"])
            if not (ok and n.isdigit() and int(n)):
                continue
            if mmdd == today:
                fine += 1
            else:
                behind.append("\"%s\" (%s)" % (title[:PROFILE_TITLE_CHARS], mmdd))
    if behind:
        return "⚠️ this session's work is not on its row yet: %s. Refresh the row, its INDEX.json stage, and Recent " \
               "Activity if it moved forward" % ", ".join(behind)
    return "%s refreshed today" % plural(fine, "row", "rows") if fine else ""


def early_summary_on():
    try:
        import compact  # lazy: compact.py imports this module
        return compact.early_summary_on()
    except Exception:  # noqa: BLE001 - unknown means offer the safe-to-clear row
        return False


def write_heartbeat(board, me, role, event, green, problem_lines):
    """One small file on the board, committed on its own and pushed. Returns a one-line result."""
    if not board or not os.path.isdir(board):
        return "HANDOVER: not reported - no board."
    hb_dir = os.path.join(board, HEARTBEAT_DIR)
    path = os.path.join(hb_dir, me + ".txt")
    if event == "start" and os.path.isfile(path):
        try:
            if (datetime.now().timestamp() - os.path.getmtime(path)) < START_WRITE_MIN_AGE_S:
                return ""
        except OSError:
            pass
    os.makedirs(hb_dir, exist_ok=True)
    state = "SAVED" if green else "NOT SAVED: " + "; ".join(l.strip() for l in problem_lines[1:])[:STATE_MAX_CHARS]
    now = datetime.now().astimezone().strftime(TIME_FMT)
    body = ("# Written by the lanes plugin (tools/handover.py), one file per PC. Never edited by hand.\n"
            "machine = %s\nrole = %s\nlast_saved = %s\nevent = %s\nstate = %s\n" % (me, role, now, event, state))
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(body)
    except OSError:
        return "HANDOVER: not reported - could not write the board file."
    rel = HEARTBEAT_DIR + "/" + me + ".txt"
    git(["add", "--", rel], board)
    ok, _ = git(["commit", "-q", "-m", "handover: %s (%s) %s, %s" % (me, role, event, "SAVED" if green else "NOT SAVED"), "--", rel], board)
    if not ok:
        return ""   # nothing changed since the last report
    git(["pull", "-q", "--rebase", "--autostash"], board, timeout=FETCH_TIMEOUT_S)
    ok, _ = git(["push", "-q"], board, timeout=PUSH_TIMEOUT_S)
    return "HANDOVER: this PC (%s) reported %s on the board." % (me, "SAVED" if green else "NOT SAVED") if ok \
        else "HANDOVER: this PC's report could NOT be pushed to the board (GitHub unreachable?)."


def fresh_report(root, pull):
    repos = repos_in(root)
    if not repos:
        return False, ["HANDOVER: no repos found in that root."]
    behind, failed, pulled = [], [], []
    for repo in repos:
        ok, _ = git(["fetch", "-q"], repo, timeout=FETCH_TIMEOUT_S)
        if not ok:
            failed.append(os.path.basename(repo)); continue
        ok, n = git(["rev-list", "--count", "HEAD..@{u}"], repo)
        if ok and n.isdigit() and int(n) > 0:
            if pull and git(["pull", "-q", "--ff-only"], repo, timeout=FETCH_TIMEOUT_S)[0]:
                pulled.append(os.path.basename(repo))
            else:
                behind.append("%s (%d)" % (os.path.basename(repo), int(n)))
    lines = []
    if not behind and not failed:
        lines.append("HANDOVER: FRESH - the %s has everything GitHub has (%d repos%s)."
                     % (root_label(root), len(repos), ", %d pulled now" % len(pulled) if pulled else ""))
    else:
        if behind:
            lines.append("HANDOVER: STALE - %d repo(s) in the %s are behind GitHub: %s" % (len(behind), root_label(root), ", ".join(behind)))
        if pulled:
            lines.append("HANDOVER: pulled now: " + ", ".join(pulled))
        if failed:
            lines.append("HANDOVER: could not fetch: " + ", ".join(failed))
    return not behind and not failed, lines


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # a Windows console's code page has no emoji
    except (AttributeError, ValueError):
        pass
    mode = argv[0] if argv else "check"
    flags = [a for a in argv[1:] if a.startswith("--")]
    args = [a for a in argv[1:] if not a.startswith("--")]
    session = os.environ.get("CLAUDE_CODE_SESSION_ID") or ""
    for f in flags:
        if f.startswith("--session="):
            session = f[len("--session="):]
    conf = read_conf()
    board = conf.get("board", "")
    me = conf.get("machine_name") or conf.get("role") or "PC"
    role = conf.get("role", "")
    if mode == "close":
        green, lines = close_box(conf, session)
        print("\n".join(lines))
        return 0 if green else (1 if roots_from(conf) else 2)
    if mode == "fresh":
        root = args[0] if args else (os.path.dirname(os.path.abspath(board)) if board else "")
        if not root or not os.path.isdir(root):
            print("HANDOVER: could not run - give a clone root, or set `board = ...` in lanes.conf"); return 2
        green, lines = fresh_report(root, "--pull" in flags)
        print("\n".join(lines)); return 0 if green else 1
    if mode not in ("check", "start", "end"):
        print(__doc__); return 2
    if mode == "end":
        end_log("began", session)
    roots = roots_from(conf)
    rows = scan_roots(roots)
    green, saved_lines, _ = saved_report(roots, rows)
    lines = list(saved_lines)
    if mode == "start":
        prev = last_session_end(session)    # read before this session's own snapshot is the newest
        if prev:
            lines.append(prev)
        snapshot_write(session, rows)
    if mode in ("start", "end"):
        lines += others_report(board, me)
        if "--write" in flags:
            r = write_heartbeat(board, me, role, mode, green, saved_lines)
            if r:
                lines.append(r)
    if mode == "end":
        end_log("done", session)
    print("\n".join(lines))
    return 0 if green else (1 if roots else 2)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
