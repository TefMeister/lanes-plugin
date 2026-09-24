"""Build a tiny synthetic board repo for testing the lanes tools.

Small on purpose. A real board is many projects of prose, and reproducing a bug
against one is both slow and non-deterministic, because concurrent sessions keep
changing it underneath the test. This fixture is deterministic apart from the
dates, which have to be current for the staleness and claim-age checks to mean
anything.

Usage:  python make-fixture-board.py [target-dir]
Prints the path it created. Safe to re-run; it deletes and rebuilds.
"""
import datetime
import io
import os
import shutil
import subprocess
import sys

TARGET = os.path.abspath(
    sys.argv[1] if len(sys.argv) > 1
    else os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixture-board")
)

if os.path.isdir(TARGET):
    shutil.rmtree(TARGET, ignore_errors=True)
os.makedirs(os.path.join(TARGET, "status"))


def write(rel, text):
    io.open(os.path.join(TARGET, rel), "w", encoding="utf-8", newline="\n").write(text)


now = datetime.datetime.now()
today = now.strftime("%Y-%m-%d")
stamp = now.strftime("%Y-%m-%d %H:%M")

# '*' is the catch-all row: every project belongs to DEV unless named otherwise.
write("machine-assignments.tsv", "# role\tproject\nDEV\t*\n")

# demo-alpha carries a FRESH live claim and one row at each gate, so it exercises
# the claim filter, the cheapest-first ordering and the per-gate counts at once.
write("status/demo-alpha.md", (
    "# Demo Alpha\n"
    "\n"
    "LIVE: /lm %s TESTBOX\n"
    "OPEN (%s): \n"
    "  [PD] a job that needs nothing running\n"
    "  [FLAT] a job that needs the app up\n"
    "  [VR CLAUDE] a job that needs the hardware connected, but nobody there\n"
    "  [VR USER] a job that needs a person using the hardware\n"
    "\n"
    "- %s a log entry, so the OPEN block is not stale.\n"
) % (stamp, today, today))

# demo-beta is idle: a well-formed block with no rows.
write("status/demo-beta.md", (
    "# Demo Beta\n"
    "\n"
    "OPEN (%s): none\n"
    "\n"
    "- %s nothing queued here.\n"
) % (today, today))


def git(*args):
    return subprocess.run(["git", "-C", TARGET] + list(args),
                          capture_output=True, text=True)


git("init", "-q", "-b", "main")
git("config", "user.email", "fixture@example.invalid")
git("config", "user.name", "fixture")
git("add", "-A")
git("commit", "-q", "-m", "fixture board")
# The tools read origin/main rather than the working tree, so point it at HEAD.
git("update-ref", "refs/remotes/origin/main", "HEAD")

print(TARGET)
