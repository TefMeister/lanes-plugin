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
- **Remote Control in every session** (`remote_control`): every Claude Code session on this PC starts with Remote Control on, so it can be watched and typed into from the Claude phone app, claude.ai/code or a session on your other PC; without it, /remote-control (or /rc) turns it on in one session. [Read more](https://github.com/TefMeister/lanes-plugin/blob/main/plugins/lanes/docs/PROTOCOL.md#35-remote-control-in-every-session-0870-2026-10-26)
- **Keep full conversation logs** (`keep_transcripts`): copies each conversation out of Claude Code's 30-day clean-up, kept on this PC only. [Read more](https://github.com/TefMeister/lanes-plugin/blob/main/plugins/lanes/docs/PROTOCOL.md#21-keep-conversations-short-an-earlier-summary-that-loses-nothing-0630-2026-10-13)

## Keeping your tools up to date (best together)

The reminder brings the weekly tool check round, and the test builds make sure an update it installs does not break what you build.

- **Weekly tool reminder** (`gu_nudge`): one line at session start when the weekly tool check (/lanes:gu) is a week old. [Read more](https://github.com/TefMeister/lanes-plugin/blob/main/plugins/lanes/docs/PROTOCOL.md#23-the-weekly-tool-check-lanesgu-0670-2026-10-14). Goes well with: Test builds before updates.
- **Test builds before updates** (`update_safety`): in the weekly tool check, an update that could break what you build (a compiler, Visual Studio, Python, Blender) is test-built first and put back if your work stops building. [Read more](https://github.com/TefMeister/lanes-plugin/blob/main/plugins/lanes/docs/PROTOCOL.md#31-test-build-before-keeping-an-update-0830-2026-10-23). Goes well with: Weekly tool reminder.

## The weekly check-up (best together)

Gold Digger keeps every run's logs on shelves, and the full scan reads them once a week together with the research, tool and tidiness checks.

- **Gold Digger shelves** (`gold_digger`): after every run, the game's logs and the BeG0nE reports are copied onto shelves (camera, guns, jitter, menus and so on) in your transfer folder, never deleted, so /lanes:gd can read them shelf by shelf and hand the new facts to the notes. [Read more](https://github.com/TefMeister/lanes-plugin/blob/main/plugins/lanes/commands/gd.md). Goes well with: Weekly full scan, Code health.
- **Weekly full scan** (`fullscan`): one line at session start when the weekly full scan (/lanes:fullscan: Gold Digger, research, the tool check, the tidiness pass, then save) is a week old. [Read more](https://github.com/TefMeister/lanes-plugin/blob/main/plugins/lanes/commands/fullscan.md). Goes well with: Gold Digger shelves, Code health.
- **Code health** (`code_health`): /lanes:ch re-reads your own tools with the Inspector on, saves a working copy to GitHub and a backup folder first, and tidies only what cannot change how they work; the weekly full scan runs it after the tool check. [Read more](https://github.com/TefMeister/lanes-plugin/blob/main/plugins/lanes/commands/ch.md). Goes well with: Gold Digger shelves, Weekly full scan.

## For VR mods (best together)

One keeps the headset picture down to the gameplay, the other reports when that picture or the hands are not smooth, so its reports are about the mod and not about blur.

- **BeG0nE recorders** (`begone_ride`): a quiet helper that starts with every session and turns each headset test of a mod wired to it into a short report on jitter and hand faults. [Read more](https://github.com/TefMeister/BeG0nE). Goes well with: Gameplay only in VR.
- **Gameplay only in VR** (`vr_effects_off`): sessions switch off every blur and screen effect a game paints over the picture, such as motion blur, blood on the screen and the low-health tint. [Read more](https://github.com/TefMeister/lanes-plugin/blob/main/plugins/lanes/docs/PROTOCOL.md#19-gameplay-only-every-blur-and-screen-effect-off-in-vr-0600-2026-10-12). Goes well with: BeG0nE recorders.
