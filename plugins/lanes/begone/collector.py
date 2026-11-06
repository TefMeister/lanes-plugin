r"""collector.py - the always-on collector (lanes-next, 2026-11-04). Every launch of a project game, on any PC,
whether or not a session is working on it, is collected quietly while it runs and shelved for Gold Digger the
moment it closes. No model reads anything here; collecting costs no tokens.

The maintainer, 2026-11-03: "all these tools we are making, please have it an universal rule to have them run
alongside any game, any launch, collecting data, when a game closes - categorizing all that collecting data for gold
digger to go through it and find the useful parts we didn't have before". Before this, a game log was kept only
when a session remembered to, and the next launch wrote over it.

The rider calls tick() every few seconds (rider.py, 0.62.0+); this file also runs on its own:

    python collector.py status              what is being collected now, and the last runs
    python collector.py runs [<game>] [N]   the ledger: the last N runs (default 20)
    python collector.py pending             runs collected but not yet on the shelves (the transfer folder was away)
    python collector.py shelve              put the pending runs on the shelves now
    python collector.py games               the games this PC would collect, and where they are

WHAT IS COLLECTED, per run, in %LOCALAPPDATA%\BeG0nE\collector\<game>\<YYYY-MM-DD_HH-MM-SS>\ (LANES_COLLECTOR_DIR
in tests), then copied onto the Gold Digger shelves (tools/gd.py) and taken off the PC:
  run.json       the run: game, program, when it started and ended, how long, how it ended (closed / crashed /
                 lost, when the rider itself was down), VR or flat, peaks, how often the window hung and for how
                 long, how long it was not in front, what could not be collected and why   -> shelf "runs"
  samples.tsv    every few seconds: the program's CPU and memory, the whole PC's CPU, the graphics card's load,
                 memory, temperature and clock (nvidia-smi, when there is one), disk read rate, threads, in front
                 or not, answering or hung, window size                                      -> shelf "performance"
  events.tsv     the moments: started, window up, VR on, hung / answering again, focus lost / back, ended
                                                                                            -> shelf "performance"
  logs/          text files under the game's folder (and the game's Gold Digger places) that changed during the
                 run, each at most `collect_log_cap_mb` (50)                     -> each on the shelf its name says
  crashes/       crash dumps written during the run (%LOCALAPPDATA%\CrashDumps)                -> shelf "crashes"
The BeG0nE reports of the run are filed by the rider as before and shelved by gd.py's own BeG0nE step.

HOW IT KNOWS A GAME STARTED: every DISCOVER_EVERY_S the processes on the PC are read; one whose program sits under a
project game's folder (tools/games.py: the store's folder, or `game_dir.<project>`) is that game; a windowed program
with an OpenXR / OpenVR dll loaded that belongs to no project is collected too, under its program's name, so an
unplanned VR run is not lost. Never collected: the VR runtime's own programs, our helper apps, and anything named in
`collect_skip` in lanes.conf (a game with anti-cheat, say); `collect_unknown = no` keeps it to project games only.
Reading a process's numbers touches nothing inside it.
Two projects on one game (Village: the scope and Visceral RE8) share a folder: the run is filed under the project
named first in `collect_prefer = <project>, ...`, else the first by name; the card lists them all.

LIMITS, said out loud: a run shorter than MIN_RUN_S (a launcher bouncing) is noted in the ledger and not shelved;
a log over the cap is listed in run.json as skipped, not copied (RE4's catches once took 18 GB); the local staging
folder is kept under `collect_keep_gb` (3): shelved runs are removed at once, unshelved ones only when over the cap,
oldest first, each noted in the ledger. CPU temperature is not read yet (no free reader is on by default); the
game's own frame times and the headset's poses still need the mod's or the layer's recorder (the next row).
On or off: `collector` (tools/features.py).
"""
import ctypes
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import begone_common as bc  # noqa: E402

LOCAL = os.environ.get("LANES_COLLECTOR_DIR") or os.path.join(bc.LOCAL, "collector")
LEDGER = os.path.join(LOCAL, "runs.tsv")
LEDGER_COLS = ["stamp", "pc", "game", "exe", "seconds", "ended", "vr", "samples", "peak_mb", "hung", "shelved", "note"]
SAMPLE_EVERY_S = 4              # one row of samples.tsv
DISCOVER_EVERY_S = 15           # how often the (dearer) process read runs
GAMES_EVERY_S = 600             # how often the project -> folder map is re-read (stores change rarely)
MIN_RUN_S = 20                  # shorter = a launcher bouncing, noted and not shelved
BYTES_PER_MB = 1048576
LOG_CAP_MB = 50                    # the most of one run's logs kept (collect_log_cap_mb)
DUMP_CAP_MB = 400                  # the most of one run's crash dumps kept (collect_dump_cap_mb)
LEDGER_ROWS = 20                   # rows the ledger shows by default
WATCHED_LATE_S = 60                # a run card watched this much less than its program ran says so
HUNG_MIN_S = 10                    # a window not answering for less than this is loading, not a hang (Run 5 D3)
VR_RUNTIME_CHECK_S = 30            # how often the list of headset runtimes running is re-read
# Programs of a headset runtime: a VR library loaded in the game counts as a VR run only while one of these runs.
# Ashes in GZDoom VR loads openvr_api.dll on every flat run too (Run 5 D3, 2026-11-06).
VR_RUNTIMES = {"vrserver.exe", "vrcompositor.exe", "ovrserver_x64.exe", "virtualdesktop.streamer.exe",
               "mixedrealityportal.exe", "pimaxclient.exe", "wmr_openxr.exe", "vrmonitor.exe"}
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259                 # what Windows gives as the exit code of a program still running
CRASH_CODE_MIN = 0xC0000000        # exit codes from here up are Windows exceptions (a crash)
TEMP_LOGGER = "librehardwaremonitor.exe"   # the temperature logger (Run 5 D10): its own CSV log holds the readings
TEMP_LOG_GLOB = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages",
                             "LibreHardwareMonitor.LibreHardwareMonitor_*", "LibreHardwareMonitorLog-*.csv")
TEMP_LOG_MAX_MB = 20               # the most of the logger's lines copied for one run
LOG_WINDOW_S = 30               # a log changed this long after the end still belongs to the run
LOG_WALK_CAP = 25000            # at most this many files are looked at under a game folder
TEXT_EXT = {".log", ".txt", ".md", ".json", ".csv", ".tsv", ".ini", ".cfg", ".yaml", ".yml", ".out", ".err"}
CRASH_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "CrashDumps")
VR_DLLS = ("openxr_loader.dll", "openvr_api.dll")
# Libraries a headset runtime puts INTO the game only once the game has started a headset session (Run 6 F21,
# 2026-11-06: Virtual Desktop's streamer runs all day on the home PC, so "a runtime is running" called every flat run VR).
# The OpenVR/OpenXR loaders above are in the game whether or not a session ever starts.
VR_SESSION_DLLS = ("vrclient_x64.dll", "vrclient.dll", "steamxr_win64.dll", "libovrrt64_1.dll", "libovrrt32_1.dll",
                   "virtualdesktop-openxr.dll", "virtualdesktop-openxr-32.dll", "mixedrealityruntime.dll",
                   "openxr_simulator.dll", "openxr_simulator-32.dll", "pimax-openxr.dll")
NOT_GAMES = ("vrserver.exe", "vrcompositor.exe", "vrmonitor.exe", "vrwebhelper.exe", "vrdashboard.exe",
             "vrstartup.exe", "steam.exe", "steamwebhelper.exe", "virtualdesktop.streamer.exe",
             "virtualdesktop.server.exe", "obs64.exe", "oculusclient.exe", "ovrserver_x64.exe",
             "windowview.exe", "handfreeze.exe", "handposer.exe", "gunposer.exe", "gripzones.exe", "vrbench.exe",
             "openxr-simulator.exe", "openxr_simulator.exe", "python.exe", "pythonw.exe", "explorer.exe")
SAMPLE_COLS = ["t", "cpu_pct", "rss_mb", "private_mb", "sys_cpu_pct", "gpu_pct", "gpu_mem_mb", "gpu_temp_c",
               "gpu_mhz", "gpu_w", "disk_read_mb_s", "threads", "in_front", "answering", "window"]
DETACHED = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_runs = {}           # pid -> run dict, the games being collected now
_last_discover = 0
_games_at, _games = 0, {}
_nvsmi = shutil.which("nvidia-smi") or (r"C:\Windows\System32\nvidia-smi.exe" if os.name == "nt" else None)
if _nvsmi and not os.path.isfile(_nvsmi):
    _nvsmi = None
_sys_cpu_primed = False


def say(msg):
    """the rider's log when run inside it; plain print on its own"""
    try:
        import rider
        rider.say("collector: " + msg)
    except Exception:
        print(msg, flush=True)


def conf(key, default=None):
    v = bc.read_conf().get(key)
    return v if v not in (None, "") else default


def pc_name():
    try:
        import gd
        return gd.pc_name()
    except Exception:
        return "PC"


def stamp(ts=None):
    return datetime.datetime.fromtimestamp(ts or time.time()).strftime("%Y-%m-%d_%H-%M-%S")


def safe_name(s):
    return re.sub(r"[^A-Za-z0-9._-]", "-", s).strip("-.") or "game"


# ----- which games -----
def games(now=None, force=False):
    """{project or exe-stem: {"where": folder, "title": ..., "exe": name or ""}} for every game this PC has."""
    global _games_at, _games
    now = now or time.time()
    if not force and _games and now - _games_at < GAMES_EVERY_S:
        return _games
    out = {}
    try:
        import games as G
        c = G.conf()
        mapping = G.read_map(c["games_record"]) if c.get("games_record") else {}
        for proj, row in G.now_state(c, mapping).items():
            w = row.get("where") or ""
            if w and w not in ("-", "NOT ON THIS PC") and os.path.isdir(w):
                out[proj] = {"where": w, "title": row.get("title") or proj, "exe": c.get("game_exe." + proj, "")}
    except Exception as e:  # games.py needs its record; without it only game_dir.* below
        say(f"could not read the games list ({e}); using game_dir.* only")
    for k, v in bc.read_conf().items():
        if k.startswith("game_dir.") and os.path.isdir(os.path.expanduser(v)):
            proj = k[len("game_dir."):]
            out.setdefault(proj, {"where": os.path.expanduser(v), "title": proj,
                                  "exe": bc.read_conf().get("game_exe." + proj, "")})
        # collect_dir.<project> = <folder>[, <folder>]: more folders whose programs are that project's game (a port's
        # build folder beside the game data: the Darkness runs from build-home-xr, its data sits in game-files)
        if k.startswith("collect_dir."):
            proj = k[len("collect_dir."):]
            for extra in v.split(","):
                extra = os.path.expanduser(extra.strip())
                if extra and os.path.isdir(extra):
                    out[proj + "@" + os.path.basename(extra)] = {"where": extra, "title": proj, "exe": "", "alias_of": proj}
    _games_at, _games = now, out
    return out


def skip_list():
    return {s.strip().lower() for s in (conf("collect_skip", "") or "").split(",") if s.strip()}


def under(path, folder):
    p, f = os.path.normcase(os.path.normpath(path)), os.path.normcase(os.path.normpath(folder))
    return p == f or p.startswith(f + os.sep)


# ----- windows -----
def windows_of(pid):
    """visible top-level windows of a process: [(hwnd, w, h)]"""
    import ctypes.wintypes as W
    u = ctypes.windll.user32
    out = []

    @ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    def cb(h, _):
        if u.IsWindowVisible(h):
            p = W.DWORD()
            u.GetWindowThreadProcessId(h, ctypes.byref(p))
            if p.value == pid:
                r = W.RECT()
                u.GetClientRect(h, ctypes.byref(r))
                out.append((h, r.right - r.left, r.bottom - r.top))
        return True
    u.EnumWindows(cb, 0)
    return out


def window_state(pid):
    """(in_front, answering, 'WxH') for the process's biggest window; ('', '', '') with no window yet"""
    try:
        ws = windows_of(pid)
    except Exception:
        return "", "", ""
    if not ws:
        return "", "", ""
    h, w, hh = max(ws, key=lambda x: x[1] * x[2])
    u = ctypes.windll.user32
    import ctypes.wintypes as W
    fg = W.DWORD()
    u.GetWindowThreadProcessId(u.GetForegroundWindow(), ctypes.byref(fg))
    return ("1" if fg.value == pid else "0"), ("0" if u.IsHungAppWindow(h) else "1"), f"{w}x{hh}"


def has_session_dll(pid):
    """True / False when the game has / has not loaded a headset runtime's own library; None when it cannot be read"""
    try:
        import psutil
        return any(os.path.basename(m.path).lower() in VR_SESSION_DLLS for m in psutil.Process(pid).memory_maps())
    except Exception:  # noqa: BLE001
        return None


def headset_session(run, now):
    """is a headset session running in this game? Looked at every VR_RUNTIME_CHECK_S at most (reading a program's
    library list is not free). Falls back to "a runtime program is running" only when the list cannot be read."""
    if now - run.get("_vr_look", 0) < VR_RUNTIME_CHECK_S:
        return False
    run["_vr_look"] = now
    seen = has_session_dll(run["pid"])
    return vr_runtime_running(now) if seen is None else seen


def has_vr_dll(proc):
    try:
        return any(os.path.basename(m.path).lower() in VR_DLLS for m in proc.memory_maps())
    except Exception:
        return False


def gpu_sample():
    """[pct, mem_mb, temp_c, mhz, watts] from nvidia-smi, or blanks"""
    if not _nvsmi:
        return [""] * 5
    try:
        r = subprocess.run([_nvsmi, "--query-gpu=utilization.gpu,memory.used,temperature.gpu,clocks.gr,power.draw",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5,
                           creationflags=DETACHED)
        parts = [p.strip() for p in r.stdout.strip().splitlines()[0].split(",")]
        return (parts + [""] * 5)[:5] if len(parts) >= 3 else [""] * 5
    except Exception:
        return [""] * 5


# ----- the run folder -----
def run_dir(game, ts):
    return os.path.join(LOCAL, safe_name(game), stamp(ts))


def append_tsv(path, cols, header=None):
    new = not os.path.exists(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        if new and header:
            f.write("# " + "\t".join(header) + "\n")
        f.write("\t".join(str(c).replace("\t", " ").replace("\n", " ") for c in cols) + "\n")


def tilde(v):
    """the home folder written as ~ (Run 5 D7: every card carried the login in its folder field; the cards are quoted
    by Gold Digger and printed on screen)"""
    if isinstance(v, str):
        home = os.path.expanduser("~")
        for h in (home, home.replace("\\", "/")):
            v = re.sub(re.escape(h), lambda _m: "~", v, flags=re.I)   # anywhere: a command line names files too
        return v
    if isinstance(v, list):
        return [tilde(x) for x in v]
    if isinstance(v, dict):
        return {k: tilde(x) for k, x in v.items()}
    return v


def write_run(run):
    keep = {k: tilde(v) for k, v in run.items() if not k.startswith("_")}
    with open(os.path.join(run["folder"], "run.json"), "w", encoding="utf-8") as f:
        json.dump(keep, f, indent=1)


def event(run, what, detail=""):
    append_tsv(os.path.join(run["folder"], "events.tsv"), [stamp(), round(time.time() - run["_start_ts"], 1), what,
                                                           detail], ["when", "t", "event", "detail"])


_vr_rt = {"t": 0, "on": False}


def _refresh_running(now):
    if now - _vr_rt["t"] >= VR_RUNTIME_CHECK_S:
        _vr_rt["t"] = now
        try:
            import psutil
            names = {(p.info["name"] or "").lower() for p in psutil.process_iter(["name"])}
        except Exception:  # noqa: BLE001
            names = set()
        _vr_rt["on"] = bool(names & VR_RUNTIMES)
        _vr_rt["temp"] = TEMP_LOGGER in names


def vr_runtime_running(now):
    _refresh_running(now)
    return _vr_rt["on"]


def temp_logger_running(now):
    _refresh_running(now)
    return _vr_rt.get("temp", False)


def copy_temperatures(run, end_ts):
    """the temperature logger's lines that fall inside the run, from its own CSV log -> temperature.csv"""
    import glob
    start = datetime.datetime.fromtimestamp(run["_start_ts"])
    end = datetime.datetime.fromtimestamp(end_ts)
    pattern = conf("temp_log_glob", TEMP_LOG_GLOB) or TEMP_LOG_GLOB
    files = [f for f in glob.glob(pattern) if os.path.getmtime(f) >= run["_start_ts"]]
    if not files:
        return
    out, header, size = [], None, 0
    for f in sorted(files, key=os.path.getmtime):
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh):
                    if i < 2:
                        header = header or line
                        if i == 1 and not out:
                            out.append(header)
                            out.append(line)
                        continue
                    when = line.split(",", 1)[0].strip().strip('"')
                    t = None
                    for fmt in ("%m/%d/%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M:%S"):
                        try:
                            t = datetime.datetime.strptime(when, fmt)
                            break
                        except ValueError:
                            continue
                    if t and start <= t <= end:
                        out.append(line)
                        size += len(line)
                        if size > TEMP_LOG_MAX_MB * BYTES_PER_MB:
                            break
        except OSError:
            continue
    if len(out) > 2:
        with open(os.path.join(run["folder"], "temperature.csv"), "w", encoding="utf-8", newline="") as fh:
            fh.writelines(out)
        run["temperature_rows"] = len(out) - 2


def open_handle(pid):
    """a handle on the program, kept while it runs, so its exit code can be read when it ends (Run 5 D5: a forced kill
    looked like a normal close). Windows only; None elsewhere or when refused."""
    if os.name != "nt":
        return None
    try:
        h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        return h or None
    except Exception:  # noqa: BLE001
        return None


def exit_code(run):
    h = run.get("_handle")
    if not h:
        return None
    try:
        code = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        run["_handle"] = None
        return code.value if ok and code.value != STILL_ACTIVE else None
    except Exception:  # noqa: BLE001
        return None


def how_it_ended(code, crashes):
    """closed / crashed / killed, from the exit code when there is one"""
    if code is None:
        return "crashed" if crashes else "closed"
    if code == 0:
        return "crashed" if crashes else "closed"
    if code >= CRASH_CODE_MIN:
        return "crashed"
    if code == 1:
        return "killed"       # what a forced end (Task Manager, taskkill /F) gives; a game quitting with 1 is rare
    return "closed" if not crashes else "crashed"


def begin(proc, game, info, now, vr, adopted=False, folder=None):
    try:
        exe_path = proc.exe() or ""
    except Exception:
        exe_path = ""
    if not folder:
        # 2026-11-05 (home PC, GZDoom VR): two copies of one program found in the same second got ONE folder, so their
        # samples and events went into the same files. A folder another live run already uses gets the pid added.
        folder = run_dir(game, now)
        if any(r.get("folder") == folder for r in _runs.values()):
            folder = f"{folder}-{proc.pid}"
    os.makedirs(folder, exist_ok=True)
    # Which build and which files this launch used (Run 5 D7: three Ashes launches ran the plain engine with none of
    # our files, and nothing on the card said so): the command line, and the program file's size and date.
    try:
        cmdline = subprocess.list2cmdline(proc.cmdline())
    except Exception:  # noqa: BLE001
        cmdline = ""
    try:
        st = os.stat(exe_path)
        exe_build = {"size": st.st_size, "modified": stamp(st.st_mtime)}
    except OSError:
        exe_build = {}
    run = {
        "game": game, "title": info.get("title", game), "project": info.get("project", game),
        "projects": info.get("projects") or [info.get("project", game)], "exe": proc.name(),
        "exe_path": exe_path, "command_line": cmdline, "exe_build": exe_build, "pid": proc.pid, "pc": pc_name(), "start": stamp(proc.create_time()),
        "end": "", "seconds": 0, "ended": "", "exit_code": "", "vr": False, "vr_dll": bool(vr),
        # Village 2026-11-04: the program loads its VR library even when no headset answers (REFramework tries, fails),
        # so "vr" says a VR dll was loaded, not that a headset session ran. The OpenXR recorder layer will know for sure.
        "vr_how": "vr = the game loaded a headset runtime's own library (SteamVR, Oculus, Virtual Desktop, WMR, the "
                  "pretend headset), which happens only when a headset session starts; vr_dll alone = the game has the "
                  "VR loader but no session was seen (a flat run of a VR build)",
        "folder": folder, "samples": 0, "peak_rss_mb": 0,
        "peak_private_mb": 0, "cpu_mean_pct": 0, "gpu_temp_max_c": "", "hung_count": 0, "hung_longest_s": 0,
        "unfocused_s": 0, "logs": [], "logs_skipped": [], "crashes": [], "missing": [], "shelved": False,
        "notes": ["adopted: the rider restarted while the game ran"] if adopted else [],
        "watched_s": 0,
        "_proc": proc, "_start_ts": proc.create_time(), "_watch_ts": now, "_last_sample": 0, "_cpu_sum": 0.0, "_hung_since": 0,
        "_unfocused_since": 0, "_last_read": None, "_last_t": 0, "_window_seen": False, "_vr_seen": bool(vr),
        "_handle": open_handle(proc.pid), "_short_hangs": 0,
    }
    if vr and headset_session(run, now):
        run["vr"] = True
    if not _nvsmi:
        run["missing"].append("graphics card numbers: no nvidia-smi on this PC")
    run["_temp_on"] = temp_logger_running(now)
    if not run["_temp_on"]:
        run["missing"].append("CPU temperature: the temperature logger (LibreHardwareMonitor) is not running")
    try:
        proc.cpu_percent(None)   # primes the delta
    except Exception:
        pass
    write_run(run)
    event(run, "started" if not adopted else "adopted", f"{proc.name()} pid {proc.pid}" + (" VR" if vr else ""))
    say(f"COLLECTING {game}: {proc.name()} (pid {proc.pid}){' in VR' if vr else ''}")
    return run


def sample(run, now, sys_cpu, gpu, vr_names):
    p = run["_proc"]
    try:
        cpu = p.cpu_percent(None)
        mem = p.memory_info()
        threads = p.num_threads()
        try:
            rd = p.io_counters().read_bytes
        except Exception:
            rd = None
    except Exception:
        return False   # gone: the caller ends it
    rate = ""
    if rd is not None and run["_last_read"] is not None and now > run["_last_t"]:
        rate = round((rd - run["_last_read"]) / (now - run["_last_t"]) / 1e6, 2)
    run["_last_read"], run["_last_t"] = rd, now
    in_front, answering, win = window_state(p.pid)
    rss, priv = round(mem.rss / 1048576), round(getattr(mem, "private", 0) / 1048576)
    append_tsv(os.path.join(run["folder"], "samples.tsv"),
               [round(now - run["_start_ts"], 1), round(cpu, 1), rss, priv, sys_cpu] + gpu +
               [rate, threads, in_front, answering, win], SAMPLE_COLS)
    run["samples"] += 1
    run["_cpu_sum"] += cpu
    run["peak_rss_mb"] = max(run["peak_rss_mb"], rss)
    run["peak_private_mb"] = max(run["peak_private_mb"], priv)
    try:
        if gpu[2] != "":
            run["gpu_temp_max_c"] = max(int(run["gpu_temp_max_c"] or 0), int(float(gpu[2])))
    except ValueError:
        pass
    if win and not run["_window_seen"]:
        run["_window_seen"] = True
        event(run, "window up", win)
    if not run["_vr_seen"] and run["exe"].lower() in vr_names:
        run["_vr_seen"] = run["vr_dll"] = True
        event(run, "VR library loaded", "a VR dll is loaded")
    temp_on = temp_logger_running(now)
    if temp_on != run.get("_temp_on", temp_on):
        run["_temp_on"] = temp_on
        what = "temperature logger started" if temp_on else "temperature logger STOPPED"
        event(run, what, "LibreHardwareMonitor")
        run["notes"].append(f"{what} at {stamp(now)[11:]}")
    if run["_vr_seen"] and not run["vr"] and headset_session(run, now):
        run["vr"] = True
        event(run, "VR on", "a VR library is loaded and a headset runtime runs")
    if answering == "0" and not run["_hung_since"]:
        run["_hung_since"] = now
        event(run, "not answering", "the window stopped answering")
    elif answering == "1" and run["_hung_since"]:
        end_hang(run, now)
    if in_front == "0" and run["_window_seen"] and not run["_unfocused_since"]:
        run["_unfocused_since"] = now
        event(run, "focus lost")
    elif in_front == "1" and run["_unfocused_since"]:
        run["unfocused_s"] += round(now - run["_unfocused_since"])
        event(run, "focus back", f"after {round(now - run['_unfocused_since'])} s")
        run["_unfocused_since"] = 0
    run["_last_sample"] = now
    return True


# ----- the end of a run -----
def copy_logs(run, end_ts):
    """text files under the game's folder (and its Gold Digger places) changed during the run -> logs/"""
    cap = int(float(conf("collect_log_cap_mb", LOG_CAP_MB) or LOG_CAP_MB) * BYTES_PER_MB)
    lo, hi = run["_start_ts"] - 5, end_ts + LOG_WINDOW_S
    places = []
    where = games().get(run["project"], {}).get("where") or (os.path.dirname(run["exe_path"]) if run["exe_path"] else "")
    if where and os.path.isdir(where):
        places.append(where)
    try:
        import gd
        for pattern, _ in gd.sources(run["game"], gd.pc_name()):
            places.extend(gd.expand(pattern))
    except Exception:
        pass
    seen, n = set(), 0
    dest_dir = os.path.join(run["folder"], "logs")
    for place in places:
        files = []
        if os.path.isdir(place):
            for base, dirs, names in os.walk(place):
                for name in names:
                    files.append(os.path.join(base, name))
                    n += 1
                if n > LOG_WALK_CAP:
                    run["notes"].append(f"logs: looked at the first {LOG_WALK_CAP} files only")
                    break
        elif os.path.isfile(place):
            files.append(place)
        for f in files:
            if f in seen or os.path.splitext(f)[1].lower() not in TEXT_EXT:
                continue
            seen.add(f)
            try:
                st = os.stat(f)
            except OSError:
                continue
            if not (lo <= st.st_mtime <= hi):
                continue
            rel = os.path.relpath(f, where).replace(os.sep, "__") if where and under(f, where) else os.path.basename(f)
            if st.st_size > cap:
                run["logs_skipped"].append(f"{rel} ({st.st_size // 1048576} MB, over the cap)")
                continue
            try:
                os.makedirs(dest_dir, exist_ok=True)
                shutil.copy2(f, os.path.join(dest_dir, re.sub(r"[^A-Za-z0-9._-]", "_", rel)[-120:]))
                run["logs"].append(rel)
            except OSError as e:
                run["logs_skipped"].append(f"{rel} (could not copy: {e})")


def copy_crashes(run, end_ts):
    """crash dumps of the run: Windows' own (%LOCALAPPDATA%\\CrashDumps\\<exe>*.dmp) and any .dmp written in the game's
    own folder during the run (REFramework writes reframework_crash.dmp beside the game, Village 2026-11-04)"""
    stem = os.path.splitext(run["exe"])[0].lower()
    cap = int(float(conf("collect_dump_cap_mb", DUMP_CAP_MB) or DUMP_CAP_MB) * BYTES_PER_MB)
    lo, hi = run["_start_ts"] - 5, end_ts + LOG_WINDOW_S
    found = []
    try:
        for name in os.listdir(CRASH_DIR):
            if name.lower().startswith(stem):
                found.append(os.path.join(CRASH_DIR, name))
    except OSError:
        pass
    where = run.get("exe_path") and os.path.dirname(run["exe_path"]) or ""
    if where and os.path.isdir(where):
        try:
            for name in os.listdir(where):
                if name.lower().endswith(".dmp"):
                    found.append(os.path.join(where, name))
        except OSError:
            pass
    for p in found:
        try:
            st = os.stat(p)
            if not (lo <= st.st_mtime <= hi):
                continue
            name = os.path.basename(p)
            if st.st_size > cap:
                run["logs_skipped"].append(f"{name} ({st.st_size // 1048576} MB dump, over the cap)")
                run["crashes"].append(name + " (not copied: over the cap)")
                continue
            os.makedirs(os.path.join(run["folder"], "crashes"), exist_ok=True)
            shutil.copy2(p, os.path.join(run["folder"], "crashes", name))
            run["crashes"].append(name)
        except OSError:
            pass


def end_hang(run, now):
    """a spell of not answering is over: HUNG_MIN_S or longer is a hang, shorter is loading (counted apart)"""
    took = round(now - run["_hung_since"])
    run["_hung_since"] = 0
    if took >= HUNG_MIN_S:
        run["hung_count"] += 1
        run["hung_longest_s"] = max(run["hung_longest_s"], took)
        event(run, "answering again", f"after {took} s: a hang")
    else:
        run["_short_hangs"] += 1
        run["short_waits"] = run["_short_hangs"]
        event(run, "answering again", f"after {took} s (loading, not counted as a hang)")


def finish(run, now, ended=None):
    if run["_hung_since"]:
        end_hang(run, now)
    if run["_unfocused_since"]:
        run["unfocused_s"] += round(now - run["_unfocused_since"])
    run["end"], run["seconds"] = stamp(now), round(now - run["_start_ts"])
    # 2026-11-05 (home PC, GZDoom VR): a card said 2741 s for a program watched only 743 s; the helper started while it
    # already ran. `seconds` stays the program's own life; `watched_s` is what the samples cover, and a gap is said.
    run["watched_s"] = round(now - run.get("_watch_ts", run["_start_ts"]))
    if run["seconds"] - run["watched_s"] > WATCHED_LATE_S:
        note = (f"watched for {run['watched_s']} s of its {run['seconds']} s: the program was running before the "
                f"helper began watching it")
        if note not in run["notes"]:
            run["notes"].append(note)
    run["cpu_mean_pct"] = round(run["_cpu_sum"] / run["samples"], 1) if run["samples"] else 0
    if run["seconds"] < MIN_RUN_S and not ended:
        run["ended"] = "brief"
        ledger(run, "a launcher bouncing, or the game did not get going; not shelved")
        shutil.rmtree(run["folder"], ignore_errors=True)
        say(f"{run['game']}: {run['exe']} ran {run['seconds']} s only; not kept")
        return
    copy_crashes(run, now)
    copy_logs(run, now)
    try:
        copy_temperatures(run, now)
    except Exception as e:  # noqa: BLE001 - a missing reading never stops a run being kept
        run["missing"].append(f"CPU temperature: the logger's lines could not be copied ({type(e).__name__})")
    code = exit_code(run)
    run["exit_code"] = "" if code is None else ("0x%08X" % code if code >= CRASH_CODE_MIN else str(code))
    run["ended"] = ended or how_it_ended(code, run["crashes"])
    event(run, "ended", run["ended"] + (f" (exit code {run['exit_code']})" if run["exit_code"] else ""))
    write_run(run)
    say(f"ENDED {run['game']}: {run['ended']} after {run['seconds']} s; {run['samples']} samples, "
        f"{len(run['logs'])} log(s), {len(run['crashes'])} dump(s)")
    shelve_run(run["folder"])


def ledger(run, note=""):
    append_tsv(LEDGER, [os.path.basename(run["folder"]), run.get("pc", ""), run["game"], run["exe"], run["seconds"],
                        run["ended"], "VR" if run.get("vr") else ("VR dll" if run.get("vr_dll") else "flat"),
                        run["samples"], run["peak_rss_mb"],
                        run["hung_count"], "yes" if run["shelved"] else "no", note], LEDGER_COLS)


def shelve_run(folder):
    """copy one finished run onto the Gold Digger shelves; True when it is there and the local copy is gone"""
    try:
        with open(os.path.join(folder, "run.json"), encoding="utf-8") as f:
            run = json.load(f)
    except (OSError, ValueError):
        return False
    try:
        import gd
        root = gd.root()
        if not (os.path.isdir(root) or os.path.isdir(os.path.dirname(root))):
            raise OSError(f"the Gold Digger folder is not there ({root}): is the transfer drive on?")
        game, pc = run["game"], gd.pc_name()
        known = {r["sha1"] for r in gd.index(game)}
        # the card goes onto the shelf already saying it is shelved (Run 5 D3: the shelf copy said false while the
        # ledger said yes); put back if the shelving fails
        run["shelved"] = True
        with open(os.path.join(folder, "run.json"), "w", encoding="utf-8") as f:
            json.dump(run, f, indent=1)
        origin = f"collector run {os.path.basename(folder)}"
        for name, shelf in (("run.json", "runs"), ("samples.tsv", "performance"), ("events.tsv", "performance"),
                            ("temperature.csv", "performance")):
            p = os.path.join(folder, name)
            if os.path.isfile(p):
                gd.shelve_one(game, p, shelf, known, pc, origin)
        for sub, shelf in (("logs", None), ("crashes", "crashes")):
            d = os.path.join(folder, sub)
            if os.path.isdir(d):
                for name in sorted(os.listdir(d)):
                    gd.shelve_one(game, os.path.join(d, name), shelf, known, pc, origin)
        try:
            gd.shelve(game, quiet=True)          # the run's BeG0nE reports, the game's own places
        except Exception:
            pass
        run["shelved"] = True
        ledger(run, "")
        shutil.rmtree(folder, ignore_errors=True)
        say(f"SHELVED {game} {os.path.basename(folder)} for Gold Digger")
        return True
    except Exception as e:
        try:
            run["shelved"] = False
            with open(os.path.join(folder, "run.json"), "w", encoding="utf-8") as f:
                json.dump(run, f, indent=1)
        except (OSError, NameError):
            pass
        say(f"not shelved yet ({e}); kept locally, will try again")
        return False


def pending():
    out = []
    try:
        for game in sorted(os.listdir(LOCAL)):
            gd_ = os.path.join(LOCAL, game)
            if not os.path.isdir(gd_):
                continue
            for run in sorted(os.listdir(gd_)):
                p = os.path.join(gd_, run, "run.json")
                if os.path.isfile(p):
                    try:
                        with open(p, encoding="utf-8") as f:
                            r = json.load(f)
                    except (OSError, ValueError):
                        continue
                    out.append((os.path.join(gd_, run), r))
    except OSError:
        pass
    return out


def shelve_pending(live_pids=()):
    done = 0
    for folder, r in pending():
        if r.get("end") and not r.get("shelved"):
            done += shelve_run(folder)
    return done


def keep_under_cap():
    cap = float(conf("collect_keep_gb", 3) or 3) * 1024 ** 3
    items = sorted(pending(), key=lambda x: x[0])
    total = sum(sum(os.path.getsize(os.path.join(b, n)) for b, _, fs in os.walk(f) for n in fs) for f, _ in items)
    for folder, r in items:
        if total <= cap:
            break
        if r.get("pid") in _runs:
            continue
        size = sum(os.path.getsize(os.path.join(b, n)) for b, _, fs in os.walk(folder) for n in fs)
        r["ended"] = r.get("ended") or "lost"
        ledger(r, f"dropped before shelving: the local folder was over {cap / 1024 ** 3:g} GB")
        shutil.rmtree(folder, ignore_errors=True)
        total -= size
        say(f"dropped {os.path.basename(folder)} ({size // 1048576} MB) to stay under the cap")


# ----- discovery -----
def discover(now, vr_names):
    """start a run for every game process that has none yet; returns the exe names of VR processes seen"""
    try:
        import psutil
    except ImportError:
        return
    gm = games(now)
    skip = skip_list()
    for proc in psutil.process_iter(["pid", "name", "exe", "create_time"]):
        pid, name = proc.info["pid"], (proc.info["name"] or "")
        if pid in _runs or not name or name.lower() in NOT_GAMES or pid == os.getpid():
            continue
        exe = proc.info["exe"] or ""
        match = None
        hits = [(proj, info) for proj, info in gm.items()
                if (exe and under(exe, info["where"]))
                or (info.get("exe") and name.lower() == os.path.basename(info["exe"]).lower())]
        if hits:
            # two projects on one game (Village: the scope and Visceral RE8) share a folder: the run is filed under
            # the one named in `collect_prefer`, else the first by name, and the card lists them all
            prefer = [s.strip() for s in (conf("collect_prefer", "") or "").split(",") if s.strip()]
            hits = [(h[1].get("alias_of", h[0]), h[1]) for h in hits]      # a collect_dir folder counts as its project
            hits.sort(key=lambda h: (prefer.index(h[0]) if h[0] in prefer else len(prefer), h[0]))
            proj, info = hits[0]
            match = (proj, dict(info, project=proj, projects=sorted({h[0] for h in hits})))
        if match and (match[0].lower() in skip or name.lower() in skip):
            continue
        if not match:
            if name.lower() in skip or not exe or (conf("collect_unknown", "yes") or "yes").lower() in ("no", "off", "0"):
                continue
            if name.lower() in vr_names or (pid in _windowed_cache(now) and has_vr_dll(proc)):
                match = (safe_name(os.path.splitext(name)[0]), {"title": name, "project": "", "where": os.path.dirname(exe)})
        if not match:
            continue
        try:
            _runs[pid] = begin(proc, match[0], match[1], now, name.lower() in vr_names or (match[1].get("project") == "" ))
        except Exception as e:
            say(f"could not start collecting {name}: {e}")


_wc_at, _wc = 0, set()


def _windowed_cache(now):
    global _wc_at, _wc
    if now - _wc_at > 5:
        try:
            import rider
            _wc = rider.windowed_pids()
        except Exception:
            _wc = set()
        _wc_at = now
    return _wc


def recover():
    """at start: runs left open by a rider that stopped. The game still running = adopted; gone = ended 'lost'."""
    try:
        import psutil
    except ImportError:
        return
    for folder, r in pending():
        if r.get("end"):
            continue
        pid = r.get("pid")
        try:
            p = psutil.Process(pid)
            if p.name().lower() == (r.get("exe") or "").lower():
                run = begin(p, r["game"], {"title": r.get("title"), "project": r.get("project", r["game"])}, time.time(),
                            r.get("vr"), adopted=True, folder=folder)
                run["samples"] = r.get("samples", 0)
                _runs[pid] = run
                continue
        except Exception:
            pass
        r["end"], r["ended"] = r.get("end") or stamp(), "lost"
        r["notes"] = r.get("notes", []) + ["the rider was down when the game closed; no logs copied"]
        with open(os.path.join(folder, "run.json"), "w", encoding="utf-8") as f:
            json.dump(r, f, indent=1)
        shelve_run(folder)


# ----- the rider's call -----
def tick(now=None, vr_exes=()):
    """called by the rider every poll. vr_exes: names of windowed programs with a VR dll (the rider knows them)."""
    global _last_discover, _sys_cpu_primed
    now = now or time.time()
    vr_names = {n.lower() for n in vr_exes}
    if now - _last_discover >= DISCOVER_EVERY_S:
        discover(now, vr_names)
        _last_discover = now
    if not _runs:
        return []
    try:
        import psutil
        if not _sys_cpu_primed:
            psutil.cpu_percent(None)
            _sys_cpu_primed = True
        sys_cpu = psutil.cpu_percent(None)
    except Exception:
        sys_cpu = ""
    gpu = None
    for pid, run in list(_runs.items()):
        if now - run["_last_sample"] < SAMPLE_EVERY_S:
            continue
        if gpu is None:
            gpu = gpu_sample()
        alive = run["_proc"].is_running() and run["_proc"].status() != "zombie"
        if alive:
            alive = sample(run, now, sys_cpu, gpu, vr_names)
        if not alive:
            del _runs[pid]
            try:
                finish(run, now)
            except Exception as e:
                say(f"could not finish {run['game']}: {e}")
            try:
                shelve_pending()
                keep_under_cap()
            except Exception as e:
                say(f"shelving failed: {e}")
        elif run["samples"] % 15 == 0:
            write_run(run)     # a crash of the PC still leaves a readable run.json
    return [f"{r['game']} ({r['exe']})" for r in _runs.values()]


# ----- commands -----
def read_ledger(game=None, n=LEDGER_ROWS):
    rows = []
    try:
        with open(LEDGER, encoding="utf-8") as f:
            for line in f:
                if line.startswith("#") or not line.strip():
                    continue
                r = dict(zip(LEDGER_COLS, line.rstrip("\n").split("\t")))
                if not game or r.get("game") == safe_name(game):
                    rows.append(r)
    except OSError:
        pass
    return rows[-n:]


def cmd_status():
    live = [r for _, r in pending() if not r.get("end")]
    print("collecting now:", ", ".join(f"{r['game']} ({r['exe']}, since {r['start'][11:].replace('-', ':')})" for r in live) or "nothing")
    waiting = [r for _, r in pending() if r.get("end") and not r.get("shelved")]
    print("waiting for the shelves:", len(waiting))
    for r in read_ledger(n=5):
        print(f"  {r['stamp']}  {r['game']:<28} {r['exe']:<22} {r['seconds']:>6} s  {r['ended']:<8} {r['vr']:<5} "
              f"shelved {r['shelved']}" + (f"  {r['note']}" if r.get("note") else ""))
    print("graphics card numbers:", "nvidia-smi" if _nvsmi else "none (no nvidia-smi)")
    print("staging folder:", LOCAL)


def main(argv):
    cmd = argv[0] if argv else "status"
    if cmd == "status":
        cmd_status()
    elif cmd == "runs":
        game = argv[1] if len(argv) > 1 and not argv[1].isdigit() else None
        n = int(argv[-1]) if len(argv) > 1 and argv[-1].isdigit() else LEDGER_ROWS
        for r in read_ledger(game, n):
            print("\t".join(r.get(c, "") for c in LEDGER_COLS))
    elif cmd == "pending":
        for folder, r in pending():
            print(f"{'LIVE ' if not r.get('end') else '     '}{folder}  {r['game']}  {r.get('ended') or 'running'}")
    elif cmd == "shelve":
        print(f"shelved {shelve_pending()} run(s)")
    elif cmd == "games":
        for proj, info in sorted(games(force=True).items()):
            print(f"{proj:<30} {info['where']}" + (f"  ({info['exe']})" if info.get("exe") else ""))
        if skip_list():
            print("never collected (collect_skip):", ", ".join(sorted(skip_list())))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
