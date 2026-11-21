"""fresh_pc_faults_test.py - three faults a brand-new one-PC install met in its first full scan (0.121.1).

Reported from the Workshop PC on 2026-11-21 as lanes-plugin issues #3, #4 and #5:
  #3  gd.py's BeG0nE lookup crashed on Windows when `begone =` is not set (a "\\0" path, ValueError from glob);
  #4  thanks.py said "gh is not installed" when gh only took too long to answer;
  #5  the shell tools that read lanes.conf kept a trailing "# note" in the value, so `board = <folder>   # note`
      found no board.
Runs in a temp folder with its own lanes.conf; touches nothing of this PC. Exit 0 = pass."""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
T = tempfile.mkdtemp(prefix="freshpc-")
fails = 0


def check(ok, what):
    global fails
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        fails += 1


def slash(p):
    return p.replace("\\", "/")


board = os.path.join(T, "board")
os.makedirs(os.path.join(board, "status"))
subprocess.run(["git", "init", "-q", board], capture_output=True)
conf = os.path.join(T, "lanes.conf")
with open(conf, "w", encoding="utf-8", newline="\n") as f:
    f.write("board = %s   # the shared work board (estate.py)\nrole = HOME   # this PC\n" % slash(board))
os.environ["LANES_CONFIG"] = conf

# ---- #3: no `begone =` line
import gd  # noqa: E402
try:
    got = gd.begone_games()
    check(got == set(), "#3 gd.py: no begone = set means no BeG0nE games, not a crash")
except ValueError as e:
    check(False, "#3 gd.py: no begone = set crashed (%s)" % e)

# ---- #4: gh that only times out
import thanks  # noqa: E402
slow = os.path.join(T, "slow_gh.py")
with open(slow, "w", encoding="utf-8") as f:
    f.write("import time\ntime.sleep(5)\n")
thanks.GH, thanks.GH_TIMEOUT_S = sys.executable, 1
real_run = subprocess.run


def run_slow(args, **kw):
    return real_run([sys.executable, slow] + list(args[1:]), **kw)


thanks.subprocess.run = run_slow
logged, may_follow, words = thanks.gh_state()
thanks.subprocess.run = real_run
check(not logged and "did not answer in time" in words and "not installed" not in words,
      "#4 thanks.py: a gh that only times out is said as such, not as 'not installed' (%s)" % words)
thanks.GH = os.path.join(T, "no-such-gh.exe")
logged, may_follow, words = thanks.gh_state()
check(not logged and "not installed" in words, "#4 thanks.py: a gh that is really missing is still 'not installed'")

# ---- #5: every shell reader of lanes.conf finds the board through a trailing "# note"
env = dict(os.environ, LANES_CONFIG=conf, HOME=T)
for script, args, bad in (("frontpage-scan.sh", [], "no board found"),
                          ("lane-claim.sh", ["list"], "no board found"),
                          ("owed.sh", ["list"], "no board found"),
                          ("gate-scan.sh", ["--check"], "no board found")):
    r = subprocess.run(["bash", slash(os.path.join(TOOLS, script))] + args, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=120)
    check(bad not in (r.stdout + r.stderr), "#5 %s finds `board = <folder>   # note`" % script)

print()
print("fresh_pc_faults_test.py: %s" % ("all passed" if not fails else "%d FAILED" % fails))
sys.exit(1 if fails else 0)
