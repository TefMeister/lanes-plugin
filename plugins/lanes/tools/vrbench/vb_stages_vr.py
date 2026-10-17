"""vb_stages_vr - the VR stages: the head through the simulator, the hands and buttons through the VR Bench layer.

Hand positions are the 2026-10-16 Hard Reset list (sim_hands_drive.py), which was measured in the simulator: given
here relative to the head and turned into room positions (the layer's poses are in the LOCAL room space).
"""
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
BUTTONS = (  # label, hand, input values held
    ("right trigger", S.HAND_RIGHT, dict(trigger=1.0)), ("left trigger", S.HAND_LEFT, dict(trigger=1.0)),
    ("A", S.HAND_RIGHT, dict(a=True)), ("B", S.HAND_RIGHT, dict(b=True)), ("X", S.HAND_LEFT, dict(x=True)),
    ("Y", S.HAND_LEFT, dict(y=True)), ("menu", S.HAND_LEFT, dict(menu=True)),
    ("left stick forward", S.HAND_LEFT, dict(stick=(0.0, 1.0))), ("right stick right", S.HAND_RIGHT, dict(stick=(1.0, 0.0))))
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
    t.head(0.0, S.DEFAULT_HEAD["y"], 0.0, 0, 0, 0)
    moved = sum(1 for a, b in zip(pics, pics[1:]) if a and b and t.picture_diff(a, b) > STILL_DIFFERENCE)
    how = f"the picture followed the head {moved} of {len(pics) - 1} moves"
    if moved == len(pics) - 1:
        L.known_add("Controls", "VR: the picture follows the head, turns, tilt and lean (VR Bench, simulator)")
        return L.verdict("vr_head", "PASS", how, pics[-1])
    return L.verdict("vr_head", "CHECK", how, pics[-1])


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


def vr_buttons(L):
    t, rows, worked = L.tools, [], 0
    for label, hand, values in BUTTONS:
        log0 = list(t.game_log_tail(LOG_TAIL))
        before = t.sim_shot(f"button_{label.replace(' ', '_')}_before")
        t.send(vb_input.Input().mode(poses="pass", buttons="set").hand(hand, **values))
        t.sleep(STICK_HOLD_S if "stick" in values else BUTTON_HOLD_S)
        after = t.sim_shot(f"button_{label.replace(' ', '_')}")
        t.send(vb_input.Input().mode(poses="pass", buttons="pass"))
        t.sleep(EFFECT_WAIT_S)
        if list(t.game_log_tail(LOG_TAIL)) != log0:
            rows.append(f"{label}: the game logged something")
            worked += 1
        elif before and after and t.picture_diff(before, after) > STILL_DIFFERENCE:
            rows.append(f"{label}: the picture changed")
            worked += 1
        else:
            rows.append(f"{label}: no visible effect")
    if worked:
        L.known_add("Controls", "VR: " + "; ".join(r for r in rows if "no visible" not in r) + " (VR Bench, simulator)")
    result = "PASS" if worked == len(BUTTONS) else "CHECK" if worked else "UNKNOWN"
    return L.verdict("vr_buttons", result, "; ".join(rows))
