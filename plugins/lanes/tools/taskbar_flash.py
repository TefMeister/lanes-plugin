"""taskbar_flash.py - make the terminal's taskbar button blink when Claude finishes a reply or needs an answer.

A hook runs in a hidden console of its own, so a plain bell goes nowhere. This walks up the processes that started
it, attaches to the first one that has the real terminal (the Claude Code session), and writes one bell character
there. Windows Terminal, with "bellStyle": "taskbar", turns that bell into a blinking taskbar button for the right
window. Falls back to blinking the Windows Terminal window directly. Never fails the hook: exit 0 always.
"""
import ctypes
import ctypes.wintypes as w
import os
import sys

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
u32 = ctypes.WinDLL("user32", use_last_error=True)

# Windows' own numbers, named (they never change between Windows versions)
MAX_PATH = 260                 # the longest program name a process list entry holds
TH32CS_SNAPPROCESS = 2         # "list every process"
GENERIC_WRITE = 0x40000000     # open the terminal for writing
SHARE_READ_WRITE = 3           # let the session keep using it meanwhile
OPEN_EXISTING = 3              # the terminal is already there
FLASHW_TRAY = 2                # blink the taskbar button
FLASHW_TIMERNOFG = 12          # ... until the window comes to the front


class PE(ctypes.Structure):
    _fields_ = [("dwSize", w.DWORD), ("cntUsage", w.DWORD), ("th32ProcessID", w.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", w.DWORD), ("cntThreads", w.DWORD),
                ("th32ParentProcessID", w.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", w.DWORD),
                ("szExeFile", ctypes.c_wchar * MAX_PATH)]


def processes():
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    out = {}
    e = PE()
    e.dwSize = ctypes.sizeof(PE)
    ok = k32.Process32FirstW(snap, ctypes.byref(e))
    while ok:
        out[e.th32ProcessID] = (e.th32ParentProcessID, e.szExeFile.lower())
        ok = k32.Process32NextW(snap, ctypes.byref(e))
    k32.CloseHandle(snap)
    return out


def ancestors():
    procs = processes()
    pid, seen = os.getpid(), set()
    while pid in procs and pid not in seen:
        seen.add(pid)
        pid = procs[pid][0]
        if pid in procs:
            yield pid, procs[pid][1]


def bell_into_terminal(chain):
    for pid, exe in chain:
        if exe in ("windowsterminal.exe", "explorer.exe"):
            return False
        k32.FreeConsole()
        if not k32.AttachConsole(pid):
            continue
        if not k32.GetConsoleWindow():
            continue                       # another hidden console, keep climbing
        h = k32.CreateFileW("CONOUT$", GENERIC_WRITE, SHARE_READ_WRITE, None, OPEN_EXISTING, 0, None)
        if h in (0, -1, ctypes.c_void_p(-1).value):
            continue
        n = w.DWORD()
        ok = k32.WriteConsoleW(h, "\a", 1, ctypes.byref(n), None)
        k32.CloseHandle(h)
        k32.FreeConsole()
        return bool(ok)
    return False


class FLASHWINFO(ctypes.Structure):
    _fields_ = [("cbSize", w.UINT), ("hwnd", w.HWND), ("dwFlags", w.DWORD), ("uCount", w.UINT),
                ("dwTimeout", w.DWORD)]


def flash_terminal_window(chain):
    wt = [pid for pid, exe in chain if exe == "windowsterminal.exe"]
    if not wt:
        return False
    found = []

    @ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    def each(hwnd, _):
        p = w.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        cls = ctypes.create_unicode_buffer(64)
        u32.GetClassNameW(hwnd, cls, 64)
        if p.value == wt[0] and cls.value == "CASCADIA_HOSTING_WINDOW_CLASS" and u32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    u32.EnumWindows(each, 0)
    if len(found) != 1 or u32.GetForegroundWindow() == found[0]:
        return False                       # several windows: cannot tell which one, so blink none
    fi = FLASHWINFO(ctypes.sizeof(FLASHWINFO), found[0], FLASHW_TRAY | FLASHW_TIMERNOFG, 0, 0)
    return bool(u32.FlashWindowEx(ctypes.byref(fi)))


def terminal_settings():
    """Windows Terminal's settings files on this PC (store, preview and unpackaged installs)."""
    base = os.environ.get("LOCALAPPDATA", "")
    for rel in (r"Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json",
                r"Packages\Microsoft.WindowsTerminalPreview_8wekyb3d8bbwe\LocalState\settings.json",
                r"Microsoft\Windows Terminal\settings.json"):
        p = os.path.join(base, rel)
        if os.path.isfile(p):
            yield p


def bell_to_blink():
    """Once per PC: the terminal's bell blinks the taskbar button instead of beeping. A bellStyle the person set
    themselves, anywhere in the file, is left alone. The file is backed up beside itself first."""
    import re
    import shutil
    for p in terminal_settings():
        try:
            text = open(p, encoding="utf-8").read()
            if '"bellStyle"' in text:
                continue
            m = re.search(r'"defaults"\s*:\s*\{', text)
            if not m:
                continue
            rest = text[m.end():]
            if re.match(r"\s*\}", rest):          # an empty block: {}
                new = text[:m.end()] + '\n            "bellStyle": "taskbar"\n        ' + rest.lstrip()
            else:
                new = text[:m.end()] + '\n            "bellStyle": "taskbar",' + rest
            shutil.copy2(p, p + ".before-lanes-blink")
            open(p, "w", encoding="utf-8").write(new)
        except OSError:
            pass


def main():
    try:
        sys.stdin.read()                   # the hook's JSON; not needed
    except Exception:
        pass
    try:
        bell_to_blink()
        chain = list(ancestors())
        if not bell_into_terminal(chain):
            flash_terminal_window(chain)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
