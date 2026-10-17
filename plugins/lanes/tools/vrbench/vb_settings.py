"""vb_settings - every folder, file name and number VR Bench uses, in one place (the code-shape rule: numbers get names).

Folders follow the environment so tests never touch the real ones:
  LANES_VRBENCH_DIR        VR Bench's own state (default %LOCALAPPDATA%\\VRBench): the input file the layer reads,
                           the switch, the PC profile, the run folders, the layer's log
  LANES_OPENXRSIM_DATA     the OpenXR Simulator's command folder (default %LOCALAPPDATA%\\OpenXR-Simulator)
  LANES_VRBENCH_LAYER_DIR  where install.ps1 put the layer (default %LOCALAPPDATA%\\Programs\\VRBench)
"""
import os

_LOCAL = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))

STATE_DIR = os.environ.get("LANES_VRBENCH_DIR") or os.path.join(_LOCAL, "VRBench")
INPUT_FILE = os.path.join(STATE_DIR, "input.json")        # read by the layer at every xrSyncActions
ENABLED_FILE = os.path.join(STATE_DIR, "enabled")         # exists = the layer acts; written by start, removed by stop
PROFILE_FILE = os.path.join(STATE_DIR, "profile.json")
RUNS_DIR = os.path.join(STATE_DIR, "runs")
LAYER_LOG = os.path.join(STATE_DIR, "layer.log")

LAYER_DIR = os.environ.get("LANES_VRBENCH_LAYER_DIR") or os.path.join(_LOCAL, "Programs", "VRBench")
LAYER_DLL64 = "vrbench_layer.dll"
LAYER_DLL32 = "vrbench_layer32.dll"
LAYER_JSON64 = "vrbench_layer.json"
LAYER_JSON32 = "vrbench_layer32.json"

SIM_DATA_DIR = os.environ.get("LANES_OPENXRSIM_DATA") or os.path.join(_LOCAL, "OpenXR-Simulator")
HEAD_CMD = "head_pose_command.json"           # x, y, z in metres; yaw, pitch, roll in radians [measured 2026-10-16]
SHOT_REQ = "screenshot_request.json"
SHOT_FILES = ("screenshot.png", "screenshot.bmp", "screenshot.jpg", "screenshot.jpeg")   # the simulator writes one
SHOT_SETTLE_S = 0.3                           # the picture file is still being written for a moment after it appears
SHOT_POLL_S = 0.1
SHOT_FRESH_SLACK_S = 0.5                      # a picture this much older than the request still counts (clock grain)

INPUT_VERSION = 1
REPLACE_RETRIES = 50                          # the reader may hold the file open at the instant of the swap
REPLACE_WAIT_S = 0.005
HAND_LEFT, HAND_RIGHT = 0, 1
HAND_NAMES = ("left", "right")

DEFAULT_HEAD = dict(x=0.0, y=1.7, z=0.0)      # the simulator's own standing height
HANDS_FULL = 9                                # hand positions tried per hand by the learn stages
HANDS_LIGHT = 5
STAGE_TIMEOUT_S = 600
LEARN_MINUTES_DEFAULT = 60
FOOTAGE_WARN_GB_DEFAULT = 20
