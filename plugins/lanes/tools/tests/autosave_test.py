"""autosave_test.py - the rider saves its own BeG0nE reports, and nothing else (0.101.0, 2026-11-05).
Checks, in a temp folder with a pretend GitHub (a bare repo): a filed report is committed and pushed; a session's own
half-done change elsewhere in the clone is neither committed nor touched; nothing new = silent; git busy (index.lock)
= skipped and left for later; a clone behind GitHub pulls and pushes when nothing else is changed, and does not pull
(commits only) when something else is. Exit 0 = pass."""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(PLUGIN, "begone"))
import autosave  # noqa: E402

fails = 0


def check(ok, what):
    global fails
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        fails += 1


def git(repo, *a):
    r = subprocess.run(["git", "-C", repo] + list(a), capture_output=True, text=True)
    return r.stdout.rstrip()   # not strip(): `git status --porcelain` starts with a meaningful space


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main():
    t = tempfile.mkdtemp(prefix="autosave-")
    bare, a, b = (os.path.join(t, n) for n in ("remote.git", "a", "b"))
    env_cfg = ["-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "core.hooksPath=" + os.path.join(t, "nohooks")]
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", bare], check=True)
    subprocess.run(["git", "clone", "-q", bare, a], check=True, capture_output=True)
    for r in (a,):
        for k, v in (("user.name", "t"), ("user.email", "t@example.invalid"), ("core.hooksPath", os.path.join(t, "nohooks"))):
            git(r, "config", k, v)
    write(os.path.join(a, "README.md"), "x\n")
    write(os.path.join(a, "ghost-hand", "README.md"), "tool\n")
    git(a, "add", "-A"); git(a, "commit", "-q", "-m", "start"); git(a, "push", "-q", "-u", "origin", "main")

    # 1. a report and a session's half-done edit
    write(os.path.join(a, "ghost-hand", "data", "village", "r1", "report.md"), "report\n")
    write(os.path.join(a, "ghost-hand", "data", "village", "r1", "summary.json"), "{}\n")
    write(os.path.join(a, "README.md"), "a session is editing this\n")
    write(os.path.join(a, "ideas", "new-idea.md"), "not ours\n")
    line = autosave.save(a, ["ghost-hand", "camera-jitter"])
    check("pushed" in line, "a filed report is committed and pushed (%s)" % line)
    remote_files = git(bare, "ls-tree", "-r", "--name-only", "main")
    check("ghost-hand/data/village/r1/report.md" in remote_files, "the report is on the pretend GitHub")
    check("ideas/new-idea.md" not in remote_files, "a file outside the data folders is not committed")
    st = git(a, "status", "--porcelain")
    check(" M README.md" in st and "?? ideas/" in st, "the session's own changes are left as they were")

    # 2. nothing new
    check(autosave.save(a, ["ghost-hand"]) == "", "nothing new = silent")

    # 3. git busy
    write(os.path.join(a, "ghost-hand", "data", "village", "r2", "report.md"), "report 2\n")
    lock = os.path.join(a, ".git", "index.lock")
    open(lock, "w").close()
    line = autosave.save(a, ["ghost-hand"])
    check("skipped" in line, "git busy = skipped (%s)" % line)
    os.remove(lock)

    # 4. behind GitHub, other changes present: commits, does not pull
    subprocess.run(["git", "clone", "-q", bare, b], check=True, capture_output=True)
    for k, v in (("user.name", "t"), ("user.email", "t@example.invalid"), ("core.hooksPath", os.path.join(t, "nohooks"))):
        git(b, "config", k, v)
    write(os.path.join(b, "other.md"), "from the other PC\n")
    git(b, "add", "other.md"); git(b, "commit", "-q", "-m", "other"); git(b, "push", "-q")
    line = autosave.save(a, ["ghost-hand"])
    check("not pushed" in line, "behind + other changes: committed, not pulled (%s)" % line)
    check(git(a, "stash", "list") == "", "no stash was made")

    # 5. behind GitHub, clone otherwise clean: pulls and pushes
    git(a, "checkout", "-q", "--", "README.md")
    write(os.path.join(a, "ghost-hand", "data", "village", "r3", "report.md"), "report 3\n")
    line = autosave.save(a, ["ghost-hand"])
    check(line.endswith("pushed"), "behind + clean: pulled and pushed (%s)" % line)
    remote_files = git(bare, "ls-tree", "-r", "--name-only", "main")
    check("ghost-hand/data/village/r2/report.md" in remote_files and "other.md" in remote_files,
          "the earlier unpushed report and the other PC's work are both on GitHub")
    check(not os.path.isdir(os.path.join(a, ".git", "rebase-merge")), "no rebase left half-way")

    print("%d failed" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
