"""frames_test.py - BeG0nE's jitter log lined up with a recording of the same session (0.76.0), with a made-up log and
a made-up video, nothing of a real game. Exit 0 = pass (or skipped: no ffmpeg on this PC)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
JIT = os.path.join(HERE, "..", "..", "begone", "camera-jitter")
sys.path.insert(0, JIT)

START_MS = 1_700_000_000_000      # the made-up recording's first frame
LOG_AT_S = 2.0                    # the log starts this far into the recording
VIDEO_S, FPS = 12, 60

fails = 0


def check(ok, what):
    global fails
    print(("  ok    " if ok else "FAIL: ") + what)
    fails += not ok


def main():
    ff = shutil.which("ffmpeg")
    if not ff:
        print("frames: skipped (no ffmpeg on this PC)")
        return 0
    t = tempfile.mkdtemp()
    try:
        rec = os.path.join(t, "rec", "selftest")
        os.makedirs(rec)
        conf = os.path.join(t, "lanes.conf")
        open(conf, "w").write(f"recordings = {os.path.join(t, 'rec')}\n")
        os.environ["LANES_CONFIG"] = conf
        import frames
        import jitter_log_check as jc
        video = os.path.join(rec, "begone_2023-11-14_23-13-20.mp4")
        subprocess.run([ff, "-v", "error", "-f", "lavfi", "-i", f"testsrc=size=320x180:rate={FPS}", "-t", str(VIDEO_S),
                        "-pix_fmt", "yuv420p", video], check=True)
        json.dump({"start_ms": START_MS, "stop_ms": START_MS + VIDEO_S * 1000, "window": "game window", "fps": FPS,
                   "file": os.path.basename(video)}, open(video + ".json", "w"))

        log = os.path.join(t, "selftest.jl")
        text = jc._synth("stepped").replace("#jitterlog 1 game=selftest runtime=none",
                                            f"#jitterlog 1 game=selftest runtime=none wall_ms={START_MS + int(LOG_AT_S * 1000)}")
        open(log, "w").write(text)
        run = os.path.join(t, "data", "selftest", "run1")
        jc.check(log, run)
        line = frames.attach(run, log, "selftest")
        r = json.load(open(os.path.join(run, "recording.json")))
        v = r["videos"][0] if r.get("videos") else {}
        check(abs(v.get("offset_s", -1) - LOG_AT_S) < 1e-6, f"the log is found {LOG_AT_S} s into the recording")
        cuts = [c for c in v.get("cuts", []) if c["frames"]]
        check(any(c["stretch"].startswith("jitter_") for c in cuts), "a jittery stretch is cut out as frames")
        c = cuts[0] if cuts else {}
        folder = os.path.join(t, "rec", c.get("folder", "-"))
        want = round((c.get("to_s", 0) - c.get("from_s", 0) + 2 * frames.PAD_S) * FPS)
        check(abs(c.get("frames", 0) - want) <= 1, f"every frame of it, padded either side ({c.get('frames')} of {want})")
        check(os.path.isfile(os.path.join(folder, "sheet.jpg")), "all of them on one sheet")
        text = open(os.path.join(folder, "frames.txt")).read().splitlines() if os.path.isdir(folder) else []
        first = next((x for x in text if x.startswith("f_001.jpg")), "")
        check(f"log {c.get('from_s', 0) - frames.PAD_S:7.3f} s" in first, "frames.txt gives each frame's log second")
        try:
            import numpy, PIL  # noqa: F401
            check(any(x.startswith("on screen:") for x in text), "frames.txt says how many pictures held or jumped")
        except ImportError:
            print("  skip  the on-screen check needs Pillow and numpy")
        check("On the recording" in open(os.path.join(run, "report.md"), encoding="utf-8").read(),
              "the report says where to look")
        check("cut" in line, "attach answers in one line")

        os.remove(video + ".json")
        line = frames.attach(run, log, "selftest")
        check("no recording" in line, "no recording of that time: it says so")
    finally:
        shutil.rmtree(t, ignore_errors=True)
    print(f"frames: {'FAIL' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
