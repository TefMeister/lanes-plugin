"""vb_sim - talks to the OpenXR Simulator through its command files (webhead2oo9's fork; elliotttate's original has none).

The simulator reads a command file and deletes it [measured 2026-10-16], so every write is a .tmp swapped in with
retries. The head is the simulator's job: VR Bench never moves the head through the layer.
"""
import json
import math
import os
import subprocess
import time

import vb_settings as S


def _command(name, payload, data_dir):
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, name)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    for _ in range(S.REPLACE_RETRIES):
        try:
            os.replace(tmp, path)
            return True
        except PermissionError:
            time.sleep(S.REPLACE_WAIT_S)
    os.remove(tmp)
    return False


def head(x, y, z, yaw_deg, pitch_deg, roll_deg=0.0, data_dir=None):
    """put the simulated head at x, y, z (metres, room) facing yaw / pitch / roll (degrees here, radians in the file)"""
    return _command(S.HEAD_CMD, {"x": x, "y": y, "z": z, "yaw": math.radians(yaw_deg), "pitch": math.radians(pitch_deg),
                                 "roll": math.radians(roll_deg)}, data_dir or S.SIM_DATA_DIR)


def screenshot(out_png, timeout_s=5.0, data_dir=None):
    """ask the simulator for both eyes and save them as a PNG; False when no picture came within timeout_s"""
    data_dir = data_dir or S.SIM_DATA_DIR
    outs = [os.path.join(data_dir, n) for n in S.SHOT_FILES]
    for o in outs:
        try:
            os.remove(o)
        except OSError:
            pass
    t0 = time.time()
    if not _command(S.SHOT_REQ, {"timestamp": t0, "eye": "both", "include_ui": True, "requested_by": "vrbench"}, data_dir):
        return False
    while time.time() - t0 < timeout_s:
        for o in outs:
            if os.path.exists(o) and os.path.getmtime(o) >= t0 - S.SHOT_FRESH_SLACK_S:
                time.sleep(S.SHOT_SETTLE_S)
                from PIL import Image   # only needed once a picture exists
                os.makedirs(os.path.dirname(os.path.abspath(out_png)), exist_ok=True)
                Image.open(o).convert("RGB").save(out_png)
                return True
        time.sleep(S.SHOT_POLL_S)
    return False


def loaded_in(pid):
    """is the simulator's runtime (openxr_simulator*.dll) loaded in process `pid`?"""
    try:
        import psutil
        return any("openxr_simulator" in os.path.basename(m.path).lower() for m in psutil.Process(pid).memory_maps())
    except ImportError:
        pass
    except Exception:
        return False
    r = subprocess.run(["tasklist", "/m", "/fi", f"PID eq {pid}", "/fo", "csv", "/nh"],
                       capture_output=True, text=True)
    return "openxr_simulator" in r.stdout.lower()
