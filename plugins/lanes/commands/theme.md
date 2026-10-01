---
description: (Theme) The look the plugin ships with - an old green monitor, a faint starburst behind the text and a light rolling down the screen, in Windows Terminal. The first session after installing puts it on by itself; this command puts it on again, replaces a look you had before, or puts everything back the way it was. Safe beside every other lane.
---

`/lanes:theme` is the plugin's look: the `green-monitor-starburst` style from the
[terminal-themes](https://github.com/TefMeister/terminal-themes) repo, shipped inside the plugin so
everyone who installs it gets the same screen. It runs in **Windows Terminal** (the shader and the
rolling light are its pixel-shader feature); elsewhere it says so and changes nothing.

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
- **`restore`** → `theme.py restore`. Puts the profile and Claude Code's theme back exactly as they
  were; the font and the backup stay.

## Say it plainly

- After `apply`: the terminal changes at once (Windows Terminal reloads its settings), and **Claude
  Code's own colours follow after a restart**. One sentence, plus how to undo it.
- `theme = off` in `lanes.conf` (or `LANES_THEME=0`) stops the first-session apply on a PC where it
  is not wanted.
- The style, the shader's tuning numbers and the other styles live in the terminal-themes repo; a
  different picture goes in through `experimental.pixelShaderImagePath`, as its README says.
