#!/usr/bin/env python3
"""handover.py - the handover light: is it safe to carry on from the other PC?

    python handover.py check            SAVED / NOT SAVED: is every clone on this PC fully on GitHub?
    python handover.py start [--write]  the same, plus when each OTHER PC last saved and how it ended;
                                        --write also reports this PC on the board (at most once an hour)
    python handover.py end   [--write]  the same check at the end of a session; --write reports it on
                                        the board every time, so the other PC is told how this one ended
    python handover.py fresh [ROOT]     fetch every repo in one clone root and say which are behind GitHub
                                        (--pull brings them up to date; fast-forward only)

Exit 0 = green, 1 = red (something is not on GitHub, or a repo is behind), 2 = could not run.

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
  (hooks/handover-end), and every lane's write-up ends with its first line. No line, no trust.

WHAT COUNTS AS NOT SAVED
  In every clone of every root: a file never added, a change not committed, a commit on no remote
  branch at all. The Inspector's local notes (an `inspector/` folder) and Python caches are the two
  things kept on one PC on purpose, so they do not count.

WHAT IT NEVER DOES
  It never pulls, merges or resets anything in `check`, `start` or `end`. The one write is one small
  file on the board, `handover/<machine>.txt`, committed on its own and pushed; a refused push is
  reported, never forced. Output names repos, roots by lane and PCs by their plugin names only.
"""
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

ROOT_SUFFIXES = ("-pd", "-gr", "-sr", "-gs")      # the lane roots beside the live one (PROTOCOL section 3)
IGNORED_PATH_PARTS = ("inspector/", "__pycache__/")  # kept on one PC on purpose
IGNORED_SUFFIXES = (".pyc",)
HEARTBEAT_DIR = "handover"
START_WRITE_MIN_AGE_S = 3600                        # a start report at most once an hour (fewer commits)
GIT_TIMEOUT_S = 30
FETCH_TIMEOUT_S = 90
PUSH_TIMEOUT_S = 60
TIME_FMT = "%Y-%m-%d %H:%M %z"


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
    for key in ("root", "lane_roots"):
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


def repo_state(repo):
    """(untracked, changed, unpushed, note) for one clone; note is a reason it could not be read."""
    # --untracked-files=all: a new folder is otherwise listed collapsed ("dev-archive/"), and the
    # Inspector's notes inside it would count as a file never added
    ok, status = git(["--no-optional-locks", "status", "--porcelain=v1", "--untracked-files=all"], repo)
    if not ok:
        return 0, 0, 0, "could not read"
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
    note = "" if ok else "no remote"
    return untracked, changed, unpushed, note


def saved_report(roots):
    """Returns (green, lines, repo_count). The clones are read in parallel: 60 clones one after another
    took 63 s on 2026-10-01, far past a session-start hook's patience."""
    jobs = [(root, repo) for root in roots for repo in repos_in(root)]
    with ThreadPoolExecutor(max_workers=STATUS_WORKERS) as pool:
        states = list(pool.map(lambda j: repo_state(j[1]), jobs))
    problems, count = [], 0
    for (root, repo), (u, c, p, note) in zip(jobs, states):
        count += 1
        if True:
            if u or c or p or note:
                parts = []
                if u: parts.append("%d file(s) never added" % u)
                if c: parts.append("%d change(s) not committed" % c)
                if p: parts.append("%d commit(s) not pushed" % p)
                if note: parts.append(note)
                problems.append("  %s (%s): %s" % (os.path.basename(repo), root_label(root), ", ".join(parts)))
    if not roots:
        return False, ["HANDOVER: could not run - no clone root found (is `board = ...` set in lanes.conf?)"], 0
    if not problems:
        return True, ["HANDOVER: SAVED - everything on this PC is on GitHub (%d repos in %d folder%s)."
                      % (count, len(roots), "" if len(roots) == 1 else "s")], count
    head = "HANDOVER: NOT SAVED - %d repo(s) hold work that is not on GitHub:" % len(problems)
    return False, [head] + problems, count


def age_text(when):
    s = (datetime.now(timezone.utc) - when.astimezone(timezone.utc)).total_seconds()
    if s < 0:
        s = 0
    if s < SECONDS_PER_HOUR:
        return "%d min ago" % (s // SECONDS_PER_MINUTE)
    if s < AGE_IN_HOURS_UP_TO_H * SECONDS_PER_HOUR:
        return "%d h ago" % (s // SECONDS_PER_HOUR)
    return "%d days ago" % (s // SECONDS_PER_DAY)


def parse_heartbeat(text):
    out = {}
    for line in text.splitlines():
        m = re.match(r"^\s*([a-z_]+)\s*=\s*(.*?)\s*$", line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def others_report(board, me):
    """What every other PC wrote on the board, read from GitHub (origin/main), never from this disk."""
    if not board or not os.path.isdir(board):
        return ["HANDOVER: no board to read the other PC from."]
    fetched, _ = git(["fetch", "-q", "origin"], board, timeout=FETCH_TIMEOUT_S)
    ref = "origin/main" if git(["rev-parse", "--verify", "-q", "origin/main"], board)[0] else "origin/HEAD"
    ok, listing = git(["ls-tree", "--name-only", ref, HEARTBEAT_DIR + "/"], board)
    names = [l for l in listing.splitlines() if l.endswith(".txt")] if ok else []
    lines = []
    for path in names:
        machine = os.path.basename(path)[:-4]
        if machine == me:
            continue
        ok, text = git(["show", ref + ":" + path], board)
        hb = parse_heartbeat(text) if ok else {}
        try:
            when = datetime.strptime(hb.get("last_saved", ""), TIME_FMT)
        except ValueError:
            lines.append("HANDOVER: %s has a report on the board that could not be read." % machine)
            continue
        role = hb.get("role", "")
        who = "%s (%s)" % (machine, role) if role else machine
        state = hb.get("state", "unknown")
        lines.append("HANDOVER: %s last saved %s, %s, and ended %s." % (who, when.strftime("%Y-%m-%d %H:%M"), age_text(when), state))
    if not lines:
        lines.append("HANDOVER: no other PC has reported on the board yet.")
    if not fetched:
        lines.append("HANDOVER: (GitHub could not be reached just now; the line above may be old)")
    return lines


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
    mode = argv[0] if argv else "check"
    flags = [a for a in argv[1:] if a.startswith("--")]
    args = [a for a in argv[1:] if not a.startswith("--")]
    conf = read_conf()
    board = conf.get("board", "")
    me = conf.get("machine_name") or conf.get("role") or "PC"
    role = conf.get("role", "")
    if mode == "fresh":
        root = args[0] if args else (os.path.dirname(os.path.abspath(board)) if board else "")
        if not root or not os.path.isdir(root):
            print("HANDOVER: could not run - give a clone root, or set `board = ...` in lanes.conf"); return 2
        green, lines = fresh_report(root, "--pull" in flags)
        print("\n".join(lines)); return 0 if green else 1
    if mode not in ("check", "start", "end"):
        print(__doc__); return 2
    roots = roots_from(conf)
    green, saved_lines, _ = saved_report(roots)
    lines = list(saved_lines)
    if mode in ("start", "end"):
        lines += others_report(board, me)
        if "--write" in flags:
            r = write_heartbeat(board, me, role, mode, green, saved_lines)
            if r:
                lines.append(r)
    print("\n".join(lines))
    return 0 if green else (1 if roots else 2)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
