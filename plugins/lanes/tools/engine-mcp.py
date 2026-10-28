#!/usr/bin/env python3
"""engine-mcp.py - the two "look inside the running game" MCP servers (0.82.0, 2026-10-23, asked for by the
maintainer: "please bake these features into Lanes").

    python engine-mcp.py status [--json]          what is installed, registered, and whether a newer one is out
    python engine-mcp.py install re               RE Engine MCP (praydog): clone or update, build, register
    python engine-mcp.py install uevr             UEVR-MCP (elliotttate): newest release, register
    python engine-mcp.py game re <game folder> [--check | --remove]
    python engine-mcp.py game uevr <game .exe> [--check | --remove | --dumper]

Exit 0 = done or nothing to do, 1 = could not (the reason is printed), 2 = not applicable here.

WHAT THEY ARE
  re   https://github.com/praydog/re-engine-mcp (MIT). A C# plugin for REFramework inside any RE Engine game
       (Resident Evil 2/3/4/7/Village and more) serves the game's live objects on localhost:8899; the MCP server
       hands them to Claude: every type, singleton, field and method, read and write, call any method, walk the
       object graph, hot-reload C# test plugins and read their compile errors. Needs a NIGHTLY REFramework plus
       its csharp-api.zip in the game, and the .NET 10 SDK on the PC.
  uevr https://github.com/elliotttate/uevr-mcp. A UEVR plugin inside any Unreal Engine 4.22 to 5.5 game, also on
       localhost:8899: every UObject, live Lua, HMD and controller poses, GPU screenshots, function hooks, a
       ProcessEvent listener, object snapshots and diffs, USMAP and buildable-project dumps. Its server is one
       self-contained program; some of its verbs (ps-resolve, ps-symbols) read the game's .exe with nothing running.
  Both listen on the same port, so only one game with either plugin runs at a time.

TWO HALVES, AND WHO MAY DO EACH
  `install` is PC-wide (no game is touched): /lanes:setup and /lanes:gu run it. `game` puts the small game-side
  part into ONE game (the C# plugin into <game>/reframework/plugins/source, or uevr_mcp.dll into
  %APPDATA%\\UnrealVRMod\\<exe name>\\plugins) and takes it out again with --remove; only that game's own session
  (/lm, /ms) runs it, never /pd, /gr, /sr, /gs or setup. What `game` copied is listed in the state dir
  (engine-mcp-games.json), so --remove takes out exactly those files and nothing else. --dumper also writes UEVR's
  dumper_mode file, which turns UEVR's VR drawing OFF for that game: for dumping only, removed with --remove.

Tests set LANES_ENGINEMCP_HOME (stands in for %LOCALAPPDATA%\\Programs), LANES_UEVR_APPDATA (for %APPDATA%),
LANES_CLAUDE_JSON (for ~/.claude.json), LANES_STATE_DIR, and LANES_ENGINEMCP_OFFLINE=1 (no network, no claude CLI).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

HOME = os.path.expanduser("~")
LOCALAPPDATA = os.environ.get("LOCALAPPDATA", os.path.join(HOME, "AppData", "Local"))
APPS = os.environ.get("LANES_ENGINEMCP_HOME") or os.path.join(LOCALAPPDATA, "Programs")
APPDATA = os.environ.get("LANES_UEVR_APPDATA") or os.environ.get("APPDATA", os.path.join(HOME, "AppData", "Roaming"))
CLAUDE_JSON = os.environ.get("LANES_CLAUDE_JSON") or os.path.join(HOME, ".claude.json")
STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(HOME, ".claude", "lanes")
GAMES_FILE = os.path.join(STATE_DIR, "engine-mcp-games.json")
OFFLINE = os.environ.get("LANES_ENGINEMCP_OFFLINE") == "1"
NET_TIMEOUT_S = 60
BUILD_TIMEOUT_S = 900
MARKER = "lanes-release.txt"
API_PORT_URL = "http://localhost:8899"

SERVERS = {
    "re": {"title": "RE Engine MCP", "repo": "praydog/re-engine-mcp", "mcp_name": "reframework",
           "folder": "re-engine-mcp"},
    "uevr": {"title": "UEVR-MCP", "repo": "elliotttate/uevr-mcp", "mcp_name": "uevr", "folder": "uevr-mcp"},
}
RE_PLUGIN_SRC = os.path.join("reframework", "plugins", "source")
RE_CSHARP_MARK = os.path.join("reframework", "plugins", "REFramework.NET.dll")
RE_DLL = os.path.join("mcp-server", "bin", "Release", "net10.0", "McpServer.dll")
UEVR_EXE = os.path.join("bin", "UevrMcpServer.exe")
UEVR_PLUGIN = os.path.join("bin", "uevr_mcp.dll")


def say(msg):
    print(msg)


def app_dir(kind):
    return os.path.join(APPS, SERVERS[kind]["folder"])


def run(cmd, cwd=None, timeout=NET_TIMEOUT_S):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)


def read_marker(kind):
    try:
        with open(os.path.join(app_dir(kind), MARKER), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def write_marker(kind, text):
    with open(os.path.join(app_dir(kind), MARKER), "w", encoding="utf-8") as f:
        f.write(text + "\n")


def registered(kind):
    """The user-scope entry Claude Code holds for this server, or None."""
    try:
        with open(CLAUDE_JSON, encoding="utf-8") as f:
            return (json.load(f).get("mcpServers") or {}).get(SERVERS[kind]["mcp_name"])
    except (OSError, ValueError):
        return None


def register(kind, command, env=None):
    name = SERVERS[kind]["mcp_name"]
    if OFFLINE:
        return True, "offline: registration skipped"
    run(["claude", "mcp", "remove", "-s", "user", name])          # a stale path from an older install goes first
    cmd = ["claude", "mcp", "add", "-t", "stdio", "-s", "user", name]
    for k, v in (env or {}).items():
        cmd += ["-e", f"{k}={v}"]
    rc, out = run(cmd + ["--"] + command)
    return rc == 0, out.strip()


def dotnet10():
    rc, out = run(["dotnet", "--list-sdks"])
    return rc == 0 and any(line.startswith("10.") for line in out.splitlines())


def gh_json(url):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "lanes-plugin"})
    with urllib.request.urlopen(req, timeout=NET_TIMEOUT_S) as r:
        return json.load(r)


def latest_of(kind):
    """Newest upstream version: a release tag (uevr) or the main branch's commit (re). '' when unknown."""
    if OFFLINE:
        return ""
    try:
        if kind == "uevr":
            return gh_json(f"https://api.github.com/repos/{SERVERS[kind]['repo']}/releases/latest").get("tag_name", "")
        rc, out = run(["git", "ls-remote", f"https://github.com/{SERVERS[kind]['repo']}", "HEAD"])
        return out.split()[0][:12] if rc == 0 and out.strip() else ""
    except Exception:
        return ""


def installed(kind):
    d = app_dir(kind)
    return os.path.isfile(os.path.join(d, RE_DLL if kind == "re" else UEVR_EXE))


# ---------------------------------------------------------------- status

def status(as_json):
    rows = {}
    for kind, s in SERVERS.items():
        have, latest = read_marker(kind), latest_of(kind)
        rows[kind] = {"title": s["title"], "installed": installed(kind), "version": have or None,
                      "latest": latest or None, "newer": bool(latest and have and latest != have),
                      "registered": registered(kind) is not None, "folder": app_dir(kind)}
    rows["re"]["dotnet10_sdk"] = OFFLINE or dotnet10()
    rows["games"] = load_games()
    if as_json:
        print(json.dumps(rows, indent=1))
        return 0
    for kind in SERVERS:
        r = rows[kind]
        if not r["installed"]:
            line = f"{r['title']}: not installed."
        else:
            line = f"{r['title']}: installed ({r['version'] or 'version unknown'})"
            line += "; a newer one is out: " + r["latest"] + "." if r["newer"] else ", up to date."
        line += "" if r["registered"] else " Not registered with Claude Code."
        say(line)
    if not rows["re"]["dotnet10_sdk"]:
        say("RE Engine MCP needs the .NET 10 SDK, which this PC does not have yet.")
    for game, g in rows["games"].items():
        say(f"In a game: {g['kind']} plugin in {game} ({len(g['files'])} files"
            + (", dumper mode ON" if g.get("dumper") else "") + ").")
    return 0


# ---------------------------------------------------------------- install (PC-wide)

def install_re():
    d = app_dir("re")
    if not OFFLINE and not dotnet10():
        say("RE Engine MCP needs the .NET 10 SDK first. Install it with (needs admin; Windows asks to approve):\n"
            "  winget install --id Microsoft.DotNet.SDK.10 -e\nthen run this again.")
        return 1
    if os.path.isdir(os.path.join(d, ".git")):
        rc, out = run(["git", "-C", d, "pull", "--ff-only", "-q"])
    else:
        os.makedirs(APPS, exist_ok=True)
        rc, out = run(["git", "clone", "-q", "--depth", "1", f"https://github.com/{SERVERS['re']['repo']}", d])
    if rc != 0:
        say(f"Could not fetch RE Engine MCP: {out.strip()}")
        return 1
    if not OFFLINE:
        rc, out = run(["dotnet", "build", "-c", "Release", "mcp-server"], cwd=d, timeout=BUILD_TIMEOUT_S)
        if rc != 0:
            say("The MCP server did not build:\n" + "\n".join(out.strip().splitlines()[-15:]))
            return 1
    rc, head = run(["git", "-C", d, "rev-parse", "HEAD"])
    write_marker("re", head.strip()[:12] if rc == 0 else "")
    ok, out = register("re", ["dotnet", os.path.join(d, RE_DLL)], {"REFRAMEWORK_API_URL": API_PORT_URL})
    if not ok:
        say(f"Built, but Claude Code did not take the registration: {out}")
        return 1
    say(f"RE Engine MCP installed in {d} and registered as '{SERVERS['re']['mcp_name']}'. "
        "It takes effect from the next restart of Claude Code. Each game also needs its plugin (engine-mcp.py game re).")
    return 0


def server_running(exe_name):
    rc, out = run(["tasklist", "/FI", f"IMAGENAME eq {exe_name}"])
    return rc == 0 and exe_name.lower() in out.lower()


def install_uevr():
    if sys.platform != "win32" and not OFFLINE:
        say("UEVR-MCP is a Windows program; nothing to do here.")
        return 2
    d = app_dir("uevr")
    if not OFFLINE and server_running(os.path.basename(UEVR_EXE)):
        say("UEVR-MCP is running (a session is using it). Close Claude Code's other sessions, then run this again.")
        return 1
    try:
        rel = gh_json(f"https://api.github.com/repos/{SERVERS['uevr']['repo']}/releases/latest")
    except Exception as e:
        say(f"Could not reach GitHub: {e}")
        return 1
    zips = [a for a in rel.get("assets", []) if a.get("name", "").lower().endswith(".zip")]
    if not zips:
        say(f"The newest release ({rel.get('tag_name', '?')}) has no zip to install.")
        return 1
    work = tempfile.mkdtemp(prefix="uevr-mcp-")
    try:
        zpath = os.path.join(work, "release.zip")
        urllib.request.urlretrieve(zips[0]["browser_download_url"], zpath)
        with zipfile.ZipFile(zpath) as z:
            bad = [n for n in z.namelist() if n.startswith(("/", "\\")) or ".." in n.replace("\\", "/").split("/")]
            if bad:
                say(f"The zip holds paths outside its own folder ({bad[0]}); not installed.")
                return 1
            z.extractall(os.path.join(work, "x"))
        src = os.path.join(work, "x")
        if not os.path.isfile(os.path.join(src, UEVR_EXE)):
            say("The release zip does not hold bin\\UevrMcpServer.exe; not installed.")
            return 1
        if os.path.isdir(d):
            shutil.rmtree(d)
        shutil.copytree(src, d)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    write_marker("uevr", rel.get("tag_name", ""))
    ok, out = register("uevr", [os.path.join(d, UEVR_EXE)])
    if not ok:
        say(f"Installed, but Claude Code did not take the registration: {out}")
        return 1
    say(f"UEVR-MCP {rel.get('tag_name', '')} installed in {d} and registered as 'uevr'. It takes effect from the next "
        "restart of Claude Code. Each game also needs its plugin (engine-mcp.py game uevr).")
    return 0


# ---------------------------------------------------------------- game (one game, its own session only)

def load_games():
    try:
        with open(GAMES_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_games(games):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(GAMES_FILE, "w", encoding="utf-8") as f:
        json.dump(games, f, indent=1)


def game_re(game_dir, mode):
    game_dir = os.path.abspath(game_dir)
    key = os.path.normcase(game_dir)
    if not os.path.isdir(os.path.join(game_dir, "reframework")):
        say(f"No REFramework in {game_dir}: install a NIGHTLY REFramework into the game first.")
        return 1
    has_cs = os.path.isfile(os.path.join(game_dir, RE_CSHARP_MARK))
    games = load_games()
    if mode == "check":
        held = key in games
        say(f"REFramework: present. C# support (csharp-api.zip): {'present' if has_cs else 'MISSING'}. "
            f"RE Engine MCP plugin: {'in the game' if held else 'not in the game'}.")
        return 0
    if mode == "remove":
        return remove_listed(games, key)
    if not has_cs:
        say("This REFramework has no C# support. Unzip csharp-api.zip from the same nightly release "
            "(https://github.com/praydog/REFramework-nightly/releases) into the game folder, then run this again.")
        return 1
    src = os.path.join(app_dir("re"), RE_PLUGIN_SRC)
    if not os.path.isdir(src):
        say("RE Engine MCP is not installed on this PC yet: run engine-mcp.py install re first.")
        return 1
    dest = os.path.join(game_dir, RE_PLUGIN_SRC)
    files = copy_tree(src, dest)
    games[key] = {"kind": "re", "path": game_dir, "files": files}
    save_games(games)
    say(f"RE Engine MCP plugin put into the game ({len(files)} files). REFramework compiles it at the next launch; "
        f"its log then says '[WebAPI] Listening on {API_PORT_URL}/'.")
    return 0


def copy_tree(src, dest):
    files = []
    for root, _, names in os.walk(src):
        for n in names:
            s = os.path.join(root, n)
            t = os.path.join(dest, os.path.relpath(s, src))
            os.makedirs(os.path.dirname(t), exist_ok=True)
            shutil.copy2(s, t)
            files.append(t)
    return sorted(files)


def game_uevr(exe, mode, dumper):
    stem = os.path.splitext(os.path.basename(exe))[0]
    if not re.fullmatch(r"[\w .()-]+", stem or ""):
        say(f"'{exe}' does not look like a game program.")
        return 1
    key = os.path.normcase(os.path.abspath(exe))
    plugdir = os.path.join(APPDATA, "UnrealVRMod", stem, "plugins")
    games = load_games()
    if mode == "check":
        say(f"UEVR profile for {stem}: {'present' if os.path.isdir(os.path.dirname(plugdir)) else 'none yet'}. "
            f"UEVR-MCP plugin: {'in place' if key in games else 'not in place'}.")
        return 0
    if mode == "remove":
        return remove_listed(games, key)
    src = os.path.join(app_dir("uevr"), UEVR_PLUGIN)
    if not os.path.isfile(src):
        say("UEVR-MCP is not installed on this PC yet: run engine-mcp.py install uevr first.")
        return 1
    os.makedirs(plugdir, exist_ok=True)
    files = [os.path.join(plugdir, "uevr_mcp.dll")]
    shutil.copy2(src, files[0])
    if dumper:
        files.append(os.path.join(os.path.dirname(plugdir), "dumper_mode"))
        open(files[-1], "w").close()
    games[key] = {"kind": "uevr", "path": exe, "files": files, "dumper": dumper}
    save_games(games)
    say(f"UEVR-MCP plugin put in UEVR's profile for {stem}. It starts when UEVR is injected into the game."
        + (" DUMPER MODE is on: UEVR draws no VR for this game until --remove." if dumper else ""))
    return 0


def remove_listed(games, key):
    g = games.pop(key, None)
    if not g:
        say("Nothing of ours is listed for that game; nothing removed.")
        return 0
    gone = 0
    for f in g["files"]:
        try:
            os.remove(f)
            gone += 1
        except OSError:
            pass
    for f in g["files"]:                     # tidy the folders we made, deepest first, only when empty
        d = os.path.dirname(f)
        while d and os.path.isdir(d) and not os.listdir(d) and os.path.basename(d) not in ("source", "plugins"):
            os.rmdir(d)
            d = os.path.dirname(d)
    save_games(games)
    say(f"Taken out of the game: {gone} files (the master copy stays installed on this PC).")
    return 0


def main(argv):
    a = argv[1:]
    if not a or a[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0 if a else 2
    if a[0] == "status":
        return status("--json" in a)
    if a[0] == "install" and len(a) > 1 and a[1] in SERVERS:
        return install_re() if a[1] == "re" else install_uevr()
    if a[0] == "game" and len(a) > 2 and a[1] in SERVERS:
        mode = "check" if "--check" in a else "remove" if "--remove" in a else "add"
        if a[1] == "re":
            return game_re(a[2], mode)
        return game_uevr(a[2], mode, "--dumper" in a)
    print(__doc__)
    return 2


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):   # a character the console cannot show prints as ? (0.94.2)
        try:
            _stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv))
