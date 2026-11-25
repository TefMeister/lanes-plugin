#!/usr/bin/env python3
"""backstage.py - Backstage-o-matiC: games run OFF the screen while you use the PC (2026-11-25, extra `backstage`).

Tefa, 2026-11-25: "you really need to learn how to work on the background so i can use the pc at the same time";
"the games also have to start at the background already and not take over the screen, even for launch".

    python backstage.py launch --watch re4.exe[,other.exe] [--log FILE] [--pad] -- <program, file or steam:// link> [args]
                                      start the watcher (and the kept pad with --pad), then the game; returns at once
    python backstage.py watch --watch NAMES | --pid PID [--log FILE] [--max-s S]
                                      the watcher itself: every window of those programs is put BEHIND your windows
                                      the moment Windows shows it (it stays on the monitor; `backstage_place =
                                      off_screen` in lanes.conf parks it past the edge of all screens instead; never
                                      minimized: a minimized game stops drawing), and the keyboard focus is handed
                                      back to your window whenever one of them takes it. Ends when the programs have
                                      closed (or after --max-s).
    python backstage.py away|back <pid>            move a program's windows off / back on the screen, no focus change
    python backstage.py shot <pid> <out.png> [--class C]   a picture of the window itself, wherever it is (PrintWindow)
    python backstage.py key <pid> <key> [--class C]        one key sent as window messages (no focus, no real key)
    python backstage.py pad serve | pad send <words>       the kept pretend Xbox pad (see PAD below)
    python backstage.py report [LOG]                       the flash log in plain words (default: the newest)

WHERE THE GAME GOES (Tefa, 2026-11-25: "behind as default, off screen as option"): `backstage_place = behind` (the
default) leaves the game on the monitor under your windows, so a glance at it is possible (it comes to the front only
when YOU click it in the taskbar or on its window, or Alt+Tab to it, and is then left alone until you click away); `off_screen` parks it past
the left edge of all screens, so nothing of it can show. Both keep it running and give its pictures.

THE FLASH LOG (JSON lines, one per event): "shown" (a window of the game appeared; `on_screen_ms` = how long until it
was put behind / moved away), "focus" (the game took the keyboard focus; `back_ms` = until it was handed back),
"seen_on_screen" (found on top of your window, or on the screen in off_screen, by the half-second check: an event that
was missed, or the game raised itself), "end". `report` turns it into lines like
"re4.exe: 1 time(s) on top of your windows, longest 12 ms; took the focus 1 time(s), always given back".

PAD. Some games pause or complain when their pad disappears (The Darkness; Fallout: "controller disconnected"), and some
only look for pads at start-up, so the pad is plugged in BEFORE the game starts and kept until the run ends. `pad send`
writes one line to the pad's command file: a button (a b x y start back lb rb up down left right ls rs) = a 150 ms tap;
`stick X Y SECONDS` / `rstick X Y SECONDS` hold a stick (-1..1); `lt` / `rt` pull a trigger; `quit` unplugs it.
Needs the ViGEmBus driver and the Python package vgamepad (docs/TOOLS.md).
"""
import argparse
import ctypes
import ctypes.wintypes as w
import glob
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "lanes")
OUT_DIR = os.path.join(STATE_DIR, "backstage")
PAD_CMD = os.path.join(OUT_DIR, "pad_cmd.txt")
PAD_LOG = os.path.join(OUT_DIR, "pad.log")
PAD_PID = os.path.join(OUT_DIR, "pad.pid")

AWAY_GAP_PX = 200           # how far past the left edge of all screens a window is parked (off_screen)
BEHIND, OFF_SCREEN = "behind", "off_screen"
PILE_WALK_MAX = 5000        # windows walked up the pile when asking "is the game above yours?"
CHECK_EVERY_S = 0.5         # the safety check that finds a window an event did not report
OTHERS_FORGET_S = 10.0      # a process found not to be ours is asked again after this long
USER_INPUT_MS = 700         # real input this recent, with the pointer on the game or the taskbar (or Alt held) = YOU
                            # chose the game (Tefa 2026-11-25: "it only becomes the main thing if i actually click on it
                            # in the taskbar or the window header")
OWN_INPUT_MS = 400          # our own Alt tap (give_front) is never taken for yours
GONE_GRACE_S = 8.0          # the programs must stay gone this long before the watcher ends (a launcher hands over)
DEFAULT_MAX_S = 6 * 3600    # a watcher never outlives a long session
TAP_S = 0.15                # a pad button or a posted key is held this long
PAD_PLUG_S = 2.0            # a freshly plugged pad is seen by a game after about this long
PAD_POLL_S = 0.05

EVENT_SYSTEM_FOREGROUND = 0x0003
EVENT_OBJECT_SHOW = 0x8002
EVENT_OBJECT_LOCATIONCHANGE = 0x800B
WINEVENT_OUTOFCONTEXT, WINEVENT_SKIPOWNPROCESS = 0x0000, 0x0002
OBJID_WINDOW = 0
SWP_NOSIZE, SWP_NOACTIVATE, SWP_NOOWNERZORDER = 0x0001, 0x0010, 0x0200
HWND_BOTTOM = 1
SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 76, 77, 78, 79
GW_OWNER, GW_HWNDPREV = 4, 3
SWP_NOMOVE = 0x0002
WM_KEYDOWN, WM_KEYUP, WM_CLOSE = 0x0100, 0x0101, 0x0010
VK_MENU = 0x12
KEYEVENTF_KEYUP = 0x0002
PW_CLIENT_FULL = 3          # PW_CLIENTONLY | PW_RENDERFULLCONTENT: also a window drawn by the graphics card
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PM_REMOVE = 0x0001

u = ctypes.windll.user32 if os.name == "nt" else None
k32 = ctypes.windll.kernel32 if os.name == "nt" else None
g32 = ctypes.windll.gdi32 if os.name == "nt" else None
if u:
    u.GetForegroundWindow.restype = w.HWND
    u.WindowFromPoint.restype = w.HWND
    u.GetWindow.restype = w.HWND
    u.GetAncestor.restype = w.HWND
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)      # real pixels, or a 200 % screen gives quarter pictures
    except Exception:
        pass

# Keys that can be sent as window messages: name -> (virtual key, scan code, extended)
KEYS = {"insert": (0x2D, 0x52, True), "enter": (0x0D, 0x1C, False), "esc": (0x1B, 0x01, False),
        "space": (0x20, 0x39, False), "tab": (0x09, 0x0F, False), "up": (0x26, 0x48, True),
        "down": (0x28, 0x50, True), "left": (0x25, 0x4B, True), "right": (0x27, 0x4D, True),
        "backspace": (0x08, 0x0E, False), "f1": (0x70, 0x3B, False), "grave": (0xC0, 0x29, False)}
for _c in "abcdefghijklmnopqrstuvwxyz":
    KEYS[_c] = (ord(_c.upper()), 0, False)
for _n in range(10):
    KEYS[str(_n)] = (0x30 + _n, 0, False)
    KEYS["num%d" % _n] = (0x60 + _n, 0, False)


def is_on():
    """The extra `backstage` (tools/features.py). A tool that cannot read it counts it off."""
    try:
        sys.path.insert(0, os.path.dirname(HERE))
        import features
        return features.is_on("backstage")
    except Exception:
        return False


# ---------------------------------------------------------------------------------------------------------------------
# WINDOWS AND PROGRAMS

def pid_of_window(h):
    p = w.DWORD()
    u.GetWindowThreadProcessId(h, ctypes.byref(p))
    return p.value


def exe_of_pid(pid):
    hp = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not hp:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = w.DWORD(1024)
        if k32.QueryFullProcessImageNameW(hp, 0, buf, ctypes.byref(n)):
            return os.path.basename(buf.value).lower()
        return ""
    finally:
        k32.CloseHandle(hp)


def windows_of(pid, cls=None):
    out = []

    @ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    def cb(h, _):
        if pid_of_window(h) == pid and u.IsWindowVisible(h):
            if cls:
                c = ctypes.create_unicode_buffer(64)
                u.GetClassNameW(h, c, 64)
                if c.value != cls:
                    return True
            out.append(h)
        return True
    u.EnumWindows(cb, 0)
    return out


def main_window(pid, cls=None):
    """The program's biggest visible top-level window (a game has one; a splash or dialog is smaller)."""
    best, area = None, -1
    for h in windows_of(pid, cls):
        r = w.RECT()
        u.GetWindowRect(h, ctypes.byref(r))
        a = (r.right - r.left) * (r.bottom - r.top)
        if a > area:
            best, area = h, a
    return best


def title_of(h):
    b = ctypes.create_unicode_buffer(256)
    u.GetWindowTextW(h, b, 256)
    return b.value


def screens():
    """left, top, right, bottom of all screens together"""
    x, y = u.GetSystemMetrics(SM_XVIRTUALSCREEN), u.GetSystemMetrics(SM_YVIRTUALSCREEN)
    return x, y, x + u.GetSystemMetrics(SM_CXVIRTUALSCREEN), y + u.GetSystemMetrics(SM_CYVIRTUALSCREEN)


def on_screen(h):
    r = w.RECT()
    u.GetWindowRect(h, ctypes.byref(r))
    left, top, right, bottom = screens()
    return r.right > left and r.left < right and r.bottom > top and r.top < bottom and r.right > r.left


def place():
    """behind (the default) or off_screen: BACKSTAGE_PLACE, else `backstage_place` in lanes.conf"""
    v = os.environ.get("BACKSTAGE_PLACE")
    if not v:
        try:
            sys.path.insert(0, os.path.dirname(HERE))
            import features
            v = features.conf_value("backstage_place")
        except Exception:
            v = None
    v = (v or "").strip().lower().replace("-", "_").replace(" ", "_")
    return OFF_SCREEN if v in ("off_screen", "offscreen", "off", "away") else BEHIND


def above(h, other):
    """True when window h lies above window `other` in the pile of windows (so it may cover it)"""
    if not h or not other or not u.IsWindow(other):
        return False
    x, n = u.GetWindow(other, GW_HWNDPREV), 0
    while x and n < PILE_WALK_MAX:
        if x == h:
            return True
        x, n = u.GetWindow(x, GW_HWNDPREV), n + 1
    return False


def push_behind(h):
    """Put the window at the bottom of the pile: it stays on the monitor, under your windows, not activated."""
    u.SetWindowPos(h, HWND_BOTTOM, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER)


def move_away(h):
    """Park the window past the left edge of all screens, at the bottom of the pile, without activating it.
    Returns True when it moved."""
    if not on_screen(h) or u.IsIconic(h):
        return False
    r = w.RECT()
    u.GetWindowRect(h, ctypes.byref(r))
    x = screens()[0] - (r.right - r.left) - AWAY_GAP_PX
    u.SetWindowPos(h, HWND_BOTTOM, x, r.top, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER)
    return True


def bring_back(h):
    left, top, _r, _b = screens()
    u.SetWindowPos(h, HWND_BOTTOM, left + 40, top + 40, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER)


def user_chose(now_tick, last_input_tick, own_input_tick, pointer_on_game_or_taskbar, alt_down):
    """True when a focus change to the game was YOUR doing: real input a moment ago (not our own Alt tap), with the
    pointer on the game's window or the taskbar (a click there), or Alt held (Alt+Tab). Plain numbers, so it is tested
    without a desktop (tests/backstage_test.py)."""
    def since(a, b):                                      # b - a in ms, signed, across the 49-day tick wrap
        return ((b - a + 2 ** 31) & 0xFFFFFFFF) - 2 ** 31
    if not 0 <= since(last_input_tick, now_tick) <= USER_INPUT_MS:
        return False
    if own_input_tick and abs(since(own_input_tick, last_input_tick)) <= OWN_INPUT_MS:
        return False                                      # the last input was our own Alt tap
    return bool(pointer_on_game_or_taskbar or alt_down)


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", w.UINT), ("dwTime", w.DWORD)]


def you_chose(h):
    """user_chose() with this desktop's real readings, for the game's window h"""
    li = LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO), 0)
    if not u.GetLastInputInfo(ctypes.byref(li)):
        return False
    pt = w.POINT()
    u.GetCursorPos(ctypes.byref(pt))
    under = u.WindowFromPoint(pt)
    top = u.GetAncestor(under, 2) if under else None          # GA_ROOT
    cls = ctypes.create_unicode_buffer(64)
    if top:
        u.GetClassNameW(top, cls, 64)
    on_it = bool(top) and (top == h or pid_of_window(top) == pid_of_window(h) or
                           cls.value in ("Shell_TrayWnd", "Shell_SecondaryTrayWnd", "XamlExplorerHostIslandWindow",
                                         "TaskListThumbnailWnd", "MultitaskingViewFrame", "ForegroundStaging"))
    alt = bool(u.GetAsyncKeyState(VK_MENU) & 0x8000)
    return user_chose(k32.GetTickCount(), li.dwTime, _own_input_tick, on_it, alt)


def hold_file(pid):
    return os.path.join(OUT_DIR, "hold-%d" % pid)


def hold(pid, on):
    """Tell the watcher to leave this program's windows where they are (a step that needs the real mouse brings the
    window back on the screen for a moment), or to look after them again."""
    os.makedirs(OUT_DIR, exist_ok=True)
    if on:
        open(hold_file(pid), "w").close()
    else:
        try:
            os.remove(hold_file(pid))
        except OSError:
            pass


def held(pid):
    return os.path.exists(hold_file(pid))


_own_input_tick = 0


def give_front(h):
    """Hand the keyboard focus to window h. Windows lets a background program do this only right after a key event of
    its own, so a lone Alt press and release goes first (the usual way; it reaches no menu)."""
    global _own_input_tick
    if not h or not u.IsWindow(h):
        return False
    _own_input_tick = k32.GetTickCount()
    u.keybd_event(VK_MENU, 0, 0, 0)
    u.SetForegroundWindow(h)
    u.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    return u.GetForegroundWindow() == h


# ---------------------------------------------------------------------------------------------------------------------
# THE WATCHER

class Watcher:
    def __init__(self, names, pid, log_path):
        self.names = {n.strip().lower() for n in names if n.strip()}
        self.pid = pid
        self.log_path = log_path
        self.t0 = time.time()
        self.owner = u.GetForegroundWindow()          # your window: it gets the focus back
        self.known = {}                               # pid -> exe of a program we look after
        self.others = {}                              # pid -> when it was found NOT to be one (forgotten after a while:
                                                      # a launcher's process number can be given to the game later)
        self.moved = set()
        self.seen_any = False
        self.gone_since = None
        self.last_refused = 0.0
        self.place = place()
        self.picked = set()                           # pids of games YOU brought to the front: left alone until you leave
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        self.log = open(log_path, "a", encoding="utf-8")
        self.write("start", watch=sorted(self.names) or None, pid=pid, place=place())

    def write(self, event, **fields):
        fields = {k: v for k, v in fields.items() if v is not None}
        self.log.write(json.dumps(dict(t=round(time.time() - self.t0, 3), event=event, **fields)) + "\n")
        self.log.flush()

    def ours(self, pid):
        """the program name when this process is one we look after, else None (both remembered: a window that moves
        sends many events, and asking Windows for a program's name each time would be slow)"""
        if not pid:
            return None
        if pid in self.known:
            return self.known[pid]
        if pid in self.others and time.time() - self.others[pid] < OTHERS_FORGET_S:
            return None
        exe = exe_of_pid(pid)
        if (self.pid and pid == self.pid) or (exe and exe in self.names):
            self.known[pid] = exe or str(pid)
            self.seen_any = True
            return self.known[pid]
        self.others[pid] = time.time()
        return None

    def handle_window(self, h, how, shown_at=None):
        if not h or not u.IsWindowVisible(h):
            return
        pid = pid_of_window(h)
        exe = self.ours(pid)
        if not exe or held(pid):
            return
        start = shown_at or time.time()
        first = int(h) not in self.moved
        if self.place == OFF_SCREEN:
            changed = move_away(h)
        elif how == "moved":
            return                                        # behind: where the window sits on the monitor is its own
        else:
            changed = first or above(h, self.owner)       # a new window, or one that came up over yours
            if changed:
                push_behind(h)
        if changed:
            self.moved.add(int(h))
            self.write(how if first else "back_on_screen", exe=exe, window=int(h), title=title_of(h)[:60],
                       on_screen_ms=round((time.time() - start) * 1000, 1))

    def handle_focus(self, h, at):
        if not h:
            return
        pid = pid_of_window(h)
        exe = self.ours(pid)
        if not exe:
            self.owner = h                                # the window you are using now
            if self.picked:                               # you went back to your own windows: the game is ours again
                self.picked.clear()
                self.write("you_left", window=int(h))
            return
        if held(pid):                                     # a tool gave it the focus on purpose, for one step
            return
        if pid in self.picked:
            return
        if you_chose(h):                                  # your click on it (taskbar, window) or your Alt+Tab
            self.picked.add(pid)
            self.write("you_picked", exe=exe)
            return
        ok = give_front(self.owner)
        if self.place == BEHIND:
            push_behind(h)
        if ok or time.time() - self.last_refused > 1.0:   # a refusal is retried every check; noted once a second
            self.write("focus", exe=exe, given_back=ok, back_ms=round((time.time() - at) * 1000, 1))
        if not ok:
            self.last_refused = time.time()

    def sweep(self):
        """the safety check: any window of ours on top of yours (behind) or on the screen (off_screen) that an event
        did not report, or that the game raised or moved back itself"""
        @ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
        def cb(h, _):
            pid = pid_of_window(h)
            if u.IsWindowVisible(h) and self.ours(pid) and pid not in self.picked:
                if (on_screen(h) if self.place == OFF_SCREEN else above(h, self.owner)):
                    self.handle_window(h, "seen_on_screen")
            return True
        u.EnumWindows(cb, 0)
        fg = u.GetForegroundWindow()
        if fg and self.ours(pid_of_window(fg)):
            self.handle_focus(fg, time.time())

    def alive(self):
        if self.pid:
            return bool(exe_of_pid(self.pid)) or bool(windows_of(self.pid))
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.lower()
        return any('"%s"' % n in out for n in self.names)

    def run(self, max_s):
        WinEventProc = ctypes.WINFUNCTYPE(None, w.HANDLE, w.DWORD, w.HWND, w.LONG, w.LONG, w.DWORD, w.DWORD)

        def on_event(_hook, event, h, id_object, _child, _thread, _ms):
            if id_object != OBJID_WINDOW or not h:
                return
            now = time.time()
            try:
                if event == EVENT_SYSTEM_FOREGROUND:
                    self.handle_focus(h, now)
                elif event in (EVENT_OBJECT_SHOW, EVENT_OBJECT_LOCATIONCHANGE) and u.GetAncestor(h, 2) == h:
                    self.handle_window(h, "shown" if event == EVENT_OBJECT_SHOW else "moved", now)
            except Exception as e:                       # never let one odd window end the watcher
                self.write("error", what=str(e)[:200])
        proc = WinEventProc(on_event)
        flags = WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS
        hooks = [u.SetWinEventHook(EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND, 0, proc, 0, 0, flags),
                 u.SetWinEventHook(EVENT_OBJECT_SHOW, EVENT_OBJECT_SHOW, 0, proc, 0, 0, flags),
                 u.SetWinEventHook(EVENT_OBJECT_LOCATIONCHANGE, EVENT_OBJECT_LOCATIONCHANGE, 0, proc, 0, 0, flags)]
        msg = w.MSG()
        next_check = 0.0
        end = self.t0 + max_s
        why = "time limit"
        try:
            while time.time() < end:
                while u.PeekMessageW(ctypes.byref(msg), 0, 0, 0, PM_REMOVE):
                    u.TranslateMessage(ctypes.byref(msg))
                    u.DispatchMessageW(ctypes.byref(msg))
                if time.time() >= next_check:
                    next_check = time.time() + CHECK_EVERY_S
                    self.sweep()
                    if self.seen_any or self.pid:
                        if self.alive():
                            self.gone_since = None
                        elif self.gone_since is None:
                            self.gone_since = time.time()
                        elif time.time() - self.gone_since > GONE_GRACE_S:
                            why = "the game closed"
                            break
                u.MsgWaitForMultipleObjects(0, None, False, 20, 0x04FF)   # QS_ALLINPUT: wake for any event
        finally:
            for hk in hooks:
                if hk:
                    u.UnhookWinEvent(hk)
            self.write("end", why=why, windows_moved=len(self.moved))
            self.log.close()


def new_log_path(names):
    os.makedirs(OUT_DIR, exist_ok=True)
    tag = (sorted(names)[0] if names else "pid").replace(".exe", "")
    return os.path.join(OUT_DIR, "flash-%s-%s.jsonl" % (time.strftime("%Y-%m-%d_%H-%M-%S"), tag))


def start_watch(names, log_path=None, max_s=DEFAULT_MAX_S, pid=None):
    """Start a watcher as its own hidden program; returns (process, log path). For other tools."""
    log_path = log_path or new_log_path(names)
    cmd = [sys.executable, os.path.abspath(__file__), "watch", "--log", log_path, "--max-s", str(max_s)]
    cmd += ["--pid", str(pid)] if pid else ["--watch", ",".join(names)]
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return p, log_path


# ---------------------------------------------------------------------------------------------------------------------
# PICTURES AND KEYS

def shot(h):
    """The window's own picture (PrintWindow), wherever it is and whatever covers it. None when Windows refuses or the
    window is minimized (a minimized window has nothing to give)."""
    from PIL import Image

    class BIH(ctypes.Structure):
        _fields_ = [("biSize", w.DWORD), ("biWidth", w.LONG), ("biHeight", w.LONG), ("biPlanes", w.WORD),
                    ("biBitCount", w.WORD), ("biCompression", w.DWORD), ("biSizeImage", w.DWORD),
                    ("biXPelsPerMeter", w.LONG), ("biYPelsPerMeter", w.LONG), ("biClrUsed", w.DWORD),
                    ("biClrImportant", w.DWORD)]
    if not h or u.IsIconic(h):
        return None
    r = w.RECT()
    u.GetClientRect(h, ctypes.byref(r))
    width, height = r.right, r.bottom
    if width <= 0 or height <= 0:
        return None
    hdc = u.GetDC(h)
    mdc = g32.CreateCompatibleDC(hdc)
    bmp = g32.CreateCompatibleBitmap(hdc, width, height)
    g32.SelectObject(mdc, bmp)
    ok = u.PrintWindow(h, mdc, PW_CLIENT_FULL)
    bi = BIH(ctypes.sizeof(BIH), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(width * height * 4)
    g32.GetDIBits(mdc, bmp, 0, height, buf, ctypes.byref(bi), 0)
    g32.DeleteObject(bmp)
    g32.DeleteDC(mdc)
    u.ReleaseDC(h, hdc)
    if not ok:
        return None
    return Image.frombuffer("RGB", (width, height), buf, "raw", "BGRX", 0, 1)


def post_key(h, name, hold_s=TAP_S):
    """One key as window messages to h: no focus, no real key. Reaches a game that reads its window's key messages,
    and REFramework's own menu key (Insert)."""
    vk, sc, ext = KEYS[name.lower()]
    sc = sc or u.MapVirtualKeyW(vk, 0)
    lp = 1 | (sc << 16) | ((1 << 24) if ext else 0)
    u.PostMessageW(h, WM_KEYDOWN, vk, lp)
    time.sleep(hold_s)
    u.PostMessageW(h, WM_KEYUP, vk, lp | (1 << 30) | (1 << 31))


# ---------------------------------------------------------------------------------------------------------------------
# THE KEPT PAD

def pad_send(words, cmd_file=PAD_CMD):
    os.makedirs(os.path.dirname(cmd_file), exist_ok=True)
    with open(cmd_file, "a", encoding="utf-8") as f:
        f.write(" ".join(words).strip() + "\n")


def pad_running():
    """True when a pad keeper's program still runs (its number is in pad.pid)."""
    try:
        pid = int(open(PAD_PID, encoding="utf-8").read().strip())
    except (OSError, ValueError):
        return False
    return bool(exe_of_pid(pid))


def pad_start():
    """Start a pad keeper as its own hidden program (no-op when one runs). For other tools."""
    if pad_running():
        return None
    return subprocess.Popen([sys.executable, os.path.abspath(__file__), "pad", "serve"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def pad_line(pad, words, buttons):
    """Carry out one command line on the pad. Returns False for quit."""
    if not words:
        return True
    cmd = words[0].lower()
    if cmd == "quit":
        return False
    if cmd in ("stick", "rstick"):
        x, y, secs = float(words[1]), float(words[2]), float(words[3])
        move = pad.left_joystick_float if cmd == "stick" else pad.right_joystick_float
        move(x, y); pad.update(); time.sleep(secs)
        move(0.0, 0.0); pad.update()
    elif cmd in ("lt", "rt"):
        secs = float(words[1]) if len(words) > 1 else TAP_S
        pull = pad.left_trigger_float if cmd == "lt" else pad.right_trigger_float
        pull(1.0); pad.update(); time.sleep(secs)
        pull(0.0); pad.update()
    elif cmd in buttons:
        secs = float(words[1]) if len(words) > 1 else TAP_S
        pad.press_button(buttons[cmd]); pad.update(); time.sleep(secs)
        pad.release_button(buttons[cmd]); pad.update()
    else:
        raise ValueError("unknown pad command: %s" % " ".join(words))
    return True


def pad_serve(cmd_file=PAD_CMD, pad=None, max_s=DEFAULT_MAX_S):
    if pad is None:
        import vgamepad as vg
        pad = vg.VX360Gamepad()
    import_buttons = getattr(pad, "BUTTONS", None)
    if import_buttons is None:
        import vgamepad as vg
        B = vg.XUSB_BUTTON
        import_buttons = {"a": B.XUSB_GAMEPAD_A, "b": B.XUSB_GAMEPAD_B, "x": B.XUSB_GAMEPAD_X,
                          "y": B.XUSB_GAMEPAD_Y, "start": B.XUSB_GAMEPAD_START, "back": B.XUSB_GAMEPAD_BACK,
                          "lb": B.XUSB_GAMEPAD_LEFT_SHOULDER, "rb": B.XUSB_GAMEPAD_RIGHT_SHOULDER,
                          "up": B.XUSB_GAMEPAD_DPAD_UP, "down": B.XUSB_GAMEPAD_DPAD_DOWN,
                          "left": B.XUSB_GAMEPAD_DPAD_LEFT, "right": B.XUSB_GAMEPAD_DPAD_RIGHT,
                          "ls": B.XUSB_GAMEPAD_LEFT_THUMB, "rs": B.XUSB_GAMEPAD_RIGHT_THUMB}
    os.makedirs(os.path.dirname(cmd_file), exist_ok=True)
    open(cmd_file, "w").close()
    if cmd_file == PAD_CMD:
        with open(PAD_PID, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    log = open(PAD_LOG if cmd_file == PAD_CMD else cmd_file + ".log", "a", encoding="utf-8")
    pad.update()
    log.write("plugged in %s\n" % time.strftime("%H:%M:%S")); log.flush()
    done, end = 0, time.time() + max_s
    while time.time() < end:
        try:
            lines = open(cmd_file, encoding="utf-8").read().splitlines()
        except OSError:
            lines = []
        for line in lines[done:]:
            done += 1
            try:
                if not pad_line(pad, line.split(), import_buttons):
                    log.write("quit\n"); log.close()
                    return
                log.write("%s done\n" % line)
            except Exception as e:
                log.write("%s FAILED: %s\n" % (line, e))
            log.flush()
        time.sleep(PAD_POLL_S)
    log.write("quit (time limit)\n"); log.close()


# ---------------------------------------------------------------------------------------------------------------------
# THE REPORT

def report_lines(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    by = {}
    for r in rows:
        if r["event"] in ("shown", "seen_on_screen", "back_on_screen", "focus"):
            by.setdefault(r.get("exe", "?"), []).append(r)
    out = []
    start = next((r for r in rows if r["event"] == "start"), {})
    where = "on the screen" if start.get("place") == OFF_SCREEN else "on top of your windows"
    for exe, rs in by.items():
        shown = [r for r in rs if r["event"] in ("shown", "seen_on_screen", "back_on_screen")]
        focus = [r for r in rs if r["event"] == "focus"]
        bits = []
        if shown:
            worst = max(r.get("on_screen_ms", 0) for r in shown)
            late = [r for r in shown if r["event"] == "seen_on_screen"]
            bits.append("%d time(s) %s, longest %d ms%s" % (len(shown), where, worst,
                        " (%d found by the half-second check, so up to half a second)" % len(late) if late else ""))
        if focus:
            bad = [r for r in focus if not r.get("given_back")]
            bits.append("took the focus %d time(s)%s" % (len(focus),
                        ", NOT given back %d time(s)" % len(bad) if bad else ", always given back"))
        out.append("%s: %s" % (exe, "; ".join(bits)))
    end = [r for r in rows if r["event"] == "end"]
    out.append("watch ended: %s" % (end[-1].get("why") if end else "still running (or cut off)"))
    return out or ["nothing of the game showed"]


def newest_log():
    logs = sorted(glob.glob(os.path.join(OUT_DIR, "flash-*.jsonl")), key=os.path.getmtime)
    return logs[-1] if logs else None


# ---------------------------------------------------------------------------------------------------------------------

def find_pid(name):
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq " + name, "/FO", "CSV", "/NH"], capture_output=True,
                         text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) > 1 and parts[0].lower() == name.lower():
            return int(parts[1])
    return None


def target_pid(s):
    return int(s) if s.isdigit() else find_pid(s)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="backstage.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("watch", "launch"):
        p = sub.add_parser(name)
        p.add_argument("--watch", default="", help="program names, comma-separated (re4.exe,ModOrganizer.exe)")
        p.add_argument("--pid", type=int)
        p.add_argument("--log")
        p.add_argument("--max-s", type=float, default=DEFAULT_MAX_S)
        if name == "launch":
            p.add_argument("--pad", action="store_true", help="plug the kept pad in before the game starts")
            p.add_argument("what", nargs=argparse.REMAINDER)
    for name in ("away", "back"):
        sub.add_parser(name).add_argument("target")
    p = sub.add_parser("shot"); p.add_argument("target"); p.add_argument("out"); p.add_argument("--class", dest="cls")
    p = sub.add_parser("key"); p.add_argument("target"); p.add_argument("key"); p.add_argument("--class", dest="cls")
    p = sub.add_parser("pad"); p.add_argument("words", nargs="+")
    p = sub.add_parser("report"); p.add_argument("log", nargs="?")
    a = ap.parse_args(argv)
    names = [n for n in a.watch.split(",") if n] if hasattr(a, "watch") else []

    if a.cmd == "watch":
        if not names and not a.pid:
            ap.error("give --watch NAMES or --pid PID")
        Watcher(names, a.pid, a.log or new_log_path(names)).run(a.max_s)
    elif a.cmd == "launch":
        what = [x for x in a.what if x != "--"]
        if not what or not names:
            ap.error("give --watch NAMES and, after --, what to start")
        if a.pad:
            pad_start()
            time.sleep(PAD_PLUG_S)
        _p, log = start_watch(names, a.log, a.max_s)
        time.sleep(0.5)                                   # the watcher's hooks are up before the game's first window
        target = what[0]
        if "://" in target or not os.path.isfile(target):
            os.startfile(target)                          # a steam:// link or a shortcut
        else:
            subprocess.Popen(what, cwd=os.path.dirname(os.path.abspath(target)))
        print("started; watching %s; flash log: %s" % (", ".join(names), log))
    elif a.cmd in ("away", "back"):
        pid = target_pid(a.target)
        for h in windows_of(pid) if pid else []:
            if a.cmd == "away":
                print("moved away" if move_away(h) else "already off the screen")
            else:
                bring_back(h); print("back on the screen")
    elif a.cmd == "shot":
        pid = target_pid(a.target)
        img = shot(main_window(pid, a.cls)) if pid else None
        if img is None:
            print("no picture (no window, minimized, or Windows refused)"); return 1
        img.save(a.out); print("saved %dx%d" % img.size)
    elif a.cmd == "key":
        pid = target_pid(a.target)
        h = main_window(pid, a.cls) if pid else None
        if not h:
            print("no window"); return 1
        post_key(h, a.key); print("sent", a.key)
    elif a.cmd == "pad":
        if a.words[0] == "serve":
            pad_serve()
        elif a.words[0] == "send":
            pad_send(a.words[1:])
        else:
            ap.error("pad serve | pad send <words>")
    elif a.cmd == "report":
        log = a.log or newest_log()
        if not log:
            print("no flash log yet"); return 1
        print("\n".join(report_lines(log)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
