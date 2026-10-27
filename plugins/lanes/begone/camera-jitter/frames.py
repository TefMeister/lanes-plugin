"""frames.py - line a filed jitter log up with the recording of the same session, and cut its jittery seconds out as
frames (0.76.0, 2026-10-17, asked for by the maintainer: "automated recordings and begone tools working in tandem, so
that at the timestamp of a jitter, you can also see the recording frame by frame where and how the jitter happened").

    python frames.py attach <run folder> [--log <file.jl>] [--game <project>]
        find the recording that covers this log, cut the first MAX_SPANS jittery stretches and one smooth turning
        second, write <run folder>/recording.json and an "On the recording" part at the end of report.md.
        Prints one line. Safe to run again (it replaces its own part).
    python frames.py cut <run folder> <from s> <to s> [--full]
        cut any stretch of the log, by log seconds; --full keeps the recording's own size instead of FRAME_WIDTH
    python frames.py where <run folder>
        which recording, and where the frames are

HOW THE TWO LINE UP. Both carry the PC's clock: the log's first line has `wall_ms` (jitterlog.h since 0.76.0; an
older log uses the moment its file was created, which is the same moment to within a millisecond or so), and every
file obs-rec.py saves has a `<file>.json` beside it with the moment its first frame was (`start_ms`). So log second
t is recording second (wall_ms - start_ms) / 1000 + t. Both clocks are the PC's, so they agree to about one frame;
each cut is padded by PAD_S either side.

WHERE THE FRAMES GO: beside the recordings, <recordings>/<project>/begone-frames/<run>/<stretch>/: f_001.jpg ...,
sheet.jpg (all of them on one picture, in order) and frames.txt (each frame's log second and recording time). They
stay off GitHub; the report names them by those folder names only.
"""
import glob
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import begone_common as bc  # noqa: E402

BREAKS_LOG = os.path.join(os.environ.get("LOCALAPPDATA", ""), "obs-rec-breaks.log")   # obs-rec's guard writes it
BREAK_SLACK_S = 30       # a break noted this soon after the log ended still belongs to its session
MAX_SPANS = 3            # jittery stretches cut per session
MAX_SPAN_S = 2.0         # a longer stretch is cut to its first this-many seconds
PAD_S = 0.25             # seconds added before and after each cut, for the clocks' small disagreement
FRAME_WIDTH = 640        # frames are scaled to this width (the sheet uses SHEET_TILE_W)
SHEET_COLS, SHEET_TILE_W = 5, 384  # the sheet: this many a row, each this wide
SHEET_MAX = 30           # frames on one sheet (half a second at 60 fps), from the start of the stretch
SBS_ASPECT = 3.0         # a picture wider than this is two eyes side by side: frames show the left eye only
JPEG_Q = 4               # ffmpeg -q:v (2 best .. 31 worst)
DEFAULT_FPS = 60
FFMPEG_TIMEOUT_S = 120
PART_HEAD = "## On the recording"
MOTION_NEAR = 4          # a frame's change is judged against the median of this many frames either side
HELD_SHARE = 0.35        # changed less than this share of its neighbours while they moved: the picture HELD
JUMP_SHARE = 1.6         # changed more than this many times its neighbours: the picture JUMPED (caught up)
MOVING_MIN = 1.0         # neighbours changing less than this (0-255 grey levels) are not moving: nothing judged


def rec_root():
    """the recordings folder, the same way obs-rec.py finds it"""
    c = bc.read_conf()
    if c.get("recordings"):
        return os.path.expandvars(os.path.expanduser(c["recordings"]))
    if c.get("transfer"):
        return os.path.join(os.path.expandvars(os.path.expanduser(c["transfer"])), "Videos")
    return os.path.join(os.path.expanduser("~"), "Videos", "Lanes recordings")


def ffmpeg():
    """LANES_FFMPEG, else PATH, else winget's own package folder: the rider may have started before winget put
    ffmpeg on PATH (seen on the home PC 2026-10-26: "ffmpeg is not installed" with ffmpeg installed)"""
    found = os.environ.get("LANES_FFMPEG") or shutil.which("ffmpeg")
    if found:
        return found
    pkgs = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages")
    hits = sorted(glob.glob(os.path.join(pkgs, "Gyan.FFmpeg*", "*", "bin", "ffmpeg.exe")))
    return hits[-1] if hits else None


def log_wall_ms(log):
    """when the log's second 0 was, on the PC's clock (ms since 1970)"""
    try:
        with open(log, encoding="utf-8", errors="replace") as f:
            head = dict(kv.split("=", 1) for kv in f.readline().split()[1:] if "=" in kv)
        if head.get("wall_ms", "").isdigit():
            return int(head["wall_ms"]), "log clock"
    except OSError:
        return None, None
    st = os.stat(log)
    return int(getattr(st, "st_birthtime", st.st_ctime) * 1000), "log file made"


def load_json(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def summary(run):
    return load_json(os.path.join(run, "summary.json")) or {}


def recordings_for(game, wall_ms, seconds):
    """[(video path, sidecar)] of every finished recording that covers part of the log, the headset view first"""
    root, end = rec_root(), wall_ms + seconds * 1000
    folders = [os.path.join(root, game)] if game else []
    folders += [d for d in glob.glob(os.path.join(root, "*")) if os.path.isdir(d) and d not in folders]
    found = []
    for d in folders:
        for side in glob.glob(os.path.join(d, "*.mp4.json")):
            j = load_json(side)
            if j and j.get("start_ms") and j.get("stop_ms") and j["start_ms"] < end and j["stop_ms"] > wall_ms:
                found.append((side[:-len(".json")], j))
        if found:
            break
    return sorted(found, key=lambda v: 0 if (v[1].get("window") or "").startswith("OpenXR") else 1)


def stretches(s, covered=None):
    """[(label, from s, to s)]: the first MAX_SPANS jittery stretches, then one smooth turning second; with covered
    = (from s, to s), only seconds the recording holds (2026-10-17: a recording that began six minutes into the log
    had its three cuts taken from before it started, all empty)"""
    windows = s.get("windows", [])
    if covered:
        windows = [w for w in windows if covered[0] <= float(w.get("at_s", 0)) and float(w.get("at_s", 0)) + 1 <= covered[1]]
    out, start, last = [], None, None
    for w in windows + [{"at_s": -1, "kind": "end"}]:
        t, k = int(w.get("at_s", 0)), w.get("kind")
        if k == "JITTER":
            start = t if start is None else start
            last = t
        elif start is not None:
            out.append((f"jitter_{start}-{last + 1}s", start, min(last + 1, start + MAX_SPAN_S)))
            start = None
    out = out[:MAX_SPANS]
    smooth = next((int(w["at_s"]) for w in windows if w.get("kind") == "smooth"), None)
    if smooth is not None:
        out.append((f"smooth_{smooth}-{smooth + 1}s", smooth, smooth + 1))
    return out


def cut(video, side, wall_ms, a, b, out, full=False):
    """frames of log seconds a..b (padded) from one recording into `out`; returns the frame count, or a reason"""
    exe = ffmpeg()
    if not exe:
        return "ffmpeg is not installed"
    fps = side.get("fps") or DEFAULT_FPS
    offset = (wall_ms - side["start_ms"]) / 1000.0          # recording second of log second 0
    t0 = max(0.0, offset + a - PAD_S)
    dur = (b - a) + 2 * PAD_S
    if t0 >= (side["stop_ms"] - side["start_ms"]) / 1000.0:
        return "the recording had stopped by then"
    os.makedirs(out, exist_ok=True)
    for old in glob.glob(os.path.join(out, "f_*.jpg")):
        os.remove(old)
    left_eye = f"crop='if(gt(iw/ih,{SBS_ASPECT}),iw/2,iw)':ih:0:0"
    scale = [] if full else ["-vf", f"{left_eye},scale={FRAME_WIDTH}:-2"]
    r = subprocess.run([exe, "-v", "error", "-ss", f"{t0:.3f}", "-i", video, "-t", f"{dur:.3f}", *scale,
                        "-q:v", str(JPEG_Q), os.path.join(out, "f_%03d.jpg")], capture_output=True, text=True,
                       timeout=FFMPEG_TIMEOUT_S)
    frames = sorted(glob.glob(os.path.join(out, "f_*.jpg")))
    if r.returncode != 0 or not frames:
        return "ffmpeg cut nothing: " + (r.stderr.strip().splitlines() or ["?"])[-1][:120]
    first = round(PAD_S * fps) if t0 > 0 else 0              # the sheet starts where the stretch does
    on_sheet = min(SHEET_MAX, max(1, len(frames) - first))
    rows = -(-on_sheet // SHEET_COLS)
    subprocess.run([exe, "-v", "error", "-y", "-ss", f"{t0 + first / fps:.3f}", "-i", video, "-vf",
                    f"{left_eye},scale={SHEET_TILE_W}:-2,tile={SHEET_COLS}x{rows}", "-frames:v", "1", "-q:v",
                    str(JPEG_Q), os.path.join(out, "sheet.jpg")], capture_output=True, timeout=FFMPEG_TIMEOUT_S)
    moved = motion(frames)
    held = sum(1 for _, t in moved if t == "HELD")
    jumps = sum(1 for _, t in moved if t == "JUMP")
    with open(os.path.join(out, "frames.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write(f"recording {os.path.basename(video)}; log second 0 = recording {offset:.3f} s\n")
        f.write(f"sheet.jpg: f_{first + 1:03d} to f_{first + on_sheet:03d}, {SHEET_COLS} a row, left to right, top to "
                f"bottom (a side-by-side picture shows its left eye)\n")
        if moved:
            f.write(f"on screen: {held} pictures HELD while the view moved, {jumps} JUMPED (change = grey levels "
                    f"that differ from the frame before)\n")
        for i, fr in enumerate(frames):
            t = t0 + i / fps
            m = f"  change {moved[i][0]:6.2f} {moved[i][1]}" if moved else ""
            f.write(f"{os.path.basename(fr)}  log {t - offset:7.3f} s  recording {int(t // 60)}:{t % 60:06.3f}{m}\n")
    return (len(frames), held, jumps) if moved else len(frames)


def motion(frames):
    """[(change from the frame before, 'HELD' | 'JUMP' | '')] per frame: how much of the picture moved, in grey
    levels (0-255, mean over the frame). Needs Pillow and numpy; without them, an empty list."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        return []
    change, prev = [0.0], None
    for f in frames:
        a = np.asarray(Image.open(f).convert("L"), dtype=np.float32)
        if prev is not None:
            change.append(float(np.abs(a - prev).mean()))
        prev = a
    out = []
    for i, c in enumerate(change):
        near = [change[j] for j in range(max(1, i - MOTION_NEAR), min(len(change), i + MOTION_NEAR + 1)) if j != i]
        med = float(np.median(near)) if near else 0.0
        tag = ""
        if i and med >= MOVING_MIN:
            tag = "HELD" if c < HELD_SHARE * med else "JUMP" if c > JUMP_SHARE * med else ""
        out.append((round(c, 2), tag))
    return out


def frames_dir(game, run, label, video):
    view = "headset" if (load_json(video + ".json") or {}).get("window", "").startswith("OpenXR") else "game"
    return os.path.join(rec_root(), game, "begone-frames", os.path.basename(run), f"{label}_{view}")


def write_part(run, lines):
    p = os.path.join(run, "report.md")
    try:
        text = open(p, encoding="utf-8").read()
    except OSError:
        text = ""
    if PART_HEAD in text:
        text = text[:text.index(PART_HEAD)].rstrip() + "\n"
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text.rstrip() + "\n\n" + PART_HEAD + "\n\n" + "\n".join(lines) + "\n")


def attach(run, log=None, game=None):
    rec = load_json(os.path.join(run, "recording.json")) or {}
    s = summary(run)
    game = game or rec.get("game") or os.path.basename(os.path.dirname(run))
    if log:
        rec["wall_ms"], rec["clock"] = log_wall_ms(log)
    if not rec.get("wall_ms"):
        return "no clock for this log: attach it with --log <file.jl> (the filed copy is in the log folder's done)"
    rec["game"] = game
    videos = recordings_for(game, rec["wall_ms"], s.get("seconds", 0))
    lines = []
    if not videos:
        live = load_json(os.path.join(os.environ.get("LOCALAPPDATA", ""), "obs-rec-state.json")) or {}
        why = ("a recording is still running: once it stops, run `begone.py frames camera-jitter <run> attach`"
               if live.get("recording") else "no recording covers this session")
        rec["videos"] = []
        json.dump(rec, open(os.path.join(run, "recording.json"), "w", encoding="utf-8"), indent=1)
        write_part(run, [f"- {why}."])
        return why
    rec["videos"], done = [], 0
    for video, side in videos:
        offset = (rec["wall_ms"] - side["start_ms"]) / 1000.0
        lines.append(f"- **{side.get('window') or 'game window'}**: `{os.path.basename(video)}`; the log starts "
                     f"{offset:.2f} s into it ({rec.get('clock')}).")
        cuts = []
        covered = ((side["start_ms"] - rec["wall_ms"]) / 1000.0, (side["stop_ms"] - rec["wall_ms"]) / 1000.0)
        for label, a, b in stretches(s, covered):
            out = frames_dir(game, run, label, video)
            n = cut(video, side, rec["wall_ms"], a, b, out)
            n, held, jumps = n if isinstance(n, tuple) else (n, None, None)
            rel = os.path.relpath(out, rec_root()).replace("\\", "/")
            cuts.append({"stretch": label, "from_s": a, "to_s": b, "frames": n if isinstance(n, int) else 0,
                         "held": held, "jumped": jumps, "folder": rel, "note": None if isinstance(n, int) else n})
            seen = f"; on screen {held} pictures held, {jumps} jumped" if held is not None else ""
            lines.append(f"  - {label.replace('_', ' ')}: " + (f"{n} frames{seen}, in `<recordings>/{rel}/` (sheet.jpg)"
                                                              if isinstance(n, int) else n))
            done += isinstance(n, int)
        rec["videos"].append({"file": os.path.basename(video), "window": side.get("window"), "offset_s": round(offset, 3),
                              "cuts": cuts})
    for at_s, why, how in breaks(rec["wall_ms"], s.get("seconds", 0)):
        lines.append(f"- ⚠️ the recording broke at {at_s:.0f} s of the log: {why} ({how}).")
    json.dump(rec, open(os.path.join(run, "recording.json"), "w", encoding="utf-8"), indent=1)
    write_part(run, lines)
    return f"on the recording: {done} stretches cut from {len(videos)} file(s)"


def breaks(wall_ms, seconds):
    """[(log second, why, restarted or not)] for every recording break obs-rec's guard noted inside this log"""
    try:
        with open(BREAKS_LOG, encoding="utf-8") as f:
            rows = [_break_row(line, wall_ms) for line in f]
    except OSError:
        return []
    return [r for r in rows if r and 0 <= r[0] <= seconds + BREAK_SLACK_S]


def _break_row(line, wall_ms):
    """one BREAKS_LOG line as (log second, why, restarted or not), or None"""
    p = line.rstrip("\n").split("\t")
    if len(p) < 5 or not p[0].isdigit():
        return None
    return (int(p[0]) - wall_ms) / 1000.0, p[3], p[4]


def main(a):
    if len(a) >= 2 and a[0] == "attach":
        opt = lambda k: a[a.index(k) + 1] if k in a and a.index(k) + 1 < len(a) else None
        return attach(a[1], opt("--log"), opt("--game"))
    if len(a) >= 4 and a[0] == "cut":
        run = a[1]
        rec = load_json(os.path.join(run, "recording.json")) or {}
        if not rec.get("wall_ms"):
            return "attach this run first (frames.py attach <run> --log <file.jl>)"
        videos = recordings_for(rec["game"], rec["wall_ms"], summary(run).get("seconds", 0))
        if not videos:
            return "no recording covers this session"
        lab = f"asked_{a[2]}-{a[3]}s"
        out = []
        for video, side in videos:
            d = frames_dir(rec["game"], run, lab, video)
            n = cut(video, side, rec["wall_ms"], float(a[2]), float(a[3]), d, full="--full" in a)
            if isinstance(n, tuple):
                out.append(f"{n[0]} frames ({n[1]} held, {n[2]} jumped on screen) in {d}")
            else:
                out.append(f"{n} frames in {d}" if isinstance(n, int) else n)
        return "\n".join(out)
    if len(a) >= 2 and a[0] == "where":
        rec = load_json(os.path.join(a[1], "recording.json"))
        if not rec:
            return "not attached yet"
        return "\n".join(f"{v['file']} ({v['window']}), log 0 s = {v['offset_s']} s in: "
                         + ", ".join(f"{c['stretch']} -> {os.path.join(rec_root(), c['folder'])}" for c in v["cuts"])
                         for v in rec.get("videos", [])) or "no recording covers this session"
    return __doc__


if __name__ == "__main__":
    print(main(sys.argv[1:]))
