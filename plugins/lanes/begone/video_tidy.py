"""video_tidy.py - the BeG0nE recordings take themselves off the PC once nothing needs them (0.90.0, 2026-10-27).

The maintainer, 2026-10-17: "automatic recordings are now only for pairing with the BeG0nE tools and to be deleted
once they are no longer used". Ten days later nothing had ever deleted one (15 videos, 1.9 GB), and asked "see if the
used ones we don't need are actually also automatically removed from the pc?", they said yes to building it.

    python video_tidy.py list      what would go and what stays, one line each (deletes nothing)
    python video_tidy.py tidy      take off the videos nothing needs, and say what went

WHEN A VIDEO IS NO LONGER NEEDED (all three):
  1. it is finished: its <file>.json says when it stopped (a running recording has no stop yet);
  2. its jittery seconds are already cut out as frames: no jitter report of that game from that time is still
     waiting for its recording (a report that has no recording.json yet);
  3. it has been replaced: the same game was recorded again on a LATER DAY (the test was redone, so the job moved on),
     or it is older than MAX_DAYS (nobody came back to that job: it was fixed or dropped).
So a game always keeps the videos of its last test day until it is tested again, or two weeks pass.

WHAT STAYS: the cut frames (sheet.jpg, frames.txt, the f_*.jpg) and every report. Only the .mp4 and its .json go.
Every removal is written to %LOCALAPPDATA%\\BeG0nE\\videos-removed.tsv (when, game, file, size, why). In a folder that
MEGA syncs, a removed file also waits in MEGA's own Rubbish Bin for a while.

Switched on or off with `begone_video_tidy` (features.py). The rider runs `tidy` once an hour while nothing records.
"""
import csv
import glob
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "camera-jitter"))
import begone_common as bc  # noqa: E402
import frames  # noqa: E402   (rec_root: the recordings folder, found the same way obs-rec.py finds it)

MAX_DAYS = 14                    # a video nobody came back to for this long is no longer needed
WAIT_BEFORE_S = 600              # a jitter report that began this long before a recording can still be on it
REMOVED_LOG = os.path.join(bc.LOCAL, "videos-removed.tsv")
DAY = 86400


def videos(root=None):
    """[(game, video path, sidecar)] of every recording that has a sidecar"""
    root = root or frames.rec_root()
    out = []
    for side in glob.glob(os.path.join(root, "*", "*.mp4.json")):
        j = frames.load_json(side) or {}
        out.append((os.path.basename(os.path.dirname(side)), side[:-len(".json")], j))
    return out


def day_of(ms):
    return time.strftime("%Y-%m-%d", time.localtime(ms / 1000))


def waiting_runs():
    """{game: [ms]}: when each jitter report began that has not been lined up with a recording yet"""
    t = bc.tool("camera-jitter")
    out = {}
    if not t:
        return out
    try:
        with open(bc.index_path(t), newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except (OSError, csv.Error):
        return out
    for r in rows:
        run = os.path.join(bc.data_dir(t), r.get("game", ""), r.get("run", ""))
        if os.path.isfile(os.path.join(run, "recording.json")):
            continue
        try:
            at = time.mktime(time.strptime(f"{r['date']} {r['time']}", "%Y-%m-%d %H-%M-%S")) * 1000
        except (KeyError, ValueError):
            continue
        out.setdefault(r.get("game", ""), []).append(at)
    return out


def verdicts(now=None, root=None):
    """[(game, video, size, go?, why)] for every recording"""
    now = (now or time.time()) * 1000
    vids = videos(root)
    waiting = waiting_runs()
    last_day = {}
    for game, _, j in vids:
        if j.get("start_ms") and j.get("stop_ms"):     # a test still being recorded has not replaced anything yet
            last_day[game] = max(last_day.get(game, ""), day_of(j["start_ms"]))
    out = []
    for game, v, j in vids:
        size = os.path.getsize(v) if os.path.isfile(v) else 0
        start, stop = j.get("start_ms"), j.get("stop_ms")
        if not start or not stop:
            out.append((game, v, size, False, "still recording"))
            continue
        if any(start - WAIT_BEFORE_S * 1000 <= at <= stop for at in waiting.get(game, [])):
            out.append((game, v, size, False, "its jitter frames are not cut yet"))
            continue
        if day_of(start) < last_day[game]:
            out.append((game, v, size, True, f"tested again on {last_day[game]}"))
        elif now - stop > MAX_DAYS * DAY * 1000:
            out.append((game, v, size, True, f"older than {MAX_DAYS} days"))
        else:
            out.append((game, v, size, False, "the last test of this game"))
    return sorted(out, key=lambda x: (x[0], os.path.basename(x[1])))


def tidy(now=None, root=None):
    """take off what nothing needs; returns [(game, file, size, why)] of what went"""
    gone = []
    for game, v, size, go, why in verdicts(now, root):
        if not go:
            continue
        try:
            if os.path.isfile(v):
                os.remove(v)
            os.remove(v + ".json")
        except OSError:
            continue                    # in use (a player has it open): next hour
        gone.append((game, os.path.basename(v), size, why))
    if gone:
        os.makedirs(bc.LOCAL, exist_ok=True)
        with open(REMOVED_LOG, "a", encoding="utf-8", newline="\n") as f:
            stamp = time.strftime("%Y-%m-%d %H:%M")
            for g, name, size, why in gone:
                f.write(f"{stamp}\t{g}\t{name}\t{size}\t{why}\n")
    return gone


def mb(n):
    return f"{n / 1048576:.0f} MB"


def main(a):
    if a and a[0] == "tidy":
        gone = tidy()
        if not gone:
            return "BeG0nE videos: nothing to take off"
        return (f"BeG0nE videos: took off {len(gone)} ({mb(sum(g[2] for g in gone))}); their frames stay\n"
                + "\n".join(f"  {g}: {name} ({why})" for g, name, _, why in gone))
    if a and a[0] == "list":
        rows = verdicts()
        if not rows:
            return "BeG0nE videos: none on this PC"
        go = [r for r in rows if r[3]]
        lines = [f"  {'GOES ' if r[3] else 'stays'} {r[0]}: {os.path.basename(r[1])} ({mb(r[2])}, {r[4]})" for r in rows]
        return (f"BeG0nE videos: {len(rows)}, {len(go)} would go ({mb(sum(r[2] for r in go))})\n" + "\n".join(lines))
    return __doc__


if __name__ == "__main__":
    print(main(sys.argv[1:]))
