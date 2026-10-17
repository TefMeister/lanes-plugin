"""vb_install - install or update the VR Bench layer from its public GitHub releases (TefMeister/vr-bench).

The same shape as hand-freeze.py: ask GitHub's API for the newest release (no sign-in), download its zip into a fresh
temporary folder, unzip it, run the zip's own install.ps1 (which copies the layer to %LOCALAPPDATA%\\Programs\\VRBench
and writes its manifests), note the release beside it, and tell the board (installed.py) so the other PC knows.
Installing registers NOTHING with OpenXR: `vrbench.py start` does that per run, for the game's bitness only.
It refuses while a run is on, because Windows will not replace a layer a game has loaded.

Tests set LANES_VRBENCH_LAYER_DIR (the install folder) and LANES_VRBENCH_RELEASE (a JSON file standing in for
GitHub's answer); then the files are copied instead of running PowerShell.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

import vb_layer
import vb_settings as S

REPO = "TefMeister/vr-bench"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
NET_TIMEOUT_S = 30
MARKER = "lanes-release.txt"
INSTALLED_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "installed.py")


def installed_tag():
    """None = not installed; "" = installed, but not by this tool (release unknown)"""
    if not os.path.isfile(os.path.join(S.LAYER_DIR, S.LAYER_DLL64)) and \
            not os.path.isfile(os.path.join(S.LAYER_DIR, S.LAYER_DLL32)):
        return None
    try:
        with open(os.path.join(S.LAYER_DIR, MARKER), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def latest_release():
    fake = os.environ.get("LANES_VRBENCH_RELEASE")
    if fake:
        with open(fake, encoding="utf-8") as f:
            return json.load(f)
    req = urllib.request.Request(API_LATEST, headers={"Accept": "application/vnd.github+json",
                                                      "User-Agent": "lanes-plugin"})
    with urllib.request.urlopen(req, timeout=NET_TIMEOUT_S) as r:
        return json.load(r)


def status():
    have = installed_tag()
    if os.environ.get("LANES_OPENXRSIM_OFFLINE") or os.environ.get("LANES_VRBENCH_OFFLINE"):   # start-up checks
        return {"installed": have is not None, "release": have or None, "latest_release": None, "newer": False,
                "error": None}
    try:
        latest, err = latest_release().get("tag_name", ""), None
    except Exception as e:   # network down, rate limit: say so, never guess
        latest, err = "", str(e)
    return {"installed": have is not None, "release": have or None, "latest_release": latest or None,
            "newer": bool(latest) and have is not None and have != latest, "error": err}


def _fetch(src, dest):
    if src.startswith("file:") or os.path.isfile(src):   # tests hand a local zip
        shutil.copyfile(src.replace("file:", ""), dest)
        return
    req = urllib.request.Request(src, headers={"User-Agent": "lanes-plugin"})
    with urllib.request.urlopen(req, timeout=NET_TIMEOUT_S) as r, open(dest, "wb") as o:
        o.write(r.read())


def _unzip(zpath, out_dir):
    with zipfile.ZipFile(zpath) as z:
        for m in z.infolist():
            name = m.filename.replace("\\", "/")   # a zip made on Windows may use its separators
            if name.endswith("/") or ".." in name.split("/"):
                continue
            dest = os.path.join(out_dir, *name.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with z.open(m) as i, open(dest, "wb") as o:
                o.write(i.read())


def install():
    testing = bool(os.environ.get("LANES_VRBENCH_RELEASE"))
    if sys.platform != "win32" and not testing:
        print("VR Bench is for Windows; nothing to do here.")
        return 2
    if vb_layer.registered():
        print("A VR Bench run is on (the layer is in the OpenXR list): stop it first with `vrbench.py stop`, "
              "close the game, then run this again.")
        return 1
    try:
        rel = latest_release()
    except Exception as e:
        print(f"Could not reach GitHub: {e}")
        return 1
    tag = rel.get("tag_name", "")
    zips = [a for a in rel.get("assets", []) if a.get("name", "").lower().endswith(".zip")]
    if not zips:
        print(f"The newest VR Bench release ({tag}) has no zip to install.")
        return 1
    work = tempfile.mkdtemp(prefix="vrbench-")
    try:
        zpath = os.path.join(work, "release.zip")
        _fetch(zips[0]["browser_download_url"], zpath)
        out_dir = os.path.join(work, "unzipped")
        _unzip(zpath, out_dir)
        scripts = [os.path.join(d, "install.ps1") for d, _, fs in os.walk(out_dir) if "install.ps1" in fs]
        if not scripts:
            print("The release zip has no install.ps1; nothing was installed.")
            return 1
        folder = os.path.dirname(scripts[0])
        if testing:   # copy instead of running PowerShell
            os.makedirs(S.LAYER_DIR, exist_ok=True)
            for f in os.listdir(folder):
                shutil.copyfile(os.path.join(folder, f), os.path.join(S.LAYER_DIR, f))
        else:
            r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", scripts[0],
                                "-From", folder], capture_output=True, text=True)
            if r.returncode != 0 or installed_tag() is None:
                print("The installer did not finish:\n" + (r.stderr or r.stdout).strip())
                return 1
    finally:
        shutil.rmtree(work, ignore_errors=True)
    with open(os.path.join(S.LAYER_DIR, MARKER), "w", encoding="utf-8") as f:
        f.write(tag + "\n")
    print(f"VR Bench {tag} installed. Nothing is switched on: `vrbench.py start <game>` does that for one run.")
    if not testing or os.environ.get("LANES_BOARD"):   # tell the other PCs: a note on the board
        subprocess.run([sys.executable, INSTALLED_PY, "record", "VR Bench", tag])
    return 0


def uninstall():
    if vb_layer.registered():
        print("A VR Bench run is on: stop it first with `vrbench.py stop`.")
        return 1
    vb_layer.stop()
    if os.path.isdir(S.LAYER_DIR):
        shutil.rmtree(S.LAYER_DIR)
    print("VR Bench layer removed. Its runs and pictures stay where they are.")
    return 0
