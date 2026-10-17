"""begone.py - the BeG0nE tools ride every session (0.52.0; shipped inside the plugin since 0.62.0).

    python begone.py brief                 start the rider if needed; print what is NEW since the last look (then
                                           bookmark it), the tools and when to read them, and the wiring rules
    python begone.py status                the same, for a person, without moving the bookmark
    python begone.py new [--peek]          only the new reports, one line each (--peek keeps the bookmark where it is)
    python begone.py report <tool> <run|latest> [--game <project>]     one report in full (short by design)
    python begone.py ask <tool> <run|latest> <question...> [--game <project>]
                                           a short answer computed from the numbers, capped in size
    python begone.py frames <tool> <run|latest> [attach | where | <from s> <to s> [--full]] [--game <project>]
                                           the recording of that session, cut at the jittery seconds (0.76.0):
                                           attach (again), where the frames are, or any stretch by log seconds
    python begone.py for "<what the job is>"                which tools to read for this job
    python begone.py tools                 every tool, what it watches, how a mod wires it in

WHY IT IS BUILT LIKE THIS (asked for by the maintainer, 2026-10-12)
  A recording is two things: a short report (a paragraph) and the raw numbers (one Alan Wake session: 600 KB, most
  of a session's reading on its own). So the PC does the counting (each tool's filer, run by the rider the moment a
  headset session ends), the session reads one line per NEW report (a bookmark per PC remembers what was shown),
  opens the full report only when a line looks wrong or the job is linked to that tool, and asks questions through
  `ask`, whose answers are capped. The raw files themselves are locked (hooks/begone-raw-guard.py).

Nothing printed here names a path, a machine or a person: project names, counts and verdicts only.
"""
import csv
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BEGONE = os.path.join(os.path.dirname(HERE), "begone")
sys.path.insert(0, BEGONE)
import begone_common as bc  # noqa: E402

RIDER = os.path.join(BEGONE, "rider.py")
STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "lanes")
SEEN = os.path.join(STATE_DIR, "begone-seen.json")
START_TIMEOUT_S = 20
VERDICT_CHARS = 200             # one new-report line never carries more of the verdict than this
NEW_MAX = 12                    # at most this many new lines at session start; the rest are counted
ASK_MAX_LINES = 60              # an answer is cut here, whatever the tool printed
ASK_MAX_CHARS = 4000
REPORT_MAX_LINES = 80
FRAMES_TIMEOUT_S = 600   # cutting a stretch of a recording into frames (ffmpeg) can take minutes
ASK_TIMEOUT_S = 120      # a tool's own answer to one question

READ_RULE = ("RULE: BeG0nE reports are read, never the raw numbers. After every headset test, run "
             "`begone.py new`; open a full report (`begone.py report <tool> latest`) when a line looks wrong or the "
             "job is linked to that tool (`begone.py for \"<job>\"`); dig further only with `begone.py ask`. "
             "summary.json and the raw recordings are locked. PROTOCOL section 20.")
WIRE_RULE = ("RULE: every VR mod in early development has the jitter recorder wired in, without being asked "
             "(PROTOCOL section 18), and any mod with hand gestures (racking, grabbing, reloading by hand, two-handed "
             "aim) also has Ghost Hand (section 20). `begone.py tools` says how; the files are in the plugin's begone/.")


def rows(t):
    try:
        with open(bc.index_path(t), newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except (OSError, csv.Error):
        return []


def key(t, r):
    return f"{t['folder']}/{r.get('game', '?')}/{r.get('run', '?')}"


def load_seen():
    try:
        with open(SEEN, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save_seen(seen):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(SEEN, "w", encoding="utf-8") as f:
            json.dump(seen, f, indent=0)
    except OSError:
        pass


def new_reports(mark):
    """([(tool, row)] not yet shown on this PC, oldest first; count bookmarked on a first look). The very first
    look bookmarks everything already filed: a session start full of old news gets skimmed."""
    seen = load_seen()
    first = seen is None
    seen = seen or {}
    fresh = [(t, r) for t in bc.tools() for r in rows(t) if key(t, r) not in seen]
    if mark or first:
        for t, r in fresh:
            seen[key(t, r)] = 1
        save_seen(seen)
    if first:
        return [], len(fresh)
    fresh.sort(key=lambda x: (x[1].get("date", ""), x[1].get("time", "")))
    return fresh, 0


def new_line(t, r):
    v = (r.get("verdict") or "").strip()
    if len(v) > VERDICT_CHARS:
        v = v[:VERDICT_CHARS - 3] + "..."
    return f"NEW {t['name']} - {r.get('game', '?')} {r.get('date', '')} {r.get('time', '')}: {v}"


def rider(cmd):
    try:
        r = subprocess.run([sys.executable, RIDER, cmd], capture_output=True, text=True, timeout=START_TIMEOUT_S,
                           env=dict(os.environ, LANES_BEGONE=bc.home()))
        return r.returncode, r.stdout
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def rider_running():
    _, out = rider("status")
    return "rider: running" in out and "OLDER" not in out


def tool_lines():
    out = []
    for t in bc.tools():
        via = (" (checked through " + ", ".join(t["checked_by"]) + ")") if t.get("checked_by") else ""
        out.append(f"  {t['name']}: {len(rows(t))} reports{via}. Read it for: " + ", ".join(t.get("jobs", [])[:10]) + ".")
    return out


def brief(mark=True, start=True):
    running = (start and rider("start")[0] == 0) or rider_running()
    fresh, bookmarked = new_reports(mark)
    total = sum(len(rows(t)) for t in bc.tools())
    out = [f"BeG0nE (in Lanes): rider {'running' if running else 'NOT running (begone.py brief starts it)'}; "
           f"{total} reports on file, {len(fresh)} new since this PC last looked."]
    if bookmarked:
        out.append(f"First look on this PC: {bookmarked} earlier reports bookmarked as read.")
    out += [new_line(t, r) for t, r in fresh[:NEW_MAX]]
    if len(fresh) > NEW_MAX:
        out.append(f"... and {len(fresh) - NEW_MAX} more: begone.py new --peek")
    out.append("Tools:")
    out += tool_lines()
    out += [READ_RULE, WIRE_RULE]
    return "\n".join(out)


def find_run(t, which, game=None):
    rs = [r for r in rows(t) if not game or r.get("game") == game]
    if not rs:
        return None
    if which == "latest":
        r = max(rs, key=lambda r: (r.get("date", ""), r.get("time", "")))
    else:
        r = next((r for r in rs if r.get("run") == which), None)
    return os.path.join(bc.data_dir(t), r["game"], r["run"]) if r else None


def cap(text):
    lines = text.splitlines()
    cut = len(lines) > ASK_MAX_LINES
    out = "\n".join(lines[:ASK_MAX_LINES])
    if len(out) > ASK_MAX_CHARS:
        out, cut = out[:ASK_MAX_CHARS], True
    return out + ("\n[cut here: ask a narrower question]" if cut else "")


def opt(a, name):
    if name in a:
        i = a.index(name)
        v = a[i + 1] if i + 1 < len(a) else None
        del a[i:i + 2]
        return v
    return None


def main(a):
    if not a:
        return __doc__
    cmd = a[0]
    if cmd == "brief":
        return brief()
    if cmd == "status":
        return brief(mark=False, start=False)
    if cmd == "new":
        fresh, bookmarked = new_reports(mark="--peek" not in a)
        if bookmarked:
            return f"First look on this PC: {bookmarked} earlier reports bookmarked as read."
        return "\n".join(new_line(t, r) for t, r in fresh) or "nothing new"
    if cmd == "tools":
        return "\n".join(f"{t['name']} ({t['folder']}): {t['what']}.\n  wire: {t.get('wire', '-')}" for t in bc.tools())
    if cmd == "for" and len(a) >= 2:
        job = " ".join(a[1:]).lower()
        hits = [t["name"] for t in bc.tools() if any(w in job for w in t.get("jobs", []))]
        return ("read: " + ", ".join(hits)) if hits else "no BeG0nE tool is linked to this job"
    if cmd in ("report", "ask", "frames") and len(a) >= 3:
        a = list(a)
        game = opt(a, "--game")
        t = bc.tool(a[1])
        if not t:
            return f"no tool called {a[1]}"
        if not t.get("filer"):
            return f"{t['name']} has no recorder of its own; " + t.get("wire", "")
        run = find_run(t, a[2], game)
        if not run or not os.path.isdir(run):
            return f"no {t['name']} report {a[2]}" + (f" for {game}" if game else "")
        if cmd == "frames":
            fr = os.path.join(t["dir"], "frames.py")
            if not os.path.isfile(fr):
                return f"{t['name']} does not cut recordings"
            rest = [x for x in a[3:] if x != "--game" and x != game] or ["where"]
            if rest[0].replace(".", "", 1).isdigit():   # "<from s> <to s>" is frames.py's cut
                rest = ["cut"] + rest
            r = subprocess.run([sys.executable, fr, rest[0], run] + rest[1:], capture_output=True, text=True,
                               timeout=FRAMES_TIMEOUT_S)
            return cap((r.stdout or r.stderr).strip())
        if cmd == "report":
            try:
                with open(os.path.join(run, "report.md"), encoding="utf-8") as f:
                    lines = [x for x in f.read().splitlines() if not x.startswith("![")]
            except OSError:
                return "that run has no report.md"
            return "\n".join(lines[:REPORT_MAX_LINES])
        r = subprocess.run([sys.executable, os.path.join(t["dir"], t["filer"]), "ask", run] + a[3:],
                           capture_output=True, text=True, timeout=ASK_TIMEOUT_S)
        return cap((r.stdout or r.stderr).strip())
    return __doc__


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")   # reports carry ⚠️; a Windows console is cp1252 (2026-10-17)
    print(main(sys.argv[1:]))
