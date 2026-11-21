#!/usr/bin/env python3
"""spacecheck.py - what is sitting on this PC's drives taking space (0.116.0, 2026-11-15, extra `spacecheck`).

Asked for by the maintainer, 2026-11-15, for the weekly full scan: "a scan of the whole pc files that are just sitting
there taking space". It LOOKS ONLY: nothing is deleted, moved or changed, ever. The person decides; a session removes
something only on the person's word, one item at a time.

    python spacecheck.py scan [--minutes N] [--root <folder> ...] [--json]
                                   walk every fixed drive (or only the folders given), then print a short summary in
                                   plain words and write the full list to this PC's Lanes folder (never GitHub: it
                                   names folders). Exit 0 = done, 1 = cut off by the time limit, 2 = could not run
    python spacecheck.py show      print the last summary again

WHAT IT LOOKS FOR, in three groups:
  safe to clear      the Recycle Bin, temporary files older than a week, caches that rebuild themselves
  probably safe      old downloads (installers and archives in a Downloads folder, untouched for 60 days), old crash
                     dumps, very big log files, Windows Update's leftover downloads
  yours to decide    big files untouched for half a year, the same big file kept twice, folders untouched for a year,
                     old videos

WHAT IT NEVER SUGGESTS. Programs (Program Files: uninstall, never delete), Windows itself, game libraries (any
steamapps folder), every saved build and every project copy (the folders lanes.conf names: builds, root, transfer,
recordings, any folder holding a .git), this tool's own state, and every folder named in `spacecheck_keep =`
(lanes.conf, separated by ";": a full path, or a bare folder name that matches that name anywhere). Those folders are
not even walked.

Settings are named below; tests shrink every size with SPACECHECK_TEST_SMALL=1 (megabytes become kilobytes).
"""
import ctypes
import hashlib
import json
import os
import re
import string
import sys
import time

HOME = os.path.expanduser("~")
CONF = os.environ.get("LANES_CONFIG") or os.path.join(HOME, ".claude", "lanes.conf")
STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(HOME, ".claude", "lanes")
OUT_DIR = os.path.join(STATE_DIR, "spacecheck")

# ---- settings (named numbers, one place) --------------------------------------------------------
MINUTES_DEFAULT = 30          # the walk stops after this, says so, and reports what it saw
TEMP_DAYS = 7                 # temporary files older than this are safe to clear
DOWNLOAD_DAYS = 60            # an installer or archive in Downloads untouched this long is an old download
DUMP_DAYS = 30                # a crash dump older than this has been read (Gold Digger shelves what it needs)
BIG_OLD_DAYS = 180            # a big file untouched this long
OLD_FOLDER_DAYS = 365         # a folder whose newest file is older than this
VIDEO_DAYS = 90
MB = 1024 * 1024
SIZES_MB = {"big_file": 1024, "dup_file": 200, "old_folder": 5 * 1024, "big_log": 100, "video": 500,
            "show_min": 50}   # show_min: smaller items are counted in the totals but not listed one by one
DUP_HASH_BUDGET_GB = 60       # at most this much is read to confirm copies; the rest is reported as "same size"
QUICK_HASH_MB = 4             # first and last part read before a full read
OLD_FOLDER_DEPTH = 3          # folders this deep below a drive (or a root given) are judged as a whole
TOP_SHOWN = 5                 # items named per group in the summary
INSTALLER_EXT = {".exe", ".msi", ".msix", ".zip", ".7z", ".rar", ".iso", ".img", ".tar", ".gz", ".xz"}
VIDEO_EXT = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"}
DUMP_EXT = {".dmp", ".hdmp", ".mdmp"}
SKIP_NAMES = {"system volume information", "$windows.~bt", "$windows.~ws", "$sysreset", "recovery",
              "program files", "program files (x86)", "windowsapps", "steamapps", "$recycle.bin", ".git"}
SYSTEM_FILES = {"pagefile.sys", "hiberfil.sys", "swapfile.sys"}

GROUPS = (("safe", "safe to clear"), ("probably", "probably safe"), ("yours", "yours to decide"))
KINDS = {  # kind: (group, plain name)
    "recycle": ("safe", "the Recycle Bin"),
    "temp": ("safe", "temporary files older than a week"),
    "cache": ("safe", "caches that rebuild themselves"),
    "download": ("probably", "old downloads (installers and archives)"),
    "dump": ("probably", "old crash dumps"),
    "log": ("probably", "very big log files"),
    "winupdate": ("probably", "Windows Update's leftover downloads (Disk Clean-up removes them)"),
    "big_old": ("yours", "big files untouched for half a year"),
    "duplicate": ("yours", "the same big file kept twice"),
    "old_folder": ("yours", "folders untouched for a year"),
    "video": ("yours", "old videos"),
}

if os.environ.get("SPACECHECK_TEST_SMALL"):
    MB = 1024
    QUICK_HASH_MB = 1


def conf():
    out = {}
    try:
        with open(CONF, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                if "=" in line:
                    k, v = line.split("=", 1)
                    out.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except OSError:
        pass
    return out


def norm(p):
    return os.path.normcase(os.path.normpath(os.path.expandvars(os.path.expanduser(p))))


def keep_rules(c):
    """(full folders, bare folder names) never walked and never suggested"""
    full, names = set(), set()
    for key in ("builds", "root", "transfer", "recordings", "parcel_root", "ideas", "board"):
        if c.get(key):
            full.add(norm(c[key]))
    for key, v in c.items():                       # every lane root and per-project app folder named there
        if key.startswith("builds_app.") or key == "lane_roots":
            for part in re.split(r"[;,]", v):
                if part.strip():
                    full.add(norm(part.strip()))
    full.add(norm(os.path.join(HOME, ".claude")))
    full.add(norm(STATE_DIR))
    windir = os.environ.get("WINDIR", r"C:\Windows")
    full.add(norm(windir))
    for part in c.get("spacecheck_keep", "").split(";"):
        part = part.strip()
        if not part:
            continue
        if any(sep in part for sep in ("/", "\\", ":")):
            full.add(norm(part))
        else:
            names.add(part.lower())
    return full, names


def fixed_drives():
    if os.name != "nt":
        return ["/"]
    out = []
    mask = ctypes.windll.kernel32.GetLogicalDrives()
    for i, letter in enumerate(string.ascii_uppercase):
        if mask & (1 << i):
            root = letter + ":\\"
            if ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(root)) == 3:   # DRIVE_FIXED
                out.append(root)
    return out


def drive_space(root):
    if os.name != "nt":
        st = os.statvfs(root)
        return st.f_bavail * st.f_frsize, st.f_blocks * st.f_frsize
    free, total = ctypes.c_ulonglong(0), ctypes.c_ulonglong(0)
    ctypes.windll.kernel32.GetDiskFreeSpaceExW(ctypes.c_wchar_p(root), None, ctypes.byref(total), ctypes.byref(free))
    return free.value, total.value


def is_link(entry):
    try:
        if entry.is_symlink():
            return True
        st = entry.stat(follow_symlinks=False)
        return bool(getattr(st, "st_file_attributes", 0) & 0x400)            # a junction (reparse point)
    except OSError:
        return True


class Walk:
    def __init__(self, keep_full, keep_names, deadline, now):
        self.keep_full, self.keep_names, self.deadline, self.now = keep_full, keep_names, deadline, now
        self.items = []                 # (kind, path, bytes, age_days)
        self.by_size = {}               # size -> [path] for files big enough to be copies
        self.cut_off = False
        self.files = 0
        self.kept_seen = 0

    def kept(self, path, name):
        n = norm(path)
        if n in self.keep_full or name.lower() in self.keep_names or name.lower() in SKIP_NAMES:
            return True
        return False

    def age(self, mtime):
        return max(0, int((self.now - mtime) / 86400))

    def add(self, kind, path, size, mtime):
        self.items.append((kind, path, size, self.age(mtime)))

    def tree(self, top, depth=0, context=""):
        """walk a folder; returns (bytes, newest mtime). Judges files on the way, folders at OLD_FOLDER_DEPTH."""
        if time.time() >= self.deadline:
            self.cut_off = True
            return 0, 0
        total, newest = 0, 0
        try:
            entries = list(os.scandir(top))
        except OSError:
            return 0, 0
        if any(e.name == ".git" for e in entries):              # a project copy: its own history keeps it
            self.kept_seen += 1
            return 0, 0
        for e in entries:
            if is_link(e):
                continue
            try:
                if e.is_dir(follow_symlinks=False):
                    if self.kept(e.path, e.name):
                        self.kept_seen += 1
                        continue
                    sub = context or self.context_of(e)
                    size, new = self.tree(e.path, depth + 1, sub)
                    total += size
                    newest = max(newest, new)
                    if depth + 1 <= OLD_FOLDER_DEPTH and size >= SIZES_MB["old_folder"] * MB and new \
                            and self.age(new) >= OLD_FOLDER_DAYS and not sub:
                        self.add("old_folder", e.path, size, new)
                    continue
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            self.files += 1
            size, mtime = st.st_size, st.st_mtime
            total += size
            newest = max(newest, mtime)
            self.judge_file(e.name, e.path, size, mtime, context, depth)
        return total, newest

    def context_of(self, entry):
        """a folder whose files are judged by where they are: a Downloads folder. (Windows' own temp folders are
        counted as a whole by special_places; another program's folder that happens to be called temp is not.)"""
        return "downloads" if entry.name.lower() == "downloads" else ""

    def judge_file(self, name, path, size, mtime, context, depth):
        low = name.lower()
        ext = os.path.splitext(low)[1]
        age = self.age(mtime)
        if depth == 0 and low in SYSTEM_FILES:
            return
        if context == "temp":
            if age >= TEMP_DAYS:
                self.add("temp", path, size, mtime)
            return
        if context == "downloads" and ext in INSTALLER_EXT and age >= DOWNLOAD_DAYS:
            self.add("download", path, size, mtime)
            return
        if ext in DUMP_EXT and age >= DUMP_DAYS:
            self.add("dump", path, size, mtime)
            return
        if ext == ".log" and size >= SIZES_MB["big_log"] * MB:
            self.add("log", path, size, mtime)
            return
        if ext in VIDEO_EXT and size >= SIZES_MB["video"] * MB and age >= VIDEO_DAYS:
            self.add("video", path, size, mtime)
        elif size >= SIZES_MB["big_file"] * MB and age >= BIG_OLD_DAYS:
            self.add("big_old", path, size, mtime)
        if size >= SIZES_MB["dup_file"] * MB:
            self.by_size.setdefault(size, []).append(path)

    def whole(self, kind, top, min_age_days=0):
        """a folder counted as one item (a cache, the Recycle Bin): its size, files older than min_age_days only"""
        total, newest = 0, 0
        stack = [top]
        while stack:
            if time.time() >= self.deadline:
                self.cut_off = True
                break
            d = stack.pop()
            try:
                entries = list(os.scandir(d))
            except OSError:
                continue
            for e in entries:
                if is_link(e):
                    continue
                try:
                    if e.is_dir(follow_symlinks=False):
                        stack.append(e.path)
                        continue
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                if self.age(st.st_mtime) >= min_age_days:
                    total += st.st_size
                    newest = max(newest, st.st_mtime)
        if total:
            self.items.append((kind, top, total, self.age(newest) if newest else 0))


def quick_hash(path, size, full=False):
    h = hashlib.sha256()
    part = QUICK_HASH_MB * MB
    with open(path, "rb") as f:
        if full or size <= 2 * part:
            for block in iter(lambda: f.read(MB), b""):
                h.update(block)
        else:
            h.update(f.read(part))
            f.seek(size - part)
            h.update(f.read(part))
    return h.hexdigest()


def find_copies(w):
    budget = DUP_HASH_BUDGET_GB * 1024 * MB
    for size in sorted(w.by_size, reverse=True):
        paths = w.by_size[size]
        if len(paths) < 2:
            continue
        groups = {}
        for p in paths:
            try:
                groups.setdefault(quick_hash(p, size), []).append(p)
            except OSError:
                continue
        for same in groups.values():
            if len(same) < 2:
                continue
            if budget >= size * len(same):
                budget -= size * len(same)
                full = {}
                for p in same:
                    try:
                        full.setdefault(quick_hash(p, size, full=True), []).append(p)
                    except OSError:
                        continue
                sets = [s for s in full.values() if len(s) > 1]
            else:
                sets = [same]
            for s in sets:
                s.sort(key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0)
                for extra in s[1:]:                       # the oldest copy is "the one", the rest are extras
                    try:
                        mtime = os.path.getmtime(extra)
                    except OSError:
                        mtime = w.now
                    w.items.append(("duplicate", extra, size, w.age(mtime), s[0]))


def special_places(w):
    """the known places counted as a whole: the Recycle Bin, temp folders, caches, Windows Update's downloads"""
    local = os.environ.get("LOCALAPPDATA", os.path.join(HOME, "AppData", "Local"))
    roaming = os.environ.get("APPDATA", os.path.join(HOME, "AppData", "Roaming"))
    windir = os.environ.get("WINDIR", r"C:\Windows")
    temps = {norm(p): p for p in (os.environ.get("TEMP", ""), os.path.join(local, "Temp"), os.path.join(windir, "Temp"))
             if p and os.path.isdir(p)}
    for p in temps.values():
        w.whole("temp", p, TEMP_DAYS)
    caches = [os.path.join(local, "pip", "Cache"), os.path.join(local, "npm-cache"), os.path.join(roaming, "npm-cache"),
              os.path.join(local, "NVIDIA", "DXCache"), os.path.join(local, "NVIDIA", "GLCache"),
              os.path.join(local, "D3DSCache"), os.path.join(local, "AMD", "DxCache"),
              os.path.join(local, "Microsoft", "Windows", "INetCache"), os.path.join(HOME, ".cargo", "registry", "cache"),
              os.path.join(local, "CrashDumps")]
    for p in caches:
        if os.path.isdir(p):
            w.whole("dump" if p.endswith("CrashDumps") else "cache", p, DUMP_DAYS if p.endswith("CrashDumps") else 0)
    sd = os.path.join(windir, "SoftwareDistribution", "Download")
    if os.path.isdir(sd):
        w.whole("winupdate", sd, 14)
    return set(temps)


def scan(roots, minutes):
    c = conf()
    keep_full, keep_names = keep_rules(c)
    now = time.time()
    w = Walk(keep_full, keep_names, now + minutes * 60, now)
    drives = []
    if not roots:
        temps = special_places(w)
        w.keep_full |= temps                       # counted already as a whole
        for d in fixed_drives():
            free, total = drive_space(d)
            drives.append({"drive": d.rstrip("\\"), "free": free, "total": total})
            rb = os.path.join(d, "$Recycle.Bin")
            if os.path.isdir(rb):
                w.whole("recycle", rb)
        roots = fixed_drives()
    for r in roots:
        if w.cut_off:
            break
        w.tree(r)
    if not w.cut_off:
        find_copies(w)
    return w, drives


def summarise(w, drives, last):
    totals = {g: 0 for g, _ in GROUPS}
    per_kind = {}
    counted = set()
    for it in sorted(w.items, key=lambda i: i[0] != "duplicate"):   # a big old copy counts once, as a copy
        kind, size = it[0], it[2]
        if norm(it[1]) in counted:
            continue
        counted.add(norm(it[1]))
        totals[KINDS[kind][0]] += size
        per_kind[kind] = per_kind.get(kind, 0) + size
    return totals, per_kind


def gb(n):
    return "%.1f GB" % (n / (1024.0 ** 3)) if n >= 1024 ** 3 else "%d MB" % max(1, round(n / (1024.0 ** 2)))


def plain_name(path):
    """the item without its folder: a drive letter and the file or folder name (the summary is read on screen)"""
    drive = os.path.splitdrive(path)[0]
    return ("%s %s" % (drive, os.path.basename(path.rstrip("\\/")))).strip()


def write_report(w, drives, totals, per_kind, minutes_used):
    os.makedirs(OUT_DIR, exist_ok=True)
    day = time.strftime("%Y-%m-%d")
    md = os.path.join(OUT_DIR, "%s.md" % day)
    lines = ["# Space check, %s" % time.strftime("%Y-%m-%d %H:%M"), "",
             "Looked only: nothing was deleted or changed. %d files looked at in %.0f minute(s)%s." % (
                 w.files, minutes_used, ", CUT OFF by the time limit" if w.cut_off else ""), ""]
    for d in drives:
        lines.append("- %s %s free of %s" % (d["drive"], gb(d["free"]), gb(d["total"])))
    for g, label in GROUPS:
        lines += ["", "## %s: %s" % (label.capitalize(), gb(totals[g])), ""]
        for kind, (kg, kname) in KINDS.items():
            if kg != g or kind not in per_kind:
                continue
            lines.append("### %s: %s" % (kname, gb(per_kind[kind])))
            for it in sorted((i for i in w.items if i[0] == kind), key=lambda i: -i[2]):
                if it[2] < SIZES_MB["show_min"] * MB and kind not in ("recycle", "temp", "cache", "winupdate"):
                    continue
                twin = " (the same as %s)" % it[4] if len(it) > 4 else ""
                lines.append("- %s, %s, untouched %d days: `%s`%s" % (gb(it[2]), kind, it[3], it[1], twin))
            lines.append("")
    with open(md, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    data = {"when": time.strftime("%Y-%m-%d %H:%M"), "totals": totals, "per_kind": per_kind, "drives": drives,
            "cut_off": w.cut_off, "report": md}
    with open(os.path.join(OUT_DIR, "last.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    return md


def summary_text(w, drives, totals, per_kind, last, md):
    out = ["SPACE CHECK (looked only, nothing deleted)%s" % (": CUT OFF by the time limit, the rest next week"
                                                        if w.cut_off else "")]
    if drives:
        out.append("  drives: " + ", ".join("%s %s free of %s" % (d["drive"], gb(d["free"]), gb(d["total"]))
                                           for d in drives))
    for g, label in GROUPS:
        if not totals[g]:
            continue
        grew = ""
        if last and last.get("totals", {}).get(g) is not None:
            diff = totals[g] - last["totals"][g]
            if abs(diff) >= 1024 ** 3:
                grew = " (%s %s since %s)" % ("up" if diff > 0 else "down", gb(abs(diff)), last.get("when", "")[:10])
        parts = ["%s %s" % (KINDS[k][1], gb(per_kind[k])) for k in KINDS if KINDS[k][0] == g and k in per_kind]
        out.append("  %s: %s%s - %s" % (label, gb(totals[g]), grew, "; ".join(parts)))
        top = sorted((i for i in w.items if KINDS[i[0]][0] == g), key=lambda i: -i[2])[:TOP_SHOWN]
        for it in top:
            out.append("      %s  %s, untouched %d days" % (gb(it[2]).rjust(8), plain_name(it[1]), it[3]))
    if not any(totals.values()):
        out.append("  nothing worth clearing was found.")
    out.append("report: %s" % md)
    return "\n".join(out)


def main(argv):
    verb = argv[0] if argv else ""
    if verb == "show":
        last = _read_last()
        if not last:
            print("spacecheck: no check has run on this PC yet")
            return 1
        print(open(last["report"], encoding="utf-8").read() if os.path.isfile(last.get("report", "")) else last)
        return 0
    if verb != "scan":
        print(__doc__)
        return 2
    minutes = MINUTES_DEFAULT
    roots = []
    as_json = "--json" in argv
    i = 1
    while i < len(argv):
        if argv[i] == "--minutes" and i + 1 < len(argv):
            minutes = float(argv[i + 1])
            i += 1
        elif argv[i] == "--root" and i + 1 < len(argv):
            roots.append(argv[i + 1])
            i += 1
        i += 1
    last = _read_last()
    started = time.time()
    w, drives = scan(roots, minutes)
    totals, per_kind = summarise(w, drives, last)
    md = write_report(w, drives, totals, per_kind, (time.time() - started) / 60)
    if as_json:
        print(json.dumps({"totals": totals, "per_kind": per_kind, "cut_off": w.cut_off, "report": md,
                          "items": [list(it) for it in w.items]}, indent=1))
    else:
        print(summary_text(w, drives, totals, per_kind, last, md))
    return 1 if w.cut_off else 0


def _read_last():
    try:
        with open(os.path.join(OUT_DIR, "last.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
