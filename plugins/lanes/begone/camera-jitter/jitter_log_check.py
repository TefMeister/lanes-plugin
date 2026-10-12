"""jitter_log_check.py -- read a .jl file a VR mod wrote (jitterlog.h / jitterlog.lua) and say WHY the view jitters.

    python jitter_log_check.py <file.jl> [--out <folder>]      check one log; writes summary.json, report.md, chart.png
    python jitter_log_check.py selftest                        made-up logs with known faults, every verdict checked

Three streams per frame: P = the mod read the headset pose, C = the mod wrote the camera, F = a picture went out.
Two more for Occlusion Drift BeG0nE: L and R = a controller read, with a ninth field saying whether it was tracked.
Per second of log, while the head is turning, it measures:
  camera held      share of pictures that went out with a camera identical to the picture before   -> JITTER
  camera rate      camera writes per picture                                                        -> the rate fault
  pose repeated    share of pose reads identical to the read before, while the head moved           -> stale pose
  pose age         how old the pose was when the camera was written (ms)                            -> latency
  camera lag       the camera matching the pose BEFORE last better than the last one                -> one-frame lag
Vocabulary is Tefa's (claude-memory PREFERENCES.md, "what jittery means"): JITTER = stepped under a smooth slow turn.
"""
import json
import math
import os
import sys
import time

import numpy as np

# --- settings: every number with a name ---
WINDOW_S = 1.0                # verdicts per one-second piece
MOVING_DEG_S = 4.0            # the head counts as turning when yaw changes at least this fast (slow smooth turn ~20-40)
HELD_DEG = 0.02               # a camera that moved less than this between two pictures counts as HELD
HANDS_CLOSE_M = 0.30          # controllers nearer than this are 'stacked': one can hide the other from the headset
JITTER_HELD_SHARE = 0.20      # a turning second with 20%+ held pictures is JITTER
LOW_CAMERA_RATE = 0.85        # camera writes per picture below this: the camera is renewed less often than pictures
LOW_POSE_RATE = 0.85          # pose reads per picture below this: the pose is read less often than pictures
STALE_POSE_SHARE = 0.15       # 15%+ pose reads identical to the previous while turning: the runtime gave a stale pose
LAG_SHARE = 0.60              # 60%+ pictures whose camera matches the pose before last: one-frame lag
POSE_AGE_HIGH_MS = 12.0       # median pose age above this (about one 90 Hz frame) is worth saying
MIN_TURNING_S = 2.0           # fewer turning seconds than this: no jitter verdict
MIN_PICTURES_S = 20.0         # fewer pictures a second than this: the mod was not really running
CHART_W, ROW_H, MARGIN = 1200, 90, 50
KIND_COLOUR = {"smooth": (120, 200, 120), "JITTER": (60, 60, 230), "still": (200, 200, 200), "thin": (90, 90, 90)}


def read_log(path):
    """Returns (header dict, list of (t_s, kind, yaw, pitch, roll, x, y, z)); marks are kept as kind 'M' with text."""
    head, rows = {}, []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("#"):
                for part in line.split()[1:]:
                    if "=" in part:
                        k, v = part.split("=", 1)
                        head[k] = v
                continue
            p = line.split()
            if len(p) < 2:
                continue
            try:
                t = int(p[0]) / 1e6
            except ValueError:
                continue
            if p[1] == "M":
                rows.append((t, "M", " ".join(p[2:])))
            elif len(p) >= 8:
                try:
                    rows.append((t, p[1]) + tuple(float(v) for v in p[2:8]) + ((int(p[8]),) if len(p) > 8 else ()))
                except ValueError:
                    pass
    return head, rows


def _yaw_delta(a, b):
    d = (b - a + 180.0) % 360.0 - 180.0
    return d


def analyse(rows):
    """Per-second windows plus whole-log numbers."""
    poses = [r for r in rows if r[1] == "P"]
    cams = [r for r in rows if r[1] == "C"]
    frames = [r for r in rows if r[1] == "F"]
    if not frames:
        return {"error": "no pictures (F lines) in the log"}
    end = frames[-1][0]
    # the camera in force at each picture: the last C written before it
    cam_at = []
    ci = -1
    pi = -1
    for f in frames:
        while ci + 1 < len(cams) and cams[ci + 1][0] <= f[0]:
            ci += 1
        while pi + 1 < len(poses) and poses[pi + 1][0] <= f[0]:
            pi += 1
        cam_at.append((f[0], ci, pi))
    windows = []
    for k in range(int(end // WINDOW_S) + 1):
        lo, hi = k * WINDOW_S, (k + 1) * WINDOW_S
        fw = [c for c in cam_at if lo <= c[0] < hi]
        pw = [p for p in poses if lo <= p[0] < hi]
        cw = [c for c in cams if lo <= c[0] < hi]
        w = {"at_s": lo, "pictures": len(fw), "pose_reads": len(pw), "camera_writes": len(cw)}
        if len(fw) < MIN_PICTURES_S * WINDOW_S:
            w["kind"] = "thin"; windows.append(w); continue
        # is the head turning? yaw travelled over the second, from the pose stream
        turning = False
        if len(pw) >= 2:
            yaw_rate = abs(_yaw_delta(pw[0][2], pw[-1][2])) / max(1e-6, pw[-1][0] - pw[0][0])
            w["head_deg_s"] = round(yaw_rate, 1)
            turning = yaw_rate >= MOVING_DEG_S
        # held pictures: camera index unchanged, or camera yaw unchanged, picture to picture
        held = 0
        lag_hits = lag_total = 0
        ages = []
        for i in range(1, len(fw)):
            a, b = fw[i - 1], fw[i]
            if b[1] < 0:
                held += 1; continue
            if a[1] == b[1] or (a[1] >= 0 and abs(_yaw_delta(cams[a[1]][2], cams[b[1]][2])) < HELD_DEG
                                and abs(cams[a[1]][3] - cams[b[1]][3]) < HELD_DEG):
                held += 1
            # which pose did this FRESHLY written camera come from: the last pose, or the one before?
            if b[2] >= 1 and b[1] >= 0 and a[1] != b[1]:
                c = cams[b[1]]
                d_last = abs(_yaw_delta(c[2], poses[b[2]][2])) + abs(c[3] - poses[b[2]][3])
                d_prev = abs(_yaw_delta(c[2], poses[b[2] - 1][2])) + abs(c[3] - poses[b[2] - 1][3])
                if d_last > 1e-6 or d_prev > 1e-6:
                    lag_total += 1
                    if d_prev < d_last:
                        lag_hits += 1
        for c in cw:   # pose age at each camera write
            j = np.searchsorted([p[0] for p in pw], c[0], side="right") - 1
            if j >= 0:
                ages.append((c[0] - pw[j][0]) * 1000.0)
        stale = 0
        for i in range(1, len(pw)):
            if abs(_yaw_delta(pw[i - 1][2], pw[i][2])) < HELD_DEG and abs(pw[i - 1][3] - pw[i][3]) < HELD_DEG:
                stale += 1
        n = max(1, len(fw) - 1)
        w.update(held_share=round(held / n, 2), camera_per_picture=round(len(cw) / len(fw), 2),
                 pose_per_picture=round(len(pw) / len(fw), 2),
                 stale_pose_share=round(stale / max(1, len(pw) - 1), 2),
                 lag_share=round(lag_hits / lag_total, 2) if lag_total else 0.0,
                 pose_age_ms=round(float(np.median(ages)), 1) if ages else None)
        if not turning:
            w["kind"] = "still"
        elif w["held_share"] >= JITTER_HELD_SHARE:
            w["kind"] = "JITTER"
        else:
            w["kind"] = "smooth"
        windows.append(w)
    hands = analyse_hands(rows, end)
    return {"hands": hands, "seconds": round(end, 2), "pictures_per_s": round(len(frames) / max(end, 1e-6), 1),
            "pose_reads_per_s": round(len(poses) / max(end, 1e-6), 1),
            "camera_writes_per_s": round(len(cams) / max(end, 1e-6), 1), "windows": windows,
            "marks": [(round(r[0], 2), r[2]) for r in rows if r[1] == "M"][:40]}


def analyse_hands(rows, end):
    """Per controller: reads a second, share of reads the runtime called untracked, the longest untracked run,
    and how much of the untracked time the other controller was close (the occlusion shape)."""
    out = {}
    hands = {k: [r for r in rows if r[1] == k and len(r) > 8] for k in ("L", "R")}
    if not hands["L"] and not hands["R"]:
        return out
    for side, other in (("L", "R"), ("R", "L")):
        hs, os_ = hands[side], hands[other]
        if not hs:
            continue
        untracked = [r for r in hs if r[8] == 0]
        longest, run_start = 0.0, None
        for r in hs:
            if r[8] == 0 and run_start is None:
                run_start = r[0]
            elif r[8] == 1 and run_start is not None:
                longest = max(longest, r[0] - run_start); run_start = None
        if run_start is not None:
            longest = max(longest, hs[-1][0] - run_start)
        close = 0
        if os_ and untracked:
            ot = np.array([r[0] for r in os_])
            for r in untracked:
                j = min(len(os_) - 1, max(0, int(np.searchsorted(ot, r[0]))))
                o = os_[j]
                if math.sqrt((r[5] - o[5]) ** 2 + (r[6] - o[6]) ** 2 + (r[7] - o[7]) ** 2) < HANDS_CLOSE_M:
                    close += 1
        out[side] = {"reads_per_s": round(len(hs) / max(end, 1e-6), 1),
                     "untracked_share": round(len(untracked) / len(hs), 3),
                     "longest_untracked_s": round(longest, 2),
                     "untracked_while_hands_close_share": round(close / len(untracked), 2) if untracked else 0.0}
    return out


def judge(a):
    if "error" in a:
        return dict(a, quality="faulty", verdict=f"Not usable: {a['error']}.", causes=[])
    turning = [w for w in a["windows"] if w.get("kind") in ("smooth", "JITTER")]
    jit = [w for w in turning if w["kind"] == "JITTER"]
    s = dict(a)
    s["seconds_turning"], s["seconds_jitter"] = len(turning), len(jit)
    s["jitter_times_s"] = [w["at_s"] for w in jit][:60]
    causes = []
    if len(turning) < MIN_TURNING_S:
        s["quality"] = "no-movement"
        s["verdict"] = "The head hardly turned, so this log cannot show jitter. Turn the head slowly and smoothly for a few seconds."
        s["causes"] = causes
        return s
    s["quality"] = "good"
    med = lambda key: float(np.median([w[key] for w in turning if w.get(key) is not None])) if turning else 0.0
    cam_rate, pose_rate = med("camera_per_picture"), med("pose_per_picture")
    stale, lag, age = med("stale_pose_share"), med("lag_share"), med("pose_age_ms")
    if jit:
        if cam_rate < LOW_CAMERA_RATE:
            causes.append(f"the camera is written {cam_rate:.2f} times per picture: it is renewed less often than "
                          f"pictures are drawn, so some pictures reuse the previous camera (the rate fault)")
        if stale >= STALE_POSE_SHARE:
            causes.append(f"{stale:.0%} of pose reads returned the same pose as the read before while the head was "
                          f"turning: the runtime handed a stale pose (the pose is read at the wrong moment, or from a "
                          f"cached copy, not once per frame after waiting for the frame)")
        if pose_rate < LOW_POSE_RATE:
            causes.append(f"the pose is read {pose_rate:.2f} times per picture: less often than pictures are drawn")
        if not causes:
            causes.append("the camera held still on some pictures although it was written and the pose was fresh: "
                          "the value written did not change, so look at what sits between the pose and the camera "
                          "(a smoothing step, a rounding, a once-per-tick game update)")
    if lag >= LAG_SHARE:
        causes.append(f"{lag:.0%} of pictures carry a camera that matches the pose BEFORE last: the camera trails the "
                      f"pose by one frame (swim, not jitter)")
    if age and age >= POSE_AGE_HIGH_MS:
        causes.append(f"the pose was {age:.0f} ms old when the camera was written: more than a frame")
    s["causes"] = causes
    if jit:
        v = f"JITTER in {len(jit)} of {len(turning)} turning seconds. Why: " + "; ".join(causes[:3]) + "."
    else:
        v = f"Smooth: in {len(turning)} turning seconds the camera moved with every picture."
        if causes:
            v += " Worth knowing: " + "; ".join(causes) + "."
    s["verdict"] = v
    return s


def chart(path, s):
    import cv2
    secs = max(s.get("seconds", 1.0), 1e-6)
    canvas = np.full((ROW_H + 40, CHART_W, 3), 245, np.uint8)
    x_of = lambda t: int(MARGIN + (CHART_W - 2 * MARGIN) * t / secs)
    for w in s.get("windows", []):
        cv2.rectangle(canvas, (x_of(w["at_s"]), 24), (x_of(w["at_s"] + WINDOW_S), ROW_H), KIND_COLOUR.get(w["kind"], (90, 90, 90)), -1)
    cv2.putText(canvas, s["verdict"][:170], (MARGIN, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (20, 20, 20), 1, cv2.LINE_AA)
    x = MARGIN
    for name, col in KIND_COLOUR.items():
        cv2.rectangle(canvas, (x, ROW_H + 14), (x + 14, ROW_H + 24), col, -1)
        cv2.putText(canvas, name, (x + 18, ROW_H + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (20, 20, 20), 1)
        x += 110
    cv2.imwrite(path, canvas)


def report(head, s, src):
    lines = [f"# {head.get('game', 'game')} ({head.get('runtime', '?')})", "",
             f"Log `{os.path.basename(src)}`, checked {time.strftime('%Y-%m-%d %H:%M')}. `[measured]`: one VR session.", "",
             s["verdict"], "", f"- quality: **{s['quality']}**"]
    if "pictures_per_s" in s:
        lines += [f"- {s['seconds']} s; {s['pictures_per_s']} pictures, {s['pose_reads_per_s']} pose reads, "
                  f"{s['camera_writes_per_s']} camera writes a second",
                  f"- turning {s.get('seconds_turning', 0)} s, jitter {s.get('seconds_jitter', 0)} s"]
    if s.get("causes"):
        lines += ["", "## Why", ""] + [f"- {c}" for c in s["causes"]]
    if s.get("hands"):
        lines += ["", "## Controllers (Occlusion Drift BeG0nE)", ""]
        for side, h in s["hands"].items():
            lines.append(f"- {'left' if side == 'L' else 'right'}: {h['reads_per_s']} reads a second; untracked "
                         f"{h['untracked_share']:.1%} of the time, longest {h['longest_untracked_s']} s; "
                         f"{h['untracked_while_hands_close_share']:.0%} of the untracked reads came while the other "
                         f"controller was within {HANDS_CLOSE_M} m")
    if s.get("marks"):
        lines += ["", "## Marks the mod left", ""] + [f"- {t} s: {m}" for t, m in s["marks"]]
    lines += ["", "![chart](chart.png)", ""]
    return "\n".join(lines)


def check(path, out=None):
    head, rows = read_log(path)
    s = judge(analyse(rows))
    s["file"], s["game"], s["runtime"] = os.path.basename(path), head.get("game", "game"), head.get("runtime", "?")
    if out:
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "summary.json"), "w", encoding="utf-8") as f:
            json.dump(s, f, indent=1)
        with open(os.path.join(out, "report.md"), "w", encoding="utf-8") as f:
            f.write(report(head, s, path))
        try:
            chart(os.path.join(out, "chart.png"), s)
        except ImportError:
            pass
    return s


# ----- self-test: logs with known faults -----
def _synth(case, hz=90.0, seconds=8.0, turn_deg_s=30.0):
    lines = ["#jitterlog 1 game=selftest runtime=none"]
    dt = 1.0 / hz
    n = int(seconds * hz)
    last_pose = None
    prev_pose = None
    for i in range(n):
        t = i * dt
        yaw = turn_deg_s * t if case != "still" else 0.0
        pose = (yaw, 0.0)
        if case == "stale" and i % 2 == 1:
            pose = last_pose          # runtime handed the same pose again
        us = lambda s: int(s * 1e6)
        lines.append(f"{us(t)} P {pose[0]:.3f} {pose[1]:.3f} 0 0 1.6 0")
        write_cam = True
        if case == "stepped" and i % 3:
            write_cam = False         # camera renewed every 3rd frame only
        if case == "lowrate" and i % 2:
            write_cam = False
        cam = pose
        if case == "lag" and prev_pose is not None:
            cam = prev_pose           # camera built from the previous frame's pose
        if write_cam:
            lines.append(f"{us(t + 0.001)} C {cam[0]:.3f} {cam[1]:.3f} 0 0 1.6 0")
        lines.append(f"{us(t + 0.005)} F 0 0 0 0 0 0")
        prev_pose, last_pose = last_pose, pose
    lines.append("#end")
    return "\n".join(lines) + "\n"


EXPECT = {
    "smooth": lambda s: s["seconds_jitter"] == 0 and s["quality"] == "good" and not s["causes"],
    "stepped": lambda s: s["seconds_jitter"] >= s["seconds_turning"] - 1 and any("renewed less often" in c for c in s["causes"]),
    "lowrate": lambda s: s["seconds_jitter"] >= s["seconds_turning"] - 1 and any("renewed less often" in c for c in s["causes"]),
    "stale": lambda s: s["seconds_jitter"] >= s["seconds_turning"] - 1 and any("stale pose" in c for c in s["causes"]),
    "lag": lambda s: s["seconds_jitter"] == 0 and any("trails the pose" in c for c in s["causes"]),
    "still": lambda s: s["quality"] == "no-movement",
}


def selftest():
    import tempfile
    folder = tempfile.mkdtemp(prefix="begone-jl-")
    failed = 0
    for case, ok in EXPECT.items():
        p = os.path.join(folder, case + ".jl")
        with open(p, "w", encoding="utf-8") as f:
            f.write(_synth(case))
        s = check(p)
        good = ok(s)
        failed += not good
        print(f"{'PASS' if good else 'FAIL'}  {case:8s} {s['verdict'][:150]}")
        if not good:
            print("      ", {k: s.get(k) for k in ("seconds_turning", "seconds_jitter", "quality", "causes")})
            print("      ", s["windows"][1:3])
    print(f"{len(EXPECT) - failed}/{len(EXPECT)} cases judged right")
    return failed == 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == "selftest":
        sys.exit(0 if selftest() else 1)
    out = a[a.index("--out") + 1] if "--out" in a else None
    s = check(a[0], out)
    print(s["verdict"])
    for c in s.get("causes", []):
        print(" -", c)
