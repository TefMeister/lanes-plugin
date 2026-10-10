r"""obs-autorec.py - record every FULLSCREEN game by itself, with OBS, game window only (asked for by the maintainer,
2026-10-10: "when i play any game in fullscreen, it starts recording").

    pythonw obs-autorec.py            run the watcher (what the Startup shortcut does; silent, no window)
    python  obs-autorec.py install    put it in the Startup folder and start the watcher now
    python  obs-autorec.py uninstall  remove it from Startup and stop the watcher
    python  obs-autorec.py status     is it running, what it is recording, where the log is
    python  obs-autorec.py test       say what the watcher would do with the window in front right now

HOW IT DECIDES: every 2 s it looks at the window in front. It is "a game in fullscreen" when its program lives under a
game folder (every Steam library's steamapps\common, plus EXTRA_ROOTS) and the window covers its whole monitor. Then it
calls obs-rec.py start, which records ONLY that window (Windows Graphics Capture) and ONLY that program's sound - never
the screen, never the desktop (the standing rule). It stops when the game process ends, or when the game has had no
window for a minute (then obs-rec.py stop and done, which puts your own OBS profile back and closes OBS if the
watcher opened it). A recording some other tool started (a /lm session) is left alone.
PICTURE CHECK (2026-10-10: a game's first launch recorded 18 minutes of black): every 10 s while recording it
asks obs-rec.py check; black for 30 s with the game's window up = obs-rec.py repoint (same file keeps recording).
Files: obs-rec.py's folder per game (the game's own folder name), label "play": <REC_ROOT>\<game>\play_<date>_<time>.mp4.
Pause it without uninstalling: make the file %LOCALAPPDATA%\obs-autorec.off (delete it to resume).
Log: %LOCALAPPDATA%\obs-autorec.log.
"""
import ctypes, ctypes.wintypes as W, json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
OBS_REC = os.path.join(HERE, "obs-rec.py")
PYTHON = sys.executable
PYTHONW = os.path.join(os.path.dirname(PYTHON), "pythonw.exe")
LOCAL = os.path.expandvars("%LOCALAPPDATA%")
LOG = os.path.join(LOCAL, "obs-autorec.log")
OFF_FILE = os.path.join(LOCAL, "obs-autorec.off")
MY_STATE = os.path.join(LOCAL, "obs-autorec-state.json")     # what THIS watcher started
OBS_REC_STATE = os.path.join(LOCAL, "obs-rec-state.json")    # obs-rec.py's own state (any recording at all)
STEAM_ROOTS = [r"C:\Steam", r"C:\Program Files (x86)\Steam"]
EXTRA_ROOTS = []                       # more game folders: lanes.conf `game_roots = D:\Games; E:\Other`
SKIP_FOLDERS = {"steamvr", "steamworks shared", "steam controller configs"}
SKIP_EXES = {"vrserver.exe", "vrmonitor.exe", "vrcompositor.exe", "steam.exe", "steamwebhelper.exe", "crashhandler64.exe",
             "unitycrashhandler64.exe", "easyanticheat_eos_setup.exe"}
POLL_S = 2.0
GONE_S = 60.0          # no window from the game for this long = the game is over
LABEL = "play"
CHECK_S = 10.0        # how often the recording is checked for a real picture
BLACK_CHECKS = 3      # this many black checks in a row (30 s) = point the capture at the window again
PATH_CHARS = 520

u = ctypes.windll.user32; k = ctypes.windll.kernel32

def log(s):
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + s
    try:
        with open(LOG, "a", encoding="utf-8") as f: f.write(line + "\n")
    except OSError: pass
    if sys.stdout: print(line)

def steam_libraries():
    libs = []
    for root in STEAM_ROOTS:
        vdf = os.path.join(root, "steamapps", "libraryfolders.vdf")
        try:
            txt = open(vdf, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for p in re.findall(r'"path"\s+"([^"]+)"', txt):
            libs.append(os.path.join(p.replace("\\\\", "\\"), "steamapps", "common"))
    return libs

def lanes_conf(key, default=None):
    """A value from lanes.conf ($LANES_CONFIG, else ~/.claude/lanes.conf): `key = value` lines, # comments."""
    path = os.environ.get("LANES_CONFIG") or os.path.join(os.path.expanduser("~"), ".claude", "lanes.conf")
    try:
        for line in open(path, encoding="utf-8"):
            line = line.split("#", 1)[0].strip()
            if "=" in line:
                k, v = line.split("=", 1)
                if k.strip() == key and v.strip(): return os.path.expandvars(os.path.expanduser(v.strip()))
    except OSError:
        pass
    return default

def game_roots():
    seen, out = set(), []
    conf = [x.strip() for x in (lanes_conf("game_roots") or "").split(";") if x.strip()]
    for r in steam_libraries() + EXTRA_ROOTS + conf:
        n = os.path.normcase(os.path.normpath(r))
        if n not in seen and os.path.isdir(r): seen.add(n); out.append(os.path.normpath(r))
    return out

def exe_of(hwnd):
    pid = W.DWORD(); u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    hp = k.OpenProcess(0x1000, False, pid.value)
    if not hp: return pid.value, None
    buf = ctypes.create_unicode_buffer(PATH_CHARS); n = W.DWORD(PATH_CHARS)
    ok = k.QueryFullProcessImageNameW(hp, 0, buf, ctypes.byref(n)); k.CloseHandle(hp)
    return pid.value, (buf.value if ok else None)

class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", W.DWORD), ("rcMonitor", W.RECT), ("rcWork", W.RECT), ("dwFlags", W.DWORD)]

def covers_monitor(hwnd):
    r = W.RECT(); u.GetWindowRect(hwnd, ctypes.byref(r))
    mon = u.MonitorFromWindow(hwnd, 2)   # MONITOR_DEFAULTTONEAREST
    mi = MONITORINFO(); mi.cbSize = ctypes.sizeof(MONITORINFO)
    if not u.GetMonitorInfoW(mon, ctypes.byref(mi)): return False
    m = mi.rcMonitor
    return r.left <= m.left and r.top <= m.top and r.right >= m.right and r.bottom >= m.bottom

def game_of(path, roots):
    """the game's folder name if path lives under a game root (and is not a helper), else None"""
    if not path: return None
    p = os.path.normcase(os.path.normpath(path))
    if os.path.basename(p) in SKIP_EXES: return None
    for root in roots:
        rn = os.path.normcase(root) + os.sep
        if p.startswith(rn):
            game = p[len(rn):].split(os.sep)[0]
            if game in SKIP_FOLDERS: return None
            return path[len(root) + 1:].split(os.sep)[0]
    return None

def front_game(roots):
    """(pid, exe path, game folder) for the window in front when it is a fullscreen game, else None"""
    h = u.GetForegroundWindow()
    if not h or not u.IsWindowVisible(h): return None
    pid, path = exe_of(h)
    game = game_of(path, roots)
    if game is None or not covers_monitor(h): return None
    return pid, path, game

def pid_alive(pid):
    hp = k.OpenProcess(0x1000, False, pid)
    if not hp: return False
    code = W.DWORD(); ok = k.GetExitCodeProcess(hp, ctypes.byref(code)); k.CloseHandle(hp)
    return bool(ok) and code.value == 259   # STILL_ACTIVE

def windows_of_pid(pid):
    n = [0]
    @ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    def cb(h, _):
        if u.IsWindowVisible(h):
            p = W.DWORD(); u.GetWindowThreadProcessId(h, ctypes.byref(p))
            if p.value == pid: n[0] += 1
        return True
    u.EnumWindows(cb, 0)
    return n[0]

def load(p):
    try: return json.load(open(p))
    except (OSError, ValueError): return {}

def save(p, d): json.dump(d, open(p, "w"), indent=1)

def obs_rec(*args, quiet=False):
    r = subprocess.run([PYTHON, OBS_REC, *args], capture_output=True, text=True, creationflags=0x08000000)  # CREATE_NO_WINDOW
    out = (r.stdout + r.stderr).strip()
    if not quiet: log(f"obs-rec {' '.join(args)}: {out or 'ok'}")
    return r.returncode == 0, out

def safe_label(s):
    return re.sub(r"[^A-Za-z0-9 _.-]+", "", s).strip() or "game"

def watch():
    log(f"watcher up; game roots: {', '.join(game_roots()) or 'NONE'}")
    rec = load(MY_STATE).get("recording")     # survive a restart of the watcher mid-game
    gone_since = None
    last_check, blacks = time.time(), 0
    while True:
        try:
            if os.path.exists(OFF_FILE):
                time.sleep(POLL_S); continue
            roots = game_roots()
            if rec is None:
                other = load(OBS_REC_STATE).get("recording")
                fg = front_game(roots)
                if fg and not other:
                    pid, path, game = fg
                    ok, out = obs_rec("start", os.path.basename(path), LABEL, "--game", safe_label(game))
                    if ok:
                        rec = {"pid": pid, "exe": path, "game": game, "since": time.strftime("%H:%M:%S")}
                        save(MY_STATE, {"recording": rec}); gone_since = None; last_check = time.time(); blacks = 0
                        log(f"RECORDING {game} ({os.path.basename(path)}, pid {pid})")
                    else:
                        log(f"could not start for {game}; trying again in a minute")
                        time.sleep(60)
            else:
                alive = pid_alive(rec["pid"])
                has_window = alive and windows_of_pid(rec["pid"]) > 0
                if has_window: gone_since = None
                # 2026-10-10: a game's first launch recorded 18 minutes of black (the capture missed the window while
                # it was being set up). Check the picture every 10 s; black for 30 s with the game's window up = repoint.
                if has_window and time.time() - last_check >= CHECK_S:
                    last_check = time.time()
                    ok, out = obs_rec("check", quiet=True)
                    if ok and out.strip().startswith("BLACK"):
                        blacks += 1
                        if blacks >= BLACK_CHECKS:
                            ok2, out2 = obs_rec("repoint", os.path.basename(rec["exe"]))
                            log(f"{rec['game']}: no picture for {int(blacks * CHECK_S)} s -> {out2.strip() if ok2 else 'repoint FAILED: ' + out2.strip()}")
                            blacks = 0
                    elif ok:
                        if blacks: log(f"{rec['game']}: picture back ({out.strip()})")
                        blacks = 0
                elif gone_since is None: gone_since = time.time()
                if not alive or (gone_since and time.time() - gone_since > GONE_S):
                    log(f"{rec['game']} is over ({'process ended' if not alive else 'no window for a minute'}): stopping")
                    obs_rec("stop"); obs_rec("done")
                    rec = None; save(MY_STATE, {})
        except Exception as e:
            log(f"error: {e!r}")
        time.sleep(POLL_S)

STARTUP_LNK = os.path.join(os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"),
                           "OBS auto-record games.lnk")

def ps(cmd):
    return subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True,
                          creationflags=0x08000000)

def cmd_install():
    # a shortcut in the Startup folder (a logon scheduled task needs admin rights on this PC: "Access is denied")
    script = os.path.abspath(__file__)
    r = ps(f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{STARTUP_LNK}');"
           f"$s.TargetPath='{PYTHONW}';$s.Arguments='\"{script}\"';$s.WorkingDirectory='{HERE}';"
           f"$s.Description='Records games in fullscreen with OBS (game window only)';$s.Save()")
    print("startup shortcut:", "made" if os.path.exists(STARTUP_LNK) else ("FAILED " + r.stderr.strip()))
    if not watcher_running():
        subprocess.Popen([PYTHONW, script], cwd=HERE, creationflags=0x00000008)   # DETACHED_PROCESS
        time.sleep(2)
    cmd_status()

def cmd_uninstall():
    try: os.remove(STARTUP_LNK)
    except OSError: pass
    for pid in watcher_pids(): subprocess.run(["taskkill", "/f", "/pid", str(pid)], capture_output=True)
    print("removed: startup shortcut and running watcher")

def watcher_pids():
    """pids of running watchers (pythonw/python with this script and no command after it); wmic is gone on Windows 11"""
    ps = ("Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
          "ForEach-Object { \"$($_.ProcessId)|$($_.CommandLine)\" }")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                         creationflags=0x08000000).stdout
    pids = []
    for line in out.splitlines():
        pid, _, cmd = line.partition("|")
        if "obs-autorec.py" in cmd and cmd.strip().rstrip('"').endswith("obs-autorec.py") and pid.strip().isdigit():
            pids.append(int(pid))
    return pids

def watcher_running():
    return bool(watcher_pids())

def cmd_status():
    print("watcher:", "running" if watcher_running() else "NOT running")
    print("paused:", os.path.exists(OFF_FILE))
    print("starts at login:", "yes" if os.path.exists(STARTUP_LNK) else "NO")
    print("recording:", json.dumps(load(MY_STATE).get("recording")))
    print("game roots:", game_roots())
    print("log:", LOG)

def cmd_test():
    fg = front_game(game_roots())
    h = u.GetForegroundWindow(); pid, path = exe_of(h)
    print("window in front:", path, "| covers its monitor:", covers_monitor(h) if h else None)
    print("would record:", fg[2] if fg else "no (not a game in fullscreen)")

if __name__ == "__main__":
    a = sys.argv[1:]
    if not a: watch()
    elif a[0] == "install": cmd_install()
    elif a[0] == "uninstall": cmd_uninstall()
    elif a[0] == "status": cmd_status()
    elif a[0] == "test": cmd_test()
    else: sys.exit(__doc__)
