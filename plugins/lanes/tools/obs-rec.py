r"""obs-rec.py - record ONLY a game's window (and only its sound) during a test, with OBS (asked for by the maintainer, 2026-10-07).

    python obs-rec.py start <exe> <label> [--game <project>] [--class <cls>] [--also <exe>[:<cls>|:!<cls>]]
                                                                start recording that game's window
    python obs-rec.py stop                                      stop; prints the file it wrote
    python obs-rec.py done                                      put your own OBS profile back; close OBS if we opened it
    python obs-rec.py status
    python obs-rec.py check                                     is the game window showing a picture? PICTURE / BLACK
    python obs-rec.py repoint <exe>                             point the capture at that window again, still recording
    python obs-rec.py sim <exe>                                 is the OpenXR Simulator's preview up for that game?

PRIVACY, the reason for the shape: it never captures the screen. The picture comes from a Window Capture of the game's
own window (Windows Graphics Capture: no injection into the game, so it cannot fight our Present hooks), and the sound
from an Application Audio Capture of the game's exe only. Nothing else on the PC can end up in a recording.

It works in its OWN OBS profile and scene collection ("claude-tests"), so your own OBS setup is never changed, and
`done` switches back to whatever was active before. Recording uses the graphics card's encoder (NVENC), 1280x720,
60 fps, OBS's "High Quality, Medium File Size" preset (good quality, medium size), so the game loses
almost nothing. Files go to E:\OBS gameplay videos\<project>\<label>_<date>_<time>.mp4.

TWO WINDOWS AT ONCE (asked for by the maintainer, 2026-10-07): `--also` records a second window (e.g. the OpenXR simulator's preview)
into its OWN file, `<label>_second_<date>.mp4`, started and stopped by the same recording so the two line up. It
uses the Source Record add-on (exeldro/obs-source-record). The add-on only records a source OBS is drawing, so the
second window sits in the game scene but far outside the picture (a hidden scene never draws it: tested 2026-10-07). `:<cls>` picks
that window class, `:!<cls>` any other class (the simulator's preview lives in the game's own process).
`--class` does the same for the main window.

THE SIMULATOR'S PREVIEW, BY ITSELF (0.72.0): without `--also`, `start` records the OpenXR Simulator's preview as the
second file whenever it is up, and if it is not up yet leaves a quiet watcher that adds it the moment it opens (then
restarts the recording so both files begin together). `sim <exe>` says whether it is up. The main window never picks
the preview, even when the preview is the bigger window.

THE CLOCK BESIDE EACH FILE (0.76.0): every saved file gets a small `<file>.json` beside it saying when its first frame
was on the PC's clock (`start_ms`, milliseconds since 1970: the moment OBS confirmed recording, less how long OBS
says it had already run), when it stopped, which game and which window. BeG0nE lines a jitter log up with it by that
clock and cuts the jittery seconds out as frames (begone/camera-jitter/frames.py).

THE GUARD (0.77.0): every `start` leaves a quiet guard that looks at OBS every 5 s while it records. If OBS closes,
crashes (its crash boxes are closed for you) or stops recording mid-session, the guard writes when and why into
%LOCALAPPDATA%\obs-rec-breaks.log, which the jitter reports quote, and starts a fresh recording if the game is still
open. After an unclean close OBS asks "Crash Detected" on its next start and never comes up for the recorder;
`start` clears the leftover marks first, and closes an OBS stuck on that question.

Needs: OBS 28+ with its WebSocket server on (Tools -> WebSocket Server Settings; the password is read from OBS's own
config file, never copied anywhere), and `pip install obsws-python`.
"""
import ctypes, ctypes.wintypes as W, json, os, subprocess, sys, time

OBS_EXE = r"C:\Program Files\obs-studio\bin\64bit\obs64.exe"
CRASH_TITLE = "OBS Studio Crash Detected"   # the window OBS shows instead of starting, after an unclean close
CRASH_BOXES = (CRASH_TITLE, "OBS has crashed!", "Source Cleanup Error")   # boxes OBS leaves on screen (2026-10-17)
BREAKS_LOG = os.path.join(os.path.expandvars("%LOCALAPPDATA%"), "obs-rec-breaks.log")   # read by BeG0nE's frames.py
GUARD_POLL_S = 5        # how often the guard looks at OBS while it records
GUARD_MISSES = 3        # WebSocket polls in a row without an answer before OBS counts as stopped
GUARD_RESTART_S = 120   # the most a fresh start may take (OBS may have to start first)
OBS_CFG = os.path.expandvars(r"%APPDATA%\obs-studio\plugin_config\obs-websocket\config.json")
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

# Where the recordings go: lanes.conf `recordings = <folder>`, else the synced transfer folder's Videos
# (`transfer = <folder>`, see /lanes:setup), else your Videos folder. One subfolder per project.
_transfer = lanes_conf("transfer")
REC_ROOT = lanes_conf("recordings") or (os.path.join(_transfer, "Videos") if _transfer else
                                        os.path.join(os.path.expanduser("~"), "Videos", "Lanes recordings"))
STATE = os.path.join(os.path.expandvars("%LOCALAPPDATA%"), "obs-rec-state.json")
PROFILE = COLLECTION = "claude-tests"
SCENE = "Game"
VIDEO_W, VIDEO_H, FPS = 1280, 720, 60   # 60 fps
CONNECT_TRIES, CONNECT_GAP_S = 40, 0.5
START_CHECKS, START_CHECK_GAP_S = 10, 0.5   # up to 5 s for the recording to really begin
CLOSE_CHECKS, CLOSE_CHECK_GAP_S = 10, 0.5   # up to 5 s for OBS to close politely (the recording is saved by then)
SIM_TITLE = "OpenXR Simulator"     # the simulator's preview window title starts with this (read from its dll)
SIM_LABEL = "OpenXR Simulator preview"
SIM_WAIT_S, SIM_POLL_S = 900, 2.0   # the watcher looks for the preview every 2 s, for up to 15 min
# elliotttate's OpenXR OBS Mirror (0.92.0): its OBS source shows what the headset is shown, D3D11 and D3D12 alike
MIRROR_KIND = "openxrmirror_capture"
MIRROR_LABEL = "OpenXR headset view (OBS Mirror)"   # starts with "OpenXR": frames.py treats it as the headset view
DETACHED_PROCESS, CREATE_NEW_PROCESS_GROUP = 0x00000008, 0x00000200
NO_WINDOW = 0x08000000   # tasklist/taskkill from the windowless guard flashed a console every poll (2026-10-17)
SRC_VIDEO, SRC_AUDIO = "game window", "game sound"
SRC_SECOND, SECOND_FILTER = "second window", "record second window"
OFF_CANVAS_X = 50000   # the second window sits in the game scene but far off the picture: drawn, never seen
SR_RECORD_WHILE_RECORDING, SR_OFF = 3, 0          # Source Record's record_mode values
SR_ENCODER = "obs_nvenc_h264_soft"   # 2026-10-17: the _tex one crashed OBS inside Source Record (nvenc_create_base)
SR_SIZE_WAIT_S = 10                   # how long the second window may take to show a picture before it is recorded
BOUNDS_SCALE_INNER = "OBS_BOUNDS_SCALE_INNER"
WGC_METHOD = 2   # Windows Graphics Capture
BLACK_MEAN = 2.0   # source picture darker than this on average = nothing captured
PATH_CHARS = 520   # room for a long exe path (2x MAX_PATH)

def load_state():
    try:
        return json.load(open(STATE))
    except (OSError, ValueError):
        return {}

def save_state(s):
    json.dump(s, open(STATE, "w"), indent=1)

def obs_running():
    out = subprocess.run(["tasklist", "/fi", "imagename eq obs64.exe", "/nh"], capture_output=True, creationflags=NO_WINDOW, text=True).stdout
    return "obs64.exe" in out.lower()

def connect():
    import obsws_python as obs
    cfg = json.load(open(OBS_CFG))
    if not cfg.get("server_enabled"):
        sys.exit("OBS WebSocket server is off (Tools -> WebSocket Server Settings)")
    last = None
    for _ in range(CONNECT_TRIES):
        try:
            return obs.ReqClient(host="localhost", port=cfg["server_port"], password=cfg.get("server_password", ""), timeout=5)
        except Exception as e:  # OBS still starting
            last = e
            time.sleep(CONNECT_GAP_S)
    sys.exit(f"could not reach OBS: {last}")

def obs_stuck():
    """OBS 31+ asks "OBS Studio Crash Detected" (normal or safe mode?) after an unclean close, and
    --disable-shutdown-check does not stop it; until someone answers, its WebSocket never comes up (2026-10-17)."""
    out = subprocess.run(["tasklist", "/v", "/fi", "imagename eq obs64.exe", "/fo", "csv", "/nh"],
                         capture_output=True, creationflags=NO_WINDOW, text=True).stdout
    return CRASH_TITLE.lower() in out.lower()

def clear_crash_marks():
    """with no OBS running, every run marker left in OBS's .sentinel folder is from a run that ended uncleanly"""
    folder = os.path.join(os.path.expandvars("%APPDATA%"), "obs-studio", ".sentinel")
    if obs_running() or not os.path.isdir(folder):
        return
    for name in os.listdir(folder):
        if name.startswith("run_"):
            try:
                os.remove(os.path.join(folder, name))
            except OSError:
                pass

def ensure_obs(state):
    if obs_running() and obs_stuck():   # only waiting on the crash question, so recording nothing: start it again
        subprocess.run(["taskkill", "/f", "/im", "obs64.exe"], capture_output=True, creationflags=NO_WINDOW)
        time.sleep(2)
    if not obs_running():
        clear_crash_marks()
        subprocess.Popen([OBS_EXE, "--minimize-to-tray", "--disable-shutdown-check", "--disable-updater"],
                         cwd=os.path.dirname(OBS_EXE))
        state["we_started_obs"] = True
        time.sleep(3)
    return connect()

def window_spec(exe, want=None, sim=False, must=True):
    """OBS's 'title:class:exe' string for the biggest visible top-level window of that exe (':' escaped as #3A).
    want: a window class to require, or '!<class>' to require any OTHER class.
    sim: True = only the OpenXR Simulator's preview (title starts with SIM_TITLE); False = never it, so the preview
    (it lives in the game's own process and can be the bigger window) is never taken for the game; None = either.
    must: False = return None instead of stopping when there is no such window."""
    u = ctypes.windll.user32; k = ctypes.windll.kernel32
    found = []
    @ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    def cb(h, _):
        if not u.IsWindowVisible(h): return True
        pid = W.DWORD(); u.GetWindowThreadProcessId(h, ctypes.byref(pid))
        hp = k.OpenProcess(0x1000, False, pid.value)
        if not hp: return True
        buf = ctypes.create_unicode_buffer(PATH_CHARS); n = W.DWORD(PATH_CHARS)
        ok = k.QueryFullProcessImageNameW(hp, 0, buf, ctypes.byref(n)); k.CloseHandle(hp)
        if ok and os.path.basename(buf.value).lower() == exe.lower():
            t = ctypes.create_unicode_buffer(256); c = ctypes.create_unicode_buffer(256); r = W.RECT()
            u.GetWindowTextW(h, t, 256); u.GetClassNameW(h, c, 256); u.GetClientRect(h, ctypes.byref(r))
            sim_ok = sim is None or t.value.startswith(SIM_TITLE) == sim
            if sim_ok and (want is None or (want.startswith("!") and c.value != want[1:]) or c.value == want):
                found.append((r.right * r.bottom, t.value, c.value))
        return True
    u.EnumWindows(cb, 0)
    if not found:
        if not must: return None
        sys.exit(f"no visible {'simulator preview ' if sim else ''}window for {exe} ({want or 'any class'}): start it first")
    _, title, cls = max(found)
    esc = lambda s: s.replace(":", "#3A")
    return f"{esc(title)}:{esc(cls)}:{exe}"

def wait_ready(cl):
    """OBS answers 207 'not ready' for a few seconds after it starts."""
    for _ in range(CONNECT_TRIES):
        try:
            return cl.get_profile_list()
        except Exception as e:
            if "207" not in str(e): raise
            time.sleep(CONNECT_GAP_S)
    sys.exit("OBS never became ready")

def ensure_setup(cl, state):
    cur = wait_ready(cl)
    if "prev_profile" not in state:   # remember the user's own setup, never our own (a half-finished run leaves ours active)
        prof = cur.current_profile_name
        coll = cl.get_scene_collection_list().current_scene_collection_name
        state["prev_profile"] = prof if prof != PROFILE else "Untitled"
        state["prev_collection"] = coll if coll != COLLECTION else "Untitled"
    if PROFILE not in cur.profiles:
        cl.create_profile(PROFILE)
    elif cur.current_profile_name != PROFILE:
        cl.set_current_profile(PROFILE)
    cols = cl.get_scene_collection_list()
    if COLLECTION not in cols.scene_collections:
        cl.create_scene_collection(COLLECTION)
    elif cols.current_scene_collection_name != COLLECTION:
        cl.set_current_scene_collection(COLLECTION)
    time.sleep(1)
    for cat, name, val in [("Output", "Mode", "Simple"), ("SimpleOutput", "RecEncoder", "nvenc"),
                           ("SimpleOutput", "RecQuality", "Small"), ("SimpleOutput", "RecFormat2", "hybrid_mp4"),
                           ("Output", "FilenameFormatting", "%CCYY-%MM-%DD_%hh-%mm-%ss")]:
        cl.set_profile_parameter(cat, name, val)
    cl.set_video_settings(numerator=FPS, denominator=1, base_width=VIDEO_W, base_height=VIDEO_H,
                          out_width=VIDEO_W, out_height=VIDEO_H)
    scenes = [s["sceneName"] for s in cl.get_scene_list().scenes]
    if SCENE not in scenes:
        cl.create_scene(SCENE)
    cl.set_current_program_scene(SCENE)

def point_sources(cl, spec):
    names = [i["inputName"] for i in cl.get_input_list().inputs]
    vid = {"window": spec, "method": WGC_METHOD, "cursor": False, "client_area": True}
    aud = {"window": spec, "priority": 2}   # 2 = match by exe
    if SRC_VIDEO in names:
        cl.set_input_settings(SRC_VIDEO, vid, True)
    else:
        cl.create_input(SCENE, SRC_VIDEO, "window_capture", vid, True)
    if SRC_AUDIO in names:
        cl.set_input_settings(SRC_AUDIO, aud, True)
    else:
        cl.create_input(SCENE, SRC_AUDIO, "wasapi_process_output_capture", aud, True)
    item = cl.get_scene_item_id(SCENE, SRC_VIDEO).scene_item_id
    cl.set_scene_item_transform(SCENE, item, {"boundsType": BOUNDS_SCALE_INNER, "boundsWidth": VIDEO_W,
                                              "boundsHeight": VIDEO_H, "positionX": 0, "positionY": 0})

def mirror_ready(cl):
    """True when OBS has the OpenXR OBS Mirror source loaded (its plugin is installed)"""
    try:
        return MIRROR_KIND in cl.get_input_kind_list(False).input_kinds
    except Exception:
        return False

def point_second(cl, spec, folder, label, kind="window_capture"):
    """The second source: in the game scene but off the picture, + a Source Record filter that writes its own file.
    kind MIRROR_KIND records the headset view instead of a window (spec is then unused). True when it records."""
    names = [i["inputName"] for i in cl.get_input_list().inputs]
    if spec is None and kind == "window_capture":
        if SRC_SECOND in names:
            cl.set_source_filter_settings(SRC_SECOND, SECOND_FILTER, {"record_mode": SR_OFF}, True)
            cl.set_scene_item_enabled(SCENE, cl.get_scene_item_id(SCENE, SRC_SECOND).scene_item_id, False)
        return False
    vid = {"window": spec, "method": WGC_METHOD, "cursor": False, "client_area": True} if kind == "window_capture" else {}
    if SRC_SECOND in names and cl.get_input_settings(SRC_SECOND).input_kind != kind:
        cl.remove_input(SRC_SECOND)     # the second source changes kind (a window <-> the headset view)
        time.sleep(0.5)
        names.remove(SRC_SECOND)
    if SRC_SECOND in names:
        cl.set_input_settings(SRC_SECOND, vid, True)
    else:
        cl.create_input(SCENE, SRC_SECOND, kind, vid, True)
    item = cl.get_scene_item_id(SCENE, SRC_SECOND).scene_item_id
    cl.set_scene_item_transform(SCENE, item, {"positionX": OFF_CANVAS_X, "positionY": 0})
    cl.set_scene_item_enabled(SCENE, item, True)
    # a window capture with no picture yet is 0x0, and Source Record starting NVENC on it divides by zero inside
    # obs-nvenc (crashes 2026-10-17 18:20 and 18:47, both at the simulator window's start): wait for a size first
    t_end = time.time() + SR_SIZE_WAIT_S
    while time.time() < t_end:
        tr = cl.get_scene_item_transform(SCENE, item).scene_item_transform
        if tr.get("sourceWidth", 0) > 0 and tr.get("sourceHeight", 0) > 0: break
        time.sleep(0.5)
    else:
        print(f"second recording skipped: {SRC_SECOND} showed no picture in {SR_SIZE_WAIT_S} s")
        cl.set_scene_item_enabled(SCENE, item, False)
        return False
    rec = {"record_mode": SR_RECORD_WHILE_RECORDING, "path": folder, "rec_format": "mp4", "encoder": SR_ENCODER,
           "filename_formatting": f"{label}_second_%CCYY-%MM-%DD_%hh-%mm-%ss"}
    if SECOND_FILTER in [f["filterName"] for f in cl.get_source_filter_list(SRC_SECOND).filters]:
        cl.set_source_filter_settings(SRC_SECOND, SECOND_FILTER, rec, True)
    else:
        cl.create_source_filter(SRC_SECOND, SECOND_FILTER, "source_record_filter", rec)
    return True

def split_target(t):
    exe, _, want = t.partition(":")
    return exe, (want or None)

def cmd_start(exe, label, project, cls=None, also=None):
    state = load_state()
    cl = ensure_obs(state)
    ensure_setup(cl, state)
    save_state(state)   # so `done` can put the user's own setup back even if the start fails below
    folder = os.path.join(REC_ROOT, project)
    os.makedirs(folder, exist_ok=True)
    cl.set_profile_parameter("SimpleOutput", "FilePath", folder)
    cl.set_profile_parameter("Output", "FilenameFormatting", f"{label}_%CCYY-%MM-%DD_%hh-%mm-%ss")
    point_sources(cl, window_spec(exe, cls))
    sim = None if also else window_spec(exe, sim=True, must=False)   # the simulator preview, if it is up already
    # no simulator preview: the headset view through the OBS Mirror, when that is installed and shows a picture
    mirror = not also and not sim and mirror_ready(cl) and point_second(cl, None, folder, label, kind=MIRROR_KIND)
    if not mirror:
        point_second(cl, window_spec(*split_target(also), sim=None) if also else sim, folder, label)
    start_ms = start_recording(cl)
    if sim: also = SIM_LABEL
    if mirror: also = MIRROR_LABEL
    state["recording"] = {"exe": exe, "label": label, "folder": folder, "also": also, "since": time.strftime("%H:%M:%S"),
                          "project": project, "start_ms": start_ms}
    save_state(state)
    print(f"RECORDING {exe}{' + ' + also if also else ''} -> {folder} ({label})")
    start_guard()
    if not also:
        start_sim_watch(exe)
        print(f"  watching for the OpenXR Simulator preview (up to {SIM_WAIT_S // 60} min): it is added by itself if it opens")

def record_start_ms(cl):
    """when this recording's first frame was, on the PC's clock (ms since 1970): now, less how long OBS has run it"""
    try:
        return int(time.time() * 1000 - (cl.get_record_status().output_duration or 0))
    except Exception:
        return int(time.time() * 1000)

def start_recording(cl):
    """start a fresh recording; returns when its first frame was (record_start_ms)"""
    if cl.get_record_status().output_active:
        write_sidecars(cl.stop_record().output_path, load_state().get("recording", {})); time.sleep(1)
    cl.start_record()
    for _ in range(START_CHECKS):   # OBS can accept the request and never start (seen 2026-10-08 during a driver update)
        time.sleep(START_CHECK_GAP_S)
        if cl.get_record_status().output_active: return record_start_ms(cl)
    sys.exit("OBS took the start request but is NOT recording: restart OBS (or the PC after a driver update) and retry")

# ---- The OpenXR Simulator's preview, recorded by itself (asked for by the maintainer, 2026-10-16). The preview opens
# only once the game's headset session starts, often well after the recording began, so `start` leaves a quiet
# watcher behind: when the preview appears it is added as the second window and the recording is restarted, so the
# game file and the "_second" preview file begin together (the path tested 2026-10-07; whether Source Record would
# pick up a window added mid-recording is not known). The first game file (launch to session start) is kept. The
# watcher ends when the recording stops or after SIM_WAIT_S.
def start_sim_watch(exe):
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    py = pyw if os.path.isfile(pyw) else sys.executable
    subprocess.Popen([py, os.path.abspath(__file__), "simwatch", exe], close_fds=True,
                     creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP)

def cmd_simwatch(exe):
    deadline = time.time() + SIM_WAIT_S
    while time.time() < deadline:
        rec = load_state().get("recording")
        if not rec or rec.get("exe", "").lower() != exe.lower() or rec.get("also"): return
        spec = window_spec(exe, sim=True, must=False)
        if spec:
            cl = connect()
            point_second(cl, spec, rec["folder"], rec["label"])
            start_ms = start_recording(cl)
            state = load_state()
            state["recording"]["start_ms"] = start_ms
            state["recording"]["also"] = SIM_LABEL
            state["recording"]["sim_since"] = time.strftime("%H:%M:%S")
            save_state(state)
            return
        time.sleep(SIM_POLL_S)

# ---- The guard (asked for by the maintainer, 2026-10-17: "can you add some sort of a checker that detects when obs
# stops mid recording?"). That day OBS crashed twice mid-session inside the Source Record add-on, and the crash
# boxes sat on the maintainer's screen while the session went on unrecorded. `start` leaves one guard per recording:
# every GUARD_POLL_S it asks whether OBS is still open, still recording and free of crash boxes. When it is not, the
# guard writes the break into BREAKS_LOG (the jitter reports quote it), closes the crash boxes, and starts a fresh
# recording if the game is still open (that start leaves its own guard). It ends with the recording.
def start_guard():
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    py = pyw if os.path.isfile(pyw) else sys.executable
    subprocess.Popen([py, os.path.abspath(__file__), "guard"], close_fds=True,
                     creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP)

def crash_boxes():
    """titles of OBS's crash boxes open on the screen right now"""
    u, found = ctypes.windll.user32, []
    def cb(h, _):
        if u.IsWindowVisible(h):
            buf = ctypes.create_unicode_buffer(256)
            u.GetWindowTextW(h, buf, 256)
            if buf.value in CRASH_BOXES: found.append(buf.value)
        return True
    u.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, W.HWND, W.LPARAM)(cb), 0)
    return found

def log_break(rec, why, restarted):
    line = (f"{int(time.time() * 1000)}\t{rec.get('project', '')}\t{rec.get('start_ms', 0)}\t{why}\t"
            f"{'restarted' if restarted else 'not restarted'}\n")
    try:
        with open(BREAKS_LOG, "a", encoding="utf-8") as f: f.write(line)
    except OSError:
        pass

def guard_check(misses):
    """(why the recording broke or None, misses): OBS gone, a crash box up, or not recording; a WebSocket that does
    not answer counts only after GUARD_MISSES polls in a row (OBS can be busy for a moment)"""
    boxes = crash_boxes()
    if boxes: return "OBS showed " + " and ".join(f'"{b}"' for b in boxes), 0
    if not obs_running(): return "OBS closed", 0
    try:
        import obsws_python as obs
        cfg = json.load(open(OBS_CFG))
        cl = obs.ReqClient(host="localhost", port=cfg["server_port"], password=cfg.get("server_password", ""), timeout=5)
        try:
            return (None if cl.get_record_status().output_active else "OBS stopped recording"), 0
        finally:
            cl.disconnect()   # one left open each poll piled up in OBS (2026-10-17)
    except Exception:
        misses += 1
        return ("OBS stopped answering" if misses >= GUARD_MISSES else None), misses

def cmd_guard():
    rec = load_state().get("recording")
    if not rec: return
    mine, misses = rec.get("start_ms"), 0
    while True:
        time.sleep(GUARD_POLL_S)
        rec = load_state().get("recording")
        if not rec or rec.get("start_ms") != mine and not rec.get("sim_since"): return   # stopped, or a newer start
        if rec.get("sim_since"): mine = rec.get("start_ms")   # the simulator watcher restarted it on purpose
        why, misses = guard_check(misses)
        if not why: continue
        if crash_boxes() or not obs_running() or why == "OBS stopped answering":
            subprocess.run(["taskkill", "/f", "/im", "obs64.exe"], capture_output=True, creationflags=NO_WINDOW)   # clears the boxes too
            time.sleep(2)
        game_open = window_spec(rec.get("exe", ""), must=False) is not None
        if game_open:
            state = load_state(); state.pop("recording", None); save_state(state)
            r = subprocess.run([sys.executable, os.path.abspath(__file__), "start", rec["exe"], rec["label"],
                                "--game", rec.get("project", "")], capture_output=True, text=True, timeout=GUARD_RESTART_S)
            log_break(rec, why, r.returncode == 0)
        else:
            state = load_state(); state.pop("recording", None); save_state(state)
            log_break(rec, why, False)
        return

def cmd_sim(exe):
    """Is the OpenXR Simulator's preview up for this game? (what the watcher looks for)"""
    spec = window_spec(exe, sim=True, must=False)
    print(f"SIM PREVIEW {spec}" if spec else f"no simulator preview window for {exe}")

def cmd_check():
    """Is the game window source showing a picture? Prints PICTURE or BLACK with the mean brightness (0-255)."""
    import base64, io
    cl = connect()
    if not cl.get_record_status().output_active:
        print("not recording"); return
    shot = cl.get_source_screenshot(SRC_VIDEO, "png", 64, 36, -1).image_data
    data = base64.b64decode(shot.split(",", 1)[1])
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data)).convert("L"); px = list(im.get_flattened_data() if hasattr(im, "get_flattened_data") else im.getdata())
        mean = sum(px) / max(1, len(px))
    except ImportError:
        mean = 255.0 if len(data) > 400 else 0.0   # no Pillow: a flat black png compresses to almost nothing
    print(f"{'BLACK' if mean < BLACK_MEAN else 'PICTURE'} {mean:.1f}")

def cmd_repoint(exe):
    """Point the sources at the game's window again, without stopping the recording."""
    cl = connect()
    state = load_state(); rec = state.get("recording", {})
    point_sources(cl, window_spec(exe, None))
    print(f"REPOINTED {exe} (recording {'on' if cl.get_record_status().output_active else 'off'}{', since ' + rec['since'] if rec.get('since') else ''})")

def second_file(rec, after_ms):
    """the newest '_second_' file of this recording, if it was written after `after_ms`"""
    folder = rec.get("folder")
    if not rec.get("also") or not folder or not os.path.isdir(folder): return None
    second = sorted((f for f in os.listdir(folder) if f.startswith(rec["label"] + "_second_") and f.endswith(".mp4")),
                    key=lambda f: os.path.getmtime(os.path.join(folder, f)))
    if second and os.path.getmtime(os.path.join(folder, second[-1])) * 1000 >= after_ms:
        return os.path.join(folder, second[-1])
    return None

def write_sidecars(path, rec, stop_ms=None):
    """<file>.json beside the main file and the second file: when each began and ended, on the PC's clock"""
    if not path or not rec.get("start_ms"): return None
    stop_ms = stop_ms or int(time.time() * 1000)
    time.sleep(2)   # Source Record closes its file a moment after the main one
    second = second_file(rec, rec["start_ms"])
    for f, window in ((path, "game window"), (second, rec.get("also"))):
        if not f: continue
        try:
            json.dump({"start_ms": rec["start_ms"], "stop_ms": stop_ms, "exe": rec.get("exe"), "label": rec.get("label"),
                       "project": rec.get("project"), "window": window, "file": os.path.basename(f),
                       "fps": FPS}, open(f + ".json", "w"), indent=1)
        except OSError:
            pass
    return second

def cmd_stop():
    state = load_state()
    cl = connect()
    if not cl.get_record_status().output_active:
        print("not recording"); return
    stop_ms = int(time.time() * 1000)
    path = cl.stop_record().output_path
    rec = state.pop("recording", {}); save_state(state)
    print(f"SAVED {path}")
    if rec.get("also"):
        second = write_sidecars(path, rec, stop_ms)
        print(f"SAVED {second}" if second else "SECOND FILE MISSING")
    else:
        write_sidecars(path, rec, stop_ms)

def cmd_done():
    state = load_state()
    if obs_running():
        cl = connect()
        if cl.get_record_status().output_active:
            stop_ms = int(time.time() * 1000)
            path = cl.stop_record().output_path
            write_sidecars(path, state.get("recording", {}), stop_ms)
            print("SAVED", path)
        if state.get("prev_collection"):
            # Source Record keeps its output open, and OBS then quits with "Source Cleanup Error" while it switches
            # collections (2026-10-17): take the add-on's filter off first
            try: cl.remove_source_filter(SRC_SECOND, SECOND_FILTER); time.sleep(1)
            except Exception: pass
            cl.set_current_scene_collection(state["prev_collection"])
        if state.get("prev_profile"): cl.set_current_profile(state["prev_profile"])
        time.sleep(1)
        if state.get("we_started_obs"):
            subprocess.run(["taskkill", "/im", "obs64.exe"], capture_output=True, creationflags=NO_WINDOW)
            for _ in range(CLOSE_CHECKS):   # started minimised to the tray, OBS can ignore a polite close
                time.sleep(CLOSE_CHECK_GAP_S)
                if not obs_running(): break
            else:
                subprocess.run(["taskkill", "/f", "/im", "obs64.exe"], capture_output=True, creationflags=NO_WINDOW)
    print("OBS back to", state.get("prev_profile", "its own profile"))
    try: os.remove(STATE)
    except OSError: pass

def main():
    a = sys.argv[1:]
    if not a: sys.exit(__doc__)
    if a[0] == "start" and len(a) >= 3:
        project = a[a.index("--game") + 1] if "--game" in a else os.path.splitext(a[1])[0]
        opt = lambda k: a[a.index(k) + 1] if k in a else None
        cmd_start(a[1], a[2], project, opt("--class"), opt("--also"))
    elif a[0] == "simwatch" and len(a) >= 2: cmd_simwatch(a[1])
    elif a[0] == "guard": cmd_guard()
    elif a[0] == "sim" and len(a) >= 2: cmd_sim(a[1])
    elif a[0] == "stop": cmd_stop()
    elif a[0] == "check": cmd_check()
    elif a[0] == "repoint" and len(a) >= 2: cmd_repoint(a[1])
    elif a[0] == "done": cmd_done()
    elif a[0] == "status": print(json.dumps(load_state(), indent=1))
    else: sys.exit(__doc__)

main()
