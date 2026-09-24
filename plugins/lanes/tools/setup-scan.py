#!/usr/bin/env python3
"""setup-scan - which of the optional tools in docs/TOOLS.md are present on this machine.

Read-only. Never installs anything; /lanes:setup does that, one confirmed step at a time.

USAGE
  python setup-scan.py            table grouped like docs/TOOLS.md
  python setup-scan.py --json     machine-readable, for the setup command
  python setup-scan.py --state    print the saved setup state (what the user chose last time)
  python setup-scan.py --mark-done [--choices JSON]   record that setup has been offered/run here

THE STATE FILE
  <state dir>/setup-state.json, where the state dir is $LANES_STATE_DIR or ~/.claude/lanes.
  It exists once setup has been offered on this machine. The SessionStart nudge stays silent from
  then on, so the offer is made once per machine, not every session.
"""
import argparse
import datetime
import glob
import json
import os
import shutil
import socket
import subprocess
import sys

HOME = os.path.expanduser("~")
LOCALAPPDATA = os.environ.get("LOCALAPPDATA", os.path.join(HOME, "AppData", "Local"))
APPDATA = os.environ.get("APPDATA", os.path.join(HOME, "AppData", "Roaming"))
PROGRAMFILES = os.environ.get("ProgramFiles", r"C:\Program Files")
PROGRAMFILES_X86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
WINGET_PKGS = os.path.join(LOCALAPPDATA, "Microsoft", "WinGet", "Packages")
STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(HOME, ".claude", "lanes")
STATE_FILE = os.path.join(STATE_DIR, "setup-state.json")
CHECK_TIMEOUT_S = 15
BLENDER_PORT = 9876          # the port the MCP for Blender add-on listens on inside Blender
BLENDER_PROBE_TIMEOUT_S = 2  # short: a scan must never hang on a closed Blender


def run_ok(cmd):
    """True when the command starts and exits 0. Store-stub Pythons fail this, which is the point."""
    try:
        return subprocess.run(cmd, capture_output=True, timeout=CHECK_TIMEOUT_S).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def on_path(*names):
    return any(shutil.which(n) for n in names)


def any_glob(*patterns):
    return any(glob.glob(p) for p in patterns)


def python_cmd():
    for cand in ("python", "py", "python3"):
        if shutil.which(cand) and run_ok([cand, "-c", ""]):
            return cand
    return None


def py_imports(*mods):
    py = python_cmd()
    return bool(py) and run_ok([py, "-c", "import " + ", ".join(mods)])


def mcp_servers():
    """Names of user-scope MCP servers from Claude Code's own config."""
    try:
        with open(os.path.join(HOME, ".claude.json"), encoding="utf-8") as f:
            return set((json.load(f).get("mcpServers") or {}).keys())
    except (OSError, ValueError):
        return set()


def claude_plugins():
    try:
        with open(os.path.join(HOME, ".claude", "plugins", "installed_plugins.json"), encoding="utf-8") as f:
            data = json.load(f)
        return {k.split("@")[0] for k in (data.get("plugins") or data).keys()}
    except (OSError, ValueError, AttributeError):
        return set()


def llvm_mingw():
    return on_path("x86_64-w64-mingw32-clang") or any_glob(
        os.path.join(WINGET_PKGS, "MartinStorsjo.LLVM-MinGW*", "*", "bin", "x86_64-w64-mingw32-clang.exe"))


def x64dbg_exe():
    hits = glob.glob(os.path.join(WINGET_PKGS, "x64dbg.x64dbg*", "release", "x64", "x64dbg.exe"))
    return hits[0] if hits else shutil.which("x64dbg")


def x64dbg_automate_plugin():
    exe = x64dbg_exe()
    return bool(exe) and os.path.isfile(os.path.join(os.path.dirname(exe), "plugins", "x64dbg-automate.dp64"))


def vs_cpp_tools():
    vswhere = os.path.join(PROGRAMFILES_X86, "Microsoft Visual Studio", "Installer", "vswhere.exe")
    if not os.path.isfile(vswhere):
        return False
    try:
        out = subprocess.run([vswhere, "-products", "*", "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                              "-property", "installationPath"], capture_output=True, text=True, timeout=CHECK_TIMEOUT_S)
        return bool(out.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        return False


def blender():
    return any_glob(os.path.join(PROGRAMFILES, "Blender Foundation", "*", "blender.exe")) or on_path("blender")


def blender_addon():
    return any_glob(os.path.join(APPDATA, "Blender Foundation", "Blender", "*", "scripts", "addons", "*mcp*"),
                    os.path.join(APPDATA, "Blender Foundation", "Blender", "*", "extensions", "*", "*mcp*"))


def blender_link_live():
    """True when Blender is open with its MCP server started, i.e. the link actually answers.

    A registered server and an add-on file on disk are not a working link: the last two steps happen
    by hand inside Blender. Asking the socket is the only honest test, and it is what stops setup
    walking someone through clicks they already did.
    """
    try:
        with socket.create_connection(("127.0.0.1", BLENDER_PORT), timeout=BLENDER_PROBE_TIMEOUT_S) as sock:
            sock.sendall(json.dumps({"type": "get_scene_info", "params": {}}).encode())
            reply = sock.recv(65536)
    except OSError:
        return False
    try:
        return json.loads(reply.decode("utf-8", "replace")).get("status") == "success"
    except ValueError:
        return False


def service_running(name):
    return run_ok(["sc", "query", name]) and "RUNNING" in subprocess.run(
        ["sc", "query", name], capture_output=True, text=True).stdout


def process_running(image):
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {image}"], capture_output=True, text=True,
                             timeout=CHECK_TIMEOUT_S).stdout
        return image.lower() in out.lower()
    except (OSError, subprocess.TimeoutExpired):
        return False


def registry_install_dirs(*name_prefixes):
    """Folders Windows recorded for a program, so a tool installed outside Program Files is still found.

    A check that tests one hardcoded folder reports a false MISSING, and a false missing is worse than
    no check: it sends setup off to reinstall something the machine already has.
    """
    try:
        import winreg
    except ImportError:
        return []
    roots = ((winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
             (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
             (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"))
    dirs = []
    for hive, path in roots:
        try:
            key = winreg.OpenKey(hive, path)
        except OSError:
            continue
        with key:
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    with winreg.OpenKey(key, winreg.EnumKey(key, i)) as sub:
                        name = winreg.QueryValueEx(sub, "DisplayName")[0]
                        if not any(name.startswith(p) for p in name_prefixes):
                            continue
                        loc = winreg.QueryValueEx(sub, "InstallLocation")[0]
                except OSError:
                    continue
                if loc:
                    dirs.append(loc)
    return dirs


def sevenzip():
    dirs = [os.path.join(PROGRAMFILES, "7-Zip"), os.path.join(PROGRAMFILES_X86, "7-Zip")]
    dirs += registry_install_dirs("7-Zip")
    return on_path("7z") or any(os.path.isfile(os.path.join(d, "7z.exe")) for d in dirs)


def steam_roots():
    """Where Steam itself is, asked of Steam rather than guessed: it is often not on C:."""
    roots = []
    try:
        import winreg
        for hive, path, value in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                                  (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
                                  (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath")):
            try:
                with winreg.OpenKey(hive, path) as key:
                    roots.append(os.path.normpath(winreg.QueryValueEx(key, value)[0]))
            except OSError:
                continue
    except ImportError:
        pass
    roots += registry_install_dirs("Steam")
    return roots + [os.path.join(PROGRAMFILES_X86, "Steam"), os.path.join(PROGRAMFILES, "Steam"), r"C:\Steam"]


def steam_libraries():
    """Every Steam library on the machine, not just the one beside Steam itself.

    Games routinely live on another drive; libraryfolders.vdf is Steam's own list of where.
    """
    roots = steam_roots()
    libs = []
    for root in roots:
        if not os.path.isdir(os.path.join(root, "steamapps")):
            continue
        libs.append(root)
        try:
            with open(os.path.join(root, "steamapps", "libraryfolders.vdf"), encoding="utf-8", errors="replace") as f:
                for line in f:
                    parts = line.split('"')
                    # "path"    "E:\\SteamLibrary"
                    if len(parts) >= 5 and parts[1] == "path":
                        libs.append(parts[3].replace("\\\\", "\\"))
        except OSError:
            pass
    return list(dict.fromkeys(os.path.normcase(lib) for lib in libs))


def steam_app_installed(appid):
    return any(os.path.isfile(os.path.join(lib, "steamapps", f"appmanifest_{appid}.acf"))
               for lib in steam_libraries())


def catalog():
    mcp = mcp_servers()
    plugins = claude_plugins()
    # (group, id, name, check, needs_admin, manual_only)
    return [
        ("core", "git", "Git for Windows", lambda: run_ok(["git", "--version"]), False, False),
        ("core", "gh", "GitHub CLI (signed in)", lambda: run_ok(["gh", "auth", "status"]), False, False),
        ("core", "python", "Python 3", lambda: python_cmd() is not None, False, False),
        ("core", "pypkgs", "Python packages (pefile, capstone, pillow, psutil, pywin32, numpy)",
         lambda: py_imports("pefile", "capstone", "PIL", "psutil", "win32gui", "numpy"), False, False),
        ("core", "uv", "uv / uvx", lambda: on_path("uvx") or any_glob(os.path.join(WINGET_PKGS, "astral-sh.uv*", "uvx.exe")), False, False),
        ("core", "7zip", "7-Zip", sevenzip, False, False),
        ("build", "llvm-mingw", "llvm-mingw", llvm_mingw, False, False),
        ("build", "cmake", "CMake", lambda: on_path("cmake") or os.path.isfile(os.path.join(PROGRAMFILES, "CMake", "bin", "cmake.exe")), False, False),
        ("build", "vsbuildtools", "Visual Studio 2022 Build Tools (C++)", vs_cpp_tools, True, False),
        ("build", "rust", "Rust (cargo)", lambda: on_path("cargo") or os.path.isfile(os.path.join(HOME, ".cargo", "bin", "cargo.exe")), False, False),
        ("build", "lua", "Lua 5.4 (luac)", lambda: on_path("luac") or any_glob(os.path.join(LOCALAPPDATA, "Programs", "Lua", "bin", "luac.exe")), False, False),
        ("re", "x64dbg", "x64dbg", lambda: bool(x64dbg_exe()), False, False),
        ("re", "x64dbg-automate", "x64dbg-automate plugin + MCP",
         lambda: x64dbg_automate_plugin() and py_imports("x64dbg_automate") and "x64dbg" in mcp, False, False),
        ("re", "x64dbg-skills", "x64dbg-skills (Claude Code plugin)", lambda: "x64dbg-skills" in plugins, False, False),
        ("re", "ghidrust", "Ghidrust + MCP", lambda: "ghidrust" in mcp, False, False),
        ("drive", "vigembus", "ViGEmBus (virtual gamepad driver)", lambda: service_running("ViGEmBus"), True, False),
        ("drive", "vgamepad", "vgamepad (Python)", lambda: py_imports("vgamepad"), False, False),
        ("3d", "blender", "Blender", blender, False, False),
        ("3d", "blender-mcp", "Blender MCP (server + add-on)", lambda: "blender" in mcp and blender_addon(), False, False),
        ("vr", "steamvr", "SteamVR", lambda: steam_app_installed(250820), False, True),
        ("vr", "virtualdesktop", "Virtual Desktop Streamer", lambda: process_running("VirtualDesktop.Streamer.exe")
         or os.path.isdir(os.path.join(PROGRAMFILES, "Virtual Desktop Streamer")), False, True),
    ]


GROUP_TITLES = {"core": "1. Core", "build": "2. Building mod code", "re": "3. Reverse engineering",
                "drive": "4. Driving an app unattended", "3d": "5. 3D and assets", "vr": "6. VR"}


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--state", action="store_true")
    ap.add_argument("--mark-done", action="store_true")
    ap.add_argument("--choices", default="{}", help="JSON object: tool id -> installed-by-claude | user | skip")
    args = ap.parse_args()

    if args.state:
        print(json.dumps(load_state(), indent=2))
        return 0
    if args.mark_done:
        os.makedirs(STATE_DIR, exist_ok=True)
        state = load_state() or {}
        state["offered"] = datetime.date.today().isoformat()
        state.setdefault("choices", {}).update(json.loads(args.choices))
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        print(f"setup state saved: {STATE_FILE}")
        return 0

    rows = []
    for group, tid, name, check, admin, manual in catalog():
        try:
            present = bool(check())
        except Exception:  # a broken check must read as "not found", never crash the scan
            present = False
        rows.append({"group": group, "id": tid, "name": name, "present": present,
                     "needs_admin": admin, "manual_only": manual, "detail": None})
    for row in rows:
        if row["id"] == "blender-mcp" and row["present"]:
            # Say whether the link ANSWERS, so setup can skip the in-Blender steps for someone who
            # has already done them, and name the two clicks for someone who has not.
            row["detail"] = ("link live: Blender is open and answering" if blender_link_live()
                             else "installed, but not answering: open Blender, press N, "
                                  "MCP for Blender tab, Start MCP Server")
    if args.json:
        print(json.dumps({"state_file": STATE_FILE, "state": load_state(), "tools": rows}, indent=2))
        return 0
    for g, title in GROUP_TITLES.items():
        print(title)
        for r in (r for r in rows if r["group"] == g):
            flags = (" (needs admin)" if r["needs_admin"] else "") + (" (manual download)" if r["manual_only"] else "")
            suffix = f" - {r['detail']}" if r["detail"] else ("" if r["present"] else flags)
            print(f"  {'[x]' if r['present'] else '[ ]'} {r['name']}{suffix}")
    missing = sum(1 for r in rows if not r["present"])
    print(f"\n{len(rows) - missing} of {len(rows)} present. Details and links: docs/TOOLS.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
