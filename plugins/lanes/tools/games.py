#!/usr/bin/env python3
"""games.py - which of the projects' apps (games) are on this PC, and has anything about them changed (0.95.0).

The maintainer, 2026-10-28: "the state of what games are installed on the pc and what are not, for that you do need an
overview of all the game folders and see if they match what is on github and vice versa, and Lanes must know if
something has changed in the beginning of a session, so a quick check to see if game locations and files still match
must be done in the beginning of a session."

    python games.py check              session start: silent unless something changed since this PC's record
    python games.py overview [--json]  every project: on this PC or not, where, which build; and the other PCs' records
    python games.py record [--push]    write this PC's record (commit and push only that file with --push)
    python games.py set <project> steam <appid> [title]     which game a project is about (shared by every PC)
    python games.py set <project> folder [title]            a game no store knows: each PC names its folder with
                                                            game_dir.<project> = <folder> in lanes.conf
    python games.py set <project> none                      a project with no game of its own (a tool, a library)
    python games.py scan [--json]      every game the stores on this PC know about (Steam, GOG, Epic), with no project
Tests set LANES_CONFIG and LANES_STEAM_ROOTS (a fake Steam folder; GOG and Epic are then left out).

WHAT IS CHECKED AT SESSION START (all read from the PC, no network, well under a second)
  - GAME UPDATED: a store updated a game since the record (Steam's build number changed). A mod that patches the game
    by address can stop working after an update, so this is said before anything is tested.
  - GAME CHANGED: a game no store manages (game_dir) has a different main program than when it was recorded.
  - GAME GONE / GAME MOVED / GAME FOUND: the folder is not there any more, is somewhere else, or a project's game turned
    up on this PC that the record did not have.
  - NEW PROJECT: a project folder in the live root that games.tsv does not name yet: say which game it is about.
  - GONE PROJECT: games.tsv names a project that no longer has a folder (deleted or renamed on GitHub).
  Each line ends with the command that brings the record level. Our own mod files are checked elsewhere (builds.py
  check for projects with a builds folder); this one is about the games themselves.

WHERE THINGS ARE (lanes.conf)
  games_record = <folder in a private repo clone>   holds games.tsv (which game each project is about, one file for
                                                    every PC) and <PC name>-games.tsv (what this PC had last time)
  game_dir.<project> = <folder>                     a game no store knows, on this PC
  game_exe.<project> = <program, relative to it>    its main program (else the biggest .exe in its top two levels)
  Not set: the tool says so and does nothing. A home-folder path is written as ~ in the record, never the login.

WHY APP IDS AND NOT NAMES
  The first version of this check (in the maintainer's own notes repo) matched project names against Steam's names and
  called classic DOOM + DOOM II "DOOM (2016)": installed, while the real game was not on the PC. The record agreed with
  itself, so the session-start check was silent about a wrong answer. A store's own id cannot be mistaken.
"""
import glob
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lanes_common import utf8_console  # noqa: E402

HOME = os.path.expanduser("~")
CONF = os.environ.get("LANES_CONFIG") or os.path.join(HOME, ".claude", "lanes.conf")
MAP_FILE = "games.tsv"
STEAM_SEEDS = [r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam", r"C:\Steam", r"D:\Steam",
               r"D:\Program Files (x86)\Steam", r"C:\SteamLibrary", r"D:\SteamLibrary", r"E:\SteamLibrary"]
EPIC_MANIFESTS = r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests"
STEAM_FULLY_INSTALLED = 4          # StateFlags bit: Steam has every file of the game
PROJECT_MARKERS = ("engine-research", "dev-archive", "modding-notes")   # a folder layout only game projects have
RECORD_COLS = ("project", "store", "id", "title", "where", "build", "fingerprint")


# ------------------------------------------------------------------ settings and files

def conf():
    out = {}
    try:
        with open(CONF, encoding="utf-8") as f:
            for line in f:
                m = re.match(r"^\s*([A-Za-z_][\w.\-]*)\s*=\s*(.*?)\s*(?:\s#.*)?$", line)
                if m and not line.lstrip().startswith("#"):
                    out[m.group(1)] = m.group(2).strip().strip('"')
    except OSError:
        pass
    return out


def pc_name(c):
    return c.get("machine_name") or "this-pc"


def live_root(c):
    board = c.get("board", "")
    if board and os.path.isdir(board):
        return os.path.dirname(os.path.abspath(board))
    rec = c.get("games_record", "")
    # the record folder sits inside a clone; that clone's parent is a root of clones
    d = os.path.abspath(rec) if rec else ""
    while d and os.path.dirname(d) != d:
        if os.path.isdir(os.path.join(d, ".git")):
            return os.path.dirname(d)
        d = os.path.dirname(d)
    return ""


def read_tsv(path):
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\r\n")
                if line and not line.startswith("#"):
                    rows.append(line.split("\t"))
    except OSError:
        pass
    return rows


def read_map(rec_dir):
    """{project: (store, id, title)} from games.tsv."""
    return {r[0]: (r[1] if len(r) > 1 else "none", r[2] if len(r) > 2 else "", r[3] if len(r) > 3 else "")
            for r in read_tsv(os.path.join(rec_dir, MAP_FILE)) if r and r[0]}


def write_map(rec_dir, m):
    lines = ["# Which game each project is about. One file for every PC; each PC records what it has in <PC>-games.tsv.",
             "# store: steam (id = Steam app id), gog, epic (id = the store's own id), folder (each PC sets",
             "# game_dir.<project> in lanes.conf), none (a project with no game of its own). Written by games.py set.",
             "# project\tstore\tid\ttitle"]
    lines += ["\t".join((p,) + tuple(m[p])) for p in sorted(m)]
    with open(os.path.join(rec_dir, MAP_FILE), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def tilde(path):
    """A path as the record keeps it: the home folder as ~, so no login name is ever written down."""
    if path and os.path.normcase(path).startswith(os.path.normcase(HOME)):
        return "~" + path[len(HOME):]
    return path


# ------------------------------------------------------------------ what the stores know

def steam_roots():
    if os.environ.get("LANES_STEAM_ROOTS"):          # tests: these roots only, no registry, no usual places
        return os.environ["LANES_STEAM_ROOTS"].split(os.pathsep)
    roots = []
    try:
        import winreg
        for hive, key in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                          (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
            try:
                with winreg.OpenKey(hive, key) as k:
                    for v in ("SteamPath", "InstallPath"):
                        try:
                            roots.append(os.path.normpath(winreg.QueryValueEx(k, v)[0]))
                        except OSError:
                            pass
            except OSError:
                pass
    except ImportError:
        roots += [os.path.join(HOME, ".steam", "steam"), os.path.join(HOME, ".local", "share", "Steam")]
    return roots + STEAM_SEEDS


def steam_libraries():
    """Every steamapps folder Steam knows about (libraryfolders.vdf), plus the usual places."""
    seen, out = set(), []

    def add(d):
        k = os.path.normcase(os.path.abspath(d))
        if k not in seen and os.path.isdir(d):
            seen.add(k)
            out.append(d)

    for root in steam_roots():
        apps = os.path.join(root, "steamapps")
        add(apps)
        for vdf in (os.path.join(apps, "libraryfolders.vdf"), os.path.join(root, "config", "libraryfolders.vdf")):
            try:
                text = open(vdf, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            for m in re.finditer(r'"path"\s+"([^"]+)"', text):
                add(os.path.join(m.group(1).replace("\\\\", "\\"), "steamapps"))
    return out


def acf_value(text, key):
    m = re.search(r'"%s"\s+"([^"]*)"' % re.escape(key), text, re.I)
    return m.group(1) if m else ""


def steam_games():
    """{appid: {...}} for every Steam app manifest on this PC."""
    games = {}
    for lib in steam_libraries():
        for f in glob.glob(os.path.join(lib, "appmanifest_*.acf")):
            try:
                t = open(f, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            appid = acf_value(t, "appid")
            flags = acf_value(t, "StateFlags")
            folder = os.path.join(lib, "common", acf_value(t, "installdir"))
            if not appid:
                continue
            installed = flags.isdigit() and int(flags) & STEAM_FULLY_INSTALLED and os.path.isdir(folder)
            games[appid] = {"store": "steam", "id": appid, "title": acf_value(t, "name"), "where": folder,
                            "build": acf_value(t, "buildid"), "installed": bool(installed)}
    return games


def gog_games():
    games = {}
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\GOG.com\Games") as k:
            i = 0
            while True:
                try:
                    gid = winreg.EnumKey(k, i)
                except OSError:
                    break
                i += 1
                try:
                    with winreg.OpenKey(k, gid) as g:
                        path = reg_value(winreg, g, "path")
                        games[gid] = {"store": "gog", "id": gid, "title": reg_value(winreg, g, "gameName") or gid,
                                      "where": path, "build": reg_value(winreg, g, "ver"),
                                      "installed": bool(path) and os.path.isdir(path)}
                except OSError:
                    continue
    except (ImportError, OSError):
        pass
    return games


def reg_value(winreg, key, name):
    try:
        return str(winreg.QueryValueEx(key, name)[0])
    except OSError:
        return ""


def epic_games():
    games = {}
    for f in glob.glob(os.path.join(EPIC_MANIFESTS, "*.item")):
        try:
            d = json.load(open(f, encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            continue
        aid, path = d.get("AppName", ""), d.get("InstallLocation", "")
        if aid:
            games[aid] = {"store": "epic", "id": aid, "title": d.get("DisplayName", aid), "where": path,
                          "build": d.get("AppVersionString", ""), "installed": os.path.isdir(path)}
    return games


def store_games():
    if os.environ.get("LANES_STEAM_ROOTS"):          # tests: the fake Steam only
        return {"steam": steam_games(), "gog": {}, "epic": {}}
    return {"steam": steam_games(), "gog": gog_games(), "epic": epic_games()}


def fingerprint(folder, exe=""):
    """The game's main program as name:size:modified - enough to see that it was replaced or updated, without
    reading gigabytes. `exe` (game_exe.<project> in lanes.conf, relative to the folder) names it; otherwise the
    biggest .exe in the folder's top two levels is taken."""
    if exe:
        try:
            st = os.stat(os.path.join(folder, exe))
            return "%s:%d:%d" % (exe.replace("\\", "/"), st.st_size, int(st.st_mtime))
        except OSError:
            return "missing " + exe.replace("\\", "/")
    best = None
    for pattern in ("*.exe", os.path.join("*", "*.exe")):
        for f in glob.glob(os.path.join(folder, pattern)):
            try:
                st = os.stat(f)
            except OSError:
                continue
            if best is None or st.st_size > best[1]:
                best = (os.path.relpath(f, folder).replace("\\", "/"), st.st_size, int(st.st_mtime))
    return "%s:%d:%d" % best if best else ""


# ------------------------------------------------------------------ projects

def project_folders(root, board=""):
    """Project folders in the live root: a clone with a game project's layout (engine-research/, dev-archive/ or
    modding-notes/ at its top), or one the board keeps a status file for (status/<repo>.md)."""
    out = []
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return out
    for n in names:
        p = os.path.join(root, n)
        if not os.path.isdir(os.path.join(p, ".git")):
            continue
        if any(os.path.isdir(os.path.join(p, m)) for m in PROJECT_MARKERS) or \
                (board and os.path.isfile(os.path.join(board, "status", n + ".md"))):
            out.append(n)
    return out


def same_place(a, b):
    """Two folders are the same place whatever the letter case or slashes (Steam reports its own folder in lower
    case from the registry and in its own case from a library list)."""
    return os.path.normcase(os.path.normpath(a or "")) == os.path.normcase(os.path.normpath(b or ""))


def now_state(c, mapping, stores=None):
    """{project: row dict} for every project games.tsv names: where its game is on this PC right now."""
    stores = stores if stores is not None else store_games()
    out = {}
    for proj, (store, gid, title) in mapping.items():
        row = {"project": proj, "store": store, "id": gid, "title": title, "where": "", "build": "", "fingerprint": ""}
        if store in stores:
            g = stores[store].get(gid)
            if g and g["installed"]:
                row.update(where=g["where"], build=g["build"], title=title or g["title"])
        elif store == "folder":
            d = os.path.expanduser(c.get("game_dir." + proj, ""))
            if d and os.path.isdir(d):
                row.update(where=d, fingerprint=fingerprint(d, c.get("game_exe." + proj, "")))
        if store == "none":
            row["where"] = "-"
        elif not row["where"]:
            row["where"] = "NOT ON THIS PC"
        out[proj] = row
    return out


def record_path(c):
    return os.path.join(c["games_record"], "%s-games.tsv" % pc_name(c))


def read_record(c):
    rows = {}
    for r in read_tsv(record_path(c)):
        d = dict(zip(RECORD_COLS, r + [""] * (len(RECORD_COLS) - len(r))))
        d["where"] = os.path.expanduser(d["where"]) if d["where"].startswith("~") else d["where"]
        rows[d["project"]] = d
    return rows


def write_record(c, state):
    lines = ["# The games of every project on %s, as games.py record found them. where: the folder, '-' for a" % pc_name(c),
             "# project with no game, NOT ON THIS PC when it is missing. build: the store's build number.",
             "# fingerprint: the main program of a game no store manages (name:size:modified).",
             "# " + "\t".join(RECORD_COLS)]
    for p in sorted(state):
        r = state[p]
        lines.append("\t".join([r["project"], r["store"], r["id"], r["title"], tilde(r["where"]), r["build"],
                                r["fingerprint"]]))
    with open(record_path(c), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


# ------------------------------------------------------------------ commands

def settings_or_none():
    c = conf()
    rec = c.get("games_record", "")
    if not rec or not os.path.isdir(rec):
        return None
    return c


def differences(c, mapping, state, record):
    msgs = []
    for p in sorted(state):
        now, was = state[p], record.get(p)
        name = now["title"] or p
        if was is None:
            if now["where"] not in ("-", "NOT ON THIS PC"):
                msgs.append("GAME FOUND: %s (%s) is on this PC now, at %s; the record did not have it." % (name, p, tilde(now["where"])))
            continue
        if same_place(now["where"], was["where"]):
            if now["build"] and was["build"] and now["build"] != was["build"]:
                msgs.append("GAME UPDATED: %s (%s) - the store updated it since the record (build %s -> %s). A mod that "
                            "patches the game may need a fix; test before trusting it." % (name, p, was["build"], now["build"]))
            elif now["fingerprint"] and was["fingerprint"] and now["fingerprint"] != was["fingerprint"]:
                msgs.append("GAME CHANGED: %s (%s) - its main program is not the one recorded (%s -> %s)."
                            % (name, p, was["fingerprint"].split(":")[0], now["fingerprint"].split(":")[0]))
        elif now["where"] == "NOT ON THIS PC":
            msgs.append("GAME GONE: %s (%s) was at %s, and is not on this PC any more." % (name, p, tilde(was["where"])))
        elif was["where"] in ("NOT ON THIS PC", "-", ""):
            msgs.append("GAME FOUND: %s (%s) is on this PC now, at %s." % (name, p, tilde(now["where"])))
        else:
            msgs.append("GAME MOVED: %s (%s) from %s to %s." % (name, p, tilde(was["where"]), tilde(now["where"])))
    root = live_root(c)
    if root:
        folders = set(project_folders(root, c.get("board", "")))
        for p in sorted(folders - set(mapping)):
            msgs.append("NEW PROJECT: %s has no game set yet - say which game it is about: games.py set %s steam <appid>"
                        " (or folder / none)." % (p, p))
        for p in sorted(set(mapping) - folders):
            if mapping[p][0] != "none" and not os.path.isdir(os.path.join(root, p)):
                msgs.append("GONE PROJECT: %s is in games.tsv but has no folder in the live root (deleted or renamed on "
                            "GitHub?)." % p)
    return msgs


def cmd_check():
    c = settings_or_none()
    if c is None:
        return 0
    mapping = read_map(c["games_record"])
    if not mapping:
        print("GAMES CHECK (lanes): games.tsv is empty - nothing to compare. games.py set <project> ... names each "
              "project's game, then games.py record --push.")
        return 0
    if not os.path.isfile(record_path(c)):
        print("GAMES CHECK (lanes): this PC (%s) has no games record yet: run games.py record --push." % pc_name(c))
        return 0
    msgs = differences(c, mapping, now_state(c, mapping), read_record(c))
    if msgs:
        print("GAMES CHECK (lanes, this PC: %s) - tell the person in plain words:" % pc_name(c))
        for m in msgs:
            print("  " + m)
        print("  When the change is understood, bring the record level: games.py record --push")
    return 0


def other_records(c):
    out = {}
    for f in sorted(glob.glob(os.path.join(c["games_record"], "*-games.tsv"))):
        pc = os.path.basename(f)[:-len("-games.tsv")]
        if pc != pc_name(c):
            out[pc] = {r[0]: (r[4] if len(r) > 4 else "") for r in read_tsv(f)}
    return out


def cmd_overview(as_json):
    c = settings_or_none()
    if c is None:
        print("games_record is not set in lanes.conf (a folder in a private repo clone): nothing to show.")
        return 2
    mapping = read_map(c["games_record"])
    state = now_state(c, mapping)
    others = other_records(c)
    root = live_root(c)
    unmapped = sorted(set(project_folders(root, c.get("board", ""))) - set(mapping)) if root else []
    if as_json:
        print(json.dumps({"pc": pc_name(c), "projects": state, "other_pcs": others, "no_game_set": unmapped}, indent=1))
        return 0
    head = "%-28s %-34s %-12s %s" % ("PROJECT", "GAME", pc_name(c), " | ".join(others) or "")
    print(head)
    print("-" * len(head))
    have = 0
    for p in sorted(state, key=lambda x: (state[x]["store"] == "none", x)):
        r = state[p]
        here = "yes" if r["where"] not in ("NOT ON THIS PC", "-") else ("-" if r["where"] == "-" else "NO")
        have += here == "yes"
        other = " | ".join(("yes" if (o.get(p, "") not in ("", "NOT ON THIS PC", "-")) else
                            ("-" if o.get(p) == "-" else ("NO" if p in o else "?"))) for o in others.values())
        print("%-28s %-34s %-12s %s" % (p[:28], (r["title"] or "")[:34], here, other))
    games = sum(1 for r in state.values() if r["store"] != "none")
    print("\n%d of %d project games are on this PC." % (have, games))
    if unmapped:
        print("No game set yet (games.py set ...): " + ", ".join(unmapped))
    return 0


def cmd_record(push):
    c = settings_or_none()
    if c is None:
        print("games_record is not set in lanes.conf: nowhere to write the record.")
        return 2
    mapping = read_map(c["games_record"])
    write_record(c, now_state(c, mapping))
    print("recorded: %s" % os.path.basename(record_path(c)))
    if push:
        return push_files(c["games_record"], [record_path(c)], "games: %s's record" % pc_name(c))
    return 0


def push_files(folder, paths, message):
    """Commit only these files in the repo that holds them, pull --rebase, push."""
    def g(*a):
        return subprocess.run(["git", "-C", folder] + list(a), capture_output=True, text=True)
    g("add", "--", *paths)
    if not g("diff", "--cached", "--quiet", "--", *paths).returncode:
        print("nothing changed, nothing to push")
        return 0
    r = g("commit", "-m", message, "--", *paths)
    if r.returncode:
        print("commit refused:\n" + r.stdout + r.stderr)
        return 1
    g("pull", "--rebase", "-q")
    r = g("push", "-q")
    print("pushed" if r.returncode == 0 else "push failed:\n" + r.stderr)
    return r.returncode


def cmd_set(argv):
    c = settings_or_none()
    if c is None or len(argv) < 2 or argv[1] not in ("steam", "gog", "epic", "folder", "none"):
        print(__doc__)
        return 2
    proj, store = argv[0], argv[1]
    gid = argv[2] if store in ("steam", "gog", "epic") and len(argv) > 2 else ""
    if store in ("steam", "gog", "epic") and not gid:
        print("give the store's id: games.py set %s %s <id> [title]" % (proj, store))
        return 2
    title = " ".join(argv[3:] if gid else argv[2:])
    if not title and gid:
        title = store_games()[store].get(gid, {}).get("title", "")
    m = read_map(c["games_record"])
    m[proj] = (store, gid, title)
    write_map(c["games_record"], m)
    print("%s -> %s %s %s" % (proj, store, gid, title))
    return 0


def cmd_scan(as_json):
    stores = store_games()
    if as_json:
        print(json.dumps(stores, indent=1))
        return 0
    for store, games in stores.items():
        for gid, g in sorted(games.items(), key=lambda x: x[1]["title"].lower()):
            print("%-6s %-12s %-50s %s" % (store, gid, g["title"][:50], tilde(g["where"]) if g["installed"] else "(not fully installed)"))
    return 0


def main(argv):
    utf8_console()
    if not argv:
        print(__doc__)
        return 2
    c = argv[0]
    if c == "check":
        return cmd_check()
    if c == "overview":
        return cmd_overview("--json" in argv)
    if c == "record":
        return cmd_record("--push" in argv)
    if c == "set":
        return cmd_set(argv[1:])
    if c == "scan":
        return cmd_scan("--json" in argv)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
