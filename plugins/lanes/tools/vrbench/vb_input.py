"""vb_input - writes the file the VR Bench layer reads: pretend hands, buttons and sticks (version 1).

The shape is the one the layer's parser is tested against (vr-bench repo, layer/vb_input.h and
test/vb_input_test.cpp). A value left as None is not written, and the layer then passes the runtime's own answer
through for it. Poses are in the room (the LOCAL space), metres; orientations as quaternions x, y, z, w.

    inp = Input().mode(poses="set", buttons="set")
    inp.hand(HAND_LEFT, grip=pose_from_ypr((-0.2, 1.4, -0.4), 0, 0), trigger=0.8)
    write(inp)
"""
import json
import math
import os
import time

import vb_settings as S

_MODES = ("pass", "set", "add")
_BUTTONS = ("a", "b", "x", "y", "menu", "stick_click")


def pose_from_ypr(p, yaw_deg, pitch_deg, roll_deg=0.0):
    """a pose at p (x, y, z), turned yaw about up (Y), then pitch about X, then roll about Z (OpenXR: -Z is forward)"""
    hy, hp, hr = (math.radians(a) / 2 for a in (yaw_deg, pitch_deg, roll_deg))
    qy = (0.0, math.sin(hy), 0.0, math.cos(hy))
    qp = (math.sin(hp), 0.0, 0.0, math.cos(hp))
    qr = (0.0, 0.0, math.sin(hr), math.cos(hr))
    q = _qmul(_qmul(qy, qp), qr)
    return {"p": [float(v) for v in p], "q": [round(v, 9) + 0.0 for v in q]}


def _qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


class Input:
    def __init__(self):
        self._mode = {"poses": "set", "buttons": "set"}
        self._hands = [{}, {}]

    def mode(self, poses="set", buttons="set"):
        if poses not in _MODES or buttons not in _MODES:
            raise ValueError(f"modes are {_MODES}")
        self._mode = {"poses": poses, "buttons": buttons}
        return self

    def hand(self, h, grip=None, aim=None, trigger=None, squeeze=None, stick=None, a=None, b=None,
             x=None, y=None, menu=None, stick_click=None):
        d = self._hands[h]
        if grip is not None:
            d["grip_pose"] = grip
        if aim is not None:
            d["aim_pose"] = aim
        if trigger is not None:
            d["trigger"] = float(trigger)
        if squeeze is not None:
            d["squeeze"] = float(squeeze)
        if stick is not None:
            d["stick"] = [float(stick[0]), float(stick[1])]
        for name, v in zip(_BUTTONS, (a, b, x, y, menu, stick_click)):
            if v is not None:
                d[name] = bool(v)
        return self

    def clear(self):
        self._hands = [{}, {}]
        return self

    def as_dict(self):
        vr = {S.HAND_NAMES[h]: dict(self._hands[h]) for h in (S.HAND_LEFT, S.HAND_RIGHT) if self._hands[h]}
        return {"v": S.INPUT_VERSION, "mode": dict(self._mode), "vr": vr}

    def to_json(self):
        return json.dumps(self.as_dict())


def write(inp, path=None):
    """the layer must never read half a file: write a .tmp beside it, then swap it in (retried while it is open)"""
    path = path or S.INPUT_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(inp.to_json())
    for _ in range(S.REPLACE_RETRIES):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(S.REPLACE_WAIT_S)
    os.remove(tmp)
    raise OSError(f"could not replace {os.path.basename(path)}: held open")
