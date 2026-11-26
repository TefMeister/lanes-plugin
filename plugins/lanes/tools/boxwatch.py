"""boxwatch: log every console window that shows on the desktop, with who started it.

Runs under pythonw (no console of its own). Two parts:
  1. a WinEvent hook (EVENT_OBJECT_SHOW, out of context) that fires the moment any
     top-level window is shown; console-ish classes are logged at once;
  2. a process poller (every 40 ms) keeping the last 10 s of new processes with their
     command line and parent chain, dumped next to each window event, so a box that
     lives 100 ms is still traced to the program that started it.
Log: argv[1] (JSON lines).

    pythonw boxwatch.py <log.jsonl>      (0.125.1; PROTOCOL section 52) stop it with Task Manager or taskkill
"""
import ctypes, ctypes.wintypes as W, json, sys, threading, time, collections
import psutil

LOG = sys.argv[1]
CONSOLE_CLASSES = {"ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS",
                   "PseudoConsoleWindow", "mintty"}
user32 = ctypes.windll.user32
EVENT_OBJECT_SHOW = 0x8002
EVENT_OBJECT_CREATE = 0x8000
WINEVENT_OUTOFCONTEXT = 0x0000
lock = threading.Lock()
recent = collections.deque()          # (t, info)
known = set(psutil.pids())


def write(rec):
    rec["ts"] = time.strftime("%Y-%m-%d %H:%M:%S") + ("%.3f" % (time.time() % 1))[1:]
    with lock, open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def describe(pid, depth=4):
    out = []
    try:
        p = psutil.Process(pid)
        for _ in range(depth):
            try:
                out.append({"pid": p.pid, "name": p.name(),
                            "cmd": " ".join(p.cmdline())[:400]})
            except Exception as e:
                out.append({"pid": p.pid, "err": type(e).__name__})
            p = p.parent()
            if p is None:
                break
    except Exception as e:
        out.append({"pid": pid, "err": type(e).__name__})
    return out


def poller():
    global known
    while True:
        try:
            now = set(psutil.pids())
            for pid in now - known:
                info = describe(pid, 4)
                recent.append((time.time(), info))
            known = now
            cut = time.time() - 10
            while recent and recent[0][0] < cut:
                recent.popleft()
        except Exception:
            pass
        time.sleep(0.04)


WinEventProc = ctypes.WINFUNCTYPE(None, W.HANDLE, W.DWORD, W.HWND, W.LONG, W.LONG, W.DWORD, W.DWORD)


def cls_of(hwnd):
    b = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, b, 256)
    return b.value


def title_of(hwnd):
    b = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, b, 512)
    return b.value


def on_event(hook, event, hwnd, idObject, idChild, thread, t):
    if idObject != 0 or not hwnd:
        return
    try:
        c = cls_of(hwnd)
        if c not in CONSOLE_CLASSES:
            return
        if user32.GetParent(hwnd):
            return
        pid = W.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        visible = bool(user32.IsWindowVisible(hwnd))
        r = W.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        rec = {"ev": "show" if event == EVENT_OBJECT_SHOW else "create", "class": c,
               "title": title_of(hwnd), "visible": visible,
               "rect": [r.left, r.top, r.right, r.bottom],
               "owner": describe(pid.value, 5)}
        cut = time.time() - 4
        rec["new_procs_4s"] = [i for (tt, i) in list(recent) if tt >= cut]
        write(rec)
    except Exception as e:
        write({"ev": "error", "err": repr(e)})


cb = WinEventProc(on_event)
threading.Thread(target=poller, daemon=True).start()
h1 = user32.SetWinEventHook(EVENT_OBJECT_SHOW, EVENT_OBJECT_SHOW, 0, cb, 0, 0, WINEVENT_OUTOFCONTEXT)
write({"ev": "start", "hook": bool(h1)})
msg = W.MSG()
while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) != 0:
    user32.TranslateMessage(ctypes.byref(msg))
    user32.DispatchMessageW(ctypes.byref(msg))
