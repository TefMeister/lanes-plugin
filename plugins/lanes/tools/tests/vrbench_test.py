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
sys.path.insert(0, os.path.join(TOOLS, "vrbench"))

import vb_settings  # noqa: E402
import vb_input  # noqa: E402
import vb_sim  # noqa: E402
import vb_run  # noqa: E402

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
