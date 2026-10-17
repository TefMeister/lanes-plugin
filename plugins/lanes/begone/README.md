# BeG0nE tools in Lanes

Tools that find and remove unwanted faults in VR mods. They ship inside Lanes (since 0.62.0), so every install has
them and they update with the plugin. Each game's cures, the guides for modders and the gathered knowledge stay in
the public [BeG0nE](https://github.com/TefMeister/BeG0nE) repo.

| Tool | What it finds | Recorder a mod carries |
| --- | --- | --- |
| [Camera Jitter](camera-jitter/) | a stepped, jittery camera, and why | `jitterlog.h` (native) or `jitterlog.lua` (REFramework) |
| [Ghost Hand](ghost-hand/) | gaps between the real hand and the player's hand: lag, offset, jumps, lost tracking, gestures that miss | `ghosthand.h` (native) or `ghosthand.lua` (REFramework) |
| [Occlusion Drift](occlusion-drift/) | a two-handed aim drifting because one hand hides the other controller | none: read through Ghost Hand's tracked flags; per-game cure code in `games/` |

## How it works

1. A mod with a recorder wired in writes its numbers only while a headset session runs, into
   `%LOCALAPPDATA%\BeG0nE\<tool>\`.
2. The **rider** (`rider.py`, started by Lanes at every session) notices when the session ends and runs the tool's
   filer, which turns the numbers into a short `report.md` (and a `summary.json` for questions) in your BeG0nE home:
   `begone = <folder>` in lanes.conf (a clone of the BeG0nE repo, if you want the reports on GitHub), otherwise
   `Documents\BeG0nE recordings`. The raw recording moves to `done\` and stays on that PC.
3. Each session start shows one line per **new** report since that PC last looked (`tools/begone.py brief`); a
   session reads a full report only when a line looks wrong or its job is linked to that tool, and asks further
   questions with `tools/begone.py ask`, whose answers are capped.
4. The raw files are locked against being read by accident (`hooks/begone-raw-guard.py`).

## Adding a tool

A new folder here with a `tool.json` (name, what it finds, log folder and extension, its filer, the jobs it belongs
to, how a mod wires it in) and a filer that answers `file <log> --home <folder>` with one verdict line and
`ask <run folder> <question>` with short answers. The rider, the reader and the lock pick it up by themselves.
