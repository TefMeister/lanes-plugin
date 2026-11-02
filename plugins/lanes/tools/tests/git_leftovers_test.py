"""git_leftovers_test.py - a save cut off half-way is named for what it left behind (two-PC test 4, 2026-11-01).

    python tools/tests/git_leftovers_test.py      (exit 0 = all passed)
"""
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import git_leftovers as G  # noqa: E402

N = FAILED = 0


def check(ok, text):
    global N, FAILED
    N += 1
    if not ok:
        FAILED += 1
    print(("  ok    " if ok else "  FAIL  ") + text)


def repo():
    d = tempfile.mkdtemp()
    subprocess.run(["git", "init", "-q", d], check=True)
    return d


r = repo()
check(G.leftovers(r) == "", "a clean clone has nothing to say")

lock = os.path.join(r, ".git", "index.lock")
open(lock, "w").close()
check(G.leftovers(r) == "", "a fresh lock (a git running right now) is left alone")
old = time.time() - 10 * 60
os.utime(lock, (old, old))
check("lock file" in G.leftovers(r), "a lock left for ten minutes is named")
os.remove(lock)

os.makedirs(os.path.join(r, ".git", "rebase-merge"))
check("pull was cut off" in G.leftovers(r), "an open rebase is named")
os.rmdir(os.path.join(r, ".git", "rebase-merge"))

open(os.path.join(r, ".git", "MERGE_HEAD"), "w").close()
check("merge was cut off" in G.leftovers(r), "an open merge is named")
os.remove(os.path.join(r, ".git", "MERGE_HEAD"))

wt = tempfile.mkdtemp()
with open(os.path.join(wt, ".git"), "w") as f:
    f.write("gitdir: " + os.path.join(r, ".git") + "\n")
os.makedirs(os.path.join(r, ".git", "rebase-apply"))
check("pull was cut off" in G.leftovers(wt), "a worktree's .git file is followed to its git folder")

check(G.leftovers(tempfile.mkdtemp()) == "", "a folder with no git at all has nothing to say")

print(f"git-leftovers-test: {N} checks, {FAILED} failed")
sys.exit(1 if FAILED else 0)
