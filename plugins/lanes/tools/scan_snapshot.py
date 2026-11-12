#!/usr/bin/env python3
"""scan_snapshot.py - what a full scan changed, and what it did not: a snapshot of every copy on this PC and of
GitHub before the scan, the same after, and the differences in plain words (0.113.0, 2026-11-12).

    python scan_snapshot.py take <label>        save a snapshot (label: before / after / anything)
    python scan_snapshot.py diff [<a> <b>]      the differences between two snapshots (default: the newest
                                                "before" and the newest "after"); exit 1 when something changed
                                                that no saved step explains
    python scan_snapshot.py list                the snapshots kept on this PC

Asked for by the person, 2026-11-07, after a full scan's report called Far Cry 2 "to be paused" when it had been
paused since 2026-09-23: "next fullscan, i want you to go over everything and take a snapshot of the files on pc and
github, and then after the fullscan to see if there are any differences." The scan had changed nothing there; the
wrong line was the session's own. So every full scan can now prove what it changed and what it did not.

A SNAPSHOT, per copy in every clone root (handover.py's list): its branch, the step it is on, the step GitHub had at
the last look, GitHub's step now (asked live), every tracked file's content hash, the files changed and not saved,
the new files git does not track. Plus, from the board: each project's OPEN / PAUSED / LIVE lines and WATCHING.md.
Kept in <state dir>/scan-snapshots/ as JSON, never on GitHub (it names folders on this PC).

THE REPORT, most important first: (1) changes that no saved step explains (a file changed, added or removed with no
commit); (2) a branch switched or history rewritten; (3) board lines that changed (paused, open, live); (4) per copy,
the saved steps made, grouped by who made them (the subject's first word: "gr:", "sr:", "gs:" ...) with the files they
touched; (5) GitHub moving on its own (the other PC, the Keeper). Names copies and files, never folder paths.
"""
import concurrent.futures
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import handover  # noqa: E402

STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "lanes")
SNAP_DIR = os.path.join(STATE_DIR, "scan-snapshots")
GIT_TIMEOUT_S = 60
REMOTE_TIMEOUT_S = 30
WORKERS = 8
SHOWN = 15                     # files or steps listed per copy before "... and N more"
BOARD_LINE = re.compile(r"^\s*(OPEN\b|PAUSED\b|⏸|LIVE:|STATUS:|WATCHING\b)", re.I)


def git(repo, *args, timeout=GIT_TIMEOUT_S):
    try:
        r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        return r.returncode, r.stdout
    except (subprocess.TimeoutExpired, OSError):
        return 1, ""


def file_hash(path):
    h = hashlib.sha1()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return "unreadable"
    return h.hexdigest()


def repo_state(repo):
    _, branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    _, head = git(repo, "rev-parse", "HEAD")
    _, up = git(repo, "rev-parse", "@{u}")
    rc, remote = git(repo, "ls-remote", "origin", "HEAD", timeout=REMOTE_TIMEOUT_S)
    _, listing = git(repo, "ls-files", "-s", "-z")
    files = {}
    for entry in listing.split("\0"):
        m = re.match(r"^\d+ ([0-9a-f]+) \d\t(.+)$", entry)
        if m:
            files[m.group(2)] = m.group(1)
    _, status = git(repo, "status", "--porcelain", "-z", "--untracked-files=all")
    changed, untracked = {}, []
    for entry in status.split("\0"):
        if len(entry) < 4:
            continue
        code, path = entry[:2], entry[3:]
        if code == "??":
            untracked.append(path)
        else:
            changed[path] = code.strip() + ":" + file_hash(os.path.join(repo, path))
    return {"branch": branch.strip(), "head": head.strip(), "upstream": up.strip(),
            "github": remote.split()[0] if rc == 0 and remote.split() else "", "files": files,
            "changed": changed, "untracked": sorted(untracked)}


def board_lines(board):
    out = {}
    for path in sorted(glob.glob(os.path.join(board, "status", "*.md"))) + [os.path.join(board, "WATCHING.md")]:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                lines = [ln.rstrip() for ln in f if BOARD_LINE.match(ln)]
        except OSError:
            continue
        if path.endswith("WATCHING.md"):
            with open(path, encoding="utf-8", errors="replace") as f:
                lines = [ln.rstrip() for ln in f if ln.strip()]
        out[os.path.basename(path)] = lines
    return out


def take(label):
    conf = handover.read_conf()
    repos = []
    for root in handover.roots_from(conf):
        for repo in handover.repos_in(root):
            repos.append(("%s | %s" % (handover.root_label(root), os.path.basename(repo)), repo))
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(WORKERS) as ex:
        states = dict(zip([k for k, _ in repos], ex.map(lambda kr: repo_state(kr[1]), repos)))
    board = conf.get("board", "")
    snap = {"label": label, "when": time.strftime("%Y-%m-%d %H:%M:%S"), "repos": states,
            "paths": {k: r for k, r in repos}, "board": board_lines(board) if board and os.path.isdir(board) else {}}
    os.makedirs(SNAP_DIR, exist_ok=True)
    path = os.path.join(SNAP_DIR, "%s_%s.json" % (time.strftime("%Y-%m-%d_%H-%M-%S"), re.sub(r"\W+", "-", label)))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snap, f)
    print("snapshot '%s': %d copies, %d board files, %.0f s" % (label, len(states), len(snap["board"]), time.time() - t0))
    return 0


def snapshots():
    return sorted(glob.glob(os.path.join(SNAP_DIR, "*.json")))


def newest(label):
    found = [p for p in snapshots() if p.endswith("_%s.json" % label)]
    return found[-1] if found else None


def load(ref):
    path = ref if os.path.isfile(ref) else (newest(ref) or "")
    if not path:
        sys.exit("scan_snapshot: no snapshot '%s' (take one first)" % ref)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def more(items):
    return items[:SHOWN] + (["... and %d more" % (len(items) - SHOWN)] if len(items) > SHOWN else [])


def who(subject):
    m = re.match(r"^\s*([\w/.-]+):", subject)
    return m.group(1).lower() if m else "(no prefix)"


def diff(a_ref="before", b_ref="after"):
    a, b = load(a_ref), load(b_ref)
    unexplained, rewritten, steps, github_moved = [], [], [], []
    for key in sorted(set(a["repos"]) | set(b["repos"])):
        ra, rb = a["repos"].get(key), b["repos"].get(key)
        if not ra or not rb:
            unexplained.append("%s: the copy %s" % (key, "appeared" if rb else "is gone"))
            continue
        repo = b["paths"].get(key) or a["paths"].get(key)
        if ra["branch"] != rb["branch"]:
            rewritten.append("%s: branch %s -> %s" % (key, ra["branch"], rb["branch"]))
        committed = set()
        if ra["head"] != rb["head"]:
            rc, _ = git(repo, "merge-base", "--is-ancestor", ra["head"], rb["head"])
            if rc != 0:
                rewritten.append("%s: history rewritten (the earlier step %s is no longer behind the new one)"
                                 % (key, ra["head"][:8]))
            _, log = git(repo, "log", "--format=%h%x09%s", "%s..%s" % (ra["head"], rb["head"]))
            _, names = git(repo, "diff", "--name-only", ra["head"], rb["head"])
            committed = set(names.split())
            groups = {}
            for ln in log.splitlines():
                h, _, s = ln.partition("\t")
                groups.setdefault(who(s), []).append("%s %s" % (h, s))
            steps.append((key, groups, sorted(committed)))
        # files whose saved content changed without a step that touched them, and work left unsaved
        for path in sorted(set(ra["files"]) | set(rb["files"])):
            if ra["files"].get(path) != rb["files"].get(path) and path not in committed:
                unexplained.append("%s: %s %s with no saved step" % (
                    key, path, "added" if path not in ra["files"] else ("removed" if path not in rb["files"] else "changed")))
        for path, h in sorted(rb["changed"].items()):
            if ra["changed"].get(path) != h:
                unexplained.append("%s: %s changed and not saved" % (key, path))
        for path in sorted(set(rb["untracked"]) - set(ra["untracked"])):
            unexplained.append("%s: new file %s, not saved" % (key, path))
        if rb["github"] and ra["github"] and rb["github"] != ra["github"] and rb["github"] != rb["head"]:
            github_moved.append("%s: GitHub moved on by itself (%s -> %s): the other PC or the Keeper"
                                % (key, ra["github"][:8], rb["github"][:8]))
    board = []
    for name in sorted(set(a["board"]) | set(b["board"])):
        la, lb = a["board"].get(name, []), b["board"].get(name, [])
        for ln in lb:
            if ln not in la:
                board.append("%s: + %s" % (name, ln.strip()[:200]))
        for ln in la:
            if ln not in lb:
                board.append("%s: - %s" % (name, ln.strip()[:200]))
    print("WHAT CHANGED between '%s' (%s) and '%s' (%s)" % (a["label"], a["when"], b["label"], b["when"]))
    print("\n1. Changed with no saved step behind it (%d)%s" % (len(unexplained), "" if unexplained else ": none"))
    for ln in more(unexplained):
        print("   ! " + ln)
    print("\n2. Branch switched or history rewritten (%d)%s" % (len(rewritten), "" if rewritten else ": none"))
    for ln in rewritten:
        print("   ! " + ln)
    print("\n3. Board lines that changed (paused, open, live, the watch list) (%d)%s"
          % (len(board), "" if board else ": none"))
    for ln in more(board):
        print("   " + ln)
    print("\n4. Saved steps made, per copy, by who made them (%d copies)%s" % (len(steps), "" if steps else ": none"))
    for key, groups, files in steps:
        print("   %s: %d step(s), %d file(s)" % (key, sum(len(v) for v in groups.values()), len(files)))
        for w, items in sorted(groups.items()):
            print("     %s: %s" % (w, "; ".join(more(items))))
    print("\n5. GitHub moving on its own (%d)%s" % (len(github_moved), "" if github_moved else ": none"))
    for ln in github_moved:
        print("   " + ln)
    total = sum(len(a["repos"].get(k, {}).get("files", {})) for k in a["repos"])
    print("\nEverything else is as it was: %d copies, %d tracked files compared." % (len(b["repos"]), total))
    return 1 if unexplained or rewritten else 0


def cmd_list():
    for p in snapshots():
        print(os.path.basename(p))
    return 0


def main(argv):
    if argv[:1] == ["take"] and len(argv) == 2:
        return take(argv[1])
    if argv[:1] == ["diff"]:
        return diff(*(argv[1:3] if len(argv) >= 3 else []))
    if argv[:1] == ["list"]:
        return cmd_list()
    print(__doc__.split("\n\n")[1])
    return 2


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))
