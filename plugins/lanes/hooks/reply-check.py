"""Stop hook: the reply check (0.105.0, 2026-11-06; audit proposals P1 and, with talk-rule, P11).

The 2026-11-06 audit counted promises that lived only in words and had faded: the green tick ("You can quit the
game now", 0 times in 25 home game sessions), and the 🐚 line under the close-out box (missing in about one write-up
in six). Words are remembered or not; this hook reads the reply that just ended and, when one of these is missing,
hands it back with one line saying what to add, so it is added in the same turn:

  1. a close-out box (🔦) with no 🐚 line under it (what is still running, safe to close?);
  2. "you're right" / "you are right" / "you're correct" / "good catch" outside quotes (the talk rule);
  3. the person is running the game for the session (an earlier reply said "keep it running"), and this reply means
     they may quit, close or restart it, with no ✅ line;
  4. the person is holding something for a test (an earlier reply asked them to hold the controllers, a pose ...),
     and this reply neither frees them with ✅ nor says the hold goes on.

Never loops: when Claude Code says the stop hook is already active, nothing is handed back (the state is still
updated). Off: the reply_check extra. Any error -> silent, exit 0. State: <state>/reply-state/<session id>.json.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "lanes")

QUOTED = re.compile(r"`[^`\n]*`|\"[^\"\n]*\"|“[^”\n]*”")
RIGHT = re.compile(r"\byou(?:'|’| a)re (?:right|correct)\b|\bgood catch\b", re.I)
KEEP_RUNNING = re.compile(r"\b(?:keep|leave) (?:it|the game) running\b", re.I)
MAY_CLOSE = re.compile(r"\b(?:quit|close|restart|relaunch) (?:it|the game)\b|\bneeds? a restart\b|\byou can close\b",
                       re.I)
HOLD = re.compile(r"\bhold (?:the|your|both) (?:controllers?|gun|trigger|button|grip|head|headset|pose|hands?|arms?)\b"
                  r"|\bkeep holding\b|\bhold (?:it|them|still) (?:there|steady|for)\b|\bcontrollers? up\b", re.I)
HOLD_GOES_ON = re.compile(r"\bkeep holding\b|\bstill (?:need you to )?hold", re.I)
TICK = "✅"


def reply_text(data):
    direct = data.get("last_assistant_message")
    if isinstance(direct, str) and direct.strip():
        return direct
    path = data.get("transcript_path") or ""
    if not path or not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()[-400:]
    parts = []
    for line in reversed(lines):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        kind, msg = rec.get("type"), rec.get("message") or {}
        content = msg.get("content")
        if kind == "assistant" and isinstance(content, list):
            texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
            if texts:
                parts.append("\n".join(texts))
        elif kind == "user":
            if isinstance(content, str):
                break
            if isinstance(content, list) and not all(isinstance(b, dict) and b.get("type") == "tool_result"
                                                     for b in content):
                break
    return "\n".join(reversed(parts))


def findings(text, state):
    out = []
    if "\U0001F526" in text and "\U0001F41A" not in text:
        out.append("The write-up has the close-out box but no \U0001F41A line under it: add one line saying what of "
                   "this session is still running and whether the window is safe to close.")
    if RIGHT.search(QUOTED.sub(" ", text)):
        out.append("The reply says \"you're right\" (or \"good catch\"). Check the fact and say what was found "
                   "(\"I checked: ...\"), or \"agreed\" when it really is: add a one-line correction.")
    ticked = TICK in text
    if state.get("game_in_hand") and not ticked and MAY_CLOSE.search(text):
        out.append("The person is running the game for this session and this reply means they may close or restart "
                   "it: add the line ✅ **You can quit the game now.** (or say plainly it must stay open).")
    if state.get("holding") and not ticked and not HOLD.search(text) and not HOLD_GOES_ON.search(text):
        out.append("The person was asked to hold something for the test and this reply does not free them: add "
                   "✅ **You can stop** (or one line saying the hold goes on).")
    return out


def update(state, text):
    if TICK in text:
        state["game_in_hand"] = False
        state["holding"] = False
    if KEEP_RUNNING.search(text):
        state["game_in_hand"] = True
    state["holding"] = bool(HOLD.search(text) or HOLD_GOES_ON.search(text))   # a tick with no new hold frees them
    return state


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8-sig", "replace") or "{}")
    except Exception:  # noqa: BLE001
        return 0
    import features
    if not features.is_on("reply_check"):
        return 0
    text = reply_text(data)
    if not text:
        return 0
    session = re.sub(r"[^A-Za-z0-9_-]", "", str(data.get("session_id") or "")) or "no-session"
    path = os.path.join(STATE_DIR, "reply-state", session + ".json")
    try:
        with open(path, encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError):
        state = {}
    found = [] if data.get("stop_hook_active") else findings(text, state)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(update(dict(state), text), f)
    except OSError:
        pass
    if found:
        sys.stdout.write(json.dumps({"decision": "block", "reason": "Lanes reply check, before this turn ends:\n- "
                                     + "\n- ".join(found)}))
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception:  # noqa: BLE001
        code = 0
    sys.exit(code)
