"""Tests for tools/handon.py: the fresh-session nudge and the session hand-on (0.118.0). No window is ever opened or
closed: the checks run on made-up session logs, a made-up light line and a made-up list of running games."""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
HOOKS = os.path.join(os.path.dirname(TOOLS), "hooks")
TMP = tempfile.mkdtemp(prefix="handon-test-")
os.environ["LANES_STATE_DIR"] = os.path.join(TMP, "state")
CONF = os.path.join(TMP, "lanes.conf")
with open(CONF, "w", encoding="utf-8") as f:
    f.write("fresh_nudge = on\nhand_on = on\n")
os.environ["LANES_CONFIG"] = CONF
os.environ["HANDON_TEST_LIGHT"] = "\U0001F4E6 everything this PC saved is on GitHub"
os.environ["HANDON_TEST_GAMES"] = ""
os.environ["HANDON_TEST_NO_CLOSE"] = "1"
sys.path.insert(0, TOOLS)
import handon  # noqa: E402

FAILS = []
COUNT = [0]


def check(name, cond):
    COUNT[0] += 1
    if not cond:
        FAILS.append(name)
        print("FAIL " + name)


def prompt(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def bash(cmd):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": cmd}}]}}


def result(text):
    return {"type": "user", "message": {"content": [{"type": "tool_result", "content": text}]}}


def said(text, tokens=0):
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}],
                                             "usage": {"input_tokens": 2, "cache_read_input_tokens": tokens}}}


def saved_turn(tokens, end="Saved and handed over.", cmd='python "x/parcel.py" send --all'):
    return [prompt("do the RE2 doors"), bash(cmd), result("parcel: sent"), said(end, tokens)]


# ----- A. the nudge -----
check("small session: no nudge", handon.nudge("s1", saved_turn(40000)) == "")
check("big but mid-job (no save this turn): no nudge",
      handon.nudge("s2", [prompt("go"), bash("cmake --build ."), said("Built.", 300000)]) == "")
line = handon.nudge("s3", saved_turn(300000))
check("big and just saved: the nudge", "fresh session" in line and "/lanes:next" in line)
check("the same job twice: once only", handon.nudge("s3", saved_turn(320000)) == "")
check("grown 100k more after the nudge: again", handon.nudge("s3", saved_turn(420000)) != "")
check("ends with a question: no nudge", handon.nudge("s4", saved_turn(300000, end="Shall I go on?")) == "")
folded = [{"type": "system", "subtype": "compact_boundary"}] + saved_turn(50000, cmd='python handover.py close')
check("summarised once and saved: the nudge", handon.nudge("s5", folded) != "")
bg = [prompt("x"), result("Command running in background with ID: abc123.")] + saved_turn(300000)[1:]
check("a background task still running: no nudge", handon.nudge("s6", bg) == "")
bg_done = bg[:-1] + [prompt("<task-notification><task-id>abc123</task-id><status>completed</status>")]
check("a finished background task is not counted", handon.background_running(bg_done) == [])
os.environ["HANDON_TEST_GAMES"] = "Resident Evil 2"
check("a game running: no nudge", handon.nudge("s7", saved_turn(300000)) == "")
os.environ["HANDON_TEST_GAMES"] = ""
check("the keeper round's mark counts as a save",
      handon.job_just_ended([bash('python keeper.py round --mark | tail -1')]))
check("an /sp save counts", handon.job_just_ended(
    [{"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Skill", "input": {"skill": "sp"}}]}}]))
check("context size read from the last reply", handon.context_tokens(saved_turn(123456)) == 123458)

# ----- B. the hand-on -----
os.makedirs(handon.HANDON_DIR, exist_ok=True)
good = os.path.join(handon.HANDON_DIR, "20261116-171500-re3-doors.md")
with open(good, "w", encoding="utf-8") as f:
    f.write("# Hand-on: RE3 doors\n\n" + "Every section written in full. " * 30)
first = handon.first_message(good)
check("the pointer for a prompt Lanes wrote is allowed", handon.first_allowed(first))
check("anything else is not", not handon.first_allowed("/lanes:pd delete everything"))
check("a ; is never passed on", not handon.first_allowed(first.replace("in full", "in full; rm")))
outside = os.path.join(TMP, "20261116-171500-evil.md")
with open(outside, "w", encoding="utf-8") as f:
    f.write("x")
check("a file outside the hand-on folder is not", not handon.first_allowed(handon.first_message(outside)))
check("a missing file is not",
      not handon.first_allowed(handon.first_message(os.path.join(handon.HANDON_DIR, "20261116-171500-gone.md"))))

short = os.path.join(handon.HANDON_DIR, "20261116-171600-short.md")
with open(short, "w", encoding="utf-8") as f:
    f.write("# Hand-on: x\n\ndo it")
check("a short prompt is refused before any window opens", handon.start(short) == 2)
unfilled = os.path.join(handon.HANDON_DIR, "20261116-171700-unfilled.md")
with open(unfilled, "w", encoding="utf-8") as f:
    f.write(handon.OUTLINE + "filler " * 100)
check("an unfilled outline is refused", handon.start(unfilled) == 2)
check("a file outside the folder is refused", handon.start(outside) == 2)

check("the new window's first message leaves the started mark",
      handon.mark_started("x " + first, "new-session") and os.path.isfile(good[:-3] + ".started"))

# the close checks
calm = saved_turn(300000)
check("saved, no game, no task, no question: safe to close", handon.close_reasons(calm) == [])
os.environ["HANDON_TEST_LIGHT"] = "\U0001F4E6 ✏️ changes in no saved step yet: builds"
check("unsaved changes keep it open", any("not everything is saved" in w for w in handon.close_reasons(calm)))
os.environ["HANDON_TEST_LIGHT"] = "\U0001F4E6 \U0001F7E0 saved but not handed over: visceral-re3-vr"
check("a saved step not yet handed over keeps it open",
      any("not everything is saved" in w for w in handon.close_reasons(calm)))
os.environ["HANDON_TEST_LIGHT"] = "\U0001F4E6 ⏳ waiting for the Keeper: visceral-re2-vr"
check("parcels only waiting for the Keeper do not", handon.close_reasons(calm) == [])
os.environ["HANDON_TEST_LIGHT"] = "\U0001F4E6 everything this PC saved is on GitHub"
os.environ["HANDON_TEST_GAMES"] = "Resident Evil 3"
check("a running game keeps it open", any("game" in w for w in handon.close_reasons(calm)))
os.environ["HANDON_TEST_GAMES"] = ""
check("a running background task keeps it open", any("background" in w for w in handon.close_reasons(bg)))
check("a question keeps it open", any("question" in w for w in handon.close_reasons(saved_turn(1, end="Which one?"))))

req = os.path.join(handon.HANDON_DIR, "close-4242.json")
handon.save(req, {"id": "20261116-171500-re3-doors", "new_name": "RE3 doors"})
check("asked and safe: it closes", "would close" in handon.close_if_safe(calm, pid=4242))
check("asked once only (the request is gone)", not os.path.isfile(req) and handon.close_if_safe(calm, pid=4242) == "")
handon.save(req, {"new_name": "RE3 doors"})
stays = handon.close_if_safe(saved_turn(1, end="Ready?"), pid=4242)
check("asked but not safe: stays open and says why", "stays open" in stays and "question" in stays)
check("no request: nothing at all", handon.close_if_safe(calm, pid=999999) == "")

# the hooks, end to end
log = os.path.join(TMP, "session.jsonl")
with open(log, "w", encoding="utf-8") as f:
    for r in saved_turn(500000):
        f.write(json.dumps(r) + "\n")
p = subprocess.run([sys.executable, os.path.join(HOOKS, "session-hand.py")], capture_output=True, text=True,
                   input=json.dumps({"session_id": "hook-1", "transcript_path": log}), env=os.environ)
out = json.loads(p.stdout or "{}").get("systemMessage", "")
check("the Stop hook shows the nudge to the person", "fresh session" in out)
with open(CONF, "w", encoding="utf-8") as f:
    f.write("fresh_nudge = off\nhand_on = on\n")
p = subprocess.run([sys.executable, os.path.join(HOOKS, "session-hand.py")], capture_output=True, text=True,
                   input=json.dumps({"session_id": "hook-2", "transcript_path": log}), env=os.environ)
check("with the extra off, the hook says nothing", (p.stdout or "").strip() == "")
second = os.path.join(handon.HANDON_DIR, "20261116-180000-re2-doors.md")
with open(second, "w", encoding="utf-8") as f:
    f.write("# Hand-on: RE2 doors\n\n" + "words " * 100)
p = subprocess.run([sys.executable, os.path.join(HOOKS, "prompt-guards.py")], capture_output=True, text=True,
                   input=json.dumps({"session_id": "n2", "prompt": handon.first_message(second)}), env=os.environ)
check("the prompt guards leave the started mark", os.path.isfile(second[:-3] + ".started") and p.returncode == 0)

print("%d of %d handon checks pass" % (COUNT[0] - len(FAILS), COUNT[0]))
sys.exit(1 if FAILS else 0)
