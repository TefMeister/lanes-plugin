"""vb_stages_body - room-scale: the body moves in the room, not only the head on the spot.

Asked for by the maintainer, 2026-10-17, passing on a Discord user's tip: "real life roomscale movement, + roomscale
bending over & crouching. It'll help with tweaking and troubleshooting as well." A seated test never shows what a
player does when they step to the side, lean down to look under something, or crouch behind cover.

Each move goes out and back along a smooth path (the head commands reach the simulator about 20 times a second, so a
path is many small steps, never one jump), with both hands carried along at their usual place beside the body. A
picture at the start, at the far end and back again says whether the game followed.
"""
import vb_input
import vb_settings as S
from vb_stages_flat import STILL_DIFFERENCE

PATH_HZ = 20          # head commands a second: about what the simulator takes in (vb_stages_vr._sweep)
MOVE_S = 3.0          # seconds out, and again back: about a slow step, or a slow crouch
HOLD_S = 1.0          # still at the far end before its picture
NOISE_TIMES = 4.0     # a move counts when the picture changed this many times more than start-to-back-again did
NOISE_FLOOR = 0.05    # the smallest noise used for that, so two identical pictures do not make every change count
HANDS = ((-0.20, -0.30, -0.35), (0.20, -0.30, -0.35))   # left, right: beside the body, relative to the head (m)
MOVES = (  # label, then the far end relative to standing: dx, dy, dz (m, -z ahead), pitch (deg, - looks down)
    ("step forward", 0.0, 0.0, -1.0, 0),
    ("step to the side", 0.6, 0.0, 0.0, 0),
    ("bend over", 0.0, -0.35, -0.30, -50),   # a hip bend: the head goes forward and down, looking at the floor
    ("crouch", 0.0, -0.60, 0.0, 0),
)


def _body(t, x, y, z, pitch):
    """the head at x, y, z looking straight ahead (pitched), both hands where they hang beside it"""
    t.head(x, y, z, 0, pitch, 0)
    inp = vb_input.Input().mode(poses="set", buttons="pass")
    for h, (hx, hy, hz) in zip((S.HAND_LEFT, S.HAND_RIGHT), HANDS):
        pose = vb_input.pose_from_ypr((x + hx, y + hy, z + hz), 0, 0)
        inp.hand(h, grip=pose, aim=pose)
    t.send(inp)


def _glide(t, start, end):
    """from start to end (x, y, z, pitch) in small even steps, eased in and out so it starts and stops gently"""
    steps = max(1, int(MOVE_S * PATH_HZ))
    for i in range(1, steps + 1):
        u = i / steps
        u = u * u * (3 - 2 * u)
        _body(t, *(a + (b - a) * u for a, b in zip(start, end)))
        t.sleep(1.0 / PATH_HZ)


def vr_body(L):
    t, rows, followed, last = L.tools, [], 0, None
    stand = (0.0, S.DEFAULT_HEAD["y"], 0.0, 0)
    for label, dx, dy, dz, pitch in MOVES:
        far = (stand[0] + dx, stand[1] + dy, stand[2] + dz, pitch)
        _body(t, *stand)
        t.sleep(HOLD_S)
        name = label.replace(" ", "_")
        before = t.sim_shot(f"body_{name}_start")
        _glide(t, stand, far)
        t.sleep(HOLD_S)
        there = t.sim_shot(f"body_{name}")
        _glide(t, far, stand)
        t.sleep(HOLD_S)
        back = t.sim_shot(f"body_{name}_back")
        last = there or last
        if not (before and there):
            rows.append(f"{label}: no picture")
            continue
        moved = t.picture_diff(before, there)
        noise = t.picture_diff(before, back) if back else None
        returned = noise is not None and noise < moved
        # a plain wall ahead changes little when the body steps along it (Hard Reset 2026-10-17: sideways 1.0, back to
        # the start 0.1), so beside the fixed bar a move also counts when it is well above the run's own noise
        if moved > STILL_DIFFERENCE or (noise is not None and moved > NOISE_TIMES * max(noise, NOISE_FLOOR)):
            followed += 1
            rows.append(f"{label}: followed" + ("" if returned else ", but did not come back to the start"))
        else:
            rows.append(f"{label}: the picture did not change")
    _body(t, *stand)
    t.send(vb_input.Input().mode(poses="pass", buttons="pass"))
    if not followed and not last:
        return L.verdict("vr_body", "UNKNOWN", "the simulator gave no pictures")
    if followed == len(MOVES):
        L.known_add("Controls", "VR room-scale: stepping forward and sideways, bending over and crouching move the "
                                "view (VR Bench, simulator)")
    result = "PASS" if followed == len(MOVES) else "CHECK" if followed else "UNKNOWN"
    return L.verdict("vr_body", result, "; ".join(rows), last)
