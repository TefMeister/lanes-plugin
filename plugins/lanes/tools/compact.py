#!/usr/bin/env python3
"""compact.py - keep conversations short: an earlier automatic summary that loses nothing (0.63.0).

    python compact.py status          is the early summary on, at what size, and does this Claude Code have it?
    python compact.py on [PERCENT]    switch it on: the summary happens when the conversation reaches PERCENT
                                      of the model's room (default: `early_summary` in lanes.conf, else 40).
                                      Writes one setting into ~/.claude/settings.json, backed up first.
    python compact.py off             take that setting out again (backed up first)
    python compact.py pre             PreCompact hook: save a checkpoint and the full log, then tell the
                                      summary what must survive (its output becomes summary instructions)
    python compact.py post            SessionStart hook, after a summary: put the checkpoint back in view
    python compact.py end             SessionEnd hook: keep a copy of the full conversation log

WHY (0.63.0, asked for by the maintainer)
  A long conversation costs more for every new message and gets vaguer as it grows. Claude Code already
  summarises a conversation by itself when it is nearly full; this moves that point earlier, and makes
  sure the summary cannot drop what matters: which project, which claim is held, what is not saved on
  GitHub yet, and the next step.

WHAT WAS CHECKED BEFORE BUILDING ON IT (2026-10-13, Claude Code 2.1.296)
  - The setting is the environment value CLAUDE_AUTOCOMPACT_PCT_OVERRIDE. Read in the program itself:
    the summary point becomes min(room x PERCENT/100, room - 13000 tokens), so it can only move EARLIER.
  - Live, three runs: with it set (both as an environment value and from a settings file's `env` block)
    a short conversation was summarised; text printed by the PreCompact hook was kept in the summary word
    for word; the SessionStart hook with source "compact" reached the next turn; and the log file kept
    every earlier message after the summary. [verified-live 2026-10-13, n=3]
  - The summary is prepared in the background and lands on the turn AFTER the point is passed.
  - The `autoCompactWindow` setting did NOT trigger a summary from a --settings file in the same test, so
    this tool does not use it. [measured 2026-10-13, n=1]
  - If a future Claude Code drops the setting, `status` says so and the close-out box falls back to a
    "SAVED - safe to /clear" row (tools/handover.py).

WHAT THE CHECKPOINT HOLDS
  Written by `pre` into the session logs (`session_logs` in lanes.conf, PROTOCOL section 17), one file per
  summary, committed and pushed when that folder is a clone: the project, claims this PC holds, the repos
  holding work not on GitHub, the first OPEN row of the project's board, the last few things the person
  asked for (word for word) and the last reply. The judgement part - folding anything still unrecorded
  into the board - is done by the session itself right after the summary, because a hook cannot know what
  a conversation decided; the summary is told to make that its first step.

THE FULL LOGS
  Claude Code never removes earlier messages from its log file, but it deletes old log files after 30 days
  (cleanupPeriodDays). `pre` and `end` copy the log to `transcripts` in lanes.conf (default
  ~/.claude/lanes-transcripts/<project folder>/), overwriting only the older copy of the same session.

Every hook mode is silent on failure and never blocks a summary or a session end.
"""
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import handover  # noqa: E402  (shares the lanes.conf reader, the repo scan and the claim reader)

ENV_KEY = "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"
CONF_KEY = "early_summary"
DEFAULT_PERCENT = 40                 # of the model's room; the summary itself needs a little more than 13k
PERCENT_MIN, PERCENT_MAX = 10, 95    # below 10 it would summarise almost every turn
LAST_ASKS = 5                        # the person's last requests kept word for word in the checkpoint
ASK_MAX_CHARS = 600
REPLY_MAX_CHARS = 1500
SLUG = "summary-checkpoint"
FOLDER_MAX_CHARS = 48                # of Claude Code's project folder name, in the kept-log path


def settings_path():
    return os.environ.get("LANES_CLAUDE_SETTINGS") or os.path.join(os.path.expanduser("~"), ".claude", "settings.json")


def load_settings():
    try:
        with open(settings_path(), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_settings(data):
    path = settings_path()
    if os.path.isfile(path):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(path, "%s.bak-lanes-%s" % (path, stamp))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def claude_program():
    """The installed Claude Code program file, or None. Native install first, then npm."""
    home = os.path.expanduser("~")
    vdir = os.path.join(home, ".local", "share", "claude", "versions")
    if os.path.isdir(vdir):
        files = [os.path.join(vdir, v) for v in os.listdir(vdir) if os.path.isfile(os.path.join(vdir, v))]
        if files:
            return max(files, key=os.path.getmtime)
    exe = shutil.which("claude")
    if exe:
        npm = os.path.join(os.path.dirname(exe), "node_modules", "@anthropic-ai", "claude-code", "cli.js")
        return npm if os.path.isfile(npm) else os.path.realpath(exe)
    return None


def program_has_setting():
    """True / False when the program could be read; None when it could not be found."""
    path = claude_program()
    if not path:
        return None
    needle = ENV_KEY.encode()
    try:
        with open(path, "rb") as f:
            tail = b""
            while True:
                chunk = f.read(1 << 22)
                if not chunk:
                    return False
                if needle in tail + chunk:
                    return True
                tail = chunk[-len(needle):]
    except OSError:
        return None


def current_percent():
    val = (load_settings().get("env") or {}).get(ENV_KEY)
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def early_summary_on():
    """Is the early summary active on this PC? (used by the close-out box's fallback row)"""
    return current_percent() is not None and program_has_setting() is not False


def wanted_percent(arg, conf):
    raw = arg if arg is not None else conf.get(CONF_KEY, "")
    if str(raw).strip().lower() == "off":
        return None
    try:
        pct = int(float(raw)) if str(raw).strip() else DEFAULT_PERCENT
    except ValueError:
        pct = DEFAULT_PERCENT
    return max(PERCENT_MIN, min(PERCENT_MAX, pct))


def cmd_status():
    has = program_has_setting()
    pct = current_percent()
    if has is None:
        print("EARLY SUMMARY: could not find the Claude Code program to check it.")
    elif not has:
        print("EARLY SUMMARY: this Claude Code does not have the setting; the close-out box shows "
              "\"SAVED - safe to /clear\" instead.")
    if pct is None:
        print("EARLY SUMMARY: off. `compact.py on` switches it on.")
    else:
        print("EARLY SUMMARY: on, at %g%% of the model's room (takes effect in sessions started after it was set)." % pct)
    return 0


def cmd_on(arg):
    if program_has_setting() is False:
        print("EARLY SUMMARY: not switched on - this Claude Code does not have the setting. "
              "The close-out box will say when it is safe to /clear instead.")
        return 1
    pct = wanted_percent(arg, handover.read_conf())
    if pct is None:
        print("EARLY SUMMARY: lanes.conf says early_summary = off; nothing changed.")
        return 0
    data = load_settings()
    env = data.setdefault("env", {})
    if env.get(ENV_KEY) == str(pct):
        print("EARLY SUMMARY: already on at %d%%." % pct)
        return 0
    env[ENV_KEY] = str(pct)
    save_settings(data)
    print("EARLY SUMMARY: on at %d%% (settings.json backed up first). Restart Claude Code for it to apply." % pct)
    return 0


def cmd_off():
    data = load_settings()
    env = data.get("env") or {}
    if ENV_KEY not in env:
        print("EARLY SUMMARY: already off.")
        return 0
    del env[ENV_KEY]
    if not env:
        data.pop("env", None)
    save_settings(data)
    print("EARLY SUMMARY: off (settings.json backed up first). Restart Claude Code for it to apply.")
    return 0


# ---------- the hooks ----------

def hook_input():
    try:
        return json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return {}


def transcripts_root(conf):
    return os.path.expanduser(conf.get("transcripts") or os.path.join("~", ".claude", "lanes-transcripts"))


def keep_transcript(inp, conf):
    """Copy the full log out of Claude Code's 30-day clean-up. Returns the copy's path or ''."""
    src = inp.get("transcript_path") or ""
    if not src or not os.path.isfile(src):
        return ""
    # Claude Code's folder names spell the whole working path out; cut short, a deep root stays under
    # Windows' 260-character path limit (a session id alone keeps every file name unique)
    folder = os.path.basename(os.path.dirname(src))[-FOLDER_MAX_CHARS:].lstrip("-") or "sessions"
    dest_dir = os.path.join(transcripts_root(conf), folder)
    try:
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, os.path.basename(src))
        shutil.copy2(src, dest)
        return dest
    except OSError:
        return ""


def project_of(inp, conf, held):
    """The project this session is on: the claim this PC holds, else the repo the session runs in."""
    if held:
        return held[0].split(" ", 1)[1]
    cwd = inp.get("cwd") or os.getcwd()
    ok, top = handover.git(["rev-parse", "--show-toplevel"], cwd)
    return os.path.basename(top) if ok and top else ""


def next_step(board, project):
    """The first row of the project's OPEN block on the board, or ''."""
    if not board or not project:
        return ""
    try:
        with open(os.path.join(board, "status", project + ".md"), encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return ""
    for i, line in enumerate(lines):
        if re.match(r"^\s*OPEN\b", line):
            for row in lines[i + 1:]:
                if not row.strip():
                    return ""
                if row.strip().startswith("["):
                    return " ".join(row.split())
            return ""
    return ""


def text_of(message):
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
    return ""


def conversation_tail(path):
    """The person's last few requests and the last reply, since the most recent summary."""
    asks, reply = [], ""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("isCompactSummary") or d.get("isMeta"):
                    continue
                if d.get("type") == "user":
                    t = text_of(d.get("message")).strip()
                    if t and not t.startswith("<"):
                        asks.append(t[:ASK_MAX_CHARS])
                elif d.get("type") == "assistant":
                    t = text_of(d.get("message")).strip()
                    if t:
                        reply = t[:REPLY_MAX_CHARS]
    except OSError:
        pass
    return asks[-LAST_ASKS:], reply


def save_checkpoint(project, body):
    """Into the session logs through session-log.py, so it is committed and pushed. Returns its name or ''."""
    tool = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session-log.py")
    try:
        r = subprocess.run([sys.executable, tool, "write", project or "general", SLUG], input=body,
                           capture_output=True, text=True, encoding="utf-8", timeout=90)
    except (OSError, subprocess.SubprocessError):
        return ""
    m = re.search(r"saved (\S+)", r.stdout or "")
    return m.group(1) if m else ""


def cmd_pre():
    inp = hook_input()
    conf = handover.read_conf()
    board = conf.get("board", "")
    me = conf.get("machine_name") or conf.get("role") or "PC"
    held = handover.claims_held(board, me)
    project = project_of(inp, conf, held)
    rows = handover.scan_roots(handover.roots_from(conf))
    unsaved = ["%s: %s" % (r["name"], handover.problem_text(r, short=True)) for r in rows if r["problem"]]
    step = next_step(board, project)
    copy = keep_transcript(inp, conf)
    asks, reply = conversation_tail(inp.get("transcript_path") or "")

    body = ["# Summary checkpoint%s" % (" - " + project if project else ""), "",
            "Written by Lanes just before Claude Code summarised the conversation (%s)." % inp.get("trigger", "auto"), "",
            "- Project: %s" % (project or "none found"),
            "- Claims this PC holds: %s" % (", ".join(held) or "none"),
            "- Not on GitHub yet: %s" % ("; ".join(unsaved) or "nothing"),
            "- Next step on the board: %s" % (step or "no OPEN row found"),
            "- Full conversation log kept at: %s" % (copy or "not copied"), "",
            "## The last things asked for, word for word", ""]
    body += ["> " + a.replace("\n", "\n> ") + "\n" for a in asks] or ["(none found)"]
    body += ["", "## The last reply", "", reply or "(none found)"]
    saved = save_checkpoint(project, "\n".join(body))

    # Everything printed here is added to the summary's instructions by Claude Code.
    out = ["LANES - THE SUMMARY MUST KEEP THESE, WORD FOR WORD:",
           "- Project: %s" % (project or "none"),
           "- Claims held by this PC: %s" % (", ".join(held) or "none"),
           "- Work not on GitHub yet: %s" % ("; ".join(unsaved) or "nothing"),
           "- Next step on the board: %s" % (step or "none recorded"),
           "- The model and gate last named, and any question still waiting for the person's answer.",
           "- Every decision the person made in this conversation, and anything they reported seeing.",
           "- Checkpoint saved as: %s" % (saved or "not saved (no session_logs folder)"),
           "- Full log copy: %s" % (copy or "none"),
           "Make the summary's next step begin with: write onto the board and the project's notes anything "
           "this conversation found or decided that is not recorded there yet, then carry on."]
    print("\n".join(out))
    return 0


def cmd_post():
    hook_input()
    conf = handover.read_conf()
    root = conf.get("session_logs")
    newest = ""
    if root and os.path.isdir(os.path.expanduser(root)):
        best = 0
        for dirpath, _, files in os.walk(os.path.expanduser(root)):
            for name in files:
                if SLUG in name:
                    p = os.path.join(dirpath, name)
                    if os.path.getmtime(p) > best:
                        best, newest = os.path.getmtime(p), p
    text = ("LANES: the conversation was just summarised early to keep it short. Nothing was lost: the full log "
            "is kept on this PC%s. FIRST, before other work: write onto the board and the project's notes anything "
            "the summary says is not recorded yet, and save anything not on GitHub. Then carry on with the next step."
            % ((", and the checkpoint is " + newest) if newest else ""))
    sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
    return 0


def cmd_end():
    keep_transcript(hook_input(), handover.read_conf())
    return 0


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    mode = argv[0] if argv else "status"
    try:
        if mode == "status":
            return cmd_status()
        if mode == "on":
            return cmd_on(argv[1] if len(argv) > 1 else None)
        if mode == "off":
            return cmd_off()
        if mode == "pre":
            return cmd_pre()
        if mode == "post":
            return cmd_post()
        if mode == "end":
            return cmd_end()
    except Exception:  # noqa: BLE001 - a hook must never block a summary or a session end
        return 0 if mode in ("pre", "post", "end") else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
