# The plugin's look: green-monitor-starburst

An old green monitor: sharp letters with a soft glow, green glass, dark corners, a faint striped
starburst behind the text and a light that slowly runs down the screen. This is the style the lanes
plugin puts on the terminal the first time it runs after being installed (`tools/theme.py`,
`hooks/theme-apply`, `/lanes:theme`). It is a copy of the `green-monitor-starburst` style from the
[terminal-themes](https://github.com/TefMeister/terminal-themes) repo, where it is tuned and where the
other styles live.

| File | What it is |
| --- | --- |
| `starburst.hlsl` | the shader Windows Terminal runs over the window; every tuning number sits at its top with a comment |
| `starburst.png` | the picture behind the text (any picture works; the shader turns it green and striped) |
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
- The starburst and the icon are our own drawings, made in the spirit of the Claude logo; this is a
  fan-made look, **not** made by, endorsed by or connected to Anthropic.
- Style designed by TefMeister, written by Claude.

If we used your work and you are not credited here, or credited wrongly, please open an issue and we
will fix it as soon as possible.
