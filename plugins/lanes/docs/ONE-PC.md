# Lanes on one PC: the recommended setup (0.120.0)

Most people have one PC. The maintainer, 2026-11-21: *"most people don't have a 2 pc setup and if we can actually
make Lanes run like this, well organized on a single pc, then it's more useful to a lot more people"*. This is that
setup. Two PCs (`TWO-PCS.md`) is an extra on top of it, never a requirement.

## Three roles, one PC

One PC, several Claude Code windows, each doing one kind of job. The role follows from the command the window was
started with; the window says it in its first reply (`🧰 Developer — ...`).

| Role | Started with | Does | Never does |
| --- | --- | --- | --- |
| **Developer** | `/pd`, `/gr`, `/sr`, `/gd` | Builds, reads, researches, writes code that can be checked with no game running | Start a game or the headset |
| **Tester** | `/lm`, `/ms`, `/lanes:bench`, `/lanes:menu` | The only role that starts a game, the headset or VR Bench; reads what happened | Two games at once |
| **Keeper** | `/lanes:keeper`, `/fullscan` and its parts (`/gu`, `/od`, `/gs`, `/ch`) | Uploads, the front page, the index, the activity log, the weekly check-up | Write code, launch anything |

What keeps them from tripping over each other is already in Lanes:

- **The lane claim** (one game, one modding window): a Developer and a Tester on the same game at once is refused.
- **The clash guard** (§45): jobs that must not run together (two full scans, two saves of one folder) wait.
- **The full scan goes first** (§48): while it runs, the other windows finish their step, save and wait.
- **One writer per file**: the Keeper alone writes the front page, the index and the activity log.

## Saving: the Keeper in the background

Switch on the `keeper` extra with `keeper_mode = this_pc` (`/lanes:setup` does it when you answer "One PC"):

1. The Developer or the Tester commits as usual, then hands over: `python tools/parcel.py send <project>`
   (`--note "<one sentence>"` when something moved forward). The upload runs in the background on this PC.
2. A Keeper window opens by itself only when there is a job for it (a hand-over with news, a weekly job due,
   `keeper.py ask "<job>"`), does its round, and closes (`keeper.py close`). Nothing listens on a network.
3. Every write-up ends with the one light line from `parcel.py light`: "everything saved is on GitHub", or what waits.

## When a PC leaves

A second PC that is sold, wiped or moved to another GitHub account still has its last notes on the board, so the
PCs that stay keep printing its lines. On a PC that stays: `python tools/machine-name.py retire <its name>`. Its
files move to `<board>/retired/<name>-<date>/` (kept, never deleted), its name leaves `machines.txt`, and its
reminders still waiting are counted so they can be cleared or raised again.

## Checking it works

`docs/ONE-PC-TEST.md`, once after setup and after every Lanes update that touches the Keeper.
