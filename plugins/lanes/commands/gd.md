---
description: (Gold Digger) Reads what earlier runs left on the shelves - game logs, mod logs, BeG0nE reports - one shelf at a time, folds the repeats away, and hands every new fact to the notes, boards and tools it belongs to. Never launches anything, never deletes anything. Safe beside every other lane.
---

`/gd` — **Gold Digger: find the few useful lines in a mountain of logs.** Asked for by the maintainer, 2026-10-24
(*"there must be a way to save the useful stuff and discard the repeated and other junk"*) and shaped on 2026-10-26
(*"categorizin and "shelving" all the collected data after each run ... so that the actual /gd can more systematically go
through all this, instead of being dropped into a sea of information"*). PROTOCOL §36.

Argument: `$ARGUMENTS` — optional. A game name to read only that game; a game and a shelf (`alice camera`) to read
only that shelf. Empty reads every game with something waiting.

## 0. How the data gets here (nothing for you to do)

Every run's leftovers are **shelved** without a model: `tools/gd.py shelve` copies a game's logs and new BeG0nE
reports onto shelves (camera, jitter, hands, guns, first-person, enemies, menus, hud, sound, crashes, performance,
logs, other) in the Gold Digger folder (`gd.py where`; the synced transfer folder, so both PCs see everything). The
session hooks do it at the start and end of every session, and `/lm` and `/ms` do it right after closing a game. A
game's places are set once per PC with `gd.py sources <game> add <glob> [<shelf>]`; a session that finds a log the
list does not have adds it.

## 1. Rules

- **Never launch, drive or close an app.** Everything here is reading files.
- **Never delete or edit anything on the shelves.** The shelves are the record. Reading an item is marked with
  `gd.py sifted`, nothing else changes. Folding repeats happens in what you read, never in the files.
- **Write only through the doors that are safe beside every lane:** create-only files in a project's
  `engine-research/inbox/` (the modding lane folds them in at its next start), the game's `KNOWN.md` in the routes
  repo (driving facts), and create-only inbox files for tools that keep one (BeG0nE's `ideas/`, the toolkit). Never
  edit a project's board, dossier or notes directly from here.
- **Clone root: `gd_root =` in lanes.conf**, else a root of its own beside the others (`github-backups-gd`, made with
  `git clone --local` from the main root the first time). Never work in another lane's root. Pull before reading.
- **Nothing new, nothing written.** A shelf that taught nothing gets marked read and one line in the report.

## 2. Look

```bash
python "${CLAUDE_PLUGIN_ROOT}/tools/gd.py" list            # per game and shelf: how many wait
python "${CLAUDE_PLUGIN_ROOT}/tools/gd.py" unsifted <game> <shelf>
```

Pick the game with the most waiting (or the one named). Read that game's board row, its dossier's latest sections and
its `KNOWN.md` first, so you know what is already known: Gold Digger is worth something only when it finds what the
notes do not already say.

## 3. Read one shelf at a time

For each waiting item on the shelf, oldest first:

```bash
python "${CLAUDE_PLUGIN_ROOT}/tools/gd.py" fold <item>                       # repeats folded, warnings marked W
python "${CLAUDE_PLUGIN_ROOT}/tools/gd.py" fold <item> --against <older item from the same place>   # only what is new
```

Use `--against` whenever an older item from the same place exists (the index's `from` column): across runs is where
the gold is. Look for:

- **errors and warnings** (`W`), above all ones the notes do not mention, or one that started in a certain run;
- **first-time lines**: a feature that switched on, a setting the game read, a file it could not find;
- **numbers that drift** between runs (a frame time, a count, an address);
- **menus and screens** that changed (for `KNOWN.md`);
- a BeG0nE report: read the report, never the raw numbers (PROTOCOL §20).

Items listed with `also: <shelf>` are read once, from their own shelf, and their lines for the other shelf are noted
there too.

## 4. Hand over what is new

Per finding, one destination, never two copies:
- engine or mod behaviour → `engine-research/inbox/YYYY-MM-DD-gd-<slug>.md` in the game's repo, tagged
  (`[measured YYYY-MM-DD]` from a log line, quoted with the shelf item's name), with a proposed board row if it is work;
- how to drive the game (a screen, a key, a hazard) → that game's `KNOWN.md`;
- a lesson for a tool → that tool's inbox, or a dated line under `## Tool ideas` in `KNOWN.md`.

Then mark the shelf read: `gd.py sifted <game> <id>...` (or `--shelf <shelf>` when every item on it was read).
Commit only the files you wrote, `git pull --rebase`, push.

## 5. Report

Short and plain: per game, which shelves were read, and the few things found (or "nothing new"). Then the close-out box.
