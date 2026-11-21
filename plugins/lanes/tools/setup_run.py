#!/usr/bin/env python3
"""setup_run.py - setup's recommended way: install everything that needs nobody in one go, and keep the steps that
need the person in one list for the very end (0.121.0, 2026-11-21).

Tefa, 2026-11-21: "the option to install everything and leave for work, then come back in the evening and it's all
set up, leave the manual installs that need the user for the very last thing. or have the option to go through things
one by one." The one-by-one way is /lanes:setup's walk-through; this is the other one.

    python setup_run.py plan [--json]        what `run` would do on this PC, and what it would leave for you; does nothing
    python setup_run.py start                the ONE Windows Yes click, while the person is still at the PC: it sets up
                                             the no-click installer (quiet_install.py setup); after it no install waits
    python setup_run.py run                  everything that needs nobody, in one command (so Claude Code asks permission
                                             once, not at every step while nobody is there); can be run again: what is
                                             done is skipped, what failed is tried again
    python setup_run.py todo [--json|--count]  the "What needs you" list; --count prints only how many are left
    python setup_run.py done <n>|all         tick a step of that list off

WHAT IT READS (asked at setup's start, before `run`): `pcs` (1 or 2) and `bench_headset` (real / none) in lanes.conf.
WHAT IT DOES: every extra marked recommended in features.py on (the rest off); every catalog program with a package in
the Windows catalogue (through quiet_install.py), the Python packages, Lanes' own installers (the live-game connectors,
the pretend headset with VR Bench, Hand Freeze), all of our own apps and the other makers' tools, the Claude Code
plugins and the Blender link, the settings setup's questions would set to their recommended answer, and the GitHub setup
when GitHub is signed in already (estate.py; all private). Anything that needs a person (a sign-in, a click inside
another program, a maker's own installer, a sign-up form) and anything that failed goes on the list, in plain words.
The run's own log: <state>/setup-run.log; its record: <state>/setup-run.json.
Tests: LANES_STATE_DIR, LANES_CONFIG, LANES_SETUP_FAKE=1 (no command runs; each is logged and counts as done),
LANES_SETUP_FAIL=<step id,...> (those fail), LANES_SETUP_SCAN=<file> (a setup-scan.py --json answer to use).
"""
import json
import os
import subprocess
import sys
import urllib.request
import zipfile
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
HOME = os.path.expanduser("~")
STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(HOME, ".claude", "lanes")
RECORD = os.path.join(STATE_DIR, "setup-run.json")
LOG = os.path.join(STATE_DIR, "setup-run.log")
LOCALAPPDATA = os.environ.get("LOCALAPPDATA", os.path.join(HOME, "AppData", "Local"))
FAKE = os.environ.get("LANES_SETUP_FAKE") == "1"
FAIL = {s.strip() for s in os.environ.get("LANES_SETUP_FAIL", "").split(",") if s.strip()}
PY = sys.executable or "python"
START_PATH = os.environ.get("PATH", "")
STEP_TIMEOUT_S = 3 * 60 * 60     # one step (a compiler build, a big download) may take long, but never for ever
INSTALL_WAIT_MIN = "60"          # quiet_install.py --wait: the compiler zip alone took over 30 minutes (FAULTS 2026-11-21)
DEFAULT_ROOT = os.path.join(HOME, "github-backups")   # the clone root when lanes.conf names none
REALESRGAN_ZIP = ("https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/"
                  "realesrgan-ncnn-vulkan-20220424-windows.zip")   # the newest release with a Windows zip (TOOLS.md)

# Catalog rows (setup-scan.py ids) that the Windows package catalogue installs, in the order they are needed.
WINGET = [("git", "Git.Git"), ("gh", "GitHub.cli"), ("uv", "astral-sh.uv"), ("7zip", "7zip.7zip"),
          ("cmake", "Kitware.CMake"), ("rust", "Rustlang.Rustup"), ("lua", "DEVCOM.Lua"),
          ("x64dbg", "x64dbg.x64dbg"), ("vigembus", "ViGEm.ViGEmBus"), ("blender", "BlenderFoundation.Blender"),
          ("gimp", "GIMP.GIMP.3"), ("obs", "OBSProject.OBSStudio"), ("ffmpeg", "Gyan.FFmpeg"),
          ("dotnet10", "Microsoft.DotNet.SDK.10"), ("llvm-mingw", "MartinStorsjo.LLVM-MinGW.UCRT")]
PIP = [("pypkgs", ["pefile", "capstone", "pillow", "psutil", "pywin32", "numpy"]), ("vgamepad", ["vgamepad"]),
       ("obsws", ["obsws-python"]), ("x64dbg-automate", ["x64dbg-automate"])]

# Steps only a person can do, always on the list (catalog rows marked "you", or a click inside another program).
# (id, title, why, how, when): when = None (always), "headset", "two_pcs".
PERSON = [
    ("vsbuildtools", "Visual Studio Build Tools (Microsoft's C++ compiler)",
     "some mods must be built with Microsoft's own compiler (REFramework plugins, Window View, VR Bench)",
     "say \"install Visual Studio Build Tools\": one Windows Yes click, then about half an hour on its own", None),
    ("blender-clicks", "Two clicks inside Blender",
     "they connect Claude to Blender, so it can build and change 3D models with you",
     "open Blender: Edit, Preferences, Add-ons, tick \"Interface: MCP for Blender\"; then in the 3D view press N, "
     "open the MCP for Blender tab and click Start MCP Server", None),
    ("x64dbg-link", "Connect Claude to the x64dbg debugger",
     "it lets Claude pause a running game and read it without you clicking anything",
     "say \"finish the x64dbg link\": Claude copies the plugin from its maker's page and adds the link with you", None),
    ("gimp-link", "Connect Claude to GIMP",
     "it lets Claude crop, clean and colour pictures inside GIMP while you watch",
     "open GIMP once (it makes its folders), then say \"finish the GIMP link\"", None),
    ("source-record", "Source Record for OBS",
     "it lets OBS film one window on its own, which the VR test recordings use",
     "say \"install Source Record\": its maker's installer opens and Windows asks one Yes", None),
    ("resolve", "DaVinci Resolve (free video editor)",
     "for cutting your own videos; Claude does not need it",
     "download it from blackmagicdesign.com/products/davinciresolve (a short sign-up form first) and install it", None),
    ("steamless", "Steamless",
     "it unwraps a Steam game's program so it can be read; only needed for some games",
     "download the newest zip from github.com/atom0s/Steamless/releases, unzip it anywhere, and tell Claude where", None),
    ("re-mesh-editor", "RE Mesh Editor for Blender",
     "it opens the 3D models of Resident Evil games in Blender; only needed for those games",
     "say \"install RE Mesh Editor\" when you start such a game", None),
    ("steamvr", "SteamVR", "the program most PC VR games talk to the headset through",
     "install it from Steam (search SteamVR in the Steam store)", "headset"),
    ("virtual-desktop", "Virtual Desktop (Quest headsets only)",
     "streams PC VR to a Quest without a cable",
     "buy it on the headset's store, then install the free Streamer from vrdesktop.net", "headset"),
    ("transfer-folder", "A synced folder for your two PCs",
     "big files that must never go on GitHub (recordings, game files) travel between your PCs through it",
     "say \"set up the transfer folder\": Claude gives the steps (a free MEGA account, its app, one folder)", "two_pcs"),
]


# ---------------------------------------------------------------- small helpers

def now():
    return datetime.now().isoformat(timespec="seconds")


def log(line):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{now()}  {line}\n")


def conf_file():
    if os.environ.get("LANES_CONFIG"):
        return os.environ["LANES_CONFIG"]
    return os.path.join(HOME, ".claude", "lanes.conf")


def conf_value(key):
    try:
        for line in open(conf_file(), encoding="utf-8"):
            k, _, v = line.partition("=")
            if k.strip() == key:
                return v.split("#")[0].strip().strip('"')
    except OSError:
        pass
    return None


def conf_set(key, value, note):
    p = conf_file()
    try:
        lines = open(p, encoding="utf-8").read().splitlines()
    except OSError:
        lines = []
    if any(l.partition("=")[0].strip() == key for l in lines):
        return False                                   # never overwrite what the person (or an earlier run) set
    lines.append(f"{key} = {value}   # {note} (setup_run.py)")
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    return True


def tool(name):
    return os.path.join(HERE, name)


def refresh_path():
    """A program installed a minute ago is not on this process's PATH yet: read Windows' saved PATH again."""
    if os.name != "nt":
        return
    try:
        import winreg
        parts = []
        for hive, key in ((winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                          (winreg.HKEY_CURRENT_USER, r"Environment")):
            try:
                with winreg.OpenKey(hive, key) as k:
                    parts.append(os.path.expandvars(winreg.QueryValueEx(k, "Path")[0]))
            except OSError:
                pass
        extra = [os.path.join(HOME, ".cargo", "bin"), os.path.join(HOME, ".local", "bin")]
        seen, out = set(), []
        for p in os.pathsep.join(parts + extra + [START_PATH]).split(os.pathsep):   # rebuilt each time, never grown
            if p and p.lower() not in seen:
                seen.add(p.lower())
                out.append(p)
        os.environ["PATH"] = os.pathsep.join(out)
    except ImportError:
        pass


def sh(step_id, args, timeout=STEP_TIMEOUT_S, cwd=None):
    """Run one command of a step. Returns (ok, last lines of its output)."""
    shown = " ".join(str(a) for a in args)
    if step_id in FAIL:
        log(f"[{step_id}] (test: made to fail) {shown}")
        return False, "made to fail by the test"
    if FAKE:
        log(f"[{step_id}] would run: {shown}")
        return True, "fake"
    log(f"[{step_id}] {shown}")
    try:
        p = subprocess.run([str(a) for a in args], capture_output=True, text=True, timeout=timeout, cwd=cwd,
                           encoding="utf-8", errors="replace", env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        out = ((p.stdout or "") + (p.stderr or "")).strip()
        log(f"[{step_id}] exit {p.returncode}: {out[-600:]}")
        return p.returncode == 0, out[-300:]
    except (OSError, subprocess.TimeoutExpired) as e:
        log(f"[{step_id}] could not run: {e}")
        return False, str(e)[:300]


def scan():
    """setup-scan.py's answer: {tool id: present}."""
    src = os.environ.get("LANES_SETUP_SCAN")
    try:
        if src:
            data = json.load(open(src, encoding="utf-8"))
        else:
            out = subprocess.run([PY, tool("setup-scan.py"), "--json"], capture_output=True, text=True,
                                 timeout=600, encoding="utf-8", errors="replace").stdout
            data = json.loads(out)
        present = {r["id"]: bool(r["present"]) for r in data.get("tools", [])}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        present = {}
    if "dotnet10" not in present:          # the RE Engine connector needs the .NET 10 SDK; the scan has no row for it
        try:
            out = "" if src else subprocess.run(["dotnet", "--list-sdks"], capture_output=True, text=True,
                                                 timeout=60).stdout
            present["dotnet10"] = any(l.startswith("10.") for l in out.splitlines())
        except (OSError, subprocess.TimeoutExpired):
            present["dotnet10"] = False
    return present


def gh_signed_in():
    if FAKE:
        return os.environ.get("LANES_SETUP_GH", "yes") == "yes"
    try:
        return subprocess.run(["gh", "auth", "status"], capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def load():
    try:
        d = json.load(open(RECORD, encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save(d):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = RECORD + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(d, f, indent=1)
    os.replace(tmp, RECORD)


# ---------------------------------------------------------------- the steps

def extras_step(_):
    sys.path.insert(0, HERE)
    import features
    on = features.recommended_names()
    off = [n for n in features.FEATURES if n not in on]
    ok = True
    for n in on:
        ok &= sh("extras", [PY, tool("features.py"), "on", n])[0]
    for n in off:
        ok &= sh("extras", [PY, tool("features.py"), "off", n])[0]
    if conf_value("pcs") == "1" and "keeper" in on:
        conf_set("keeper_mode", "this_pc", "one PC: saving to GitHub runs in the background")
    if "theme" in on:
        sh("extras", [PY, tool("theme.py"), "apply"])
    return ok, f"{len(on)} extras on, {len(off)} off"


def winget_step(pkg):
    def run_it(_):
        return sh("program:" + pkg, [PY, tool("quiet_install.py"), "run", "winget:" + pkg, "--wait", INSTALL_WAIT_MIN])
    return run_it


def pip_step(sid, pkgs):
    def run_it(_):
        return sh(sid, [PY, "-m", "pip", "install", "--user", *pkgs])
    return run_it


def cmd_step(sid, *cmds):
    def run_it(_):
        detail = ""
        for c in cmds:
            ok, detail = sh(sid, list(c))
            if not ok:
                return False, detail
        return True, detail
    return run_it


def ghidrust_step(_):
    folder = os.path.join(HOME, "Tools", "Ghidrust")
    steps = [] if os.path.isdir(os.path.join(folder, ".git")) else [
        ["git", "clone", "--depth", "1", "https://github.com/oofz/Ghidrust", folder]]
    steps += [["cargo", "build", "--release"],
              ["claude", "mcp", "add", "--scope", "user", "ghidrust", "--",
               os.path.join(folder, "target", "release", "ghidrust.exe"), "mcp"]]
    for c in steps:
        ok, detail = sh("ghidrust", c, cwd=folder if c[0] == "cargo" and not FAKE else None)
        if not ok:
            return False, detail
    return True, "built and linked"


def realesrgan_step(_):
    dest = os.path.join(LOCALAPPDATA, "Programs", "Real-ESRGAN")
    if "realesrgan" in FAIL:
        return False, "made to fail by the test"
    if FAKE:
        log(f"[realesrgan] would download {REALESRGAN_ZIP} into {dest}")
        return True, "fake"
    try:
        os.makedirs(dest, exist_ok=True)
        zpath = os.path.join(dest, "download.zip")
        urllib.request.urlretrieve(REALESRGAN_ZIP, zpath)
        with zipfile.ZipFile(zpath) as z:
            z.extractall(dest)
        os.remove(zpath)
        return True, "unpacked"
    except (OSError, zipfile.BadZipFile) as e:
        return False, str(e)[:300]


def settings_step(_):
    """What setup's one-time questions would set, at their recommended answer."""
    ok = True
    insp = os.path.join(HOME, ".claude", "lanes-inspector")
    if not FAKE:
        os.makedirs(insp, exist_ok=True)
    conf_set("inspector", "on", "the Inspector looks over every piece of code a session writes")
    conf_set("inspector_home", insp, "where the Inspector keeps its notes")
    rec = os.path.join(HOME, "Videos", "Lanes recordings")
    if not conf_value("transfer"):
        if not FAKE:
            os.makedirs(rec, exist_ok=True)
        conf_set("recordings", rec, "where the VR test recordings go")
    for args in ([tool("compact.py"), "on"], [tool("unlock.py"), "on"], [tool("shortcut.py"), "create"],
                 [tool("remote-control.py"), "apply"]):
        ok &= sh("settings", [PY, *args])[0]
    return ok, "Inspector, recordings folder, early summaries, unlock-first, Desktop shortcut"


def bench_profile_step(_):
    return sh("bench-profile", [PY, os.path.join(HERE, "vrbench", "vrbench.py"), "profile"])


def github_step(_):
    if not gh_signed_in():
        return None, "GitHub is not signed in on this PC"
    ok = True
    if not conf_value("board"):
        root = conf_value("root") or DEFAULT_ROOT
        ok &= sh("github", [PY, tool("estate.py"), "make", "--root", root])[0]
    ok &= sh("github", [PY, tool("thanks.py"), "on"])[0]
    ok &= sh("github", [PY, tool("thanks.py"), "credits"])[0]
    # GitHub's private address on every saved step (setup's §0.12.1); the two boxes on GitHub's page go on the list
    addr = "<id>+<login>@users.noreply.github.com"
    if not FAKE:
        try:
            p = subprocess.run(["gh", "api", "user", "--jq", '"\\(.id)+\\(.login)@users.noreply.github.com"'],
                               capture_output=True, text=True, timeout=60)
            addr = p.stdout.strip().strip('"')
        except (OSError, subprocess.TimeoutExpired):
            addr = ""
    if addr.endswith("@users.noreply.github.com"):
        sh("github", ["git", "config", "--global", "user.email", addr])
    return ok, "the private repos, the thank-you stars, and GitHub's private e-mail address for your saved work"


def offers_step(_):
    for name in ("thanks", "shortcut", "openxr-sim", "begone-record", "superpowers", "estate", "unlock-all",
                 "video-tidy", "outside-tools", "our-tools", "github-email", "remote-control"):
        sh("offers", [PY, tool("offers.py"), "made", name, "recommended-set"])
    return True, "every one-time offer marked as answered"


def build_steps(present, record):
    """(id, title in plain words, function). Steps for tools already on the PC are left out."""
    sys.path.insert(0, HERE)
    import ours
    import outside
    steps = [("extras", "Switch on the recommended extras", extras_step)]
    for sid, pkg in WINGET:
        if not present.get(sid):
            steps.append(("program:" + pkg, "Install " + (".NET 10 SDK" if sid == "dotnet10" else pkg.split(".", 1)[-1]),
                          winget_step(pkg)))
    for sid, pkgs in PIP:
        if not present.get(sid):
            steps.append((sid, "Python packages: " + ", ".join(pkgs), pip_step(sid, pkgs)))
    lanes = [("re-engine-mcp", "The live connector for RE Engine games", [tool("engine-mcp.py"), "install", "re"]),
             ("uevr-mcp", "The live connector for Unreal games", [tool("engine-mcp.py"), "install", "uevr"]),
             ("openxrsim", "The pretend headset and VR Bench", [tool("openxr-sim.py"), "install", "--fork", "--bench"]),
             ("handfreeze", "Hand Freeze", [tool("hand-freeze.py"), "install"])]
    for sid, title, args in lanes:
        if not present.get(sid):
            steps.append((sid, title, cmd_step(sid, [PY, *args])))
    if not present.get("x64dbg-skills"):
        steps.append(("x64dbg-skills", "Debugger routines for Claude (x64dbg-skills)", cmd_step(
            "x64dbg-skills", ["claude", "plugin", "marketplace", "add", "dariushoule/x64dbg-skills"],
            ["claude", "plugin", "install", "x64dbg-skills@x64dbg-skills"])))
    steps.append(("superpowers", "The superpowers skills", cmd_step(
        "superpowers", ["claude", "plugin", "install", "superpowers@claude-plugins-official"])))
    if not present.get("blender-mcp"):
        steps.append(("blender-mcp", "The Blender link (its part outside Blender)", cmd_step(
            "blender-mcp", ["claude", "mcp", "add", "--scope", "user", "blender", "--", "uvx", "mcp-for-blender"],
            ["uvx", "mcp-for-blender", "install-addon"])))
    if not present.get("ghidrust"):
        steps.append(("ghidrust", "Ghidrust, the program reader (built here, several minutes)", ghidrust_step))
    if not present.get("realesrgan"):
        steps.append(("realesrgan", "Real-ESRGAN, the picture enlarger", realesrgan_step))
    for name in ours.TOOLS:
        steps.append(("ours:" + name, ours.TOOLS[name]["label"], cmd_step("ours:" + name, [PY, tool("ours.py"), "get", name])))
    for name, t in outside.TOOLS.items():
        if t["kind"] != "setup":            # a maker's own installer waits for a person: it goes on the list instead
            steps.append(("outside:" + name, t["label"], cmd_step("outside:" + name,
                                                                  [PY, tool("outside.py"), "get", name])))
    steps.append(("settings", "The recommended settings", settings_step))
    if conf_value("bench_headset"):
        steps.append(("bench-profile", "VR Bench's measure of this PC", bench_profile_step))
    steps.append(("github", "Your GitHub, the Lanes way (all private)", github_step))
    steps.append(("offers", "Mark the one-time offers as answered", offers_step))
    return steps


def person_items(record):
    """The fixed list of steps that need the person, for this PC."""
    sys.path.insert(0, HERE)
    import outside
    two = conf_value("pcs") == "2"
    headset = conf_value("bench_headset") == "real"
    items = []
    for pid, title, why, how, when in PERSON:
        if (when == "headset" and not headset) or (when == "two_pcs" and not two):
            continue
        items.append({"id": pid, "title": title, "why": why, "how": how})
    for name, t in outside.TOOLS.items():
        if t["kind"] == "setup":
            items.append({"id": "outside:" + name, "title": t["label"], "why": t["what"],
                          "how": f"say \"install {t['label']}\": its maker's installer opens; click through it"})
    gh = (record.get("steps", {}).get("github") or {}).get("status")
    if gh in (None, "skipped"):
        items.append({"id": "github-signin", "title": "Sign in to GitHub",
                      "why": "your work is saved on GitHub, in private repos only you can see",
                      "how": "no account yet? make one at github.com/signup. Then type ! gh auth login and follow it; "
                             "then say \"finish my setup\" and the GitHub part runs by itself"})
    items.append({"id": "github-email", "title": "Two boxes on GitHub's e-mail page",
                  "why": "they keep your e-mail address private on everything you save to GitHub",
                  "how": "open github.com/settings/emails and tick \"Keep my email addresses private\" and "
                         "\"Block command line pushes that expose my email\""})
    items.append({"id": "restart", "title": "Restart Claude Code",
                  "why": "the new links and skills only appear after a restart",
                  "how": "close this window and open Claude Code again"})
    return items


# ---------------------------------------------------------------- commands

def cmd_plan(as_json):
    present = scan()
    record = load()
    steps = build_steps(present, record)
    people = person_items(record)
    if as_json:
        print(json.dumps({"steps": [{"id": s, "title": t} for s, t, _ in steps], "for_you": people}, indent=1))
        return 0
    print(f"The recommended run would do {len(steps)} steps by itself:")
    for _, title, _ in steps:
        print("  - " + title)
    print(f"and leave {len(people)} for you, at the end:")
    for p in people:
        print("  - " + p["title"])
    return 0


def cmd_start():
    """The one Yes click, while the person is still there."""
    ok, detail = sh("start", [PY, tool("quiet_install.py"), "setup"])
    sh("start", [PY, tool("features.py"), "on", "quiet_installs"])
    print("The no-click installer is set up: nothing that runs next will wait at a Windows Yes."
          if ok else f"The no-click installer was not set up ({detail}). The run still goes ahead; any install that "
                     "would wait at a Yes click is put on your list instead of waiting.")
    return 0 if ok else 1


def cmd_run():
    os.makedirs(STATE_DIR, exist_ok=True)
    refresh_path()
    record = load()
    record.setdefault("steps", {})
    record["started"] = record.get("started") or now()
    log("run: started")
    present = scan()
    steps = build_steps(present, record)
    done = failed = 0
    for sid, title, fn in steps:
        prev = record["steps"].get(sid, {})
        if prev.get("status") == "done":
            continue
        print(f"... {title}", flush=True)
        try:
            ok, detail = fn(sid)
        except Exception as e:      # one broken step must not stop the rest of the night's work
            ok, detail = False, f"{type(e).__name__}: {e}"[:300]
        status = "skipped" if ok is None else ("done" if ok else "failed")
        record["steps"][sid] = {"title": title, "status": status, "detail": detail, "at": now()}
        save(record)
        refresh_path()
        done += status == "done"
        failed += status == "failed"
    sh("mark-done", [PY, tool("setup-scan.py"), "--mark-done", "--choices", json.dumps({"recommended-run": "installed-by-claude"})])
    todo = [dict(p, done=False) for p in person_items(record)]
    for sid, r in record["steps"].items():
        if r["status"] == "failed":
            todo.insert(0, {"id": "retry:" + sid, "title": f"{r['title']}: did not finish",
                            "why": r["detail"] or "no reason given",
                            "how": "say \"try it again\" (the same run picks up only what is left), or do it by hand "
                                   "from the tools page", "done": False})
    old = {t["id"]: t.get("done") for t in record.get("todo", [])}
    for t in todo:
        t["done"] = bool(old.get(t["id"]))
    record["todo"] = todo
    record["finished"] = now()
    save(record)
    log(f"run: finished, {done} done now, {failed} failed")
    left = [t for t in todo if not t["done"]]
    print(f"\nDone by itself: {sum(1 for r in record['steps'].values() if r['status'] == 'done')} steps"
          f"{f', {failed} did not finish' if failed else ''}. {len(left)} steps need you: `setup_run.py todo`.")
    return 0 if not failed else 1


def cmd_todo(argv):
    record = load()
    todo = record.get("todo", [])
    left = [t for t in todo if not t.get("done")]
    if "--count" in argv:
        print(len(left))
        return 0
    if "--json" in argv:
        print(json.dumps(todo, indent=1))
        return 0
    if not left:
        print("Nothing waits for you from setup.")
        return 0
    print("What needs you:")
    for i, t in enumerate(todo, 1):
        if not t.get("done"):
            print(f"{i}. {t['title']}: {t['why']}. How: {t['how']}.")
    return 0


def cmd_done(argv):
    record = load()
    todo = record.get("todo", [])
    if not argv:
        print("say which: setup_run.py done <number>|all")
        return 2
    if argv[0] == "all":
        for t in todo:
            t["done"] = True
    else:
        try:
            todo[int(argv[0]) - 1]["done"] = True
        except (ValueError, IndexError):
            print(f"there is no step {argv[0]} on the list")
            return 2
    save(record)
    print(f"{sum(1 for t in todo if not t.get('done'))} left")
    return 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "plan":
        return cmd_plan("--json" in rest)
    if cmd == "start":
        return cmd_start()
    if cmd == "run":
        return cmd_run()
    if cmd == "todo":
        return cmd_todo(rest)
    if cmd == "done":
        return cmd_done(rest)
    print(__doc__)
    return 2


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))
