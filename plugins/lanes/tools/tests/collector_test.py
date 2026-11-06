"""collector_test.py - the always-on collector (lanes-next, 2026-11-04) with a pretend game: a small Python program
standing in a pretend game folder, found by the collector, sampled while it runs, and shelved for Gold Digger when it
closes. Nothing of a real game; everything in a temp folder. Exit 0 = pass."""
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(os.path.dirname(HERE))
fails = 0


def check(ok, what):
    global fails
    print(("  ok    " if ok else "FAIL: ") + what)
    fails += not ok


def main():
    try:
        import psutil  # noqa: F401
    except ImportError:
        print("collector: skipped (no psutil on this PC)")
        return 0
    t = tempfile.mkdtemp()
    game_dir = os.path.join(t, "Pretend Game")
    os.makedirs(game_dir)
    shelves = os.path.join(t, "shelves")
    conf = os.path.join(t, "lanes.conf")
    with open(conf, "w", encoding="utf-8") as f:
        f.write(f"machine_name = TESTPC\ngame_dir.pretend-game-vr = {game_dir}\ngame_exe.pretend-game-vr = game.exe\n"
                f"collect_skip = skipped-game\ncollect_unknown = no\n")   # never a real game running beside the test
    os.environ["LANES_CONFIG"] = conf
    os.environ["LANES_GD_DIR"] = shelves
    os.environ["LANES_STATE_DIR"] = os.path.join(t, "state")
    os.environ["LANES_COLLECTOR_DIR"] = os.path.join(t, "staging")
    os.environ["LANES_BEGONE"] = os.path.join(t, "begone-home")
    sys.path.insert(0, os.path.join(PLUGIN, "begone"))
    import collector as C
    C.MIN_RUN_S = 0                      # the pretend game runs seconds, not minutes
    C.DISCOVER_EVERY_S = 0
    C.SAMPLE_EVERY_S = 0
    C._nvsmi = None                      # no nvidia-smi calls: about a second each, which skews the timing below

    # the pretend game: a copy of python standing in the game folder, writing a log while it runs
    exe = os.path.join(game_dir, "game.exe")
    import shutil
    shutil.copy2(sys.executable, exe)
    for n in os.listdir(os.path.dirname(sys.executable)):        # python's dlls beside it, so the copy starts
        if n.lower().endswith((".dll", ".zip")) or n.lower().startswith("python3"):
            try:
                shutil.copy2(os.path.join(os.path.dirname(sys.executable), n), game_dir)
            except OSError:
                pass
    # it also drops a crash dump beside itself before it ends (the way REFramework writes reframework_crash.dmp)
    script = ("import time,sys,os\nopen(sys.argv[1],'a').write('the game started\\n')\n"
              "time.sleep(float(sys.argv[2]))\nopen(sys.argv[1],'a').write('the game ended\\n')\n"
              "open(os.path.join(os.path.dirname(sys.argv[1]),'pretend_crash.dmp'),'wb').write(b'MDMP' + b'0' * 64)\n")
    log = os.path.join(game_dir, "game.log")
    env = dict(os.environ, PYTHONHOME=os.path.dirname(sys.executable))   # the copy finds python's own library (-E keeps it from the user's PYTHONPATH)
    p = subprocess.Popen([exe, "-c", script, log, "8"], cwd=game_dir, creationflags=0x08000000, env=env,
                         stderr=subprocess.PIPE)
    try:
        time.sleep(0.4)
        check(p.poll() is None, "the pretend game starts" + ("" if p.poll() is None else f": {p.stderr.read()[:200]}"))
        games = C.games(force=True)
        check("pretend-game-vr" in games and games["pretend-game-vr"]["where"] == game_dir,
              "the pretend game is on this PC's list, from game_dir in lanes.conf")
        time.sleep(0.5)
        live = C.tick(time.time())
        check(any("pretend-game-vr" in x for x in live), f"collecting starts when the game runs: {live}")
        run = next(iter(C._runs.values()), None)
        check(run is not None and run["exe"].lower() == "game.exe" and run["project"] == "pretend-game-vr",
              "the run names the program and the project")
        time.sleep(0.6)
        C.tick(time.time())
        time.sleep(0.6)
        C.tick(time.time())
        samples = os.path.join(run["folder"], "samples.tsv")
        rows = [l for l in open(samples, encoding="utf-8") if not l.startswith("#")] if os.path.isfile(samples) else []
        check(len(rows) >= 2, f"samples are written while it runs ({len(rows)} rows)")
        check(rows and rows[0].count("\t") == len(C.SAMPLE_COLS) - 1, "a sample row has every column")
        p.wait(timeout=20)
        time.sleep(0.3)
        live = C.tick(time.time())
        check(not live and not C._runs, "the run ends when the game closes")
        # shelved for Gold Digger
        sys.path.insert(0, os.path.join(PLUGIN, "tools"))
        import gd
        rows = gd.index("pretend-game-vr")
        shelves_used = {r["shelf"] for r in rows}
        check("runs" in shelves_used, f"run.json is on the 'runs' shelf ({sorted(shelves_used)})")
        check("performance" in shelves_used, "samples and events are on the 'performance' shelf")
        check("logs" in shelves_used, "the log the game wrote during the run is on the 'logs' shelf")
        card = next((r for r in rows if r["shelf"] == "runs"), None)
        data = json.load(open(os.path.join(gd.game_dir("pretend-game-vr"), card["item"]), encoding="utf-8")) if card else {}
        check(data.get("ended") == "crashed" and data.get("samples", 0) >= 2 and data.get("pc") == "TESTPC",
              f"the run card says how it ended (a dump in the game folder = crashed) and who collected it: "
              f"{data.get('ended')}, {data.get('samples')} samples")
        check("game.log" in " ".join(data.get("logs", [])), "the run card lists the copied log")
        check(data.get("crashes") == ["pretend_crash.dmp"] and "crashes" in shelves_used,
              f"the dump is on the 'crashes' shelf and named on the card: {data.get('crashes')}")
        check(not os.path.isdir(run["folder"]), "the local staging copy is gone once shelved")
        ledger = C.read_ledger()
        check(ledger and ledger[-1]["shelved"] == "yes" and ledger[-1]["ended"] == "crashed", "the ledger has the run")
        # a run shorter than MIN_RUN_S is a bounce: noted, not shelved
        C.MIN_RUN_S = 3600
        p2 = subprocess.Popen([exe, "-c", "import time; time.sleep(0.8)"], cwd=game_dir, creationflags=0x08000000,
                              env=env)
        time.sleep(0.3)
        C.tick(time.time())
        p2.wait(timeout=20)
        time.sleep(0.2)
        C.tick(time.time())
        before = len(rows)
        check(len(gd.index("pretend-game-vr")) == before and C.read_ledger()[-1]["ended"] == "brief",
              "a launcher bounce is noted in the ledger and not shelved")
        # 2026-11-05: two copies of the game starting in the same second get a folder each (GZDoom VR on the home PC
        # put a launcher and the game into one folder), and a program running before the helper watched it says so
        C.MIN_RUN_S = 0
        twins = [subprocess.Popen([exe, "-c", "import time; time.sleep(3)"], cwd=game_dir, creationflags=0x08000000,
                                  env=env) for _ in range(2)]
        time.sleep(0.4)
        C.tick(time.time())
        folders = [r["folder"] for r in C._runs.values()]
        check(len(folders) == 2 and len(set(folders)) == 2, f"two copies found in one second get two folders: {folders}")
        for r in C._runs.values():
            r["_start_ts"] -= 200            # as if the program had run 200 s before the helper began watching it
        for q in twins:
            q.wait(timeout=20)
        time.sleep(0.3)
        C.tick(time.time())
        cards = [json.load(open(os.path.join(gd.game_dir("pretend-game-vr"), r["item"]), encoding="utf-8"))
                 for r in gd.index("pretend-game-vr") if r["shelf"] == "runs"]
        late = [c for c in cards if c.get("seconds", 0) >= 200]
        check(len(late) == 2 and all(c.get("watched_s", 999) < 60 and any("watched for" in n for n in c["notes"])
                                     for c in late),
              f"a card watched only part of its program's life says so: "
              f"{[(c.get('seconds'), c.get('watched_s'), c.get('notes')) for c in late]}")
        # the skip list and the not-a-game list
        check("skipped-game" in C.skip_list(), "collect_skip is read from lanes.conf")
        check("vrserver.exe" in C.NOT_GAMES and "python.exe" in C.NOT_GAMES, "the VR runtime and python are never games")
    finally:
        try:
            p.kill()
        except Exception:
            pass
        shutil.rmtree(t, ignore_errors=True)
    print(f"collector: {'all passed' if not fails else str(fails) + ' failed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
