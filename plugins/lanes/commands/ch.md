---
description: (Code health) A careful re-read of our own tools - the plugin, the BeG0nE tools, the o-matiC tools and the rest - with the Inspector on, tidying only what cannot change how they work. A working copy of everything is saved to GitHub and to a backup folder first. Never launches anything.
---

`/ch` — **Code health: re-read our own tools and tidy them without breaking what works.** Asked for by the
maintainer, 2026-10-27: *"it's been months of adding stuff and maybe a complete re-read of the code is in order, but at
the same time i hope this is not going to break things that actually work right now, so please save a working copy of
everything just in case something goes wrong"*; then, after the first pass, *"please make a slash command /ch for Code
health and also add this slash command to the /fullscan function"*. PROTOCOL §37.

Argument: `$ARGUMENTS` — optional. A repo name (`/ch BeG0nE`) to look at only that one. Empty looks at every repo
`ch.py repos` lists.

**The habit:** it is part of the weekly `/fullscan`. Alone, whenever tools have had a busy week.

## 0. Rules

- **Never launch, drive or close an app.** Everything here is reading and editing code, and running tests.
- **Work in the tool-check clone root** (the one `ours =` points into, `github-backups-gu\` on the maintainer's PCs),
  never in a lane root another session uses. Never run beside `/gu`, which uses the same root. Pull every repo first.
- **Save the working copy before the first change, every time:** `ch.py backup`. It must end "Every repo saved."
  If it does not, fix that first and change nothing until it does.
- **Only change what cannot change how a tool behaves.** Allowed: an import nothing uses; a function, setting or
  variable that `ch.py scan` lists as having no caller anywhere (it already counts tests, docs and commands);
  text that names a command or file that no longer exists; a twin copy brought up to its newer side; a frozen copy
  moved into the repo's `archive/` once its own "stays until" condition is met. **Never delete: move to `archive/`
  with a line in its README.**
- **Everything else is a board row, not a change:** splitting a long file or function, merging duplicate helpers,
  renaming, wiring in a setting that was planned and never used, behaviour fixes. Write it as a `fix later` with the
  reason, so a session can do it on its own and test it.
- **A setting named but never read is a lead, not dead code.** It may be a safety limit that was planned and never
  wired in (VR Bench's per-stage time limit was one). Never delete it; give it a board row.
- **Run the repo's tests after the changes** (the plugin: `tools/tests/smoke-test.sh` and the Python tests beside the
  tools). A failing test means the change that caused it goes back, at once.
- **The Inspector is on for every change** (the edit hook), and answered before the end (step 5).

## 1. Pull and save the working copy

```
python "${CLAUDE_PLUGIN_ROOT}/tools/ch.py" repos
python "${CLAUDE_PLUGIN_ROOT}/tools/ch.py" backup
```

`git pull` each repo listed, then `backup`: a `pre-ch-<date>` tag in each, pushed to GitHub, and a bundle of each
repo's whole history in the backup folder. To put a repo back: `git reset --hard pre-ch-<date>` in its clone (only
with the maintainer's yes), or clone the bundle.

## 2. The look

```
python "${CLAUDE_PLUGIN_ROOT}/tools/ch.py" scan
python "${CLAUDE_PLUGIN_ROOT}/tools/inspector.py" review <repo>     # once per repo
```

`scan` lists possible errors and unused imports, code with no caller left anywhere, settings named but never read,
twin copies that drifted apart (the same `twin =` lines `/gu` uses), and leftovers on this PC (old cached plugin
versions, stray files among the commands). Without ruff and vulture it says so: offer `pip install ruff vulture`
among the questions at the end. The Inspector's full review writes every finding into the repo's inspector notes.

**Read before changing.** For each "no caller" line, look at the code: a hit can still be wrong (a name built at
run time, a function a person runs by hand). For each drifted twin, diff both sides and take the newer one's change
across, rewriting the display name as the copy does.

## 3. Tidy

Make the allowed changes from step 2, one repo at a time, smallest first. Keep two copies of one tool identical
(change both, or let the twin check show which one is the master). Commit each repo on its own with a message that
says what went and why it could not change behaviour.

## 4. Test

Run each repo's tests. All must pass as they did before the changes. A failure: put that change back, note it.

## 5. Answer the Inspector

Every finding the review raised gets a verdict (`fix now` only for the kinds that cannot change behaviour; `fix
later: <board row>`; or `keep: <why>`), the way the Inspector's README says. Duplicates against a frozen or archived
copy are `keep`. Repeated helpers across tools that each have to run on their own are `keep`; a real shared helper
worth making is `fix later`.

## 6. Leftovers on this PC

Old cached plugin versions and stray files are **listed, never removed without a yes**: they go into the questions
at the end. With a yes, old plugin versions beyond the newest two are moved into the backup folder (not deleted), and
stray command files likewise.

## 7. Save and report

Commit and push each repo, release the plugin if it changed (`tools/release.sh`), then
`python "${CLAUDE_PLUGIN_ROOT}/tools/ch.py" done`. Report in plain words: what went, what was kept and why, the board
rows written, the tests run and their result, and the backup tag. Questions (installs, PC leftovers) go last.
