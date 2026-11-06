"""rider_test.py - the BeG0nE rider must never die on one bad recording (2026-11-04: twice in one evening on the home PC,
a Ghost Hand log the game still held open killed the loop, and a whole headset run went uncollected). Checks: a held
file is left for a later pass and moved once free; a recording is filed once, never twice; a pass that throws does not
end the loop; a recording whose header says game=? is named after the collector's open run, never "?".
Nothing of a real game; everything in a temp folder. Exit 0 = pass."""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(os.path.dirname(HERE))
fails = 0


def check(ok, what):
    global fails
    print(("ok   " if ok else "FAIL ") + what)
    if not ok:
        fails += 1


def main():
    t = tempfile.mkdtemp(prefix="rider-test-")
    os.environ["LANES_CONFIG"] = os.path.join(t, "lanes.conf")
    os.environ["LANES_STATE_DIR"] = os.path.join(t, "state")
    os.environ["LANES_GD_DIR"] = os.path.join(t, "shelves")
    os.environ["LANES_BEGONE"] = os.path.join(t, "begone-home")
    open(os.environ["LANES_CONFIG"], "w").write("machine_name = TESTPC\n")
    sys.path.insert(0, os.path.join(PLUGIN, "begone"))
    import rider as R
    R.say = lambda msg: said.append(msg)
    said = []

    # 1. a recording the game still holds open: Windows refuses the move; the rider leaves it and lives
    logs = os.path.join(t, "logs")
    os.makedirs(logs)
    p = os.path.join(logs, "ghosthand_2026-11-04.ghl")
    open(p, "w").write("game=?\npid=lua\n" + "x" * 500)
    held = open(p, "r")                      # Python opens without delete-sharing, as the game's own handle does
    calls = []
    R.file_one = lambda tool, path, game=None: calls.append((path, game)) or "filed"
    tool = {"name": "Ghost Hand BeG0nE", "short": "ghost-hand"}
    announced, filed = {p}, set()
    if os.name == "nt":
        R.file_ended([(tool, p, "pretend-game-vr")], announced, filed)
        check(os.path.isfile(p), "a held file stays where it is (not lost, not half-moved)")
        check(p in filed, "a held file is remembered as filed")
        check(any("still held open" in s for s in said), "the rider says the file is still held")
        R.file_ended([(tool, p, "pretend-game-vr")], announced, filed)
        check(len(calls) == 1, f"a held file is filed once, not again on the next pass (filed {len(calls)} times)")
    else:
        print("skip held-file checks: only Windows refuses to move an open file")
    held.close()
    R.file_ended([(tool, p, "pretend-game-vr")], announced, filed)
    check(not os.path.exists(p) and os.path.isfile(os.path.join(logs, "done", os.path.basename(p))),
          "once free, the file is moved into done\\")
    check(p not in filed and p not in announced, "a moved file is forgotten")
    check(len(calls) == 1, f"filed exactly once in all ({len(calls)})")

    # 2. a filer that throws is reported, and the file is still put away
    q = os.path.join(logs, "ghosthand_2026-11-05.ghl")
    open(q, "w").write("game=x\n")

    def boom(*a, **k):
        raise RuntimeError("filer broke")
    R.file_one = boom
    R.file_ended([(tool, q, "x")], set(), set())
    check(any("could not file" in s for s in said) and not os.path.exists(q), "a filer that throws does not stop the rest")

    # 3. a pass that throws does not end the loop
    passes = []

    def bad_pass(*a):
        passes.append(1)
        if len(passes) == 1:
            raise PermissionError("[WinError 32] the file is used by another process")
        raise KeyboardInterrupt              # the second pass ends the test
    R.one_pass, R.POLL_S = bad_pass, 0
    R.PID_FILE = os.path.join(t, "ride.pid")
    R.feature_on = lambda name: False
    R.write_state = lambda **k: None
    try:
        R.run()
    except KeyboardInterrupt:
        pass
    check(len(passes) == 2, "after a pass throws, the rider runs the next one")
    check(any("one pass failed, carrying on" in s for s in said), "the failed pass is written to the rider's log")

    # 4. game=? is named after the collector's open run, never "?"
    runs = [{"game": "visceral-re8-vr", "exe": "re8.exe"}]
    check(R.game_of({"game": "visceral-re8-vr"}) == "visceral-re8-vr", "a header's game is kept")
    check(R.game_of({"game": "?"}, ["re8.exe"], runs) == "visceral-re8-vr", "game=? takes the open run's game")
    check(R.game_of({}, [], runs) == "visceral-re8-vr", "no game= and one open run: that run's game")
    check(R.game_of({"game": "?"}, [], []) == R.UNKNOWN_GAME, "nothing to go by: unknown-game, not ?")
    two = runs + [{"game": "the-darkness-vr", "exe": "darkness.exe"}]
    check(R.game_of({"game": "?"}, [], two) == R.UNKNOWN_GAME, "two open runs and no clue: unknown-game, no guess")
    check(R.game_of({"game": "?"}, ["darkness.exe"], two) == "the-darkness-vr", "two open runs: the VR one wins")
    check("?" not in R.UNKNOWN_GAME, "the fallback name is a valid folder name")

    print("rider_test: " + ("all passed" if not fails else f"{fails} failed"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
