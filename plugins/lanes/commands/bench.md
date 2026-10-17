---
description: (VR Bench) A robot player for VR games - the OpenXR Simulator plays the headset, the VR Bench layer plays the hands, buttons and sticks, and a learning hour finds out how a game's head, hands and buttons behave with nobody wearing anything. Launching belongs to /lm (or the person's say-so); never from /pd, /gr, /sr or /gs.
---

`/bench` — **VR Bench.** Tests and learns a VR game with nobody in the headset. The OpenXR Simulator (by
elliotttate; webhead2oo9's fork for 32-bit games) shows the two eyes in a desktop window and moves the head; the
VR Bench layer ([TefMeister/vr-bench](https://github.com/TefMeister/vr-bench)) plays both controllers from a file.
A learning run moves the head, the hands and every button in turn, takes a picture after each, and writes down
what the game did.

The tool is `python "${CLAUDE_PLUGIN_ROOT}/tools/vrbench/vrbench.py"`, below `vrbench`. Design:
`docs/specs/2026-10-17-vr-bench-design.md`. Windows only; needs Pillow.

## Which lane may use it

- **`/lm`**: yes, all of it (typing `/lm`, or the person's "all yours", is the go-ahead to launch the game).
- **`/ms`**: only when the person asks for it in that session.
- **`/pd`, `/gr`, `/sr`, `/gs`**: never run `learn`, `start` or `stop`. They may run `status` and `profile`, and
  read the runs on disk.
- **One run at a time per PC.** `learn` takes a claim (lane `/vb`) and gives it back when it ends, even after an
  error; a second run is refused while one holds it.

## The commands

1. **`vrbench status [--json]`**: is the layer installed and switched on, is the simulator here, this PC's
   profile, how many runs are on disk. Read it first.
2. **`vrbench install`** / **`uninstall`**: the layer, from its newest GitHub release. `/lanes:setup` §3.6 and
   `/lanes:update` offer it; it refuses while a run is on.
3. **`vrbench start <exe | project>`** then **`vrbench stop`**: switches the layer on for the next run of that
   game only, registered for the game's bitness (32 or 64, read from the program itself), and takes it out of
   the OpenXR layer list again afterwards. Other OpenXR layers are never touched. Start BEFORE the game launches;
   an OpenXR game reads its layers once, at start.
4. **`vrbench profile`**: notes this PC's processor, graphics card, memory, OpenXR runtimes, games and headset,
   and picks the tier: **light** (5 hand poses, short holds) or **full** (9 poses, more pictures).
   `bench_tier =` in lanes.conf overrides it; `bench_headset = real | none` is asked once at setup.
5. **`vrbench learn <project> [--minutes 60] [--stage ...] [--tier light|full]`**: the learning hour. Stages:
   pre-flight, launch, menus, flat, VR head, VR hands, VR buttons, report. The game must already be running in
   the simulator. Each stage ends with a verdict (worked / did nothing / could not tell) and the reason.

## Before a run

- The game runs **windowed** and is confirmed (the window rule, `/lanes:menu`). Its music is muted.
- Its routes and `KNOWN.md` are read (`/lanes:menu`, PROTOCOL §22).
- `vrbench start <project>` before the launch, `vrbench stop` after the game has closed.
- ⚠️ **Until the background-input part lands, the menus and flat stages need the game's window in front**:
  Menu-o-matiC and Move-o-matiC press real keys. The VR stages do not: head, hands and buttons travel through
  files, so they run behind other windows.

## What a run leaves

`%LOCALAPPDATA%\VRBench\runs\<project>\<date>\`: `run.json` (stages and verdicts), `input.jsonl` (every input
sent), `screens/` (the pictures), `game-log/` (a copy of the game's own log, when `vrbench_log.<project>` names
it) and `debrief.md` when a run did not finish. Pictures are never committed. Video recording comes with the
wearing half (the real headset, OBS Mirror); its footage will be kept in the person's transfer folder and is never
deleted by the tool (`bench_footage_warn_gb` only says when it grows large).

## Report

`MODEL: OPUS` for a learning run: read it like a guided test, against what the board predicted. Then the usual
write-up (close-out box, gate/model box, the text sections) with the stages as numbered rows, one plain line each:
what was tried and what the game did ("𝟐 the left hand moved left, up, right and down as asked, in both eyes").
Anything learned about the game goes into its `KNOWN.md` and board the same session.
