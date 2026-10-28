#!/usr/bin/env python3
"""gu_guard.py - /lanes:gu's update safety: test-build our work before keeping an update (0.83.0, 2026-10-23).

Asked for by the maintainer: "is there a way to make our work VS Build Tools future proof? and any other program or
tool we use for that matter?", then "yes please on the safety test before an update ... is there any way to filter it
to things that can actually break things and not simple win-zip". So:

  1. RISK. Every update the run is about to offer is sorted: BUILD-CRITICAL (a compiler, the build tools, Python
     itself, the debugger, Blender, a major jump of a Python package; plus anything in `critical =`) or "no known
     risk" (an archiver, a viewer, a minor library bump). Only the critical ones get the test build; the rest are
     installed as before.
  2. BEFORE. Writes down the version each ticked critical update replaces, and runs every `build_check =` once: the
     known-good result to compare with.
  3. AFTER. Once one critical update is installed, runs the checks again. A check that passed before and fails now
     means that update broke our work: it says so, and `putback` returns the old version. One update at a time, so
     the culprit is never in doubt.

    python gu_guard.py checks                          the build checks this PC has
    python gu_guard.py risk <item>...                  sort updates: winget:<Id>  or  pip:<name>:<have>:<new>
    python gu_guard.py before <item>...                note the versions they replace, run the checks (baseline)
    python gu_guard.py after                           run the checks again; exit 1 if one that passed now fails
    python gu_guard.py putback <item>                  install the version noted by `before` again

A build check (lanes.conf, may repeat):  build_check = <name> | <folder, or -> | <command>
The command runs in the folder (Git's bash for a command starting `bash `). Built-in probes instead of a command:
  @msvc     Visual Studio's C++ compiler builds a tiny 64-bit and 32-bit program
  @blender  the newest Blender starts in the background with its add-ons and runs Python
  @pip      `pip check`: no installed package pins another out of range
Choose checks that only build and test: never one that installs into a game folder.
Extra build-critical names (may repeat):  critical = <part of a winget Id or pip name> | <what it could break>
State: <state dir>/gu_guard.json. Tests set LANES_CONFIG, LANES_STATE_DIR and LANES_GUARD_FAKE_VERSIONS (JSON
{"winget:Id": "1.0"}), so no real installer is ever asked.
"""
import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gu import conf_values, pair  # noqa: E402  (one reader of lanes.conf, not two)

STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "lanes")
STATE_FILE = os.path.join(STATE_DIR, "gu_guard.json")
CHECK_TIMEOUT_S = 900        # a whole add-on with its self-tests builds in a few minutes on a slow PC
VERSION_TIMEOUT_S = 60
TAIL_LINES = 8               # of a failing check's output, kept to show what broke

# What can break a build, by part of the winget Id (case-insensitive). Everything else is "no known risk".
CRITICAL_WINGET = [
    ("llvm-mingw", "the compiler our add-ons are built with: a new version moves its folder and changes every build"),
    ("visualstudio.", "Visual Studio's build tools: the C++ compiler for Visual Studio-built add-ons and apps"),
    ("buildtools", "Visual Studio's build tools: the C++ compiler for Visual Studio-built add-ons and apps"),
    ("cmake", "CMake, which sets up C++ builds"),
    ("ninja", "Ninja, the build runner"),
    ("python.python", "Python itself: every tool and MCP server runs on it, and its packages may need reinstalling"),
    ("x64dbg", "the debugger and its MCP helper"),
    ("blender", "Blender: add-ons, the Blender MCP and our export scripts can break on a new version"),
    ("rustlang", "the Rust compiler"),
    ("dotnet.sdk", "the .NET SDK, which builds C# tools"),
]
LOW_RISK = "no known risk"


def now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)


# ---- sorting updates ------------------------------------------------------------------------------------------

def parse_item(item):
    """'winget:Id' or 'pip:name:have:new' -> (kind, name, have, new)."""
    kind, _, rest = item.partition(":")
    if kind == "pip":
        name, _, vers = rest.partition(":")
        have, _, new = vers.partition(":")
        return "pip", name, have or None, new or None
    return kind, rest, None, None


def major(version):
    m = re.match(r"\d+", version or "")
    return int(m.group()) if m else None


def risk(item):
    """(True, why) for a build-critical update, (False, LOW_RISK) for the rest."""
    kind, name, have, new = parse_item(item)
    low = name.lower()
    for value in conf_values("critical"):
        part, why = pair(value)
        if part and part.lower() in low:
            return True, why or "named build-critical in lanes.conf"
    if kind == "winget":
        for part, why in CRITICAL_WINGET:
            if part in low:
                return True, why
    if kind == "pip" and major(have) is not None and major(new) is not None and major(new) > major(have):
        return True, f"a major version ({have} -> {new}): it may remove what our tools and MCP servers use"
    return False, LOW_RISK


# ---- versions -------------------------------------------------------------------------------------------------

def fake_versions():
    path = os.environ.get("LANES_GUARD_FAKE_VERSIONS")
    if not path:
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def current_version(item):
    kind, name, _, _ = parse_item(item)
    fake = fake_versions()
    if fake is not None:
        return fake.get(f"{kind}:{name}")
    if kind == "pip":
        r = subprocess.run([sys.executable, "-c", f"import importlib.metadata as m; print(m.version({name!r}))"],
                           capture_output=True, text=True, timeout=VERSION_TIMEOUT_S)
        return (r.stdout.strip() or None) if r.returncode == 0 else None
    if kind == "winget":
        r = subprocess.run(["winget", "list", "--id", name, "--exact", "--disable-interactivity",
                            "--accept-source-agreements"], capture_output=True, text=True, timeout=VERSION_TIMEOUT_S,
                           encoding="utf-8", errors="replace")
        for line in r.stdout.splitlines():
            words = line.split()
            if name in words:
                after = words[words.index(name) + 1:]
                return after[0] if after else None
    return None


def putback_command(item, version):
    kind, name, _, _ = parse_item(item)
    if kind == "pip":
        return [sys.executable, "-m", "pip", "install", "--quiet", f"{name}=={version}"]
    return ["winget", "install", "--id", name, "--exact", "--version", version, "--force",
            "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity"]


# ---- the build checks -----------------------------------------------------------------------------------------

def git_bash():
    """Git's own bash (on Windows `bash` on the PATH may be WSL's, which cannot see these paths)."""
    if os.name != "nt":
        return shutil.which("bash") or "bash"
    git = shutil.which("git")
    if git:
        root = os.path.dirname(os.path.dirname(os.path.realpath(git)))
        for cand in (os.path.join(root, "bin", "bash.exe"), os.path.join(root, "usr", "bin", "bash.exe")):
            if os.path.isfile(cand):
                return cand
    return "bash"


def checks():
    out = []
    for value in conf_values("build_check"):
        parts = [p.strip() for p in value.split("|", 2)]
        if len(parts) == 3 and parts[0] and parts[2]:
            out.append({"name": parts[0], "folder": None if parts[1] in ("", "-") else parts[1], "command": parts[2]})
    return out


def probe_msvc(tmp):
    vswhere = os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                           "Microsoft Visual Studio", "Installer", "vswhere.exe")
    if not os.path.isfile(vswhere):
        return 1, "vswhere.exe not found: Visual Studio's build tools are not installed"
    r = subprocess.run([vswhere, "-latest", "-products", "*", "-property", "installationPath"],
                       capture_output=True, text=True, timeout=VERSION_TIMEOUT_S)
    root = r.stdout.strip().splitlines()[0] if r.stdout.strip() else ""
    src = os.path.join(tmp, "hello.c")
    with open(src, "w") as f:
        f.write("#include <stdio.h>\nint main(void){puts(\"ok\");return 0;}\n")
    lines = []
    for bat in ("vcvars64.bat", "vcvars32.bat"):
        vc = os.path.join(root, "VC", "Auxiliary", "Build", bat)
        if not os.path.isfile(vc):
            return 1, f"{bat} not found under {root or 'no Visual Studio'}"
        exe = os.path.join(tmp, bat.replace(".bat", ".exe"))
        r = subprocess.run(f'call "{vc}" >nul && cl /nologo "{src}" /Fe"{exe}" /Fo"{tmp}\\\\" && "{exe}"',
                           shell=True, capture_output=True, text=True, timeout=CHECK_TIMEOUT_S, cwd=tmp)
        lines.append(f"{bat}: exit {r.returncode}")
        if r.returncode != 0 or "ok" not in r.stdout:
            return 1, (r.stdout + r.stderr)[-2000:]
    return 0, "; ".join(lines)


def probe_blender(tmp):
    found = sorted(glob.glob(os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                                          "Blender Foundation", "Blender *", "blender.exe")))
    if not found:
        return 1, "no Blender found"
    r = subprocess.run([found[-1], "-b", "--python-exit-code", "1", "--python-expr",
                        "import bpy, addon_utils; print('BLENDER_OK', bpy.app.version_string)"],
                       capture_output=True, text=True, timeout=CHECK_TIMEOUT_S, cwd=tmp, encoding="utf-8",
                       errors="replace")
    return (0 if r.returncode == 0 and "BLENDER_OK" in r.stdout else 1), (r.stdout + r.stderr)[-2000:]


def run_check(c):
    started = datetime.datetime.now()
    tmp = tempfile.mkdtemp(prefix="gu_guard_")
    try:
        cmd = c["command"]
        if cmd == "@msvc":
            code, text = probe_msvc(tmp)
        elif cmd == "@blender":
            code, text = probe_blender(tmp)
        elif cmd == "@pip":
            r = subprocess.run([sys.executable, "-m", "pip", "check"], capture_output=True, text=True,
                               timeout=CHECK_TIMEOUT_S)
            code, text = r.returncode, r.stdout + r.stderr
        else:
            folder = c["folder"] or tmp
            if not os.path.isdir(folder):
                return {"ok": False, "secs": 0, "tail": [f"folder not found: {folder}"]}
            argv = [git_bash(), "-c", cmd] if cmd.startswith("bash ") else None   # else cmd.exe / sh runs it
            first, _, args = cmd.partition(" ")
            if argv is None and os.path.isfile(os.path.join(folder, first)):     # cmd.exe did not find build.bat
                cmd = f'"{os.path.join(folder, first)}" {args}'.strip()          # in its own folder (live, 2026-10-23)
            r = subprocess.run(argv or cmd, shell=argv is None, capture_output=True, text=True, cwd=folder,
                               timeout=CHECK_TIMEOUT_S, encoding="utf-8", errors="replace")
            code, text = r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        code, text = 1, f"took longer than {CHECK_TIMEOUT_S} s"
    except OSError as e:
        code, text = 1, str(e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    secs = round((datetime.datetime.now() - started).total_seconds(), 1)
    return {"ok": code == 0, "secs": secs, "tail": [l for l in text.strip().splitlines() if l.strip()][-TAIL_LINES:]}


def run_all():
    results = {}
    for c in checks():
        res = run_check(c)
        results[c["name"]] = res
        print(f"   {c['name']}: {'builds' if res['ok'] else 'FAILS'} ({res['secs']} s)")
        if not res["ok"]:
            for line in res["tail"]:
                print(f"      {line}")
    return results


# ---- commands -------------------------------------------------------------------------------------------------

def cmd_checks():
    cs = checks()
    if not cs:
        print("No build checks on this PC (build_check = <name> | <folder> | <command> in lanes.conf).")
    for c in cs:
        print(f"   {c['name']}: {c['command']}" + (f"  (in {c['folder']})" if c["folder"] else ""))
    return 0


def cmd_risk(items):
    for item in items:
        crit, why = risk(item)
        print(f"{'BUILD-CRITICAL' if crit else 'low'}\t{item}\t{why}")
    return 0


def cmd_before(items):
    state = {"when": now(), "versions": {}, "baseline": {}}
    for item in items:
        state["versions"][item] = current_version(item)
        print(f"   {item}: now {state['versions'][item] or 'version not found (cannot be put back by itself)'}")
    if not checks():
        print("No build checks set: nothing to compare with. Add build_check lines to lanes.conf.")
    print("Known-good build, before updating:")
    state["baseline"] = run_all()
    save_state(state)
    already = [n for n, r in state["baseline"].items() if not r["ok"]]
    if already:
        print("Already failing before any update (they cannot judge it): " + ", ".join(already))
    return 0


def cmd_after():
    state = load_state()
    if not state.get("baseline"):
        print("No baseline: run `gu_guard.py before <item>...` before installing.")
        return 2
    print("After the update:")
    results = run_all()
    broke = [n for n, r in results.items() if not r["ok"] and state["baseline"].get(n, {}).get("ok")]
    fixed = [n for n, r in results.items() if r["ok"] and not state["baseline"].get(n, {}).get("ok", True)]
    state["after"] = {"when": now(), "results": results}
    save_state(state)
    if fixed:
        print("Builds now that failed before: " + ", ".join(fixed))
    if broke:
        print("BROKEN BY THE UPDATE: " + ", ".join(broke) + ". Put it back: gu_guard.py putback <item>")
        for item, version in state.get("versions", {}).items():
            if version:
                print(f"   {item}: back to {version}")
        return 1
    print("SAFE: every check that built before still builds.")
    return 0


def cmd_putback(item):
    version = load_state().get("versions", {}).get(item)
    if not version:
        print(f"No version noted for {item}; it cannot be put back by itself. Say so to the person.")
        return 2
    argv = putback_command(item, version)
    if fake_versions() is not None:
        print("would run: " + " ".join(argv))
        return 0
    print(f"Putting {item} back to {version} ...")
    r = subprocess.run(argv, capture_output=True, text=True, timeout=CHECK_TIMEOUT_S, encoding="utf-8",
                       errors="replace")
    have = current_version(item)
    ok = have == version
    print(f"   now {have or '?'}: " + ("put back" if ok else "NOT put back; the installer said: "
                                      + (r.stdout + r.stderr).strip()[-600:]))
    return 0 if ok else 1


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "checks":
        return cmd_checks()
    if cmd == "risk" and rest:
        return cmd_risk(rest)
    if cmd == "before":
        return cmd_before(rest)
    if cmd == "after":
        return cmd_after()
    if cmd == "putback" and len(rest) == 1:
        return cmd_putback(rest[0])
    print(__doc__)
    return 2


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):   # a character the console cannot show prints as ? (0.94.2)
        try:
            _stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))
