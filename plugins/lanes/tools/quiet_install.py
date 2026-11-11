#!/usr/bin/env python3
"""quiet_install.py - install and update PC programs with no Windows "Yes" click, so a full scan never hangs on one
(0.110.0, 2026-11-11, feature `quiet_installs`). Windows only.

The maintainer, 2026-11-11: "is there any way to bypass the uac prompts, because many times i cannot actually be
present to click yes on them myself and that just leaves things hanging while fullscan is running", then: "building
a one time windows task with admin rights that Lanes uses for installs, that sounds like a solution".

    python quiet_install.py setup              ONE Yes click, once per PC: makes the protected folder and the task
    python quiet_install.py status             is it set up, and is its runner the one this Lanes ships (exit 0 = ready)
    python quiet_install.py probe              start the task with an empty order: proves it runs with admin rights
    python quiet_install.py run winget:<Id>[@<version>] ... [--upgrade] [--force] [--wait <minutes>]
                                               install (or --upgrade) each program; one line each; exit 1 if any failed
    python quiet_install.py uninstall          take the task and its folder away (one Yes click)

HOW IT WORKS
  setup starts tools/quiet-install/setup.ps1 with administrator rights. That makes a folder in ProgramData that only
  administrators can change, copies tools/quiet-install/runner.ps1 into it, and registers a Windows task that runs
  that copy with the highest rights, started by hand only. From then on `run` writes a small order into the folder's
  queue, starts the task (no Yes click: starting one's own task needs none) and reads the answer.

WHAT THE TASK CAN DO: only "install or upgrade this package id from the official winget catalogue, at this version".
  The runner builds the command line itself; an order cannot carry a program, a path or a switch. So the task is not
  a way to run anything as administrator. What it does allow: any program already running under this login can have
  a catalogue program installed without a Yes click. That is the trade this extra makes; switch it off to take it back.

WHEN IT IS NOT SET UP (or the extra is off, or the runner changed with a Lanes update and setup has not been run
  again): `run` installs the ordinary way, but never waits for ever: an install still running after DIRECT_LIMIT_MIN
  minutes is most likely sitting at a Yes click nobody is there to give, so it is stopped, marked SKIPPED and listed
  at the end for the person. A program whose maker offers only their own installer (not in the catalogue) is not
  handled here at all: say so and list it.

Tests set LANES_QUIET_ROOT (the folder), LANES_QUIET_FAKE (run the runner directly, no task) and LANES_QUIET_WINGET.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "lanes")
TASK = "Lanes quiet install"
FOLDER = "LanesQuietInstall"
RUNNER_SRC = os.path.join(HERE, "quiet-install", "runner.ps1")
SETUP_PS1 = os.path.join(HERE, "quiet-install", "setup.ps1")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]{1,99}$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,39}$")
MAX_ITEMS = 40
DEFAULT_WAIT_MIN = 45        # how long `run` waits for the task's answer, per order
DIRECT_LIMIT_MIN = 15        # without the task: an install still running after this is taken for a waiting Yes click
POLL_S = 2
MIN_S = 60                   # seconds in a minute
NUDGE_AFTER_S = 60           # an order still in the queue this long after the start: start the task again
SAID_CHARS = 200             # how much of an installer's or a tool's own words is passed on in one line
SETUP_WAIT_S = 300           # how long setup waits for the Yes click and the few seconds of work after it
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# winget's own "nothing to do" answers: the program is there already, or no newer version exists
WINGET_NOTHING_TO_DO = {-1978335189: "already up to date", -1978335135: "already installed",
                        2316632107: "already up to date", 2316632161: "already installed"}


def root():
    return os.environ.get("LANES_QUIET_ROOT") or os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), FOLDER)


def system_exe(*parts):
    return os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", *parts)


POWERSHELL = system_exe("WindowsPowerShell", "v1.0", "powershell.exe")


def sha256(path):
    """the file's fingerprint, the same whether git checked it out with Windows or Unix line ends"""
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()
    except OSError:
        return ""


def read_json(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def feature_on():
    try:
        import features
        return features.is_on("quiet_installs")
    except Exception:  # noqa: BLE001
        return False


def fake():
    return bool(os.environ.get("LANES_QUIET_FAKE"))


def task_exists():
    if fake():
        return os.path.isfile(os.path.join(root(), "runner.ps1"))
    p = subprocess.run([system_exe("schtasks.exe"), "/Query", "/TN", TASK], capture_output=True, text=True,
                       creationflags=NO_WINDOW)
    return p.returncode == 0


def ready():
    """(ready, one plain line)"""
    if os.name != "nt":
        return False, "quiet installs are for Windows only"
    if not feature_on():
        return False, "the extra quiet_installs is off"
    info = read_json(os.path.join(root(), "installed.json"))
    if not info or not task_exists():
        return False, "not set up on this PC yet: quiet_install.py setup (one Yes click, once)"
    if sha256(os.path.join(root(), "runner.ps1")) != sha256(RUNNER_SRC):   # the copy the task really runs
        return False, ("this Lanes version ships a newer runner than the one set up on this PC: "
                       "quiet_install.py setup again (one Yes click)")
    return True, "ready: installs from the Windows package catalogue need no Yes click"


# ----- setup / uninstall: the one Yes click -----
def elevated_setup(extra):
    """run setup.ps1 with administrator rights and hand back its report"""
    os.makedirs(STATE_DIR, exist_ok=True)
    report = os.path.join(STATE_DIR, "quiet-install-setup.json")
    try:
        os.remove(report)
    except OSError:
        pass
    args = ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", SETUP_PS1, "-Root", root(), "-Report", report] + extra
    if fake():                                    # tests: no rights are asked for; setup.ps1 itself refuses to go on
        p = subprocess.run([POWERSHELL] + args, capture_output=True, text=True, creationflags=NO_WINDOW)
        return read_json(report) or {"ok": False, "error": (p.stdout + p.stderr).strip()[:SAID_CHARS]}
    # Start-Process joins the list with spaces and quotes nothing: a path or name with a space is quoted here
    quoted = ", ".join("'%s'" % (('"%s"' % a) if " " in a else a).replace("'", "''") for a in args)
    cmd = "Start-Process -FilePath '%s' -ArgumentList %s -Verb RunAs -WindowStyle Hidden -Wait" % (POWERSHELL, quoted)
    try:
        p = subprocess.run([POWERSHELL, "-NoProfile", "-Command", cmd], capture_output=True, text=True,
                           timeout=SETUP_WAIT_S, creationflags=NO_WINDOW)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "nobody clicked Yes within %d minutes" % (SETUP_WAIT_S // MIN_S)}
    r = read_json(report)
    if r:
        return r
    said = (p.stdout + p.stderr).strip()
    if "canceled" in said.lower() or "cancelled" in said.lower():
        return {"ok": False, "error": "the Yes click was answered with No"}
    return {"ok": False, "error": said[:SAID_CHARS] or "setup wrote no report"}


def who():
    domain, user = os.environ.get("USERDOMAIN", ""), os.environ.get("USERNAME", "")
    return ("%s\\%s" % (domain, user)) if domain and user else user


def setup():
    if os.name != "nt":
        print("QUIET INSTALLS: Windows only.")
        return 1
    r = elevated_setup(["-Source", RUNNER_SRC, "-User", who(), "-TaskName", TASK])
    if not r.get("ok"):
        print("QUIET INSTALLS: not set up: %s" % r.get("error", "?"))
        return 1
    ok, line = ready()
    print("QUIET INSTALLS: set up. %s" % (line if ok or feature_on() else
                                          "Switch the extra on to use it: features.py on quiet_installs"))
    return 0


def uninstall():
    r = elevated_setup(["-Remove", "-TaskName", TASK])
    print("QUIET INSTALLS: taken off this PC." if r.get("ok") else "QUIET INSTALLS: not removed: %s" % r.get("error", "?"))
    return 0 if r.get("ok") else 1


# ----- orders -----
def parse_item(text, action, force):
    """'winget:Id' or 'winget:Id@1.2.3' -> the order's item, or None when it is not a catalogue id"""
    m = re.match(r"^(?:winget:)?([^@]+)(?:@(.+))?$", text.strip())
    if not m or not ID_RE.match(m.group(1)) or (m.group(2) and not VERSION_RE.match(m.group(2))):
        return None
    item = {"action": action, "package": m.group(1)}
    if m.group(2):
        item["version"] = m.group(2)
    if force and action == "install":
        item["force"] = True
    return item


def start_task():
    if fake():
        args = [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", os.path.join(root(), "runner.ps1"),
                "-TestRoot", root()]
        if os.environ.get("LANES_QUIET_WINGET"):
            args += ["-TestWinget", os.environ["LANES_QUIET_WINGET"]]
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
        return True, ""
    p = subprocess.run([system_exe("schtasks.exe"), "/Run", "/TN", TASK], capture_output=True, text=True,
                       creationflags=NO_WINDOW)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def order(items, wait_min=DEFAULT_WAIT_MIN):
    """hand one order to the task and wait for its answer: (answer dict or None, error line)"""
    rid = uuid.uuid4().hex
    queue, results = os.path.join(root(), "queue"), os.path.join(root(), "results")
    path = os.path.join(queue, rid + ".json")
    try:
        with open(path + ".part", "w", encoding="utf-8") as f:
            json.dump({"id": rid, "items": items}, f)
        os.replace(path + ".part", path)
    except OSError as e:
        return None, "could not write the order: %s" % e
    ok, said = start_task()
    if not ok:
        try:
            os.remove(path)
        except OSError:
            pass
        return None, "the task could not be started: %s" % said[:SAID_CHARS]
    end = time.time() + wait_min * MIN_S
    answer_path = os.path.join(results, rid + ".json")
    nudged = time.time()
    while time.time() < end:
        if os.path.isfile(answer_path):
            return read_json(answer_path), ""
        if os.path.isfile(path) and time.time() - nudged > NUDGE_AFTER_S:
            start_task()                 # the task was busy with an earlier order and has ended since: start it again
            nudged = time.time()
        time.sleep(POLL_S)
    return None, "no answer after %d minutes (the order stays queued; the task's log is in its folder)" % wait_min


def verdict(one):
    """(ok, plain words) for one item of an answer"""
    status, code = one.get("status"), one.get("exit")
    if status == "ran" and code == 0:
        return True, "done"
    if status == "ran" and code in WINGET_NOTHING_TO_DO:
        return True, WINGET_NOTHING_TO_DO[code]
    if status == "ran":
        return False, "the installer answered %s: %s" % (code, (one.get("tail") or "").strip()[:SAID_CHARS])
    if status == "timeout":
        return False, "SKIPPED: %s" % one.get("tail", "it took too long")
    return False, "%s: %s" % (status or "no answer", (one.get("tail") or "").strip()[:SAID_CHARS])


def run_direct(items, limit_min=DIRECT_LIMIT_MIN):
    """without the task: the ordinary way, but an install that sits at a Yes click is stopped, never waited on"""
    winget = os.environ.get("LANES_QUIET_WINGET") or "winget"
    out = []
    for it in items:
        cmd = [winget, it["action"], "--id", it["package"], "--exact", "--source", "winget", "--silent",
               "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity"]
        if it.get("version"):
            cmd += ["--version", it["version"]]
        if it.get("force"):
            cmd.append("--force")
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                 text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW,
                                 shell=winget.lower().endswith((".cmd", ".bat")))
        except OSError as e:
            out.append(dict(it, status="error", tail=str(e)))
            continue
        try:
            said, _ = p.communicate(timeout=limit_min * MIN_S)
            lines = [l.strip() for l in (said or "").splitlines() if re.search(r"[A-Za-z0-9]{3}", l)]
            out.append(dict(it, status="ran", exit=p.returncode, tail=" | ".join(lines[-4:])))
        except subprocess.TimeoutExpired:
            subprocess.run([system_exe("taskkill.exe"), "/T", "/F", "/PID", str(p.pid)], capture_output=True,
                           creationflags=NO_WINDOW)
            out.append(dict(it, status="timeout", tail="still running after %g minutes, most likely waiting for a "
                                                       "Yes click nobody was there to give" % limit_min))
    return out


def run(argv):
    action = "upgrade" if "--upgrade" in argv else "install"
    force = "--force" in argv
    wait_min = DEFAULT_WAIT_MIN
    limit_min = DIRECT_LIMIT_MIN
    names = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--wait", "--limit") and i + 1 < len(argv):
            try:
                if a == "--wait":
                    wait_min = float(argv[i + 1])
                else:
                    limit_min = float(argv[i + 1])
            except ValueError:
                pass
            i += 1
        elif not a.startswith("--"):
            names.append(a)
        i += 1
    items, bad = [], []
    for n in names:
        it = parse_item(n, action, force)
        (items if it else bad).append(it or n)
    for n in bad:
        print("QUIET INSTALLS: %s is not a catalogue id (winget:<Id> or winget:<Id>@<version>); left out." % n)
    if not items or len(items) > MAX_ITEMS:
        print("QUIET INSTALLS: nothing to install." if not items else "QUIET INSTALLS: at most %d at a time." % MAX_ITEMS)
        return 1 if bad or items else 0
    ok, why = ready()
    if ok:
        answer, err = order(items, wait_min)
        if answer is None or answer.get("error"):
            print("QUIET INSTALLS: %s" % (err or answer.get("error")))
            return 1
        answers = answer.get("items") or []
        how = "no Yes click"
    else:
        print("QUIET INSTALLS: %s. Installing the ordinary way; anything that waits for a Yes click is skipped." % why)
        answers = run_direct(items, limit_min)
        how = "the ordinary way"
    worst, skipped = 0, []
    for one in answers:
        good, words = verdict(one)
        print("%s %s %s: %s" % ("ok  " if good else "FAIL", one.get("action"), one.get("package"), words))
        if not good:
            worst = 1
            if one.get("status") == "timeout":
                skipped.append(one.get("package"))
    if skipped:
        print("FOR THE PERSON: these were skipped and still want installing by hand: %s" % ", ".join(skipped))
    print("QUIET INSTALLS: %d of %d done (%s)." % (sum(1 for o in answers if verdict(o)[0]), len(answers), how))
    return worst


def probe():
    ok, why = ready()
    if not ok:
        print("QUIET INSTALLS: %s" % why)
        return 1
    answer, err = order([], 2)
    if answer is None:
        print("QUIET INSTALLS: the task did not answer: %s" % err)
        return 1
    good = bool(answer.get("elevated")) or fake()
    print("QUIET INSTALLS: the task answered%s; winget %s."
          % (" with administrator rights" if answer.get("elevated") else " WITHOUT administrator rights",
             answer.get("winget") or "not found"))
    return 0 if good and (answer.get("winget") or fake()) else 1


def main(argv):
    verb = argv[0] if argv else "status"
    if verb == "setup":
        return setup()
    if verb == "uninstall":
        return uninstall()
    if verb == "status":
        ok, line = ready()
        print("QUIET INSTALLS: %s" % line)
        return 0 if ok else 1
    if verb == "probe":
        return probe()
    if verb == "run":
        return run(argv[1:])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
