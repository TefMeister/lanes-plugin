# The plugin's look: green-monitor-lanes

An old green monitor: sharp letters with a soft glow, green glass, dark corners, and the Lanes banner
behind the text in a dim, striped green. It is still by default (since 2026-11-01); the moving version adds a light
that slowly runs down the screen, at the cost of a bit more of the PC. This is the style the lanes
plugin puts on the terminal the first time it runs after being installed (`tools/theme.py`,
`hooks/theme-apply`, `/lanes:theme`). It is a copy of the `green-monitor-lanes` style from the
[terminal-themes](https://github.com/TefMeister/terminal-themes) repo, where it is tuned and where the
other styles live.

| File | What it is |
| --- | --- |
| `lanes-still.hlsl` | the default shader Windows Terminal runs over the window: nothing moves, so the window is drawn again only when the text changes |
| `lanes.hlsl` | the moving version, with the rolling light; it never stops redrawing, so it uses a bit more of the processor and graphics card. Every tuning number sits at its top with a comment |
| `lanes.png` | the Lanes banner behind the text (any picture works; the shader turns it dim green and striped) |
| `profile-snippet.json` | the terminal profile and the RobCo colour scheme, for pasting by hand |
| `claude-theme-robco.json` | Claude Code's own theme: your messages on a hidden marker colour the shader turns yellow-green |
| `matrix-claude.png` | the tab icon |
| `ShareTechMono-Regular.ttf`, `OFL.txt` | the font and its licence |

It needs **Windows Terminal**; the shader is its experimental pixel-shader feature, which may change
or break in future updates. `theme.py restore` puts everything back; `theme = off` in `lanes.conf`
stops the first-run apply.

## Credits

- **Windows Terminal** (Microsoft) for the pixel-shader feature this is built on.
- **Share Tech Mono**, designed by **Ralph du Carrois / Carrois Type Design** (now Carrois Apostrophe),
  [carrois.com](https://www.carrois.com). Free under the SIL Open Font License 1.1; included unchanged
  with its licence, `OFL.txt`. "Share" is a Reserved Font Name of its creator.
- The Lanes banner and the icon are our own artwork, made in the spirit of the Claude logo; this is a
  fan-made look, **not** made by, endorsed by or connected to Anthropic.
- Style designed by TefMeister, written by Claude.

If we used your work and you are not credited here, or credited wrongly, please open an issue and we
will fix it as soon as possible.

`lanes.ico` (0.53.0) is `matrix-claude.png` as a Windows icon file, for the desktop shortcut `tools/shortcut.py` makes.
