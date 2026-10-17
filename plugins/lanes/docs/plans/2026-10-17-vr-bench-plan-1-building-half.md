# VR Bench, plan 1 of 3: the BUILDING half — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task
> (this estate runs work inline, no subagents). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a game on the OpenXR Simulator can be driven in VR by VR Bench — pretend hands, buttons and sticks through
our own OpenXR layer, the head through the simulator — from one tool that is installed by the plugin's setup, and
the first `learn` run on Hard Reset reproduces the 2026-10-16 hands-and-controls run without the simulator's own
command files.

**Architecture:** a C++ OpenXR API layer (`vr-bench` repo, grown from the Hand Freeze layer) answers the game's
action-state and pose questions from `%LOCALAPPDATA%\VRBench\input.json`; a Python driver in the plugin
(`tools/vrbench/`) writes that file, moves the simulator's head, takes its screenshots, runs the learn stages and
writes what it learns to the game's `KNOWN.md`. The layer is registered only while a run is on, and only for the
bitness of the game being run, which is also the fix for the Hand Freeze 32-bit failure of 2026-10-16.

**Tech Stack:** C++17 (MSVC Build Tools, `cl`, 32 + 64), OpenXR headers (Khronos, already vendored in
hand-freeze-vr/third_party), Python 3.12 (stdlib + Pillow), bash test fixtures as in `tools/tests/`, GitHub
releases via `gh`.

**Spec:** `plugins/lanes/docs/specs/2026-10-17-vr-bench-design.md` (§5.1 layer, §5.3 driver, §5.5 setup,
§6.1 learn, §6.4 tiers, §7 where things live). Plans 2 and 3 (background keyboard/mouse; the WEARING half) are
scoped at the end of this file and written after this plan is proven live.

## Global Constraints

- Nobody's name is written down but the chosen one: no paths, machine names or people in anything the layer logs,
  the driver prints, or the `vr-bench` repo ships (PROTOCOL §12; `scrub-scan.py` before any push).
- Code shape: hand-written files 800 lines soft / 1,500 hard; numbers get names in one settings table per tool
  (PROTOCOL §6; `code-shape-scan.py`).
- The layer changes nothing unless `%LOCALAPPDATA%\VRBench\enabled` exists; with it gone, every hook passes through.
- Only `/lm`, `/lanes:bench` or the person's say-so may launch a game; `learn` takes the LIVE claim
  (`lane-claim.sh take bench <game>`) and releases it at the end.
- The simulator fork is not ours: nothing here edits it; its command files (`head_pose_command.json`,
  `screenshot_request.json`) are used as they are, in its data folder `%LOCALAPPDATA%\OpenXR-Simulator`.
- Plugin version for this plan: **0.74.0**, one CHANGELOG line in plain words, released only through `release.sh`.
- The input file is **version 1**: `{"v": 1, ...}`; a file with another `v` is ignored with one log line.
- Numpad keys, never F-keys, for anything a person presses.

## Review Focus

1. The game asks for an action the file does not name (a game-specific "crouch" bound to a path we never list):
   the layer must pass the runtime's answer through unchanged. Test in Task 1 (`unknown_path_is_none`), used by Task 2.
2. `input.json` half-written while the layer reads it (the driver is mid-write): the layer must keep the last good
   state, not zero everything. Test in Task 1 (`bad_json_keeps_previous`), and Task 3 writes atomically (`.tmp` +
   replace).
3. A 32-bit game started while the 64-bit manifest is registered: `xrCreateInstance` fails in that game (seen
   2026-10-16 with Hand Freeze). Task 4 registers by the exe's bitness and Task 4's test proves the other manifest is
   absent while a run is on.
4. The simulator not installed, or the game not at gameplay, when `learn` starts: it must stop with one plain line,
   not drive blind. Task 6 (`pre-flight refuses`).
5. A learn run that ends early (crash, time limit): the claim must be released and the layer unregistered anyway.
   Task 6 (`finally: release`) with a test that kills the stage loop.

---

## File structure

**New repo `TefMeister/vr-bench` (public; Tefa 2026-10-17):**
- `layer/vrbench_layer.cpp` — the hooks and the OpenXR chaining (from Hand Freeze's shape, under 800 lines).
- `layer/vb_input.h` — pure: parse `input.json` v1 into `VbInput`; look a binding path up to a value. No Windows,
  no OpenXR types beyond plain floats, so a host test can run it.
- `layer/vb_log.h` — one log file per run, state changes only.
- `layer/vrbench_layer.json`, `layer/vrbench_layer32.json` — manifests (written at install with the real path).
- `test/vb_input_test.cpp` — host test for `vb_input.h`.
- `build.bat` (32 + 64, from Hand Freeze's), `install.ps1` (copies to `%LOCALAPPDATA%\Programs\VRBench`, writes
  the two manifests with the real `library_path`, registers nothing), `README.md`, `CREDITS.md`, `LICENSE` (MIT).

**Plugin `plugins/lanes/`:**
- `tools/vrbench/vrbench.py` — the CLI: `status`, `profile`, `install`, `uninstall`, `start`, `stop`, `learn`.
- `tools/vrbench/vb_settings.py` — every named number and path in one place.
- `tools/vrbench/vb_profile.py` — specs, runtime, tier, headset, games → `profile.json`.
- `tools/vrbench/vb_layer.py` — enabled file; register/unregister the manifest for a given exe's bitness.
- `tools/vrbench/vb_input.py` — build and write `input.json` (hands, buttons, sticks).
- `tools/vrbench/vb_sim.py` — the simulator's head and screenshot command files; is the simulator loaded in a game.
- `tools/vrbench/vb_run.py` — the run folder: `run.json`, `screens/`, `input.jsonl`, `game-log/`.
- `tools/vrbench/vb_learn.py` — the stage machine and the stages (0 pre-flight … 5 report).
- `tools/vrbench/vb_install.py` — download the `vr-bench` release like `hand-freeze.py`; `installed.py record`.
- `tools/tests/vrbench-fixture.sh`, `tools/tests/vrbench_test.py` — the driver's tests, no game, no headset.
- `tools/openxr-sim.py` — `--bench` on `install`.
- `tools/setup-scan.py` — catalog row `("vr", "vrbench", ...)`.
- `tools/installed.py` — `APPS["VR Bench"]`.
- `commands/bench.md` — `/lanes:bench` (short `/vb`); `commands/setup.md` §3.6; `commands/update.md` step 7 and new 8.
- `docs/PROTOCOL.md` §24; `docs/TOOLS.md` row; `lanes.conf.example` keys; `CHANGELOG.md`; root `README.md` row;
  `CREDITS.md`.

---

### Task 1: the `vr-bench` repo and the pure input parser

**Files:**
- Create: `vr-bench/layer/vb_input.h`, `vr-bench/test/vb_input_test.cpp`, `vr-bench/build.bat`, `vr-bench/README.md`,
  `vr-bench/CREDITS.md`, `vr-bench/LICENSE`, `vr-bench/.gitignore`
- Copy: `hand-freeze-vr/third_party/openxr/` → `vr-bench/third_party/openxr/`

**Interfaces:**
- Produces (`vb_input.h`, namespace `vb`):
  - `struct Pose { float px, py, pz, qx, qy, qz, qw; bool set; };`
  - `struct Hand { Pose grip, aim; float trigger, squeeze; float stick_x, stick_y; bool a, b, x, y, menu, stick_click;
     bool trigger_set, squeeze_set, stick_set, a_set, b_set, x_set, y_set, menu_set, stick_click_set; };`
  - `struct Input { int version; bool valid; Hand hand[2]; enum Mode { PASS, SET, ADD } poses, buttons; };`
  - `bool parse(const char* json, size_t n, Input& out);` — false (and `out` untouched) on bad JSON or `v != 1`.
  - `enum Kind { NONE, BOOL, FLOAT, VEC2, POSE_GRIP, POSE_AIM };`
  - `Kind lookup(const Input& in, const char* binding_path, int& hand, float& f, bool& b, float& vx, float& vy);`
    — maps `/user/hand/{left|right}/input/{trigger/value, trigger/click, squeeze/value, squeeze/click, thumbstick,
    thumbstick/x, thumbstick/y, thumbstick/click, trackpad, trackpad/click, a/click, b/click, x/click, y/click,
    menu/click, grip/pose, aim/pose}`; `trigger/click` is `trigger >= 0.75`; `thumbstick/x` returns `stick_x` as
    FLOAT; an unknown path or a hand whose value is not `_set` returns NONE.
  - A hand-rolled JSON reader is fine (flat objects, numbers, bools, strings); no library.

- [ ] **Step 1: create the repo, public (Tefa said so, 2026-10-17)**

Run: `gh repo create TefMeister/vr-bench --public --description "VR Bench: the OpenXR layer that plays a VR game for you - pretend hands, buttons and sticks from a file, and the look-at-this mark when you wear the headset" --clone` inside `github-backups/`
Expected: an empty clone at `github-backups/vr-bench`.

- [ ] **Step 2: write the failing host test**

```cpp
// test/vb_input_test.cpp — builds with: cl /EHsc /std:c++17 /I..\layer vb_input_test.cpp
static const char* kFile = R"({"v":1,"mode":{"poses":"set","buttons":"set"},
 "vr":{"left":{"trigger":0.8,"stick":[0.5,-0.25],"a":true,"grip_pose":{"p":[-0.2,-0.3,-0.4],"q":[0,0,0,1]}},
       "right":{"squeeze":1.0}}})";
TEST(parses_v1)            { vb::Input in{}; CHECK(vb::parse(kFile, strlen(kFile), in)); CHECK(in.valid); CHECK(in.poses == vb::Input::SET); }
TEST(left_trigger_value)   { ...; CHECK(vb::lookup(in, "/user/hand/left/input/trigger/value", h, f, b, vx, vy) == vb::FLOAT); CHECK(h == 0); CHECK(f == 0.8f); }
TEST(trigger_click_from_value) { ... "/user/hand/left/input/trigger/click" ... == vb::BOOL && b == true }
TEST(stick_vec2_and_x)     { ... "/user/hand/left/input/thumbstick" == VEC2 && vx == 0.5f && vy == -0.25f; "/thumbstick/x" == FLOAT && f == 0.5f }
TEST(grip_pose)            { ... "/user/hand/left/input/grip/pose" == POSE_GRIP; in.hand[0].grip.set; px == -0.2f }
TEST(unknown_path_is_none) { ... "/user/hand/left/input/crouch/click" == NONE }
TEST(unset_hand_value_is_none) { ... "/user/hand/right/input/trigger/value" == NONE }   // right has only squeeze
TEST(bad_json_keeps_previous)  { vb::Input in{}; parse(kFile,...); CHECK(!vb::parse("{\"v\":1,", 7, in)); CHECK(in.hand[0].trigger == 0.8f); }
TEST(wrong_version_rejected)   { CHECK(!vb::parse("{\"v\":2}", 7, in)); }
```

(`TEST`/`CHECK` are ten lines of macros at the top of the file; the program prints `N passed, M failed` and exits 1 on
any failure.)

- [ ] **Step 3: run it to make sure it fails**

Run (in a VS 2022 x64 developer shell, `vr-bench/test/`): `cl /nologo /EHsc /std:c++17 /I..\layer vb_input_test.cpp && vb_input_test.exe`
Expected: compile error, `vb_input.h` not found.

- [ ] **Step 4: implement `layer/vb_input.h`** with the interfaces above; header-only, `inline` functions, no `<windows.h>`.

- [ ] **Step 5: run the test to make sure it passes**

Run: same as step 3. Expected: `9 passed, 0 failed`.

- [ ] **Step 6: `build.bat`, `README.md`, `CREDITS.md`, `LICENSE`, `.gitignore`**

`build.bat`: Hand Freeze's, with `vrbench_layer.cpp` → `dist\vrbench_layer.dll` and `dist\vrbench_layer32.dll`, then
builds and runs `test\vb_input_test.cpp` and stops on a failure (the layer source lands in Task 2; until then
`build.bat` builds the test only, guarded by `if exist layer\vrbench_layer.cpp`). `README.md`: what it is in Tefa's
layout, the three setup choices, what it never does (no names, nothing switched on by installing). `CREDITS.md`:
spec §8, including the placeholder line for the Discord author. `.gitignore`: `build/`, `dist/`, `*.exe`, `*.obj`.

- [ ] **Step 7: scrub and commit**

Run: `python <plugin>/tools/scrub-scan.py vr-bench` → expected `nothing found`.
```bash
git add -A && git commit -m "vb_input.h: the input file parser and binding lookup, with its host test" && git push
```

---

### Task 2: the layer — pretend hands, buttons and sticks

**Files:**
- Create: `vr-bench/layer/vrbench_layer.cpp`, `vr-bench/layer/vb_log.h`, `vr-bench/layer/vrbench_layer.json`,
  `vr-bench/layer/vrbench_layer32.json`, `vr-bench/install.ps1`
- Test: `vr-bench/test/vb_input_test.cpp` (grows), live check in Task 7

**Interfaces:**
- Consumes: `vb::parse`, `vb::lookup` (Task 1); Hand Freeze's chaining shape (`xrNegotiateLoaderApiLayerInterface`,
  `hf_xrGetInstanceProcAddr`, `hf_xrCreateApiLayerInstance`, `fetch_next`, the per-session LOCAL `g_room`).
- Produces: layer name `XR_APILAYER_LANES_vr_bench`; reads `%LOCALAPPDATA%\VRBench\enabled` (exists = on) and
  `%LOCALAPPDATA%\VRBench\input.json` at every `xrSyncActions` (re-read only when the file's write time changed);
  writes `%LOCALAPPDATA%\VRBench\layer.log`.

- [ ] **Step 1: write the hooks (no test can run them without a runtime; the live check is Task 7)**

In `vrbench_layer.cpp`, hooks and what each does when enabled (every hook calls the runtime first, then edits):
- `xrSuggestInteractionProfileBindings`: remember `action → binding path string` per profile (`xrPathToString`),
  so each action's meaning is known. Store `std::map<XrAction, std::string>` keyed by the LAST suggested profile
  per action; also hook `xrGetCurrentInteractionProfile` to prefer bindings of the profile in use.
- `xrCreateActionSpace` / `xrDestroySpace` / `xrDestroySession`: as Hand Freeze (controller spaces, `g_room`).
- `xrSyncActions`: re-read the file if changed; `vb::parse`; on failure keep the previous `Input` and log once per
  change of file time. Also the first sync writes `layer.log: on, game <exe name>, file v1`.
- `xrGetActionStateBoolean/Float/Vector2f`: `lookup(binding path of info->action, hand from subaction or binding)`;
  with `buttons == SET` and a value: `isActive = XR_TRUE`, `currentState = value`, `changedSinceLastSync` = value
  differs from the last answer given, `lastChangeTime = now`. `ADD`: boolean OR, float max, vec2 sum clamped to
  ±1. `PASS` or NONE: untouched.
- `xrGetActionStatePose`: for actions whose binding is `grip/pose` or `aim/pose` with a `set` pose: `isActive = XR_TRUE`.
- `xrLocateSpace` / `xrLocateSpaces`: for a controller space whose action is a `grip/pose` or `aim/pose` with
  `poses == SET` and the pose `set`: answer `relative(base in room, file pose)` with flags valid + tracked, velocity
  zero (Hand Freeze's `held_pose` with the kept pose replaced by the file pose).
- `xrApplyHapticFeedback`: log `haptic <hand> <ms>`; call through.

- [ ] **Step 2: `vb_log.h`**: `inline void vb_log(const char* fmt, ...)` → one timestamped line appended to
  `%LOCALAPPDATA%\VRBench\layer.log`; opened and closed per line so a crash loses nothing.

- [ ] **Step 3: manifests and `install.ps1`**

Manifests as Hand Freeze writes them (`file_format_version 1.0.0`, `api_layer` with `name`
`XR_APILAYER_LANES_vr_bench`, `library_path`, `api_version 1.0`, `implementation_version 1`,
`description "VR Bench: pretend hands and buttons for a VR game, and the look-at-this mark"`); `install.ps1` copies
`dist\*.dll` to `%LOCALAPPDATA%\Programs\VRBench`, writes both manifests there with the real path, and **registers
nothing** (the driver does, per run, per bitness: Task 4). Prints `Installed to ...; the plugin switches it on per run.`

- [ ] **Step 4: build both bitnesses**

Run: `build.bat` → Expected: `dist\vrbench_layer.dll`, `dist\vrbench_layer32.dll`, test `9 passed`, `BUILD OK`.
Check the 32-bit export: `dumpbin /exports dist\vrbench_layer32.dll | findstr xrNegotiate` shows the plain name.

- [ ] **Step 5: scrub, commit, first release**

```bash
python <plugin>/tools/scrub-scan.py vr-bench   # nothing found
git add -A && git commit -m "the layer: hands, buttons and sticks answered from input.json; manifests; install.ps1"
git push
cd dist && zip -r ../vr-bench-v0.1.0.zip vrbench_layer.dll vrbench_layer32.dll vrbench_layer.json vrbench_layer32.json ../install.ps1
gh release create v0.1.0 ../vr-bench-v0.1.0.zip --title "VR Bench layer 0.1.0" --notes "First build: pretend hands, buttons and sticks from input.json. Nothing switched on by installing."
```
(The manifests in the zip carry a placeholder path; `install.ps1` rewrites them.)

---

### Task 3: the driver's foundations — settings, input writer, simulator, run folder

**Files:**
- Create: `plugins/lanes/tools/vrbench/vb_settings.py`, `vb_input.py`, `vb_sim.py`, `vb_run.py`, `vrbench.py`
  (CLI skeleton: `status` only for now)
- Test: `plugins/lanes/tools/tests/vrbench_test.py`

**Interfaces:**
- `vb_settings.py`: `STATE_DIR = env LANES_VRBENCH_DIR or %LOCALAPPDATA%\VRBench`; `INPUT_FILE`, `ENABLED_FILE`,
  `PROFILE_FILE`, `RUNS_DIR`, `LAYER_LOG`; `SIM_DATA_DIR = env LANES_OPENXRSIM_DATA or %LOCALAPPDATA%\OpenXR-Simulator`;
  `HEAD_CMD = "head_pose_command.json"`, `SHOT_REQ = "screenshot_request.json"`, `SHOT_FILE = "screenshot.bmp"`;
  `INPUT_VERSION = 1`; `REPLACE_RETRIES = 50`, `REPLACE_WAIT_S = 0.005`; `HAND_LEFT, HAND_RIGHT = 0, 1`;
  `DEFAULT_HEAD = dict(x=0.0, y=1.7, z=0.0)`; `HANDS_FULL = 9`, `HANDS_LIGHT = 5` (positions per hand);
  `STAGE_TIMEOUT_S = 600`; `LEARN_MINUTES_DEFAULT = 60`; `FOOTAGE_WARN_GB_DEFAULT = 20`.
- `vb_input.py`:
  - `class Input` with `hand(h: int, grip=None, aim=None, trigger=None, squeeze=None, stick=None, a=None, b=None,
    x=None, y=None, menu=None, stick_click=None) -> Input` (None = leave unset), `mode(poses="set", buttons="set")`,
    `to_json() -> str` (shape of Task 1's `kFile`; poses as `{"p":[x,y,z],"q":[x,y,z,w]}`; `yaw_deg`/`pitch_deg`
    helper `pose_from_ypr(p, yaw_deg, pitch_deg, roll_deg=0.0)`), `clear() -> Input`.
  - `write(inp: Input, path=INPUT_FILE) -> None` — `.tmp` then `os.replace` with the retries.
- `vb_sim.py`: `head(x, y, z, yaw_deg, pitch_deg, roll_deg=0.0, data_dir=SIM_DATA_DIR)`, `screenshot(out_png,
  timeout_s=5.0, data_dir=SIM_DATA_DIR) -> bool` (writes the request, waits for `screenshot.bmp` to change, converts
  with Pillow), `loaded_in(pid) -> bool` (is `openxr_simulator*.dll` in that process's module list: `psutil` if
  present, else `tasklist /m`).
- `vb_run.py`: `class Run` — `Run.new(game) -> Run` (folder `RUNS_DIR/<game>/<YYYY-MM-DD>_<HH-MM-SS>`), `shot(name) ->
  path` (via `vb_sim.screenshot`, into `screens/`), `input_sent(inp: Input)` (one JSON line into `input.jsonl`),
  `stage(name, verdict, how, picture=None)` (append to `run.json["stages"]`), `copy_log(path)` (into `game-log/`),
  `finish(reason)`; `run.json` keys `game, started, finished, reason, tier, stages[]`.

- [ ] **Step 1: write the failing tests**

```python
# tools/tests/vrbench_test.py (unittest; LANES_VRBENCH_DIR and LANES_OPENXRSIM_DATA point at a temp folder)
def test_input_json_shape(self):           # left trigger 0.8 + stick, right squeeze -> exactly Task 1's kFile keys, v == 1
def test_pose_from_ypr_identity(self):     # yaw 0 pitch 0 -> q == [0,0,0,1]; yaw 90 -> q.y == sin(45deg) within 1e-6
def test_write_is_atomic(self):            # after write(), no .tmp remains and json.load(INPUT_FILE)["v"] == 1
def test_head_command_file(self):          # vb_sim.head(0,1.7,0,30,0) writes head_pose_command.json with yaw == radians(30)
def test_screenshot_times_out_cleanly(self):   # no simulator: screenshot(...) returns False within timeout_s + 0.5
def test_run_folder_and_stage_record(self):    # Run.new("x"): folder exists; stage("head","PASS","picture followed") -> run.json has it
def test_run_input_log(self):              # input_sent twice -> input.jsonl has two lines, each parses
```

- [ ] **Step 2: run them to make sure they fail**

Run: `python -m unittest tools/tests/vrbench_test.py -v` → Expected: `ModuleNotFoundError: vb_settings`.

- [ ] **Step 3: implement the four modules and `vrbench.py status`** (`status` prints: layer installed? enabled?,
  simulator found (`openxr-sim.py status --json`), profile present?, runs on disk).

- [ ] **Step 4: run the tests to make sure they pass**

Run: same. Expected: `OK` (7 tests).

- [ ] **Step 5: commit**

```bash
git add plugins/lanes/tools/vrbench plugins/lanes/tools/tests/vrbench_test.py
git commit -m "vrbench: settings, input writer, simulator head and screenshots, run folder"
```

---

### Task 4: the layer switch — enabled file and per-bitness registration

**Files:**
- Create: `plugins/lanes/tools/vrbench/vb_layer.py`
- Modify: `plugins/lanes/tools/vrbench/vrbench.py` (`start <exe-or-game>`, `stop`)
- Test: `plugins/lanes/tools/tests/vrbench_test.py` (grows)

**Interfaces:**
- `vb_layer.py`: `exe_bits(path) -> 32 | 64` (PE header: `0x14c` → 32, `0x8664` → 64); `manifest_for(bits) -> path`
  (`%LOCALAPPDATA%\Programs\VRBench\vrbench_layer{32}.json`, `LANES_VRBENCH_APP` overrides the folder);
  `register(bits)` / `unregister_all()` — HKCU `Software\Khronos\OpenXR\1\ApiLayers\Implicit`, value = manifest
  path, DWORD 0; `unregister_all` removes both of ours and never anyone else's; `enable()` / `disable()` write and
  remove `ENABLED_FILE`; `registered() -> list[str]`. Registry calls go through one small `_reg` shim so the test
  can stub it (`LANES_VRBENCH_FAKEREG=<json file>`).
- `vrbench.py start <exe path | game name>`: resolves a game name through `builds_app.<game>` in lanes.conf, else
  takes a path; `exe_bits`; `unregister_all(); register(bits); enable()`; prints one line. `stop`: `disable();
  unregister_all()`.

- [ ] **Step 1: failing tests**

```python
def test_exe_bits_reads_pe_header(self):      # a 64-byte fake PE with 0x14c -> 32, 0x8664 -> 64
def test_start_registers_only_that_bitness(self):   # fake reg: start(32-bit exe) -> registered() == [manifest32]
def test_start_replaces_other_bitness(self):  # register(64) then start(32-bit) -> only manifest32 remains
def test_stop_unregisters_and_disables(self): # after stop: registered() == [] and not ENABLED_FILE.exists()
def test_unregister_leaves_others_alone(self): # fake reg holding a HandFreeze manifest keeps it
```

- [ ] **Step 2: run to fail** — `AttributeError: module has no attribute exe_bits`.
- [ ] **Step 3: implement `vb_layer.py` and the two commands.**
- [ ] **Step 4: run to pass** — `OK` (12 tests).
- [ ] **Step 5: commit** — `git commit -m "vrbench start/stop: the layer on for one run, registered for the game's bitness only"`

---

### Task 5: the PC profile

**Files:**
- Create: `plugins/lanes/tools/vrbench/vb_profile.py`
- Modify: `vrbench.py` (`profile`, and `status` prints the tier), `lanes.conf.example`
- Test: `vrbench_test.py` (grows)

**Interfaces:**
- `vb_profile.py`: `collect(conf: dict, probes: Probes) -> dict` where `Probes` is a small class with `cpu()`,
  `gpus()`, `ram_gb()`, `windows()`, `runtime(bits)` (registry `ActiveRuntime`, 64 and WOW6432Node), `games()`
  (`installed-games.py --record` output if the board has it, else `[]`) — the real one shells out, the test passes
  a fake. Result keys: `cpu, gpus, ram_gb, windows, runtime64, runtime32, headset` (`conf["bench_headset"]` or
  `"none"`), `tier`, `games`, `written`.
- `tier(gpus: list[str], ram_gb: int) -> "light" | "full"`: light when `ram_gb < 24` or no GPU name matches
  `GPU_FULL_RE = r"RTX|GTX 16[7-9]0|GTX 2|RX 6|RX 7|Arc"` **and** `GTX 1660` counts light (Tefa's dev PC);
  `conf["bench_tier"]` overrides.
- `write(profile) -> PROFILE_FILE`; `read() -> dict | None`.

- [ ] **Step 1: failing tests**
```python
def test_tier_dev_pc_is_light(self):     # ["NVIDIA GeForce GTX 1660 SUPER", "Intel(R) HD Graphics 4000"], 16 -> "light"
def test_tier_rtx_32gb_is_full(self):    # ["NVIDIA GeForce RTX 4080"], 32 -> "full"
def test_tier_conf_override(self):       # conf bench_tier=full with the light PC -> "full"
def test_profile_written_and_read(self): # collect(fake) -> write -> read()["headset"] == "none"
```
- [ ] **Step 2: run to fail.** - [ ] **Step 3: implement.** - [ ] **Step 4: run to pass** (`OK`, 16 tests).
- [ ] **Step 5: `lanes.conf.example`**: add, under the simulator block:
  `# bench_headset = real | none   (can a real VR headset be worn on this PC? set by /lanes:setup)`,
  `# bench_tier = light | full     (VR Bench's strength; chosen from the PC's specs when unset)`,
  `# bench_footage_warn_gb = 20`.
- [ ] **Step 6: commit** — `"vrbench profile: this PC's specs, runtime, headset and tier"`.

---

### Task 6: `learn` — the stage machine and the stages

**Files:**
- Create: `plugins/lanes/tools/vrbench/vb_learn.py`, `plugins/lanes/tools/vrbench/vb_stages_flat.py`,
  `plugins/lanes/tools/vrbench/vb_stages_vr.py`
- Modify: `vrbench.py` (`learn <game> [--minutes N] [--stage name[,name]] [--tier light|full]`)
- Test: `vrbench_test.py` (grows)

**Interfaces:**
- `vb_learn.py`:
  - `STAGES = ["preflight", "launch", "menus", "flat", "vr_head", "vr_hands", "vr_buttons", "report"]`.
  - `class Learn(game, minutes, stages, tier, run: Run, tools: Tools)` where `Tools` bundles callables the test can
    fake: `mom(args) -> dict` (Menu-o-matiC JSON output), `sim_loaded() -> bool`, `game_log_tail(n) -> list[str]`,
    `now() -> float`, `claim(take: bool)`, `layer_start(exe)`, `layer_stop()`, `known_add(section, text)`.
  - `run_all() -> dict` — runs each stage in order inside `try/finally` so `claim(False)` and `layer_stop()` always
    run; stops at the time limit (`now() - started > minutes*60`) or `STAGE_TIMEOUT_S` per stage; every stage returns
    `Verdict(name, result in {"PASS","CHECK","UNKNOWN"}, how: str, picture: str|None)` and `run.stage(...)` records it.
  - `preflight()` refuses (raises `Refused(reason)`) when: the simulator is not installed, the game exe is not found,
    `bench_headset == none` and no simulator runtime is set for this game, or KNOWN.md cannot be read/created. On
    success: reads KNOWN.md (`mom known <folder>`), writes `profile`, mutes nothing itself but records whether the
    game's music setting is known (KNOWN.md "Controls" has a `music` line) — else `CHECK` with "music switch not
    known yet" (the standing rule is kept by the session, not the robot).
- `vb_stages_flat.py` (this plan: through Menu-o-matiC as it is, which brings the game to the front; the honest line
  `"this game needs the screen for the flat stages until plan 2"` goes into `run.json` and the report):
  - `launch(L)`: `mom run <route launch→gameplay>` when the route exists → PASS/CHECK from its result; else UNKNOWN
    "no launch route yet: record one with the person, or run the learn-by-looking loop (plan 2)".
  - `menus(L)`: `mom known` lists the three goals; each present route replayed once; verdict per goal.
  - `flat(L)`: still camera first: `mom turn` 25° × 4 with a screenshot after each (`run.shot`), compared with the
    no-input picture (`mom probe` difference) → PASS when 3 of 4 changed; then each key in KNOWN.md Controls held
    1.5 s with `mom probe --region`.
- `vb_stages_vr.py`:
  - `vr_head(L)`: `vb_sim.head` yaw 0, +30, −30, pitch +20, roll 10, lean x +0.3: screenshot per pose; PASS when each
    picture differs from the previous by more than `STILL_DIFFERENCE` (Menu-o-matiC's) and the game log (if our
    mod logs `headset pose`) shows the yaw within 2°.
  - `vr_hands(L)`: positions from `HANDS_FULL`/`HANDS_LIGHT` (the 2026-10-16 list: 9 points incl. nearer, farther,
    yaw 90, pitch −60), written with `vb_input` as grip + aim poses, `poses=set`; PASS when the screenshot's hand
    centroid moves the way the position moved (left/right/up/down sign test, as `sim_hands_drive.centroids`);
    UNKNOWN with "no hands drawn in this game" when no coloured centroid is found in any picture.
  - `vr_buttons(L)`: right trigger, left trigger, A, B, X, Y, menu, left stick forward 1 s, right stick right 1 s,
    each held through `vb_input` for 0.4 s; PASS when the game log gained a line within 1 s (our mods log key presses)
    or the picture changed; otherwise CHECK "no visible effect" with the picture.
  - `report(L)`: writes `debrief.md` (plan 3 makes it richer): one row per stage, the KNOWN.md lines added, and the
    "needs the screen" line; copies the game log; `run.finish("done")`.
- Every PASS/CHECK with a learned fact calls `known_add` (e.g. `Controls`, `"VR: right trigger fires (seen 2026-10-17, simulator)"`).

- [ ] **Step 1: failing tests (fake `Tools`, no game)**
```python
def test_preflight_refuses_without_simulator(self):   # sim installed False -> Refused, run.json reason starts "simulator"
def test_stages_run_in_order_and_record(self):        # all fakes PASS -> run.json stages == STAGES, each "PASS"
def test_time_limit_stops_early(self):                # now() jumps 61 min after "menus" -> last stage "menus", reason "time"
def test_claim_and_layer_released_on_crash(self):     # fake flat() raises -> claim(False) and layer_stop() were called, reason "error: ..."
def test_only_requested_stages(self):                 # stages ["vr_head"] -> preflight, vr_head, report only
def test_hands_unknown_without_centroid(self):        # fake screenshots with no colour -> vr_hands UNKNOWN "no hands drawn"
def test_buttons_pass_on_log_line(self):              # fake game_log_tail grows after trigger -> PASS
```
- [ ] **Step 2: run to fail.** - [ ] **Step 3: implement the three modules and the `learn` command** (the real `Tools`
  shells out to `menu_o_matic.py`, `lane-claim.sh`, `vb_layer`, `mom_known`). - [ ] **Step 4: run to pass** (`OK`, 23).
- [ ] **Step 5: `code-shape-scan.py tools/vrbench`** → no file over 800 lines. **Commit** —
  `"vrbench learn: the stage machine, flat stages through Menu-o-matiC, VR stages through the layer and the simulator"`.

---

### Task 7: first live proof — Hard Reset on the dev PC

**Files:**
- Modify: `hard-reset-vr/modding-notes/2026-10-17-vr-bench-first-learn.md` (new note), `ai-game-control-profiles/routes/hard-reset-vr/KNOWN.md` (via the tool), the Hard Reset board row.
- No code changes expected; fixes found here go back into Tasks 2–6 with a test each.

- [ ] **Step 1: install the layer** — `python tools/vrbench/vrbench.py install` (Task 8 brings the downloader; for
  this step run `vr-bench/install.ps1` by hand) → `%LOCALAPPDATA%\Programs\VRBench` holds both DLLs and manifests.
- [ ] **Step 2: Hard Reset at gameplay** (the session launches it, `/lm` rules; `d3d9_openxr.txt`, `d3d9_head_track.txt`,
  `d3d9_hands.txt` on; `DISABLE_HAND_FREEZE_LAYER=1` no longer needed once Hand Freeze is unregistered for the run).
- [ ] **Step 3: run** — `python tools/vrbench/vrbench.py learn hard-reset-vr --stage vr_head,vr_hands,vr_buttons --tier light`
  Expected: `layer.log` says `on, game hardreset.exe, file v1`; the game's own log shows `controllers per s:` with
  both hands located while the simulator's command files are untouched; `vr_hands` PASS in ≥ 4 of 5 positions;
  `vr_buttons` PASS for right trigger (`fire` in the game log) and A (`jump`).
- [ ] **Step 4: write the note** (Tefa's layout: what was run, what each stage said, the pictures' names, what broke),
  the board row (`[FLAT]` → done line), and the KNOWN.md diff; commit each repo on its own lane paths; push.
- [ ] **Step 5: if anything failed**, fix it in the owning task with a new test, rebuild, rerun step 3, and only then
  move to Task 8.

---

### Task 8: install, status and the three choices in setup and update

**Files:**
- Create: `plugins/lanes/tools/vrbench/vb_install.py`
- Modify: `vrbench.py` (`install`, `uninstall`, `status --json`), `tools/openxr-sim.py` (`--bench`),
  `tools/setup-scan.py` (catalog row), `tools/installed.py` (`APPS`), `commands/setup.md` (§3.6, the headset
  question), `commands/update.md` (step 7 reworded, step 8 added)
- Test: `tools/tests/vrbench-fixture.sh`, `tools/tests/openxr-sim-fixture.sh` (grows)

**Interfaces:**
- `vb_install.py`: `REPO = "TefMeister/vr-bench"`; `status() -> dict(installed, release, latest_release, newer,
  error)` and `install() -> int` exactly as `hand-freeze.py` (download the latest release zip, unzip into a fresh
  temp folder, run its `install.ps1 -From <folder>`, write `lanes-release.txt`, then `installed.py record "VR Bench"
  <tag>`); refuses while a game has the layer loaded (`vb_layer.registered()` non-empty → "a run is on; stop it
  first"). Tests set `LANES_VRBENCH_APP` and `LANES_VRBENCH_RELEASE` (a JSON file standing in for GitHub).
- `openxr-sim.py install --fork --bench`: after the simulator, runs `vrbench.py install`; `status --json` gains
  `"bench": <vb_install.status()>`.
- `setup-scan.py`: `("vr", "vrbench", "VR Bench (plays a VR game for you on the simulator; marks the spot you point at in the headset)", vrbench_found, False, False)`.
- `installed.py`: `APPS["VR Bench"] = vrbench_found` (reads `lanes-release.txt` in the app folder).
- `commands/setup.md` §3.6 "The pretend headset and VR Bench (0.74.0, VR group)": the three choices worded as spec
  §5.5, item 1 marked recommended; then the one question *"Can a real VR headset be used on this PC?"* →
  `bench_headset = real | none` written to lanes.conf; then the OBS Mirror yes/no **deferred to plan 3** (say so in
  one line: "recording the headset's own view comes with the next version").
- `commands/update.md` step 7: the same three choices replace the two; step 8 "VR Bench, every run": `vrbench.py
  status --json` → `newer` true → ask "Update VR Bench" / "Not now"; `installed` false → say nothing.

- [ ] **Step 1: failing fixture** (`vrbench-fixture.sh`, shape of `openxr-sim-fixture.sh`: a scratch zip with the two
  DLLs, manifests and an `install.ps1` that copies them; a fake release JSON):
  - not installed → `status --json` has `"installed": false` and the fake tag;
  - `install` → the app folder holds `vrbench_layer32.dll` and `lanes-release.txt` with the tag, and the board's
    `installed/<PC>.json` names `VR Bench`;
  - `install` while `LANES_VRBENCH_FAKEREG` lists our manifest → refused, nothing replaced;
  - `openxr-sim.py install --fork --bench` (with both fakes) → both `lanes-release.txt` files exist.
- [ ] **Step 2: run to fail** — `bash tools/tests/vrbench-fixture.sh` → `FAIL` lines.
- [ ] **Step 3: implement** `vb_install.py`, the `--bench` flag, the catalog row, `APPS`, and the two command texts.
- [ ] **Step 4: run to pass** — fixture `N passed, 0 failed`; `openxr-sim-fixture.sh` still passes;
  `python -m unittest tools/tests/vrbench_test.py` still `OK`.
- [ ] **Step 5: commit** — `"vrbench install/status; the pretend headset is offered in three ways at setup and update"`.

---

### Task 9: the command, the rule, the docs, the release

**Files:**
- Create: `plugins/lanes/commands/bench.md`
- Modify: `docs/PROTOCOL.md` (§24), `docs/TOOLS.md`, `CHANGELOG.md`, repo root `README.md`, `.claude-plugin/plugin.json`,
  `.claude-plugin/marketplace.json`, `CREDITS.md`, `tools/tests/smoke-test.sh` (the new command on the front page)

- [ ] **Step 1: `commands/bench.md`** (`/lanes:bench`, short `/vb`), in `menu.md`'s shape: what it is in three plain
  lines; which lane may use it (`/lm`-class: it launches and drives; `/pd`, `/gr`, `/sr`, `/gs` never); the four
  commands (`learn`, `start`/`stop`, `profile`, `status`); the claim; the "needs the screen until plan 2" honesty
  line; the model line (`MODEL: OPUS` for a learn run, read like a guided test); the write-up shape (close-out box,
  gate/model box, the stage table in Tefa's numbered rows).
- [ ] **Step 2: `docs/PROTOCOL.md` §24 "VR Bench: learned by the robot, marked by the person (0.74.0)"**: the rule
  that a game handed over ("all yours") may have its first setup done by `learn` alone, with every press preceded
  by a look and recorded (supersedes the 2026-09-29 "setup with the person first" wording in §22 — add one line
  there pointing here); the layer-per-run-per-bitness rule and why; recording is for development and footage stays
  in the transfer folder (spec §6.3). Then the same change to the estate's rule text
  (`claude-memory/PREFERENCES.md` and `game-mod-rules.md` "-o-matic" section, one line each) in that repo.
- [ ] **Step 3: `docs/TOOLS.md`** row for VR Bench (link `https://github.com/TefMeister/vr-bench`, check
  `vrbench.py status`), `CREDITS.md` (spec §8), root `README.md` command row and version, `CHANGELOG.md`:
  `- **0.74.0** (date): **VR Bench, the robot player.** ...` one plain paragraph; `plugin.json` + `marketplace.json`
  `0.74.0`.
- [ ] **Step 4: checks** — `bash tools/tests/smoke-test.sh`, `bash tools/tests/hooks-test.sh`,
  `python tools/scrub-scan.py .`, `python tools/code-shape-scan.py tools/vrbench`, `bash tools/release.sh 0.74.0 --check`
  → all pass.
- [ ] **Step 5: release** — `bash tools/release.sh 0.74.0 "VR Bench: a robot player for VR games on the OpenXR Simulator, installed from setup"`;
  then `/lanes:update` on this PC and the one-line-per-version note to Tefa; `owed.sh add HOME` for the home PC's
  update + `bench_headset = real`.

---

## Follow-on plans (written after Task 7 proves the layer live)

- **Plan 2 — background keyboard, mouse and pad (`benchinput.h`, proxy-gen `--bench`, Menu-o-matiC's background
  path).** Spec §5.2. Removes the "needs the screen" line; adds the learn-by-looking loop for a game with no route
  (§6.1 stage 1) and the pretend-focused hooks.
- **Plan 3 — the WEARING half (home PC).** Spec §5.1 mark, §5.6, §6.2, §6.3: the chord and haptic receipt in the
  layer, the mark files with the pointed spot, `vrbench start/stop` with recording (obs-rec + OBS Mirror install
  option), `debrief`, `purge`, the footage line in the close-out box.
