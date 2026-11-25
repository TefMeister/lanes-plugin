#!/usr/bin/env python3
"""backstage_test.py - Backstage-o-matiC (tools/backstage/backstage.py): a window that appears is moved off the screen at
once and logged, the watcher ends when its program ends, the pad's commands, and the report in plain words.

A small test window of our own stands in for a game (shown WITHOUT activation, so the test never takes your focus,
your mouse or your keys). The state folder is a temporary one (LANES_STATE_DIR)."""
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
TMP = tempfile.mkdtemp(prefix="backstage-test-")
os.environ["LANES_STATE_DIR"] = TMP
sys.path.insert(0, os.path.join(TOOLS, "backstage"))
import backstage as B  # noqa: E402

PASS = FAIL = 0


def check(what, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  ok   " + what)
    else:
        FAIL += 1
        print("  FAIL " + what + (": " + detail if detail else ""))


# A stand-in game: waits DELAY s (so the watcher is ready), shows a 320x200 window at 200,200 without activating it,
# keeps it for LIFE s, then ends.
FAKE_GAME = r'''
import ctypes, ctypes.wintypes as w, sys, time
u = ctypes.windll.user32; k = ctypes.windll.kernel32
delay, life = float(sys.argv[1]), float(sys.argv[2])
time.sleep(delay)
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
u.DefWindowProcW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]; u.DefWindowProcW.restype = ctypes.c_ssize_t
proc = WNDPROC(lambda h, m, wp, lp: u.DefWindowProcW(h, m, wp, lp))
class WC(ctypes.Structure):
    _fields_ = [("style", w.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", w.HINSTANCE), ("hIcon", w.HICON), ("hCursor", w.HANDLE), ("hbrBackground", w.HBRUSH),
                ("lpszMenuName", w.LPCWSTR), ("lpszClassName", w.LPCWSTR)]
wc = WC(0, proc, 0, 0, k.GetModuleHandleW(None), None, None, None, None, "BackstageTestGame")
u.RegisterClassW(ctypes.byref(wc))
u.CreateWindowExW.restype = w.HWND
h = u.CreateWindowExW(0x08000000, "BackstageTestGame", "Backstage test game", 0x00CF0000, 200, 200, 320, 200,
                      None, None, wc.hInstance, None)   # WS_EX_NOACTIVATE, WS_OVERLAPPEDWINDOW
u.ShowWindow(h, 4)                                      # SW_SHOWNOACTIVATE
print(int(h), flush=True)
end = time.time() + life; msg = w.MSG()
while time.time() < end:
    while u.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):
        u.TranslateMessage(ctypes.byref(msg)); u.DispatchMessageW(ctypes.byref(msg))
    time.sleep(0.01)
'''


def test_watch(where):
    print("the watcher, %s" % where)
    os.environ["BACKSTAGE_PLACE"] = where
    owner = B.u.GetForegroundWindow()
    script = os.path.join(TMP, "fake_game.py")
    open(script, "w", encoding="utf-8").write(FAKE_GAME)
    game = subprocess.Popen([sys.executable, script, "1.5", "4"], stdout=subprocess.PIPE, text=True,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    log = os.path.join(TMP, "flash-%s.jsonl" % where)
    watcher, _ = B.start_watch([], log, max_s=60, pid=game.pid)
    hwnd = int(game.stdout.readline().strip() or 0)
    check("the stand-in game made its window", hwnd > 0)
    time.sleep(0.8)
    if where == B.OFF_SCREEN:
        check("its window is off the screen", hwnd and not B.on_screen(hwnd))
    else:
        check("its window is still on the monitor", hwnd and B.on_screen(hwnd))
        check("it lies under your window, not over it", hwnd and owner and not B.above(hwnd, owner))
    check("it was never activated (your window kept the focus)", B.u.GetForegroundWindow() != hwnd)
    game.wait(timeout=20)
    try:
        watcher.wait(timeout=B.GONE_GRACE_S + 10)
    except subprocess.TimeoutExpired:
        watcher.kill()
    rows = [json.loads(l) for l in open(log, encoding="utf-8")] if os.path.exists(log) else []
    shown = [r for r in rows if r["event"] in ("shown", "seen_on_screen")]
    check("the log has the window", len(shown) >= 1, str(rows))
    check("it was moved by the event, not the half-second check", shown and shown[0]["event"] == "shown", str(shown))
    check("it was on screen under 100 ms", shown and shown[0].get("on_screen_ms", 999) < 100, str(shown))
    check("the watcher ended by itself when the game ended",
          rows and rows[-1]["event"] == "end" and rows[-1].get("why") == "the game closed", str(rows[-1:]))
    lines = B.report_lines(log)
    word = "on the screen" if where == B.OFF_SCREEN else "on top of your windows"
    check("the report says where and for how long", any(word in l for l in lines), str(lines))


class FakePad:
    BUTTONS = {"a": "A", "start": "START"}

    def __init__(self):
        self.calls = []

    def update(self):
        self.calls.append("update")

    def press_button(self, b):
        self.calls.append("press " + b)

    def release_button(self, b):
        self.calls.append("release " + b)

    def left_joystick_float(self, x, y):
        self.calls.append("left %.1f %.1f" % (x, y))

    def right_joystick_float(self, x, y):
        self.calls.append("right %.1f %.1f" % (x, y))

    def left_trigger_float(self, v):
        self.calls.append("lt %.1f" % v)

    def right_trigger_float(self, v):
        self.calls.append("rt %.1f" % v)


def test_pad():
    print("the kept pad")
    p = FakePad()
    B.pad_line(p, ["a", "0.01"], p.BUTTONS)
    check("a button is pressed and let go", "press A" in p.calls and "release A" in p.calls)
    p.calls.clear()
    B.pad_line(p, ["stick", "0", "1", "0.01"], p.BUTTONS)
    check("a stick is held, then centred", p.calls[0] == "left 0.0 1.0" and "left 0.0 0.0" in p.calls, str(p.calls))
    check("quit ends the pad", B.pad_line(p, ["quit"], p.BUTTONS) is False)
    try:
        B.pad_line(p, ["jump"], p.BUTTONS)
        check("an unknown word is refused", False)
    except ValueError:
        check("an unknown word is refused", True)
    cmd = os.path.join(TMP, "pad_cmd.txt")
    import threading
    t = threading.Thread(target=B.pad_serve, args=(cmd, FakePad(), 10))
    t.start()
    time.sleep(0.3)
    B.pad_send(["start", "0.01"], cmd)
    B.pad_send(["quit"], cmd)
    t.join(5)
    log = open(cmd + ".log", encoding="utf-8").read()
    check("the pad keeper carries out sent lines and stops on quit", "start 0.01 done" in log and "quit" in log, log)


def test_you_chose():
    print("your click, or the game taking the front by itself")
    uc = B.user_chose
    check("a click on the game in the taskbar a moment ago = you", uc(10_000, 9_800, 0, True, False))
    check("Alt held (Alt+Tab) a moment ago = you", uc(10_000, 9_900, 0, False, True))
    check("no recent input = the game did it by itself", not uc(10_000, 5_000, 0, True, False))
    check("recent typing elsewhere, pointer not on the game or taskbar = the game", not uc(10_000, 9_950, 0, False, False))
    check("our own Alt tap is never taken for yours", not uc(10_000, 9_900, 9_900, True, True))
    check("your click well after our tap still counts", uc(10_000, 9_900, 8_000, True, False))
    check("the tick counter wrapping round is no trouble", uc(100, 0xFFFFFF00, 0, True, False))


def test_report():
    print("the report")
    log = os.path.join(TMP, "r.jsonl")
    with open(log, "w", encoding="utf-8") as f:
        for r in ({"t": 0, "event": "start"}, {"t": 4.1, "event": "shown", "exe": "game.exe", "on_screen_ms": 3.2},
                  {"t": 9, "event": "seen_on_screen", "exe": "game.exe", "on_screen_ms": 0.4},
                  {"t": 4.2, "event": "focus", "exe": "game.exe", "given_back": True, "back_ms": 5},
                  {"t": 60, "event": "focus", "exe": "game.exe", "given_back": False, "back_ms": 5},
                  {"t": 99, "event": "end", "why": "the game closed"}):
            f.write(json.dumps(r) + "\n")
    lines = B.report_lines(log)
    text = "\n".join(lines)
    check("counts the times on top", "2 time(s) on top of your windows" in text, text)
    check("says the half-second check found one", "half-second check" in text, text)
    check("says the focus was NOT given back once", "NOT given back 1" in text, text)
    check("says why the watch ended", "the game closed" in text, text)


if __name__ == "__main__":
    if os.name != "nt":
        print("Windows only; skipped")
        sys.exit(0)
    test_report()
    test_you_chose()
    test_pad()
    test_watch(B.BEHIND)
    test_watch(B.OFF_SCREEN)
    os.environ["BACKSTAGE_PLACE"] = ""
    print("where the game goes")
    check("behind is the default", B.place() == B.BEHIND)
    os.environ["BACKSTAGE_PLACE"] = "off-screen"
    check("'off-screen' is read as off_screen", B.place() == B.OFF_SCREEN)
    print("backstage_test: %d passed, %d failed" % (PASS, FAIL))
    sys.exit(1 if FAIL else 0)
