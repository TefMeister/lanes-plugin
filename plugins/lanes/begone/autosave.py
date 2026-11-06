"""autosave.py - the rider puts the reports it filed on GitHub by itself (0.101.0, 2026-11-05, feature `begone_autosave`).

WHY. The rider only ever FILED reports into the BeG0nE folder; saving them to GitHub was left to whichever session
was open. On 2026-11-05 eight Village reports (10:11 to 10:34) were filed on the home PC and sat there unsaved after
the session ended; the home PC committed them by hand later. Every BeG0nE report commit before that was a session's.

WHAT IT TOUCHES, AND WHAT IT NEVER DOES.
  * Only new or changed files inside each tool's own data folder (<BeG0nE>/<tool>/data/...), the folders the filers
    write. Committed with an explicit file list (`git commit --only -- <files>`), so whatever a session has staged or
    changed elsewhere in that clone is left exactly as it was. Never `git add -A`.
  * Skips the whole pass when git is busy there (index.lock, a rebase or merge half-way): a session is working.
  * Pulls only when nothing else in the clone is changed (no autostash, so no stash can be left behind), and only
    with --rebase; a failed rebase is aborted at once. When it cannot pull or push, the commit stays on this PC and
    the close-out box's save light still names it, which was the only safety net before.
Never raises: the rider must live on whatever git says.

    python autosave.py <BeG0nE folder> [<tool folder> ...]     one save, for testing; prints what it did
"""
import os
import subprocess

GIT_TIMEOUT_S = 60
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _git(repo, *args, timeout=GIT_TIMEOUT_S):
    r = subprocess.run(["git", "-C", repo] + list(args), capture_output=True, text=True, timeout=timeout,
                       creationflags=NO_WINDOW, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _busy(repo):
    rc, gd = _git(repo, "rev-parse", "--git-dir")
    if rc != 0:
        return "not a git copy"
    gd = gd.strip().splitlines()[0] if gd.strip() else ".git"
    gd = gd if os.path.isabs(gd) else os.path.join(repo, gd)
    for n in ("index.lock", "rebase-merge", "rebase-apply", "MERGE_HEAD", "CHERRY_PICK_HEAD"):
        if os.path.exists(os.path.join(gd, n)):
            return "git is busy there (%s)" % n
    return ""


def _changed(repo, pathspecs):
    """paths (repo-relative) that are new or modified under the given folders"""
    rc, out = _git(repo, "status", "--porcelain", "-uall", "-z", "--", *pathspecs)
    if rc != 0:
        return []
    files = []
    for entry in out.split("\0"):
        if len(entry) > 3 and entry[:2] in ("??", " M", "M ", "MM", "A ", "AM"):
            files.append(entry[3:])
    return files


def save(repo, folders, label="reports"):
    """commit and push the new report files under <repo>/<folder>/data for each folder. Returns one plain line."""
    try:
        if not repo or not os.path.isdir(repo):
            return "autosave: no BeG0nE folder"
        why = _busy(repo)
        if why:
            return "autosave: skipped, %s; tried again next time" % why
        specs = [f + "/data" for f in folders if os.path.isdir(os.path.join(repo, f, "data"))]
        files = _changed(repo, specs) if specs else []
        if not files:
            return ""
        rc, out = _git(repo, "add", "--", *files)
        if rc != 0:
            return "autosave: could not add the reports: " + out.strip()[-200:]
        n = sum(1 for f in files if f.endswith("report.md")) or len(files)
        tools = sorted({f.split("/")[0] for f in files})
        msg = "%s: %d %s filed by the rider, saved by itself" % (", ".join(tools), n, label if n != 1 else "report")
        rc, out = _git(repo, "commit", "-q", "--only", "-m", msg, "--", *files)
        if rc != 0:
            return "autosave: could not commit: " + out.strip()[-200:]
        rc, _ = _git(repo, "push", "-q")
        if rc == 0:
            return "autosave: %s, pushed" % msg
        # behind GitHub: pull, but only when nothing else in the clone is changed (no stash ever made)
        rc, dirty = _git(repo, "status", "--porcelain", "--untracked-files=no")
        if rc != 0 or dirty.strip():
            return "autosave: committed, not pushed (other changes in the clone; a session will push it)"
        rc, out = _git(repo, "pull", "-q", "--rebase")
        if rc != 0:
            _git(repo, "rebase", "--abort")
            return "autosave: committed, not pushed (the pull failed; the save light will show it)"
        rc, _ = _git(repo, "push", "-q")
        return "autosave: %s, %s" % (msg, "pushed" if rc == 0 else "committed, the push failed")
    except Exception as e:  # never stop the rider
        return "autosave: %s: %s" % (type(e).__name__, e)


if __name__ == "__main__":
    import sys
    print(save(sys.argv[1], sys.argv[2:]) or "autosave: nothing new")
