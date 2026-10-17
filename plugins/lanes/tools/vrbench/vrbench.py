#!/usr/bin/env python3
"""vrbench.py - VR Bench: plays a VR game for you, so it can be tested and learned with nobody in the headset.

The OpenXR Simulator plays the headset; the VR Bench layer (TefMeister/vr-bench) plays the hands, buttons and sticks
from a file this tool writes. Design: docs/specs/2026-10-17-vr-bench-design.md.

    python vrbench.py status [--json] is the layer installed and switched on, is the simulator here, the PC profile,
                                      how many runs are on disk (--json: installed, release, newer, for update)
    python vrbench.py install         download the newest layer from GitHub (TefMeister/vr-bench) and install it;
                                      the same command updates it. Registers nothing.
    python vrbench.py uninstall       remove the layer (runs and pictures stay)
    python vrbench.py start <exe | game>
                                      switch the layer on for the next run of that game, registered for its bitness
                                      only (a game name: `vrbench_exe.<game> = <path>` in lanes.conf, else the one
                                      program in its `builds_app.<game>` folder)
    python vrbench.py stop            switch it off again and take it out of the OpenXR layer list
    python vrbench.py profile         note this PC's specs, OpenXR runtimes, headset and tier (light | full)
    python vrbench.py learn <project> [--minutes 60] [--stage vr_head,vr_hands,vr_body] [--tier light|full]
                                      the learning hour: pre-flight, launch, menus, flat movement, the head, the
                                      hands, room-scale (stepping, bending over, crouching), the buttons, then a
                                      debrief; the game must already be running in the
                                      simulator (only /lm or the person launches games)
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
SIM_STATUS_TIMEOUT_S = 60   # the simulator status check reads GitHub; a slow network must not hang the bench


def _simulator():
    try:
        r = subprocess.run([sys.executable, OPENXR_SIM, "status", "--json"], capture_output=True, text=True, timeout=SIM_STATUS_TIMEOUT_S)
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
    import vb_profile
    prof = vb_profile.read()
    if prof:
        print(f"PC profile: {prof['tier']} tier; headset {'can be worn here' if prof['headset'] == 'real' else 'none here'}"
              f"; made {prof['written']}.")
    else:
        print("PC profile: not made yet (`vrbench.py profile`).")
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


def profile():
    import vb_profile
    conf = {k: S.conf_get(k) for k in ("bench_headset", "bench_tier")}
    prof = vb_profile.collect(conf, vb_profile.Probes())
    vb_profile.write(prof)
    print(f"VR Bench profile: {prof['cpu']}; {', '.join(prof['gpus']) or 'graphics card unknown'}; {prof['ram_gb']} GB.")
    print(f"  OpenXR runtime: {prof['runtime64'] or 'none'} (64-bit games), {prof['runtime32'] or 'none'} (32-bit games).")
    print(f"  Headset: {'can be worn here' if prof['headset'] == 'real' else 'none (simulator only)'}; "
          f"tier: {prof['tier']}; {len(prof['games'])} Steam games installed.")
    return 0


def learn(argv):
    import argparse
    import vb_learn
    import vb_profile
    import vb_run
    import vb_tools
    p = argparse.ArgumentParser(prog="vrbench.py learn")
    p.add_argument("project")
    p.add_argument("--minutes", type=int, default=S.LEARN_MINUTES_DEFAULT)
    p.add_argument("--stage", default="", help="comma-separated stage names (pre-flight and report always run)")
    p.add_argument("--tier", choices=("light", "full"))
    a = p.parse_args(argv)
    stages = [s for s in a.stage.split(",") if s]
    bad = [s for s in stages if s not in vb_learn.STAGES]
    if bad:
        print(f"VR Bench: unknown stage {', '.join(bad)}; the stages are {', '.join(vb_learn.STAGES)}")
        return 1
    tier = a.tier or (vb_profile.read() or {}).get("tier") or "light"
    run = vb_run.Run.new(a.project, tier=tier)
    res = vb_learn.Learn(a.project, a.minutes, stages, tier, run, vb_tools.Tools(a.project, run)).run_all()
    for i, s in enumerate(res["stages"], 1):
        print(f"{i}. {s['name']}: {s['result']}. {s['how']}")
    print(f"Ended: {res['reason']}. The debrief and pictures are in {res['folder']}.")
    return 0 if res["reason"] == "done" else 1


def main(argv):
    if argv[:1] == ["status"] and "--json" in argv:
        import vb_install
        print(json.dumps(vb_install.status()))
        return 0
    if argv[:1] == ["install"]:
        import vb_install
        return vb_install.install()
    if argv[:1] == ["uninstall"]:
        import vb_install
        return vb_install.uninstall()
    if argv[:1] == ["status"]:
        return status()
    if argv[:1] == ["learn"]:
        return learn(argv[1:])
    if argv[:1] == ["profile"]:
        return profile()
    if argv[:1] == ["start"] and len(argv) == 2:
        return start(argv[1])
    if argv[:1] == ["stop"]:
        return stop()
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
