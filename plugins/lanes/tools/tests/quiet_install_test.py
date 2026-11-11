"""quiet_install_test.py - installs with no Yes click: what an order may carry, the runner's refusals, the answer,
and the skip when nothing is set up (0.110.0, 2026-11-11).

Nothing here asks for administrator rights, makes a Windows task or installs anything: the runner is started directly
in a temp folder (LANES_QUIET_FAKE) with a pretend winget that only writes down what it was asked. Windows only; on
another system it passes without running. Exit 0 = pass."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
QI = os.path.join(TOOLS, "quiet_install.py")
RUNNER = os.path.join(TOOLS, "quiet-install", "runner.ps1")
fails = 0


def check(ok, what):
    global fails
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        fails += 1


if os.name != "nt":
    print("quiet_install_test: skipped (Windows only)")
    sys.exit(0)

sys.path.insert(0, TOOLS)
import quiet_install as Q  # noqa: E402

T = tempfile.mkdtemp(prefix="quiet-")
ROOT = os.path.join(T, "root")
for d in ("queue", "results"):
    os.makedirs(os.path.join(ROOT, d))
ASKED = os.path.join(T, "asked.txt")
FAKE = os.path.join(T, "winget.cmd")
with open(FAKE, "w", encoding="ascii") as f:        # a pretend winget: writes down its orders, answers like the real one
    f.write("@echo off\r\n"
            "if \"%1\"==\"--version\" (echo v0.0.test& exit /b 0)\r\n"
            "echo %*>>\"" + ASKED + "\"\r\n"
            "echo Found the package\r\n"
            "echo %* | findstr /C:\"Broken.App\" >nul && exit /b 5\r\n"
            "echo %* | findstr /C:\"Slow.App\" >nul && (ping -n 30 127.0.0.1 >nul & exit /b 0)\r\n"
            "echo %* | findstr /C:\"Same.App\" >nul && exit /b -1978335189\r\n"
            "exit /b 0\r\n")


def env(**more):
    conf = os.path.join(T, "lanes.conf")
    with open(conf, "w", encoding="utf-8") as f:
        f.write("machine_name = B\nquiet_installs = %s\n" % more.pop("extra", "on"))
    e = dict(os.environ, LANES_CONFIG=conf, LANES_STATE_DIR=os.path.join(T, "state"), LANES_QUIET_ROOT=ROOT,
             LANES_QUIET_FAKE="1", LANES_QUIET_WINGET=FAKE)
    e.update(more)
    return e


def qi(args, e):
    p = subprocess.run([sys.executable, QI] + args, env=e, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return p.returncode, (p.stdout + p.stderr).strip()


def asked():
    try:
        return open(ASKED, encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


# ----- what an order may carry -----
check(Q.parse_item("winget:Git.Git", "install", False) == {"action": "install", "package": "Git.Git"}, "a plain id")
check(Q.parse_item("winget:Git.Git@2.47.0", "upgrade", True) == {"action": "upgrade", "package": "Git.Git", "version": "2.47.0"},
      "an id at a version; --force only goes with install")
for bad in ("winget:Git.Git --override x", "winget:a&calc", "winget:..\\x", "winget:Git.Git@1 2", "winget:", "winget:a;b",
            "winget:Git.Git@$(x)", "winget:\"x\""):
    check(Q.parse_item(bad, "install", False) is None, "refused before it is even written: %r" % bad)

# ----- not set up: status says so -----
rc, out = qi(["status"], env())
check(rc == 1 and "not set up" in out, "status: not set up yet (one Yes click, once)")

# ----- set up (pretend: the runner copied in, its fingerprint noted) -----
shutil.copy(RUNNER, os.path.join(ROOT, "runner.ps1"))
with open(os.path.join(ROOT, "installed.json"), "w", encoding="utf-8") as f:
    json.dump({"sha256": Q.sha256(RUNNER)}, f)
rc, out = qi(["status"], env())
check(rc == 0 and "ready" in out, "status: ready once the task and this version's runner are there")
rc, out = qi(["status"], env(extra="off"))
check(rc == 1 and "off" in out, "the extra switched off: not ready")
rc, out = qi(["probe"], env())
check(rc == 0 and "answered" in out and "v0.0.test" in out, "probe: an empty order comes back answered")

# ----- orders through the runner -----
rc, out = qi(["run", "winget:Good.App", "winget:Pinned.App@1.2.3", "--force"], env())
a = asked()
check(rc == 0 and "2 of 2 done (no Yes click)" in out, "two installs go through the task and are reported done")
check("install --id Good.App --exact --source winget --silent" in a and "--disable-interactivity" in a,
      "the runner builds the whole command line itself (official catalogue only, silent)")
check("--id Pinned.App" in a and "--version 1.2.3" in a and "--force" in a, "a version and --force are passed on")
rc, out = qi(["run", "winget:Same.App", "--upgrade"], env())
check(rc == 0 and "already up to date" in out and "upgrade --id Same.App" in asked(), "nothing newer counts as done")
rc, out = qi(["run", "winget:Broken.App", "winget:Good.App"], env())
check(rc == 1 and "FAIL install Broken.App" in out and "ok   install Good.App" in out,
      "a failed install is said, with the installer's answer; the others still run")
rc, out = qi(["run", "winget:a&calc", "winget:Good.App"], env())
check("not a catalogue id" in out and "calc" not in asked(), "a bad id is left out and never reaches the runner")
check(not os.listdir(os.path.join(ROOT, "queue")), "answered orders leave the queue")

# ----- the runner refuses what it is not for, even when an order is written by hand -----


def hand_order(items, name="0123456789abcdef0123456789abcdef"):
    with open(os.path.join(ROOT, "queue", name + ".json"), "w", encoding="utf-8") as f:
        json.dump({"id": name, "items": items}, f)
    subprocess.run([Q.POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", os.path.join(ROOT, "runner.ps1"),
                    "-TestRoot", ROOT, "-TestWinget", FAKE], capture_output=True)
    return Q.read_json(os.path.join(ROOT, "results", name + ".json"))


before = asked()
r = hand_order([{"action": "uninstall", "package": "Good.App"}, {"action": "install", "package": "x --override calc"},
                {"action": "install", "package": "Good.App", "version": "1; calc"},
                {"action": "install", "package": "Good.App\" --location \"C:\\x"}])
check(len(r.get("items", [])) == 4 and all(i["status"] == "refused" for i in r["items"]) and asked() == before,
      "by hand: another action, a switch in the id, a bad version: all refused, winget never started")
r = hand_order([{"action": "install", "package": "Good.App"}] * 41)
check("more than" in r.get("error", "") and asked() == before, "by hand: an over-long order is refused whole")
with open(os.path.join(ROOT, "queue", "run-me.json"), "w") as f:
    f.write("{}")
hand_order([])
check(os.path.isfile(os.path.join(ROOT, "queue", "run-me.json")), "by hand: a file with another kind of name is not read")
os.remove(os.path.join(ROOT, "queue", "run-me.json"))

# ----- a runner that changed with a Lanes update needs setup again -----
with open(os.path.join(ROOT, "runner.ps1"), "rb") as f:
    body = f.read()
with open(os.path.join(ROOT, "runner.ps1"), "wb") as f:
    f.write(body.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
check(qi(["status"], env())[0] == 0, "other line ends in the installed copy (git's doing) are not a change")
with open(os.path.join(ROOT, "runner.ps1"), "ab") as f:
    f.write(b"# an older runner\r\n")
rc, out = qi(["status"], env())
check(rc == 1 and "setup again" in out, "a newer runner in the plugin: setup again (one Yes click), never the old one silently")

# ----- not set up: the ordinary way, and nothing hangs -----
rc, out = qi(["run", "winget:Good.App", "winget:Slow.App", "--limit", "0.05"], env())
check("ordinary way" in out and "ok   install Good.App" in out, "not set up: installs the ordinary way")
check(rc == 1 and "SKIPPED" in out and "FOR THE PERSON" in out and "Slow.App" in out,
      "an install that would sit at a Yes click is stopped, skipped and listed for the person")

shutil.rmtree(T, ignore_errors=True)
print("quiet_install_test: %s" % ("all passed" if not fails else "%d FAILED" % fails))
sys.exit(1 if fails else 0)
