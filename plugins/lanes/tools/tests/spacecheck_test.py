"""spacecheck_test.py - the space check looks only, finds what sits taking space, and never names a kept folder
(0.116.0, 2026-11-15).

In a temp folder: a pretend drive (sizes shrunk: megabytes become kilobytes), with old downloads, a crash dump, a
big old file, a copy of it, an old video, a project copy, a builds store and a folder kept by name. Exit 0 = pass."""
import json
import os
import subprocess
import sys
import tempfile
import time

T = tempfile.mkdtemp(prefix="spacecheck-")
HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(HERE), "spacecheck.py")
KB = 1024
DAY = 86400
fails = 0


def check(ok, what):
    global fails
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        fails += 1


def p(*parts):
    return os.path.join(T, *parts)


def put(rel, kb, days_old, fill=b"x"):
    full = p("drive", *rel.split("/"))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "wb") as f:
        f.write((fill * 1024)[:1024] * kb)
    t = time.time() - days_old * DAY
    os.utime(full, (t, t))
    return full


put("Users/me/Downloads/old-setup.exe", 80, 200)
put("Users/me/Downloads/new-setup.exe", 80, 3)
put("Users/me/Downloads/notes.txt", 80, 300)                    # not an installer or archive
put("Games/crash/game.dmp", 60, 90)
put("Stuff/huge-old.bin", 1500, 400, b"a")
put("Stuff/copy/huge-old.bin", 1500, 300, b"a")                 # the same file kept twice
put("Stuff/huge-new.bin", 1500, 5, b"b")
put("Videos/trip.mp4", 700, 200, b"v")
put("Logs/app.log", 150, 1)
put("Project/.git/HEAD", 1, 1)
put("Project/big-old-in-a-repo.bin", 2000, 500)                 # a project copy: never walked
put("Builds/b001/mod.dll", 2000, 500)                           # the builds store (lanes.conf): never walked
put("Aethir/data.bin", 2000, 500)                               # kept by name (spacecheck_keep)
put("Archive/a/old1.bin", 3000, 500, b"c")
put("Archive/a/old2.bin", 3000, 500, b"d")
before = sum(len(fs) for _, _, fs in os.walk(p("drive")))

conf = p("lanes.conf")
with open(conf, "w", encoding="utf-8") as f:
    f.write("builds = %s\nspacecheck_keep = Aethir; %s\n" % (p("drive", "Builds"), p("nowhere")))
env = dict(os.environ, LANES_CONFIG=conf, LANES_STATE_DIR=p("state"), SPACECHECK_TEST_SMALL="1")


def run(*args):
    r = subprocess.run([sys.executable, TOOL] + list(args), env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, r.stdout + r.stderr


rc, out = run("scan", "--root", p("drive"), "--json")
check(rc == 0, "the scan runs and finishes (exit 0)")
data = json.loads(out)
items = data["items"]
kinds = {}
for it in items:
    kinds.setdefault(it[0], []).append(os.path.basename(it[1]))
check("old-setup.exe" in kinds.get("download", []), "an old installer in Downloads is an old download")
check("new-setup.exe" not in sum(kinds.values(), []), "a new download is left alone")
check("notes.txt" not in sum(kinds.values(), []), "a document in Downloads is not called a download")
check("game.dmp" in kinds.get("dump", []), "an old crash dump is found")
check("huge-old.bin" in kinds.get("big_old", []), "a big file untouched for half a year is found")
check("huge-new.bin" not in kinds.get("big_old", []), "a big file in use is not")
check(kinds.get("duplicate") == ["huge-old.bin"], "the same big file kept twice is found once, as the extra copy")
dup = [it for it in items if it[0] == "duplicate"][0]
check(dup[1].replace("\\", "/").endswith("Stuff/huge-old.bin") and dup[4].replace("\\", "/").endswith("copy/huge-old.bin")
      or dup[4].replace("\\", "/").endswith("Stuff/huge-old.bin"), "and names the copy it matches")
check("trip.mp4" in kinds.get("video", []), "an old video is listed for the person to decide")
check("app.log" in kinds.get("log", []), "a very big log file is found")
check("Archive" in kinds.get("old_folder", []) or "a" in kinds.get("old_folder", []),
      "a big folder untouched for a year is found")
flat = json.dumps(items)
check("big-old-in-a-repo" not in flat and "Project" not in flat, "a project copy (it has .git) is never named")
check("Builds" not in flat and "mod.dll" not in flat, "the builds store from lanes.conf is never named")
check("Aethir" not in flat, "a folder kept by name (spacecheck_keep) is never named")
after = sum(len(fs) for _, _, fs in os.walk(p("drive")))
check(after == before, "nothing was deleted or moved")
check(os.path.isfile(os.path.join(p("state"), "spacecheck", "last.json")), "the result is kept in this PC's Lanes folder")
check(data["report"].startswith(p("state")), "and the full list too, never next to the files")

rc, out = run("scan", "--root", p("drive"))
summary = out.split("report:")[0]
check("yours to decide" in summary and "probably safe" in summary, "the summary speaks in the three groups")
check(p("drive") not in summary and "\\Stuff\\" not in summary and "/Stuff/" not in summary,
      "the summary names items without their folders (it is read on screen)")
check("report:" in out, "and points at the full list on its own line")
rc, out = run("scan", "--root", p("drive"), "--minutes", "0")
check(rc == 1 and "CUT OFF" in out, "a scan out of time says it was cut off (exit 1)")
rc, out = run("show")
check(rc == 0 and "Space check" in out, "show prints the last full list")

print()
print("spacecheck_test.py: %s" % ("all passed" if not fails else "%d FAILED" % fails))
sys.exit(1 if fails else 0)
