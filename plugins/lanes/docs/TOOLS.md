# Optional tools: the catalog `/lanes:setup` walks through

Every tool below is **optional**. The lanes themselves need only Git and Bash. The rest are tools
these lanes have actually used on reverse-engineering and modding projects, grouped by what they let
a session do. `/lanes:setup` goes through them one group at a time. For each missing tool it offers
three choices: **Claude installs it**, **you install it yourself** from the official link below, or
**skip**.

Rules for every entry:
- **Official sources only.** A link here is the project's own site or its own GitHub. Never a
  mirror or a download aggregator.
- **Every entry names who made it**, with a link to them. These are other people's free tools; the
  credit is part of the entry, not an afterthought (sections 1 to 8). Section 9 is what Lanes itself
  brings, section 10 the other public repos sessions read.
- **The "Claude installs it" command** is what the session runs, shown to you before it runs. Most
  use `winget`, Windows' own package manager. Anything that needs administrator rights says so,
  because Windows will ask you to approve it.
- **"How to check"** is what `tools/setup-scan.py` looks for. A tool counts as present only when
  that check passes.
- **"(ours)"** marks a tool made alongside Lanes, by the same maintainer. **"Not offered yet"** marks one
  of ours that has no download yet: setup names it so you know it is coming and offers it once it has a
  release (the scan asks GitHub).
- Links and steps were checked on 2026-09-17, the rows added in 0.79.0 on 2026-10-18, and the two game-inspecting MCP servers on 2026-10-23. Projects
  move; if a step no longer matches the project's own README, the README wins.

---

## 1. Core: working with the repos

| Tool | What it is for | Official link | Claude installs it | How to check |
| --- | --- | --- | --- | --- |
| **Git for Windows** (includes Git Bash), by the [Git for Windows project](https://github.com/git-for-windows) | Keeps every version of every file and carries work between sessions and PCs. Every lane pulls, commits and pushes with it, and the board tools run in its Bash | https://git-scm.com/download/win | `winget install --id Git.Git -e` | `git --version` |
| **GitHub CLI**, by [GitHub](https://github.com/cli/cli) | Lets a session talk to GitHub directly: make private repos, read and close issues, make releases, star and follow. Without it those steps are yours, by hand in the browser | https://cli.github.com/ | `winget install --id GitHub.cli -e`, then **you** run `! gh auth login` (it opens a browser) | `gh auth status` |
| **Python 3.12**, by the [Python Software Foundation](https://www.python.org/psf-landing/) | Runs nearly every helper Lanes ships: the scans, the board tools, screenshots, input, the BeG0nE reports, reading program files | https://www.python.org/downloads/windows/ | `winget install --id Python.Python.3.12 -e` | `python --version` works (not the Microsoft Store stub) |
| **Python packages**: [pefile](https://github.com/erocarrera/pefile) (Ero Carrera), [capstone](https://github.com/capstone-engine/capstone) (Nguyen Anh Quynh and team), [Pillow](https://github.com/python-pillow/Pillow), [psutil](https://github.com/giampaolo/psutil) (Giampaolo Rodola), [pywin32](https://github.com/mhammond/pywin32) (Mark Hammond), [numpy](https://github.com/numpy/numpy) | pefile reads a game's .exe and .dll files (what they need, what they offer); capstone turns machine code into readable instructions; Pillow takes and compares screenshots; psutil and pywin32 find, focus and drive windows; numpy does the number work in the BeG0nE reports and image checks | https://pypi.org/ | `python -m pip install pefile capstone pillow psutil pywin32 numpy` | `python -c "import pefile, capstone, PIL, psutil, win32gui, numpy"` |
| **uv**, by [Astral](https://github.com/astral-sh/uv) | A fast Python installer. Runs Python-based MCP servers (the links that let Claude use another program) such as Blender MCP and gimp-mcp, each in its own sealed box | https://docs.astral.sh/uv/ | `winget install --id astral-sh.uv -e` | `uvx --version` |
| **7-Zip**, by [Igor Pavlov](https://www.7-zip.org/) | Opens tool downloads and archives of every kind (.7z, .zip, .rar and more) | https://www.7-zip.org/ | `winget install --id 7zip.7zip -e` | `7z` in `C:\Program Files\7-Zip\` |

## 2. Building mod code

| Tool | What it is for | Official link | Claude installs it | How to check |
| --- | --- | --- | --- | --- |
| **llvm-mingw**, by [Martin Storsjö](https://github.com/mstorsjo/llvm-mingw) | A compiler that turns C and C++ into Windows programs and DLLs, for both 32- and 64-bit games. It builds the small files a mod drops into a game folder (`tools/proxy-gen`) and quick test programs | https://github.com/mstorsjo/llvm-mingw/releases | `winget install --id MartinStorsjo.LLVM-MinGW.UCRT -e` | `x86_64-w64-mingw32-clang --version` |
| **CMake**, by [Kitware](https://cmake.org/) | Sets up bigger C++ projects so they build the same way on every PC | https://cmake.org/download/ | `winget install --id Kitware.CMake -e` | `cmake --version` |
| **Visual Studio 2022 Build Tools** (C++ workload), by [Microsoft](https://visualstudio.microsoft.com/) | Microsoft's own compiler. Needed for mods that must match it exactly, such as REFramework native plugins, Window View and VR Bench | https://visualstudio.microsoft.com/downloads/ (under "Tools for Visual Studio") | `winget install --id Microsoft.VisualStudio.2022.BuildTools -e --override "--add Microsoft.VisualStudio.Workload.VCTools --includeRecommended --passive"`. **Needs admin; about 6 GB** | `vswhere` finds a VC tools install |
| **Rust (rustup)**, by the [Rust project](https://github.com/rust-lang/rustup) | Builds tools written in Rust from their source, such as Ghidrust | https://rustup.rs/ | `winget install --id Rustlang.Rustup -e` | `cargo --version` |
| **Lua 5.4**, by [PUC-Rio](https://www.lua.org/) | `luac -p` checks a game's Lua script for typing mistakes before it goes into the game, so a typo costs seconds instead of a game restart | https://www.lua.org/download.html | `winget install --id DEVCOM.Lua -e` | `luac -v` |

## 3. Reverse engineering

| Tool | What it is for | Official link | Claude installs it | How to check |
| --- | --- | --- | --- | --- |
| **x64dbg**, by the [x64dbg team](https://github.com/x64dbg/x64dbg) | A debugger: pauses a running game and shows what it is doing at that moment (its memory, its numbers, the code it is running). This is how a camera or a hand gets found in a game nobody has written notes on | https://x64dbg.com/ | `winget install --id x64dbg.x64dbg -e` | `x64dbg.exe` in the winget package's `release\x64\` |
| **x64dbg-automate** (plugin + Python client + MCP server), by [Darius Houle](https://github.com/dariushoule) | Lets Claude drive x64dbg itself: set stops, read memory, step through code, without you clicking anything | https://github.com/dariushoule/x64dbg-automate · client docs https://dariushoule.github.io/x64dbg-automate-pyclient/installation/ | `python -m pip install x64dbg-automate`, then put the plugin release files in x64dbg's `release\x64\plugins\` as its install page says; then `claude mcp add --scope user x64dbg --env X64DBG_PATH=<path to x64dbg.exe> -- x64dbg-automate-mcp` | `x64dbg-automate.dp64` in the plugins folder; `x64dbg` in `claude mcp list` |
| **x64dbg-skills** (Claude Code plugin), by [Darius Houle](https://github.com/dariushoule) | Ready-made debugger routines Claude can follow: save the whole state of a game and compare two moments, trace code, turn a function into readable C | https://github.com/dariushoule/x64dbg-skills | `claude plugin marketplace add dariushoule/x64dbg-skills`, then `claude plugin install x64dbg-skills@x64dbg-skills` | in `claude plugin list` |
| **Ghidrust** (+ its MCP server), by [oofz](https://github.com/oofz) | Reads a game's .exe with nothing running: lists its functions and text, shows who calls what, and **turns machine code back into readable C**. Most `/pd` work on a new game starts here | https://github.com/oofz/Ghidrust (Apache-2.0) | needs Git + Rust: `git clone https://github.com/oofz/Ghidrust %USERPROFILE%\Tools\Ghidrust`, then `cargo build --release` in that folder (several minutes); then `claude mcp add --scope user ghidrust -- %USERPROFILE%\Tools\Ghidrust\target\release\ghidrust.exe mcp` | `ghidrust` in `claude mcp list` and the exe exists |
| **RE Engine MCP**, by [praydog](https://github.com/praydog) | Lets Claude look inside a running RE Engine game (Resident Evil 2/3/4/7/Village, Monster Hunter, Devil May Cry and more) while it plays: every object, value and function the game has, read and changed live, and small C# test plugins built and reloaded in the running game with their errors read back. Instead of guessing what a number in memory means, a session asks the game. Needs a nightly REFramework with its C# add-on in the game; only that game's own session puts the game half in (`engine-mcp.py game re`). RE Engine games only | https://github.com/praydog/re-engine-mcp (MIT) | `python tools/engine-mcp.py install re`: fetches it, builds it and registers it with Claude Code; the same command updates it. Needs the **.NET 10 SDK** first (`winget install --id Microsoft.DotNet.SDK.10 -e`, **needs admin**) | `python tools/engine-mcp.py status` |
| **UEVR-MCP**, by [elliotttate](https://github.com/elliotttate) | The same for Unreal Engine 4 and 5 games running UEVR: every object and function live, Lua run inside the game, the headset's and controllers' poses, screenshots straight from the graphics card, hooks that log what the game calls when you do something, and dumps of the game's whole class layout. Some of its commands read the game's .exe with nothing running. Only that game's own session puts the game half in (`engine-mcp.py game uevr`). Unreal Engine games only | https://github.com/elliotttate/uevr-mcp | `python tools/engine-mcp.py install uevr`: the newest release (one self-contained program, no SDK), registered with Claude Code; the same command updates it. No admin | `python tools/engine-mcp.py status` |
| **Steamless**, by [atom0s](https://github.com/atom0s/Steamless) | Some Steam games ship their .exe wrapped in a protective shell that hides the real code from a debugger or decompiler. Steamless unwraps a copy so it can be read. **Only on games you own, only for your own modding, and the unwrapped file is never shared** | https://github.com/atom0s/Steamless/releases | **you**: download the release zip and unzip it anywhere (no installer), then write `steamless = <that folder>` in `lanes.conf` so sessions find it | `Steamless.exe` in the `steamless =` folder |

## 4. Driving an app unattended

| Tool | What it is for | Official link | Claude installs it | How to check |
| --- | --- | --- | --- | --- |
| **ViGEmBus** (virtual gamepad driver), by [Benjamin Höglinger-Stelzer (nefarius)](https://github.com/nefarius/ViGEmBus) | Makes Windows believe an Xbox controller is plugged in, so a session can press pad buttons in games that ignore the keyboard | https://github.com/nefarius/ViGEmBus/releases (archived by its author in 2023, still works) | `winget install --id ViGEm.ViGEmBus -e`. **Needs admin (a driver)** | Windows service `ViGEmBus` is running |
| **vgamepad** (Python), by [Yann Bouteiller](https://github.com/yannbouteiller/vgamepad) | The Python side of ViGEmBus: what Menu-o-matiC and Move-o-matiC press the pretend pad with | https://pypi.org/project/vgamepad/ | `python -m pip install vgamepad` | `python -c "import vgamepad"` |

## 5. 3D, images and assets

### Blender + Blender MCP: step by step

**What it gives you:** Claude can build and change 3D scenes in a running Blender (models, materials,
renders), for things like weapon remakes and reference props. Blender is by the
[Blender Foundation](https://www.blender.org/); Blender MCP by [Siddharth Ahuja (ahujasid)](https://github.com/ahujasid).

**Check before you start.** `setup-scan.py` asks the add-on inside Blender for the scene and reports
**"link live"** on the Blender MCP line. That is the test that matters: a registered server and an
add-on file on disk prove the first four steps were done, not that the link works. If it is already
live, skip this section — nobody should be walked through steps they finished long ago. Also note
`install-addon` crashes while printing its result on a Windows console that cannot show `→`; run it
with `PYTHONIOENCODING=utf-8`, and the install itself succeeds either way.

1. **Install Blender.** Official site: **https://www.blender.org/download/**. Pick the Windows
   installer. Or let Claude run `winget install --id BlenderFoundation.Blender -e`.
2. **Install uv** (section 1). The MCP server runs through `uvx`. The project says to use the
   official installer, not `pip install uv`.
3. **Add the server to Claude Code** (one line, run once per machine):
   `claude mcp add --scope user blender -- uvx mcp-for-blender`
4. **Install the Blender add-on:** `uvx mcp-for-blender install-addon`
5. **In Blender:** Edit → Preferences → Add-ons → enable **"Interface: MCP for Blender"**.
6. **Connect:** in the 3D viewport press **N**, open the **MCP for Blender** tab, click
   **Start MCP Server**.
7. **Restart Claude Code.** New MCP servers are picked up at session start. `claude mcp list`
   should show `blender`, and a session can then read the scene.

Official project page: **https://github.com/ahujasid/mcp-for-blender** (MIT). It used to be called
`blender-mcp`; an older setup that runs `uvx blender-mcp` still works, and new installs should use
`mcp-for-blender`. Run only **one** MCP client connected to Blender at a time.

| Tool | What it is for | Official link | Claude installs it | How to check |
| --- | --- | --- | --- | --- |
| **CubeKit** (Blender add-on, ours) | Builds pixel-style models out of little cubes, like pixel art with depth, from a settings file instead of by hand: one cube size for everything, pick any single cube, carved wear, stop-motion animation, and export for GZDoom. Made for the old-school shooter weapons and hands | https://github.com/TefMeister/blender-cubekit | download `dist/blender_cubekit-<version>.zip` from the repo, then `blender --command extension install-file --repo user_default --enable <zip>` (Blender 4.2 or newer) | a `blender_cubekit` folder in Blender's `extensions\` |
| **RE Mesh Editor** (Blender add-on), by [NSACloud](https://github.com/NSACloud) | Opens and saves the 3D models of RE Engine games (Resident Evil 2, 3, 4, 7, Village) in Blender | https://github.com/NSACloud/RE-Mesh-Editor (archived, GPL-3.0) | manual: download the release zip, then Blender → Add-ons → Install from Disk | listed in Blender's add-ons |
| **GIMP**, by the [GIMP team](https://www.gimp.org/) | A free image editor, like Photoshop. Used for cleaning up scanned drawings, textures and screenshots | https://www.gimp.org/downloads/ | `winget install --id GIMP.GIMP.3 -e` | `gimp-3.exe` in GIMP's `bin\` folder |
| **gimp-mcp**, by [maorcc](https://github.com/maorcc/gimp-mcp) | The link that lets Claude work inside a running GIMP, the way Blender MCP does for Blender: open, crop, clean, colour-correct and export images while you watch. **To use it:** open GIMP, open an image, then Tools → MCP → Start MCP Server | https://github.com/maorcc/gimp-mcp (GPL-3.0) | needs Git, uv and GIMP: clone it to a tools folder; copy its `gimp-mcp-plugin.py` into `%APPDATA%\GIMP\<version>\plug-ins\gimp-mcp-plugin\`; then `claude mcp add --scope user gimp -- uv run --directory <clone> gimp_mcp_server.py`; restart GIMP and Claude Code | `gimp` in `claude mcp list` and the plugin file in GIMP's `plug-ins\` |
| **Real-ESRGAN** (portable ncnn-vulkan build), by [Xintao Wang (xinntao)](https://github.com/xinntao/Real-ESRGAN) | Enlarges a small or blurry picture four times while keeping it sharp. Used for old low-resolution scans; the `realesrgan-x4plus` model keeps pencil grain (the `-anime` one looks painted). Runs on any graphics card | https://github.com/xinntao/Real-ESRGAN/releases (the `realesrgan-ncnn-vulkan-...-windows.zip`) | download that zip from the latest release and unzip it into `%LOCALAPPDATA%\Programs\Real-ESRGAN`; elsewhere, write `realesrgan = <folder>` in `lanes.conf` | `realesrgan-ncnn-vulkan.exe` there, on PATH, or in the `realesrgan =` folder |

## 6. VR

| Tool | What it is for | Official link | Claude installs it | How to check |
| --- | --- | --- | --- | --- |
| **SteamVR**, by [Valve](https://store.steampowered.com/app/250820/SteamVR/) | The program that connects a PC VR headset to games. Most VR mods run through it | https://store.steampowered.com/app/250820/SteamVR/ | **you**, through Steam | installed in Steam |
| **Virtual Desktop** (Quest headsets), by [Guy Godin](https://www.vrdesktop.net/) | Streams PC VR to a Quest wirelessly, with its own OpenXR runtime (the part games talk to). **Paid app** on the headset; the PC Streamer is free | https://www.vrdesktop.net/ | **you**: buy on the headset's store, install the Streamer from that site | `VirtualDesktop.Streamer` running |
| **OpenXR Simulator**, by [elliotttate](https://github.com/elliotttate); 32-bit fork by [webhead2oo9](https://github.com/webhead2oo9) | A pretend headset: shows a VR game's two eyes in a desktop window, head and controllers moved by mouse, keys or small command files, so VR work can be built and checked with no headset plugged in. The original is for 64-bit games; the fork adds a 32-bit runtime, controller command files, screenshots and a helper for Claude Code | https://github.com/elliotttate/OpenXR-Simulator (fork: https://github.com/webhead2oo9/OpenXR-Simulator) | `python tools/openxr-sim.py install` (the original), `... install --fork` (with 32-bit); no admin, the same command updates it. It is NOT switched on: a mod points at it for one game, or the user runs its Activate script for every game | `python tools/openxr-sim.py status` |
| **Hand Freeze** (ours) | Holds both VR controllers still in any OpenXR game, so hand and weapon poses can be tuned with the mouse while the controllers lie on the desk. Switch it ON before starting the game | https://github.com/TefMeister/hand-freeze-vr | `python tools/hand-freeze.py install` (the newest release, no admin; the same command updates it) | `HandFreeze.exe` in `%LOCALAPPDATA%\Programs\HandFreeze` |
| **VR Bench** (ours) | A robot player for VR games: with the OpenXR Simulator as the headset, it plays both controllers' poses, buttons and sticks from a file, so a session can learn and test a game's head, hands and buttons with nobody wearing anything (`/lanes:bench`). With a real headset, holding both grips and the left trigger marks the spot you point at, so you can show a session where something is wrong | https://github.com/TefMeister/vr-bench | `python tools/vrbench/vrbench.py install` (the newest release, no admin; the same command updates it), or `openxr-sim.py install --fork --bench` with the simulator. Registered only for one run, for the game's bitness | `python tools/vrbench/vrbench.py status` |
| **Window View** (ours, **untested**, not offered yet) | Hangs any desktop window (Hand Freeze, Hand Poser, a browser) inside any OpenXR game, about a metre in front of you, and lets you use it with the mouse and keyboard while the game only hears the controllers. Page Up hands the mouse to the floating windows, Page Down gives it back. Made so a mod can be tuned without taking the headset off. Proven only on the OpenXR Simulator so far | https://github.com/TefMeister/window-view-vr | once it has a release: download the zip, unzip, right-click `install.ps1` → Run with PowerShell (no admin). Switch its layer ON before the game starts | `WindowView` in `%LOCALAPPDATA%\Programs\` |
| **Hand Poser** (ours, **untested**, not offered yet; RE Engine games only) | A small window of sliders that poses the player's fingers and wrists live in an RE Engine game (through REFramework), keeps each pose, and saves named poses to load later. With Hand Freeze holding the controllers and Window View showing this window in the headset, fingers can be posed from inside VR. Inspired by the poser in [alphaZomega's EMV Engine](https://github.com/alphazolam/EMV-Engine). Proven only against a stand-in game so far | https://github.com/TefMeister/hand-poser-vr | once it has a release: download the zip, unzip, right-click `install.ps1` → Run with PowerShell (no admin). The game needs REFramework | `HandPoser.exe` in `%LOCALAPPDATA%\Programs\HandPoser` |

## 7. Per-game frameworks (install into one game, only when that game needs it)

These go **into a game's folder**, so a session installs them only as part of that game's own work,
never from `/lanes:setup`. Links are here so they are all in one place, with the people who made them.

| Framework | What it is for | Official link |
| --- | --- | --- |
| **REFramework**, by [praydog](https://github.com/praydog) | The base of every RE Engine mod (Resident Evil 2/3/4/7/Village and more): Lua scripts, native C++ plugins, an in-game menu, and VR for the whole game. Visceral and the Village scope are built on it | https://github.com/praydog/REFramework · dev builds https://github.com/praydog/REFramework-nightly/releases |
| **UEVR**, by [praydog](https://github.com/praydog) | Puts almost any Unreal Engine 4 or 5 game into VR with no game-specific code; our own plugin then adds what the game needs (Silent Hill 2 remake) | https://uevr.io/ · https://github.com/praydog/UEVR · nightly builds https://github.com/praydog/UEVR-nightly |
| **EMV Engine**, by [alphaZomega](https://github.com/alphazolam) | An REFramework script that opens up an RE Engine game's objects, joints and animations in a menu: inspect, move and pose anything. The idea behind our Hand Poser | https://github.com/alphazolam/EMV-Engine |
| **ree-pak-rs**, by [eigeen](https://github.com/eigeen) | Unpacks RE Engine `.pak` archives so the game's own files (scripts, models, menus) can be read | https://github.com/eigeen/ree-pak-rs (MIT) |
| **REMSG_Converter**, by [dtlnor](https://github.com/dtlnor) | Turns RE Engine text files into something editable and back, for changing in-game wording | https://github.com/dtlnor/REMSG_Converter (MIT) |
| **GZDoom VR**, by [hh79](https://github.com/hh79) (on GZDoom by the [ZDoom team](https://github.com/ZDoom/gzdoom)) | Classic Doom, Heretic, Hexen and mods such as Brutal Doom and Ashes 2063 in a VR headset. Our 3D weapons and hands are made for it, and we keep a patched build of it | https://github.com/hh79/gzdoomvr |
| **OldUnreal's Unreal 227 patch**, by [OldUnreal](https://github.com/OldUnreal) | The community patch that keeps Unreal (1998) and Unreal Gold running on modern Windows, with its own SDK and the ICBINDx11 renderer our Unreal Gold driver builds on | https://github.com/OldUnreal/Unreal-testing |
| **ReXGlue SDK**, by [the rexglue team](https://github.com/rexglue) | Turns an Xbox 360 game's code into a Windows program (static recompilation), so games that never came to PC can be run and then modded. Condemned 2 and The Darkness are built with it | https://github.com/rexglue/rexglue-sdk |

## 8. Recording, editing videos and moving big files

For turning test runs into progress videos, for the recordings the BeG0nE jitter reports are cut from,
and for carrying files between your own PCs that must never go on GitHub.

| Tool | What it is for | Official link | Claude installs it | How to check |
| --- | --- | --- | --- | --- |
| **OBS Studio**, by the [OBS Project](https://github.com/obsproject/obs-studio) | Records the screen or one window. Sessions drive it to record a game while BeG0nE logs a headset run (`begone_record = yes`), so every jittery second can be looked at picture by picture | https://obsproject.com/ | `winget install --id OBSProject.OBSStudio -e`. **Needs admin** | `obs64.exe` in `C:\Program Files\obs-studio\bin\64bit\` |
| **Source Record** (OBS plugin), by [exeldro](https://github.com/exeldro/obs-source-record) | Lets OBS record one window (the game, the simulator's view) into its own file, without catching anything else on the screen | https://github.com/exeldro/obs-source-record/releases | **you**: run the `source-record-<version>-windows-installer.exe` from the latest release (it installs into OBS; Windows asks for approval) | a `source-record` plugin in OBS's plugins folder |
| **obsws-python**, by [aatikturk](https://github.com/aatikturk/obsws-python) | The Python side that lets a session start and stop OBS recordings by itself, through OBS's own remote control (its WebSocket server, switched on in OBS → Tools → WebSocket Server Settings) | https://pypi.org/project/obsws-python/ | `python -m pip install obsws-python` | `python -c "import obsws_python"` |
| **FFmpeg**, by the [FFmpeg project](https://ffmpeg.org/) (Windows builds by [gyan.dev](https://www.gyan.dev/ffmpeg/builds/)) | What **Claude** uses on the recordings: check them, cut clips, join them, pull out still frames (the BeG0nE contact sheets), and convert files the free Resolve will not open (for example some HEVC or 10-bit recordings, or MKV files) into ones it will | https://ffmpeg.org/download.html | `winget install --id Gyan.FFmpeg -e` | `ffmpeg -version` |
| **DaVinci Resolve** (free version), by [Blackmagic Design](https://www.blackmagicdesign.com/) | The video editor **you** cut the recordings in: trimming, titles, music. The free version is enough. Claude does not drive it (scripting it from outside needs the paid Studio version). Resolve runs without FFmpeg, but install both together | https://www.blackmagicdesign.com/products/davinciresolve | **you**: the download asks for a short sign-up form first | `C:\Program Files\Blackmagic Design\DaVinci Resolve\Resolve.exe` |
| **MEGA desktop app**, by [MEGA](https://mega.io/) | Keeps one folder the same on all your PCs, so the files a project needs on both but that must never go on GitHub (the app's own files, extracted assets, recordings, big builds) travel by themselves. Free tier available; any other sync app works too. **For your own PCs only; sharing game files with anyone else is illegal** | https://mega.io/desktop | **you**: install it and sign in (your account and password are yours alone), then set up the sync as `/lanes:setup` §0.9 says | `transfer =` set in `lanes.conf` |

### Other people's tools, got by `tools/outside.py` (0.92.0)

Each is an optional extra (`outside_<name>` in `features.py`), asked once at setup or update.
`python outside.py get <name>` gets one; `outside.py newer` says which have a newer release.

| Tool | What it is for | Link | How Lanes gets it |
| --- | --- | --- | --- |
| **OpenXR OBS Mirror**, by [elliotttate](https://github.com/elliotttate) | Lets OBS record what the headset is shown, in Direct3D 11 and 12 OpenXR games and SteamVR; the BeG0nE recording then films the headset view beside the game window (the Resident Evil games included) | https://github.com/elliotttate/OpenXR-Layer-OBSMirror | its own installer (checked against the release's SHA256SUMS); needs OBS Studio |
| **xrFPS**, by [elliotttate](https://github.com/elliotttate) | Turn a controller upside down in any OpenXR game to see the frame rate and frame times as a graph, inside the headset | https://github.com/elliotttate/xrFPS | its own installer (checked against the release's SHA256SUMS) |
| **OpenXR CAS**, by [elliotttate](https://github.com/elliotttate) | Sharpens the headset picture (AMD's FidelityFX CAS) and adjusts colour in any OpenXR game; changes what every test sees, so it is downloaded, not switched on | https://github.com/elliotttate/OpenXR-CAS | the release zip, unpacked |
| **PIX MCP**, by [elliotttate](https://github.com/elliotttate) | Takes apart one captured frame of a Direct3D 12 game, draw by draw, through Microsoft PIX: which pass drew what, with which textures and numbers (the RE Engine games are Direct3D 12) | https://github.com/elliotttate/pix-mcp | a clone, its own Python environment, then added to Claude Code as a connector; needs Microsoft.PIX |
| **Nsight Graphics MCP**, by [elliotttate](https://github.com/elliotttate) | The same for NVIDIA's frame tool: capture a frame of a D3D11, D3D12 or Vulkan game and read every draw, resource and timing from it | https://github.com/elliotttate/nsight-graphics-mcp | a clone, its own Python environment, then added to Claude Code as a connector; needs NVIDIA Nsight Graphics, from https://developer.nvidia.com/nsight-graphics (an NVIDIA graphics card only) |
| **vrframework guides**, by [elliotttate](https://github.com/elliotttate) | A 17-part guide to making a flat game VR from the outside, built on REFramework and two of mutars' ports: frame timing, one eye per frame (AFR) and its smearing, per-eye projection, HUD, input. Read, not built: its code is a scaffold | https://github.com/elliotttate/vrframework | a clone |
| **MelonMCP**, by [elliotttate](https://github.com/elliotttate) | A live connection into Unity games through MelonLoader: inspect and change the running game, the Unity cousin of the RE Engine and UEVR connectors | https://github.com/elliotttate/MelonMCP | a clone |
| **UEVR cutscene comfort**, by [elliotttate](https://github.com/elliotttate) | A UEVR plugin that puts the camera back after a cutscene by itself, and can show cutscenes on a still screen in the room, for Unreal games such as Silent Hill 2 | https://github.com/elliotttate/uevr-cutscene-comfort | a clone |
| **UEVR RenderDoc Capture**, by [elliotttate](https://github.com/elliotttate) | UEVR with RenderDoc built in: grab one real Direct3D 12 frame, flat or stereo, from an Unreal game and open it in RenderDoc | https://github.com/elliotttate/UEVR-RenderDoc-Capture | the release zip, unpacked |
| **UEVR 6DOF window**, by [elliotttate](https://github.com/elliotttate) | A UEVR fork with a comfort mode that shows the game in a stereo window you can lean around, for games that are uncomfortable in full VR | https://github.com/elliotttate/UEVR-6DOF-Window | the link only |

---

## 9. What Lanes itself gives you (built in, nothing to install)

Everything here comes with the plugin. The commands are typed in a session; the rest runs by itself or
is used by the commands. Full rules: `docs/PROTOCOL.md`.

**The lanes, one kind of session each**

| Command | What it is for |
| --- | --- |
| `/lanes:gates` | Prints every project's open work, grouped by what it needs: nothing running, you, the app running, or special hardware such as a headset. The quickest answer to "what can be done right now?" |
| `/lanes:gate-watch` | A quiet background watcher that tells you when another session or your other PC has pushed work that changes what can be done. Says nothing when nothing changed |
| `/lanes:pd` | Parallel development: moves a project as far as it can go with nothing running, reading the program's files, writing and compiling code, unblocking what was stuck. Never starts the app |
| `/lanes:lm` | Live modding: the one lane allowed to start the app, drive it and test in it, by itself, while you are away. It closes the app when the run ends |
| `/lanes:ms` | Manual session: you are the hands. The session gives you a few numbered steps, you do them and say what you saw, it reads the logs and writes the next piece of code |
| `/lanes:gr` | Research on the open web for each project, after reading the project's own notes and dead ends first, so nothing is looked up twice |
| `/lanes:sr` | Research across all projects at once, building one shared library of what works in which engine |
| `/lanes:gs` | A read-only check of every repo: are findings marked with how sure they are, are hand-over folders being emptied, has anything drifted. Fixes nothing itself; it files notes for whoever owns the file |
| `/lanes:gu` | The weekly tool check: brings our own tools up to date on every PC, lists new releases of outside tools, feeds lessons into the tools, and freshens repo descriptions and front pages |
| `/lanes:ideas` | Files the ideas you jotted into your ideas repo (from the phone, from GitHub) word for word onto each project's page, so the project's next session shows them to you as a numbered list |
| `/lanes:menu` | **Menu-o-matiC and Move-o-matiC**: gets an app from its launch to where the work happens, and back out, by replaying a recorded route of key presses with checks along the way; Move-o-matiC records and replays walking and driving the same way. A replay costs almost nothing; Claude only looks when a check fails |
| `/lanes:bench` | **VR Bench**: the pretend headset plus pretend hands play a VR game, and a learning hour finds out how its head, hands and buttons behave with nobody wearing anything |
| `/lanes:setup` | This walk-through: your name for notes, this PC's name, and every optional tool above |
| `/lanes:update` | Checks for a newer Lanes, says in plain words what it adds, and updates it on your yes; also checks Hand Freeze, the simulator and VR Bench for newer versions |
| `/lanes:theme` | Puts on the plugin's look in Windows Terminal (an old green monitor with the Lanes banner faint behind the text), or puts your old look back |
| `/lanes:pt` | Tests the plugin itself against real work, from the installed copy, and writes only to the plugin's own repo |
| `/lanes:uninstall` | Takes Lanes off this PC in one go after showing what it will do, leaving your own work and the tools setup installed alone |
| the `lanes` skill | The short rulebook a session reads when it needs it: which session may edit which file, how to hand a finding to another lane, what a board tag means |

**Things that run by themselves**

| Feature | What it is for |
| --- | --- |
| **The close-out box** (`tools/handover.py`) | Printed at the end of every session: one headline word, SAVED or NOT SAVED, says whether everything on this PC is safely on GitHub, with a line per repo, the Inspector's count and what is still running. If it is red, type `/sp` |
| **The board summary and the guards** (hooks) | Every session opens with one line of what is queued; the guards stop two sessions of the same kind from working the same job, and stop a background helper writing where it must not |
| **Reminders for your other PC** (`tools/owed.sh`) | A job that can only be done on one particular PC (an install, a headset test) is addressed to that PC and greets only it, until it is done |
| **The Inspector** (`inspector = on`) | Looks over every piece of code a session writes and notes anything messy for you to decide on before it is uploaded |
| **Saved builds** (`tools/builds.py`, `builds =`) | Every version you install is kept as its own numbered build in a private repo, so any earlier one can be put back, and your other PC can use exactly the same one |
| **BeG0nE tools** (`begone/`, `begone =`) | Fault finders for VR mods. **Camera Jitter** logs when the head pose is read, when the camera is written and when the picture goes out, and says why a view feels stepped. **Ghost Hand** records your real hands, the game's hands and the weapon every frame and points at where they part (racking, grabbing, two-handed holds). **Occlusion Drift** is for two-handed aim drifting when one hand hides the other from the headset. A rider in the background files a short report after every headset run; with `begone_record = yes` the report comes with the recording cut frame by frame |
| **Session logs** (`tools/session-log.py`, `session_logs =`) | A dated plain-words summary of every session, one folder per project, in a private repo |
| **Thanks on GitHub** (`tools/thanks.py`, offered once) | Stars and follows, on your own GitHub account, the people whose tools, mods or findings your work uses, even one useful fact. Off unless you say yes |
| **Early summarising** (`tools/compact.py`, offered in setup) | Has Claude Code summarise a long conversation at about 40% full, after saving everything, so sessions stay sharp and cheaper |
| **New account set-up** (`tools/estate.py`, `docs/NEW-ACCOUNT.md`) | From a brand-new GitHub account to the whole working setup: the private board, ideas and builds repos, a copy for each kind of session, and the settings that point at them |
| **Extras you choose** (`tools/features.py`, 0.82.0) | Six built-in extras a new install switches on or off at setup: the green look, the "never say you are right before checking" rule, the BeG0nE recorders, blur and screen effects off in VR, the weekly tool check reminder, and keeping full conversation logs. A PC that had Lanes before 0.82.0 keeps them all on. `features.py on <name>` or `off <name>` changes one any time |
| **The Desktop shortcut** (`tools/shortcut.py`, offered once) | A **Lanes** icon that opens Claude Code in the plugin's look |
| **Proxy maker** (`tools/proxy-gen/`) | Makes the small logging file that is the first thing of ours a new game is tested with: it proves the game will load our code at all |
| **Shape and privacy checks** (`tools/code-shape-scan.py`, `tools/scrub-scan.py`) | One warns when a code file grows too big or hides its settings as bare numbers; the other stops anything private (names, paths, machine names) reaching a public repo |
| **Installed apps list** (`tools/installed.py`) | Each PC's note of which of our apps it has and which version, so neither PC plans work around something the other already did |
| **The superpowers skills** (offered once), by [Jesse Vincent (obra)](https://github.com/obra/superpowers) | Not ours: a set of working habits Claude follows, from Anthropic's official plugin list: think a job through before building, hunt a bug down step by step, check the work before calling it done. Lanes' Windows hook shim is adapted from it |

## 10. Our other public repos sessions read

| Repo | What it is for |
| --- | --- |
| [flat-to-vr-RE-toolkit](https://github.com/TefMeister/flat-to-vr-RE-toolkit) | The tested tools and the playbook for turning a flat game into VR: window capture, key and mouse sending, a virtual pad, quick .exe readers, shader readers, and `openxr-probe`, which checks a PC's VR runtime gives two eyes |
| [flat-to-vr-cross-engine-research](https://github.com/TefMeister/flat-to-vr-cross-engine-research) | One page per game engine of what is publicly known about putting it into VR, with every source credited (CC-BY-4.0) |
| [ai-game-control-profiles](https://github.com/TefMeister/ai-game-control-profiles) | How to operate each game by program: keys, menu routes, how to tell a menu from gameplay, and a `KNOWN.md` per game. Menu-o-matiC reads and adds to it |
| [BeG0nE](https://github.com/TefMeister/BeG0nE) | The home of the BeG0nE cures: each fault explained, each game's fix, and the reports and knowledge the tools gather |
| [terminal-themes](https://github.com/TefMeister/terminal-themes) | The retro green-monitor looks for Windows Terminal, including the one Lanes ships with |

---

**Credits:** every tool in sections 1 to 8, except those marked "(ours)", belongs to the people named
beside it. This file only points at them. If a link or a credit is wrong, open an issue and it will be
fixed.
