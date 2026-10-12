"""ghost_hand_check.py - read a Ghost Hand log (.ghl, written by ghosthand.lua) and say where the real hand and the
player's hand parted, and why each hand gesture missed.

    python ghost_hand_check.py file <file.ghl> --home <tool home> [--game <project>]
        check one log, write <home>/data/<game>/<stamp>_<runtime>/ (summary.json, report.md), add the INDEX.csv line;
        prints ONE line: the verdict.
    python ghost_hand_check.py check <file.ghl>        the verdict and the report, printed, nothing written
    python ghost_hand_check.py ask <run folder> <question>
        attempts          every gesture attempt, one line each (at most 40)
        attempt <n>       one attempt in detail; with the raw log still on this PC, its frames sampled (at most 25)
        jumps             when a hand jumped (at most 40)
        tracking          when a controller lost tracking, and whether the hands were stacked (at most 40)
        gaps              how far the game's hands sat from the real ones, and how late they followed
    python ghost_hand_check.py selftest                made-up logs with known faults, every verdict checked

What it measures (all positions in the game world, metres):
  gap        distance from the real controller to the hand the game draws. A steady gap is just the grip offset;
             what matters is how much it WANDERS from its usual size.
  lag        how many frames the game's hand trails the controller, found by lining up their movements.
  jumps      a hand that moved more than JUMP_M in one frame: the game's hand while the controller was calm
             (the game's fault), or the controller itself (a tracking glitch).
  tracking   frames a controller reported untracked; 'stacked' when the hands were nearer than HANDS_CLOSE_M,
             which is what Occlusion Drift BeG0nE is about.
  attempts   each gesture between gh.event(<g>, 'start') and its done/fail/cancel: how far the hands moved apart,
             how far the left hand travelled, how far the gun hand moved, what the mod measured, and why it missed.
"""
import csv
import json
import math
import os
import sys
import time

# --- settings: every number with a name ---
JUMP_M = 0.06                 # a hand moving more than this in one frame (~5 m/s at 90 Hz) is a jump
CALM_M = 0.02                 # ... counted as the GAME's jump when the controller moved less than this that frame
HANDS_CLOSE_M = 0.30          # controllers nearer than this are stacked: one can hide the other
LAG_MAX_FRAMES = 12           # lag is searched up to this many frames
LAG_MIN_TRAVEL_M = 0.5        # a hand must have travelled this much in all before its lag means anything
GUN_MOVED_M = 0.03            # the gun hand moving more than this during a gesture is worth saying
WANDER_HIGH_M = 0.03          # the gap wandering more than this (95th percentile) from its usual size is worth saying
MIN_FRAMES = 60               # fewer frames than this: no verdict
MAX_LIST = 40                 # an answer never lists more than this
MAX_SAMPLES = 25              # frames shown for one attempt
REPORT_MISSES = 15            # misses listed in report.md
DONE = ("done", "ok", "finished", "success")
ENDS = DONE + ("fail", "failed", "cancel", "cancelled", "abort", "end")


def dist(a, b):
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def pct(vals, p):
    if not vals:
        return 0.0
    v = sorted(vals)
    return v[min(len(v) - 1, int(round(p / 100.0 * (len(v) - 1))))]


# ----- reading -----
def read_log(path):
    """Returns (header, frames, events). A frame: {t, real:{side:(tracked,x,y,z)}, game:{side:(x,y,z)},
    parts:{name:(x,y,z)}, values:{name:v}, buttons:{name:0|1}}; events: [(t, name, what)]."""
    head, frames, events = {}, [], []
    cur = {"real": {}, "game": {}, "parts": {}, "values": {}, "buttons": {}}
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
                k = p[1]
                if k == "R" and len(p) >= 7:
                    cur["real"][p[2]] = (int(p[3]), float(p[4]), float(p[5]), float(p[6]))
                elif k == "G" and len(p) >= 6:
                    cur["game"][p[2]] = (float(p[3]), float(p[4]), float(p[5]))
                elif k == "P" and len(p) >= 6:
                    cur["parts"][p[2]] = (float(p[3]), float(p[4]), float(p[5]))
                elif k == "V" and len(p) >= 4:
                    cur["values"][p[2]] = float(p[3])
                elif k == "B" and len(p) >= 4:
                    cur["buttons"][p[2]] = int(p[3])
                elif k == "E" and len(p) >= 4:
                    events.append((t, p[2], p[3].lower()))
                elif k == "F":
                    cur["t"] = t
                    frames.append(cur)
                    cur = {"real": {}, "game": {}, "parts": {}, "values": {}, "buttons": {}}
            except ValueError:
                continue
    return head, frames, events


def real_pos(fr, side):
    r = fr["real"].get(side)
    return (r[1], r[2], r[3]) if r else None


def frame_at(frames, t):
    """Index of the first frame at or after t."""
    lo, hi = 0, len(frames)
    while lo < hi:
        mid = (lo + hi) // 2
        if frames[mid]["t"] < t:
            lo = mid + 1
        else:
            hi = mid
    return min(lo, len(frames) - 1)


# ----- measuring -----
def hand_gaps(frames, side):
    gaps = [dist(real_pos(f, side), f["game"][side]) for f in frames if real_pos(f, side) and side in f["game"]]
    if not gaps:
        return None
    usual = pct(gaps, 50)
    wander = [abs(g - usual) for g in gaps]
    return {"frames": len(gaps), "usual_m": round(usual, 4), "wander_p95_m": round(pct(wander, 95), 4),
            "wander_max_m": round(max(wander), 4)}


def hand_lag(frames, side):
    """Frames the game's hand trails the controller: the shift that best lines up their frame-to-frame moves."""
    pairs = [(real_pos(f, side), f["game"][side]) for f in frames if real_pos(f, side) and side in f["game"]]
    if len(pairs) < LAG_MAX_FRAMES * 4:
        return None
    dr = [tuple(pairs[i][0][j] - pairs[i - 1][0][j] for j in range(3)) for i in range(1, len(pairs))]
    dg = [tuple(pairs[i][1][j] - pairs[i - 1][1][j] for j in range(3)) for i in range(1, len(pairs))]
    if sum(math.sqrt(sum(c * c for c in d)) for d in dr) < LAG_MIN_TRAVEL_M:
        return None
    best, best_err = 0, None
    for k in range(LAG_MAX_FRAMES + 1):
        n = len(dg) - k
        err = sum(math.sqrt(sum((dg[i + k][j] - dr[i][j]) ** 2 for j in range(3))) for i in range(n)) / max(1, n)
        if best_err is None or err < best_err - 1e-9:
            best, best_err = k, err
    return best


def jumps(frames):
    out = []
    for i in range(1, len(frames)):
        a, b = frames[i - 1], frames[i]
        for side in ("L", "R"):
            ra, rb = real_pos(a, side), real_pos(b, side)
            rstep = dist(ra, rb) if ra and rb else None
            if side in a["game"] and side in b["game"]:
                gstep = dist(a["game"][side], b["game"][side])
                if gstep > JUMP_M and (rstep is None or rstep < CALM_M):
                    out.append({"t": round(b["t"], 3), "side": side, "who": "game", "m": round(gstep, 3)})
            if rstep is not None and rstep > JUMP_M:
                out.append({"t": round(b["t"], 3), "side": side, "who": "controller", "m": round(rstep, 3)})
    return out


def tracking(frames):
    out = []
    for side in ("L", "R"):
        start = None
        for f in frames + [None]:
            r = f["real"].get(side) if f else None
            lost = r is not None and r[0] == 0
            if lost and start is None:
                start = f
            elif not lost and start is not None:
                end_t = f["t"] if f else start["t"]
                a, b = real_pos(start, "L"), real_pos(start, "R")
                d = dist(a, b) if a and b else None
                out.append({"t": round(start["t"], 3), "side": side, "s": round(end_t - start["t"], 3),
                            "hands_m": round(d, 3) if d is not None else None,
                            "stacked": d is not None and d < HANDS_CLOSE_M})
                start = None
    return sorted(out, key=lambda x: x["t"])


def attempts(frames, events, jlist, tlist):
    out, open_ = [], {}
    for t, name, what in events:
        if what == "start":
            open_[name] = t
        elif what in ENDS and name in open_:
            out.append((name, open_.pop(name), t, what))
    res = []
    for n, (name, t0, t1, what) in enumerate(out, 1):
        i0, i1 = frame_at(frames, t0), frame_at(frames, t1)
        seg = frames[i0:i1 + 1]
        a = {"n": n, "gesture": name, "t": round(t0, 3), "s": round(t1 - t0, 3), "outcome": what,
             "done": what in DONE}
        sep = [dist(real_pos(f, "L"), real_pos(f, "R")) for f in seg if real_pos(f, "L") and real_pos(f, "R")]
        l0 = next((real_pos(f, "L") for f in seg if real_pos(f, "L")), None)
        r0 = next((real_pos(f, "R") for f in seg if real_pos(f, "R")), None)
        if sep:
            a["apart_m"] = round(max(max(sep) - sep[0], sep[0] - min(sep)), 4)
        if l0:
            a["left_travel_m"] = round(max(dist(l0, real_pos(f, "L")) for f in seg if real_pos(f, "L")), 4)
        if r0:
            a["gun_moved_m"] = round(max(dist(r0, real_pos(f, "R")) for f in seg if real_pos(f, "R")), 4)
        vals = [f["values"][name] for f in seg if name in f["values"]]
        if vals:
            a["mod_max"] = round(max(vals), 4)
        need = None
        for f in frames[:i1 + 1]:
            if name + "_need" in f["values"]:
                need = f["values"][name + "_need"]
        if need is not None:
            a["need_m"] = round(need, 4)
        a["lost"] = sum(1 for x in tlist if t0 <= x["t"] <= t1)
        a["jumps"] = sum(1 for x in jlist if t0 <= x["t"] <= t1)
        a["why"] = why(a)
        res.append(a)
    return res


def why(a):
    if a["done"]:
        return "finished"
    if a["lost"]:
        return "a controller lost tracking during it"
    if a["jumps"]:
        return "a hand jumped during it"
    apart, left, gun, need = a.get("apart_m"), a.get("left_travel_m"), a.get("gun_moved_m", 0), a.get("need_m")
    if need is None or apart is None:
        return "not judged: the mod does not log how far it needs (gh.value('<g>_need', metres))"
    if apart >= need:
        return (f"the hands moved {apart * 100:.1f} cm apart, enough for the {need * 100:.1f} cm needed, "
                f"but the mod measured less" + (f" ({a['mod_max']:.2f})" if "mod_max" in a else ""))
    if left is not None and left >= need and gun > GUN_MOVED_M:
        return (f"the gun hand moved back with the pull: the left hand travelled {left * 100:.1f} cm but the hands "
                f"only moved {apart * 100:.1f} cm apart ({need * 100:.1f} needed; gun moved {gun * 100:.1f} cm)")
    return f"pull too short: {apart * 100:.1f} cm of {need * 100:.1f} cm"


# ----- judging -----
def judge(head, frames, events):
    s = {"game": head.get("game", "game"), "runtime": head.get("runtime", "?"), "frames": len(frames)}
    s["seconds"] = round(frames[-1]["t"] - frames[0]["t"], 2) if len(frames) > 1 else 0.0
    s["frames_per_s"] = round(len(frames) / s["seconds"], 1) if s["seconds"] else 0.0
    has_real = any(f["real"] for f in frames)
    if len(frames) < MIN_FRAMES or not has_real:
        s.update(quality="thin" if has_real else "no-controllers", attempts=[], jumps=[], tracking=[], hands={},
                 verdict="Too little to judge: " + (f"{len(frames)} frames." if has_real else
                                                    "the mod logged no controller positions (gh.real)."))
        return s
    dt = s["seconds"] / max(1, len(frames) - 1)
    s["hands"] = {}
    for side in ("L", "R"):
        g = hand_gaps(frames, side)
        if g:
            lag = hand_lag(frames, side)
            if lag is not None:
                g["lag_frames"], g["lag_ms"] = lag, round(lag * dt * 1000, 1)
            s["hands"][side] = g
    j, t = jumps(frames), tracking(frames)
    s["jumps"], s["tracking"] = j, t
    s["attempts"] = attempts(frames, events, j, t)
    s["quality"] = "good"
    s["verdict"] = verdict(s)
    return s


def verdict(s):
    parts = []
    by = {}
    for a in s["attempts"]:
        by.setdefault(a["gesture"], []).append(a)
    for g, lst in by.items():
        done = sum(1 for a in lst if a["done"])
        line = f"{g}: {done} of {len(lst)} finished"
        misses = [a["why"].split(":")[0] for a in lst if not a["done"]]
        if misses:
            top = max(set(misses), key=misses.count)
            line += f"; most misses: {top} ({misses.count(top)} of {len(misses)})"
        parts.append(line)
    for side, h in s["hands"].items():
        name = "left" if side == "L" else "right"
        if h.get("lag_frames"):
            parts.append(f"the game's {name} hand trails the controller by {h['lag_frames']} frames ({h['lag_ms']} ms)")
        if h["wander_p95_m"] > WANDER_HIGH_M:
            parts.append(f"the game's {name} hand wanders up to {h['wander_p95_m'] * 100:.1f} cm from its usual place")
    gj = sum(1 for x in s["jumps"] if x["who"] == "game")
    cj = sum(1 for x in s["jumps"] if x["who"] == "controller")
    if gj:
        parts.append(f"the game's hand jumped {gj} times while the controller was calm")
    if cj:
        parts.append(f"a controller jumped {cj} times (tracking glitches)")
    if s["tracking"]:
        st = sum(1 for x in s["tracking"] if x["stacked"])
        parts.append(f"tracking lost {len(s['tracking'])} times" + (f", {st} with the hands stacked (occlusion)" if st else ""))
    return ("; ".join(parts) + ".") if parts else "The hands followed cleanly: no jumps, no lost tracking, no lag."


def report(s, src):
    out = [f"# {s['game']} ({s['runtime']}) - Ghost Hand", "",
           f"Log `{os.path.basename(src)}`, checked {time.strftime('%Y-%m-%d %H:%M')}. `[measured]`: one VR session.", "",
           s["verdict"], "", f"- quality: **{s['quality']}**",
           f"- {s['seconds']} s, {s['frames_per_s']} frames a second"]
    for side, h in s.get("hands", {}).items():
        out.append(f"- {'left' if side == 'L' else 'right'} hand: usual gap {h['usual_m'] * 100:.1f} cm, wanders "
                   f"{h['wander_p95_m'] * 100:.1f} cm (95%), lag {h.get('lag_frames', '?')} frames")
    misses = [a for a in s.get("attempts", []) if not a["done"]]
    if s.get("attempts"):
        out += ["", "## Misses", ""]
        if not misses:
            out.append("None.")
        for a in misses[:REPORT_MISSES]:
            out.append(f"- #{a['n']} {a['gesture']} at {a['t']} s: {a['why']}")
        if len(misses) > REPORT_MISSES:
            out.append(f"- ... {len(misses) - REPORT_MISSES} more: `begone.py ask ghost <run> attempts`")
    return "\n".join(out) + "\n"


def check(path, out=None):
    head, frames, events = read_log(path)
    s = judge(head, frames, events)
    s["file"] = os.path.basename(path)
    if out:
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "summary.json"), "w", encoding="utf-8") as f:
            json.dump(s, f, indent=1)
        with open(os.path.join(out, "report.md"), "w", encoding="utf-8") as f:
            f.write(report(s, path))
    return s


# ----- filing -----
INDEX_FIELDS = ["run", "game", "runtime", "date", "time", "seconds", "attempts", "finished", "jumps",
                "tracking_lost", "quality", "verdict"]


def file_log(path, home, game=None):
    head, _, _ = read_log_head(path)
    game = game or head.get("game", "unknown")
    runtime = head.get("runtime", "unknown")
    stamp = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime(os.path.getmtime(path)))
    run = f"{stamp}_{runtime}"
    data = os.path.join(home, "data")
    s = check(path, os.path.join(data, game, run))
    index = os.path.join(data, "INDEX.csv")
    rows = []
    if os.path.exists(index):
        with open(index, newline="", encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if r.get("run") != run]
    rows.append({"run": run, "game": game, "runtime": runtime, "date": stamp[:10], "time": stamp[11:],
                 "seconds": s["seconds"], "attempts": len(s["attempts"]),
                 "finished": sum(1 for a in s["attempts"] if a["done"]), "jumps": len(s["jumps"]),
                 "tracking_lost": len(s["tracking"]), "quality": s["quality"], "verdict": s["verdict"]})
    os.makedirs(data, exist_ok=True)
    with open(index, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=INDEX_FIELDS)
        w.writeheader(); w.writerows(rows)
    return f"{game}/{run}: {s['verdict']}"


def read_log_head(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            first = f.readline()
        return dict(kv.split("=", 1) for kv in first.split()[1:] if "=" in kv), None, None
    except OSError:
        return {}, None, None


# ----- asking -----
def raw_for(s):
    local = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "BeG0nE", "ghost-hand")
    for p in (os.path.join(local, "done", s.get("file", "")), os.path.join(local, s.get("file", ""))):
        if s.get("file") and os.path.isfile(p):
            return p
    return None


def fmt_attempt(a):
    bits = [f"#{a['n']} {a['gesture']} at {a['t']} s, {a['s']} s, {a['outcome']}"]
    for k, label in (("apart_m", "apart"), ("left_travel_m", "left travel"), ("gun_moved_m", "gun moved"),
                     ("need_m", "needed")):
        if k in a:
            bits.append(f"{label} {a[k] * 100:.1f} cm")
    if "mod_max" in a:
        bits.append(f"mod max {a['mod_max']}")
    return ", ".join(bits) + f" -> {a['why']}"


def ask(run_folder, words):
    with open(os.path.join(run_folder, "summary.json"), encoding="utf-8") as f:
        s = json.load(f)
    q = words[0] if words else "gaps"
    if q == "attempts":
        lst = s.get("attempts", [])
        lines = [f"{len(lst)} attempts"] + [fmt_attempt(a) for a in lst[:MAX_LIST]]
        if len(lst) > MAX_LIST:
            lines.append(f"... {len(lst) - MAX_LIST} more; ask 'attempt <n>'")
        return lines
    if q == "attempt" and len(words) >= 2:
        n = int(words[1])
        a = next((a for a in s.get("attempts", []) if a["n"] == n), None)
        if not a:
            return [f"no attempt {n}"]
        lines = [fmt_attempt(a)]
        raw = raw_for(s)
        if not raw:
            return lines + ["(the raw log is not on this PC, so no frames)"]
        _, frames, _ = read_log(raw)
        i0, i1 = frame_at(frames, a["t"]), frame_at(frames, a["t"] + a["s"])
        step = max(1, (i1 - i0 + 1) // MAX_SAMPLES)
        lines.append("t  realL  realR  gameL  hands_apart  values")
        for f in frames[i0:i1 + 1:step][:MAX_SAMPLES]:
            def p(v):
                return "(%.3f %.3f %.3f)" % tuple(v) if v else "-"
            rl, rr = real_pos(f, "L"), real_pos(f, "R")
            apart = f"{dist(rl, rr):.3f}" if rl and rr else "-"
            vals = " ".join(f"{k}={v:.3f}" for k, v in list(f["values"].items())[:4])
            lines.append(f"{f['t']:.3f} {p(rl)} {p(rr)} {p(f['game'].get('L'))} {apart} {vals}")
        return lines
    if q == "jumps":
        lst = s.get("jumps", [])
        return [f"{len(lst)} jumps"] + [f"{x['t']} s {x['side']} {x['who']} {x['m'] * 100:.1f} cm" for x in lst[:MAX_LIST]]
    if q == "tracking":
        lst = s.get("tracking", [])
        return [f"{len(lst)} tracking losses"] + [
            f"{x['t']} s {x['side']} for {x['s']} s, hands {x['hands_m']} m apart{' (stacked)' if x['stacked'] else ''}"
            for x in lst[:MAX_LIST]]
    if q == "gaps":
        return [f"{side}: {json.dumps(h)}" for side, h in s.get("hands", {}).items()] or ["no hand data"]
    return ["questions: attempts | attempt <n> | jumps | tracking | gaps"]


# ----- self-test -----
def _synth(path, case, hz=90.0, racks=6):
    """A made-up session: racks with the left hand pulling back 8 cm from a gun hand at the origin."""
    lines = ["#ghosthand 1 game=selftest runtime=test\n"]
    t, dt, lag = 0.0, 1.0 / hz, (3 if case == "lag" else 0)
    hist = []
    need = 0.06
    for r in range(racks):
        n = int(0.6 * hz)
        lines.append(f"{int(t * 1e6)} V rack_need {need}\n")
        lines.append(f"{int(t * 1e6)} E rack start\n")
        reached = 0.0
        for i in range(n):
            ph = math.sin(math.pi * i / (n - 1))
            pull = 0.08 * ph
            gun_back = (0.06 * ph) if case == "gun" else 0.0
            L = (0.0, 0.0, 0.30 - pull)
            R = (0.0, 0.0, 0.0 - gun_back)
            tracked = 0 if (case == "lost" and r % 2 == 0 and n // 3 < i < n // 2) else 1
            if case == "lost" and not tracked:
                L = (0.0, 0.0, 0.12)                    # stacked over the gun hand while hidden
            hist.append(L)
            G = hist[max(0, len(hist) - 1 - lag)]
            G = (G[0] + 0.02, G[1], G[2])               # a steady grip offset
            if case == "jump" and r == 2 and i == n // 2:
                G = (G[0] + 0.15, G[1], G[2])
            sep = abs(L[2] - R[2])
            ratio = min(1.0, max(0.0, (0.30 - sep) / need))
            reached = max(reached, ratio)
            us = int(t * 1e6)
            lines += [f"{us} R L {tracked} {L[0]:.4f} {L[1]:.4f} {L[2]:.4f}\n", f"{us} R R 1 {R[0]:.4f} {R[1]:.4f} {R[2]:.4f}\n",
                      f"{us} G L {G[0]:.4f} {G[1]:.4f} {G[2]:.4f}\n", f"{us} V rack {ratio:.4f}\n", f"{us} F\n"]
            t += dt
        ok = reached >= 1.0 and not (case == "lost" and r % 2 == 0) and not (case == "jump" and r == 2)
        lines.append(f"{int(t * 1e6)} E rack {'done' if ok else 'fail'}\n")
        for i in range(int(0.3 * hz)):                  # rest between racks
            us = int(t * 1e6)
            hist.append((0.0, 0.0, 0.30))
            lines += [f"{us} R L 1 0.0 0.0 0.30\n", f"{us} R R 1 0.0 0.0 0.0\n", f"{us} G L 0.02 0.0 0.30\n", f"{us} F\n"]
            t += dt
    lines.append("#end\n")
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)


def selftest():
    import tempfile
    tmp = tempfile.mkdtemp(prefix="ghosthand-")
    failed = 0

    def ok(name, cond, s):
        nonlocal failed
        failed += not cond
        print(("ok   " if cond else "FAIL ") + name + ("" if cond else "   verdict: " + s["verdict"]))

    for case in ("clean", "gun", "lost", "lag", "jump"):
        p = os.path.join(tmp, case + ".ghl")
        _synth(p, case)
        s = check(p)
        a = s["attempts"]
        if case == "clean":
            ok("clean: all 6 racks finished, nothing else said", len(a) == 6 and all(x["done"] for x in a)
               and not s["jumps"] and not s["tracking"], s)
        elif case == "gun":
            ok("gun: misses blamed on the gun hand moving back", a and not any(x["done"] for x in a)
               and all("gun hand moved back" in x["why"] for x in a), s)
        elif case == "lost":
            ok("lost: tracking losses found, stacked, and blamed", s["tracking"] and all(x["stacked"] for x in s["tracking"])
               and all(x["why"].startswith("a controller lost") for x in a if not x["done"]) and "occlusion" in s["verdict"], s)
        elif case == "lag":
            ok("lag: the game's left hand trails by 3 frames", s["hands"]["L"].get("lag_frames") == 3, s)
        elif case == "jump":
            ok("jump: the game's hand jump is found and blamed", any(x["who"] == "game" for x in s["jumps"])
               and any(x["why"].startswith("a hand jumped") for x in a), s)
    # filing and asking go through the same path a real session uses
    home = os.path.join(tmp, "home")
    p = os.path.join(tmp, "gun.ghl")
    line = file_log(p, home)
    run = os.path.join(home, "data", "selftest", line.split(":")[0].split("/")[1])
    ok("file: report, summary and INDEX written", os.path.isfile(os.path.join(run, "report.md"))
       and os.path.isfile(os.path.join(home, "data", "INDEX.csv")), {"verdict": line})
    ans = ask(run, ["attempts"])
    ok("ask: attempts answered within the cap", ans[0] == "6 attempts" and len(ans) <= MAX_LIST + 2, {"verdict": ans[0]})
    print("selftest:", "ALL OK" if not failed else f"{failed} FAILED")
    return 1 if failed else 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "selftest":
        sys.exit(selftest())
    elif len(a) >= 2 and a[0] == "file" and "--home" in a:
        game = a[a.index("--game") + 1] if "--game" in a else None
        print(file_log(a[1], a[a.index("--home") + 1], game))
    elif len(a) >= 2 and a[0] == "check":
        s = check(a[1])
        print(report(s, a[1]))
    elif len(a) >= 2 and a[0] == "ask":
        print("\n".join(ask(a[1], a[2:])))
    else:
        sys.exit(__doc__)
