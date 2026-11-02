"""git_leftovers.py - what a save cut off half-way leaves inside a clone, in plain words.

Two-PC test 4 (2026-11-01, "close a window mid-save"): the save light already called such a clone NOT SAVED, but only
as "1 change not committed", which hides the two leftovers that trip the next session up:
  * git's lock file (.git/index.lock): every later commit fails with "Unable to create index.lock: File exists";
  * a pull stopped half-way (an open rebase or merge): a session that just commits there commits into the middle of it.
Used by handover.py's per-clone state; reads files only, never runs git, never changes anything.
"""
import os
import time

LOCK_MIN_AGE_S = 120   # a lock younger than this may belong to a git that is running right now (another session)


def git_dir(repo):
    """The clone's git folder: .git, or the folder a worktree's .git file points at. None if there is none."""
    dot = os.path.join(repo, ".git")
    if os.path.isdir(dot):
        return dot
    try:
        with open(dot, encoding="utf-8") as f:
            line = f.readline().strip()
    except OSError:
        return None
    if not line.startswith("gitdir:"):
        return None
    path = line[len("gitdir:"):].strip()
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(repo, path))


def leftovers(repo, now=None):
    """One plain line naming what a cut-off save left behind, or ''."""
    gd = git_dir(repo)
    if not gd:
        return ""
    found = []
    lock = os.path.join(gd, "index.lock")
    try:
        if (now or time.time()) - os.path.getmtime(lock) >= LOCK_MIN_AGE_S:
            found.append("git's lock file was left behind by a cut-off save (delete .git/index.lock once no git "
                         "is running there)")
    except OSError:
        pass
    if os.path.isdir(os.path.join(gd, "rebase-merge")) or os.path.isdir(os.path.join(gd, "rebase-apply")):
        found.append("a pull was cut off half-way (finish it with git rebase --continue, or undo it with "
                     "git rebase --abort, before anything else)")
    elif os.path.isfile(os.path.join(gd, "MERGE_HEAD")):
        found.append("a merge was cut off half-way (finish it, or undo it with git merge --abort, before anything "
                     "else)")
    return "; ".join(found)
