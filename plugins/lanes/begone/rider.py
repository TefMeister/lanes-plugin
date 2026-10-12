r"""rider.py - the BeG0nE rider (Lanes 0.62.0): sits in the background, and the moment a VR session ends it files
every recording any BeG0nE tool made, turning millions of numbers into a short report. Idle, it costs one folder
look every few seconds and one process look every PROCESS_LOOK_EVERY_S.

    python rider.py start | stop | status
    python rider.py run                     the loop itself, in the foreground
    python rider.py install | uninstall     start with Windows for this user (Startup folder; no admin) / undo that
    python rider.py file <log> [--game <project>]    file one recording by hand

Was BeG0nE's camera-jitter/ride-along/ride.py, which knew one tool. This one reads every tool.json beside it, so a
new tool is filed without touching this file. Where reports go: begone_common.home(); raw recordings are read from
%LOCALAPPDATA%\BeG0nE\<log dir>\ and moved to done\ there (they stay on the PC that made them).

HOW IT KNOWS A VR SESSION IS ON, three ways (the 'never one method' rule): a recording growing in a tool's log
folder (the only one that produces data); SteamVR running; a windowed process with an OpenXR/OpenVR dll loaded.
"""
import ctypes
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import begone_common as bc  # noqa: E402

STATE = os.path.join(bc.LOCAL, "ride-state.json")
PID_FILE = os.path.join(bc.LOCAL, "ride.pid")          # the same file the old ride.py used, so one stops the other
RIDE_LOG = os.path.join(bc.LOCAL, "ride.log")
POLL_S = 5                      # how often the rider looks
SETTLE_S = 10                   # a recording that has not grown for this long is a finished session
PROCESS_LOOK_EVERY_S = 15       # how often the (dearer) process check runs
FILE_TIMEOUT_S = 600            # one filing may take this long (a two-hour session is a big log)
MIN_LOG_BYTES = 200             # a recording smaller than this never got past its header
STARTUP_CMD = os.path.join(os.path.expandvars("%APPDATA%"), r"Microsoft\Windows\Start Menu\Programs\Startup",
                           "BeG0nE-rider.cmd")
OLD_STARTUP_CMD = os.path.join(os.path.dirname(STARTUP_CMD), "BeG0nE-jitter-rider.cmd")
STEAMVR_EXES = ("vrserver.exe", "vrcompositor.exe", "vrmonitor.exe")
VR_DLLS = ("openxr_loader.dll", "openvr_api.dll")
DETACHED_PROCESS = 0x00000008


def say(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    try:
        os.makedirs(bc.LOCAL, exist_ok=True)
        with open(RIDE_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# ----- VR signals -----
def windowed_pids():
    import ctypes.wintypes as W
    u = ctypes.windll.user32
    pids = set()

    @ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    def cb(h, _):
        if u.IsWindowVisible(h):
            pid = W.DWORD()
            u.GetWindowThreadProcessId(h, ctypes.byref(pid))
            pids.add(pid.value)
        return True
    u.EnumWindows(cb, 0)
    pids.discard(os.getpid())
    return pids


def vr_processes():
    try:
        import psutil
    except ImportError:
        return False, []
    steam, loaded = False, []
    try:
        wp = windowed_pids()
    except Exception:
        wp = set()
    for p in psutil.process_iter(["pid", "name"]):
        name = (p.info["name"] or "").lower()
        if name in STEAMVR_EXES:
            steam = True
        if p.info["pid"] in wp:
            try:
                for m in p.memory_maps():
                    if os.path.basename(m.path).lower() in VR_DLLS:
                        loaded.append(p.info["name"]); break
            except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
                pass
    return steam, loaded


# ----- recordings -----
def recordings():
    """(tool, path, size, mtime) for every recording waiting in any tool's log folder."""
    out = []
    for t in bc.tools():
        d, ext = bc.log_dir(t), t.get("log_ext")
        if not d or not ext or not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            p = os.path.join(d, f)
            if f.endswith(ext) and os.path.isfile(p):
                out.append((t, p, os.path.getsize(p), os.path.getmtime(p)))
    return out


def log_head(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            first = f.readline()
        return dict(kv.split("=", 1) for kv in first.split()[1:] if "=" in kv)
    except OSError:
        return {}


def log_ended(path):
    try:
        with open(path, "rb") as f:
            f.seek(max(0, os.path.getsize(path) - 16))
            return b"#end" in f.read()
    except OSError:
        return False


def file_one(t, path, game=None):
    """Run the tool's filer on one recording; returns its one-line verdict."""
    cmd = [sys.executable, os.path.join(t["dir"], t["filer"]), "file", path, "--home", bc.tool_home(t)]
    if game:
        cmd += ["--game", game]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=FILE_TIMEOUT_S,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout).strip() else "filer failed")
    return r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "filed"


def write_state(**kw):
    os.makedirs(bc.LOCAL, exist_ok=True)
    kw["at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    kw["home"] = "set" if bc.home() != bc.DEFAULT_HOME else "default"
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(kw, f, indent=1)


def run():
    os.makedirs(bc.LOCAL, exist_ok=True)
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    say("rider up: " + ", ".join(t["name"] for t in bc.tools() if t.get("log_dir")))
    last_proc_look, steam, loaded, announced = 0, False, [], set()
    while True:
        now = time.time()
        if now - last_proc_look >= PROCESS_LOOK_EVERY_S:
            steam, loaded = vr_processes()
            last_proc_look = now
        live = []
        for t, p, size, mtime in recordings():
            head = log_head(p)
            game = head.get("game", "?")
            if p not in announced and size >= MIN_LOG_BYTES:
                say(f"VR SESSION: {game} is recording for {t['name']}"); announced.add(p)
            if size < MIN_LOG_BYTES and now - mtime > SETTLE_S:
                os.remove(p); continue          # never got going
            if log_ended(p) or now - mtime > SETTLE_S:
                try:
                    say(f"FILED {t['name']}: {file_one(t, p, game)}")
                except Exception as e:  # one bad recording must not stop the rider
                    say(f"could not file {os.path.basename(p)}: {e}")
                done = os.path.join(os.path.dirname(p), "done")
                os.makedirs(done, exist_ok=True)
                shutil.move(p, os.path.join(done, os.path.basename(p)))
                announced.discard(p)
            else:
                live.append(f"{game} ({t['short']})")
        write_state(vr=bool(live or steam or loaded), recording=live, steamvr=steam, vr_dll_in=loaded,
                    code=HERE)
        time.sleep(POLL_S)


# ----- start / stop -----
def running():
    """(pid, command line) of the rider running now, this one or the old ride.py; (None, '') if none."""
    try:
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
    except (OSError, ValueError):
        return None, ""
    try:
        import psutil
        cmd = " ".join(psutil.Process(pid).cmdline())
        return (pid, cmd) if ("rider.py" in cmd or "ride.py" in cmd) else (None, "")
    except Exception:
        return None, ""


def is_this(cmd):
    return os.path.normcase(os.path.abspath(__file__)) in os.path.normcase(cmd)


def start():
    pid, cmd = running()
    if pid and is_this(cmd):
        print("already running"); return True
    if pid:
        stop()                          # an older rider (another plugin version, or BeG0nE's ride.py): replace it
    os.makedirs(bc.LOCAL, exist_ok=True)
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    exe = pyw if os.path.exists(pyw) else sys.executable
    subprocess.Popen([exe, os.path.abspath(__file__), "run"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | DETACHED_PROCESS)
    for _ in range(10):
        time.sleep(0.5)
        pid, cmd = running()
        if pid and is_this(cmd):
            print("rider started"); return True
    print("rider did not start; see " + RIDE_LOG)
    return False


def stop():
    pid, _ = running()
    if not pid:
        print("not running"); return
    subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    try:
        os.remove(PID_FILE)
    except OSError:
        pass
    print("rider stopped")


def status():
    pid, cmd = running()
    print("rider:", (f"running (pid {pid})" + ("" if is_this(cmd) else ", an OLDER copy")) if pid else "not running")
    try:
        with open(STATE, encoding="utf-8") as f:
            st = json.load(f)
        print("VR now:", "YES" if st.get("vr") else "no", "| recording:", st.get("recording") or "none",
              "| SteamVR:", "up" if st.get("steamvr") else "down", "| at", st.get("at"))
    except (OSError, ValueError):
        print("no state yet")
    print("starts with Windows:", "yes" if os.path.exists(STARTUP_CMD) else "no")


def install():
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = sys.executable
    os.makedirs(os.path.dirname(STARTUP_CMD), exist_ok=True)
    with open(STARTUP_CMD, "w", encoding="utf-8") as f:
        f.write(f'@echo off\r\nstart "" "{pyw}" "{os.path.abspath(__file__)}" run\r\n')
    try:
        os.remove(OLD_STARTUP_CMD)
    except OSError:
        pass
    print("starts with Windows: yes")
    start()


def uninstall():
    for p in (STARTUP_CMD, OLD_STARTUP_CMD):
        try:
            os.remove(p)
        except OSError:
            pass
    stop()
    print("startup entry removed")


if __name__ == "__main__":
    a = sys.argv[1:]
    cmd = a[0] if a else ""
    if cmd == "run": run()
    elif cmd == "start": sys.exit(0 if start() else 1)
    elif cmd == "stop": stop()
    elif cmd == "status": status()
    elif cmd == "install": install()
    elif cmd == "uninstall": uninstall()
    elif cmd == "file" and len(a) >= 2:
        ext = os.path.splitext(a[1])[1]
        t = next((t for t in bc.tools() if t.get("log_ext") == ext), None)
        if not t:
            sys.exit(f"no tool records {ext} files")
        print(file_one(t, a[1], a[a.index("--game") + 1] if "--game" in a else None))
    else:
        sys.exit(__doc__)
