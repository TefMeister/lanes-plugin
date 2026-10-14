#!/usr/bin/env python3
"""hand-freeze.py - install or update Hand Freeze from its public GitHub releases (0.64.0, 2026-10-14, asked for by
the maintainer: "make it part of lanes initial setup/update option to install it from our github").

Hand Freeze is a small desktop app that holds both VR controllers still in any OpenXR game, so hand and weapon poses
can be tuned with the mouse while the controllers lie on the desk. Source and releases:
https://github.com/TefMeister/hand-freeze-vr

    python hand-freeze.py status [--json]   installed or not, which release, and whether a newer one is out
    python hand-freeze.py install           download the newest release zip and run its own install.ps1
                                            (the same command updates an older copy)

Exit 0 = done or nothing to do, 1 = could not (the reason is printed), 2 = not applicable here (not Windows).

WHAT INSTALL DOES
  Fetches the newest release from GitHub's API (no sign-in needed), downloads its zip into a fresh temporary
  folder, unzips it, and runs the zip's own install.ps1, which copies three files to
  %LOCALAPPDATA%\\Programs\\HandFreeze and puts a "Hand Freeze" icon on the Desktop. No administrator rights.
  Nothing is switched on: the app's own ON/OFF button does that. The release tag is written next to the app
  (lanes-release.txt) so `status` can say whether a newer one is out. It refuses while the app is open, because
  Windows will not replace a running program.

Tests set LANES_HANDFREEZE_DIR (stands in for the install folder) and LANES_HANDFREEZE_RELEASE (a JSON file standing
in for GitHub's answer), so no network is needed.
"""
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

REPO = "TefMeister/hand-freeze-vr"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
NET_TIMEOUT_S = 30
LOCALAPPDATA = os.environ.get("LOCALAPPDATA", os.path.join(os.path.expanduser("~"), "AppData", "Local"))
INSTALL_DIR = os.environ.get("LANES_HANDFREEZE_DIR") or os.path.join(LOCALAPPDATA, "Programs", "HandFreeze")
EXE = "HandFreeze.exe"
MARKER = "lanes-release.txt"


def installed_tag():
    """None = not installed; "" = installed, but not by this tool (release unknown)."""
    if not os.path.isfile(os.path.join(INSTALL_DIR, EXE)):
        return None
    try:
        with open(os.path.join(INSTALL_DIR, MARKER), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def latest_release():
    fake = os.environ.get("LANES_HANDFREEZE_RELEASE")
    if fake:
        with open(fake, encoding="utf-8") as f:
            return json.load(f)
    req = urllib.request.Request(API_LATEST, headers={"Accept": "application/vnd.github+json",
                                                      "User-Agent": "lanes-plugin"})
    with urllib.request.urlopen(req, timeout=NET_TIMEOUT_S) as r:
        return json.load(r)


def app_running():
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {EXE}"], capture_output=True, text=True,
                             timeout=NET_TIMEOUT_S).stdout
        return EXE.lower() in out.lower()
    except (OSError, subprocess.TimeoutExpired):
        return False


def status(as_json):
    have = installed_tag()
    try:
        rel = latest_release()
        latest, err = rel.get("tag_name", ""), None
    except Exception as e:  # network down, rate limit: say so, never guess
        latest, err = "", str(e)
    newer = bool(latest) and have is not None and have != latest
    if as_json:
        print(json.dumps({"installed": have is not None, "installed_release": have or None,
                          "latest_release": latest or None, "newer": newer, "error": err}))
        return 0
    if have is None:
        print("Hand Freeze: not installed." + (f" Newest release: {latest}." if latest else ""))
    elif newer:
        print(f"Hand Freeze: installed ({have or 'release unknown'}); a newer release is out: {latest}.")
    else:
        print(f"Hand Freeze: installed, up to date ({have}).")
    if err:
        print(f"Could not reach GitHub: {err}")
    return 0


def install():
    if sys.platform != "win32" and not os.environ.get("LANES_HANDFREEZE_RELEASE"):
        print("Hand Freeze is a Windows app; nothing to do here.")
        return 2
    if app_running():
        print("Hand Freeze is open. Close its window first (that also unfreezes the hands), then run this again.")
        return 1
    try:
        rel = latest_release()
    except Exception as e:
        print(f"Could not reach GitHub: {e}")
        return 1
    tag = rel.get("tag_name", "")
    zips = [a for a in rel.get("assets", []) if a.get("name", "").lower().endswith(".zip")]
    if not zips:
        print(f"The newest release ({tag}) has no zip to install.")
        return 1
    work = tempfile.mkdtemp(prefix="handfreeze-")
    zpath = os.path.join(work, "release.zip")
    src = zips[0]["browser_download_url"]
    if src.startswith("file:") or os.path.isfile(src):          # tests hand a local zip
        with open(src.replace("file:", ""), "rb") as i, open(zpath, "wb") as o:
            o.write(i.read())
    else:
        req = urllib.request.Request(src, headers={"User-Agent": "lanes-plugin"})
        with urllib.request.urlopen(req, timeout=NET_TIMEOUT_S) as r, open(zpath, "wb") as o:
            o.write(r.read())
    out_dir = os.path.join(work, "unzipped")
    with zipfile.ZipFile(zpath) as z:
        for m in z.infolist():
            name = m.filename.replace("\\", "/")           # the release zip was made with Windows separators
            if name.endswith("/") or ".." in name.split("/"):
                continue
            dest = os.path.join(out_dir, *name.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with z.open(m) as i, open(dest, "wb") as o:
                o.write(i.read())
    scripts = [os.path.join(d, "install.ps1") for d, _, fs in os.walk(out_dir) if "install.ps1" in fs]
    if not scripts:
        print("The release zip has no install.ps1; nothing was installed.")
        return 1
    folder = os.path.dirname(scripts[0])
    if os.environ.get("LANES_HANDFREEZE_RELEASE"):        # tests: copy instead of running PowerShell
        os.makedirs(INSTALL_DIR, exist_ok=True)
        for f in os.listdir(folder):
            with open(os.path.join(folder, f), "rb") as i, open(os.path.join(INSTALL_DIR, f), "wb") as o:
                o.write(i.read())
    else:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", scripts[0],
                            "-From", folder], capture_output=True, text=True)
        if r.returncode != 0 or not os.path.isfile(os.path.join(INSTALL_DIR, EXE)):
            print("The installer did not finish:\n" + (r.stderr or r.stdout).strip())
            return 1
    with open(os.path.join(INSTALL_DIR, MARKER), "w", encoding="utf-8") as f:
        f.write(tag + "\n")
    print(f"Hand Freeze {tag} installed: its icon is on the Desktop. Switch it ON before starting a game.")
    # tell the other PCs (0.65.0): a note on the board, saved with it at the session's end
    if not os.environ.get("LANES_HANDFREEZE_RELEASE") or os.environ.get("LANES_BOARD"):
        subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "installed.py"),
                        "record", "Hand Freeze", tag])
    return 0


def main():
    args = sys.argv[1:]
    if not args or args[0] not in ("status", "install"):
        print(__doc__)
        return 1
    return status("--json" in args) if args[0] == "status" else install()


if __name__ == "__main__":
    sys.exit(main())
