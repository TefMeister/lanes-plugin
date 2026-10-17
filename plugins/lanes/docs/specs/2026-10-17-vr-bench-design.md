# VR Bench — the robot player that learns a game and wears the headset for you

**Status:** design, waiting for Tefa's approval (2026-10-17). Not yet built.
**Written by:** a modding session on the dev PC, from a design conversation with Tefa the same day.
**Builds on:** the OpenXR Simulator (webhead2oo9's fork of elliotttate's), Menu-o-matiC / Move-o-matiC,
`obs-rec.py`, the Hand Freeze layer, BeG0nE's ride-along headers.
**Credit owed:** the idea of a "VR bench" that plays the game for you came from a Discord post Tefa saw. Its author is not
known yet; the name goes into CREDITS the day it is. Until then the credit line reads "the person on Discord whose
VR-bench write-up this is built from".

---

## 1. Why

Tefa's words: *"within this hour, you have learned the basics of how to drive menus and know how to move the character
around in both flat and vr - in vr you know how to move hands with motion controllers, can press motion controller
buttons"*, and *"it needs to work in the background, it is one of the biggest pain points for me."*

Today every test of a mechanic costs Tefa a headset session, and every session that drives a game steals the mouse,
keyboard and screen of the PC it runs on. Hard Reset showed the way out on 2026-10-16: with the simulator as a pretend
headset, a script turned the head, moved the hands and checked each step while nobody wore anything. VR Bench makes
that the normal shape for every game, and adds the half that only a real headset can give: a one-handed way to say
"look at THIS" while Tefa is wearing it, so the debrief afterwards needs no retelling.

## 2. What it is, in one picture

Two halves, one tool, one command (`/lanes:bench`, short name `/vb`):

- **BUILDING half (both PCs, through the simulator).** Point it at a game. It spends the hour learning the game by
  itself: launch, menus, walking and turning on the flat screen, then in VR the head, both hands, their buttons and
  sticks. What it learns goes into that game's `KNOWN.md` and routes, so the next session already knows how to drive
  it. Each run leaves the game easier to drive than it found it. Nothing it does needs the game window in front.
- **WEARING half (home PC only; the dev PC cannot use a real headset).** Tefa plays, in the headset, launched through
  VR Bench. Left grip + right grip + left trigger, held together, marks "look at this": the moment's picture is saved
  with a little before and after, and the spot the hand or gun points at is worked out and cropped. `debrief` gathers
  every mark with its pictures, the game log, the buttons pressed and the head and hand poses, into one page.

Tefa also framed it as two layers of the bridge from flat to VR: one used while building the bridge, one used once the
game plays in VR but is not yet ready for gameplay. That is the same two halves.

## 3. Goals, non-goals, anti-goals

**Goals**
1. Learn a game's basics without a person: menus to gameplay, flat movement, VR head, hands, buttons, sticks.
2. Run in the background: the game never takes Tefa's mouse, keyboard or focus while VR Bench drives it.
3. Mark-and-debrief in the headset with one button chord, no speech.
4. Record for development, both the monitor's picture and the headset's own view where that is possible, and
   delete footage once it has been used.
5. Know the PC it runs on: specs, headset, games, and whether a real headset can be worn there.
6. Install through the plugin's setup and update, as one of three simulator choices.
7. Work for anyone who installs the plugin, not only Tefa: no paths, names or machines in anything it ships or
   prints beyond the person's own PC.

**Non-goals (this version)**
- Playing through levels. Fights and reaching save points stay Tefa's job at home (standing rule, 2026-10-12).
- Judging comfort, scale or "how it feels". Only a person can.
- Speech. Tefa: *"i don't want it speech based"*.
- A 32-bit build of the OBS mirror layer (elliotttate's is 64-bit only); see §6.3 for what 32-bit games get instead.
- Replacing Menu-o-matiC's recorder. VR Bench uses and extends it; it does not fork it.

**Anti-goals (a failure even if it technically works)**
- A run that steals the screen or the keyboard, even once. Tefa would stop using it.
- Footage that piles up. Tefa: *"it does eat up storage quickly."*
- Guessing recorded as knowledge. Every learned fact carries how it was learned and whether it was seen to work.
- A "mark" that is lost or lands on the wrong moment.

## 4. Constraints, as found on 2026-10-17

- The **simulator fork is not ours** (`webhead2oo9/OpenXR-Simulator`; no push rights). Its command files move the head
  (`head_pose_command.json`) and the controllers' poses with **trigger and A only** (`controller_pose_command.json`);
  no grips, B/X/Y, sticks or menu button. Screenshots and an MCP helper exist. VR Bench may send pull requests upstream,
  but must not depend on them landing.
- **Our input today needs the game in front.** Menu-o-matiC sends keys with SendInput and refuses when the window is
  not foreground (`mom_window.py`). The Hard Reset mod presses keys the same way. This is the pain point.
- **Hand Freeze already is an OpenXR API layer of ours**, built 32- and 64-bit, registered per bitness under HKCU, and
  it already intercepts action states and space locations. VR Bench's layer grows from the same shape.
- **Recording** exists: `obs-rec.py` records the game window (never the screen) and the simulator's preview as a
  second file. It was switched off everywhere on 2026-10-16 (no YouTube). Tefa, 2026-10-17: back on **for development
  only**, and deleted when no longer needed.
- **elliotttate's OpenXR OBS Mirror** (`OpenXR-Layer-OBSMirror`): an x64 OpenXR layer + OBS source that records the
  headset's own view, with wider recording FOV and smoothing. D3D11/D3D12 OpenXR apps, 64-bit only, installer wants
  admin once for the OBS plugin folder.
- **Two PCs:** dev PC (old: i7-3770S, GTX 1660 SUPER, 16 GB, simulator only), home PC (powerful, simulator and a real
  headset). The heavy/light split is Claude's call (Tefa, 2026-10-17).
- **Standing rules that bind this:** numpad not F-keys; input by a combination of methods, measured against a
  no-input control; still camera and mouse tests before walking routes; music muted first; every blur and screen
  effect off in VR; jitter recorder in every early VR mod; nobody's name written down but the chosen one; new repos
  private unless Tefa says public; model line and gate line in every write-up.

## 5. How it gets made — the parts

### 5.1 The VR Bench layer (`vrbench_layer32.dll` / `vrbench_layer.dll`) — the pretend hands and the mark

An OpenXR API layer, C++, built from the Hand Freeze layer's shape, registered per bitness so a 32-bit game never
sees the 64-bit one (the Hand Freeze bug of 2026-10-16). It sits between ANY game and ANY runtime (the simulator or a
real headset), which is what makes both halves work with one piece:

- **BUILDING: input injection.** Reads a command file (`%LOCALAPPDATA%\VRBench\input.json`, replaced atomically,
  polled each `xrSyncActions`) and answers the game's questions from it: grip and aim poses for both hands, triggers,
  grips (squeeze), sticks and trackpads, A/B/X/Y, menu, stick clicks, and haptics requests logged back. Per action it
  can be `pass` (the runtime's own value), `set` (the file's value) or `add` (file on top of runtime). Poses are given
  in the LOCAL reference space in metres, like the simulator's own command files, so the Hard Reset drive script's
  numbers carry over. The head stays the simulator's job (it already does it well, and a layer cannot move the
  runtime's views).
- **WEARING: the mark.** Every `xrSyncActions` it reads the real left grip, right grip and left trigger. All three
  held together for 0.4 s = one mark (a second mark needs a release first). It writes
  `%LOCALAPPDATA%\VRBench\marks\<run>\<time>.json`: wall time, `XrTime`, head pose, both grip and aim poses, the last
  projection views the game submitted (`xrEndFrame`: pose, fov, image rect per eye), and the **pointed spot**: the
  right aim ray (left when only the left hand is tracked) projected into each eye's image as a 0..1 fraction. A gun
  points along the aim pose by definition, and an index finger points along it too (the aim pose is the runtime's
  pointing direction), so no image analysis is needed to find the spot; the picture crop is done later from these
  numbers. If haptics are available it pulses both hands once so Tefa knows the mark took.
- **Always:** a `vrbench_layer.log` per run with one line per state change and nothing per frame; the BeG0nE
  Occlusion Drift lines (`jl_hand_q`) for both controllers, so a lost controller is on record.
- Off unless `%LOCALAPPDATA%\VRBench\enabled` exists (written by `vrbench.py start`, removed by `stop`), so a game
  launched without VR Bench never sees it.

### 5.2 Background input for keyboard, mouse and pad — `benchinput.h`

The layer covers VR input. The flat half (menus, walking) still has to reach the game without focus. VR Bench uses a
combination, tried in this order and **recorded per game in KNOWN.md** as the route that worked (standing rule: a
combination of methods, measured):

1. **In-process, through our file next to the exe.** A header-only module `benchinput.h` (the jitterlog.h pattern:
   `#define BENCHINPUT_IMPLEMENTATION` in one file) that a proxy includes. It hooks what the game actually reads:
   `GetAsyncKeyState` / `GetKeyState` / `GetKeyboardState`, `GetCursorPos` / `SetCursorPos`, RawInput
   (`GetRawInputData`), DirectInput 8 device state and buffered data, `XInputGetState`, and the window's own
   `WM_KEY*` / `WM_MOUSE*` / `WM_INPUT` messages, and feeds them from `%LOCALAPPDATA%\VRBench\input.json` (the same
   file as the layer, flat section). It also **pretends the game is focused**: `GetForegroundWindow`,
   `GetActiveWindow`, `WM_ACTIVATE` / `WM_ACTIVATEAPP` / `WM_KILLFOCUS` answered as if the window were in front, so
   games that pause or stop drawing when unfocused keep going. Each hook is on its own switch so a game that
   misbehaves under one can have that one off. `proxy-gen` grows a `--bench` flag that puts `benchinput.h` into the
   generated logging proxy, so the very first file of ours next to a new game already lets VR Bench drive it.
2. **Window messages** (`PostMessage` of key and mouse events to the game window). Works for many menus, fails for
   games that read the keyboard directly. No foreground needed.
3. **SendInput with a short focus grab**, the way it is done today: the fallback, and VR Bench says in plain words
   that this game needs the screen for N seconds. Never silently.

A `probe` step (Menu-o-matiC already has one) holds a control through each route and checks whether the pointed-at
spot on the screen changed, so "the key reached the game" is measured, not assumed.

### 5.3 The driver — `tools/vrbench.py`

One Python tool, small files, named numbers (code-shape rule). Commands:

- `vrbench profile` — writes `%LOCALAPPDATA%\VRBench\profile.json`: CPU, GPU(s), RAM, Windows version, the active
  OpenXR runtime (64 and 32), the headset's system name when one answers, `headset = none | real` (from lanes.conf
  `bench_headset =`, set by setup), `tier = light | full` (light when the GPU is below GTX 2060 class or RAM below
  24 GB; Tefa's dev PC is light, the home PC full), the games list from `installed.py`. Printed with `vrbench status`.
- `vrbench learn <game> [--minutes 60] [--stage ...]` — the BUILDING half, §6.1.
- `vrbench start <game>` / `stop` — the WEARING half: switches the layer on, starts recording, waits; `stop` ends
  recording and runs the debrief (§6.2). Also used by `/lm` when it launches a game with VR Bench.
- `vrbench debrief [<run>]` — builds the debrief page from a run folder.
- `vrbench purge [--keep-days N]` — deletes footage per §6.3's rules; also run by `debrief` on its own run.
- `vrbench install [--layer-only]` / `uninstall` — registers the layer per bitness, installs the OBS mirror when the
  person says yes (§5.5), writes `installed.py record VR Bench <release>`.

It never launches a game in a lane that may not (only `/lm`, `/lanes:bench` itself, or the person's say-so), never
takes the screen, and never commits: KNOWN.md edits and run notes are left for the session to save with the board.

### 5.4 What a run leaves behind — the run folder

`%LOCALAPPDATA%\VRBench\runs\<game>\<date>_<time>\`:
`run.json` (what was asked, what happened, stage by stage, PASS / CHECK / UNKNOWN, how each was decided),
`screens\` (PNG stills: before / during / after each step, named by step), `marks\` (the layer's mark files plus a
crop per eye around the pointed spot, 1/4 of the eye wide, and the un-cropped eye picture), `game-log\` (a copy of
the game's and our mod's log for the run), `input.jsonl` (every input VR Bench sent, timestamped), `video\` (the
recordings, until purged), `debrief.md` (the page). The debrief and `run.json` are small and may be copied into the
game repo's `modding-notes/` by the session; the folder itself stays on the PC.

### 5.5 Three simulator choices in setup and update

`openxr-sim.py` keeps its two sources and gains `--bench`. `commands/setup.md` (VR group) and `commands/update.md`
step 7 offer, worded for someone who has never heard of either:

1. **OpenXR Simulator (webhead2oo9's build) + VR Bench** — the pretend headset that also runs 32-bit games, plus
   VR Bench, our robot player that learns a game's menus and controls by itself and, with a real headset, marks the
   spot you point at when you hold both grips and the left trigger. *(Recommended.)*
2. **OpenXR Simulator (webhead2oo9's build) only** — the pretend headset, 64-bit and 32-bit games.
3. **OpenXR Simulator (elliotttate's original)** — the pretend headset, 64-bit games only.

Choice 1 runs `openxr-sim.py install --fork` then `vrbench.py install`, and asks one more yes/no: install
elliotttate's OpenXR OBS Mirror too (records the headset's own view of 64-bit games; needs OBS and one administrator
prompt). Setup also asks, once: *"Can a real VR headset be used on this PC?"* → `bench_headset = real | none`.
`vrbench.py status --json` joins update's every-run checks (`installed`, `newer`), the Hand Freeze way.

### 5.6 Recording

- `obs-rec.py start` as today: the game window (never the screen) plus the simulator preview as the second file.
- With the OBS Mirror installed and a 64-bit game: a third source, **VR Mirror Capture**, into its own file
  (`<label>_headset_<date>.mp4`), so the headset's own view is on record, not the monitor's.
- 32-bit games: the simulator preview IS the headset view on the dev PC; on the home PC with a real headset there is
  no headset-view recording for 32-bit games yet. The run says so in one line.
- Marks: the layer's mark time is matched to the recording's clock (both wall time; `obs-rec.py` writes the start
  time into the run) so `debrief` can pull a still 2 s before, at, and 2 s after each mark with ffmpeg.

## 6. How it behaves

### 6.1 `learn` — the hour, stage by stage

Each stage ends PASS (seen to work, with the picture that shows it), CHECK (did something, not sure it is right) or
UNKNOWN (could not try), and writes its facts to `KNOWN.md` (`mom_known.py --add`, sections Menus / Controls / Save
spot / Hazards / What failed / Tool ideas) with the date and how it was found. Stages, each skippable, each resumable:

0. **Pre-flight:** read KNOWN.md and the routes; `profile`; the game's music to zero; the game windowed 1280x720
   (standing rules); which proxy of ours sits next to the exe and whether it carries `benchinput.h`; the layer on.
1. **Launch** through the recorded route if one exists, else launch and learn: take a picture every 2 s, and when the
   screen stops changing, the session (the model) reads it and names the one key most likely to get past it; a
   confirmed key becomes a route step (Menu-o-matiC's recorder format), so the route is built as it is learned.
   Hazards go to KNOWN.md ("intro video, skippable with Escape after 3 s"; "keep settings? countdown").
2. **Menus:** the three goals Menu-o-matiC asks for — launch → gameplay, launch → key bindings (pictured and read
   into `controls`), gameplay → desktop.
3. **Flat movement, still camera first:** mouse turn (25° steps, screenshot every 2 s) against a no-input control
   picture; then each movement key held 1.5 s with the probe watching the pointed-at spot. Only then a short walk.
4. **VR, through the simulator:** head yaw/pitch/roll steps and a position lean, checking the picture follows
   (`validate_stereo`, `capture_screenshot`, our mod's log); both hands to nine positions and wrist turns; each
   button and stick through the layer, watching the game's log or picture for what it did ("right trigger: fired";
   "A: jumped"). Where the game has no first-person hands (Psychonauts may not), the hand stages end UNKNOWN with the
   reason, and the rest still runs.
5. **Report:** `debrief.md` for the run plus the KNOWN.md diff, and the ideas for the tools themselves under
   `Tool ideas` (the `/gu` feed).

It stops at the time limit or when every stage has ended, whichever first, and leaves the game running by default
(standing rule since 2026-09-01) unless asked to close it.

**On the setup-with-Tefa rule.** The standing rule (2026-09-29) says a game's first automation setup is done WITH Tefa,
never by blind poking. Tefa's ask for VR Bench is that it learns the basics by itself. VR Bench's learning is not
blind: it looks at the screen before every press and records what it saw. This design records that `learn` may do a
game's first setup alone when Tefa hands the game over ("all yours"), and the rule text is updated to say so. Marked
here as a change for Tefa to confirm.

### 6.2 `start` / `stop` — Tefa in the headset, then the debrief

`start <game>`: layer on in mark mode, recording on (monitor + headset view where possible), the game launched the
usual way (or already running), then VR Bench waits and watches the marks folder. `stop`: recording off, then:

`debrief.md`, in Tefa's reading shape, short: one numbered row per mark with the time into the run, the crop of the
pointed spot for the eye the hand is in (both eyes when both), the wide still, which hand pointed, what buttons were
held in the 5 s before, head yaw/pitch at that moment, and the game's log lines from 3 s before to 3 s after. Then one
list of everything else that happened (session focus lost, controller lost, frame-rate dips from the jitter log).
Tefa reads the rows and writes one line each of what they meant; the session turns those into board rows. No
retelling.

### 6.3 Footage: kept only while useful

- Video is for development. It is written into the run folder, never into the MEGA transfer folder (changed from the
  2026-10-15 rule, which was for YouTube footage; Tefa 2026-10-17: *"not gonna upload them"*).
- `debrief` pulls its stills, then the video of that run is **deleted by default**; `--keep-video` keeps it, and a
  kept video is deleted by `purge` after `bench_keep_days` (default 7) unless its run folder holds a `keep` file.
- `vrbench status` prints how much footage is on disk. The close-out box gets one line when it is over 5 GB.

### 6.4 Light and full tiers

- **light** (dev PC): screenshots at the step rate only, recording of the game window at 720p30, no second/third
  recording unless asked, hands moved in fewer positions (5 not 9), one minute between stages for the old PC.
- **full** (home PC): everything above at 60 fps, the headset view recorded, nine hand positions, the WEARING half.
  The tier is a setting, not a build: one set of files, `tier =` in profile.json, overridable per run.

## 7. Where things live

| What | Where |
| --- | --- |
| driver | `plugins/lanes/tools/vrbench/` (`vrbench.py`, `vb_profile.py`, `vb_learn.py`, `vb_marks.py`, `vb_debrief.py`, `vb_record.py`, `vb_input.py`, `tests/`) |
| layer source | `plugins/lanes/vrbench/layer/` (C++, `build.bat` makes 32 + 64), `benchinput.h` beside it; copied into mods like `jitterlog.h` |
| layer binaries | GitHub release zips of a repo `TefMeister/vr-bench` (layer + json manifests + install.ps1), fetched by `vrbench.py install` like Hand Freeze; the plugin stays source-only |
| command | `plugins/lanes/commands/bench.md` (`/lanes:bench`, short `/vb`), `skills/bench/SKILL.md` |
| rule text | `docs/PROTOCOL.md` §21 "VR Bench: learned by the robot, marked by the person"; `docs/TOOLS.md` row; `lanes.conf.example` keys `bench_headset`, `bench_keep_days`, `bench_tier` |
| per-game knowledge | `ai-game-control-profiles/routes/<game>/KNOWN.md` and routes (public: game facts only) |
| per-PC state | `%LOCALAPPDATA%\VRBench\` (profile, runs, marks, input, enabled) |

## 8. Credits that ship with it

elliotttate (OpenXR Simulator, OpenXR OBS Mirror), webhead2oo9 (the simulator fork with the 32-bit runtime, command
files and MCP helper), mbucchia (OpenXR-Layer-Template, the shape the layers follow), Khronos (OpenXR headers,
Apache-2.0 OR MIT), OBS Studio and exeldro's Source Record, and the Discord author of the VR-bench idea (name to be
added). The plugin's CREDITS and the `vr-bench` repo's README both carry them, with the standing "email us if you
should be credited and are not" line.

## 9. Left to the builder

- Exact hook list and ordering inside `benchinput.h`, and how it reaches the game's Menu-o-matiC window checks.
- The pass/check rules per stage (what counts as "the picture followed the head").
- The input.json shape (one file for VR and flat, sections `vr` and `flat`; versioned).
- Which Menu-o-matiC functions grow a "background" path versus which VR Bench wraps.
- The debrief page's exact layout, inside Tefa's reading rules (numbered rows, no jargon).
- Tests: the layer's pure parts (chord timing, ray-to-image projection) and the driver's pure parts (stage
  state machine, purge rules, tier choice) run without a game or a headset.

## 10. Calls made in this document (Claude's, for Tefa to check)

1. The pretend hands and buttons are an **OpenXR layer of ours**, not a change to the simulator fork, because the
   fork is not ours and a layer also works with a real headset and with elliotttate's original.
2. The **pointed spot comes from the aim pose**, not from finding a finger in the picture: same answer, no guessing.
3. The chord is **held 0.4 s**, with a haptic pulse as the receipt.
4. Footage is **deleted after the debrief by default**, kept 7 days at most otherwise.
5. Tiers are **light / full chosen from the PC's specs**, one set of files.
6. The layer binaries ship from a **new repo `vr-bench`** by GitHub release, like Hand Freeze; the plugin stays source.
7. `learn` may do a game's first setup **alone** when the game is handed over; the 2026-09-29 rule text changes.
8. On the home PC, 32-bit games get **no headset-view recording** for now (the OBS Mirror is 64-bit only).
9. **The game still sees the three buttons during a mark.** The layer never swallows them: a mark in a fight may
   fire the gun or grab with the left hand, and that is accepted over a layer that changes gameplay. (Read-back of
   the design as its builder, 2026-10-17.)
10. **`/lanes:bench` takes the same LIVE claim as `/lm`** (`lane-claim.sh take bench <game>`), since it launches and
    drives the game; `/pd` must not run on that game meanwhile.
11. **A game with no file of ours yet gets the logging proxy with `benchinput.h`** installed by `learn`, said in one
    line, the way `/lm`'s first job already does; the file comes out again if the game will not run with it.
12. **First proof on Hard Reset, then Psychonauts.** Hard Reset already has the drive script and the hands; its run
    turns into VR Bench's first `learn`. Psychonauts, now on OpenXR, is the second.
13. Stills are cut from video with **FFmpeg** (setup §0.10 already offers it); without it, the debrief keeps the
    screenshots taken at the mark and says the before/after stills are missing.
