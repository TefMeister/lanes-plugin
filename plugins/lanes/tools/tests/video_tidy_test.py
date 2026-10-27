"""video_tidy_test.py - BeG0nE's videos take themselves off once nothing needs them (0.90.0), with made-up files in a
temporary folder, nothing of a real game. Exit 0 = pass."""
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "begone"))

DAY_MS = 86400 * 1000
fails = 0


def check(ok, what):
    global fails
    print(("  ok    " if ok else "FAIL: ") + what)
    fails += not ok


def video(root, game, name, start_ms, stop_ms=None):
    d = os.path.join(root, game)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name)
    open(p, "wb").write(b"0" * 1024)
    side = {"start_ms": start_ms, "file": name}
    if stop_ms:
        side["stop_ms"] = stop_ms
    json.dump(side, open(p + ".json", "w"))
    return p


def main():
    t = tempfile.mkdtemp()
    try:
        rec = os.path.join(t, "rec")
        home = os.path.join(t, "home")
        conf = os.path.join(t, "lanes.conf")
        open(conf, "w").write(f"recordings = {rec}\n")
        os.environ["LANES_CONFIG"] = conf
        os.environ["LANES_BEGONE"] = home
        os.environ["LOCALAPPDATA"] = t
        import video_tidy as vt
        import begone_common as bc
        vt.REMOVED_LOG = os.path.join(t, "videos-removed.tsv")

        now = time.mktime(time.strptime("2026-10-27 12-00-00", "%Y-%m-%d %H-%M-%S"))
        at = lambda days, h=12: int((now - days * 86400) * 1000) + (h - 12) * 3600 * 1000
        old_day = video(rec, "game-a", "begone_old.mp4", at(3), at(3) + 60000)
        last_day = video(rec, "game-a", "begone_new.mp4", at(1), at(1) + 60000)
        stale = video(rec, "game-b", "begone_stale.mp4", at(20), at(20) + 60000)
        fresh = video(rec, "game-c", "begone_fresh.mp4", at(5), at(5) + 60000)
        running = video(rec, "game-c", "begone_running.mp4", at(0))
        waits = video(rec, "game-d", "begone_waits.mp4", at(30), at(30) + 600000)

        # a jitter report of game-d from inside its recording, not lined up with it yet
        t_jit = bc.tool("camera-jitter")
        idx = bc.index_path(t_jit)
        os.makedirs(os.path.dirname(idx), exist_ok=True)
        when = time.localtime((at(30) + 120000) / 1000)
        open(idx, "w", encoding="utf-8").write("run,game,date,time\nr1,game-d,"
                                               + time.strftime("%Y-%m-%d,%H-%M-%S", when) + "\n")

        gone = {name for _, name, _, _ in vt.tidy(now=now, root=rec)}
        check("begone_old.mp4" in gone and not os.path.exists(old_day) and not os.path.exists(old_day + ".json"),
              "a video from an earlier day goes once the game is tested again (and its .json with it)")
        check(os.path.exists(last_day), "the last test day of a game stays")
        check("begone_stale.mp4" in gone, "a video older than two weeks goes")
        check(os.path.exists(fresh), "a video younger than two weeks, of the last test, stays")
        check(os.path.exists(running), "a recording that is still running stays")
        check(os.path.exists(waits), "a video whose jitter frames are not cut yet stays, however old")
        check(os.path.isfile(vt.REMOVED_LOG) and len(open(vt.REMOVED_LOG).read().splitlines()) == 2,
              "every removal is written down")

        os.makedirs(os.path.join(bc.data_dir(t_jit), "game-d", "r1"), exist_ok=True)
        open(os.path.join(bc.data_dir(t_jit), "game-d", "r1", "recording.json"), "w").write("{}")
        gone = {name for _, name, _, _ in vt.tidy(now=now, root=rec)}
        check(gone == {"begone_waits.mp4"}, f"once its frames are cut, the old one goes too (went: {sorted(gone)})")
    finally:
        shutil.rmtree(t, ignore_errors=True)
    print(f"video_tidy: {'FAIL' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
