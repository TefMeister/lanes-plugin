"""setup_run_test.py - setup's recommended way (tools/setup_run.py, 0.121.0).

Tefa, 2026-11-21: install everything and leave for work; the steps that need the person come at the very end. Checked
here with no command really run (LANES_SETUP_FAKE): plan does nothing; run does every step that needs nobody, skips
tools the PC has, never runs a maker's own installer, writes the "What needs you" list (restart last, the GitHub
sign-in only when GitHub is not signed in, the two-PC folder only for two PCs, SteamVR only with a headset), puts a
failed step at the top of the list, tries only what is left when run again, and the list can be ticked off.
Run: python setup_run_test.py   (exit 0 = all passed)
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SR = os.path.join(HERE, "..", "setup_run.py")
FE = os.path.join(HERE, "..", "features.py")
fails = 0


def check(what, got, want):
    global fails
    ok = got == want
    fails += 0 if ok else 1
    print("%s  %s%s" % ("ok  " if ok else "FAIL", what, "" if ok else "  (got %r, want %r)" % (got, want)))


def fresh(conf_lines, scan_present=(), gh="yes", fail=""):
    d = tempfile.mkdtemp(prefix="lanes-setup-run-")
    conf = os.path.join(d, "lanes.conf")
    with open(conf, "w", encoding="utf-8") as f:
        f.write("\n".join(conf_lines) + "\n")
    scan = os.path.join(d, "scan.json")
    with open(scan, "w", encoding="utf-8") as f:
        json.dump({"tools": [{"id": i, "present": True} for i in scan_present]}, f)
    env = dict(os.environ, LANES_STATE_DIR=os.path.join(d, "state"), LANES_CONFIG=conf, LANES_SETUP_FAKE="1",
               LANES_SETUP_SCAN=scan, LANES_SETUP_GH=gh, LANES_SETUP_FAIL=fail, PYTHONIOENCODING="utf-8")
    return d, env


def run(env, *args):
    p = subprocess.run([sys.executable, SR, *args], capture_output=True, text=True, env=env, encoding="utf-8")
    return p.returncode, p.stdout


def logtext(d):
    try:
        return open(os.path.join(d, "state", "setup-run.log"), encoding="utf-8").read()
    except OSError:
        return ""


def todo(env):
    return json.loads(run(env, "todo", "--json")[1])


# one PC, no headset, GitHub signed in
d, env = fresh(["pcs = 1", "bench_headset = none"], scan_present=["git", "blender"])
rc, out = run(env, "plan")
check("plan works", rc, 0)
check("plan does nothing", os.path.exists(os.path.join(d, "state", "setup-run.json")), False)
check("plan names what is left for you", "leave" in out and "Restart Claude Code" in out, True)
rc, out = run(env, "run")
check("a run with nothing failing ends well", rc, 0)
log = logtext(d)
check("the recommended extras are switched on", "features.py on talk_rule" in log, True)
check("the ones not recommended are switched off", "features.py off keep_transcripts" in log, True)
check("a program the PC lacks is installed without a Yes click", "quiet_install.py run winget:GIMP.GIMP.3" in log, True)
check("a program the PC has is left alone", "winget:Git.Git" in log, False)
check("our own apps are got", "ours.py get window_view" in log, True)
check("the other makers' downloads are got", "outside.py get openxr_cas" in log, True)
check("a maker's own installer is never opened while nobody is there", "outside.py get xrfps" in log, False)
check("the GitHub setup runs by itself when GitHub is signed in", "estate.py make --root" in log, True)
check("the pretend headset and VR Bench are installed", "openxr-sim.py install --fork --bench" in log, True)
conf = open(env["LANES_CONFIG"], encoding="utf-8").read()
check("one PC: saving to GitHub runs in the background", "keeper_mode = this_pc" in conf, True)
check("the recordings get a folder", "recordings = " in conf, True)
items = todo(env)
ids = [t["id"] for t in items]
check("restart is the last step on the list", ids[-1] if ids else None, "restart")
check("no GitHub sign-in step when GitHub is signed in", "github-signin" in ids, False)
check("the Blender clicks are on the list", "blender-clicks" in ids, True)
check("a maker's own installer is on the list instead", "outside:xrfps" in ids, True)
check("no two-PC folder on one PC", "transfer-folder" in ids, False)
check("no SteamVR without a headset", "steamvr" in ids, False)
check("every step says why and how", all(t["why"] and t["how"] for t in items), True)
rc, out = run(env, "todo", "--count")
check("the count is the whole list", out.strip(), str(len(items)))
before = len(logtext(d))
rc, _ = run(env, "run")
check("a second run does nothing again", "quiet_install.py run winget:GIMP" in logtext(d)[before:], False)
run(env, "done", "1")
rc, out = run(env, "todo", "--count")
check("a step can be ticked off", out.strip(), str(len(items) - 1))
rc, _ = run(env, "run")
rc, out = run(env, "todo", "--count")
check("a ticked step stays ticked after another run", out.strip(), str(len(items) - 1))

# two PCs, a headset, GitHub not signed in, and one step that fails
d, env = fresh(["pcs = 2", "bench_headset = real"], gh="no", fail="program:GIMP.GIMP.3")
rc, out = run(env, "run")
check("a failed step makes the run say so", rc, 1)
items = todo(env)
ids = [t["id"] for t in items]
check("the failed step is at the top of the list", ids[0] if ids else None, "retry:program:GIMP.GIMP.3")
check("GitHub not signed in: the sign-in is on the list", "github-signin" in ids, True)
check("and no GitHub setup was tried", "estate.py make" in logtext(d), False)
check("two PCs: the shared folder is on the list", "transfer-folder" in ids, True)
check("a headset: SteamVR is on the list", "steamvr" in ids, True)
conf = open(env["LANES_CONFIG"], encoding="utf-8").read()
check("two PCs: no background-upload setting is written", "keeper_mode" in conf, False)
before = len(logtext(d))
env["LANES_SETUP_FAIL"] = ""
env["LANES_SETUP_GH"] = "yes"
rc, _ = run(env, "run")
again = logtext(d)[before:]
check("the next run tries the failed step again", "winget:GIMP.GIMP.3" in again, True)
check("and the GitHub part, now signed in", "estate.py make" in again, True)
check("but not what was done", "ours.py get window_view" in again, False)
ids = [t["id"] for t in todo(env)]
check("the fixed step leaves the list", "retry:program:GIMP.GIMP.3" in ids, False)
check("and so does the GitHub sign-in", "github-signin" in ids, False)

# the extras' words: plain, and worded for one PC when there is one
env1 = dict(os.environ, LANES_CONFIG=os.path.join(d, "one.conf"), LANES_STATE_DIR=os.path.join(d, "fe"))
with open(env1["LANES_CONFIG"], "w") as f:
    f.write("pcs = 1\n")
q = subprocess.run([sys.executable, FE, "ask", "--json", "--all"], capture_output=True, text=True, env=env1,
                   encoding="utf-8").stdout
check("one PC: no extra talks about your other PC", "other PC" in q or "second PC" in q, False)
check("the recommended mark reaches setup's questions", '"recommended": false' in q, True)
lint = subprocess.run([sys.executable, FE, "lint"], capture_output=True, text=True, encoding="utf-8")
check("no jargon in what setup shows", lint.returncode, 0)

# the GitHub setup writes "board = <folder>   # note": the game-lock guard must still find the board (Workshop O6)
import importlib.util  # noqa: E402
conf = os.path.join(d, "noted.conf")
with open(conf, "w", encoding="utf-8") as f:
    f.write("board = C:/somewhere/board   # the shared work board (estate.py)\n")
os.environ["LANES_CONFIG"] = conf
spec = importlib.util.spec_from_file_location("guard", os.path.join(HERE, "..", "..", "hooks", "lane-claim-guard.py"))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
check("the game-lock guard reads the board past its note", guard.read_conf("board"), "C:/somewhere/board")
out = subprocess.run(["bash", "-c", "sed -n 's/^[[:space:]]*board[[:space:]]*=[[:space:]]*//p' \"$1\" | head -1 | "
                      "sed 's/[[:space:]]#.*$//; s/[[:space:]]*$//'", "x", conf.replace("\\", "/")],
                     capture_output=True, text=True).stdout.strip()
check("and so does the claim tool's way of reading it", out, "C:/somewhere/board")

print("setup_run: %d failed" % fails)
sys.exit(1 if fails else 0)
