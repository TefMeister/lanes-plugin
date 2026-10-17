"""vb_stages_vr - the VR stages: the head through the simulator, the hands and buttons through the VR Bench layer.

Hand positions are the 2026-10-16 Hard Reset list (sim_hands_drive.py), which was measured in the simulator: given
here relative to the head and turned into room positions (the layer's poses are in the LOCAL room space).
"""
import difflib
import re

import vb_input
import vb_settings as S
from vb_stages_flat import STILL_DIFFERENCE

HEAD_POSES = (  # x, y, z, yaw, pitch, roll: straight, turn right, turn left, look up, tilt, lean
    (0.0, S.DEFAULT_HEAD["y"], 0.0, 0, 0, 0), (0.0, S.DEFAULT_HEAD["y"], 0.0, -30, 0, 0),
    (0.0, S.DEFAULT_HEAD["y"], 0.0, 30, 0, 0), (0.0, S.DEFAULT_HEAD["y"], 0.0, 0, 20, 0),
    (0.0, S.DEFAULT_HEAD["y"], 0.0, 0, 0, 10), (0.3, S.DEFAULT_HEAD["y"], 0.0, 0, 0, 0))
HAND_POSES = (  # left hand, relative to the head: centre, left, up, right, down, nearer, farther, wrist yaw, pitch
    (-0.20, -0.30, -0.40, 0, 0), (-0.45, -0.30, -0.40, 0, 0), (-0.20, -0.05, -0.40, 0, 0),
    (0.05, -0.30, -0.40, 0, 0), (-0.20, -0.55, -0.40, 0, 0), (-0.20, -0.30, -0.25, 0, 0),
    (-0.20, -0.30, -0.70, 0, 0), (-0.20, -0.30, -0.40, 90, 0), (-0.20, -0.30, -0.40, 0, -60))
SIGN_TESTS = ((1, 0, -1), (2, 1, -1), (3, 0, +1), (4, 1, +1))   # pose index, picture axis (0 x, 1 y), sign vs centre
SIGNS_NEEDED = 3
POSE_SETTLE_S = 0.5
SWEEP_YAW_DEG = 30   # the slow head sweep at the end of vr_head, for BeG0nE's jitter checker: +-30 degrees,
SWEEP_HZ = 0.1       # once every 10 s (about 19 degrees a second at the fastest: slow and smooth),
SWEEP_S = 12         # for a little over one full swing
RELEASED = dict(trigger=0.0, squeeze=0.0, stick=(0.0, 0.0), a=False, b=False, x=False, y=False, menu=False,
                stick_click=False)   # every input held at rest during a button test, so the simulator's keys cannot press
BUTTONS = (  # label, hand, input values held; the menu last, since it can open a pause menu
    ("right trigger", S.HAND_RIGHT, dict(trigger=1.0)), ("left trigger", S.HAND_LEFT, dict(trigger=1.0)),
    ("A", S.HAND_RIGHT, dict(a=True)), ("B", S.HAND_RIGHT, dict(b=True)), ("X", S.HAND_LEFT, dict(x=True)),
    ("Y", S.HAND_LEFT, dict(y=True)), ("left stick forward", S.HAND_LEFT, dict(stick=(0.0, 1.0))),
    ("right stick right", S.HAND_RIGHT, dict(stick=(1.0, 0.0))), ("menu", S.HAND_LEFT, dict(menu=True)))
PRESS_AGAIN = ("menu",)   # pressed a second time afterwards, to close whatever it opened
NUMBER = re.compile(r"[-+]?\d+(?:[.:]\d+)*")
QUOTE_CHARS = 60
QUOTE_CONTEXT_WORDS = 3
FAMILIAR_LIKENESS = 0.6   # a new line this alike to a known one is that line, changed
IDLE_LEARN_S = 16   # longer than the 15 s summaries our mods print; how long the log is watched with nothing pressed, so lines it prints now and then are known
BUTTON_HOLD_S = 0.4
STICK_HOLD_S = 1.0
EFFECT_WAIT_S = 1.0
LOG_TAIL = 20


def vr_head(L):
    t, pics = L.tools, []
    for i, (x, y, z, yaw, pitch, roll) in enumerate(HEAD_POSES):
        t.head(x, y, z, yaw, pitch, roll)
        t.sleep(POSE_SETTLE_S)
        pics.append(t.sim_shot(f"head_{i}"))
    if not any(pics):
        return L.verdict("vr_head", "UNKNOWN", "the simulator gave no pictures")
    _sweep(t)
    t.head(0.0, S.DEFAULT_HEAD["y"], 0.0, 0, 0, 0)
    moved = sum(1 for a, b in zip(pics, pics[1:]) if a and b and t.picture_diff(a, b) > STILL_DIFFERENCE)
    how = f"the picture followed the head {moved} of {len(pics) - 1} moves"
    if moved == len(pics) - 1:
        L.known_add("Controls", "VR: the picture follows the head, turns, tilt and lean (VR Bench, simulator)")
        return L.verdict("vr_head", "PASS", how, pics[-1])
    return L.verdict("vr_head", "CHECK", how, pics[-1])


def _sweep(t):
    """the simulator turns the head slowly left and right by itself, renewed every frame (head commands from here
    reach it only about 20 times a second, which reads as stepped), so every run leaves BeG0nE a usable recording"""
    t.sweep(True, SWEEP_YAW_DEG, SWEEP_HZ)
    try:
        t.sleep(SWEEP_S)
    finally:
        t.sweep(False)


def _press(hand, values):
    """one button held, every other input of both hands held at rest"""
    inp = vb_input.Input().mode(poses="pass", buttons="set")
    for h in (S.HAND_LEFT, S.HAND_RIGHT):
        inp.hand(h, **RELEASED)
    return inp.hand(hand, **values)


def _hand_input(dx, dy, dz, yaw, pitch):
    p = (dx, S.DEFAULT_HEAD["y"] + dy, dz)
    pose = vb_input.pose_from_ypr(p, yaw, pitch)
    return vb_input.Input().mode(poses="set", buttons="pass").hand(S.HAND_LEFT, grip=pose, aim=pose)


def vr_hands(L):
    t = L.tools
    n = S.HANDS_FULL if L.tier == "full" else S.HANDS_LIGHT
    spots, pics = [], []
    for i, pose in enumerate(HAND_POSES[:n]):
        t.send(_hand_input(*pose))
        t.sleep(POSE_SETTLE_S)
        pic = t.sim_shot(f"hand_{i}")
        pics.append(pic)
        spots.append(t.hand_centroid(pic) if pic else None)
    t.send(vb_input.Input().mode(poses="pass", buttons="pass"))
    if not any(spots):
        return L.verdict("vr_hands", "UNKNOWN", "no hands drawn in this game (nothing hand-coloured in any picture)",
                         next((p for p in pics if p), None))
    right = 0
    for idx, axis, sign in SIGN_TESTS:
        if idx < len(spots) and spots[0] and spots[idx] and (spots[idx][axis] - spots[0][axis]) * sign > 0:
            right += 1
    how = f"the hand moved the right way {right} of {len(SIGN_TESTS)} times"
    if right >= SIGNS_NEEDED:
        L.known_add("Controls", "VR: the left hand follows the controller, left/right/up/down (VR Bench, simulator)")
        return L.verdict("vr_hands", "PASS", how, pics[0])
    return L.verdict("vr_hands", "CHECK", how, pics[0])


def _shape(line):
    """a log line with its numbers taken out, so a counts line that ticks every second keeps one shape"""
    return NUMBER.sub("#", line).strip()


def _likeness(line, seen):
    """how alike line is to the most alike line seen before (0..1), word by word with numbers taken out"""
    words = [_shape(w) for w in line.split()]
    return max((difflib.SequenceMatcher(None, [_shape(w) for w in e.split()], words).ratio() for e in seen.values()),
               default=0.0)


def _new_line(seen, tail):
    """a line in tail whose shape the log has not shown before, or None (seen: shape -> an example line).
    A familiar line that changed ("last: fire") beats a line never seen at all, which may be an occasional one."""
    new = [line for line in tail if _shape(line) not in seen]
    if not new:
        return None
    return max(new, key=lambda line: _likeness(line, seen) >= FAMILIAR_LIKENESS)


def _changed_part(line, seen):
    """the words of line that differ from the most alike line seen before, with a little context around them"""
    words = line.split()
    best, best_ratio = None, 0.0
    for example in seen.values():
        r = difflib.SequenceMatcher(None, [_shape(w) for w in example.split()], [_shape(w) for w in words]).ratio()
        if r > best_ratio:
            best, best_ratio = example.split(), r
    if best is None:
        return line.strip()[:QUOTE_CHARS]
    ops = difflib.SequenceMatcher(None, [_shape(w) for w in best], [_shape(w) for w in words]).get_opcodes()
    for tag, _i1, _i2, j1, j2 in ops:
        if tag != "equal" and j2 > j1:
            lo, hi = max(0, j1 - QUOTE_CONTEXT_WORDS), min(len(words), j2 + QUOTE_CONTEXT_WORDS)
            return ("..." if lo else "") + " ".join(words[lo:hi])[:QUOTE_CHARS] + ("..." if hi < len(words) else "")
    return line.strip()[:QUOTE_CHARS]


def _learn(seen, tail):
    for x in tail:
        seen.setdefault(_shape(x), x)


def vr_buttons(L):
    t, rows, worked = L.tools, [], 0
    # a log that changes by itself is no receipt: learn its usual shapes over one idle press-length first
    seen = {}
    _learn(seen, t.game_log_tail(LOG_TAIL))
    for _ in range(IDLE_LEARN_S):
        t.sleep(1)
        _learn(seen, t.game_log_tail(LOG_TAIL))
    for label, hand, values in BUTTONS:
        before = t.sim_shot(f"button_{label.replace(' ', '_')}_before")
        t.send(_press(hand, values))
        t.sleep(STICK_HOLD_S if "stick" in values else BUTTON_HOLD_S)
        after = t.sim_shot(f"button_{label.replace(' ', '_')}")
        t.send(vb_input.Input().mode(poses="pass", buttons="pass"))
        t.sleep(EFFECT_WAIT_S)
        tail = list(t.game_log_tail(LOG_TAIL))
        line = _new_line(seen, tail)
        quote = _changed_part(line, seen) if line is not None else None
        _learn(seen, tail)
        if line is not None:
            rows.append(f'{label}: the game logged "{quote}"')
            worked += 1
        elif before and after and t.picture_diff(before, after) > STILL_DIFFERENCE:
            rows.append(f"{label}: the picture changed")
            worked += 1
        else:
            rows.append(f"{label}: no visible effect")
        if label in PRESS_AGAIN:
            t.send(_press(hand, values))
            t.sleep(BUTTON_HOLD_S)
            t.send(vb_input.Input().mode(poses="pass", buttons="pass"))
            t.sleep(EFFECT_WAIT_S)
    if worked:
        L.known_add("Controls", "VR: " + "; ".join(r for r in rows if "no visible" not in r) + " (VR Bench, simulator)")
    result = "PASS" if worked == len(BUTTONS) else "CHECK" if worked else "UNKNOWN"
    return L.verdict("vr_buttons", result, "; ".join(rows))
