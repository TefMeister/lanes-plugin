#!/usr/bin/env python3
"""vrbench_test - the VR Bench driver's foundations, with no game, no simulator and no headset.

Points LANES_VRBENCH_DIR and LANES_OPENXRSIM_DATA at a throwaway folder before anything is imported, then checks
the input file the layer reads (its shape must match the vr-bench repo's test/vb_input_test.cpp kFile), the pose
maths, the atomic write, the simulator's head command file, a screenshot request that nobody answers, and the run
folder. Run: python tools/tests/vrbench_test.py
"""
import atexit
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
TMP = tempfile.mkdtemp(prefix="vrbench-test-")
atexit.register(shutil.rmtree, TMP, True)
os.environ["LANES_VRBENCH_DIR"] = os.path.join(TMP, "VRBench")
os.environ["LANES_OPENXRSIM_DATA"] = os.path.join(TMP, "OpenXR-Simulator")
os.environ["LANES_VRBENCH_LAYER_DIR"] = os.path.join(TMP, "Programs", "VRBench")
FAKEREG = os.path.join(TMP, "fakereg.json")
os.environ["LANES_VRBENCH_FAKEREG"] = FAKEREG
os.environ["LANES_CONFIG"] = os.path.join(TMP, "lanes.conf")
sys.path.insert(0, os.path.join(TOOLS, "vrbench"))

import vb_settings  # noqa: E402
import vb_input  # noqa: E402
import vb_sim  # noqa: E402
import vb_run  # noqa: E402
import vb_layer  # noqa: E402

HAND_FREEZE = r"C:\Somewhere\HandFreeze\hand_freeze_layer.json"


def fake_exe(name, machine):
    """the smallest file exe_bits reads: 'MZ', the PE offset at 0x3c, 'PE\\0\\0', then the machine word"""
    path = os.path.join(TMP, name)
    data = bytearray(0x40 + 6)
    data[0:2] = b"MZ"
    data[0x3c:0x40] = (0x40).to_bytes(4, "little")
    data[0x40:0x44] = b"PE\0\0"
    data[0x44:0x46] = machine.to_bytes(2, "little")
    with open(path, "wb") as f:
        f.write(data)
    return path


def manifests_installed():
    os.makedirs(vb_settings.LAYER_DIR, exist_ok=True)
    for n in (vb_settings.LAYER_JSON64, vb_settings.LAYER_JSON32):
        with open(os.path.join(vb_settings.LAYER_DIR, n), "w") as f:
            f.write("{}")

# the same file as kFile in vr-bench/test/vb_input_test.cpp, which the layer's parser is tested against
KFILE = {"v": 1, "mode": {"poses": "set", "buttons": "set"},
         "vr": {"left": {"trigger": 0.8, "stick": [0.5, -0.25], "a": True,
                         "grip_pose": {"p": [-0.2, -0.3, -0.4], "q": [0, 0, 0, 1]}},
                "right": {"squeeze": 1.0}}}


class VrBenchTest(unittest.TestCase):
    def test_input_json_shape(self):
        inp = vb_input.Input().mode(poses="set", buttons="set")
        inp.hand(vb_settings.HAND_LEFT, trigger=0.8, stick=(0.5, -0.25), a=True,
                 grip=vb_input.pose_from_ypr((-0.2, -0.3, -0.4), 0.0, 0.0))
        inp.hand(vb_settings.HAND_RIGHT, squeeze=1.0)
        self.assertEqual(json.loads(inp.to_json()), KFILE)

    def test_pose_from_ypr_identity(self):
        self.assertEqual(vb_input.pose_from_ypr((0, 0, 0), 0, 0)["q"], [0.0, 0.0, 0.0, 1.0])
        q = vb_input.pose_from_ypr((0, 0, 0), 90, 0)["q"]
        self.assertAlmostEqual(q[1], math.sin(math.radians(45)), delta=1e-6)
        self.assertAlmostEqual(q[3], math.cos(math.radians(45)), delta=1e-6)

    def test_write_is_atomic(self):
        vb_input.write(vb_input.Input().hand(vb_settings.HAND_LEFT, trigger=1.0))
        self.assertFalse(os.path.exists(vb_settings.INPUT_FILE + ".tmp"))
        with open(vb_settings.INPUT_FILE) as f:
            self.assertEqual(json.load(f)["v"], vb_settings.INPUT_VERSION)

    def test_head_command_file(self):
        vb_sim.head(0, 1.7, 0, 30, 0)
        with open(os.path.join(vb_settings.SIM_DATA_DIR, vb_settings.HEAD_CMD)) as f:
            cmd = json.load(f)
        self.assertAlmostEqual(cmd["yaw"], math.radians(30), delta=1e-9)
        self.assertEqual((cmd["x"], cmd["y"], cmd["z"]), (0, 1.7, 0))

    def test_screenshot_times_out_cleanly(self):
        t0 = time.time()
        ok = vb_sim.screenshot(os.path.join(TMP, "never.png"), timeout_s=0.5)
        self.assertFalse(ok)
        self.assertLess(time.time() - t0, 1.0)

    def test_run_folder_and_stage_record(self):
        run = vb_run.Run.new("x")
        self.assertTrue(os.path.isdir(run.folder))
        run.stage("head", "PASS", "picture followed")
        with open(os.path.join(run.folder, "run.json")) as f:
            rec = json.load(f)
        self.assertEqual(rec["game"], "x")
        self.assertEqual(rec["stages"][-1]["name"], "head")
        self.assertEqual(rec["stages"][-1]["verdict"], "PASS")

    def test_run_input_log(self):
        run = vb_run.Run.new("y")
        run.input_sent(vb_input.Input().hand(0, trigger=0.5))
        run.input_sent(vb_input.Input().hand(1, a=True))
        with open(os.path.join(run.folder, "input.jsonl")) as f:
            lines = [json.loads(line) for line in f if line.strip()]
        self.assertEqual(len(lines), 2)

    def test_status_runs(self):
        env = dict(os.environ, LANES_OPENXRSIM_OFFLINE="1", LANES_OPENXRSIM_NOREG="1",
                   LANES_OPENXRSIM_DIR=os.path.join(TMP, "no-sim"))
        r = subprocess.run([sys.executable, os.path.join(TOOLS, "vrbench", "vrbench.py"), "status"],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("layer", r.stdout.lower())

    # ---- Task 4: the switch and the per-bitness registration ----
    def setUp(self):
        with open(FAKEREG, "w") as f:
            json.dump({HAND_FREEZE: 0}, f)   # someone else's layer is always there
        manifests_installed()
        vb_layer.disable()

    def test_exe_bits_reads_pe_header(self):
        self.assertEqual(vb_layer.exe_bits(fake_exe("a32.exe", 0x14c)), 32)
        self.assertEqual(vb_layer.exe_bits(fake_exe("a64.exe", 0x8664)), 64)

    def test_start_registers_only_that_bitness(self):
        vb_layer.start(fake_exe("g32.exe", 0x14c))
        self.assertEqual(vb_layer.registered(), [vb_layer.manifest_for(32)])
        self.assertTrue(os.path.exists(vb_settings.ENABLED_FILE))

    def test_start_replaces_other_bitness(self):
        vb_layer.register(64)
        vb_layer.start(fake_exe("g32b.exe", 0x14c))
        self.assertEqual(vb_layer.registered(), [vb_layer.manifest_for(32)])

    def test_stop_unregisters_and_disables(self):
        vb_layer.start(fake_exe("g64.exe", 0x8664))
        vb_layer.stop()
        self.assertEqual(vb_layer.registered(), [])
        self.assertFalse(os.path.exists(vb_settings.ENABLED_FILE))

    def test_unregister_leaves_others_alone(self):
        vb_layer.register(64)
        vb_layer.unregister_all()
        with open(FAKEREG) as f:
            self.assertEqual(json.load(f), {HAND_FREEZE: 0})

    def test_start_by_game_name(self):
        exe = fake_exe("named.exe", 0x8664)
        with open(os.environ["LANES_CONFIG"], "w") as f:
            f.write(f"vrbench_exe.some-game-vr = {exe}\n")
        self.assertEqual(vb_layer.resolve_exe("some-game-vr"), exe)
        r = subprocess.run([sys.executable, os.path.join(TOOLS, "vrbench", "vrbench.py"), "start", "some-game-vr"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(vb_layer.registered(), [vb_layer.manifest_for(64)])
        subprocess.run([sys.executable, os.path.join(TOOLS, "vrbench", "vrbench.py"), "stop"], capture_output=True)
        self.assertEqual(vb_layer.registered(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
