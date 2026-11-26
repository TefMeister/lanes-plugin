"""no_window_live.py - the release's live check that hidden.py really keeps console windows off the desktop (0.125.1).

It watches every window shown on the desktop (a WinEvent hook, the same way the black boxes were caught on
2026-11-26), then plays a background tool: a pythonw program (no console, like the rider and the doorman) that
  1. runs console programs through hidden.run (cmd, where),
  2. starts a background tool through hidden.background, which runs a console program WITHOUT hidden.py
     (a forgotten call: it must still open no window, since it shares the hidden console),
  3. hands over through hidden.ensure_console, as a tool started by an old Startup entry does.
Passes when the watcher proved it can see a window (its own, off the screen) and no console window showed.
    python no_window_live.py              the check (exit 0 pass, 1 fail; skipped with 0 off Windows)
    python no_window_live.py --control    also start one console program the OLD way, minimised: it must be seen
"""
import ctypes
import ctypes.wintypes as W
import os
import subprocess
import sys
import tempfile
import threading
import time

if os.name != "nt":
    print("no_window_live: skipped (not Windows)")
    sys.exit(0)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
CONSOLE_CLASSES = {"ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS", "PseudoConsoleWindow", "mintty"}
PROBE_CLASS = "LanesNoWindowProbe"
WAIT_S = 20                     # the child's three steps must finish in this time
SETTLE_S = 1.5                  # and nothing may show for this long after
EVENT_OBJECT_SHOW = 0x8002
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.DefWindowProcW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
user32.CreateWindowExW.restype = W.HWND
seen = []                       # (class, title)
lock = threading.Lock()

CHILD = r'''
import os, sys, subprocess
sys.path.insert(0, sys.argv[1])
import hidden
out = sys.argv[2]
step = sys.argv[3] if len(sys.argv) > 3 else "main"
if step == "hop":
    hidden.ensure_console()
    r = subprocess.run(["cmd", "/c", "ver"], capture_output=True)     # unflagged on purpose
    open(out + ".hop", "a").write("%d%d;" % (r.returncode, hidden.has_console()))
    sys.exit(0)
if step == "bg":
    hidden.ensure_console()                                           # must NOT start again: it has a (hidden) console
    r = subprocess.run(["cmd", "/c", "ver"], capture_output=True)     # unflagged on purpose: the hidden console covers it
    open(out + ".bg", "a").write("%d%d;" % (r.returncode, hidden.has_console()))
    sys.exit(0)
codes = [hidden.run(["cmd", "/c", "ver"], capture_output=True).returncode,
         hidden.run(["where", "cmd"], capture_output=True).returncode]
hidden.background([os.path.abspath(__file__), sys.argv[1], out, "bg"])
subprocess.Popen([sys.executable, os.path.abspath(__file__), sys.argv[1], out, "hop"])   # pythonw, no console
open(out, "w").write(",".join(map(str, codes)))
'''

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
WinEventProc = ctypes.WINFUNCTYPE(None, W.HANDLE, W.DWORD, W.HWND, W.LONG, W.LONG, W.DWORD, W.DWORD)


def cls_title(hwnd):
    b = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, b, 256)
    t = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, t, 256)
    return b.value, t.value


def on_event(hook, event, hwnd, id_object, id_child, thread, t):
    if id_object != 0 or not hwnd or user32.GetParent(hwnd):
        return
    c, title = cls_title(hwnd)
    if c in CONSOLE_CLASSES or c == PROBE_CLASS:
        with lock:
            seen.append((c, title))


CB = WinEventProc(on_event)
PROC = WNDPROC(lambda h, m, w, l: user32.DefWindowProcW(h, m, w, l))
ready = threading.Event()


def watcher():
    user32.SetWinEventHook(EVENT_OBJECT_SHOW, EVENT_OBJECT_SHOW, 0, CB, 0, 0, 0)
    probe()                     # on this thread, which pumps the hook's messages
    ready.set()
    msg = W.MSG()
    while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) > 0:
        user32.DispatchMessageW(ctypes.byref(msg))


class WNDCLASS(ctypes.Structure):
    _fields_ = [("style", W.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", W.HINSTANCE), ("hIcon", W.HICON), ("hCursor", W.HANDLE), ("hbrBackground", W.HBRUSH),
                ("lpszMenuName", W.LPCWSTR), ("lpszClassName", W.LPCWSTR)]


def probe():
    """show a window of our own far off the screen: the watcher must see it, or the check proves nothing"""
    wc = WNDCLASS(lpfnWndProc=PROC, hInstance=kernel32.GetModuleHandleW(None), lpszClassName=PROBE_CLASS)
    user32.RegisterClassW(ctypes.byref(wc))
    WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE, WS_POPUP = 0x80, 0x08000000, 0x80000000
    h = user32.CreateWindowExW(WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE, PROBE_CLASS, "probe", WS_POPUP,
                               -32000, -32000, 10, 10, None, None, wc.hInstance, None)
    user32.ShowWindow(h, 4)     # SW_SHOWNOACTIVATE
    msg = W.MSG()
    end = time.time() + 0.5
    while time.time() < end:    # let the hook's call for our own window come in
        while user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.02)
    user32.DestroyWindow(h)


def main():
    threading.Thread(target=watcher, daemon=True).start()
    ready.wait(5)
    with lock:
        saw_probe = any(c == PROBE_CLASS for c, _ in seen)
        seen.clear()
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.isfile(pyw):
        print("no_window_live: skipped (no pythonw.exe beside this Python)")
        return 0
    tmp = tempfile.mkdtemp(prefix="lanes-nowin-")
    child, out = os.path.join(tmp, "child.py"), os.path.join(tmp, "out.txt")
    open(child, "w").write(CHILD)
    subprocess.Popen([pyw, child, TOOLS, out])          # pythonw: no console, like a background tool
    deadline = time.time() + WAIT_S
    while time.time() < deadline and not all(os.path.exists(out + s) for s in ("", ".bg", ".hop")):
        time.sleep(0.2)
    time.sleep(SETTLE_S)        # a second copy (a hop too many) would write its line in this time
    def lines(s):
        try:
            return open(out + s).read()
        except OSError:
            return ""
    done = {"": os.path.exists(out), ".bg": lines(".bg") == "01;", ".hop": lines(".hop") == "01;"}
    if "--control" in sys.argv:
        si = subprocess.STARTUPINFO()
        si.dwFlags, si.wShowWindow = 1, 7                # minimised, not activated
        subprocess.Popen([pyw, "-c", "import subprocess; subprocess.run(['cmd','/c','ping -n 2 127.0.0.1 >nul'])"],
                         startupinfo=si)
        time.sleep(3)
    time.sleep(SETTLE_S)
    with lock:
        windows = [x for x in seen if x[0] != PROBE_CLASS]
    ok = True
    print("  %s the watcher sees a window shown on the desktop (its own, off the screen)" % ("ok  " if saw_probe else "FAIL"))
    ok &= saw_probe
    for s, what in (("", "hidden.run from a program with no console"), (".bg", "a forgotten call under hidden.background"),
                    (".hop", "ensure_console hands over from pythonw")):
        print("  %s %s ran, once, with a console%s" % ("ok  " if done[s] else "FAIL", what,
                                                       "" if done[s] or not s else " (%r)" % lines(s)))
        ok &= done[s]
    if "--control" in sys.argv:
        print("  %s control: the old way was seen (%d window(s))" % ("ok  " if windows else "FAIL", len(windows)))
        ok &= bool(windows)
    else:
        print("  %s no console window showed (%d)" % ("ok  " if not windows else "FAIL", len(windows)))
        for c, t in windows:
            print("       %s %r (another program on this PC may have opened it: run again)" % (c, t[:80]))
        ok &= not windows
    print("no_window_live:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
