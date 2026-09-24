# Optional tools: the catalog `/lanes:setup` walks through

Every tool below is **optional**. The lanes themselves need only Git and Bash. The rest are tools
these lanes have actually used on reverse-engineering and modding projects, grouped by what they let
a session do. `/lanes:setup` goes through them one group at a time. For each missing tool it offers
three choices: **Claude installs it**, **you install it yourself** from the official link below, or
**skip**.

Rules for every entry:
- **Official sources only.** A link here is the project's own site or its own GitHub. Never a
  mirror or a download aggregator.
- **The "Claude installs it" command** is what the session runs, shown to you before it runs. Most
  use `winget`, Windows' own package manager. Anything that needs administrator rights says so,
  because Windows will ask you to approve it.
- **"How to check"** is what `tools/setup-scan.py` looks for. A tool counts as present only when
  that check passes.
- Links and steps were checked on 2026-09-17. Projects move; if a step no longer matches the
  project's own README, the README wins.

---

## 1. Core: working with the repos

| Tool | What it lets a session do | Official link | Claude installs it | How to check |
| --- | --- | --- | --- | --- |
| **Git for Windows** (includes Git Bash) | Every lane: pull, commit, push. The board tools run in Bash | https://git-scm.com/download/win | `winget install --id Git.Git -e` | `git --version` |
| **GitHub CLI** | Create repos, releases and issues from the session | https://cli.github.com/ | `winget install --id GitHub.cli -e`, then **you** run `! gh auth login` (it opens a browser) | `gh auth status` |
| **Python 3.12** | Every helper script: scans, captures, input, PE reading | https://www.python.org/downloads/windows/ | `winget install --id Python.Python.3.12 -e` | `python --version` works (not the Microsoft Store stub) |
| **Python packages** | `pefile` (read .exe/.dll), `capstone` (disassemble), `pillow` (screenshots), `psutil` + `pywin32` (find and drive windows), `numpy` | https://pypi.org/ | `python -m pip install pefile capstone pillow psutil pywin32 numpy` | `python -c "import pefile, capstone, PIL, psutil, win32gui, numpy"` |
| **uv** | Runs Python-based MCP servers such as Blender MCP (`uvx …`) | https://docs.astral.sh/uv/ | `winget install --id astral-sh.uv -e` | `uvx --version` |
| **7-Zip** | Unpack tool releases and archives | https://www.7-zip.org/ | `winget install --id 7zip.7zip -e` | `7z` in `C:\Program Files\7-Zip\` |

## 2. Building mod code

| Tool | What it lets a session do | Official link | Claude installs it | How to check |
| --- | --- | --- | --- | --- |
| **llvm-mingw** | Build proxy DLLs and small test programs, 32- and 64-bit (`tools/proxy-gen`) | https://github.com/mstorsjo/llvm-mingw/releases | `winget install --id MartinStorsjo.LLVM-MinGW.UCRT -e` | `x86_64-w64-mingw32-clang --version` |
| **CMake** | Configure C++ plugin builds | https://cmake.org/download/ | `winget install --id Kitware.CMake -e` | `cmake --version` |
| **Visual Studio 2022 Build Tools** (C++ workload) | Build MSVC-only plugins (for example REFramework native plugins) | https://visualstudio.microsoft.com/downloads/ (under "Tools for Visual Studio") | `winget install --id Microsoft.VisualStudio.2022.BuildTools -e --override "--add Microsoft.VisualStudio.Workload.VCTools --includeRecommended --passive"`. **Needs admin; about 6 GB** | `vswhere` finds a VC tools install |
| **Rust (rustup)** | Build Rust tools from source, such as Ghidrust | https://rustup.rs/ | `winget install --id Rustlang.Rustup -e` | `cargo --version` |
| **Lua 5.4** | `luac -p` syntax-checks game Lua scripts before deploying them | https://www.lua.org/download.html | `winget install --id DEVCOM.Lua -e` | `luac -v` |

## 3. Reverse engineering

| Tool | What it lets a session do | Official link | Claude installs it | How to check |
| --- | --- | --- | --- | --- |
| **x64dbg** | Read a running program: breakpoints, memory, registers | https://x64dbg.com/ | `winget install --id x64dbg.x64dbg -e` | `x64dbg.exe` in the winget package's `release\x64\` |
| **x64dbg-automate** (plugin + Python client + MCP server) | Drive x64dbg from a session; gives Claude its x64dbg tools | https://github.com/dariushoule/x64dbg-automate · client docs https://dariushoule.github.io/x64dbg-automate-pyclient/installation/ | `python -m pip install x64dbg-automate`, then put the plugin release files in x64dbg's `release\x64\plugins\` as its install page says; then `claude mcp add --scope user x64dbg --env X64DBG_PATH=<path to x64dbg.exe> -- x64dbg-automate-mcp` | `x64dbg-automate.dp64` in the plugins folder; `x64dbg` in `claude mcp list` |
| **x64dbg-skills** (Claude Code plugin) | Ready-made debugger workflows: state snapshots, tracing, decompiling | https://github.com/dariushoule/x64dbg-skills | `claude plugin marketplace add dariushoule/x64dbg-skills`, then `claude plugin install x64dbg-skills@x64dbg-skills` | in `claude plugin list` |
| **Ghidrust** (+ its MCP server) | Read a compiled .exe with no program running: functions, strings, cross-references, **decompile to C** | https://github.com/oofz/Ghidrust (Apache-2.0, by oofz) | needs Git + Rust: `git clone https://github.com/oofz/Ghidrust %USERPROFILE%\Tools\Ghidrust`, then `cargo build --release` in that folder (several minutes); then `claude mcp add --scope user ghidrust -- %USERPROFILE%\Tools\Ghidrust\target\release\ghidrust.exe mcp` | `ghidrust` in `claude mcp list` and the exe exists |

## 4. Driving an app unattended

| Tool | What it lets a session do | Official link | Claude installs it | How to check |
| --- | --- | --- | --- | --- |
| **ViGEmBus** (virtual gamepad driver) | Send controller input to games that ignore the keyboard | https://github.com/nefarius/ViGEmBus/releases (archived by its author in 2023, still works) | `winget install --id ViGEm.ViGEmBus -e`. **Needs admin (a driver)** | Windows service `ViGEmBus` is running |
| **vgamepad** (Python) | The Python side of ViGEmBus | https://pypi.org/project/vgamepad/ | `python -m pip install vgamepad` | `python -c "import vgamepad"` |

## 5. 3D and assets

### Blender + Blender MCP: step by step

**What it gives you:** Claude can build and change 3D scenes in a running Blender (models, materials,
renders), for things like weapon remakes and reference props.

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

| Tool | What it lets a session do | Official link | Claude installs it | How to check |
| --- | --- | --- | --- | --- |
| **RE Mesh Editor** (Blender add-on) | Import and export RE Engine meshes | https://github.com/NSACloud/RE-Mesh-Editor (archived, GPL-3.0) | manual: download the release zip, then Blender → Add-ons → Install from Disk | listed in Blender's add-ons |

## 6. VR

| Tool | What it lets a session do | Official link | Claude installs it | How to check |
| --- | --- | --- | --- | --- |
| **SteamVR** | OpenVR/OpenXR runtime for PC VR | https://store.steampowered.com/app/250820/SteamVR/ | **you**, through Steam | installed in Steam |
| **Virtual Desktop** (Quest headsets) | Streams PC VR to a Quest wirelessly, with its own OpenXR runtime. **Paid app** on the headset; the PC Streamer is free | https://www.vrdesktop.net/ | **you**: buy on the headset's store, install the Streamer from that site | `VirtualDesktop.Streamer` running |

## 7. Per-game frameworks (install into one game, only when that game needs it)

These go **into a game's folder**, so a session installs them only as part of that game's own work,
never from `/lanes:setup`. Links are here so they are all in one place.

| Framework | For | Official link |
| --- | --- | --- |
| **REFramework** | RE Engine games (Resident Evil 2/3/4/7/Village, …): Lua scripting, VR, native plugins | https://github.com/praydog/REFramework · dev builds https://github.com/praydog/REFramework-nightly/releases |
| **UEVR** | Unreal Engine 4/5 games: universal VR | https://uevr.io/ · https://github.com/praydog/UEVR |
| **ree-pak-rs** | Extract RE Engine `.pak` archives | https://github.com/eigeen/ree-pak-rs (MIT) |
| **REMSG_Converter** | Convert RE Engine text files to editable formats and back | https://github.com/dtlnor/REMSG_Converter (MIT) |

---

**Credits:** every tool above belongs to its authors. This file only points at them. If a link or a
credit is wrong, open an issue and it will be fixed.
