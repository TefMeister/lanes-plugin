"""handon.py -- the fresh-session nudge and the session hand-on (0.118.0, 2026-11-16).

Asked for by the maintainer, 2026-11-16: "tell me to start a new session when a topic or a feature we are working on
has come to an end and it would be wise, because of expense", and "start a new session, type in a lengthy and
accurate prompt for the re3 job and close the re2 one, when it is safe to do so". Plan: claude-memory
keeper/2026-11-16-fresh-session-and-hand-on-plan.md.

A. THE FRESH-SESSION NUDGE (extra `fresh_nudge`). After every reply (the Stop hook session-hand.py) this looks at the
   session: how big it has grown (the tokens the last reply read, or summarised at least once), whether a job has
   JUST ended (this turn saved and handed over: parcel.py send / light, handover.py close, keeper.py round --mark /
   finish, owed.sh done, or the /sp save), and whether anything is still open (a game running, a background task,
   a question to the person). Only then one line is shown: a good moment for a fresh session. Once per job: again
   only after the session has grown by NUDGE_AGAIN_TOKENS more. Never in the middle of a job.

B. THE SESSION HAND-ON (extra `hand_on`, /lanes:next). On the person's yes to a next job:
     handon.py new "<slug>"            -> where to write the next job's prompt, and the outline it must follow
     handon.py start <file> [--name N] -> opens a NEW window whose first message points at that prompt, waits until
                                          the new session has started on it, then asks for this window to close
   The close itself happens in the Stop hook, when this reply has ended, and only when ALL of these hold: everything
   this PC saved is on GitHub (or the light line names only what waits), no game is running, no background task of
   this session is still running, and the reply does not end with a question. Any one failing: the old window stays
   open and says which. The close is the doorman's normal /exit, so the session's own end steps run; never a kill.

Other verbs: status (this session's size, read from a transcript), check-close <transcript> (the four checks, for a
person or a test). Tests: tests/handon_test.py. Never fails a hook: errors -> silent.
"""
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
HOME = os.path.expanduser("~")
STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(HOME, ".claude", "lanes")
HANDON_DIR = os.path.join(STATE_DIR, "handon")
NUDGE_STATE = os.path.join(STATE_DIR, "fresh-nudge.json")

NUDGE_TOKENS_DEFAULT = 150000      # a session that reads this much for every reply is worth starting fresh
NUDGE_AGAIN_TOKENS = 100000        # after one nudge, the next only once it has grown this much more
START_WAIT_S = 180.0               # how long the new window gets to start on its prompt
CLOSE_DELAY_S = 4.0                # after the reply ends, before /exit is typed (the input box is back by then)
LIGHT_TIMEOUT_S = 150.0
MIN_PROMPT_CHARS = 400             # a hand-on prompt is long and accurate, never one line
MARK = "LANES HAND-ON"
PLACEHOLDER = re.compile(r"(?m)^[#\s]*[^\n<]*<[^<>\n]{3,}>\s*$")      # an outline line still unfilled
ID_RE = r"[0-9]{8}-[0-9]{6}-[a-z0-9-]{1,40}"
FIRST_RE = re.compile(MARK + r" (" + ID_RE + r"): read the hand-on prompt at (.+) in full and carry it out as your job\.")
SAVE_SIGNS = re.compile(r"parcel\.py\"?\s+(?:send|light)|handover\.py\"?\s+close|keeper\.py\"?\s+(?:round\s+--mark|finish)"
                        r"|owed\.sh\"?\s+done")
SAVE_SKILLS = ("sp", "lanes:sp")
BG_STARTED = re.compile(r"running in background with ID: ([A-Za-z0-9]+)")
BG_ENDED = re.compile(r"<task-id>([A-Za-z0-9]+)</task-id>.*?<status>(\w+)</status>", re.S)
UNSAVED = ("REFUSED", "changes in no saved step")
OUTLINE = """# Hand-on: <the next job, in a few words>

## The job, in Tefa's words
<quote the yes and what was asked, word for word>

## Decided so far
<every decision that holds for this job, with who decided and when>

## Read first
<the notes, board rows, dossier sections and files to read, by name, before doing anything>

## Builds and what is installed
<the build numbers, what is installed on which PC, what has been worn or tested and what not>

## Do NOT redo
<what the finished job already did or ruled out, so the new session does not repeat it>

## Gate, model and the first step
<GATE: / MODEL: lines, and the very first thing to do>
"""


# ----- small helpers -----
def conf_value(key, default=""):
    try:
        import features
        v = features.conf_value(key)
        return default if v in (None, "") else v
    except Exception:  # noqa: BLE001
        return default


def is_on(name):
    try:
        import features
        return bool(features.is_on(name))
    except Exception:  # noqa: BLE001
        return False


def read_records(transcript, last=6000):
    if not transcript or not os.path.isfile(transcript):
        return []
    with open(transcript, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()[-last:]
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def context_tokens(records):
    """what the last reply read: its input, cached or not (0 when unknown)"""
    for r in reversed(records):
        if r.get("type") == "assistant":
            u = (r.get("message") or {}).get("usage") or {}
            n = sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens",
                                                 "cache_creation_input_tokens"))
            if n:
                return n
    return 0


def summarised(records):
    return any(r.get("type") == "system" and r.get("subtype") == "compact_boundary" for r in records)


def is_prompt(r):
    """a message the person typed (not a tool result, not a hook's or the system's note)"""
    if r.get("type") != "user" or r.get("isMeta"):
        return False
    c = (r.get("message") or {}).get("content")
    if isinstance(c, str):
        return not c.startswith("<")
    if isinstance(c, list):
        kinds = {b.get("type") for b in c if isinstance(b, dict)}
        return "text" in kinds and "tool_result" not in kinds
    return False


def last_turn(records):
    for i in range(len(records) - 1, -1, -1):
        if is_prompt(records[i]):
            return records[i + 1:]
    return records


def tool_uses(records):
    for r in records:
        if r.get("type") != "assistant":
            continue
        for b in (r.get("message") or {}).get("content") or []:
            if isinstance(b, dict) and b.get("type") == "tool_use":
                yield b.get("name", ""), b.get("input") or {}


def job_just_ended(turn):
    for name, inp in tool_uses(turn):
        if name in ("Bash", "PowerShell") and SAVE_SIGNS.search(str(inp.get("command", ""))):
            return True
        if name == "Skill" and str(inp.get("skill", "")) in SAVE_SKILLS:
            return True
    return False


def final_text(records):
    for r in reversed(records):
        if r.get("type") == "assistant":
            texts = [b.get("text", "") for b in (r.get("message") or {}).get("content") or []
                     if isinstance(b, dict) and b.get("type") == "text"]
            if any(t.strip() for t in texts):
                return "\n".join(texts)
        elif is_prompt(r):
            return ""
    return ""


def ends_with_question(text):
    return text.rstrip().rstrip("*_`").endswith("?")


def text_of(r):
    c = (r.get("message") or {}).get("content")
    if isinstance(c, str):
        return c
    out = []
    for b in c or []:
        if isinstance(b, dict):
            if b.get("type") == "text":
                out.append(b.get("text", ""))
            elif b.get("type") == "tool_result":
                inner = b.get("content")
                out.append(inner if isinstance(inner, str) else
                           " ".join(x.get("text", "") for x in inner or [] if isinstance(x, dict)))
    return "\n".join(out)


def background_running(records):
    """background tasks this session started that have not reported an end"""
    started, ended = [], set()
    for r in records:
        if r.get("type") != "user":
            continue
        t = text_of(r)
        started += BG_STARTED.findall(t)
        ended |= {tid for tid, _status in BG_ENDED.findall(t)}
    return [t for t in dict.fromkeys(started) if t not in ended]


def games_running():
    if os.environ.get("HANDON_TEST_GAMES") is not None:
        return [g for g in os.environ["HANDON_TEST_GAMES"].split(",") if g]
    try:
        import handover
        return handover.games_running()
    except Exception:  # noqa: BLE001
        return []


def light_line():
    if os.environ.get("HANDON_TEST_LIGHT") is not None:
        return os.environ["HANDON_TEST_LIGHT"]
    try:
        p = subprocess.run([sys.executable, os.path.join(HERE, "parcel.py"), "light"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=LIGHT_TIMEOUT_S)
        return (p.stdout or "").strip().splitlines()[-1] if (p.stdout or "").strip() else ""
    except Exception:  # noqa: BLE001
        return "the save check could not be read"


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, path)


# ----- A. the nudge -----
def nudge_mark():
    try:
        return max(20000, int(str(conf_value("fresh_nudge_tokens", NUDGE_TOKENS_DEFAULT)).split()[0]))
    except ValueError:
        return NUDGE_TOKENS_DEFAULT


def nudge(session, records):
    """the one line to show, or '' (the rules in the module text)"""
    tokens, folded = context_tokens(records), summarised(records)
    if tokens < nudge_mark() and not folded:
        return ""
    turn = last_turn(records)
    if not job_just_ended(turn) or ends_with_question(final_text(records)):
        return ""
    if background_running(records) or games_running():
        return ""
    st = load(NUDGE_STATE, {})
    last = st.get(session or "-", {}).get("tokens")
    if last is not None and tokens < last + NUDGE_AGAIN_TOKENS:
        return ""
    st[session or "-"] = {"tokens": tokens, "at": time.strftime("%Y-%m-%d %H:%M")}
    st = dict(list(st.items())[-50:])
    save(NUDGE_STATE, st)
    return ("\U0001F4A1 Good moment for a fresh session: this job is saved, and this window now rereads a very long "
            "history for every reply, so each next step costs more. Say what is next and it can be handed on to a new "
            "window (/lanes:next).")


# ----- B. the hand-on -----
def slug(text):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (s or "next-job")[:40].strip("-")


def new(text):
    os.makedirs(HANDON_DIR, exist_ok=True)
    path = os.path.join(HANDON_DIR, "%s-%s.md" % (time.strftime("%Y%m%d-%H%M%S"), slug(text)))
    print("Write the next job's prompt here (the Write tool), following the outline, then run handon.py start:")
    print(path)
    print()
    print(OUTLINE)
    return 0


def inside_handon_dir(path):
    real, base = os.path.realpath(path), os.path.realpath(HANDON_DIR)
    return os.path.dirname(real) == base and re.fullmatch(ID_RE + r"\.md", os.path.basename(real)) is not None


def first_message(path):
    hid = os.path.basename(path)[:-3]
    return "%s %s: read the hand-on prompt at %s in full and carry it out as your job." % (MARK, hid, path)


def first_allowed(text):
    """the doorman passes a first message on only when it is a hand-on pointer to a file Lanes wrote"""
    m = FIRST_RE.fullmatch(text or "")
    return bool(m) and '"' not in text and ";" not in text and inside_handon_dir(m.group(2)) \
        and os.path.isfile(m.group(2)) and os.path.basename(m.group(2))[:-3] == m.group(1)


def mark_started(prompt, session):
    """UserPromptSubmit (hooks/handon-started.py): the new session has its hand-on prompt"""
    m = FIRST_RE.search(prompt or "")
    if not m or not inside_handon_dir(m.group(2)):
        return False
    save(os.path.join(HANDON_DIR, m.group(1) + ".started"), {"session": session, "at": time.strftime("%Y-%m-%d %H:%M:%S")})
    return True


def own_session_pid():
    try:
        import doorman
        live, procs = set(doorman.session_pids()), doorman.processes()
    except Exception:  # noqa: BLE001
        return 0
    pid, seen = os.getpid(), 0
    while pid in procs and seen < 12:
        if pid in live:
            return pid
        pid, seen = procs[pid][0], seen + 1
    return 0


def start(path, name=""):
    if not inside_handon_dir(path) or not os.path.isfile(path):
        print("hand-on: the prompt must be a file `handon.py new` made (in the hand-on folder); nothing opened")
        return 2
    with open(path, encoding="utf-8", errors="replace") as f:
        body = f.read()
    if len(body.strip()) < MIN_PROMPT_CHARS or PLACEHOLDER.search(body):
        print("hand-on: the prompt is too short or still has the outline's <...> heading; write it in full first")
        return 2
    import doorman
    hid = os.path.basename(path)[:-3]
    mark = os.path.join(HANDON_DIR, hid + ".started")
    r = doorman.open_session(name or "Next " + hid.split("-", 2)[-1].replace("-", " "), first=first_message(path))
    if not r.get("ok"):
        print("hand-on: no new window: %s. This window stays open." % r.get("error", "it did not start"))
        return 1
    deadline = time.time() + float(os.environ.get("HANDON_START_WAIT_S", START_WAIT_S))
    while time.time() < deadline and not os.path.isfile(mark):
        time.sleep(1.0)
    if not os.path.isfile(mark):
        print("hand-on: a new window opened (%s) but has not started on the prompt within %d s. This window stays "
              "open; look at the new one." % (r.get("name") or "pid %d" % r["pid"], START_WAIT_S))
        return 1
    me = own_session_pid()
    if me:
        save(os.path.join(HANDON_DIR, "close-%d.json" % me), {"id": hid, "new_pid": r["pid"], "new_name": r.get("name", ""),
                                                             "at": time.strftime("%Y-%m-%d %H:%M:%S")})
    print("hand-on: the new window '%s' is up and working on the prompt. %s" % (
        r.get("name") or r["pid"], "This window closes by itself when this reply ends, if it is safe."
        if me else "This window could not find itself, so it stays open: close it by hand."))
    return 0


def close_reasons(records):
    """why the old window must stay open ([] = safe to close)"""
    why = []
    light = light_line()
    if not light or any(u in light for u in UNSAVED):
        why.append("not everything is saved (%s)" % (light or "the save check said nothing"))
    games = games_running()
    if games:
        why.append("a game is still running (%s)" % ", ".join(games))
    bg = background_running(records)
    if bg:
        why.append("a background task is still running (%s)" % ", ".join(bg))
    if ends_with_question(final_text(records)):
        why.append("the reply ends with a question for Tefa")
    return why


def close_if_safe(records, pid=None):
    """Stop hook: a close was asked for this window; close it when safe. Returns the line to show, or ''."""
    pid = pid or own_session_pid()
    req = os.path.join(HANDON_DIR, "close-%d.json" % pid) if pid else ""
    if not req or not os.path.isfile(req):
        return ""
    ask = load(req, {})
    try:
        os.remove(req)                       # asked once: never loops
    except OSError:
        pass
    why = close_reasons(records)
    new_name = ask.get("new_name") or "the new window"
    if why:
        return "\U0001F6AA Hand-on: '%s' is up; this window stays open because %s." % (new_name, "; ".join(why))
    if os.environ.get("HANDON_TEST_NO_CLOSE"):
        return "\U0001F6AA Hand-on: would close now (test)."
    subprocess.Popen([sys.executable, os.path.abspath(__file__), "_exit", str(pid)],
                     creationflags=0x00000008 | 0x08000000 if os.name == "nt" else 0, close_fds=True)
    return "\U0001F6AA Hand-on: '%s' has the next job; this window is saved and closes now." % new_name


def exit_later(pid):
    time.sleep(CLOSE_DELAY_S)
    import doorman
    if pid in doorman.session_pids():
        subprocess.run([sys.executable, os.path.join(HERE, "doorman.py"), "_type", str(pid)],
                       creationflags=0x08000000 if os.name == "nt" else 0)
    return 0


def main(argv):
    verb = argv[0] if argv else ""
    if verb == "new":
        return new(" ".join(argv[1:]))
    if verb == "start" and len(argv) > 1:
        name = ""
        if "--name" in argv:
            i = argv.index("--name")
            name = " ".join(argv[i + 1:i + 2])
            argv = argv[:i] + argv[i + 2:]
        return start(argv[1], name)
    if verb == "_exit" and len(argv) > 1:
        return exit_later(int(argv[1]))
    if verb == "status" and len(argv) > 1:
        rec = read_records(argv[1])
        print("read per reply: %d tokens; summarised: %s; mark: %d" % (context_tokens(rec), summarised(rec), nudge_mark()))
        return 0
    if verb == "check-close" and len(argv) > 1:
        why = close_reasons(read_records(argv[1]))
        print("safe to close" if not why else "stays open: " + "; ".join(why))
        return 0 if not why else 1
    print(__doc__.strip().split("\n\n")[0])
    print("usage: handon.py new <slug> | start <file> [--name N] | status <transcript> | check-close <transcript>")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
