# Lanes extras

Every extra below is optional: each PC switches it on or off (`features.py on|off <name>`). A new
install chooses at `/lanes:setup`; a PC that had Lanes before keeps what it had. Sets marked **best
together** are suggested as a pair. Written by `tools/features.py doc`; edit the list there, not here.

## Everyday helpers

Small things for every session. Each one works on its own.

- **The green look** (`theme`): puts the plugin's old-green-monitor look on this terminal; /lanes:theme restore undoes it. [Read more](https://github.com/TefMeister/lanes-plugin/blob/main/plugins/lanes/commands/theme.md)
- **Check before agreeing** (`talk_rule`): Claude never says "you are right" before checking what you said. [Read more](https://github.com/TefMeister/lanes-plugin/blob/main/plugins/lanes/hooks/talk-rule)
- **Use the tools, grow the tools** (`tools_rule`): Claude drives menus and tests with the tools this PC has (routes, VR Bench, BeG0nE, the live-game connectors) before doing it by hand, records what it learns, and adds a small tool or improvement whenever it does the same thing by hand twice. [Read more](https://github.com/TefMeister/lanes-plugin/blob/main/plugins/lanes/docs/PROTOCOL.md#33-use-every-tool-you-have-record-what-helps-grow-the-toolset-0850-2026-10-24)
- **Privacy guard** (`privacy_guard`): a git hook on this PC refuses any commit (and any gh issue, release or description) that carries the login name, a home-folder path or the e-mail address; public repos also never get machine names. [Read more](https://github.com/TefMeister/lanes-plugin/blob/main/plugins/lanes/docs/PROTOCOL.md#34-the-privacy-guard-no-login-no-home-paths-no-e-mail-on-github-0860-2026-10-25)
- **Games check at session start** (`games_check`): each session starts by checking this PC's project games against its record: a game a store updated (a mod may need a fix), one taken off or moved, a changed main program, a new project with no game set (tools/games.py overview lists every project and where its game is). [Read more](https://github.com/TefMeister/lanes-plugin/blob/main/plugins/lanes/tools/games.py)
- **Remote Control in every session** (`remote_control`): every Claude Code session on this PC starts with Remote Control on, so it can be watched and typed into from the Claude phone app, claude.ai/code or a session on your other PC; without it, /remote-control (or /rc) turns it on in one session. [Read more](https://github.com/TefMeister/lanes-plugin/blob/main/plugins/lanes/docs/PROTOCOL.md#35-remote-control-in-every-session-0870-2026-10-26)
- **Keep full conversation logs** (`keep_transcripts`): copies each conversation out of Claude Code's 30-day clean-up, kept on this PC only. [Read more](https://github.com/TefMeister/lanes-plugin/blob/main/plugins/lanes/docs/PROTOCOL.md#21-keep-conversations-short-an-earlier-summary-that-loses-nothing-0630-2026-10-13)

## Keeping your tools up to date (best together)

The reminder brings the weekly tool check round, and the test builds make sure an update it installs does not break what you build.

- **Weekly tool reminder** (`gu_nudge`): one line at session start when the weekly tool check (/lanes:gu) is a week old. [Read more](https://github.com/TefMeister/lanes-plugin/blob/main/plugins/lanes/docs/PROTOCOL.md#23-the-weekly-tool-check-lanesgu-0670-2026-10-14). Goes well with: Test builds before updates.
- **Test builds before updates** (`update_safety`): in the weekly tool check, an update that could break what you build (a compiler, Visual Studio, Python, Blender) is test-built first and put back if your work stops building. [Read more](https://github.com/TefMeister/lanes-plugin/blob/main/plugins/lanes/docs/PROTOCOL.md#31-test-build-before-keeping-an-update-0830-2026-10-23). Goes well with: Weekly tool reminder.

## The weekly check-up (best together)

Gold Digger keeps every run's logs on shelves, and the full scan reads them once a week together with the research, tool and tidiness checks.

- **Gold Digger shelves** (`gold_digger`): after every run, the game's logs and the BeG0nE reports are copied onto shelves (camera, guns, jitter, menus and so on) in your transfer folder, never deleted, so /lanes:gd can read them shelf by shelf and hand the new facts to the notes. [Read more](https://github.com/TefMeister/lanes-plugin/blob/main/plugins/lanes/commands/gd.md). Goes well with: Weekly full scan, Code health, Out of Date.
- **Weekly full scan** (`fullscan`): one line at session start when the weekly full scan (/lanes:fullscan: Gold Digger, research, the tool check, the tidiness pass, then save) is a week old. [Read more](https://github.com/TefMeister/lanes-plugin/blob/main/plugins/lanes/commands/fullscan.md). Goes well with: Gold Digger shelves, Code health, Out of Date.
- **Code health** (`code_health`): /lanes:ch re-reads your own tools with the Inspector on, saves a working copy to GitHub and a backup folder first, and tidies only what cannot change how they work; the weekly full scan runs it after the tool check. [Read more](https://github.com/TefMeister/lanes-plugin/blob/main/plugins/lanes/commands/ch.md). Goes well with: Gold Digger shelves, Weekly full scan, Out of Date.
- **Out of Date** (`out_of_date`): /lanes:od checks that everything you published on GitHub is as new as the work behind it (downloads older than their program, tools with no download, pages and descriptions behind) and brings it level; the weekly full scan runs it before the tool check. [Read more](https://github.com/TefMeister/lanes-plugin/blob/main/plugins/lanes/commands/od.md). Goes well with: Gold Digger shelves, Weekly full scan, Code health.

## For VR mods (best together)

One keeps the headset picture down to the gameplay, the other reports when that picture or the hands are not smooth, so its reports are about the mod and not about blur.

- **BeG0nE recorders** (`begone_ride`): a quiet helper that starts with every session and turns each headset test of a mod wired to it into a short report on jitter and hand faults. [Read more](https://github.com/TefMeister/BeG0nE). Goes well with: Gameplay only in VR.
- **Gameplay only in VR** (`vr_effects_off`): sessions switch off every blur and screen effect a game paints over the picture, such as motion blur, blood on the screen and the low-health tint. [Read more](https://github.com/TefMeister/lanes-plugin/blob/main/plugins/lanes/docs/PROTOCOL.md#19-gameplay-only-every-blur-and-screen-effect-off-in-vr-0600-2026-10-12). Goes well with: BeG0nE recorders.

## Recording the BeG0nE tests (best together)

One films the game during every BeG0nE headset test so each fault can be seen picture by picture, the other takes those videos off the PC again once nothing needs them.

- **Automatic BeG0nE recordings** (`begone_record`): OBS films the game's own window (never the screen) for the whole of every BeG0nE headset or pretend-headset test, and each report is cut at its faulty seconds as frames; needs the BeG0nE recorders and OBS. [Read more](https://github.com/TefMeister/lanes-plugin/blob/main/plugins/lanes/docs/PROTOCOL.md#26-the-recording-and-the-jitter-log-side-by-side-0760-2026-10-17). Goes well with: BeG0nE videos clean up after themselves.
- **BeG0nE videos clean up after themselves** (`begone_video_tidy`): the videos recorded beside a BeG0nE test are taken off the PC once nothing needs them: when the game is tested again on a later day, or after two weeks; the cut frames and the reports stay. [Read more](https://github.com/TefMeister/lanes-plugin/blob/main/plugins/lanes/docs/PROTOCOL.md#38-beg0ne-videos-clean-up-after-themselves-0900-2026-10-27). Goes well with: Automatic BeG0nE recordings.

## Our own apps and libraries

The other things we built for flat-to-VR work, each from its page on TefMeister's GitHub (tools/ours.py gets it). Each one is useful on its own.

- **Window View** (`ours_window_view`): hangs any desktop window (Hand Freeze, Hand Poser, a browser) inside any OpenXR game (Direct3D 11 and 12), see-through as you like, used with the mouse and keyboard (Page Up / Page Down) or the VR controllers while the game only hears the controllers, so a mod can be tuned without taking the headset off. [Read more](https://github.com/TefMeister/window-view-vr)
- **Hand Poser (untested)** (`ours_hand_poser`): a compact window of sliders that poses the player's fingers and wrists live in RE Engine games (needs REFramework): one box per finger, undo, autosave, named poses, one pose per gun. Inspired by alphaZomega's EMV Engine; not yet confirmed in a real headset session. [Read more](https://github.com/TefMeister/hand-poser-vr)
- **Grip Zones** (`ours_grip_zones`): a small window of sliders that moves and resizes every place the hand can grip a gun in VR (magazine, well, slide, pump or bolt, front grip), live on the gun, made to hang in the headset through Window View. Works with Visceral RE8 for now (Resident Evil Village VR); called Grab Zones until 2026-10-27. [Read more](https://github.com/TefMeister/grip-zones-vr)
- **CubeKit (Blender add-on)** (`ours_cubekit`): builds pixel-style models out of little cubes from a settings file: one cube size, pick any single cube, carved wear, stop-motion animation and export for GZDoom; made for the old-school shooter weapons and hands (Blender 4.2 or newer). [Read more](https://github.com/TefMeister/blender-cubekit)
- **Flat-to-VR RE toolkit** (`ours_re_toolkit`): the tested tools and the playbook for turning a flat game into VR: window capture and measuring, key, mouse and pretend-gamepad senders, shader readers that find the camera matrices, PE and export readers, and an OpenXR probe that checks the VR plumbing with no headset. [Read more](https://github.com/TefMeister/flat-to-vr-RE-toolkit)
- **Game control profiles** (`ours_control_profiles`): how to drive each game by program: recorded menu routes for Menu-o-matiC and Move-o-matiC and a KNOWN.md per game (each screen and the key past it, the controls that work, the hazards), so a session reaches gameplay without poking at keys. [Read more](https://github.com/TefMeister/ai-game-control-profiles)
- **Cross-engine VR library** (`ours_cross_engine_library`): what is publicly known about putting flat games into VR, one page per engine family (Unreal, RE Engine, id Tech, Dunia and more), with links to each project's own notes; the research lanes read it before searching the web. [Read more](https://github.com/TefMeister/flat-to-vr-cross-engine-research)
- **BeG0nE knowledge** (`ours_begone_knowledge`): the home of the BeG0nE tools: each VR fault explained (jitter, ghost hands, drifting two-handed aim, flickers), each game's fix, and what 200+ headset tests have taught so far; the recorders themselves already ship inside Lanes. [Read more](https://github.com/TefMeister/BeG0nE)
- **More terminal looks** (`ours_terminal_themes`): the other retro looks for Windows Terminal beside the green one Lanes ships with: the starburst monitor, the plain green monitor, sharp scanlines and more, each a small shader plus a colour scheme. [Read more](https://github.com/TefMeister/terminal-themes)

## Other people's tools

Downloads from other makers that help flat-to-VR work, each from its maker's GitHub (tools/outside.py gets it). Each one is useful on its own.

- **OpenXR OBS Mirror (by elliotttate)** (`outside_obs_mirror`): lets OBS record what the headset is shown, in Direct3D 11 and 12 OpenXR games and SteamVR; the BeG0nE recording then films the headset view beside the game window (the Resident Evil games included). [Read more](https://github.com/elliotttate/OpenXR-Layer-OBSMirror)
- **xrFPS (by elliotttate)** (`outside_xrfps`): turn a controller upside down in any OpenXR game to see the frame rate and frame times as a graph, inside the headset. [Read more](https://github.com/elliotttate/xrFPS)
- **OpenXR CAS (by elliotttate)** (`outside_openxr_cas`): sharpens the headset picture (AMD's FidelityFX CAS) and adjusts colour in any OpenXR game; changes what every test sees, so it is downloaded, not switched on. [Read more](https://github.com/elliotttate/OpenXR-CAS)
- **PIX MCP (by elliotttate)** (`outside_pix_mcp`): takes apart one captured frame of a Direct3D 12 game, draw by draw, through Microsoft PIX: which pass drew what, with which textures and numbers (the RE Engine games are Direct3D 12). [Read more](https://github.com/elliotttate/pix-mcp)
- **Nsight Graphics MCP (by elliotttate)** (`outside_nsight_mcp`): the same for NVIDIA's frame tool: capture a frame of a D3D11, D3D12 or Vulkan game and read every draw, resource and timing from it. [Read more](https://github.com/elliotttate/nsight-graphics-mcp)
- **vrframework guides (by elliotttate)** (`outside_vrframework`): a 17-part guide to making a flat game VR from the outside, built on REFramework and two of mutars' ports: frame timing, one eye per frame (AFR) and its smearing, per-eye projection, HUD, input. Read, not built: its code is a scaffold. [Read more](https://github.com/elliotttate/vrframework)
- **MelonMCP (by elliotttate)** (`outside_melon_mcp`): a live connection into Unity games through MelonLoader: inspect and change the running game, the Unity cousin of the RE Engine and UEVR connectors. [Read more](https://github.com/elliotttate/MelonMCP)
- **UEVR cutscene comfort (by elliotttate)** (`outside_uevr_comfort`): a UEVR plugin that puts the camera back after a cutscene by itself, and can show cutscenes on a still screen in the room, for Unreal games such as Silent Hill 2. [Read more](https://github.com/elliotttate/uevr-cutscene-comfort)
- **UEVR RenderDoc Capture (by elliotttate)** (`outside_uevr_renderdoc`): UEVR with RenderDoc built in: grab one real Direct3D 12 frame, flat or stereo, from an Unreal game and open it in RenderDoc. [Read more](https://github.com/elliotttate/UEVR-RenderDoc-Capture)
- **UEVR 6DOF window (by elliotttate)** (`outside_uevr_6dof_window`): a UEVR fork with a comfort mode that shows the game in a stereo window you can lean around, for games that are uncomfortable in full VR. [Read more](https://github.com/elliotttate/UEVR-6DOF-Window)
