#!/usr/bin/env python3
"""vrbench.py - VR Bench: plays a VR game for you, so it can be tested and learned with nobody in the headset.

The OpenXR Simulator plays the headset; the VR Bench layer (TefMeister/vr-bench) plays the hands, buttons and sticks
from a file this tool writes. Design: docs/specs/2026-10-17-vr-bench-design.md.

    python vrbench.py status          is the layer installed and switched on, is the simulator here, the PC profile,
                                      how many runs are on disk
    python vrbench.py start <exe | game>
                                      switch the layer on for the next run of that game, registered for its bitness
                                      only (a game name: `vrbench_exe.<game> = <path>` in lanes.conf, else the one
                                      program in its `builds_app.<game>` folder)
    python vrbench.py stop            switch it off again and take it out of the OpenXR layer list

More commands (learn, profile, install) arrive with the rest of plan 1.
Exit 0 = done, 1 = could not (the reason is printed).
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vb_settings as S  # noqa: E402

OPENXR_SIM = os.path.join(os.path.dirname(HERE), "openxr-sim.py")


def _simulator():
    try:
        r = subprocess.run([sys.executable, OPENXR_SIM, "status", "--json"], capture_output=True, text=True, timeout=60)
        return json.loads(r.stdout)
    except Exception as e:
        return {"installed": False, "error": str(e)}


def _runs():
    if not os.path.isdir(S.RUNS_DIR):
        return 0
    return sum(len(os.listdir(os.path.join(S.RUNS_DIR, g))) for g in os.listdir(S.RUNS_DIR)
               if os.path.isdir(os.path.join(S.RUNS_DIR, g)))


def status():
    bits = [b for b, dll in (("64-bit", S.LAYER_DLL64), ("32-bit", S.LAYER_DLL32))
            if os.path.isfile(os.path.join(S.LAYER_DIR, dll))]
    import vb_layer
    n = len(vb_layer.registered())
    print(f"VR Bench layer: {'installed (' + ', '.join(bits) + ')' if bits else 'not installed'}; "
          f"{'switched ON for a run' if os.path.exists(S.ENABLED_FILE) else 'switched off'}; "
          f"{n} {'copy' if n == 1 else 'copies'} in the OpenXR layer list.")
    sim = _simulator()
    if sim.get("installed"):
        print(f"OpenXR Simulator: on this PC ({sim.get('source') or 'source unknown'}"
              f"{', 32-bit games too' if sim.get('has_32bit') else ', 64-bit games only'}).")
    else:
        print("OpenXR Simulator: not on this PC.")
    print(f"PC profile: {'on file' if os.path.isfile(S.PROFILE_FILE) else 'not made yet'}.")
    print(f"Runs on disk: {_runs()}.")
    return 0


def start(target):
    import vb_layer
    try:
        exe = vb_layer.resolve_exe(target)
        bits = vb_layer.start(exe)
    except (LookupError, ValueError, OSError) as e:
        print(f"VR Bench: could not switch on: {e}")
        return 1
    print(f"VR Bench: on for {os.path.basename(exe)} ({bits}-bit); `vrbench.py stop` switches it off.")
    return 0


def stop():
    import vb_layer
    vb_layer.stop()
    print("VR Bench: off, and out of the OpenXR layer list.")
    return 0


def main(argv):
    if argv[:1] == ["status"]:
        return status()
    if argv[:1] == ["start"] and len(argv) == 2:
        return start(argv[1])
    if argv[:1] == ["stop"]:
        return stop()
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
