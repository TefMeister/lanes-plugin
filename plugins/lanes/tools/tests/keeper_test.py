"""keeper_test.py - the Keeper: hand-overs, the background upload of the one-PC mode, the regular jobs, the queue,
and which processes count as sessions (0.108.0, 2026-11-11).

In a temp folder: a pretend GitHub (bare repos), a clone root for the session that builds, one for the Keeper, a
pretend transfer folder and a board. Nothing listens on a network and no window is opened. Exit 0 = pass."""
import json
import os
import stat
import subprocess
import sys
import tempfile
import time

T = tempfile.mkdtemp(prefix="keeper-")
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
PARCEL = os.path.join(TOOLS, "parcel.py")
KEEPER = os.path.join(TOOLS, "keeper.py")
fails = 0


def check(ok, what):
    global fails
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        fails += 1


def sh(args, cwd=None, env=None):
    p = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout + p.stderr).strip()


def git(args, cwd):
    return sh(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "core.autocrlf=false"] + args, cwd)


def p(*parts):
    return os.path.join(T, *parts).replace("\\", "/")


def side(name, **settings):
    """a pretend PC: its own lanes.conf and state folder; returns the environment its tools run in"""
    conf = p(name + ".conf")
    with open(conf, "w", encoding="utf-8") as f:
        f.write("".join("%s = %s\n" % kv for kv in settings.items()))
    return dict(os.environ, LANES_CONFIG=conf, LANES_STATE_DIR=p("state-" + name), LANES_CONF=conf)


def tool(script, args, env):
    return sh([sys.executable, script] + args, env=env)


def commit(repo, text, msg):
    with open(os.path.join(repo, "a.txt"), "a", encoding="utf-8") as f:
        f.write(text + "\n")
    git(["commit", "-q", "-am", msg], repo)


def hub_steps(name="proj"):
    return int(git(["rev-list", "--count", "main"], p(name + ".git"))[1] or 0)


# ----- the pretend world -----
for d in ("dev", "keeper", "transfer", "one"):
    os.makedirs(p(d))
for repo_name in ("proj", "solo", "board"):
    git(["init", "-q", "--bare", "-b", "main", p(repo_name + ".git")], T)
git(["clone", "-q", p("proj.git"), p("dev", "proj")], T)
git(["checkout", "-q", "-b", "main"], p("dev", "proj"))
open(p("dev", "proj", "a.txt"), "w").write("one\n")
git(["add", "a.txt"], p("dev", "proj"))
git(["commit", "-q", "-m", "first"], p("dev", "proj"))
git(["push", "-q", "-u", "origin", "main"], p("dev", "proj"))
git(["clone", "-q", p("proj.git"), p("keeper", "proj")], T)
git(["clone", "-q", p("board.git"), p("board")], T)
git(["checkout", "-q", "-b", "main"], p("board"))
open(p("board", "README.md"), "w").write("board\n")
git(["add", "README.md"], p("board"))
git(["commit", "-q", "-m", "board"], p("board"))
git(["push", "-q", "-u", "origin", "main"], p("board"))

DEV = side("dev", machine_name="A", root=p("dev"), transfer=p("transfer"), keeper_mode="other_pc",
           keeper_role="developer", board=p("board"), doorman_peer="127.0.0.1", doorman_port="1")
KEEP = side("keeper", machine_name="B", root=p("nowhere"), parcel_root=p("keeper"), transfer=p("transfer"),
            keeper_mode="other_pc", keeper_role="keeper")

# ----- two PCs: hand-overs -----
rc, out = tool(PARCEL, ["send", "proj"], DEV)
check(rc == 0 and "no saved step" in out, "nothing to hand over when everything is on GitHub")

commit(p("dev", "proj"), "two", "second step")
commit(p("dev", "proj"), "three", "third step")
rc, out = tool(PARCEL, ["send", "proj", "--note", "the menu opens in the headset"], DEV)
check(rc == 0 and "2 step(s)" in out, "two saved steps are sealed into one parcel")
rc, out = tool(PARCEL, ["send", "proj"], DEV)
check("already handed over" in out, "the same steps are not handed over twice")
rc, out = tool(PARCEL, ["light"], DEV)
check("waiting for the Keeper: proj" in out, "the light line says what waits for the Keeper")
rc, out = tool(PARCEL, ["receive"], KEEP)
check(rc == 0 and "on GitHub" in out and hub_steps() == 3, "the Keeper checks, uploads and answers (parcel_root, not root)")
receipts = [json.load(open(os.path.join(p("transfer", "parcels", "receipts"), n), encoding="utf-8"))
            for n in os.listdir(p("transfer", "parcels", "receipts"))]
check(receipts and receipts[0].get("note") == "the menu opens in the headset", "the note travels to the receipt")
rc, out = tool(PARCEL, ["light"], DEV)
check(rc == 0 and "everything this PC saved is on GitHub" in out, "the light line is plain once it is uploaded")

# the Keeper has a step the other side has not got: refused, never forced
open(p("keeper", "proj", "k.txt"), "w").write("k\n")
git(["add", "k.txt"], p("keeper", "proj"))
git(["commit", "-q", "-m", "the Keeper's own step"], p("keeper", "proj"))
git(["push", "-q"], p("keeper", "proj"))
commit(p("dev", "proj"), "four", "fourth step")
tool(PARCEL, ["send", "proj"], DEV)
rc, out = tool(PARCEL, ["receive"], KEEP)
check(rc == 1 and "refused" in out and "pull there and hand over again" in out, "a parcel that does not fit is refused with the reason")
rc, out = tool(PARCEL, ["light"], DEV)
check(rc == 1 and "REFUSED" in out, "the light line shows a refusal in red and fails")
git(["pull", "-q", "--rebase"], p("dev", "proj"))
tool(PARCEL, ["send", "proj"], DEV)
rc, out = tool(PARCEL, ["receive"], KEEP)
check(rc == 0 and hub_steps() == 5, "after a pull it is handed over again and uploaded")

# a parcel that has not fully arrived is left alone
commit(p("dev", "proj"), "five", "fifth step")
tool(PARCEL, ["send", "proj"], DEV)
bundle = [os.path.join(p("transfer", "parcels", "outbox"), n) for n in os.listdir(p("transfer", "parcels", "outbox"))
          if n.endswith(".bundle")][0]
whole = open(bundle, "rb").read()
open(bundle, "wb").write(whole[:100])
rc, out = tool(PARCEL, ["receive"], KEEP)
check("still arriving" in out and hub_steps() == 5, "a half-synced parcel is not opened")
open(bundle, "wb").write(whole)

# an upload stopped by a check: the Keeper's copy goes back, the reason travels, a repaired one goes through
hook = p("keeper", "proj", ".git", "hooks", "pre-push")
open(hook, "w", newline="\n").write("#!/bin/sh\necho 'privacy guard: refused (test)' >&2\nexit 1\n")
os.chmod(hook, os.stat(hook).st_mode | stat.S_IEXEC)
before = git(["rev-parse", "HEAD"], p("keeper", "proj"))[1]
rc, out = tool(PARCEL, ["receive"], KEEP)
check(rc == 1 and "privacy guard: refused" in out, "an upload a check refuses is reported with the check's words")
check(git(["rev-parse", "HEAD"], p("keeper", "proj"))[1] == before, "and the Keeper's copy is back where it was")
os.remove(hook)
tool(PARCEL, ["send", "proj"], DEV)
rc, out = tool(PARCEL, ["receive"], KEEP)
check(rc == 0 and hub_steps() == 6 and not os.listdir(p("transfer", "parcels", "outbox")),
      "once repaired it is sent again and the outbox is empty")

# ----- one PC: the upload runs in the background from the working copy -----
git(["clone", "-q", p("solo.git"), p("one", "solo")], T)
git(["checkout", "-q", "-b", "main"], p("one", "solo"))
open(p("one", "solo", "a.txt"), "w").write("one\n")
git(["add", "a.txt"], p("one", "solo"))
git(["commit", "-q", "-m", "first"], p("one", "solo"))
git(["push", "-q", "-u", "origin", "main"], p("one", "solo"))
ONE = side("one", machine_name="A", root=p("one"), keeper_mode="this_pc")
commit(p("one", "solo"), "two", "second step")
rc, out = tool(PARCEL, ["send", "solo", "--note", "a note"], ONE)
check(rc == 0 and "in the background" in out, "one PC: the hand-over returns at once")
deadline = time.time() + 30
while time.time() < deadline and hub_steps("solo") < 2:
    time.sleep(0.5)
check(hub_steps("solo") == 2, "one PC: the background upload reaches GitHub")
time.sleep(1)
rc, out = tool(PARCEL, ["light"], ONE)
check(rc == 0 and "everything this PC saved is on GitHub" in out, "one PC: the light line is plain afterwards")
check(not os.path.isdir(p("transfer", "parcels", "outbox")) or not os.listdir(p("transfer", "parcels", "outbox")),
      "one PC: nothing was written to a transfer folder")

# ----- the regular jobs: reminded until done -----
rc, out = tool(KEEPER, ["due"], DEV)
check(rc == 1 and "KEEPER JOB DUE" in out and "/lanes:fullscan" in out and "every session until it is done" in out,
      "a regular job never done is due, with the exact thing to type")
rc, out = tool(KEEPER, ["due"], DEV)
check(rc == 1, "and it is due again at the next start (it does not stop by being said)")
rc, out = tool(KEEPER, ["done", "fullscan"], KEEP if False else DEV)
rc, out = tool(KEEPER, ["due"], DEV)
check(rc == 0, "once the Keeper marks it done the reminder stops")
check("jobs.tsv" in git(["ls-tree", "-r", "--name-only", "main"], p("board.git"))[1], "the jobs list is saved on the board")

# ----- a job for the Keeper session: queued even when the Keeper cannot be reached -----
rc, out = tool(KEEPER, ["ask", "refresh the front page row of proj", "--project", "proj"], DEV)
check(rc == 1 and "job is queued" in out and "not reachable" in out, "a job is queued when the Keeper PC is off")
rc, out = tool(KEEPER, ["round"], DEV)
check("refresh the front page row of proj" in out and "Uploaded since the last round" in out, "the round lists the queued job")
check("the menu opens in the headset" in out, "the round shows each upload's note")
rc, out = tool(KEEPER, ["wanted"], DEV)
check(rc == 0 and "1 queued job(s)" in out and "0 upload(s)" not in out and not out.startswith("0"),
      "what waits for a round is counted: the queued job and the uploads with a sentence")
queued = [n for n in os.listdir(p("board", "keeper", "queue")) if n.endswith(".md")]
rc, out = tool(KEEPER, ["finish", queued[0]], DEV)
check(rc == 0 and os.path.isfile(p("board", "keeper", "queue", "done", queued[0])), "a finished job leaves the queue")
rc, out = tool(KEEPER, ["brief"], DEV)
check("THE KEEPER PC IS OFF" in out and "ONE line" in out, "session start says loudly when the Keeper PC is off")
rc, out = tool(KEEPER, ["brief"], KEEP)
check(out == "", "the Keeper's own side prints nothing at its start")
tool(KEEPER, ["round", "--mark"], DEV)
rc, out = tool(KEEPER, ["wanted"], DEV)
check(rc == 0 and out.startswith("0"), "after a round nothing waits")

# ----- one round at a time (0.112.0): two Keeper windows ran a round together on 2026-11-11 -----
A = dict(DEV, CLAUDE_CODE_SESSION_ID="window-a")
B = dict(DEV, CLAUDE_CODE_SESSION_ID="window-b")
rc, out = tool(KEEPER, ["round"], A)
check(rc == 0 and "THE KEEPER'S ROUND" in out, "one round at a time: the first window's round runs")
rc, out = tool(KEEPER, ["round"], B)
check(rc == 3 and "ANOTHER KEEPER ROUND IS RUNNING" in out and "window-a"[:8] in out,
      "a second window's round is stopped and told who runs one")
rc, out = tool(KEEPER, ["round", "--mark"], B)
check(rc == 3, "the second window cannot mark the other's round done")
rc, out = tool(KEEPER, ["wanted"], B)
check(out.startswith("0") and "running now" in out, "while a round runs, the doorman is told nothing waits")
rc, out = tool(KEEPER, ["round"], A)
check(rc == 0, "the same window may look at its round again")
rc, out = tool(KEEPER, ["round", "--mark"], A)
check(rc == 0 and "marked done" in out, "the first window marks its round done")
rc, out = tool(KEEPER, ["round"], B)
check(rc == 0 and "THE KEEPER'S ROUND" in out, "after it, the other window's round runs")
lock = p("state-dev", "keeper-round.lock")
with open(lock, encoding="utf-8") as f:
    d = json.load(f)
d["at"] = time.time() - 61 * 60
with open(lock, "w", encoding="utf-8") as f:
    json.dump(d, f)
rc, out = tool(KEEPER, ["round"], A)
check(rc == 0, "a round cut off an hour ago no longer stops a new one")
tool(KEEPER, ["round", "--mark"], A)

# ----- 0.113.0: the Keeper opens a window of its own on the Developer PC -----
rc, out = tool(KEEPER, ["developer", "Keeper job"], DEV)
check(rc == 1 and "only the Keeper PC" in out, "the Developer PC cannot open a Keeper window on itself")
rc, out = tool(KEEPER, ["developer", "Keeper job"], KEEP)
check(rc == 1 and "could not open a window on the Developer PC" in out and "doorman_peer" in out,
      "with no doorman_peer the Keeper says why it cannot open the window, and opens nothing")

# ----- which processes are sessions -----
os.environ["LANES_STATE_DIR"] = p("state-unit")
sys.path.insert(0, TOOLS)
import doorman as D  # noqa: E402

D.processes = lambda: {
    10: (1, "explorer.exe"), 20: (10, "windowsterminal.exe"), 21: (20, "claude.exe"),          # a terminal session
    30: (10, "claude.exe"), 31: (30, "claude.exe"), 32: (30, "claude.exe"),                    # the desktop app
    40: (20, "cmd.exe"), 41: (40, "claude.exe"), 42: (41, "claude.exe"),                       # via cmd, plus a helper
}
check(D.session_pids() == [21, 41], "only terminal sessions count: not the desktop app, not a session's helper")
check(D.clean_name('Keeper; "link" & more') == "Keeper link  more", "a window's name cannot carry command characters")

# ----- the wake (0.109.0): a round is started by the doorman itself, never typed into a window opened by hand -----
check(not D.should_ask(0, None, 100.0), "nothing waits: no round is asked for")
check(D.should_ask(1, None, 100.0), "something waits and nothing was asked: a round is asked for")
check(not D.should_ask(1, {"at": 90.0, "count": 1}, 100.0), "a round already asked for is not asked for twice")
check(D.should_ask(2, {"at": 90.0, "count": 1}, 100.0), "more arrived since: asked again")
check(D.should_ask(1, {"at": 0.0, "count": 1}, D.WAKE_AGAIN_S + 1.0), "asked long ago and still waiting: asked again")
check(sorted(D.TYPED.values()) == ["/exit", "/lanes:keeper"], "only two fixed texts can ever be typed into a session")

KEEPER_CONF = {"keeper": "on", "keeper_mode": "other_pc", "keeper_role": "keeper"}
D.conf = lambda: dict(KEEPER_CONF)
check(D.wake_on(), "the wake is on for the Keeper PC")
D.conf = lambda: dict(KEEPER_CONF, keeper_role="developer")
check(not D.wake_on(), "and off on the PC that builds")
D.conf = lambda: dict(KEEPER_CONF, keeper_wake="off")
check(not D.wake_on(), "and off when keeper_wake = off")
D.conf = lambda: dict(KEEPER_CONF)

waiting, opened, typed, sessions = [2], [], [], []
D.round_wanted = lambda pull=False: waiting[0]
D.list_sessions = lambda: list(sessions)
D.open_session = lambda name="", first="": (opened.append(first), {"ok": True, "pid": 77})[1]


class Ran:
    returncode, stdout, stderr = 0, "", ""


D.subprocess.run = lambda args, **kw: (typed.append(args[-3:]), Ran())[1]
r = D.wake_keeper()
check(r.get("asked") and opened == ["/lanes:keeper"] and not typed, "no link window: one is opened that starts with the round")
r = D.wake_keeper()
check(not r.get("asked") and len(opened) == 1, "the same waiting work does not open a second window")
sessions[:] = [{"pid": 5, "by_doorman": False, "name": ""}, {"pid": 77, "by_doorman": True, "name": "Keeper link"}]
waiting[0] = 3
r = D.wake_keeper()
check(r.get("asked") and typed == [["_type", "77", "round"]] and len(opened) == 1,
      "a link window is open: the round is typed into it, never into the window opened by hand")
waiting[0] = 0
r = D.wake_keeper()
check(not r.get("asked") and "round_asked" not in D.read_state(), "the round done: the doorman forgets it asked")

print()
print("keeper_test.py: %s" % ("all passed" if not fails else "%d FAILED" % fails))
sys.exit(1 if fails else 0)
