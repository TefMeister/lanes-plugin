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

RECORDING IN TANDEM (0.76.0, `begone_record = yes` in lanes.conf): the moment a log starts growing, the rider
starts tools/obs-rec.py on that game's window (and the OpenXR Simulator's preview, which obs-rec adds by itself),
unless something else is recording already. When the log ends it stops the recording first, then files, so the
report is cut at its jittery seconds straight away (camera-jitter/frames.py). Only the game's own windows are
recorded, never the screen.
0.80.0 (the maintainer: "please have BeG0nE tools automatically log everything and automatically start video
recording whenever we actually launch games in either openxr simulator or in vr"): ANY tool's log starts the
recording, not only the jitter log, and one recording covers the whole session: it stops when no tool's log is
growing any more. A log whose header names no process (the Lua recorders write pid=lua) is matched to the windowed
program that has an OpenXR / OpenVR dll loaded.
0.90.0: once an hour while nothing records, the videos nothing needs any more are taken off (video_tidy.py; its
frames and reports stay). Only with `begone_video_tidy` on.

HOW IT KNOWS A VR SESSION IS ON, three ways (the 'never one method' rule): a recording growing in a tool's log
folder (the only one that produces data); SteamVR running; a windowed process with an OpenXR/OpenVR dll loaded.
lanes-next (2026-11-04): the ALWAYS-ON COLLECTOR rides here too (collector.py): every launch of a project game, flat
or VR, with or without a session, is collected while it runs and shelved for Gold Digger when it closes. With
`collector` on (features.py). `start` also restarts a running rider whose code is older than the files on disk, so
a plugin update reaches the rider without anyone remembering to.
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
import collector  # noqa: E402
import autosave  # noqa: E402

STATE =os.path.join(bc.LOCAL, "ride-state.json")
PID_FILE = os.path.join(bc.LOCAL, "ride.pid")          # the same file the old ride.py used, so one stops the other
RIDE_LOG = os.path.join(bc.LOCAL, "ride.log")
POLL_S = 5                      # how often the rider looks
SETTLE_S = 10                   # a recording that has not grown for this long is a finished session
PROCESS_LOOK_EVERY_S = 15       # how often the (dearer) process check runs
FILE_TIMEOUT_S = 600            # one filing may take this long (a two-hour session is a big log)
MIN_LOG_BYTES = 200             # a recording smaller than this never got past its header
MOVE_TRIES = 3                  # a recording the game still holds is tried this often per pass ...
MOVE_WAIT_S = 2                 # ... this far apart, then left for the next pass (2026-11-04: it killed the rider twice)
UNKNOWN_GAME = "unknown-game"   # the folder name when no game can be told: never "?" (not allowed in a Windows name)
STARTUP_CMD = os.path.join(os.path.expandvars("%APPDATA%"), r"Microsoft\Windows\Start Menu\Programs\Startup",
                           "BeG0nE-rider.cmd")
OLD_STARTUP_CMD = os.path.join(os.path.dirname(STARTUP_CMD), "BeG0nE-jitter-rider.cmd")
STEAMVR_EXES = ("vrserver.exe", "vrcompositor.exe", "vrmonitor.exe")
VR_DLLS = ("openxr_loader.dll", "openvr_api.dll")
DETACHED_PROCESS = 0x00000008
REC_TOOL = os.path.join(os.path.dirname(HERE), "tools", "obs-rec.py")
REC_LABEL = "begone"            # recordings the rider makes are named begone_<date>_<time>.mp4
REC_TIMEOUT_S = 90              # obs-rec may have to start OBS first
REC_STATE = os.path.join(os.path.expandvars("%LOCALAPPDATA%"), "obs-rec-state.json")
TIDY_EVERY_S = 3600             # how often the videos nothing needs are taken off (video_tidy.py, 0.90.0)
TIDY_FIRST_S = 300              # the first tidy this long after the rider starts
FEATURES = os.path.join(os.path.dirname(HERE), "tools", "features.py")
SAVE_RETRY_S = 600              # reports left unsaved (git busy, offline) are tried again this often (autosave.py)


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


# ----- recording in tandem -----
def record_wanted():
    # "on" too since 0.90.0: features.py writes on/off, setup writes yes/no
    return bc.read_conf().get("begone_record", "").lower() in ("yes", "on", "true", "1") and os.path.isfile(REC_TOOL)


def recording_now():
    try:
        with open(REC_STATE, encoding="utf-8") as f:
            return bool(json.load(f).get("recording"))
    except (OSError, ValueError):
        return False


def exe_of(pid):
    try:
        import psutil
        return psutil.Process(int(pid)).name()
    except Exception:
        return None


def rec(*args):
    r = subprocess.run([sys.executable, REC_TOOL, *args], capture_output=True, text=True, timeout=REC_TIMEOUT_S,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    out = (r.stdout or r.stderr or "").strip().splitlines()
    return r.returncode == 0, (out[-1] if out else "")


def start_recording(head, game, vr_exes=()):
    """True when the rider started a recording for this session (and so must stop it)"""
    if not record_wanted() or recording_now():
        return False
    pid = head.get("pid", "")
    exe = exe_of(pid) if str(pid).isdigit() else None
    if not exe and vr_exes:
        exe = vr_exes[0]          # the Lua recorders write pid=lua: the windowed program with a VR dll loaded
    if not exe:
        say("not recording: could not tell which program is logging")
        return False
    try:
        ok, line = rec("start", exe, REC_LABEL, "--game", game)
    except Exception as e:
        ok, line = False, str(e)
    say(line if ok else "could not record: " + line)
    return ok


def stop_recording():
    try:
        ok, line = rec("stop")
        rec("done")
        say("recording stopped: " + line)
    except Exception as e:
        say(f"could not stop the recording: {e}")


_feature_cache = {}


def feature_on(name, every_s=60):
    """features.py is-on <name>, asked at most once a minute (the rider runs for days; lanes.conf can change)"""
    now = time.time()
    at, val = _feature_cache.get(name, (0, True))
    if now - at < every_s:
        return val
    try:
        r = subprocess.run([sys.executable, FEATURES, "is-on", name], capture_output=True, timeout=REC_TIMEOUT_S,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        val = r.returncode == 0
    except Exception:
        val = True   # never switch a feature off because the check itself failed
    _feature_cache[name] = (now, val)
    return val


def collect(now, loaded):
    """the always-on collector's turn, when `collector` is on; its errors never stop the rider"""
    if not feature_on("collector"):
        return []
    try:
        return collector.tick(now, loaded)
    except Exception as e:
        say(f"collector: {e}")
        return []


def tidy_videos():
    """take off the recordings nothing needs any more, when `begone_video_tidy` is on (0.90.0)"""
    try:
        if not feature_on("begone_video_tidy"):
            return
        import video_tidy
        for g, name, size, why in video_tidy.tidy():
            say(f"video taken off: {g} {name} ({size // 1048576} MB, {why}); its frames stay")
    except Exception as e:  # tidying must never stop the rider
        say(f"could not tidy the videos: {e}")


def write_state(**kw):
    os.makedirs(bc.LOCAL, exist_ok=True)
    kw["at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    kw["home"] = "set" if bc.home() != bc.DEFAULT_HOME else "default"
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(kw, f, indent=1)


def put_away(p, tries=MOVE_TRIES, wait_s=MOVE_WAIT_S):
    """move a filed recording into done\\; True when moved. A file the game still holds open (Windows refuses the move)
    is tried a few times, then left where it is for the next pass: it never stops the rider."""
    done = os.path.join(os.path.dirname(p), "done")
    for i in range(tries):
        try:
            os.makedirs(done, exist_ok=True)
            shutil.move(p, os.path.join(done, os.path.basename(p)))
            return True
        except FileNotFoundError:
            return True                 # already gone: nothing left to put away
        except OSError:
            if i + 1 < tries:
                time.sleep(wait_s)
    return False


def file_ended(ended, announced, filed):
    """file each finished recording once, then put it away. `filed` holds the ones filed but not yet moved (the game
    held them), so a later pass only retries the move and never files the same recording twice."""
    for t, p, game in ended:
        if p not in filed:
            try:
                say(f"FILED {t['name']}: {file_one(t, p, game)}")
            except Exception as e:  # one bad recording must not stop the rider
                say(f"could not file {os.path.basename(p)}: {e}")
            filed.add(p)
        if put_away(p):
            filed.discard(p)
            announced.discard(p)
        else:
            say(f"{os.path.basename(p)} is still held open (the game may still have it): moved on a later pass")


_last_save = [0.0]


def save_reports(now, filed_now):
    """put the filed reports on GitHub, when `begone_autosave` is on (0.101.0): right after a filing, and every
    SAVE_RETRY_S in case an earlier try found git busy or no network. Silent when there is nothing new."""
    if not filed_now and now - _last_save[0] < SAVE_RETRY_S:
        return
    _last_save[0] = now
    if not feature_on("begone_autosave"):
        return
    try:
        line = autosave.save(bc.home(), [t["folder"] for t in bc.tools()])
    except Exception as e:
        line = f"autosave: {e}"
    if line:
        say(line)


def game_of(head, loaded=(), runs=None):
    """the game a recording belongs to: its header's game=, else the collector's one open run whose program has the
    VR dll loaded (the Lua recorders on the simulator write game=?), else UNKNOWN_GAME. Never "?" (2026-11-04)."""
    g = (head.get("game") or "").strip()
    if g and g != "?":
        return g
    if runs is None:
        try:
            runs = list(collector._runs.values())
        except Exception:
            runs = []
    names = {n.lower() for n in loaded}
    hits = {r.get("game") for r in runs if r.get("game") and (not names or (r.get("exe") or "").lower() in names)}
    return hits.pop() if len(hits) == 1 else UNKNOWN_GAME


def run():
    os.makedirs(bc.LOCAL, exist_ok=True)
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    say("rider up: " + ", ".join(t["name"] for t in bc.tools() if t.get("log_dir")))
    if feature_on("collector"):
        try:
            collector.recover()     # runs a stopped rider left open: adopted if the game still runs, else 'lost'
        except Exception as e:
            say(f"collector: could not recover earlier runs: {e}")
    last_proc_look, steam, loaded, announced = 0, False, [], set()
    last_tidy = time.time() - TIDY_EVERY_S + TIDY_FIRST_S
    rec_on = False                  # the rider started the recording that is running now (one per session)
    filed = set()                   # filed, but the game still held the file: only the move is retried
    while True:
        try:
            last_proc_look, steam, loaded, rec_on, last_tidy = one_pass(
                last_proc_look, steam, loaded, rec_on, last_tidy, announced, filed)
        except Exception as e:      # whatever goes wrong in one pass, the rider lives on to the next (2026-11-04)
            say(f"rider: one pass failed, carrying on: {type(e).__name__}: {e}")
        time.sleep(POLL_S)


def one_pass(last_proc_look, steam, loaded, rec_on, last_tidy, announced, filed):
    """one look: find recordings, start/stop the video, collect, file what ended, write the state"""
    now = time.time()
    if now - last_proc_look >= PROCESS_LOOK_EVERY_S:
        steam, loaded = vr_processes()
        last_proc_look = now
    live, ended = [], []
    for t, p, size, mtime in recordings():
        head = log_head(p)
        game = game_of(head, loaded)
        if p not in announced and size >= MIN_LOG_BYTES:
            say(f"VR SESSION: {game} is recording for {t['name']}"); announced.add(p)
            if not rec_on and start_recording(head, game, loaded):   # 0.80.0: any tool's log starts it
                rec_on = True
        if size < MIN_LOG_BYTES and now - mtime > SETTLE_S:
            try:
                os.remove(p)                # never got going
            except OSError:
                pass                        # still held: gone on a later pass
            continue
        if log_ended(p) or now - mtime > SETTLE_S:
            ended.append((t, p, game))
        else:
            live.append(f"{game} ({t['short']})")
    if rec_on and not live:
        stop_recording(); rec_on = False    # the session is over: stopped first, so the filing can cut it
    collecting = collect(now, loaded)
    if not rec_on and not live and not ended and not collecting and now - last_tidy >= TIDY_EVERY_S:
        tidy_videos(); last_tidy = now
    file_ended(ended, announced, filed)
    save_reports(now, bool(ended))
    write_state(vr=bool(live or steam or loaded), recording=live, steamvr=steam, vr_dll_in=loaded,
                collecting=collecting, code=HERE)
    return last_proc_look, steam, loaded, rec_on, last_tidy


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


def code_newer_than(pid):
    """True when a rider file on disk changed after the running rider started (a plugin update landed)"""
    try:
        import psutil
        started = psutil.Process(pid).create_time()
    except Exception:
        return False
    newest = 0
    for name in os.listdir(HERE):
        if name.endswith(".py"):
            newest = max(newest, os.path.getmtime(os.path.join(HERE, name)))
    return newest > started + 2


def start():
    pid, cmd = running()
    if pid and is_this(cmd) and not code_newer_than(pid):
        print("already running"); return True
    if pid:
        stop()                          # an older rider (another plugin version, newer code on disk, or ride.py)
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
        print("collecting:", ", ".join(st.get("collecting") or []) or "nothing")
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
