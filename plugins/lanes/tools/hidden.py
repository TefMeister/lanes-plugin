"""hidden.py - the ONE way Lanes starts another program, so no black window ever flashes up on the desktop.

Why (0.125.1, 2026-11-26, Tefa: "plenty of black boxes popping up again every now and then and these cannot be in the
Lanes public builds"): a program with no console of its own (pythonw, or anything started DETACHED) that starts a
console program (git, gh, ffmpeg, powershell, tasklist, python.exe ...) makes Windows open a NEW, visible console
window for it. Every earlier fix (0.103.1, 0.123.1, the Workshop collector) flagged the one call that was seen; the
next new tool repeated the mistake (0.125.0: the jitter filer's ffmpeg cuts, 16 windows per filed headset run). So:

  * every process start in Lanes goes through this module (hidden.run / hidden.Popen / ...: the same arguments as
    subprocess). When this process has no console, the child is given a hidden one (CREATE_NO_WINDOW), and
    everything the child starts shares it. When this process has a console (a Claude window), nothing changes:
    the child shares it as before, its output still shows.
  * DETACHED_PROCESS is never passed on: it is swapped for CREATE_NO_WINDOW (the child still outlives us, but with
    a hidden console instead of none).
  * a background tool is started with hidden.background(): the console interpreter (python.exe, never pythonw)
    under a hidden console, so nothing under it can open a window even if a call forgets this module.
  * Windows' Startup folder gets a shortcut (hidden.startup_shortcut), never a .cmd (a .cmd opens a cmd window
    at every logon); the shortcut runs `pythonw hidden.py launch <script> ...`, which hands over to background().
  * a window that SHOULD show (a Claude window, OBS) passes visible=True.
The release refuses a version with a process start outside this module (tools/window-scan.py), and a short live
run watches for console windows (tools/tests/no_window_live.py).

    python hidden.py launch <script.py> [args...]     start a Python tool in the background, hidden (Startup uses it)
"""
import os
import subprocess
import sys

IS_WIN = os.name == "nt"
NO_WINDOW = 0x08000000          # CREATE_NO_WINDOW: a console the child can use, never shown
DETACHED = 0x00000008           # DETACHED_PROCESS: no console at all (its console children each get a visible one)
NEW_GROUP = 0x00000200          # CREATE_NEW_PROCESS_GROUP: Ctrl+C in a Claude window does not reach it
NEW_CONSOLE = 0x00000010        # CREATE_NEW_CONSOLE: a console window asked for on purpose (left alone)
HOP_ENV = "LANES_HIDDEN_HOP"    # set on the copy ensure_console() starts, so it never starts another


def has_console():
    """True when this process has a console its children can share (shown or hidden)."""
    if not IS_WIN:
        return True
    try:
        import ctypes
        # GetConsoleCP, not GetConsoleWindow: a hidden console (CREATE_NO_WINDOW) and the console of a Claude tool
        # call have no window, but they are consoles; only "no console at all" (pythonw, DETACHED) answers 0
        return bool(ctypes.windll.kernel32.GetConsoleCP())
    except Exception:
        return False


def flags(kw):
    """the keyword arguments with Windows' creation flags made safe; visible=True leaves them as they are"""
    visible = kw.pop("visible", False)
    if not IS_WIN or visible:
        return kw
    f = kw.get("creationflags", 0) or 0
    if f & NEW_CONSOLE:
        return kw
    if f & DETACHED:
        f = (f & ~DETACHED) | NO_WINDOW
    elif not has_console():
        f |= NO_WINDOW
    if f:
        kw["creationflags"] = f
    return kw


def run(*a, **kw):
    return subprocess.run(*a, **flags(kw))


def Popen(*a, **kw):  # noqa: N802 (the same name as subprocess.Popen, so a call reads the same)
    return subprocess.Popen(*a, **flags(kw))


def call(*a, **kw):
    return subprocess.call(*a, **flags(kw))


def check_call(*a, **kw):
    return subprocess.check_call(*a, **flags(kw))


def check_output(*a, **kw):
    return subprocess.check_output(*a, **flags(kw))


def python_exe():
    """the console interpreter beside this one (python.exe even when this is pythonw.exe)"""
    d, name = os.path.split(sys.executable)
    if name.lower() == "pythonw.exe":
        cand = os.path.join(d, "python.exe")
        if os.path.isfile(cand):
            return cand
    return sys.executable


def pythonw_exe():
    """the window-less interpreter, for a Startup shortcut's first hop only (it hands over to python.exe at once)"""
    d = os.path.dirname(sys.executable)
    cand = os.path.join(d, "pythonw.exe")
    return cand if os.path.isfile(cand) else sys.executable


def background(argv, **kw):
    """start a long-running tool that outlives this one, under a hidden console its children share.
    argv: [script.py, args...] (run with python.exe) or a full command line starting with a program."""
    argv = list(argv)
    if argv and argv[0].lower().endswith(".py"):
        argv = [python_exe()] + argv
    elif argv and os.path.basename(argv[0]).lower() == "pythonw.exe":
        argv[0] = python_exe()
    for k in ("stdin", "stdout", "stderr"):
        kw.setdefault(k, subprocess.DEVNULL)
    kw.setdefault("close_fds", True)
    if IS_WIN:
        kw["creationflags"] = ((kw.get("creationflags", 0) or 0) & ~DETACHED) | NO_WINDOW | NEW_GROUP
    else:
        kw.setdefault("start_new_session", True)
    return subprocess.Popen(argv, **kw)


def ensure_console(argv=None):
    """call first thing in a long-running background tool: when it was started with no console at all (pythonw, an
    old Startup entry, DETACHED), start it again under a hidden console and end this copy. Returns only when this
    copy has a console (or is not on Windows)."""
    if not IS_WIN or has_console():
        os.environ.pop(HOP_ENV, None)   # what this copy starts may hop again
        return
    if os.environ.get(HOP_ENV) or os.path.basename(python_exe()).lower() == "pythonw.exe":
        return                          # one hop only, and never without a console interpreter to hop to
    env = dict(os.environ, **{HOP_ENV: "1"})
    background([os.path.abspath(sys.argv[0])] + list(sys.argv[1:] if argv is None else argv), env=env)
    sys.exit(0)


def startup_shortcut(path, script, args=(), description=""):
    """write a Windows Startup shortcut that starts `script args` in the background with no window.
    Returns True when the shortcut is there."""
    if not IS_WIN:
        return False
    me = os.path.abspath(__file__)
    arguments = " ".join('"%s"' % x for x in [me, "launch", os.path.abspath(script)] + list(args))
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:HID_LNK);$s.TargetPath=$env:HID_PY;"
          "$s.Arguments=$env:HID_ARGS;$s.WindowStyle=7;$s.Description=$env:HID_DESC;$s.Save()")
    env = dict(os.environ, HID_LNK=path, HID_PY=pythonw_exe(), HID_ARGS=arguments, HID_DESC=description or "Lanes")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], env=env, capture_output=True,
        creationflags=NO_WINDOW)
    return os.path.isfile(path)


def startup_dir():
    return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Microsoft", "Windows", "Start Menu",
                        "Programs", "Startup")


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) >= 2 and a[0] == "launch":
        background(a[1:])
        sys.exit(0)
    print(__doc__.strip().splitlines()[-1].strip())
    sys.exit(2)
