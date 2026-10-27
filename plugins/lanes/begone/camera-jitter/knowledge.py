"""knowledge.py -- the growing knowledge base: what a jittery VR camera looks like in the numbers, what a smooth one
looks like, and which measures separate the two. One entry per PATTERN, never per session, so it holds no copies.

    python knowledge.py ingest <run folder>            add one filed session (the rider does this by itself)
    python knowledge.py label <run> jittery|smooth [note]   what it FELT like in the headset: the truth the base learns from
    python knowledge.py rebuild                        re-read every session in data/ (after a checker change)
    python knowledge.py report                         rewrite knowledge/FINDINGS.md from the base

HOW IT GROWS WITHOUT COPIES: a session's turning seconds are boiled down to a fingerprint, the median of each
measure rounded into a bucket (camera writes per picture to 0.05, shares to 0.05, pose age to 2 ms, ...). Two
sessions with the same fingerprint are the same pattern: the entry gets a tally, the session's run name and its
game, nothing else. A new fingerprint is a new entry. The label (jittery / smooth, from the person wearing the
headset) sticks to the pattern, and a pattern that has been called both is flagged as a contradiction to look at.

HOW IT FINDS THE WHY: for each measure, the values across every jittery pattern and across every smooth pattern.
A measure whose two ranges do not overlap separates the groups; the report says so, per game and across games.
"""
import hashlib
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jitter_log_check import PLACES, place_of  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
# Lanes 0.62.0: the code ships in the plugin; the data and the knowledge live in the person's BeG0nE home.
ROOT = os.environ.get("BEGONE_TOOL_HOME") or os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KNOW = os.path.join(ROOT, "knowledge")
BASE = os.path.join(KNOW, "patterns.json")
FINDINGS = os.path.join(KNOW, "FINDINGS.md")

# the measures a fingerprint is made of, with the bucket each is rounded to and plain words for the report
MEASURES = [
    ("camera_per_picture", 0.05, "camera writes per picture"),
    ("pose_per_picture", 0.05, "pose reads per picture"),
    ("held_share", 0.05, "pictures that went out with an unchanged camera"),
    ("stale_pose_share", 0.05, "pose reads identical to the one before"),
    ("lag_share", 0.10, "pictures whose camera matches the pose before last"),
    ("pose_age_ms", 2.0, "age of the pose when the camera was written (ms)"),
    ("pictures_per_s", 5.0, "pictures a second"),
]
LABELS = ("jittery", "smooth")
MIN_TURNING_WINDOWS = 2        # a session with fewer turning seconds has no fingerprint (nothing to learn from)
SEPARATION_GAP = 0.0           # ranges that do not overlap at all: a separating measure


def _load():
    try:
        with open(BASE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"version": 1, "patterns": {}, "sessions": {}}


def _save(base):
    os.makedirs(KNOW, exist_ok=True)
    with open(BASE, "w", encoding="utf-8") as f:
        json.dump(base, f, indent=1, sort_keys=True)


def fingerprint(summary):
    """(bucketed values dict, id) from a summary.json, or (None, None) when there is nothing to learn from."""
    turning = [w for w in summary.get("windows", []) if w.get("kind") in ("smooth", "JITTER")]
    if len(turning) < MIN_TURNING_WINDOWS:
        return None, None
    vals = {}
    for key, bucket, _ in MEASURES:
        xs = [w[key] for w in turning if w.get(key) is not None] if key != "pictures_per_s" else [summary.get("pictures_per_s")]
        xs = [x for x in xs if x is not None]
        if not xs:
            return None, None
        vals[key] = round(round(float(np.median(xs)) / bucket) * bucket, 3)
    vals["verdict"] = "JITTER" if any(w["kind"] == "JITTER" for w in turning) else "smooth"
    vals["place"] = summary.get("place") or place_of(summary.get("runtime"))   # never pooled across places
    fid = hashlib.sha1(json.dumps(vals, sort_keys=True).encode()).hexdigest()[:10]
    return vals, fid


def ingest(run_folder, base=None, save=True):
    """Adds one filed session. Returns (pattern id, 'new'|'seen'|'skipped')."""
    base = base if base is not None else _load()
    try:
        with open(os.path.join(run_folder, "summary.json"), encoding="utf-8") as f:
            s = json.load(f)
    except (OSError, ValueError):
        return None, "skipped"
    run = os.path.basename(run_folder.rstrip("\\/"))
    game = os.path.basename(os.path.dirname(run_folder.rstrip("\\/")))
    vals, fid = fingerprint(s)
    sess = base["sessions"].setdefault(run, {"game": game, "runtime": s.get("runtime", "?"), "pattern": fid})
    sess["pattern"] = fid
    if fid is None:
        if save: _save(base)
        return None, "skipped"
    pat = base["patterns"].get(fid)
    status = "seen"
    if pat is None:
        pat = base["patterns"][fid] = {"values": vals, "count": 0, "games": {}, "first_seen": time.strftime("%Y-%m-%d"),
                                       "labels": {}, "causes": s.get("causes", [])}
        status = "new"
    pat["count"] = len([r for r, v in base["sessions"].items() if v.get("pattern") == fid])
    pat["games"].setdefault(game, []).append(run) if run not in pat["games"].get(game, []) else None
    pat["last_seen"] = time.strftime("%Y-%m-%d")
    if sess.get("label"):
        pat["labels"][sess["label"]] = pat["labels"].get(sess["label"], 0) + 0  # recounted below
    _recount_labels(base, fid)
    if save: _save(base)
    return fid, status


def _recount_labels(base, fid):
    pat = base["patterns"][fid]
    pat["labels"] = {}
    for run, v in base["sessions"].items():
        if v.get("pattern") == fid and v.get("label"):
            pat["labels"][v["label"]] = pat["labels"].get(v["label"], 0) + 1


def label(run, what, note=""):
    if what not in LABELS:
        sys.exit(f"label must be one of {LABELS}")
    base = _load()
    sess = base["sessions"].get(run)
    if sess is None:
        folder = _find_run(run)
        if folder is None:
            sys.exit(f"no session called {run}; the data/ folder names are the run names")
        ingest(folder, base, save=False)
        sess = base["sessions"][run]
    sess["label"], sess["note"] = what, note
    if sess.get("pattern"):
        _recount_labels(base, sess["pattern"])
    _save(base)
    report(base)
    print(f"{run}: {what}" + (f" ({note})" if note else ""))


def _find_run(run):
    for game in os.listdir(DATA) if os.path.isdir(DATA) else []:
        p = os.path.join(DATA, game, run)
        if os.path.isdir(p):
            return p
    return None


def rebuild():
    base = {"version": 1, "patterns": {}, "sessions": {}}
    old = _load()
    for game in sorted(os.listdir(DATA)) if os.path.isdir(DATA) else []:
        gp = os.path.join(DATA, game)
        if not os.path.isdir(gp):
            continue
        for run in sorted(os.listdir(gp)):
            fid, status = ingest(os.path.join(gp, run), base, save=False)
            if run in old.get("sessions", {}):            # labels and notes survive a rebuild
                for k in ("label", "note"):
                    if old["sessions"][run].get(k):
                        base["sessions"][run][k] = old["sessions"][run][k]
    for fid in base["patterns"]:
        _recount_labels(base, fid)
    _save(base)
    report(base)
    print(f"{len(base['sessions'])} sessions, {len(base['patterns'])} patterns")


def _label_of(pat):
    """The pattern's label: what the wearer said; the checker's verdict when nobody has said."""
    labs = pat.get("labels", {})
    if labs.get("jittery") and labs.get("smooth"):
        return "contradiction"
    if labs.get("jittery"):
        return "jittery"
    if labs.get("smooth"):
        return "smooth"
    return "unlabelled"


def _group_of(pat):
    """The group a pattern is compared in: the wearer's label when there is one, else the checker's own verdict
    (so the base learns without anybody being asked; a label, when given, outranks the checker)."""
    lab = _label_of(pat)
    if lab in ("jittery", "smooth"):
        return lab
    if lab == "unlabelled":
        return "jittery" if pat["values"].get("verdict") == "JITTER" else "smooth"
    return lab


def _place(pat):
    return pat["values"].get("place", "unknown")


def _separations(pats):
    """Per measure: the range across jittery patterns, across smooth ones, and whether they overlap."""
    out = []
    jit = [p for p in pats if _group_of(p) == "jittery"]
    smo = [p for p in pats if _group_of(p) == "smooth"]
    if not jit or not smo:
        return out, len(jit), len(smo)
    for key, _, words in MEASURES:
        a = [p["values"][key] for p in jit]
        b = [p["values"][key] for p in smo]
        lo_a, hi_a, lo_b, hi_b = min(a), max(a), min(b), max(b)
        separates = hi_a < lo_b - SEPARATION_GAP or hi_b < lo_a - SEPARATION_GAP
        out.append((key, words, (lo_a, hi_a), (lo_b, hi_b), separates))
    return out, len(jit), len(smo)


def _fmt(r):
    return f"{r[0]:g}" if r[0] == r[1] else f"{r[0]:g} to {r[1]:g}"


def report(base=None):
    base = base if base is not None else _load()
    pats = list(base["patterns"].values())
    lines = ["# What the numbers say about jittery and smooth VR cameras", "",
             f"Rebuilt {time.strftime('%Y-%m-%d %H:%M')} from {len(base['sessions'])} sessions boiled down to "
             f"{len(pats)} patterns. A pattern is one way a mod behaved; sessions that behaved the same way count "
             f"as one. A pattern is grouped as jittery or smooth by the checker's own verdict, unless the person wearing the "
             f"headset said otherwise with `file_jitter.py label`, which outranks it. Every line is `[measured]` on our own mods.", ""]
    # flat screen, simulator and real headset are compared only with themselves (they feel different)
    sections = []
    for place in [k for k in PLACES if any(_place(p) == k for p in pats)]:
        here = [p for p in pats if _place(p) == place]
        games = sorted({g for p in here for g in p["games"]})
        sections.append((f"Across every game, {PLACES[place]}", here))
        sections += [(f"{g}, {PLACES[place]}", [p for p in here if g in p["games"]]) for g in games]
    for title, group in sections:
        seps, nj, ns = _separations(group)
        lines += [f"## {title}", "", f"{len(group)} patterns: {nj} jittery, {ns} smooth, "
                  f"{sum(1 for p in group if _label_of(p) == 'contradiction')} contradictory, "
                  f"{sum(1 for p in group if _label_of(p) == 'unlabelled')} unlabelled.", ""]
        if not seps:
            lines += ["Nothing to compare yet: it needs at least one labelled jittery and one labelled smooth pattern.", ""]
            continue
        hits = [s for s in seps if s[4]]
        if hits:
            lines += ["**What separates them:**", ""]
            for key, words, ra, rb, _ in hits:
                lines.append(f"- **{words}**: jittery {_fmt(ra)}, smooth {_fmt(rb)}")
            lines.append("")
        lines += ["| measure | jittery | smooth | separates? |", "| --- | --- | --- | --- |"]
        for key, words, ra, rb, sep in seps:
            lines.append(f"| {words} | {_fmt(ra)} | {_fmt(rb)} | {'**yes**' if sep else 'no'} |")
        lines.append("")
    lines += ["## Every pattern", "", "| id | label | where | seen | games | " +
              " | ".join(w for _, _, w in MEASURES) + " | checker said |",
              "| --- | --- | --- | --- | --- | " + " | ".join("---" for _ in MEASURES) + " | --- |"]
    for fid, p in sorted(base["patterns"].items(), key=lambda kv: -kv[1]["count"]):
        v = p["values"]
        lines.append(f"| `{fid}` | {_label_of(p)} | {PLACES[_place(p)]} | {p['count']} | {', '.join(sorted(p['games']))} | " +
                     " | ".join(f"{v[k]:g}" for k, _, _ in MEASURES) + f" | {v['verdict']} |")
    contra = [fid for fid, p in base["patterns"].items() if _label_of(p) == "contradiction"]
    if contra:
        lines += ["", "## Contradictions to look at", "",
                  "The same numbers were called jittery once and smooth another time. Either the label was about "
                  "something the log does not measure, or the fingerprint is too coarse. Patterns: " +
                  ", ".join(f"`{c}`" for c in contra)]
    lines.append("")
    os.makedirs(KNOW, exist_ok=True)
    with open(FINDINGS, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == "ingest" and len(a) >= 2:
        fid, status = ingest(a[1])
        report()
        print(f"pattern {fid}: {status}")
    elif a[0] == "label" and len(a) >= 3:
        label(a[1], a[2], " ".join(a[3:]))
    elif a[0] == "rebuild":
        rebuild()
    elif a[0] == "report":
        report(); print(FINDINGS)
    else:
        sys.exit(__doc__)
