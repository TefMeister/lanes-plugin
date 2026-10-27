#!/usr/bin/env python3
"""ours.py - our own apps and libraries from TefMeister's GitHub, each an optional download with its link (0.93.0).

The maintainer, 2026-10-27, the day the other makers' tools went in (outside.py, 0.92.0): "please go through our
githubs tools, skills and all that good stuff and add the optional features to Lanes". Each one here is also an
extra in features.py (set "ours"), so a PC switches it on or off there; this file knows how to get it.

    python ours.py list [--json]          every one: on or off, got or not, the link
    python ours.py get <name>|on          download and install one (or every one switched on); safe to re-run
    python ours.py newer                  the apps got here that have a newer release (exit 0 = none)

HOW EACH ONE IS GOT ("kind"):
  app      the newest release zip, checked against the release's SHA256SUMS.txt when it has one, unpacked into a
           fresh temporary folder, then the zip's own install.ps1 copies it to %LOCALAPPDATA%\\Programs\\<folder> and
           puts its icon on the Desktop (no administrator rights). An app with no release yet says so and installs
           nothing. Nothing is switched on in any game: each app has its own ON button.
  blender  a shallow clone, then the newest add-on zip in its dist\\ folder is installed into Blender 4.2 or newer
  git      a shallow clone into <ours_dir>/<name> (pulled when it is there already)
Hand Freeze and VR Bench have their own installers (hand-freeze.py, vrbench.py) and their own setup questions, so they
are not repeated here. Apps still private (they are, until they work) are never listed.
WHERE: apps in %LOCALAPPDATA%\\Programs; the rest in `ours_dir =` from lanes.conf, else ~/Documents/Lanes our tools.
Tests: LANES_OURS_DIR, LANES_OURS_APPS (stands in for %LOCALAPPDATA%\\Programs), LANES_OURS_FAKE (a JSON file standing
in for GitHub's answers), LANES_CONFIG, LANES_STATE_DIR. With LANES_OURS_FAKE set, install.ps1 is not run: its folder
is copied instead.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import outside  # noqa: E402  (the release reader, the checked download, the runner and the clone)

GH = "https://github.com/"
LOCALAPPDATA = os.environ.get("LOCALAPPDATA", os.path.join(os.path.expanduser("~"), "AppData", "Local"))
MARKER = "lanes-release.txt"

# name: what it is. `repo` is its GitHub home; an app names its install folder and program.
TOOLS = {
    "window_view": {"label": "Window View", "repo": "TefMeister/window-view-vr", "kind": "app",
                    "folder": "WindowView", "exe": "WindowView.exe",
                    "what": "hangs any desktop window (Hand Freeze, Hand Poser, a browser) inside any OpenXR game "
                            "(Direct3D 11 and 12), see-through as you like, used with the mouse and keyboard (Page Up "
                            "/ Page Down) or the VR controllers while the game only hears the controllers, so a mod "
                            "can be tuned without taking the headset off"},
    "hand_poser": {"label": "Hand Poser (untested)", "repo": "TefMeister/hand-poser-vr", "kind": "app",
                   "folder": "HandPoser", "exe": "HandPoser.exe",
                   "what": "a compact window of sliders that poses the player's fingers and wrists live in RE Engine "
                           "games (needs REFramework): one box per finger, undo, autosave, named poses, one pose per "
                           "gun. Inspired by alphaZomega's EMV Engine; not yet confirmed in a real headset session"},
    "grip_zones": {"label": "Grip Zones", "repo": "TefMeister/grip-zones-vr", "kind": "app",
                   "folder": "GripZones", "exe": "GripZones.exe",
                   "what": "a small window of sliders that moves and resizes every place the hand can grip a gun in "
                           "VR (magazine, well, slide, pump or bolt, front grip), live on the gun, made to hang in "
                           "the headset through Window View. Works with Visceral RE8 for now (Resident Evil Village "
                           "VR); called Grab Zones until 2026-10-27"},
    "cubekit": {"label": "CubeKit (Blender add-on)", "repo": "TefMeister/blender-cubekit", "kind": "blender",
                "what": "builds pixel-style models out of little cubes from a settings file: one cube size, pick any "
                        "single cube, carved wear, stop-motion animation and export for GZDoom; made for the "
                        "old-school shooter weapons and hands (Blender 4.2 or newer)"},
    "re_toolkit": {"label": "Flat-to-VR RE toolkit", "repo": "TefMeister/flat-to-vr-RE-toolkit", "kind": "git",
                   "after": "read TOOLKIT.md first; the small tools are in tools/, the method in PLAYBOOK.md",
                   "what": "the tested tools and the playbook for turning a flat game into VR: window capture and "
                           "measuring, key, mouse and pretend-gamepad senders, shader readers that find the camera "
                           "matrices, PE and export readers, and an OpenXR probe that checks the VR plumbing with no "
                           "headset"},
    "control_profiles": {"label": "Game control profiles", "repo": "TefMeister/ai-game-control-profiles",
                         "kind": "git", "routes": "routes",
                         "what": "how to drive each game by program: recorded menu routes for Menu-o-matiC and "
                                 "Move-o-matiC and a KNOWN.md per game (each screen and the key past it, the controls "
                                 "that work, the hazards), so a session reaches gameplay without poking at keys"},
    "cross_engine_library": {"label": "Cross-engine VR library", "repo": "TefMeister/flat-to-vr-cross-engine-research",
                             "kind": "git", "after": "start at its engines index; /lanes:gr and /lanes:sr read it",
                             "what": "what is publicly known about putting flat games into VR, one page per engine "
                                     "family (Unreal, RE Engine, id Tech, Dunia and more), with links to each "
                                     "project's own notes; the research lanes read it before searching the web"},
    "begone_knowledge": {"label": "BeG0nE knowledge", "repo": "TefMeister/BeG0nE", "kind": "git",
                         "after": "read knowledge/FINDINGS.md when a jitter or hand fault comes up",
                         "what": "the home of the BeG0nE tools: each VR fault explained (jitter, ghost hands, drifting "
                                 "two-handed aim, flickers), each game's fix, and what 200+ headset tests have taught "
                                 "so far; the recorders themselves already ship inside Lanes"},
    "terminal_themes": {"label": "More terminal looks", "repo": "TefMeister/terminal-themes", "kind": "git",
                        "after": "/lanes:theme puts the Lanes look on; each other look in styles/ has its own README",
                        "what": "the other retro looks for Windows Terminal beside the green one Lanes ships with: the "
                                "starburst monitor, the plain green monitor, sharp scanlines and more, each a small "
                                "shader plus a colour scheme"},
}


def feature_name(name):
    return "ours_" + name


def is_on(name):
    import features
    return features.is_on(feature_name(name))


def root():
    return (os.environ.get("LANES_OURS_DIR") or outside.conf_value("ours_dir")
            or os.path.join(os.path.expanduser("~"), "Documents", "Lanes our tools"))


def apps_dir():
    return os.environ.get("LANES_OURS_APPS") or os.path.join(LOCALAPPDATA, "Programs")


def where(name):
    t = TOOLS[name]
    return os.path.join(apps_dir(), t["folder"]) if t["kind"] == "app" else os.path.join(root(), name)


def got(name):
    try:
        return open(os.path.join(where(name), MARKER), encoding="utf-8").read().strip()
    except OSError:
        return None


def mark(name, release):
    d = where(name)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, MARKER), "w", encoding="utf-8").write(release + "\n")


def latest(repo):
    fake = os.environ.get("LANES_OURS_FAKE")
    if fake:
        return json.load(open(fake, encoding="utf-8")).get(repo)
    return outside.latest(repo)


def app_running(exe):
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {exe}"], capture_output=True, text=True,
                             timeout=30).stdout
        return exe.lower() in out.lower()
    except (OSError, subprocess.SubprocessError):
        return False


def get_app(name, t):
    if os.name != "nt" and not os.environ.get("LANES_OURS_FAKE"):
        return [f"{t['label']}: Windows only"]
    if app_running(t["exe"]):
        raise RuntimeError(f"{t['exe']} is open: close it first, then run this again")
    rel = latest(t["repo"])
    if not rel:
        return [f"{t['label']}: no release to download yet. Its page: {GH}{t['repo']}"]
    work = tempfile.mkdtemp(prefix="lanes-ours-")
    before = os.environ.get("LANES_OUTSIDE_DIR")
    try:
        os.environ["LANES_OUTSIDE_DIR"] = work                  # the download lands in the temporary folder
        z = outside.checked_download(name, rel, ".zip")
        if before is None:
            del os.environ["LANES_OUTSIDE_DIR"]
        else:
            os.environ["LANES_OUTSIDE_DIR"] = before
        out = os.path.join(work, "unzipped")
        with zipfile.ZipFile(z) as f:
            for m in f.infolist():
                n = m.filename.replace("\\", "/")
                if n.endswith("/") or ".." in n.split("/"):
                    continue
                dest = os.path.join(out, *n.split("/"))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with f.open(m) as i, open(dest, "wb") as o:
                    o.write(i.read())
        scripts = [os.path.join(d, "install.ps1") for d, _, fs in os.walk(out) if "install.ps1" in fs]
        if not scripts:
            raise RuntimeError("the release zip has no install.ps1: nothing installed")
        folder = os.path.dirname(scripts[0])
        if os.environ.get("LANES_OURS_FAKE"):                   # tests: copy instead of running PowerShell
            shutil.copytree(folder, where(name), dirs_exist_ok=True)
        else:
            outside.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", scripts[0],
                         "-From", folder])
        if not os.path.isfile(os.path.join(where(name), t["exe"])):
            raise RuntimeError("the installer finished but the app is not there")
    finally:
        if os.environ.get("LANES_OUTSIDE_DIR") == work:
            if before is None:
                del os.environ["LANES_OUTSIDE_DIR"]
            else:
                os.environ["LANES_OUTSIDE_DIR"] = before
        shutil.rmtree(work, ignore_errors=True)
    mark(name, rel["tag_name"])
    if not os.environ.get("LANES_OURS_FAKE"):                   # tell the other PCs (installed.py, 0.65.0)
        subprocess.run([sys.executable, os.path.join(HERE, "installed.py"), "record", t["label"].split(" (")[0],
                        rel["tag_name"]], capture_output=True)
    return [f"{t['label']} {rel['tag_name']}: installed, its icon is on the Desktop"]


def clone(name, repo):
    d = where(name)
    if os.path.isdir(os.path.join(d, ".git")):
        outside.run(["git", "-C", d, "pull", "-q", "--ff-only"])
    else:
        os.makedirs(os.path.dirname(d), exist_ok=True)
        outside.run(["git", "clone", "-q", "--depth", "1", f"{GH}{repo}.git", d])
    return d, outside.run(["git", "-C", d, "rev-parse", "--short", "HEAD"]).strip()


def blender_exe():
    found = sorted(glob.glob(os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"), "Blender Foundation",
                                          "*", "blender.exe")))
    return found[-1] if found else shutil.which("blender")


def vkey(path):
    v = os.path.basename(path).rsplit("-", 1)[-1].replace(".zip", "")
    return tuple(int(x) for x in v.split(".") if x.isdigit())


def get(name):
    t = TOOLS[name]
    if t["kind"] == "app":
        return get_app(name, t)
    d, head = clone(name, t["repo"])
    notes = []
    if t["kind"] == "blender":
        zips = sorted(glob.glob(os.path.join(d, "dist", "*.zip")), key=vkey)
        exe = blender_exe()
        if not zips:
            notes.append("no add-on zip in its dist folder yet")
        elif not exe:
            notes.append(f"Blender not found: install Blender 4.2 or newer, then run this again (or install "
                         f"{os.path.basename(zips[-1])} from Blender's Get Extensions > Install from Disk)")
        else:
            outside.run([exe, "--command", "extension", "install-file", "--repo", "user_default", "--enable",
                         zips[-1]])
            notes.append(f"{os.path.basename(zips[-1])} installed into Blender: restart Blender to see it")
    if t.get("routes"):
        import features
        if not outside.conf_value("routes"):
            features.set_conf("routes", os.path.join(d, t["routes"]).replace("\\", "/"), "the games' menu routes")
            notes.append("lanes.conf now points routes = at its routes folder")
    mark(name, "git " + head)
    if t.get("after"):
        notes.append(t["after"])
    return [f"{t['label']}: got ({got(name)}) in {d}"] + notes


def newer():
    out = []
    for name, t in TOOLS.items():
        have = got(name)
        if not have or t["kind"] != "app":
            continue
        rel = latest(t["repo"])
        if rel and rel.get("tag_name") and rel["tag_name"] != have:
            out.append(f"{t['label']}: {have} -> {rel['tag_name']} ({GH}{t['repo']}/releases)")
    return out


def rows():
    return [{"name": n, "label": t["label"], "maker": "TefMeister", "link": GH + t["repo"], "what": t["what"],
             "kind": t["kind"], "on": is_on(n), "got": got(n)} for n, t in TOOLS.items()]


def main(a):
    cmd = a[0] if a else "list"
    if cmd == "list":
        r = rows()
        if "--json" in a:
            print(json.dumps(r, indent=1))
        else:
            for x in r:
                print(f"{x['name']:21} {'ON ' if x['on'] else 'off'}  {x['got'] or '-':18} {x['label']}: {x['link']}")
        return 0
    if cmd == "get" and len(a) > 1:
        names = [n for n in TOOLS if is_on(n)] if a[1] == "on" else [a[1]]
        bad = 0
        for n in names:
            if n not in TOOLS:
                print(f"nothing of ours called {n}; known: {', '.join(TOOLS)}")
                return 2
            try:
                print("\n  ".join(get(n)))
            except Exception as e:
                print(f"{TOOLS[n]['label']}: NOT got: {e}")
                bad += 1
        return 1 if bad else 0
    if cmd == "newer":
        n = newer()
        print("\n".join(n) or "every app of ours here is the newest")
        return 1 if n else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
