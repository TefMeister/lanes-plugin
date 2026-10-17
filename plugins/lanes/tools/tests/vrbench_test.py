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
import vb_profile  # noqa: E402


class FakeProbes:
    def __init__(self, gpus, ram):
        self._gpus, self._ram = gpus, ram

    def cpu(self): return "Some CPU"
    def gpus(self): return list(self._gpus)
    def ram_gb(self): return self._ram
    def windows(self): return "Windows 10"
    def runtime(self, bits): return f"runtime-{bits}.json"
    def games(self): return ["Hard Reset Redux"]


import vb_learn
import vb_stages_vr  # noqa: E402


class FakeTools:
    """everything the learning hour does to the outside world, answered from memory; `calls` keeps the order"""

    def __init__(self, sim=True, jump_after=None, crash_in=None, hands=True, pictures_change=True, chatty=False,
                 receipts=True):
        self.sim, self.jump_after, self.crash_in, self.hands, self.change = sim, jump_after, crash_in, hands, pictures_change
        self.chatty, self.receipts, self.sent, self.heads, self.sweeps = chatty, receipts, [], [], []
        self.t, self.calls, self.log, self.pic_n, self.pressed = 0.0, [], [], 0, False
        self.hand_x = self.hand_y = 0.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s
        if self.chatty:   # like Hard Reset's mod: a counts line every second, whatever happens
            self.log.append(f"[{self.t:.1f}] controls per s: updates {int(self.t * 37) % 90}, keys pressed 0")

    def sim_installed(self): return self.sim
    def resolve_exe(self, game): return "C:/Games/fake.exe"
    def known(self): return "# fake\n\n## Controls\n\n- 2026-10-17 music volume: Options > Audio\n"
    def known_add(self, section, text): self.calls.append(f"known {section}")
    def claim(self, take): self.calls.append(f"claim {take}")
    def profile(self): self.calls.append("profile")
    def layer_start(self, exe): self.calls.append("layer_start")
    def layer_stop(self): self.calls.append("layer_stop")
    def logs(self): return []
    def find_route(self, start, end): return f"routes/{start}_to_{end}.json"

    def mom(self, args):
        self.calls.append("mom " + args[0])
        if self.jump_after == "menus" and args[0] == "run" and "keybindings" in args[1]:
            self.t += 61 * 60   # the hour runs out while the menus stage is busy
        return {"code": 0, "events": []}

    def _pic(self, name):
        self.pic_n += 1
        return f"{name}-{self.pic_n if self.change else 0}.png"

    def flat_shot(self, name):
        if self.crash_in == "flat":
            raise RuntimeError("the window vanished")
        return self._pic(name)

    def turn(self, px, name): return self._pic(name)
    def probe(self, key, seconds): return True
    def picture_diff(self, a, b): return 0.0 if a.split("-")[-1] == b.split("-")[-1] else 10.0
    def sweep(self, on, yaw_amp=0.0, hz=0.0):
        self.sweeps.append((self.t, on, yaw_amp, hz))

    def head(self, *pose):
        self.calls.append("head")
        self.heads.append((self.t, pose))
    def sim_shot(self, name): return self._pic(name)

    def send(self, inp):
        d = inp.as_dict()
        left = d["vr"].get("left", {})
        if "grip_pose" in left:
            self.hand_x, self.hand_y = left["grip_pose"]["p"][0], left["grip_pose"]["p"][1]
        held = any(v for h in d["vr"].values() for k, v in h.items() if not k.endswith("_pose"))
        self.sent.append(d["vr"])
        if held and self.receipts:
            names = sorted(f"{h} {k}" for h, v in d["vr"].items() for k, x in v.items()
                           if x and not k.endswith("_pose") and x != [0.0, 0.0])
            self.log.append(f"pressed {names}")   # our mods log what they were sent, by name

    def hand_centroid(self, png):
        # the picture's y grows downwards, so a higher hand has a smaller y
        return (640 + self.hand_x * 1000, 400 - self.hand_y * 1000) if self.hands else None

    def game_log_tail(self, n): return self.log[-n:]


def learn(tools, stages=None):
    run = vb_run.Run.new("fake-game")
    return vb_learn.Learn("fake-game", 60, stages, "full", run, tools).run_all()


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

    # ---- Task 6: the learning hour, with fake tools ----
    def test_preflight_refuses_without_simulator(self):
        tools = FakeTools(sim=False)
        res = learn(tools)
        self.assertTrue(res["reason"].startswith("simulator"), res["reason"])
        with open(os.path.join(res["folder"], "run.json")) as f:
            self.assertTrue(json.load(f)["reason"].startswith("simulator"))

    def test_stages_run_in_order_and_record(self):
        res = learn(FakeTools())
        with open(os.path.join(res["folder"], "run.json")) as f:
            stages = json.load(f)["stages"]
        self.assertEqual([s["name"] for s in stages], vb_learn.STAGES)
        self.assertEqual({s["verdict"] for s in stages}, {"PASS"}, stages)

    def test_time_limit_stops_early(self):
        tools = FakeTools(jump_after="menus")
        res = learn(tools)
        self.assertEqual(res["reason"], "time")
        self.assertEqual(res["stages"][-1]["name"], "menus")
        self.assertTrue(os.path.isfile(os.path.join(res["folder"], "debrief.md")))

    def test_claim_and_layer_released_on_crash(self):
        tools = FakeTools(crash_in="flat")
        res = learn(tools)
        self.assertTrue(res["reason"].startswith("error: "), res["reason"])
        self.assertEqual(tools.calls[-2:], ["layer_stop", "claim False"])

    def test_only_requested_stages(self):
        res = learn(FakeTools(), stages=["vr_head"])
        self.assertEqual([s["name"] for s in res["stages"]], ["preflight", "vr_head", "report"])

    def test_hands_unknown_without_centroid(self):
        res = learn(FakeTools(hands=False), stages=["vr_hands"])
        hands = [s for s in res["stages"] if s["name"] == "vr_hands"][0]
        self.assertEqual(hands["result"], "UNKNOWN")
        self.assertIn("no hands drawn", hands["how"])

    def test_buttons_pass_on_log_line(self):
        res = learn(FakeTools(pictures_change=False), stages=["vr_buttons"])
        buttons = [s for s in res["stages"] if s["name"] == "vr_buttons"][0]
        self.assertEqual(buttons["result"], "PASS", buttons["how"])
        self.assertIn("right trigger: the game logged", buttons["how"])

    def test_buttons_chatty_log_alone_is_not_a_receipt(self):
        # Hard Reset 2026-10-17: the mod logs a line every second, so "the log changed" passed every button
        res = learn(FakeTools(pictures_change=False, chatty=True, receipts=False), stages=["vr_buttons"])
        buttons = [s for s in res["stages"] if s["name"] == "vr_buttons"][0]
        self.assertEqual(buttons["result"], "UNKNOWN", buttons["how"])
        self.assertIn("right trigger: no visible effect", buttons["how"])

    def test_buttons_chatty_log_with_receipt_names_the_line(self):
        res = learn(FakeTools(pictures_change=False, chatty=True), stages=["vr_buttons"])
        buttons = [s for s in res["stages"] if s["name"] == "vr_buttons"][0]
        self.assertEqual(buttons["result"], "PASS", buttons["how"])
        self.assertIn('right trigger: the game logged "pressed', buttons["how"])

    def test_buttons_quote_the_changed_part(self):
        class CountsLine(FakeTools):   # Hard Reset's receipt: one long counts line whose "last:" word changes
            def sleep(self, s):
                self.t += s
                self.log.append(f"[{self.t:.1f}] controls per s: the game asked the pad 0 times, updates "
                                f"{int(self.t * 37) % 90}, keys pressed 0 (last: none), sprint off, snap turns 0")

            def send(self, inp):
                d = inp.as_dict()
                self.sent.append(d["vr"])
                if any(v for h in d["vr"].values() for k, v in h.items() if not k.endswith("_pose")):
                    self.log.append(f"[{self.t:.1f}] controls per s: the game asked the pad 0 times, updates 74, "
                                    "keys pressed 1 (last: fire), sprint off, snap turns 0")
        res = learn(CountsLine(pictures_change=False, chatty=True, receipts=False), stages=["vr_buttons"])
        buttons = [s for s in res["stages"] if s["name"] == "vr_buttons"][0]
        self.assertIn("(last: fire)", buttons["how"].split(";")[0])

    def test_buttons_prefer_a_changed_familiar_line_over_a_one_off(self):
        # Hard Reset: a "created so far by pool" line came at the same moment as "(last: fire)" and was quoted instead
        class Both(FakeTools):
            def sleep(self, s):
                self.t += s
                self.log.append(f"[{self.t:.1f}] controls per s: the game asked the pad 0 times, updates "
                                f"{int(self.t * 37) % 90}, keys pressed 0 (last: none), sprint off, snap turns 0")

            def send(self, inp):
                d = inp.as_dict()
                self.sent.append(d["vr"])
                if any(v for h in d["vr"].values() for k, v in h.items() if not k.endswith("_pose")):
                    self.log.append(f"[{self.t:.1f}] created so far by pool 12 / 40 / 3")
                    self.log.append(f"[{self.t:.1f}] controls per s: the game asked the pad 0 times, updates 74, "
                                    "keys pressed 1 (last: fire), sprint off, snap turns 0")
        res = learn(Both(pictures_change=False, receipts=False), stages=["vr_buttons"])
        buttons = [s for s in res["stages"] if s["name"] == "vr_buttons"][0]
        self.assertIn("(last: fire)", buttons["how"].split(";")[0])

    def test_buttons_ignore_a_line_that_comes_every_few_seconds(self):
        class Periodic(FakeTools):   # like the pool counts line Hard Reset's mod prints now and then
            def sleep(self, s):
                before = int(self.t // 3)
                super().sleep(s)
                if int(self.t // 3) != before:
                    self.log.append(f"[{self.t:.1f}] created so far by pool 12 / 40 / 3")
        res = learn(Periodic(pictures_change=False, receipts=False), stages=["vr_buttons"])
        buttons = [s for s in res["stages"] if s["name"] == "vr_buttons"][0]
        self.assertEqual(buttons["result"], "UNKNOWN", buttons["how"])

    def test_buttons_hold_every_other_input_released(self):
        # the simulator turns some keys into controller presses (Space = right trigger): Hard Reset's jump also fired
        tools = FakeTools(pictures_change=False)
        learn(tools, stages=["vr_buttons"])
        held = [d for d in tools.sent if any(v for h in d.values() for k, v in h.items() if not k.endswith("_pose"))]
        for d in held:
            self.assertEqual(set(d), {"left", "right"}, d)
            for h in d.values():
                for k in ("trigger", "squeeze", "stick", "a", "b", "x", "y", "menu", "stick_click"):
                    self.assertIn(k, h, d)
        a = [d for d in held if d["right"]["a"]][0]
        self.assertEqual(a["right"]["trigger"], 0.0)

    def test_head_ends_with_a_slow_smooth_sweep(self):
        # BeG0nE's jitter checker needs a slow, smooth head turn; nobody should have to make it by hand. Head
        # commands 20 times a second read as "stepped" (Hard Reset 2026-10-17), so the simulator sweeps by itself.
        tools = FakeTools()
        learn(tools, stages=["vr_head"])
        self.assertEqual([on for _, on, _, _ in tools.sweeps], [True, False])
        (t_on, _, amp, hz), (t_off, _, _, _) = tools.sweeps
        self.assertGreaterEqual(t_off - t_on, 8.0)
        self.assertGreaterEqual(amp, 20)
        self.assertLessEqual(2 * math.pi * hz * amp, 30)   # peak speed in degrees a second: slow

    def test_sim_sweep_uses_the_simulator_folder_by_default(self):
        d, old = tempfile.mkdtemp(), vb_sim.S.SIM_DATA_DIR
        vb_sim.S.SIM_DATA_DIR = d
        try:
            vb_sim.sweep(False)
        finally:
            vb_sim.S.SIM_DATA_DIR = old
        self.assertTrue(os.path.isfile(os.path.join(d, "pose_sweep_command.json")))

    def test_sim_sweep_writes_the_command(self):
        d = tempfile.mkdtemp()
        vb_sim.sweep(True, 30, 0.1, data_dir=d)
        with open(os.path.join(d, "pose_sweep_command.json"), encoding="utf-8") as f:
            cmd = json.load(f)
        self.assertEqual(cmd, {"enabled": True, "yaw_amp_deg": 30.0, "pitch_amp_deg": 0.0, "roll_amp_deg": 0.0,
                               "freq_hz": 0.1})

    def test_menu_pressed_last_and_again_to_close(self):
        # the menu button opened the game's pause menu and spoiled the stick tests after it
        tools = FakeTools(pictures_change=False)
        learn(tools, stages=["vr_buttons"])
        held = [d for d in tools.sent if any(v for h in d.values() for k, v in h.items() if not k.endswith("_pose"))]
        self.assertTrue(held[-1].get("left", {}).get("menu"), held[-1])
        self.assertTrue(held[-2].get("left", {}).get("menu"), held[-2])
        self.assertEqual(sum(1 for d in held if d.get("left", {}).get("menu")), 2)

    # ---- Task 5: the PC profile ----
    DEV_GPUS = ["NVIDIA GeForce GTX 1660 SUPER", "Intel(R) HD Graphics 4000"]

    def test_tier_dev_pc_is_light(self):
        self.assertEqual(vb_profile.tier(self.DEV_GPUS, 16), "light")

    def test_tier_fast_card_32gb_is_full(self):
        self.assertEqual(vb_profile.tier(["AMD Radeon RX 7900 XTX"], 32), "full")

    def test_tier_conf_override(self):
        prof = vb_profile.collect({"bench_tier": "full"}, FakeProbes(self.DEV_GPUS, 16))
        self.assertEqual(prof["tier"], "full")

    def test_profile_written_and_read(self):
        vb_profile.write(vb_profile.collect({}, FakeProbes(self.DEV_GPUS, 16)))
        prof = vb_profile.read()
        self.assertEqual(prof["headset"], "none")
        self.assertEqual(prof["tier"], "light")
        self.assertEqual(prof["games"], ["Hard Reset Redux"])

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
