r"""obs-rec.py - record ONLY a game's window (and only its sound) during a test, with OBS (asked for by the maintainer, 2026-10-07).

    python obs-rec.py start <exe> <label> [--game <project>] [--class <cls>] [--also <exe>[:<cls>|:!<cls>]]
                                                                start recording that game's window
    python obs-rec.py stop                                      stop; prints the file it wrote
    python obs-rec.py done                                      put your own OBS profile back; close OBS if we opened it
    python obs-rec.py status
    python obs-rec.py check                                     is the game window showing a picture? PICTURE / BLACK
    python obs-rec.py repoint <exe>                             point the capture at that window again, still recording

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

Needs: OBS 28+ with its WebSocket server on (Tools -> WebSocket Server Settings; the password is read from OBS's own
config file, never copied anywhere), and `pip install obsws-python`.
"""
import ctypes, ctypes.wintypes as W, json, os, subprocess, sys, time

OBS_EXE = r"C:\Program Files\obs-studio\bin\64bit\obs64.exe"
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
SRC_VIDEO, SRC_AUDIO = "game window", "game sound"
SRC_SECOND, SECOND_FILTER = "second window", "record second window"
OFF_CANVAS_X = 50000   # the second window sits in the game scene but far off the picture: drawn, never seen
SR_RECORD_WHILE_RECORDING, SR_OFF = 3, 0          # Source Record's record_mode values
SR_ENCODER = "obs_nvenc_h264_tex"
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
    out = subprocess.run(["tasklist", "/fi", "imagename eq obs64.exe", "/nh"], capture_output=True, text=True).stdout
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

def ensure_obs(state):
    if not obs_running():
        subprocess.Popen([OBS_EXE, "--minimize-to-tray", "--disable-shutdown-check", "--disable-updater"],
                         cwd=os.path.dirname(OBS_EXE))
        state["we_started_obs"] = True
        time.sleep(3)
    return connect()

def window_spec(exe, want=None):
    """OBS's 'title:class:exe' string for the biggest visible top-level window of that exe (':' escaped as #3A).
    want: a window class to require, or '!<class>' to require any OTHER class."""
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
            if want is None or (want.startswith("!") and c.value != want[1:]) or c.value == want:
                found.append((r.right * r.bottom, t.value, c.value))
        return True
    u.EnumWindows(cb, 0)
    if not found:
        sys.exit(f"no visible window for {exe} ({want or 'any class'}): start it first")
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

def point_second(cl, spec, folder, label):
    """The second window: in the game scene but off the picture, + a Source Record filter that writes its own file."""
    names = [i["inputName"] for i in cl.get_input_list().inputs]
    if spec is None:
        if SRC_SECOND in names:
            cl.set_source_filter_settings(SRC_SECOND, SECOND_FILTER, {"record_mode": SR_OFF}, True)
            cl.set_scene_item_enabled(SCENE, cl.get_scene_item_id(SCENE, SRC_SECOND).scene_item_id, False)
        return
    vid = {"window": spec, "method": WGC_METHOD, "cursor": False, "client_area": True}
    if SRC_SECOND in names:
        cl.set_input_settings(SRC_SECOND, vid, True)
    else:
        cl.create_input(SCENE, SRC_SECOND, "window_capture", vid, True)
    item = cl.get_scene_item_id(SCENE, SRC_SECOND).scene_item_id
    cl.set_scene_item_transform(SCENE, item, {"positionX": OFF_CANVAS_X, "positionY": 0})
    cl.set_scene_item_enabled(SCENE, item, True)
    rec = {"record_mode": SR_RECORD_WHILE_RECORDING, "path": folder, "rec_format": "mp4", "encoder": SR_ENCODER,
           "filename_formatting": f"{label}_second_%CCYY-%MM-%DD_%hh-%mm-%ss"}
    if SECOND_FILTER in [f["filterName"] for f in cl.get_source_filter_list(SRC_SECOND).filters]:
        cl.set_source_filter_settings(SRC_SECOND, SECOND_FILTER, rec, True)
    else:
        cl.create_source_filter(SRC_SECOND, SECOND_FILTER, "source_record_filter", rec)

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
    point_second(cl, window_spec(*split_target(also)) if also else None, folder, label)
    if cl.get_record_status().output_active:
        cl.stop_record(); time.sleep(1)
    cl.start_record()
    for _ in range(START_CHECKS):   # OBS can accept the request and never start (seen 2026-10-08 during a driver update)
        time.sleep(START_CHECK_GAP_S)
        if cl.get_record_status().output_active: break
    else:
        sys.exit("OBS took the start request but is NOT recording: restart OBS (or the PC after a driver update) and retry")
    state["recording"] = {"exe": exe, "label": label, "folder": folder, "also": also, "since": time.strftime("%H:%M:%S")}
    save_state(state)
    print(f"RECORDING {exe}{' + ' + also if also else ''} -> {folder} ({label})")

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

def cmd_stop():
    state = load_state()
    cl = connect()
    if not cl.get_record_status().output_active:
        print("not recording"); return
    path = cl.stop_record().output_path
    rec = state.pop("recording", {}); save_state(state)
    print(f"SAVED {path}")
    if rec.get("also"):
        time.sleep(2)
        folder = rec["folder"]
        second = sorted((f for f in os.listdir(folder) if f.startswith(rec["label"] + "_second_")),
                        key=lambda f: os.path.getmtime(os.path.join(folder, f)))
        print(f"SAVED {os.path.join(folder, second[-1])}" if second else "SECOND FILE MISSING")

def cmd_done():
    state = load_state()
    if obs_running():
        cl = connect()
        if cl.get_record_status().output_active:
            print("SAVED", cl.stop_record().output_path)
        if state.get("prev_collection"): cl.set_current_scene_collection(state["prev_collection"])
        if state.get("prev_profile"): cl.set_current_profile(state["prev_profile"])
        time.sleep(1)
        if state.get("we_started_obs"):
            subprocess.run(["taskkill", "/im", "obs64.exe"], capture_output=True)
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
    elif a[0] == "stop": cmd_stop()
    elif a[0] == "check": cmd_check()
    elif a[0] == "repoint" and len(a) >= 2: cmd_repoint(a[1])
    elif a[0] == "done": cmd_done()
    elif a[0] == "status": print(json.dumps(load_state(), indent=1))
    else: sys.exit(__doc__)

main()
