"""fullscan_lock_test.py - the full scan runs on one PC and never twice at once (0.101.0, 2026-11-05).
In a temp folder: a pretend GitHub (bare repo) and two board clones with their own lanes.conf (PC1 HOME, PC2 DEV).
Checks: HOME may not run it, DEV may, fullscan_here overrides both ways; PC2 takes the lock, a second take from
another DEV PC is refused, PC2 taking again is fine; release only by the holder; a claim older than 12 h is taken
over; the clone's working tree and branch are never touched. Exit 0 = pass."""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import fullscan_lock as L  # noqa: E402

fails = 0


def check(ok, what):
    global fails
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        fails += 1


def git(repo, *a):
    return subprocess.run(["git", "-C", repo] + list(a), capture_output=True, text=True).stdout.rstrip()


def main():
    t = tempfile.mkdtemp(prefix="fslock-")
    bare = os.path.join(t, "remote.git")
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", bare], check=True)
    clones = {}
    for name in ("pc1", "pc2", "pc3"):
        c = os.path.join(t, name)
        subprocess.run(["git", "clone", "-q", bare, c], check=True, capture_output=True)
        for k, v in (("user.name", "t"), ("user.email", "t@example.invalid"), ("core.hooksPath", os.path.join(t, "nohooks"))):
            git(c, "config", k, v)
        clones[name] = c
    a = clones["pc1"]
    with open(os.path.join(a, "README.md"), "w") as f:
        f.write("board\n")
    git(a, "add", "README.md"); git(a, "commit", "-q", "-m", "start"); git(a, "push", "-q", "-u", "origin", "main")
    for c in clones.values():
        git(c, "pull", "-q")

    c1 = {"role": "HOME", "machine_name": "PC1", "board": clones["pc1"]}
    c2 = {"role": "DEV", "machine_name": "PC2", "board": clones["pc2"]}
    c3 = {"role": "DEV", "machine_name": "PC3", "board": clones["pc3"]}

    check(L.here(c1)[0], "a HOME PC may run the full scan too (changed 2026-11-05)")
    check(L.here(c2)[0], "a DEV PC may")
    check(L.here(dict(c1, fullscan_here="yes"))[0], "fullscan_here = yes overrides HOME")
    check(not L.here(dict(c2, fullscan_here="no"))[0], "fullscan_here = no overrides DEV")
    check(L.here({"machine_name": "PC1"})[0], "a one-PC setup with no role runs it")

    # a half-done edit in PC2's board clone must survive
    with open(os.path.join(clones["pc2"], "README.md"), "w") as f:
        f.write("a session is editing this\n")
    check(L.take(c2) == 0, "PC2 takes the lock")
    check("handover/fullscan.lock" in git(bare, "ls-tree", "-r", "--name-only", "main"), "the claim is on GitHub")
    check(git(clones["pc2"], "status", "--porcelain") == " M README.md", "PC2's working tree is untouched")
    check(L.take(c3) == 1, "a second run on another PC is refused while PC2 holds it")
    check(L.take(c2) == 0, "PC2 taking it again (same run restarted) is fine")
    check(L.release(c3) == 1, "PC3 cannot release PC2's claim")
    check(L.release(c2) == 0, "PC2 releases it")
    check("handover/fullscan.lock" not in git(bare, "ls-tree", "-r", "--name-only", "main"), "the claim is gone from GitHub")
    check(L.take(c3) == 0, "now PC3 may take it")

    # a left-over claim (over 12 h old) is taken over
    old = "# x\nmachine = PC3\nsince = 2020-01-01 00:00 +0000\n"
    git(clones["pc2"], "fetch", "-q")
    check(L.push_change(clones["pc2"], old, "test: old claim"), "an old claim is planted")
    check(L.take(c2) == 0, "a claim over 12 h old is taken over")
    who, _ = L.read_lock(clones["pc2"])
    check(who == "PC2", "the claim now names PC2")

    print("%d failed" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
