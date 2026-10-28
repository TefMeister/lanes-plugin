#!/usr/bin/env python3
"""outside.py - other people's tools that help flat-to-VR work, each an optional download with its link (0.92.0).

The maintainer, 2026-10-27, after a look through elliotttate's GitHub: "just bake anything you think we can use into
Lanes plugin as optional downloads with the links and descriptions and use all of them, as i see it there is no 'too
many tools'". Each tool here is also an extra in features.py (set "outside"), so a PC switches it on or off there;
this file knows how to get it.

    python outside.py list [--json]          every tool: on or off, got or not, the newest release, the link
    python outside.py get <name>|on          download and install one (or every one switched on); safe to re-run
    python outside.py newer                  the tools got here that have a newer release (exit 0 = none)

HOW EACH ONE IS GOT ("kind"):
  setup   the release's installer, checked against the release's SHA256SUMS.txt, then run (it may ask for admin)
  zip     the release's zip, checked the same way, unpacked into <outside_dir>/<name>
  git     a shallow clone into <outside_dir>/<name> (pulled when it is there already)
  mcp     git, then its own Python environment (.venv, `pip install -e .`), then `claude mcp add --scope user`
  link    nothing to download: the link and what to do are printed
  `needs` is what has to be on the PC first (a program from winget, or a download only its maker offers); get says so
  and, for winget ids, installs it.
WHERE: `outside_dir =` in lanes.conf, else ~/Documents/Lanes outside tools. Each folder gets lanes-release.txt.
Tests: LANES_OUTSIDE_DIR, LANES_OUTSIDE_FAKE (a JSON file standing in for the GitHub answers), LANES_CONFIG.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
NET_TIMEOUT_S = 120
RUN_TIMEOUT_S = 900
GH = "https://github.com/"

# name: what it is. `feature` is its features.py name; `repo` its GitHub home; `asset` the release file to take.
TOOLS = {
    "obs_mirror": {"label": "OpenXR OBS Mirror", "maker": "elliotttate", "repo": "elliotttate/OpenXR-Layer-OBSMirror",
                   "kind": "setup", "asset": "Setup.exe", "needs": ["OBS Studio"],
                   "what": "lets OBS record what the headset is shown, in Direct3D 11 and 12 OpenXR games and SteamVR; "
                           "the BeG0nE recording then films the headset view beside the game window (the Resident Evil "
                           "games included)"},
    "xrfps": {"label": "xrFPS", "maker": "elliotttate", "repo": "elliotttate/xrFPS", "kind": "setup",
              "asset": "Setup.exe",
              "what": "turn a controller upside down in any OpenXR game to see the frame rate and frame times as a "
                      "graph, inside the headset"},
    "openxr_cas": {"label": "OpenXR CAS", "maker": "elliotttate", "repo": "elliotttate/OpenXR-CAS", "kind": "zip",
                   "asset": ".zip", "after": "run Install-Layer.ps1 from its folder as administrator to switch it on",
                   "what": "sharpens the headset picture (AMD's FidelityFX CAS) and adjusts colour in any OpenXR game; "
                           "changes what every test sees, so it is downloaded, not switched on"},
    "pix_mcp": {"label": "PIX MCP", "maker": "elliotttate", "repo": "elliotttate/pix-mcp", "kind": "mcp",
                "mcp": "pix", "exe": "pix-mcp", "needs": ["winget:Microsoft.PIX"],
                "what": "takes apart one captured frame of a Direct3D 12 game, draw by draw, through Microsoft PIX: "
                        "which pass drew what, with which textures and numbers (the RE Engine games are Direct3D 12)"},
    "nsight_mcp": {"label": "Nsight Graphics MCP", "maker": "elliotttate", "repo": "elliotttate/nsight-graphics-mcp",
                   "kind": "mcp", "mcp": "nsight-graphics", "exe": "nsight-graphics-mcp",
                   "needs": ["NVIDIA Nsight Graphics, from https://developer.nvidia.com/nsight-graphics (an NVIDIA "
                             "graphics card only)"],
                   "what": "the same for NVIDIA's frame tool: capture a frame of a D3D11, D3D12 or Vulkan game and "
                           "read every draw, resource and timing from it"},
    "vrframework": {"label": "vrframework guides", "maker": "elliotttate", "repo": "elliotttate/vrframework",
                    "kind": "git",
                    "what": "a 17-part guide to making a flat game VR from the outside, built on REFramework and two "
                            "of mutars' ports: frame timing, one eye per frame (AFR) and its smearing, per-eye "
                            "projection, HUD, input. Read, not built: its code is a scaffold"},
    "melon_mcp": {"label": "MelonMCP", "maker": "elliotttate", "repo": "elliotttate/MelonMCP", "kind": "git",
                  "after": "build it with `dotnet build -c Release` when a Unity game with MelonLoader comes along",
                  "what": "a live connection into Unity games through MelonLoader: inspect and change the running "
                          "game, the Unity cousin of the RE Engine and UEVR connectors"},
    "uevr_comfort": {"label": "UEVR cutscene comfort", "maker": "elliotttate",
                     "repo": "elliotttate/uevr-cutscene-comfort", "kind": "git",
                     "after": "build with CMake + Visual Studio 2022 against a UEVR source checkout; copy "
                              "CutsceneComfort.dll into the game's UEVR profile plugins folder",
                     "what": "a UEVR plugin that puts the camera back after a cutscene by itself, and can show "
                             "cutscenes on a still screen in the room, for Unreal games such as Silent Hill 2"},
    "uevr_renderdoc": {"label": "UEVR RenderDoc Capture", "maker": "elliotttate",
                       "repo": "elliotttate/UEVR-RenderDoc-Capture", "kind": "zip", "asset": ".zip",
                       "what": "UEVR with RenderDoc built in: grab one real Direct3D 12 frame, flat or stereo, from an "
                               "Unreal game and open it in RenderDoc"},
    "uevr_6dof_window": {"label": "UEVR 6DOF window", "maker": "elliotttate", "repo": "elliotttate/UEVR-6DOF-Window",
                         "kind": "link",
                         "after": "a whole UEVR fork; build it only if its comfort window is wanted for a game",
                         "what": "a UEVR fork with a comfort mode that shows the game in a stereo window you can lean "
                                 "around, for games that are uncomfortable in full VR"},
}


def conf_path():
    return os.environ.get("LANES_CONFIG") or os.path.join(os.path.expanduser("~"), ".claude", "lanes.conf")


def conf_value(key):
    try:
        for line in open(conf_path(), encoding="utf-8"):
            k, _, v = line.partition("=")
            if k.strip() == key:
                return v.split(" #")[0].strip().strip('"')
    except OSError:
        pass
    return None


def root():
    return (os.environ.get("LANES_OUTSIDE_DIR") or conf_value("outside_dir")
            or os.path.join(os.path.expanduser("~"), "Documents", "Lanes outside tools"))


def feature_name(name):
    return "outside_" + name


def is_on(name):
    sys.path.insert(0, HERE)
    import features
    return features.is_on(feature_name(name))


def latest(repo):
    fake = os.environ.get("LANES_OUTSIDE_FAKE")
    if fake:
        return json.load(open(fake, encoding="utf-8")).get(repo)
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases/latest",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "lanes-plugin"})
    try:
        with urllib.request.urlopen(req, timeout=NET_TIMEOUT_S) as r:
            return json.load(r)
    except Exception:
        return None


def fetch(url, dest):
    if url.startswith("file:"):
        shutil.copyfile(url[5:], dest)
        return
    req = urllib.request.Request(url, headers={"User-Agent": "lanes-plugin"})
    with urllib.request.urlopen(req, timeout=NET_TIMEOUT_S) as r, open(dest, "wb") as o:
        shutil.copyfileobj(r, o)


def got(name):
    try:
        return open(os.path.join(root(), name, "lanes-release.txt"), encoding="utf-8").read().strip()
    except OSError:
        return None


def mark(name, release):
    d = os.path.join(root(), name)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "lanes-release.txt"), "w", encoding="utf-8").write(release + "\n")


def checked_download(name, rel, pattern):
    """the release file whose name ends with `pattern`, in <root>/<name>/downloads, checked against SHA256SUMS.txt
    when the release has one; returns its path, or raises"""
    assets = {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])}
    pick = next((n for n in assets if n.endswith(pattern)), None)
    if not pick:
        raise RuntimeError(f"the newest release has no file ending {pattern}")
    d = os.path.join(root(), name, "downloads")
    os.makedirs(d, exist_ok=True)
    dest = os.path.join(d, pick)
    fetch(assets[pick], dest)
    if "SHA256SUMS.txt" in assets:
        sums = os.path.join(d, "SHA256SUMS.txt")
        fetch(assets["SHA256SUMS.txt"], sums)
        want = {ln.split()[1].lstrip("*"): ln.split()[0].lower()
                for ln in open(sums, encoding="utf-8").read().splitlines() if len(ln.split()) >= 2}
        have = hashlib.sha256(open(dest, "rb").read()).hexdigest()
        if want.get(pick) != have:
            os.remove(dest)
            raise RuntimeError(f"{pick} does not match the release's SHA256SUMS.txt: removed, nothing installed")
    return dest


def run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=RUN_TIMEOUT_S)
    if r.returncode != 0:
        raise RuntimeError(((r.stderr or r.stdout).strip().splitlines() or ["failed"])[-1][:200])
    return r.stdout


def needs(t):
    """install what winget can; say what only its maker offers"""
    notes = []
    for n in t.get("needs", []):
        if n.startswith("winget:"):
            wid = n[len("winget:"):]
            listed = subprocess.run(["winget", "list", "--id", wid, "-e"], capture_output=True, text=True)
            if wid.lower() not in (listed.stdout or "").lower():
                run(["winget", "install", "--id", wid, "-e", "--accept-package-agreements",
                     "--accept-source-agreements", "--silent"])
                notes.append(f"installed {wid}")
        else:
            notes.append(f"needs {n}")
    return notes


def clone(name, repo):
    d = os.path.join(root(), name, "src")
    if os.path.isdir(os.path.join(d, ".git")):
        run(["git", "-C", d, "pull", "-q", "--ff-only"])
    else:
        os.makedirs(os.path.dirname(d), exist_ok=True)
        run(["git", "clone", "-q", "--depth", "1", f"{GH}{repo}.git", d])
    return d, run(["git", "-C", d, "rev-parse", "--short", "HEAD"]).strip()


def get(name):
    t = TOOLS[name]
    notes = needs(t)
    kind = t["kind"]
    if kind == "link":
        mark(name, "link only")
        return [f"{t['label']}: {GH}{t['repo']} ({t.get('after', '')})"] + notes
    if kind in ("setup", "zip"):
        rel = latest(t["repo"])
        if not rel:
            raise RuntimeError("could not read its newest release from GitHub")
        f = checked_download(name, rel, t["asset"])
        if kind == "setup":
            subprocess.Popen([f])          # the maker's installer: it shows its own steps (and may ask for admin)
            notes.append("its installer is open: click through it")
        else:
            out = os.path.join(root(), name, rel["tag_name"])
            with zipfile.ZipFile(f) as z:
                z.extractall(out)
            notes.append(f"unpacked to {out}")
        mark(name, rel["tag_name"])
    else:
        d, head = clone(name, t["repo"])
        if kind == "mcp":
            venv = os.path.join(d, ".venv")
            if not os.path.isdir(venv):
                run([sys.executable, "-m", "venv", venv])
            py = os.path.join(venv, "Scripts", "python.exe") if os.name == "nt" else os.path.join(venv, "bin", "python")
            run([py, "-m", "pip", "install", "-q", "-e", d])
            exe = os.path.join(os.path.dirname(py), t["exe"] + (".exe" if os.name == "nt" else ""))
            listed = subprocess.run(["claude", "mcp", "list"], capture_output=True, text=True, timeout=RUN_TIMEOUT_S)
            if f"{t['mcp']}:" not in (listed.stdout or ""):
                run(["claude", "mcp", "add", "--scope", "user", t["mcp"], "--", exe])
                notes.append(f"connector '{t['mcp']}' added: it works after Claude Code restarts")
        mark(name, "git " + head)
    if t.get("after"):
        notes.append(t["after"])
    return [f"{t['label']}: got ({got(name)})"] + notes


def newer():
    out = []
    for name, t in TOOLS.items():
        have = got(name)
        if not have or t["kind"] not in ("setup", "zip"):
            continue
        rel = latest(t["repo"])
        if rel and rel.get("tag_name") and rel["tag_name"] != have:
            out.append(f"{t['label']}: {have} -> {rel['tag_name']} ({GH}{t['repo']}/releases)")
    return out


def rows():
    return [{"name": n, "label": t["label"], "maker": t["maker"], "link": GH + t["repo"], "what": t["what"],
             "on": is_on(n), "got": got(n)} for n, t in TOOLS.items()]


def main(a):
    cmd = a[0] if a else "list"
    if cmd == "list":
        r = rows()
        if "--json" in a:
            print(json.dumps(r, indent=1))
        else:
            for x in r:
                print(f"{x['name']:17} {'ON ' if x['on'] else 'off'}  {x['got'] or '-':18} {x['label']} by "
                      f"{x['maker']}: {x['link']}")
        return 0
    if cmd == "get" and len(a) > 1:
        names = [n for n in TOOLS if is_on(n)] if a[1] == "on" else [a[1]]
        bad = 0
        for n in names:
            if n not in TOOLS:
                print(f"no outside tool called {n}; known: {', '.join(TOOLS)}")
                return 2
            try:
                print("\n  ".join(get(n)))
            except Exception as e:
                print(f"{TOOLS[n]['label']}: NOT got: {e}")
                bad += 1
        return 1 if bad else 0
    if cmd == "newer":
        n = newer()
        print("\n".join(n) or "every outside tool here is the newest")
        return 1 if n else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):   # a character the console cannot show prints as ? (0.94.2)
        try:
            _stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))
