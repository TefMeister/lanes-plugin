"""file_jitter.py - file one jitter log into the person's BeG0nE home, and answer short questions about a filed one.

    python file_jitter.py file <file.jl> --home <tool home> [--game <project>]
        check the log, write <home>/data/<game>/<stamp>_<runtime>/ (summary.json, report.md, chart.png), add the
        INDEX.csv line, feed the knowledge base; prints ONE line: the verdict.
    python file_jitter.py ask <run folder> <question>
        jitter            the jittery stretches, as time spans
        seconds <a> <b>   the per-second numbers between second a and b (at most 30 rows)
        rates             the overall rates
    python file_jitter.py label <run> jittery|smooth [note] --home <tool home>

Moved here from BeG0nE's ride.py (Lanes 0.62.0), unchanged in what it files.
"""
import csv
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

INDEX_FIELDS = ["run", "game", "runtime", "date", "time", "seconds", "pictures_per_s", "pose_reads_per_s",
                "camera_writes_per_s", "turning_s", "jitter_s", "quality", "verdict"]
MAX_ROWS = 30                   # an answer never lists more rows than this


def log_head(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            first = f.readline()
        return dict(kv.split("=", 1) for kv in first.split()[1:] if "=" in kv)
    except OSError:
        return {}


def file_log(path, home, game=None):
    os.environ["BEGONE_TOOL_HOME"] = home
    import jitter_log_check
    import knowledge
    data = os.path.join(home, "data")
    index = os.path.join(data, "INDEX.csv")
    head = log_head(path)
    game = game or head.get("game", "unknown")
    runtime = head.get("runtime", "unknown")
    stamp = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime(os.path.getmtime(path)))
    run = f"{stamp}_{runtime}"
    out = os.path.join(data, game, run)
    s = jitter_log_check.check(path, out)
    rows = []
    if os.path.exists(index):
        with open(index, newline="", encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if r.get("run") != run]
    rows.append({"run": run, "game": game, "runtime": runtime, "date": stamp[:10], "time": stamp[11:],
                 "seconds": s.get("seconds", 0), "pictures_per_s": s.get("pictures_per_s", 0),
                 "pose_reads_per_s": s.get("pose_reads_per_s", 0), "camera_writes_per_s": s.get("camera_writes_per_s", 0),
                 "turning_s": s.get("seconds_turning", 0), "jitter_s": s.get("seconds_jitter", 0),
                 "quality": s["quality"], "verdict": s["verdict"]})
    os.makedirs(data, exist_ok=True)
    with open(index, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=INDEX_FIELDS)
        w.writeheader(); w.writerows(rows)
    try:
        knowledge.ingest(out)
        knowledge.report()
    except Exception:  # the knowledge base must never stop a filing
        pass
    try:
        import frames   # the recording of the same session, cut at the jittery seconds (0.76.0)
        seen = frames.attach(out, path, game)
    except Exception as e:  # a recording problem must never stop a filing
        seen = f"recording not looked at: {e}"
    return f"{game}/{run}: {s['verdict']} ({seen})"


def spans(windows, kind):
    out, start, last = [], None, None
    for w in windows:
        t = int(w.get("at_s", 0))
        if w.get("kind") == kind:
            if start is None:
                start = t
            last = t
        elif start is not None:
            out.append((start, last)); start = None
    if start is not None:
        out.append((start, last))
    return out


def ask(run_folder, words):
    with open(os.path.join(run_folder, "summary.json"), encoding="utf-8") as f:
        s = json.load(f)
    win = s.get("windows", [])
    q = words[0] if words else "rates"
    if q == "rates":
        return [f"{s.get('seconds', 0)} s; pictures {s.get('pictures_per_s')}/s, pose reads {s.get('pose_reads_per_s')}/s, "
                f"camera writes {s.get('camera_writes_per_s')}/s; turning {s.get('seconds_turning')} s, "
                f"jitter {s.get('seconds_jitter')} s", f"verdict: {s.get('verdict', '')}"]
    if q == "jitter":
        sp = spans(win, "JITTER")
        lines = [f"{len(sp)} jittery stretches, {sum(b - a + 1 for a, b in sp)} s in all"]
        lines += [f"  {a}-{b} s ({b - a + 1} s)" for a, b in sp[:MAX_ROWS]]
        if len(sp) > MAX_ROWS:
            lines.append(f"  ... {len(sp) - MAX_ROWS} more; ask 'seconds <a> <b>' for a stretch")
        return lines
    if q == "seconds" and len(words) >= 3:
        a, b = float(words[1]), float(words[2])
        rows = [w for w in win if a <= w.get("at_s", 0) <= b][:MAX_ROWS]
        keys = ["at_s", "kind", "head_deg_s", "held_share", "camera_per_picture", "pose_per_picture",
                "stale_pose_share", "lag_share", "pose_age_ms"]
        return ["  ".join(keys)] + ["  ".join(str(w.get(k, "")) for k in keys) for w in rows]
    return ["questions: rates | jitter | seconds <a> <b>"]


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) >= 2 and a[0] == "file" and "--home" in a:
        game = a[a.index("--game") + 1] if "--game" in a else None
        print(file_log(a[1], a[a.index("--home") + 1], game))
    elif len(a) >= 2 and a[0] == "ask":
        print("\n".join(ask(a[1], a[2:])))
    elif len(a) >= 3 and a[0] == "label" and "--home" in a:
        i = a.index("--home")
        os.environ["BEGONE_TOOL_HOME"] = a[i + 1]
        rest = a[1:i] + a[i + 2:]
        import knowledge
        knowledge.label(rest[0], rest[1], " ".join(rest[2:]))
    else:
        sys.exit(__doc__)
