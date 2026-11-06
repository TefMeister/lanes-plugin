"""UserPromptSubmit hook: the rest reminder, said once per session past the rest time (0.105.0, 2026-11-06; P2).

The maintainer's rule since 2026-09-03 (moved to midnight 2026-10-04): when the clock passes the rest time during a
session, say so at the TOP of the reply, once, even mid-breakthrough; accept the answer, never nag. It lived only in
words that no session loads, and the 2026-11-06 audit found it said in 4 of 33 late-night sessions. Now this hook
hands the session one line the first time a prompt arrives inside the rest window.

Settings (lanes.conf): rest_from = 00:00, rest_until = 06:00 (those are the defaults). Off: the rest_reminder extra
(features.py). Once per session: a marker in <state>/rest-said/<session id>. Prints nothing outside the window, when
already said, or on any error. Run inside prompt-guards.py; still runnable on its own.
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "lanes")
DEFAULT_FROM, DEFAULT_UNTIL = "00:00", "06:00"
HOURS_PER_DAY = 24
MINUTES_PER_HOUR = 60


def minutes(text, default):
    m = re.match(r"^\s*(\d{1,2})[:.](\d{2})\s*$", text or "")
    if not m:
        m = re.match(r"^\s*(\d{1,2}):(\d{2})\s*$", default)
    h, mi = int(m.group(1)), int(m.group(2))
    return (h % HOURS_PER_DAY) * MINUTES_PER_HOUR + mi % MINUTES_PER_HOUR


def inside(now_min, start, end):
    if start == end:
        return False
    if start < end:
        return start <= now_min < end
    return now_min >= start or now_min < end          # a window that crosses midnight, e.g. 23:00-06:00


def now_minutes():
    fake = os.environ.get("LANES_FAKE_TIME")           # tests: "HH:MM"
    if fake:
        return minutes(fake, "12:00")
    t = time.localtime()
    return t.tm_hour * MINUTES_PER_HOUR + t.tm_min


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8-sig", "replace") or "{}")
    except Exception:  # noqa: BLE001
        return 0
    import features
    if not features.is_on("rest_reminder"):
        return 0
    start = minutes(features.conf_value("rest_from"), DEFAULT_FROM)
    end = minutes(features.conf_value("rest_until"), DEFAULT_UNTIL)
    now = now_minutes()
    if not inside(now, start, end):
        return 0
    session = re.sub(r"[^A-Za-z0-9_-]", "", str(data.get("session_id") or "")) or "no-session"
    mark = os.path.join(STATE_DIR, "rest-said", session)
    if os.path.exists(mark):
        return 0
    try:
        os.makedirs(os.path.dirname(mark), exist_ok=True)
        with open(mark, "w", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M\n"))
    except OSError:
        return 0
    clock = "%02d:%02d" % divmod(now, MINUTES_PER_HOUR)
    first = "%02d:%02d" % divmod(start, MINUTES_PER_HOUR)
    text = ("REST (lanes plugin): it is %s, past the rest time the person set (%s). Say so in ONE plain line at the "
            "TOP of this reply, before anything else, then carry on with what they asked. Say it once this session; "
            "if they choose to go on, accept it and never repeat it or argue." % (clock, first))
    sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                        "additionalContext": text}}))
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception:  # noqa: BLE001
        code = 0
    sys.exit(code)
