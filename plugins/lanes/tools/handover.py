#!/usr/bin/env python3
"""handover.py - the handover light: is it safe to carry on from the other PC?

    python handover.py check            SAVED / NOT SAVED: is every clone on this PC fully on GitHub?
    python handover.py start [--write]  the same, plus when each OTHER PC last saved and how it ended;
                                        --write also reports this PC on the board (at most once an hour)
    python handover.py end   [--write]  the same check at the end of a session; --write reports it on
                                        the board every time, so the other PC is told how this one ended
    python handover.py fresh [ROOT]     fetch every repo in one clone root and say which are behind GitHub
    python handover.py refresh          fetch every copy that has not looked at GitHub for a day (the end helper runs it)
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
import time
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from git_leftovers import leftovers  # noqa: E402
import lanes_version  # noqa: E402

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
STARTED_KEY = "_started"           # the snapshot's note of when the session began (0.99.2)
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
    # The builds repo lives outside every clone root (`builds =`), so a session that saved builds there never had it
    # in the box (Run 5 C6, Run 6 F15: the home PC pushed builds and the box did not list it).
    b = conf.get("builds", "").strip().strip('"')
    if b and os.path.isdir(b) and os.path.exists(os.path.join(b, ".git")):
        found.append(b)
    for key in ("root", "lane_roots", "gd_root"):
        for p in re.split(r"[,\s]+", conf.get(key, "")):
            if p and os.path.isdir(p):
                found.append(p)
                # The lane roots sit beside the live `root` too. Looking only beside the board missed them when
                # the board is cloned elsewhere (home PC: board in the home folder, so a file left in the /pd
                # root never turned the light red; two-PC test Run 4, S2).
                if key == "root":
                    for s in ROOT_SUFFIXES:
                        if os.path.isdir(p.rstrip("\\/") + s):
                            found.append(p.rstrip("\\/") + s)
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
    if os.path.exists(os.path.join(root, ".git")):   # a single repo named on its own (the builds repo, `builds =`)
        return [root]
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


OLD_HISTORY_MARK = "on the old history from before a GitHub clean-up"
OLD_HISTORY_NOTE = OLD_HISTORY_MARK + " (%d commits, every one on GitHub under a new id): move it with the clean-up move tool"


def old_count(note):
    m = re.search(r"\((\d+) commits, every one on GitHub", note or "")
    return int(m.group(1)) if m else 0


def all_on_upstream(repo, up):
    """True when every commit only this copy has is on GitHub under a new id: the same change (git cherry), or, for a
    commit the clean-up edited (home paths taken out of its files, so the change is no longer equal), one with the same
    author time and title. Home PC, Run 6 (2026-11-06): the Alice Gold Digger copy, 40 commits, was not recognised by
    git cherry alone. Weak spot, accepted: a pushed commit amended later keeps its author time and title too."""
    ok, cherry = git(["cherry", up, "HEAD"], repo)
    if not ok or not cherry.strip():
        return False
    left = [l[2:].strip() for l in cherry.splitlines() if l.startswith("+")]
    if not left:
        return True
    ok, theirs = git(["log", "--format=%at %s", up], repo)
    if not ok:
        return False
    known = set(theirs.splitlines())
    for sha in left:
        ok, mine = git(["log", "-1", "--format=%at %s", sha], repo)
        if not ok or mine.strip() not in known:
            return False
    return True


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
    old_history = 0
    if unpushed:
        # Run 6 (2026-11-06): a copy still on the history from before a GitHub clean-up shows its old commits as "not
        # pushed", yet GitHub holds every one of them as an equal change under a new id. Nothing to save there; it is
        # named in the box instead (move it with the clean-up move tool), and never turns the light red.
        cok, cur = git(["rev-parse", "--abbrev-ref", "HEAD@{upstream}"], repo)
        up = cur if cok and cur else "origin/HEAD"
        if git(["rev-parse", "-q", "--verify", up], repo)[0] and all_on_upstream(repo, up):
            old_history, unpushed = unpushed, 0
    if ok:
        unpushed += side_branch_commits(repo)
    if ok:
        note = leftovers(repo)  # a save cut off half-way: a lock file or a pull left open (two-PC test 4)
        if old_history:
            hist = OLD_HISTORY_NOTE % old_history
            note = (note + "; " + hist) if note else hist
        # 0.99.0 (release audit): a stash lives on this PC only and was invisible here. One from a 2026-10-23 tidy-up
        # sat unseen for ten days. A failed `pull --autostash` leaves one too.
        sok, stashes = git(["stash", "list"], repo)
        n_stash = len(stashes.splitlines()) if sok and stashes.strip() else 0
        if n_stash:
            stash_note = "%d stash(es) kept on this PC only (git stash list)" % n_stash
            note = (note + "; " + stash_note) if note else stash_note
    else:
        # 0.41.2: a clone that HAS a remote but cannot count against it is damaged (a fetch that died
        # half-way left a ref pointing at a commit that never arrived - seen 2026-10-01), and
        # "no remote" sent the reader looking in the wrong place
        has_remote, remotes = git(["remote"], repo)
        note = "damaged clone (run git fsck in it, or clone it afresh)" if has_remote and remotes.strip() else "no remote"
    return untracked, changed, unpushed, note, head


HOURS_PER_DAY = 24
PUSH_ATTEMPTS = 3   # the end report is retried this often when the other PC pushed first
STALE_VIEW_H = 24   # a copy that last looked at GitHub longer ago than this is named in the box (Run 5 D7)


def view_age_h(repo):
    """hours since this copy last fetched from GitHub (its FETCH_HEAD), or None when it never did / cannot tell"""
    path = os.path.join(repo, ".git", "FETCH_HEAD")
    try:
        return (time.time() - os.path.getmtime(path)) / 3600.0
    except OSError:
        return None


def stale_view_cell(rows):
    """'' or the box's warning that SAVED was measured against an old view of GitHub. Run 5 D7 (2026-11-06): a copy
    that had not fetched since the history clean-up looked SAVED while 134 commits apart from GitHub."""
    old = []
    for r in rows:
        age = view_age_h(r["repo"])
        if age is not None and age > STALE_VIEW_H:
            label = root_label(r["root"])
            old.append((age, r["name"] if label == "live root" else "%s in the %s" % (r["name"], label)))
    if not old:
        return ""
    old.sort(reverse=True)
    age, name = old[0]
    return ("⚠️ %s last looked at GitHub over a day ago (oldest: %s, %d days), so SAVED is measured against what they "
            "last saw; `handover.py fresh` looks again" % (plural(len(old), "copy", "copies"), name, int(age // HOURS_PER_DAY)))


def refresh_views(roots):
    """fetch (never pull) every copy whose view of GitHub is older than STALE_VIEW_H, in parallel. Run by the end
    helper after the window has closed, so the next box measures SAVED against GitHub as it is (Run 5 D7). A fetch
    only moves this copy's record of GitHub; it never touches the files or a branch, so it is safe beside any lane."""
    old = [repo for root in roots for repo in repos_in(root)
           if (view_age_h(repo) or STALE_VIEW_H + 1) > STALE_VIEW_H]

    def one(repo):
        return git(["fetch", "-q", "origin"], repo, timeout=FETCH_TIMEOUT_S)[0]
    with ThreadPoolExecutor(max_workers=STATUS_WORKERS) as pool:
        done = list(pool.map(one, old))
    return len(old), sum(1 for d in done if d)


HELD_H = 3                 # hooks/project-guard.py: a project a session wrote into this recently is left alone
LEVEL_CLONES_MAX = 5       # repos new on GitHub that one run copies to this PC; the rest wait for the next run
LEVEL_CLONE_TIMEOUT_S = 300
LEVEL_NAMED = 8            # repo names spelled out in the result line


def held_projects():
    """names of the projects a session on this PC is writing into now (the project guard's holds, HELD_H fresh)"""
    folder = os.path.join(os.environ.get("LANES_STATE_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "lanes"),
                          "projects-held")
    out = set()
    try:
        names = os.listdir(folder)
    except OSError:
        return out
    for n in names:
        try:
            with open(os.path.join(folder, n), encoding="utf-8") as f:
                last = float(json.load(f).get("last", 0))
        except (OSError, ValueError, AttributeError, TypeError):
            continue
        if time.time() - last < HELD_H * 3600:
            out.add(n[:-5].lower() if n.endswith(".json") else n.lower())
    return out


def level_copies(roots):
    """Bring every copy that is only BEHIND GitHub up to it (0.107.0). [(name, root label, commits)] of those moved.

    Why: the copies on a PC that mostly reads fall behind without a word. On 2026-11-10 the dev PC, which had done
    little but receive the home PC's work for a week, had 50 of the 66 repos in its live root behind GitHub (one by
    213 commits), so every note, tool and Inspector hint read there was days old. Nothing pulled them: each lane
    pulls only what it works on.

    Safe by construction. A copy is moved only when it is on a branch that follows GitHub, has nothing of its own
    that GitHub lacks, no changed or staged file, and no git step half done; then it is fast-forwarded to what the
    last fetch saw (no network here: the end helper's "GitHub looked at again" step runs just before). Left alone:
    a project a session on this PC is writing into (the project guard's hold), and the folder Lanes itself is loaded
    from (moving that is a Lanes update, which asks first)."""
    held = held_projects()
    here = norm(os.path.abspath(__file__))
    todo = []
    for root in roots:
        for repo in repos_in(root):
            if os.path.basename(repo).lower() in held or here.startswith(norm(repo).rstrip("\\/") + os.sep):
                continue
            todo.append((repo, root))

    def one(item):
        repo, root = item
        gitdir = os.path.join(repo, ".git")
        if any(os.path.exists(os.path.join(gitdir, n)) for n in ("index.lock", "MERGE_HEAD", "rebase-merge",
                                                                  "rebase-apply")):
            return None
        ok, counts = git(["rev-list", "--left-right", "--count", "HEAD...@{u}"], repo)
        parts = counts.split() if ok else []
        if len(parts) != 2 or not parts[1].isdigit() or parts[0] != "0" or int(parts[1]) == 0:
            return None                              # no branch that follows GitHub, work of its own, or level
        ok, st = git(["status", "--porcelain", "--untracked-files=no"], repo)
        if not ok or st.strip():
            return None
        if not git(["merge", "-q", "--ff-only", "@{u}"], repo, timeout=FETCH_TIMEOUT_S)[0]:
            return None
        return (os.path.basename(repo), root_label(root), int(parts[1]))
    with ThreadPoolExecutor(max_workers=STATUS_WORKERS) as pool:
        return [r for r in pool.map(one, todo) if r]


def account_repos(owner):
    """[(name, clone address)] of the account's own repos on GitHub (not forks, not archived), or None when it cannot
    be asked. LANES_LEVEL_REPOS (a JSON list of [name, address]) stands in for GitHub in the tests."""
    fake = os.environ.get("LANES_LEVEL_REPOS")
    if fake:
        try:
            return [tuple(x) for x in json.loads(fake)]
        except ValueError:
            return None
    try:
        r = subprocess.run(["gh", "repo", "list", owner, "--limit", "1000", "--json", "name,isFork,isArchived,url"],
                           capture_output=True, text=True, timeout=FETCH_TIMEOUT_S, encoding="utf-8", errors="replace")
        return [(x["name"], x["url"]) for x in json.loads(r.stdout) if not x.get("isFork") and not x.get("isArchived")] \
            if r.returncode == 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def clone_missing(conf, roots):
    """Copy to the live root the repos GitHub has that it lacks (the other PC made a new project). (cloned, waiting)."""
    owner = conf.get("texts_owner", "").strip()
    if not roots or not (owner or os.environ.get("LANES_LEVEL_REPOS")):
        return [], 0
    listed = account_repos(owner)
    if not listed:
        return [], 0
    live = roots[0]
    have = {os.path.basename(r).lower() for r in repos_in(live)}
    have |= {n.lower() for n in os.listdir(live)}       # a folder of that name that is not a clone is left alone too
    missing = [(n, url) for n, url in listed if n.lower() not in have]
    cloned = []
    for name, url in missing[:LEVEL_CLONES_MAX]:
        try:
            r = subprocess.run(["git", "clone", "-q", url, os.path.join(live, name)], capture_output=True,
                               timeout=LEVEL_CLONE_TIMEOUT_S)
            if r.returncode == 0:
                cloned.append(name)
        except (OSError, subprocess.TimeoutExpired):
            pass
    return cloned, len(missing) - len(cloned)


def level_report(conf):
    roots = roots_from(conf)
    moved = level_copies(roots)
    cloned, waiting = clone_missing(conf, roots)
    if not moved and not cloned and not waiting:
        return "HANDOVER: every copy that could be brought level with GitHub already is."
    bits = []
    if moved:
        names = ", ".join("%s%s (%d)" % (n, "" if lab == "live root" else " in the " + lab, c)
                          for n, lab, c in sorted(moved, key=lambda m: -m[2])[:LEVEL_NAMED])
        more = " and %d more" % (len(moved) - LEVEL_NAMED) if len(moved) > LEVEL_NAMED else ""
        bits.append("%s brought level with GitHub: %s%s" % (plural(len(moved), "copy", "copies"), names, more))
    if cloned:
        bits.append("new on GitHub, copied to this PC: " + ", ".join(cloned))
    if waiting:
        bits.append("%s more on GitHub with no copy here yet" % plural(waiting, "repo", "repos"))
    return "HANDOVER: " + "; ".join(bits) + "."


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
                     "problem": bool(u or c or p or (note and note != OLD_HISTORY_NOTE % old_count(note))),
                     "old_history": bool(note and OLD_HISTORY_MARK in note)})
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
    old = snapshot_read(session)
    if old and isinstance(old.get(STARTED_KEY), int):
        # 0.103.0: the same session starting again (a resume, or the start hooks after an early summary) keeps its first
        # snapshot: re-writing it made the box forget every commit before the summary (Run 5 day, 2026-11-06)
        return
    heads = {norm(r["repo"]): r["head"] for r in rows if r["head"]}
    heads[STARTED_KEY] = int(time.time())   # 0.99.2: only commits made on this PC after this count as this session's
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


def session_started(session, snap):
    """When the session began: kept in the snapshot since 0.99.2, else the snapshot file's own time."""
    if snap and isinstance(snap.get(STARTED_KEY), int):
        return snap[STARTED_KEY]
    try:
        return int(os.path.getmtime(snapshot_path(session)))
    except OSError:
        return None


def session_commits(session):
    """The commits git's post-commit hook noted for this session (privacy-guard.py's hooks, 2026-11-05), or None
    when it noted none: then every commit made on this PC since the session began counts, as before. Two sessions
    on one PC committing in the same clone were each shown the other's commits (home PC, 2026-11-05)."""
    path = os.environ.get("LANES_SESSION_COMMITS") or os.path.join(
        os.path.expanduser("~"), ".claude", "lanes", "githooks", "session-commits.txt")
    if not session:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            mine = {p[1] for p in (l.rstrip("\r\n").split("\t") for l in f) if len(p) == 2 and p[0] == session}
    except OSError:
        return None
    return mine or None


def notes_commits(repo):
    """Whether git's post-commit hook that notes a session's commits runs in this clone. A clone with its own hook folder
    (core.hooksPath) hides the machine-wide one unless its post-commit calls it: the board repo's does not, so its
    commits were never noted and the box left them out (Run 5 C6, n=3, 2026-11-06)."""
    ok, hp = git(["config", "core.hooksPath"], repo)
    if not ok or not hp.strip():
        return False
    hp = hp.strip()
    ok, top = git(["rev-parse", "--show-toplevel"], repo)
    full = os.path.normpath(os.path.join(top.strip() if ok else repo, os.path.expanduser(hp)))
    lanes_hooks = os.path.normpath(os.path.join(os.path.expanduser("~"), ".claude", "lanes", "githooks"))
    if os.path.normcase(full) == os.path.normcase(lanes_hooks):
        return True
    try:
        with open(os.path.join(full, "post-commit"), encoding="utf-8", errors="replace") as f:
            return "lanes/githooks" in f.read()
    except OSError:
        return False


def made_here(repo, since):
    """Commits made in this clone since `since` (unix time), newest first, from its HEAD reflog: a commit, an amend or a
    merge made here, never what a pull or a rebase brought in. The handover light's own board reports are left out.
    Counting the range between the start snapshot and HEAD (before 0.99.2) also counted every commit PULLED during a
    long session, so the box listed dozens of repos as "pushed" that this session never touched (2026-11-02: about 70
    rows, the /gs and /gu copies with hundreds of "new commits" each)."""
    ok, out = git(["reflog", "show", "--date=unix", "--format=%H%x09%gd%x09%gs", "HEAD"], repo)
    found = []
    if not ok:
        return found
    for line in out.splitlines():
        parts = line.split("\t", 2)
        m = re.search(r"\{(\d+)\}", parts[1]) if len(parts) == 3 else None
        if not m:
            continue
        if int(m.group(1)) < since:
            break
        action, _, subject = parts[2].partition(": ")
        if action.startswith("commit") and not subject.startswith("handover: ") and parts[0] not in found:
            found.append(parts[0])
    return found


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
    try:   # since 0.103.0 the end steps run in a helper after the window has gone: still running is not cut off
        import endwork
        if endwork.running_pid():
            return ""
    except Exception:  # noqa: BLE001
        pass
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
                    "last_end": last_end, "first": first, "lanes": hb.get("lanes", "")})
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
            if lanes_version.mismatch(pc["machine"], pc["lanes"]):
                lines.append("HANDOVER: ⚠️ " + lanes_version.mismatch(pc["machine"], pc["lanes"]) + ".")
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


def inspector_check(cell, pushed):
    """The Inspector sees code written with the edit tools only. When it saw none but this session committed code
    files (written by a shell command or a script, or in a project it does not watch), say so instead of "no code
    was written" (home PC, 2026-11-05: the Silent Hill 2 launcher's C++ was written and built, the box said none)."""
    if not cell.startswith("on, no code was written"):
        return cell
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import inspector_checks
        n = 0
        for r in pushed:
            for h in r.get("made", []):
                ok, out = git(["show", "--name-only", "--format=", h], r["repo"])
                n += sum(1 for f in out.splitlines() if f and inspector_checks.is_source(f)) if ok else 0
    except Exception:  # noqa: BLE001 - the box must print whatever happens here
        return cell
    if not n:
        return cell
    return ("⚠️ saw no code edits, but this session committed %s (written another way, or outside the projects "
            "it watches): not looked over" % plural(n, "code file", "code files"))


CLOSE_SAVED_LINES = []     # set by close_box: the saved report the close-out writes to the board as the END


def games_running():
    """project games running on this PC now, from the collector's open run cards (each checked to be still running)"""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "begone"))
        import collector
        import psutil
    except Exception:  # noqa: BLE001 - no collector, or no psutil: say nothing rather than guess
        return []
    out = []
    for _folder, r in collector.pending():
        if r.get("end") or not r.get("pid"):
            continue
        try:
            if psutil.Process(int(r["pid"])).name().lower() == str(r.get("exe", "")).lower():
                name = r.get("title") or r.get("game") or r.get("exe")
                if name not in out:
                    out.append(name)
        except Exception:  # noqa: BLE001 - gone, or a different program has the number now
            continue
    return out


def close_box(conf, session):
    """The close-out box: one markdown table that ends every lane's write-up. Returns (green, lines)."""
    roots = roots_from(conf)
    board = conf.get("board", "")
    me = conf.get("machine_name") or conf.get("role") or "PC"
    rows = scan_roots(roots)
    green, saved_lines, count = saved_report(roots, rows)
    global CLOSE_SAVED_LINES
    CLOSE_SAVED_LINES = saved_lines     # the end report main() writes after the box (2026-11-05)
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
    unanswered = 0       # filled in below from the Inspector's cell; a green box with notes waiting turns red

    def shown(r):
        return r["name"] if root_label(r["root"]) == "live root" else "%s (%s)" % (r["name"], root_label(r["root"]))

    snap = snapshot_read(session)
    since = session_started(session, snap) if snap else None
    pushed = []
    own = session_commits(session)
    for r in rows:
        if r["problem"] or since is None:
            continue
        noted = own is not None and notes_commits(r["repo"])   # else every commit made here since the start counts
        r["made"] = [h for h in made_here(r["repo"], since) if not noted or h in own]
        if not r["made"]:
            continue
        pushed.append(r)
        n = len(r["made"])
        lines.append("| 📦 %s | pushed · %s |" % (shown(r), plural(n, "new commit", "new commits")))
    for r in problems:
        lines.append("| 📦 %s | ⚠️ %s |" % (shown(r), problem_text(r, short=True)))
    old_hist = [r for r in rows if r.get("old_history") and not r["problem"] and r not in pushed]
    for r in old_hist:
        lines.append("| 📦 %s | ⚠️ %s |" % (shown(r), r["note"]))
    rest = count - len(pushed) - len(problems) - len(old_hist)
    if roots and rest > 0:
        word = "the other" if (pushed or problems) else "all"
        lines.append("| 📦 %s %s | nothing to push |" % (word, plural(rest, "repo", "repos")))
    profile = profile_cell(conf, pushed, snap)
    if profile:
        lines.append("| 🪧 Front page | %s |" % profile)
    try:
        places = places_cell(conf, pushed)
    except Exception:  # noqa: BLE001 - a check that cannot run never stops the box
        places = ""
    if places:
        lines.append("| 📣 Also mentioned | %s |" % places)
    try:
        owed = owed_cell(conf)
    except Exception:  # noqa: BLE001
        owed = ""
    if owed:
        lines.append("| 📌 Jobs for this PC | %s |" % owed)
    for g in games_running():
        # 0.103.0 (Run 5 D9): the rule is to close the game when a run ends; the box said nothing when one was open
        lines.append("| 🎮 Game | ⚠️ %s is still running: close it with its own quit if this session's run is done |" % g)
    view = stale_view_cell(rows) if roots else ""
    if view:
        lines.append("| 🌐 GitHub view | %s |" % view)
    cell = inspector_check(inspector_cell(session), pushed)
    lines.append("| 🔍 Inspector | %s |" % cell)
    m = re.search(r"(\d+) unanswered", cell)
    unanswered = int(m.group(1)) if m else 0
    if green and roots and unanswered:
        # 0.105.0 (audit P8, 2026-11-06): the Inspector's hold sits on `git push`, and with inspector_notes_local the
        # notes never go to GitHub, so nothing held; verdicts were given in 3 of 96 home sessions. The work is on
        # GitHub (the board still says SAVED), but the headline is the signal Tefa reads, so it says what is left.
        lines[0] = "| 🔦 **NOT SAVED** | **%s UNANSWERED: ANSWER THEM, THEN END** |" % plural(
            unanswered, "INSPECTOR NOTE", "INSPECTOR NOTES")
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
                if lanes_version.mismatch(pc["machine"], pc["lanes"]):
                    lines.append("| 🖥️ %s | ⚠️ %s |" % (pc["machine"], lanes_version.mismatch(pc["machine"], pc["lanes"])))
        if not pcs:
            lines.append("| 🖥️ Other PC | has not reported yet |")
        if not fetched:
            if FETCH_REASON == "damaged":
                lines.append("| 🖥️ GitHub | answers, but this PC's copy of the board could not fetch: probably a damaged clone (git fsck) |")
            else:
                lines.append("| 🖥️ GitHub | could not be reached just now, the row above may be old |")
    else:
        lines.append("| 🖥️ Other PC | no board to read it from |")
    if green and roots and not unanswered and not early_summary_on():
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
    behind, fine, seen = [], 0, set()
    for r in pushed:
        for repo, sub, mmdd, title in rows:
            if repo != r["name"].lower() or title in seen:
                continue
            day = work_day(r, sub)
            if not day:
                continue
            seen.add(title)
            # The row must be as new as the session's own last work there. Until 0.107.0 it had to carry TODAY's
            # date, so a session that ran past midnight was told its rows were behind when they were right (rows dated
            # 11-09, work committed 11-09 19:33, box printed 11-10).
            if mmdd >= day[5:] or (mmdd[:2] == "01" and day[5:7] == "12"):     # a January row after December work
                fine += 1
            else:
                behind.append("\"%s\" (%s)" % (title[:PROFILE_TITLE_CHARS], mmdd))
    if behind:
        return "⚠️ this session's work is not on its row yet: %s. Refresh the row, its INDEX.json stage, and Recent " \
               "Activity if it moved forward" % ", ".join(behind)
    return "%s up to date" % plural(fine, "row", "rows") if fine else ""


def work_day(r, sub=""):
    """'YYYY-MM-DD' of the newest commit this session made in repo row `r` that touches real work (under `sub`, when
    the front-page row is about one folder), or "" when it made none: research notes, inboxes, Inspector notes and
    ideas move without the project moving (gu_texts.NOT_WORK). Only this session's own commits count (0.99.2)."""
    try:
        from gu_texts import NOT_WORK
    except ImportError:
        NOT_WORK = ()
    spec = ["--", sub or "."] + [":(exclude,glob)%s" % p for p in NOT_WORK]
    days = []
    for h in r.get("made", []):
        if git(["diff-tree", "--no-commit-id", "--name-only", "-r", "--root", h] + spec, r["repo"])[1]:
            ok, d = git(["log", "-1", "--format=%cs", h], r["repo"])
            if ok and d.strip():
                days.append(d.strip())
    return max(days) if days else ""


def conf_values(key):
    """every value of a setting that may be written on several lines (`ours = ...`), comments cut off"""
    out = []
    try:
        with open(conf_path(), encoding="utf-8") as f:
            for line in f:
                m = re.match(r"^\s*%s\s*=\s*(.*?)\s*(#.*)?$" % re.escape(key), line)
                if m and m.group(1).strip():
                    out.append(m.group(1).strip())
    except OSError:
        pass
    return out


def squash_name(name):
    """'Hand Poser', 'hand-poser-vr' and 'HandPoser' all read as 'handposer' (the same rule as gu_texts.squash)"""
    s = re.sub(r"[^a-z0-9]", "", name.lower())
    return s[:-2] if s.endswith("vr") and len(s) > 4 else s


def places_cell(conf, pushed):
    """The close-out box's "Also mentioned" row (0.107.0): the OTHER places that speak about a repo this session pushed
    real work to, each checked from files already on this PC (no network, a second or two).

    Asked for by the maintainer, 2026-11-10: "if we upload and push new things, then all the relevant departments get
    updated, not just the mod release page for instance, but mod page, front page, notes, and other parts where this
    work might be mentioned". The front-page row had its own check since 0.94.2; that day's Out of Date scan still
    found the index behind for five games, three tool downloads older than their programs, and three tools the tool
    list page never names. Out of Date finds those once a week; this says it while the session that did the work is
    still open. Checked: the project's stage line in INDEX.json (beside the front page), the catalog page
    (`catalog =`) naming a tool of ours (`ours =`), and a tool's newest download against its program. "" = all fine."""
    page = os.environ.get("LANES_FRONTPAGE") or conf.get("frontpage", "")
    folder = (page if os.path.isdir(page) else os.path.dirname(page)) if page else ""
    stages = {}
    try:
        with open(os.path.join(folder, "INDEX.json"), encoding="utf-8") as f:
            for p in json.load(f).get("projects") or []:
                dates = sorted(re.findall(r"\d{4}-\d\d-\d\d", p.get("stage") or ""))
                if p.get("repo"):
                    stages[p["repo"].lower()] = dates[-1] if dates else ""
    except (OSError, ValueError, AttributeError):
        pass
    ours = {os.path.basename(p.replace("\\", "/").rstrip("/")).lower() for p in conf_values("ours")}
    catalogs = []
    for spec in conf_values("catalog"):
        repo, _, rel = spec.replace("\\", "/").partition("/")
        for base in [conf.get("texts", "")] + roots_from(conf):
            path = os.path.join(base, repo, rel) if base and rel else ""
            if path and os.path.isfile(path):
                try:
                    with open(path, encoding="utf-8") as f:
                        catalogs.append((repo.lower(), os.path.basename(rel), squash_name(f.read())))
                except OSError:
                    pass
                break
    flags = []
    for r in pushed:
        name = r["name"].lower()
        day = work_day(r)
        if not day:
            continue
        said = []
        if name in stages and stages[name] < day:
            said.append("its INDEX.json stage is dated %s" % (stages[name] or "with no date"))
        if name in ours:
            for cat_repo, cat_file, text in catalogs:
                if cat_repo != name and squash_name(name) not in text:
                    said.append("%s never names it" % cat_file)
            # 0.107.1: only a tag that looks like a version is a download. The first real box took a safety tag
            # ("pre-ch-2026-11-01", the copy saved before a code-health pass) for one and raised a false alarm.
            ok, tag = git(["describe", "--tags", "--abbrev=0", "--match", "v[0-9]*", "--match", "*-v[0-9]*",
                           "--match", "[0-9]*.[0-9]*"], r["repo"])
            if ok and tag.strip():
                try:
                    import od
                    changes = od.code_changes_since(r["repo"], tag.strip(), "HEAD")
                except Exception:  # noqa: BLE001 - the box is printed whatever this check does
                    changes = None
                if changes and changes[0]:
                    said.append("its download %s is %s older than the program" % (
                        tag.strip(), plural(changes[0], "change", "changes")))
        if said:
            flags.append("%s: %s" % (r["name"], ", ".join(said)))
    if flags:
        return "⚠️ " + "; ".join(flags) + ". Bring each up to date before ending (or say why it waits)"
    return ""


OWED_SHOWN = 6          # titles named in the box; the rest are counted
OWED_TITLE_CHARS = 60


def owed_cell(conf):
    """The close-out box's row of jobs raised for THIS PC that are still open (0.107.0). Nothing ticked a job off when
    its work was done and the close-out never asked, so on 2026-11-09 the home PC's start listed three waiting jobs of
    which two were finished, and it read as lost work ("something is not saving"). Read from the board's owed/<ROLE>/
    folder as it is on this PC; "" when there is none."""
    board, role = conf.get("board", ""), (conf.get("role") or "").upper()
    folder = os.path.join(board, "owed", role) if board and role else ""
    if not folder or not os.path.isdir(folder):
        return ""
    titles = []
    for n in sorted(os.listdir(folder)):
        if not n.endswith(".md") or n.lower() == "readme.md":
            continue
        try:
            with open(os.path.join(folder, n), encoding="utf-8") as f:
                first = f.readline().strip().lstrip("# ").strip()
        except OSError:
            first = ""
        titles.append((first or n[:-3])[:OWED_TITLE_CHARS])
    if not titles:
        return ""
    more = " (+%d more)" % (len(titles) - OWED_SHOWN) if len(titles) > OWED_SHOWN else ""
    return "%s still open: %s%s. Tick off any this session finished (owed.sh done), so it is not offered again" % (
        plural(len(titles), "job", "jobs"), "; ".join(titles[:OWED_SHOWN]), more)


def early_summary_on():
    try:
        import compact  # lazy: compact.py imports this module
        return compact.early_summary_on()
    except Exception:  # noqa: BLE001 - unknown means offer the safe-to-clear row
        return False


def start_report_changes_light(path, green):
    """True when the report on the board says the other light (SAVED vs NOT SAVED) than this PC has now.

    The hourly hold-back on start reports exists to save commits, never to leave the other PC looking at a stale
    red light: on 2026-11-01 the home PC wrote NOT SAVED at 10:43 and a SAVED start at 11:23 wrote nothing, so the
    dev PC saw red for up to an hour (two-PC test, Run 2). A change of light is always written.
    """
    try:
        with open(path, encoding="utf-8") as f:
            hb = dict(l.split(" = ", 1) for l in f.read().splitlines() if " = " in l)
        if hb.get("lanes", "").strip() != lanes_version.mine():
            return True             # a new Lanes is always told at once (2026-11-05)
        if "state" in hb:
            return (hb["state"].strip() == "SAVED") != bool(green)
    except OSError:
        pass
    return True   # unreadable or no state line: write a fresh one


def report_age_s(board, path):
    """Seconds since the report was last COMMITTED (git), falling back to the file's modified time.

    The file's modified time moves whenever a checkout or rebase rewrites it, which made an old report look new.
    """
    rel = os.path.relpath(path, board).replace(os.sep, "/")
    ok, out = git(["log", "-1", "--format=%ct", "--", rel], board)
    if ok and out.strip().isdigit():
        return datetime.now().timestamp() - int(out.strip())
    try:
        return datetime.now().timestamp() - os.path.getmtime(path)
    except OSError:
        return START_WRITE_MIN_AGE_S   # unknown age: allow the write


def write_heartbeat(board, me, role, event, green, problem_lines):
    """One small file on the board, committed on its own and pushed. Returns a one-line result."""
    if not board or not os.path.isdir(board):
        return "HANDOVER: not reported - no board."
    hb_dir = os.path.join(board, HEARTBEAT_DIR)
    path = os.path.join(hb_dir, me + ".txt")
    if event == "start" and os.path.isfile(path) and not start_report_changes_light(path, green) \
            and report_age_s(board, path) < START_WRITE_MIN_AGE_S:
        return ""
    os.makedirs(hb_dir, exist_ok=True)
    state = "SAVED" if green else "NOT SAVED: " + "; ".join(l.strip() for l in problem_lines[1:])[:STATE_MAX_CHARS]
    now = datetime.now().astimezone().strftime(TIME_FMT)
    body = ("# Written by the lanes plugin (tools/handover.py), one file per PC. Never edited by hand.\n"
            "machine = %s\nrole = %s\nlast_saved = %s\nevent = %s\nstate = %s\nlanes = %s\n"
            % (me, role, now, event, state, lanes_version.mine()))
    # Saved straight onto GitHub's copy of the board, without touching this PC's board folder (Run 6, 2026-11-06): the
    # old way added, committed and pulled with --autostash inside the board folder, and when the end helper did that
    # while a live session was saving there, the live session's next pull was refused and a file it had just deleted
    # came back in its staging area. The clash guard's locks are saved the same way (fullscan_lock.push_change).
    import fullscan_lock as FL
    rel = HEARTBEAT_DIR + "/" + me + ".txt"
    msg = "handover: %s (%s) %s, %s" % (me, role, event, "SAVED" if green else "NOT SAVED")
    ok = False
    for _attempt in range(PUSH_ATTEMPTS):
        git(["fetch", "-q", "origin"], board, timeout=FETCH_TIMEOUT_S)
        if FL.push_change(board, body, msg, rel=rel):
            ok = True
            break
    if ok:
        catch_up_board(board)
    return "HANDOVER: this PC (%s) reported %s on the board." % (me, "SAVED" if green else "NOT SAVED") if ok \
        else "HANDOVER: this PC's report could NOT be pushed to the board (GitHub unreachable?)."


def catch_up_board(board):
    """bring the board folder up to GitHub's copy, but only when nothing is in progress there: no git step running, no
    file changed or staged, and nothing of its own to rebase. Otherwise the folder's own next pull does it."""
    if any(os.path.exists(os.path.join(board, ".git", n)) for n in ("index.lock", "MERGE_HEAD", "rebase-merge",
                                                                       "rebase-apply")):
        return
    ok, st = git(["status", "--porcelain", "--untracked-files=no"], board)
    if not ok or st.strip():
        return
    git(["merge", "-q", "--ff-only", "origin/main"], board, timeout=FETCH_TIMEOUT_S)


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
        # The close-out is where a session really reports how it ended, so it writes the END to the board too
        # (2026-11-05). The SessionEnd hook alone never managed it: on both PCs every end report since 11-02 began
        # and was cut off before it finished (the save scan of ~300 repos takes half a minute, and Claude Code ends
        # first), so neither PC ever saw the other's session end. --no-write leaves the board and the end log alone.
        writing = bool(roots_from(conf)) and "--no-write" not in flags
        if writing:
            end_log("began", session)
        green, lines = close_box(conf, session)
        print("\n".join(lines))
        if writing:
            r = write_heartbeat(board, me, role, "end", green, CLOSE_SAVED_LINES)
            if r:
                print(r)
            end_log("done", session)
        return 0 if green else (1 if roots_from(conf) else 2)
    if mode == "fresh":
        root = args[0] if args else (os.path.dirname(os.path.abspath(board)) if board else "")
        if not root or not os.path.isdir(root):
            print("HANDOVER: could not run - give a clone root, or set `board = ...` in lanes.conf"); return 2
        green, lines = fresh_report(root, "--pull" in flags)
        print("\n".join(lines)); return 0 if green else 1
    if mode == "refresh":
        n, ok = refresh_views(roots_from(conf))
        print("HANDOVER: looked at GitHub again for %d cop%s (%d fetched)" % (n, "y" if n == 1 else "ies", ok))
        return 0
    if mode == "level":
        print(level_report(conf))
        return 0
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
