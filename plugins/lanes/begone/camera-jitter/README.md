# Camera Jitter/Shake BeG0nE

> **In Lanes (0.62.0):** this tool ships in the plugin. The rider is the plugin's `begone/rider.py` (it files every tool), the filer is `file_jitter.py`, and `jitterlog.h`, `jitterlog.lua`, `jitter_log_check.py`, `knowledge.py` sit in this folder rather than `ride-along/`. Reports go to your BeG0nE home. Commands below that name `ride.py` are now `begone/rider.py` and `tools/begone.py`.


**Started 2026-10-01. The ride-along exists since 2026-10-08; nothing cures anything yet.** A cure for the
jittery camera that VR mods written with AI code so often have. First find out why. Then a tool for modders. Then a
jitter-free camera for specific games.

## The problem

Many VR mods written with AI help share one fault: when you move slowly and smoothly, the camera does not. It
steps. It teleports a little way, holds, and steps again. Players call it jitter or shake. It is not the
headset's frame rate, and it is not reprojection; those look different and a VR player tells them apart. It
happens across different games and different engines, which suggests the cause is in how the mods are written,
not in any one game.

## What is here

### `ride-along/` — the mod writes three timestamps a frame; a rider in the background reads them

A recording of the screen can show *that* the view steps. It cannot show *why*. The mod itself can: it knows
the moment it **read the headset pose**, the moment it **wrote the game's camera**, and the moment a **picture
went out**. Those three streams, timed to the microsecond, are the whole log.

| File | What it is |
| --- | --- |
| `jitterlog.h` | one header a C or C++ mod includes; six calls (`jl_init`, `jl_vr_on/off`, `jl_pose_*`, `jl_camera_*`, `jl_present`) |
| `jitterlog.lua` | the same for REFramework scripts |
| `jitter_log_check.py` | reads a log and says, per second of head turning, whether the view stepped and **why** |
| `ride.py` | the rider: idles in the background, notices a VR session, files its log the moment it ends. Started by the Lanes plugin at every session (`begone = <this clone>` in lanes.conf, Lanes 0.52.0+), or by `ride.py install` to start with Windows |

**It only activates when the game is really in VR.** The mod writes its log only between `jl_vr_on()` and
`jl_vr_off()`, which it calls when the VR session starts and stops (OpenXR READY/STOPPING, SteamVR init and
shutdown). A flat run writes nothing, so there is no switch to remember. The rider also watches two outside
signs (SteamVR's own processes; a windowed program with the OpenXR or OpenVR library loaded) so a session can
tell "VR is up but no mod is logging" from "nothing is running".

**Flat screen, simulator and real headset are never pooled** (Tefa, 2026-10-15: *"they are different in feel"*).
The checker reads where a session ran from the runtime name the mod passes to `jl_init`: pass `"flat"` for a flat
run, and otherwise the headset runtime's own name (OpenXR `xrGetInstanceProperties` runtimeName, spaces as
dashes, for example `openxr-steamvr` or `openxr-openxr-simulator`). A name containing `sim` counts as the
simulator; a bare `openxr`/`openvr` is "VR, headset or simulator not recorded". Each place gets its own sections
in FINDINGS.md and its own patterns. A flat run is only logged if the mod calls `jl_vr_on()` for it, with the
input-driven view as the pose and the game camera as the camera (not tried yet).

**Controllers ride the same log** (`jl_hand_*`, one line per controller read with a tracked flag), so Occlusion
Drift BeG0nE collects at the same time: per controller, how often tracking dropped, for how long, and how often
the other controller was within 30 cm when it did.

**What the checker can say that a recording cannot.** While the head turns:

| It measures | When it is off, the verdict names |
| --- | --- |
| camera writes per picture | *the camera is renewed less often than pictures are drawn* — the rate fault |
| pose reads identical to the one before | *the runtime handed a stale pose* — read at the wrong moment, or from a cache |
| pose reads per picture | *the pose is read less often than pictures are drawn* |
| pictures whose camera matches the pose before last | *the camera trails the pose by one frame* — swim, not jitter |
| age of the pose when the camera was written | *the pose was N ms old when used* |
| pictures that went out with an unchanged camera | **JITTER**, whatever the cause above |

```
python camera-jitter/ride-along/ride.py install            # start with Windows, start now (no admin needed)
python camera-jitter/ride-along/ride.py status             # running? VR seen? which mod is logging?
python camera-jitter/ride-along/ride.py check <file.jl>    # file one log by hand
python camera-jitter/ride-along/jitter_log_check.py selftest   # six made-up logs with known faults
```

Needs Python 3 with `numpy` (and `psutil` for the outside signs, `opencv-python` for the chart). The header
compiles as C89 and C++11 with no dependencies beyond Windows. Logs live in `%LOCALAPPDATA%\BeG0nE\jitter\`
and cost about 10 KB a second at 90 Hz.

**Wiring a mod takes four lines**: `jl_init` at load, `jl_vr_on/off` with the session, one `jl_pose_*` where
the pose is read, one `jl_camera_*` where the camera is written, `jl_present` where the frame goes out. The
log is only as honest as the placing: put `jl_pose_*` at the actual read of the runtime, not at a copy of it.

### `knowledge/` — what jittery looks like, what smooth looks like, and what separates them

`ride-along/knowledge.py` boils every filed session down to a **fingerprint** (the typical value of each
measure, rounded into buckets). Sessions with the same fingerprint are **one pattern** with a tally, so the base
never holds copies; only a genuinely new behaviour makes a new entry. Nobody is asked anything: a pattern is grouped as
jittery or smooth by the checker's own verdict. If the person wearing the headset does say how a session **felt**
(`ride.py label <run> jittery|smooth`) that label sticks to the pattern and outranks the checker. `FINDINGS.md`
is rebuilt from the whole base after every session: per game and across games, the range of each measure over
the jittery patterns beside the range over the smooth ones, and **which measures separate the two**. That
difference is the why. A pattern called jittery once and smooth another time is listed as a contradiction to
look at, not averaged away. Self-test: `python ride-along/tests/test_knowledge.py`.

### `data/` — every VR session, kept

One folder per session the rider filed: `summary.json`, `report.md` (the verdict and the why) and `chart.png`.
`INDEX.csv` lists them. Nothing is deleted. The data is what the cause will be confirmed from: the same mod
before and after a change, a mod that jitters beside one that does not.

### `archive/video-check/` — the first attempt, kept

A checker that read screen recordings (game window and headset view) and judged jitter / shake / hitch /
freeze from the pictures alone. Built and self-tested 2026-10-08, set aside the same day: the flat window
does not show the jitter, and the headset view can be recorded but says nothing about the cause. Its four
checked runs are kept beside it.

## The plan

1. **Find out why.** Wire `jitterlog.h` into a mod that jitters and one that does not; turn the head slowly in
   each; read the two reports. The working suspicion is the rate fault (camera renewed less often than the
   headset is sampled). `[hypothesis]` until a log shows it.
2. **A tool for modders**, human or AI: how to tell jitter from the other faults, where to look in a mod for
   the cause, and the code shape that avoids it. Goes in `guide/`.
3. **A jitter-free camera for specific games**, as a drop-in fix beside the game's VR mod, once the cause is
   understood. Goes in `games/<game>/`.
