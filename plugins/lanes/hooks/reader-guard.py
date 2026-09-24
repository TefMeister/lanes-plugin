"""reader-guard.py -- stop the /lm session's background READER writing the board file
the session itself owns.

Wired as PreToolUse only (see hooks/hooks.json). Replaces tandem-guard.py (0.3.0).

WHY THIS EXISTS
  Since 0.4.0 pairing happens INSIDE one /lm session: /lm runs exactly one background
  reader agent that reads, measures and builds while /lm does the live work and owns
  every write. The reader may never touch `<board>/status/<project>.md` -- every
  collision on record (three, 2026-09-05 and 2026-09-09) was that one file, written by
  both halves of a pair. Git behaves PERFECTLY through such a collision: both edits
  rebase cleanly, nothing is lost as far as git can tell, and the later write silently
  undoes the earlier one's fix. No git rule can catch it. This is the floor under the
  written rule.

HOW IT TELLS THE READER FROM THE SESSION -- task zero, 2026-09-10
  Both share ONE session_id, so the old guard's session marker cannot discriminate (it
  would refuse /lm's own writes, or nobody's). What does discriminate: a tool call made
  by a subagent carries `agent_id` (and `agent_type`) in the hook payload; the parent
  session's calls never do. Measured live, full payloads recorded in
  docs/specs/2026-09-10-task-zero-payloads.txt [verified-live 2026-09-10, n=1 each].

  So the rule is stateless: a write to `<board-dir>/status/*.md` whose payload carries
  `agent_id` is refused, exit 2, with the reason. The same write without one is the
  session itself and passes. No marker file, no prompt latch, no SessionEnd cleanup --
  the discriminator is in every call rather than remembered between calls.

WHY IT IS THIS NARROW
  Source, notes and recon evidence never overlapped between the two halves of a pair,
  because they genuinely do different work. So this guards one path shape and nothing
  more. The reader's other bans (never deploy, never edit the curated notes) stay
  behavioural: a deploy target cannot be recognised generically, and a guard that grew
  to cover things it had no evidence for would be the tangle it exists to prevent.

  Bash coverage is BEST EFFORT and says so: a path plus a writing construct is refused,
  anything else passes. Write/Edit/MultiEdit/NotebookEdit are exact.

WHAT IT RECORDS
  Every refusal is appended to $LANES_READER_LOG (default ~/.claude/lanes-reader-
  refusals.log) as one tab-separated line, so `tools/run-log.sh --reader` can harvest
  "clean /lm runs with the reader" instead of anyone typing them. A refusal is not a
  failure of the guard -- it is the guard working -- but it IS evidence the reader
  tried, which the release checklist wants to see counted honestly.

  No board, unreadable input, any exception at all -> exit 0, silent. THIS GUARD MUST
  NEVER FAIL CLOSED: a broken guard that blocks every write is worse than no guard.
"""
import json
import os
import re
import sys
import time

LOG = os.environ.get("LANES_READER_LOG") or os.path.join(
    os.path.expanduser("~"), ".claude", "lanes-reader-refusals.log")

WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")

# A Bash command mentioning the path is only refused if it also looks like a WRITE.
# Deliberately does not include a bare "-i": `grep -i pattern status/x.md` is a read.
BASH_WRITES = re.compile(r">>?|\btee\b|\bsed\s+-i|\bperl\s+-i|\bmv\b|\bcp\b|<<")


def read_conf(key):
    """Read `key = value` from the same config file the shell tools use."""
    candidates = [os.environ.get("LANES_CONFIG"),
                  os.path.expanduser("~/.claude/lanes.conf"),
                  os.path.expanduser("~/.config/lanes/lanes.conf")]
    pat = re.compile(r"^\s*" + re.escape(key) + r"\s*=\s*(.*?)\s*$")
    for path in candidates:
        if not path or not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    m = pat.match(line.rstrip("\r\n"))
                    if m:
                        return m.group(1).strip().strip('"')
        except Exception:
            continue
    return None


def board_dir_name():
    """The board repo's FOLDER name, not its path.

    Matching the configured path would only guard one clone root. The same repo is
    cloned per lane, and a write into any of them is the same write. The folder name
    is what they share.
    """
    explicit = read_conf("board_dir")
    if explicit:
        return explicit.strip("/\\")
    board = os.environ.get("LANES_BOARD") or read_conf("board")
    if not board:
        return None
    return os.path.basename(board.rstrip("/\\"))


def guarded_path(text, dirname):
    """Does `text` name a status file inside a folder called `dirname`?

    Compared with separators normalised and case folded, so it behaves the same on
    Windows and on a case-sensitive filesystem.
    """
    if not text or not dirname:
        return None
    hay = str(text).replace("\\", "/").lower()
    needle = "/" + dirname.lower() + "/status/"
    idx = hay.find(needle)
    if idx < 0:
        return None
    tail = hay[idx + len(needle):]
    seg = tail.split("/")[0].split()[0] if tail.split("/")[0] else ""
    seg = seg.strip("\"'")
    return seg if seg.endswith(".md") else None


def targets(tool, tool_input):
    """Every path this tool call would write. Bash is best effort, and says so."""
    if not isinstance(tool_input, dict):
        return []
    if tool in WRITE_TOOLS:
        return [str(tool_input.get("file_path")
                    or tool_input.get("notebook_path") or "")]
    if tool == "Bash":
        cmd = str(tool_input.get("command", ""))
        return [cmd] if BASH_WRITES.search(cmd) else []
    return []


def record(agent_id, agent_type, tool, hit, sid):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("\t".join([
                time.strftime("%Y-%m-%dT%H:%M:%S"), str(sid), str(agent_id),
                str(agent_type), str(tool), str(hit)]) + "\n")
    except Exception:
        # The log is evidence, not the control. Failing to write it must not block.
        pass


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    if data.get("hook_event_name", "") != "PreToolUse":
        return 0

    # The whole decision. No agent_id -> this is the session itself -> never refused.
    agent_id = data.get("agent_id")
    if not agent_id:
        return 0

    dirname = board_dir_name()
    if not dirname:
        return 0

    tool = data.get("tool_name", "")
    for text in targets(tool, data.get("tool_input", {})):
        hit = guarded_path(text, dirname)
        if not hit:
            continue
        record(agent_id, data.get("agent_type", ""), tool, hit, data.get("session_id", ""))
        sys.stderr.write(
            "READER GUARD: a background agent must not write {d}/status/{f}.\n"
            "The /lm session that started you owns that file. Two edits to it both rebase "
            "cleanly and the later silently undoes the earlier -- git cannot see that, "
            "which is why this is a hook and not a note.\n"
            "Hand the finding back to the session instead: return it in your report, or "
            "drop it as a NEW file in the project's inbox/ folder. The session writes the "
            "board.\n".format(d=dirname, f=hit))
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
