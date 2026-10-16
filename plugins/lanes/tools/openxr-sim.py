#!/usr/bin/env python3
"""openxr-sim.py - download the OpenXR Simulator, a headset you do not need to own (0.73.0, 2026-10-16, asked for by
the maintainer: "an option to download elliotttate openxr simulator, if it's not already, on the first install or the
next update").

The OpenXR Simulator is an OpenXR runtime that shows a VR game's two eyes in a desktop window, with the head and the
controllers moved by mouse, keyboard or small command files. With it, VR work can be built and checked on a PC with no
headset plugged in. Two public sources, both free:

  original  https://github.com/elliotttate/OpenXR-Simulator   by elliotttate, who wrote it (64-bit games)
  fork      https://github.com/webhead2oo9/OpenXR-Simulator   webhead2oo9's fork: adds a 32-bit runtime for 32-bit
            games, command files for the controllers' poses, trigger and A button, screenshots, and a helper for
            Claude Code (an MCP server)

    python openxr-sim.py status [--json]          on this PC or not, where, which release, and whether a newer one is out
    python openxr-sim.py install [--fork] [--to FOLDER]
                                                  download the newest release into FOLDER (default: the folder it is
                                                  already in, else %LOCALAPPDATA%\\Programs\\OpenXR-Simulator); the same
                                                  command updates it
    python openxr-sim.py decline                  remember that the person said no, so the offer is not repeated

Exit 0 = done or nothing to do, 1 = could not (the reason is printed), 2 = not applicable here (not Windows).

WHAT INSTALL DOES, AND DOES NOT
  Fetches the newest release from GitHub's API (no sign-in), downloads its zip into a fresh temporary folder, checks
  it against the release's own SHA-256 file when there is one, and unpacks it into the folder. It does NOT switch the
  simulator on: that would change which runtime EVERY OpenXR game on the PC uses. To use it for one game, point that
  game's mod at the simulator's json (for example a runtime_json setting); to use it for every game, run the
  "Activate Simulator" script in its folder (Windows asks for approval), and "Deactivate Simulator" to go back to the
  headset. It refuses to update while a game has the simulator loaded, because Windows will not replace it then.

FINDING A COPY: the folder named by `openxr_sim =` in lanes.conf, the default folder, and any OpenXR runtime registered
in Windows whose file name is openxr_simulator*.json. The release is read from lanes-release.txt beside it (written by
install); a copy installed by hand has no release on record and is reported as "release unknown".

Tests set LANES_OPENXRSIM_DIR (the default folder), LANES_OPENXRSIM_OFFLINE=1 (status without asking GitHub), LANES_OPENXRSIM_RELEASE (a JSON file standing in for GitHub's
answer), LANES_OPENXRSIM_NOREG=1 (skip the registry), LANES_STATE_DIR and LANES_CONFIG, so no network is needed.
"""
import glob
import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile

SOURCES = {"original": "elliotttate/OpenXR-Simulator", "fork": "webhead2oo9/OpenXR-Simulator"}
NET_TIMEOUT_S = 60
HOME = os.path.expanduser("~")
LOCALAPPDATA = os.environ.get("LOCALAPPDATA", os.path.join(HOME, "AppData", "Local"))
DEFAULT_DIR = os.environ.get("LANES_OPENXRSIM_DIR") or os.path.join(LOCALAPPDATA, "Programs", "OpenXR-Simulator")
STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(HOME, ".claude", "lanes")
STATE_FILE = os.path.join(STATE_DIR, "openxr-sim-state.json")
MARKER = "lanes-release.txt"           # "<source> <tag>"
DLL64, DLL32 = "openxr_simulator.dll", "openxr_simulator-32.dll"


def conf_files():
    if os.environ.get("LANES_CONFIG"):
        return [os.environ["LANES_CONFIG"]]
    return [os.path.join(HOME, ".claude", "lanes.conf"), os.path.join(HOME, ".config", "lanes", "lanes.conf")]


def conf_folder():
    for c in conf_files():
        try:
            for line in open(c, encoding="utf-8"):
                k, _, v = line.partition("=")
                if k.strip() == "openxr_sim" and v.strip():
                    return os.path.expandvars(v.split(" #")[0].strip().strip('"'))
        except OSError:
            pass
    return None


def registered_folders():
    """folders of OpenXR runtimes registered in Windows whose json is the simulator's"""
    if os.environ.get("LANES_OPENXRSIM_NOREG") or sys.platform != "win32":
        return []
    import winreg
    out = []
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                k = winreg.OpenKey(hive, r"SOFTWARE\Khronos\OpenXR\1\AvailableRuntimes", 0, winreg.KEY_READ | view)
            except OSError:
                continue
            i = 0
            while True:
                try:
                    name = winreg.EnumValue(k, i)[0]
                except OSError:
                    break
                i += 1
                if os.path.basename(name).lower().startswith("openxr_simulator") and os.path.isfile(name):
                    out.append(os.path.dirname(name))
    return out


def find_copy():
    """the folder holding the simulator on this PC, or None"""
    for d in [conf_folder(), DEFAULT_DIR] + registered_folders():
        if d and os.path.isfile(os.path.join(d, DLL64)):
            return os.path.normpath(d)
    return None


def marker(folder):
    """(source, tag), or (None, "") for a copy installed by hand"""
    try:
        with open(os.path.join(folder, MARKER), encoding="utf-8") as f:
            src, _, tag = f.read().strip().partition(" ")
            return (src if src in SOURCES else None), tag
    except OSError:
        return None, ""


def latest_release(source):
    fake = os.environ.get("LANES_OPENXRSIM_RELEASE")
    if fake:
        with open(fake, encoding="utf-8") as f:
            return json.load(f)[source]
    url = f"https://api.github.com/repos/{SOURCES[source]}/releases/latest"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "lanes-plugin"})
    with urllib.request.urlopen(req, timeout=NET_TIMEOUT_S) as r:
        return json.load(r)


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(st):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f)


def status(as_json):
    folder = find_copy()
    src, have = marker(folder) if folder else (None, "")
    check_src = src or "original"
    latest, err = "", None
    if not os.environ.get("LANES_OPENXRSIM_OFFLINE"):     # the setup scan only asks whether it is there
        try:
            latest = latest_release(check_src).get("tag_name", "")
        except Exception as e:      # network down, rate limit: say so, never guess
            err = str(e)
    newer = bool(folder) and bool(have) and bool(latest) and have != latest
    st = load_state()
    info = {"installed": folder is not None, "folder": folder, "source": src, "release": have or None,
            "has_32bit": bool(folder) and os.path.isfile(os.path.join(folder, DLL32)),
            "latest_release": latest or None, "newer": newer, "declined": bool(st.get("declined")), "error": err}
    if as_json:
        print(json.dumps(info))
        return 0
    if not folder:
        print("OpenXR Simulator: not on this PC." + (f" Newest release ({SOURCES['original']}): {latest}." if latest else ""))
    else:
        bits = "64-bit and 32-bit games" if info["has_32bit"] else "64-bit games only"
        rel = f"{src} {have}" if have else "release unknown (installed by hand)"
        print(f"OpenXR Simulator: on this PC ({rel}; for {bits}).")
        if newer:
            print(f"A newer release is out: {latest}.")
    if err:
        print(f"Could not reach GitHub: {err}")
    return 0


def dll_in_use(folder):
    for name in (DLL64, DLL32):
        p = os.path.join(folder, name)
        if not os.path.isfile(p):
            continue
        try:
            with open(p, "r+b"):     # Windows refuses to open a loaded dll for writing
                pass
        except PermissionError:
            return True
        except OSError:
            pass
    return False


def safe_extract(zpath, out_dir):
    with zipfile.ZipFile(zpath) as z:
        names = [m.filename.replace("\\", "/") for m in z.infolist()]
        tops = {n.split("/")[0] for n in names if n.strip("/")}
        strip = len(tops) == 1 and all("/" in n for n in names if n.strip("/"))   # one top folder: unpack its contents
        for m, name in zip(z.infolist(), names):
            parts = [p for p in name.split("/") if p]
            if strip:
                parts = parts[1:]
            if not parts or name.endswith("/") or ".." in parts:
                continue
            dest = os.path.join(out_dir, *parts)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with z.open(m) as i, open(dest, "wb") as o:
                shutil.copyfileobj(i, o)


def fetch(url, dest):
    if url.startswith("file:") or os.path.isfile(url):          # tests hand a local file
        shutil.copyfile(url.replace("file:", ""), dest)
        return
    req = urllib.request.Request(url, headers={"User-Agent": "lanes-plugin"})
    with urllib.request.urlopen(req, timeout=NET_TIMEOUT_S) as r, open(dest, "wb") as o:
        shutil.copyfileobj(r, o)


def install(source, to):
    if sys.platform != "win32" and not os.environ.get("LANES_OPENXRSIM_RELEASE"):
        print("The OpenXR Simulator is for Windows; nothing to do here.")
        return 2
    folder = os.path.normpath(to) if to else (find_copy() or DEFAULT_DIR)
    if os.path.isdir(folder) and dll_in_use(folder):
        print("A game has the simulator loaded right now. Close the game, then run this again.")
        return 1
    try:
        rel = latest_release(source)
    except Exception as e:
        print(f"Could not reach GitHub: {e}")
        return 1
    tag = rel.get("tag_name", "")
    assets = rel.get("assets", [])
    zips = [a for a in assets if a.get("name", "").lower().endswith(".zip")]
    if not zips:
        print(f"The newest release ({tag}) has no zip to download.")
        return 1
    work = tempfile.mkdtemp(prefix="openxr-sim-")
    try:
        zpath = os.path.join(work, zips[0]["name"])
        fetch(zips[0]["browser_download_url"], zpath)
        sums = [a for a in assets if a.get("name", "").lower() == zips[0]["name"].lower() + ".sha256"]
        if sums:
            spath = zpath + ".sha256"
            fetch(sums[0]["browser_download_url"], spath)
            want = open(spath, encoding="utf-8").read().split()[0].lower()
            got = hashlib.sha256(open(zpath, "rb").read()).hexdigest()
            if want != got:
                print(f"The download does not match the release's SHA-256 file ({got[:12]} against {want[:12]}); "
                      "nothing was installed.")
                return 1
        out_dir = os.path.join(work, "unzipped")
        safe_extract(zpath, out_dir)
        if not glob.glob(os.path.join(out_dir, "**", DLL64), recursive=True):
            print(f"The release zip has no {DLL64}; nothing was installed.")
            return 1
        os.makedirs(folder, exist_ok=True)
        for d, _, fs in os.walk(out_dir):
            rel_d = os.path.relpath(d, out_dir)
            for f in fs:
                dest_dir = os.path.join(folder, rel_d) if rel_d != "." else folder
                os.makedirs(dest_dir, exist_ok=True)
                shutil.copyfile(os.path.join(d, f), os.path.join(dest_dir, f))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    with open(os.path.join(folder, MARKER), "w", encoding="utf-8") as f:
        f.write(f"{source} {tag}\n")
    st = load_state()
    st.update({"installed": True, "declined": False})
    save_state(st)
    bits = "64-bit and 32-bit games" if os.path.isfile(os.path.join(folder, DLL32)) else "64-bit games only"
    print(f"OpenXR Simulator {tag} ({SOURCES[source]}, for {bits}) is in {folder}.")
    print("It is NOT switched on. For one game: point that game's mod at its json. For every game: run "
          "'Activate Simulator' in that folder (and 'Deactivate Simulator' to go back to the headset).")
    if bits.endswith("only"):
        print("32-bit games need webhead2oo9's fork: python openxr-sim.py install --fork")
    return 0


def decline():
    st = load_state()
    st["declined"] = True
    save_state(st)
    print("Noted: the OpenXR Simulator will not be offered again. `/lanes:setup` still lists it.")
    return 0


def main():
    args = sys.argv[1:]
    if not args or args[0] not in ("status", "install", "decline"):
        print(__doc__)
        return 1
    if args[0] == "status":
        return status("--json" in args)
    if args[0] == "decline":
        return decline()
    to = args[args.index("--to") + 1] if "--to" in args and args.index("--to") + 1 < len(args) else None
    return install("fork" if "--fork" in args else "original", to)


if __name__ == "__main__":
    sys.exit(main())
