#!/usr/bin/env python3
"""obs_rec_test.py - obs-rec.py's start guards (0.113.1): OBS's video is reset only when it differs from ours, and only
one recorder start runs at a time. OBS 33.0.1 crashed inside obs_reset_video on 2026-11-12 when two game starts
overlapped and both re-sent the same video settings. No OBS is needed: the client is a stand-in.
    python tools/tests/obs_rec_test.py
"""
import importlib.util
import os
import sys
import tempfile
import threading
import time
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("obs_rec", os.path.join(HERE, "..", "obs-rec.py"))
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)

fails = 0


def check(ok, what):
    global fails
    print(("  ok    " if ok else "  FAIL  ") + what)
    if not ok:
        fails += 1


# ----- the video settings are sent only when they differ -----
same = SimpleNamespace(**R.video_wanted())
check(not R.video_differs(same), "OBS already at 1280x720, 60 fps: nothing is sent (no video reset)")
check(R.video_differs(SimpleNamespace(**dict(R.video_wanted(), base_width=1920))), "another canvas size is sent")
check(R.video_differs(SimpleNamespace(**dict(R.video_wanted(), fps_numerator=30))), "another frame rate is sent")


class FakeClient:
    def __init__(self, cur):
        self.cur, self.sent = cur, []

    def get_video_settings(self):
        return self.cur

    def set_video_settings(self, **kw):
        self.sent.append(kw)


def video_step(cl):
    """the two lines of ensure_setup that touch the video, as written there"""
    if R.video_differs(cl.get_video_settings()):
        cl.set_video_settings(numerator=R.FPS, denominator=1, base_width=R.VIDEO_W, base_height=R.VIDEO_H,
                              out_width=R.VIDEO_W, out_height=R.VIDEO_H)


src = open(os.path.join(HERE, "..", "obs-rec.py"), encoding="utf-8").read()
check("if video_differs(cl.get_video_settings()):\n        cl.set_video_settings(" in src,
      "ensure_setup asks OBS first and resets the video only on a difference")
cl = FakeClient(same)
video_step(cl)
video_step(cl)
check(cl.sent == [], "two starts in a row on a set-up OBS reset the video zero times")
cl = FakeClient(SimpleNamespace(**dict(R.video_wanted(), base_width=1920)))
video_step(cl)
check(len(cl.sent) == 1 and cl.sent[0]["base_width"] == 1280, "a different OBS is set once, to ours")

# ----- one start at a time -----
T = tempfile.mkdtemp()
lock = os.path.join(T, "start.lock")
check(R.take_start_lock(lock, wait_s=0), "the first start takes the lock")
t0 = time.time()
check(not R.take_start_lock(lock, wait_s=0.5, poll_s=0.1), "a second start does not get it while the first holds it")
check(time.time() - t0 >= 0.4, "the second start waited before giving up")
R.free_start_lock(lock)
check(not os.path.exists(lock), "the first start gives the lock back")

check(R.take_start_lock(lock, wait_s=0), "taken again")
threading.Timer(0.3, R.free_start_lock, args=(lock,)).start()
check(R.take_start_lock(lock, wait_s=3, poll_s=0.05), "a second start waits and goes on once the first is done")
R.free_start_lock(lock)

with open(lock, "w") as f:
    f.write("99999 0\n")
old = time.time() - 1000
os.utime(lock, (old, old))
check(R.take_start_lock(lock, wait_s=0, stale_s=300), "a lock left by a start that was cut off is taken over")
R.free_start_lock(lock)

check("if not take_start_lock():" in src and "free_start_lock()" in src.split("def _start", 1)[0],
      "cmd_start holds the lock around the whole start and frees it afterwards")
check('if __name__ == "__main__":' in src, "the tool runs only when started, so it can be tested")

print()
print("obs_rec_test.py: %s" % ("all passed" if not fails else "%d FAILED" % fails))
sys.exit(1 if fails else 0)
