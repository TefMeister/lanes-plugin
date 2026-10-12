# Ghost Hand BeG0nE

A tool that finds and removes the gaps between your real hand and the player's hand in virtual reality, part of
BeG0nE: tools that remove unwanted things from video games, for modders and gamers alike.

## The problem

In a VR mod, the hand you see in the game should be exactly where your real hand is, and do exactly what it did.
Often it is not quite there. It lags behind, sits off to one side, or jumps. A gesture made by hand then misses:
a slide that does not finish racking, a grab that does not catch, a two-handed hold that slips. That gap is the
**ghost hand**. Without numbers, nobody can tell whether a gesture is impossible to get right or just set up
wrong.

## The cure

**First, measure it.** While a game runs in VR, Ghost Hand records, every frame:

- where both controllers really are, and the distance between them;
- where the game draws each hand, and the weapon and its moving parts (slide, pump, magazine);
- the buttons pressed, if they matter for the gesture;
- what the mod decided at each moment ("grabbed", "80% back", "finished").

It then marks the moments that went wrong: sudden jumps, the game's hand falling behind the real one, the real
pull being longer than the measured one, a limit that was never reached. Each attempt at a gesture becomes one
line: what your hand did, what the game thought it did, and where the two parted.

**Then, fix it**, per game, from what the numbers show. If they show a gesture cannot be made reliable, that is
an answer too, and the game keeps a button for it.

## Where it stands

Planned (2026-10-12). Not built yet. First use: Resident Evil 2 (Visceral), hand racking of the pistol slide,
to find out whether it can be made accurate enough for combat.

## What it is, and what it is not

- **It is** a measuring tool for VR mods, and later small per-game fixes built from what it measures.
- **It is not** a VR mod by itself.
- **It contains** no game files, only our own code.

## For modders: wiring it in

Copy `ghosthand.lua` next to the mod's script (REFramework: `reframework/autorun/`). Its header lists every call.
In short: `gh.init(<project>, <runtime>)` at load; `gh.vr_on()` / `gh.vr_off()` with the headset session; every
frame `gh.real(side, tracked, x, y, z)` for each controller, `gh.game(side, x, y, z)` for each hand the game draws,
`gh.part(name, ...)` for moving weapon parts, `gh.value(name, v)` for what the mod measured, then `gh.frame()`.
Around each gesture: `gh.event("rack", "start")` and `gh.event("rack", "done"|"fail"|"cancel")`, and once
`gh.value("rack_need", <metres>)` so a miss can be judged. All positions in the same space (game world, metres).

`python ghost_hand_check.py selftest` checks the reader on made-up sessions with known faults.
