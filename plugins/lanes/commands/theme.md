---
description: "(Theme) Puts the Lanes terminal look on, swaps it, or puts everything back the way it was."
---

`/lanes:theme` is the plugin's look: the `green-monitor-lanes` style from the
[terminal-themes](https://github.com/TefMeister/terminal-themes) repo, shipped inside the plugin so
everyone who installs it gets the same screen. It runs in **Windows Terminal** (the shader is its
pixel-shader feature); elsewhere it says so and changes nothing. **The banner is still by default** (since
2026-11-01, asked for by the maintainer to take load off the PC); the moving version, with a light slowly
running down the screen, is the alternative.

The tool is `python "${CLAUDE_PLUGIN_ROOT}/tools/theme.py"`; read its `--help` once. Print its
`THEME:` lines back to the user in plain words.

## What to do with the argument

- **no argument, or `status`** → `theme.py status`. Say whether the look is on, since when, and where
  the backup of the terminal's settings is.
- **`apply`** → `theme.py apply`. It changes only the terminal profile Claude Code is running in (or
  adds a "Green Monitor Claude" profile when this session is not in Windows Terminal), installs the
  Share Tech Mono font for this user, writes the RobCo theme for Claude Code and selects it. Every
  previous value is kept, and the terminal's settings file is backed up first. **A profile that
  already has a pixel shader is left alone**: say so, and that `apply force` replaces it.
- When the tool says it ADDED a tab type (the session was not inside Windows Terminal), tell the
  user in plain words: the plugin comes with one look; open Windows Terminal, click the small down
  arrow next to the + on the tab bar, pick "Green Monitor Claude"; it opens on the Desktop.
- **`apply force`** → `theme.py apply --force`. Only when the user asked for the replacement.
- **`animated`** → `theme.py motion animated`. Puts the moving light on. **Always pass on the tool's note in plain
  words:** the moving light makes Windows Terminal redraw the window about 60 times a second even when nothing
  changes, so it uses a bit more of the processor and graphics card than the still banner.
- **`still`** → `theme.py motion still`. Back to the still banner, the default.
- **`shortcut`** → `python "${CLAUDE_PLUGIN_ROOT}/tools/shortcut.py" create` (0.53.0). Puts a shortcut named
  **Lanes** on the Desktop that opens Claude Code in this look: Windows Terminal, the profile the look is on, the
  same font, colours and banner (still or moving, as the look is set), starting in the folder this session runs in (`--folder <dir>` for
  another). The first session after the look goes on offers it once by itself (hook `shortcut-offer`); after that
  only this command makes one. `shortcut remove` takes it away, `shortcut status` says where it is.
  `shortcut = off` in `lanes.conf` (or `LANES_SHORTCUT=0`) stops the offer.
- **`restore`** → `theme.py restore`. Puts the profile and Claude Code's theme back exactly as they
  were; the font and the backup stay.

## Say it plainly

- After `apply`: the terminal changes at once (Windows Terminal reloads its settings), and **Claude
  Code's own colours follow after a restart**. One sentence, plus how to undo it.
- `theme = off` in `lanes.conf` (or `LANES_THEME=0`) stops the first-session apply on a PC where it
  is not wanted.
- A PC that had the moving look from an earlier version is moved to the still one once, at session start, and told
  how to get the moving light back; a look the user picked since, or a moving light they chose, is never touched.
- The style, the shader's tuning numbers and the other styles live in the terminal-themes repo; a
  different picture goes in through `experimental.pixelShaderImagePath`, as its README says.

## Last step: give back the clash guard's lock

When this run ends, or stops early: `python "${CLAUDE_PLUGIN_ROOT}/tools/clash.py" release theme`. The clash
guard's hook took it when the run started, so nothing it must not run beside could start meanwhile (docs/CLASHES.md);
the session's end gives it back too. Inside `/lanes:fullscan` too (it is harmless when nothing is held).
