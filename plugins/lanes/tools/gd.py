#!/usr/bin/env python3
"""gd.py - Gold Digger: shelve what every run leaves behind, and help /lanes:gd sift it (0.88.0, 2026-10-26).

Asked for by the maintainer, 2026-10-24: "can you maybe save this info and logs and all of that on the pc and then we
create a slash command so that you go through all this info and filter out things we actually need?"; and 2026-10-26:
"categorizin and "shelving" all the collected data after each run, without deleting any of it or even analizing any of
it, just puttin it in categories of camera work, guns, jitter data, first person stuff, enemies in game, menus ... we
need to save all the collected data in the MEGA transfer folder so both pc's can access it freely."

    python gd.py where                          the Gold Digger folder (lanes.conf `gold_digger =`, else
                                                <transfer>/Gold Digger, else ~/Lanes Gold Digger)
    python gd.py sources <game>                 where this PC finds that game's logs (one list per PC)
    python gd.py sources <game> add <glob> [<shelf>]   add a place: a file, a folder or a pattern; ~ allowed
    python gd.py shelve <game> [--quiet]        copy everything new from the game's places, and its new BeG0nE
                                                reports, onto the shelves. Copies only; never deletes, never reads
    python gd.py shelve --all [--quiet]         the same for every game that has places on this PC (the hooks)
    python gd.py add <game> <file|folder>... [--shelf <s>]   shelve these by hand
    python gd.py list [<game>]                  per game and shelf: items, and how many /lanes:gd has not read
    python gd.py unsifted <game> [<shelf>]      the items not read yet, oldest first, with their paths
    python gd.py sifted <game> <id>... | --shelf <s> | --all    mark items read (written per PC, never removed)
    python gd.py fold <file> [--against <older file>]   the file with repeated lines folded into one (count, first
                                                and last line number), warnings and errors marked, and with
                                                --against, only what the older run did not have
    python gd.py digest <game> [<shelf>]        the unread copies, each against EVERY earlier copy of the same kind:
                                                only lines nothing before had (warnings first), the copies that
                                                are only repeats counted and skipped; tables show their bad minutes;
                                                a crash dump shows its crash record (code, module+offset, Steam
                                                already unloaded?), and a rotated log counts as the same log
    python gd.py also <game> <older name>       read the shelves of an older name of this game as part of it
    python gd.py nudge                          one session-start line when the full scan is a week old
    python gd.py fullscan-done                  stamp a /lanes:fullscan run on this PC

THE SHELVES (a first set; a new one is just a new word): camera, jitter, hands, guns, first-person, enemies, menus,
hud, sound, crashes, performance, runs (the always-on collector's card per game launch, lanes-next 2026-11-04), logs
(whole game logs, a bit of everything), other. Each item lands on ONE shelf; when
its name or contents also fit others, the index names those too ("also"), so /lanes:gd reading one shelf finds it.

ON DISK, so both PCs can use it at once through a synced folder:
    <gold digger>/<game>/<shelf>/<YYYY-MM-DD_HH-MM-SS>_<PC>_<name>
    <gold digger>/<game>/INDEX-<PC>.tsv     what this PC shelved (id, when, PC, shelf, also, sha1, bytes, item, from)
    <gold digger>/<game>/SIFTED-<PC>.tsv    what /lanes:gd read on this PC (id, date)
    <gold digger>/<game>/SOURCES-<PC>.txt   this PC's places for that game: "<glob>[<TAB><shelf>]" per line
Every file is written by one PC only, so a sync never has two PCs editing the same file. Nothing here is ever
deleted. A file already shelved (same contents, from either PC) is not copied twice; a file changed in the last two
minutes is left for next time (the game may still be writing it).
State: <state dir>/gd.json (the last full scan on this PC). Tests set LANES_CONFIG, LANES_STATE_DIR, LANES_GD_DIR.
"""
import datetime
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

HOME = os.path.expanduser("~")
STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(HOME, ".claude", "lanes")
STATE_FILE = os.path.join(STATE_DIR, "gd.json")
HERE = os.path.dirname(os.path.abspath(__file__))
NUDGE_DAYS = 7                     # the habit: a full scan once a week
SETTLE_S = 120                     # a file changed more recently than this may still be written by the game
SCAN_BYTES = 8 * 1024 * 1024       # contents are looked at (for "also" shelves) only in text files up to this size
ALSO_HITS = 5                      # a shelf's words must turn up this many times in a file to be named as "also"
MAX_FOLD_LINE = 400                # longer lines are cut in the folded view
INDEX_COLS = ["id", "when", "pc", "shelf", "also", "sha1", "bytes", "item", "from"]

# Shelf words, checked in this order: the first shelf whose words appear in the item's name wins.
SHELVES = [
    ("crashes", ["crash", "dmp", "minidump", "exception", "fault", "wer", "stacktrace"]),
    ("jitter", ["jitter", "jitterlog", "camera-jitter"]),
    ("hands", ["ghost-hand", "hand", "hands", "glove", "controller", "controllers", "grip", "finger"]),
    ("guns", ["gun", "guns", "weapon", "weapons", "scope", "aim", "ammo", "reload", "muzzle", "occlusion-drift",
              "rifle", "pistol", "shotgun"]),
    ("first-person", ["fp", "firstperson", "first-person", "body", "head", "neck"]),
    ("camera", ["camera", "cam", "pose", "projection", "fov", "headrot", "openxr", "xr", "stereo", "eye", "view"]),
    ("enemies", ["enemy", "enemies", "npc", "ai", "boss", "zombie"]),
    ("menus", ["menu", "menus", "route", "routes", "ui", "title", "options", "settings", "pause"]),
    ("hud", ["hud", "crosshair", "overlay", "reticle", "subtitle"]),
    ("sound", ["sound", "audio", "music", "sfx", "fmod", "wwise", "soundxfound"]),
    ("performance", ["perf", "fps", "timing", "frametime", "profile", "gpu", "samples", "events"]),
    ("runs", ["run", "runs", "collector"]),      # the always-on collector's run.json: one card per game launch
    ("logs",["log", "logs", "txt", "framework", "console", "output"]),
]
BEGONE_TOOLS = {"camera-jitter": "jitter", "ghost-hand": "hands", "occlusion-drift": "guns"}
WARN_WORDS = (r"error|errors|fail|failed|failure|fatal|exception|crash|assert|warning|warn|refused|"
              r"denied|timeout|timed out|not found|missing|invalid|abort")
WARN = re.compile(rf"\b({WARN_WORDS})\b", re.I)
# A counter that reads zero ("refused=0", "failed 0", "0 errors") is a clean report, not a warning.
ZERO_COUNT = re.compile(rf"\b(?:{WARN_WORDS})\s*[=:]?\s*0(?![.\d])|(?<![.\d])\b0\s+(?:{WARN_WORDS})\b", re.I)


def looks_like_warning(text):
    return bool(WARN.search(ZERO_COUNT.sub("", text)))

# Bare hex addresses too ("Game Module Addr: 7ff6160b0000"): 6+ hex digits with at least one digit among them, so a
# plain word such as "facade" stays. Without this, --against called 925 lines of a Village log "new" that were only
# addresses moved by the next launch (2026-11-05, dev PC).
NUMBERS = re.compile(r"0x[0-9a-fA-F]+|\b(?=[0-9a-fA-F]*\d)[0-9a-fA-F]{6,}\b|\d+(?:\.\d+)?")


# ---- settings -----------------------------------------------------------------------------------------------------

def conf_files():
    if os.environ.get("LANES_CONFIG"):
        return [os.environ["LANES_CONFIG"]]
    return [os.path.join(HOME, ".claude", "lanes.conf"), os.path.join(HOME, ".config", "lanes", "lanes.conf")]


def conf(key):
    for c in conf_files():
        try:
            for line in open(c, encoding="utf-8"):
                if line.lstrip().startswith("#"):
                    continue
                k, sep, v = line.partition("=")
                v = v.split(" #")[0].strip().strip('"')
                if sep and k.strip() == key and v:
                    return os.path.expandvars(os.path.expanduser(v))
        except OSError:
            pass
    return None


def root():
    if os.environ.get("LANES_GD_DIR"):
        return os.environ["LANES_GD_DIR"]
    own = conf("gold_digger")
    if own:
        return own
    t = conf("transfer")
    return os.path.join(t, "Gold Digger") if t else os.path.join(HOME, "Lanes Gold Digger")


def pc_name():
    v = conf("machine_name")
    if v:
        return re.sub(r"[^A-Za-z0-9._-]", "", v)[:24] or "PC"
    try:
        out = subprocess.run([sys.executable, os.path.join(HERE, "machine-name.py"), "suggest"], capture_output=True,
                             text=True, timeout=20).stdout.strip()
        return re.sub(r"[^A-Za-z0-9._-]", "", out)[:24] or "PC"
    except Exception:
        return "PC"


def safe_game(game):
    g = re.sub(r"[^A-Za-z0-9._-]", "-", game.strip()).strip("-.")
    if not g:
        raise SystemExit("give a game name, for example alice-madness-returns-vr")
    return g


def game_dir(game):
    return os.path.join(root(), safe_game(game))


def now_stamp():
    return datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


# ---- the index ----------------------------------------------------------------------------------------------------

def read_tsv(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [line.rstrip("\n").split("\t") for line in f if line.strip() and not line.startswith("#")]
    except OSError:
        return []


def also_names(game):
    """older shelf names of this game (0.112.0): The Darkness was shelved as `darknessrecomp`, the program's name, until
    2026-11-10, so its run history was split in two. `gd.py also the-darkness-vr darknessrecomp` reads both as one;
    nothing is moved or renamed. One ALSO-<PC>.txt per PC, like every other file here."""
    out = []
    for p in sorted(glob.glob(os.path.join(game_dir(game), "ALSO-*.txt"))):
        for r in read_tsv(p):
            name = safe_game(r[0]) if r and r[0].strip() else ""
            if name and name != safe_game(game) and name not in out:
                out.append(name)
    return out


def index(game):
    """Every item either PC shelved for this game (and under its older names), as dicts, oldest first."""
    rows = []
    for name in [safe_game(game)] + also_names(game):
        for p in glob.glob(os.path.join(root(), name, "INDEX-*.tsv")):
            for r in read_tsv(p):
                if len(r) >= len(INDEX_COLS):
                    row = dict(zip(INDEX_COLS, r))
                    if name != safe_game(game):
                        row["item"] = "../%s/%s" % (name, row["item"])
                    rows.append(row)
    return sorted(rows, key=lambda r: (r["when"], r["id"]))


def sifted_ids(game):
    out = set()
    for name in [safe_game(game)] + also_names(game):
        for p in glob.glob(os.path.join(root(), name, "SIFTED-*.tsv")):
            out.update(r[0] for r in read_tsv(p) if r)
    return out


def cmd_also(game, old):
    if safe_game(old) == safe_game(game):
        print("gd: that is the same name")
        return 1
    if not os.path.isdir(game_dir(old)):
        print(f"gd: no shelves named {safe_game(old)}")
        return 1
    if safe_game(old) in also_names(game):
        print(f"{safe_game(old)} is already read as part of {safe_game(game)}")
        return 0
    append(os.path.join(game_dir(game), f"ALSO-{pc_name()}.txt"), [safe_game(old)])
    print(f"{safe_game(game)} now also reads the shelves named {safe_game(old)} "
          f"({sum(1 for r in index(game) if r['item'].startswith('../'))} item(s)); nothing was moved")
    return 0


def append(path, cols):
    new = not os.path.exists(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        if new and os.path.basename(path).startswith("INDEX-"):
            f.write("# " + "\t".join(INDEX_COLS) + "\n")
        f.write("\t".join(c.replace("\t", " ").replace("\n", " ") for c in cols) + "\n")


def sha1_of(path):
    h = hashlib.sha1()
    if os.path.isdir(path):
        for base, dirs, files in sorted(os.walk(path)):
            dirs.sort()
            for n in sorted(files):
                h.update(n.encode("utf-8"))
                with open(os.path.join(base, n), "rb") as f:
                    for chunk in iter(lambda: f.read(1 << 20), b""):
                        h.update(chunk)
        return h.hexdigest()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def size_of(path):
    if os.path.isdir(path):
        return sum(os.path.getsize(os.path.join(b, n)) for b, _, fs in os.walk(path) for n in fs)
    return os.path.getsize(path)


# ---- choosing a shelf ---------------------------------------------------------------------------------------------

def words(text):
    return set(w for w in re.split(r"[^a-z0-9]+", text.lower()) if w) | set(
        w for w in re.split(r"[^a-z0-9-]+", text.lower()) if "-" in w)


def by_name(name):
    w = words(name)
    return [s for s, keys in SHELVES if w & set(keys)]


def by_contents(path):
    """Shelves whose words turn up often in a text file (for the "also" column)."""
    if os.path.isdir(path) or os.path.getsize(path) > SCAN_BYTES:
        return []
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return []
    if b"\0" in data[:4096]:
        return []
    text = data.decode("utf-8", "replace").lower()
    tokens = re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text)
    counts = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    return [s for s, keys in SHELVES if s != "logs" and sum(counts.get(k, 0) for k in keys) >= ALSO_HITS]


def choose(path, hint=None):
    name = os.path.basename(path.rstrip("/\\"))
    named = by_name(name)
    if hint and re.fullmatch(r"[a-z0-9-]+", hint):   # a place's own shelf, or a new shelf word
        home = hint
    else:
        home = named[0] if named else "other"
    also = []
    for s in named + by_contents(path):
        if s != home and s not in also:
            also.append(s)
    return home, also


# ---- shelving -----------------------------------------------------------------------------------------------------

def shelve_one(game, path, hint, known, pc, origin):
    """Copy one file or folder onto its shelf. Returns the new row, or None when it was there already."""
    digest = sha1_of(path)
    if digest in known:
        return None
    shelf, also = choose(path, hint)
    when = now_stamp()
    name = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(path.rstrip("/\\")))[:80] or "item"
    rel = f"{shelf}/{when}_{pc}_{name}"
    dest = os.path.join(game_dir(game), rel)
    n = 1
    while os.path.exists(dest):
        n += 1
        rel = f"{shelf}/{when}_{pc}_{n}_{name}"
        dest = os.path.join(game_dir(game), rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.isdir(path):
        shutil.copytree(path, dest)
    else:
        shutil.copy2(path, dest)
    row = [f"{pc}-{when}-{digest[:6]}", when, pc, shelf, ",".join(also), digest, str(size_of(dest)), rel, origin]
    append(os.path.join(game_dir(game), f"INDEX-{pc}.tsv"), row)
    known.add(digest)
    return dict(zip(INDEX_COLS, row))


def tidy_origin(path):
    p = os.path.abspath(path).replace("\\", "/")
    h = HOME.replace("\\", "/")
    return "~" + p[len(h):] if p.lower().startswith(h.lower()) else p


def sources(game, pc):
    out = []
    for r in read_tsv(os.path.join(game_dir(game), f"SOURCES-{pc}.txt")):
        if r and r[0].strip():
            out.append((r[0].strip(), (r[1].strip() if len(r) > 1 else "") or None))
    return out


def expand(pattern):
    p = os.path.expandvars(os.path.expanduser(pattern))
    if os.path.isdir(p):
        return [os.path.join(b, n) for b, _, fs in os.walk(p) for n in fs]
    return [x for x in glob.glob(p, recursive=True) if os.path.isfile(x)]


def begone_reports(game):
    """New BeG0nE report folders for this game (report.md and chart only; the raw numbers stay where they are)."""
    home = conf("begone")
    out = []
    if not home:
        return out
    for tool, shelf in BEGONE_TOOLS.items():
        for run in sorted(glob.glob(os.path.join(home, tool, "data", safe_game(game), "*"))):
            if os.path.isfile(os.path.join(run, "report.md")):
                out.append((run, tool, shelf))
    return out


def stage_begone(run, tool):
    """A small folder holding only the report and its chart, named after the tool and the run."""
    tmp = os.path.join(STATE_DIR, "gd-tmp", f"begone-{tool}_{os.path.basename(run)}")
    if os.path.isdir(tmp):
        shutil.rmtree(tmp)
    os.makedirs(tmp)
    for n in ("report.md", "chart.png"):
        if os.path.isfile(os.path.join(run, n)):
            shutil.copy2(os.path.join(run, n), tmp)
    return tmp


def shelve(game, quiet=False):
    pc = pc_name()
    rows = index(game)
    known = {r["sha1"] for r in rows}
    # 2026-11-05: a BeG0nE report reaches both PCs (the reports travel by GitHub), and git can change its line
    # endings on the way, so the same report had other bytes on the other PC and was shelved twice (Hard Reset 17,
    # Psychonauts 5, Manhunt 6, Alice 4). A run already on any PC's index is never shelved again.
    shelved_runs = {r["from"] for r in rows if r["from"].startswith("BeG0nE ")}
    added, skipped_busy = [], 0
    for pattern, hint in sources(game, pc):
        for f in expand(pattern):
            try:
                if time.time() - os.path.getmtime(f) < SETTLE_S:
                    skipped_busy += 1
                    continue
                row = shelve_one(game, f, hint, known, pc, tidy_origin(f))
            except OSError:
                continue
            if row:
                added.append(row)
    state = load_state()
    seen = state.setdefault("begone_seen", {})
    for run, tool, shelf in begone_reports(game):
        key = f"{tool}/{safe_game(game)}/{os.path.basename(run)}"
        if key in seen or f"BeG0nE {tool} {os.path.basename(run)}" in shelved_runs:
            seen.setdefault(key, now_stamp())
            continue
        try:
            staged = stage_begone(run, tool)
            row = shelve_one(game, staged, shelf, known, pc, f"BeG0nE {tool} {os.path.basename(run)}")
            shutil.rmtree(staged, ignore_errors=True)
        except OSError:
            continue
        seen[key] = now_stamp()
        if row:
            added.append(row)
    save_state(state)
    if not quiet or added:
        for r in added:
            print(f"shelved  {safe_game(game)}  {r['shelf']:<12} {r['item']}" + (f"  (also {r['also']})" if r["also"] else ""))
        if skipped_busy:
            print(f"left for next time: {skipped_busy} file(s) changed in the last {SETTLE_S // 60} minutes")
        if not added and not quiet:
            print(f"{safe_game(game)}: nothing new to shelve")
    return added


def all_games():
    try:
        return sorted(n for n in os.listdir(root()) if os.path.isdir(os.path.join(root(), n)))
    except OSError:
        return []


def games_with_places(pc):
    return [g for g in all_games() if sources(g, pc)]


def begone_games():
    home = conf("begone")
    out = set()
    for tool in BEGONE_TOOLS:
        for d in glob.glob(os.path.join(home or "\0", tool, "data", "*")):
            if os.path.isdir(d):
                out.add(os.path.basename(d))
    return out


# ---- reading: fold ------------------------------------------------------------------------------------------------

def shape(line):
    """A line with its numbers blanked, so "frame 1201 took 16.6 ms" and "frame 1202 took 16.9 ms" fold together."""
    return NUMBERS.sub("#", line.strip())


def fold_lines(lines):
    groups, order = {}, []
    for n, line in enumerate(lines, 1):
        s = shape(line)
        if not s:
            continue
        g = groups.get(s)
        if g is None:
            groups[s] = g = {"first": n, "last": n, "count": 0, "text": line.rstrip()[:MAX_FOLD_LINE]}
            order.append(s)
        g["count"] += 1
        g["last"] = n
    return groups, order


def read_lines(path):
    with open(path, "rb") as f:
        return f.read().decode("utf-8", "replace").splitlines()


def item_file(ref):
    """a file path as given; a shelf item's id, or a shelved folder, becomes the file to read (a BeG0nE folder's
    report.md). `fold <id>` used to fail on the id that `unsifted` prints (2026-10-27)."""
    if not os.path.exists(ref):
        for game in sorted(os.listdir(root())) if os.path.isdir(root()) else []:
            for r in index(game):
                if r["id"] == ref:
                    ref = os.path.join(game_dir(game), r["item"])
                    break
            else:
                continue
            break
    if os.path.isdir(ref):
        for name in ("report.md", "README.md"):
            if os.path.isfile(os.path.join(ref, name)):
                return os.path.join(ref, name)
    return ref


# ---- reading: tables ----------------------------------------------------------------------------------------------
# ⚠️ ADDED 2026-11-05 (dev PC, Gold Digger test): `fold` blanks numbers, so a frame-rate recording (one row of numbers a
# second) folded into ONE line and showed nothing; the worst Village stutter of 11-04 sat on the performance shelf
# unseen until it was summed by hand. A table is now read by minute: the run's usual value per column, then only the
# minutes where some column left it, and by how much.
TIME_COLUMNS = ("uptime_s", "t", "seconds", "time_s", "elapsed_s")
TABLE_STEP_S = 60
TABLE_OFF = 0.4          # a minute is worth showing when a column's minute value is 40% off the run's usual
TABLE_MIN_ABS = 1.0      # ... and off by at least this much (so 0 -> 0.4 stutters is not news)


def read_table(lines):
    """(header, rows) when the text is a table of numbers with a time column; else None."""
    body = [ln for ln in lines if ln.strip()]
    if len(body) < 5:
        return None
    sep = "\t" if body[0].count("\t") >= 3 else ("," if body[0].count(",") >= 3 else None)
    if not sep:
        return None
    head = [h.strip().lstrip("#").strip() for h in body[0].split(sep)]
    tcol = next((i for i, h in enumerate(head) if h in TIME_COLUMNS), None)
    if tcol is None:
        return None
    rows = []
    for ln in body[1:]:
        p = ln.split(sep)
        vals = []
        for v in p[:len(head)]:
            try:
                vals.append(float(v))
            except ValueError:
                vals.append(None)
        if len(vals) > tcol and vals[tcol] is not None:
            rows.append(vals)
    return (head, tcol, rows) if len(rows) >= 5 else None


def table_summary(head, tcol, rows):
    def med(v):
        v = sorted(v)
        return v[len(v) // 2] if v else None
    minutes = {}
    for r in rows:
        minutes.setdefault(int(r[tcol] // TABLE_STEP_S), []).append(r)
    cols = [i for i in range(len(head)) if i != tcol and sum(1 for r in rows if i < len(r) and r[i] is not None) >= len(rows) // 2]
    per = {m: {i: med([r[i] for r in rs if i < len(r) and r[i] is not None]) for i in cols} for m, rs in minutes.items()}
    usual = {i: med([per[m][i] for m in per if per[m][i] is not None]) for i in cols}
    print(f"# a table: {len(rows)} rows, {len(minutes)} minute(s), {len(cols)} number column(s); usual = the median minute")
    print("# usual: " + "  ".join(f"{head[i]}={usual[i]:g}" for i in cols if usual[i] is not None))
    shown = 0
    for m in sorted(per):
        off = []
        for i in cols:
            v, u = per[m][i], usual[i]
            if v is None or u is None or abs(v - u) < TABLE_MIN_ABS:
                continue
            if abs(v - u) > TABLE_OFF * max(abs(u), TABLE_MIN_ABS):
                off.append(f"{head[i]} {v:g} (usual {u:g})")
        if off:
            shown += 1
            print(f"! minute {m:3d}: " + "; ".join(off[:8]) + (f"; +{len(off) - 8} more" if len(off) > 8 else ""))
    if not shown:
        print("# every minute stayed near the usual values")
    return 0


def fold(path, against=None):
    path = item_file(path)
    against = item_file(against) if against else against
    if not os.path.isfile(path):
        print(f"gd: no such file or shelf item: {path}")
        return 1
    import gd_dump
    if gd_dump.is_dump(path):
        print(f"# {os.path.basename(path)}: a crash dump")
        print("\n".join(gd_dump.summary(path)))
        return 0
    lines = read_lines(path)
    table = None if against else read_table(lines)
    if table:
        print(f"# {os.path.basename(path)}")
        return table_summary(*table)
    groups, order = fold_lines(lines)
    old = set()
    if against:
        old = set(fold_lines(read_lines(against))[0])
    shown = [s for s in order if s not in old]
    print(f"# {os.path.basename(path)}: {len(lines)} lines, {len(order)} different"
          + (f", {len(shown)} not in {os.path.basename(against)}" if against else ""))
    print("# W = looks like a warning or error;  xN = seen N times (lines first-last)")
    for s in shown:
        g = groups[s]
        mark = "W" if looks_like_warning(g["text"]) else " "
        rep = f"x{g['count']} ({g['first']}-{g['last']})" if g["count"] > 1 else f"   ({g['first']})"
        print(f"{mark} {rep:<20} {g['text']}")
    return 0


# ---- reading: digest ----------------------------------------------------------------------------------------------
# ⚠️ ADDED 2026-11-05 (dev PC, the first full Gold Digger pass): most of what arrives is the same file again (23 of 24
# Village file lists identical; 33 framework logs held 16 new kinds of warning between them). `fold --against` compares
# two files; the digest compares each unread copy against EVERY earlier copy of the same kind, and says plainly which
# copies are only repeats, so a reading session sees just the lines nothing before had.
DIGEST_CAP = 25                      # lines shown per copy; warnings first
STAMP = re.compile(r"^\d{4}-\d\d-\d\d_\d\d-\d\d-\d\d_[^_]+_(?:\d+_)?")   # (n_ = two copies in one second)
INNER_STAMP = re.compile(r"\d{4}-\d\d-\d\d(?:[-_]\d\d-?\d\d(?:-?\d\d)?)?|\d{8}[-_]\d{6}")


def shelved_order(row):
    """oldest first: the shelving second, then the copy's number within that second (2_, 3_ ...). The id cannot break
    a tie: its tail is the contents' hash, so three copies in one second came back in a random order (2026-11-05)."""
    m = re.match(r"^\d{4}-\d\d-\d\d_\d\d-\d\d-\d\d_[^_]+_(\d+)_", os.path.basename(row["item"]))
    return row["when"], int(m.group(1)) if m else 1


ROTATED = re.compile(r"[_.]\d+(?:\.\d+)*(?=\.(?:log|txt|dmp|mdmp)$)|(?<=\.log)\.\d+$", re.I)


def item_kind(item):
    """what kind of file a shelf item is: its name without the shelving stamp and dates, so copies group together.
    0.112.0: numbers that only count (a log's rotation and build number, `darknessrecomp_024.9.log`; a dump's process
    number, `game.exe.15088.dmp`; `x.log.3`) go too: 221 rotated Darkness logs were 221 kinds, never compared."""
    return ROTATED.sub("#", INNER_STAMP.sub("#", STAMP.sub("", os.path.basename(item))))


def new_lines(path, seen):
    """(lines of this copy no earlier copy had, is it a table); `seen` grows. A table's news is its bad minutes."""
    import contextlib
    import io
    import gd_dump
    if gd_dump.is_dump(path):     # 0.112.0: its crash record, never its raw memory; a dump read like a table: in full
        new = []
        for ln in gd_dump.summary(path):
            s = shape(ln)
            if s not in seen:
                seen.add(s)
                new.append(ln.strip())
        return (new if any(ln.startswith("crash") or ln.startswith("not a") for ln in new) else []), True
    try:
        lines = read_lines(path)
    except OSError:
        return [], False
    table = read_table(lines)
    if table:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            table_summary(*table)
        return [ln for ln in buf.getvalue().splitlines() if ln.startswith("!")], True
    new = []
    for ln in lines:
        s = shape(ln)
        if s and s not in seen:
            seen.add(s)
            new.append(ln.strip()[:MAX_FOLD_LINE])
    return new, False


def digest(game, shelf=None, cap=DIGEST_CAP):
    done = sifted_ids(game)
    kinds = {}
    for r in index(game):
        if not shelf or r["shelf"] == shelf or shelf in r["also"].split(","):
            kinds.setdefault(item_kind(r["item"]), []).append(r)
    repeats = 0
    for kind, rows in sorted(kinds.items(), key=lambda kv: -len(kv[1])):
        rows.sort(key=shelved_order)
        if all(r["id"] in done for r in rows):
            continue
        seen, out = set(), []
        for r in rows:
            new, table = new_lines(item_file(os.path.join(game_dir(game), r["item"])), seen)
            if r["id"] not in done:
                out.append((r, new, r is rows[0] and not table))
        adding = [o for o in out if o[1]]
        repeats += len(out) - len(adding)
        print(f"\n## {kind}: {len(rows)} copies, {len(out)} not read; {len(adding)} add something new, "
              f"{len(out) - len(adding)} are only repeats")
        for r, new, first in adding:
            warn = [x for x in new if looks_like_warning(x)]
            if first:
                print(f"  {r['id']}  the first copy ({len(new)} different lines): its warnings only")
                new = warn
            else:
                print(f"  {r['id']}  +{len(new)} new line(s)")
                new = warn + [x for x in new if x not in warn]
            for x in new[:cap]:
                print(("  W " if looks_like_warning(x) else "    ") + x)
            if len(new) > cap:
                print(f"    ... {len(new) - cap} more (gd.py fold {r['id']})")
    print(f"\n# {safe_game(game)}{' / ' + shelf if shelf else ''}: {repeats} unread copies held nothing new; "
          f"mark the whole shelf read when done (gd.py sifted {safe_game(game)} --shelf <shelf>)")
    return 0


# ---- state and nudge ----------------------------------------------------------------------------------------------

def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)


def nudge():
    try:
        last = load_state().get("last_fullscan")
        if last:
            days = (datetime.date.today() - datetime.date.fromisoformat(last)).days
            if days >= NUDGE_DAYS:
                print(f"LANES /fullscan: the full scan last ran {days} days ago on this PC (it includes the weekly tool "
                      f"check). Mention it in one line (the person types /lanes:fullscan, or /fullscan, when it "
                      f"suits); do not run it unasked.")
        else:
            waiting = sum(len([r for r in index(g) if r["id"] not in sifted_ids(g)]) for g in all_games())
            if waiting:
                print(f"LANES /fullscan: the full scan has never run on this PC and {waiting} shelved item(s) wait "
                      f"for Gold Digger. Mention it in one line (/lanes:fullscan, or /fullscan); do not run it unasked.")
    except Exception:
        pass
    return 0


# ---- commands -----------------------------------------------------------------------------------------------------

def cmd_list(game=None):
    games = [safe_game(game)] if game else all_games()
    if not games:
        print(f"nothing shelved yet ({root()})")
        return 0
    for g in games:
        rows, done = index(g), sifted_ids(g)
        if not rows:
            continue
        per = {}
        for r in rows:
            a = per.setdefault(r["shelf"], [0, 0])
            a[0] += 1
            a[1] += r["id"] not in done
        waiting = sum(v[1] for v in per.values())
        print(f"{g}: {len(rows)} item(s), {waiting} not read by Gold Digger")
        for s in sorted(per):
            print(f"   {s:<13} {per[s][0]:>4}   not read: {per[s][1]}")
    return 0


def cmd_unsifted(game, shelf=None):
    done = sifted_ids(game)
    rows = [r for r in index(game) if r["id"] not in done and (not shelf or r["shelf"] == shelf
                                                               or shelf in r["also"].split(","))]
    for r in rows:
        also = f"  also: {r['also']}" if r["also"] else ""
        print(f"{r['id']}  {r['shelf']:<12} {os.path.join(game_dir(game), r['item'])}  [{r['from']}]{also}")
    if not rows:
        print(f"{safe_game(game)}: nothing waiting" + (f" on {shelf}" if shelf else ""))
    return 0


def cmd_sifted(game, args):
    pc, today = pc_name(), datetime.date.today().isoformat()
    done = sifted_ids(game)
    if args and args[0] == "--all":
        ids = [r["id"] for r in index(game)]
    elif args and args[0] == "--shelf" and len(args) > 1:
        ids = [r["id"] for r in index(game) if r["shelf"] == args[1]]
    else:
        ids = args
    marked = 0
    for i in ids:
        if i not in done:
            append(os.path.join(game_dir(game), f"SIFTED-{pc}.tsv"), [i, today])
            marked += 1
    print(f"{safe_game(game)}: {marked} item(s) marked read")
    return 0


def cmd_sources(game, rest):
    pc = pc_name()
    path = os.path.join(game_dir(game), f"SOURCES-{pc}.txt")
    if rest and rest[0] == "add" and len(rest) > 1:
        pattern = rest[1].replace("\\", "/")
        h = HOME.replace("\\", "/")
        if pattern.lower().startswith(h.lower()):
            pattern = "~" + pattern[len(h):]
        append(path, [pattern] + ([rest[2]] if len(rest) > 2 else []))
        print(f"{safe_game(game)}: added {pattern} for {pc}")
    for p, hint in sources(game, pc):
        print(f"{p}" + (f"   -> {hint}" if hint else "") + f"   ({len(expand(p))} file(s) now)")
    if not sources(game, pc):
        print(f"{safe_game(game)}: no places on {pc} yet (gd.py sources {safe_game(game)} add <glob> [shelf])")
    return 0


def _clash_step(job, project="all"):
    """hold this tool's job against a clash (clash.step, 0.103.0)"""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import clash
    except Exception:  # noqa: BLE001
        return
    clash.step(job, project)


def main(argv):
    for stream in (sys.stdout, sys.stderr):
        try:  # a log can hold any character; a Windows console or pipe defaults to cp1252 and would crash on it
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd in ("digest", "sifted"):     # Gold Digger itself, not the shelving every session does, nor the stamp after a run
        _clash_step("gd")
    quiet = "--quiet" in rest
    rest = [a for a in rest if a != "--quiet"]
    if cmd == "where":
        print(root())
        return 0
    if cmd == "shelve":
        if rest and rest[0] == "--all":
            games = sorted(set(games_with_places(pc_name())) | begone_games())
            for g in games:
                try:
                    shelve(g, quiet=True)
                except Exception as e:
                    if not quiet:
                        print(f"{g}: could not shelve ({e})")
            if not quiet:
                print(f"looked at {len(games)} game(s); Gold Digger folder: {root()}")
            return 0
        if rest:
            shelve(rest[0], quiet)
            return 0
    if cmd == "add" and len(rest) >= 2:
        hint = None
        if "--shelf" in rest:
            i = rest.index("--shelf")
            hint = rest[i + 1] if i + 1 < len(rest) else None
            rest = rest[:i] + rest[i + 2:]
        game, pc = rest[0], pc_name()
        known = {r["sha1"] for r in index(game)}
        for p in rest[1:]:
            if not os.path.exists(p):
                print(f"not found: {p}")
                continue
            row = shelve_one(game, p, hint, known, pc, tidy_origin(p))
            print(f"shelved  {r_line(row)}" if row else f"already shelved: {p}")
        return 0
    if cmd == "sources" and rest:
        return cmd_sources(rest[0], rest[1:])
    if cmd == "list":
        return cmd_list(rest[0] if rest else None)
    if cmd == "unsifted" and rest:
        return cmd_unsifted(rest[0], rest[1] if len(rest) > 1 else None)
    if cmd == "sifted" and len(rest) >= 2:
        return cmd_sifted(rest[0], rest[1:])
    if cmd == "fold" and rest:
        against = rest[rest.index("--against") + 1] if "--against" in rest and rest.index("--against") + 1 < len(rest) else None
        return fold(rest[0], against)
    if cmd == "digest" and rest:
        return digest(rest[0], rest[1] if len(rest) > 1 else None)
    if cmd == "also" and len(rest) == 2:
        return cmd_also(rest[0], rest[1])
    if cmd == "nudge":
        return nudge()
    if cmd == "fullscan-done":
        state = load_state()
        state["last_fullscan"] = datetime.date.today().isoformat()
        save_state(state)
        print(f"/fullscan stamped {state['last_fullscan']}")
        return 0
    print(__doc__)
    return 2


def r_line(r):
    return f"{r['shelf']:<12} {r['item']}" + (f"  (also {r['also']})" if r["also"] else "")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
