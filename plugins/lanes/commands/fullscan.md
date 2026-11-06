---
description: "(Full scan) The weekly check-up in one go: Gold Digger, research, Out of Date, tool check, code health, tidiness, save."
---

`/fullscan` — **everything checked and brought up to date, in one go.** Asked for by the maintainer, 2026-10-26:
*"can we now bring together all the health check stuff like /gs, /gr, /sr, /gu, /gd and /sp have it as one command to
go through everything in one go ... these slash commands still have to be available separately as well of course"*;
the name chosen the same day. PROTOCOL §36.

**The habit: once a week**, on either PC, but never two runs at once anywhere (step 0b). A session-start line says when
it has been 7 days on this PC. Never run it unasked. It costs a lot (research is the biggest part), and it needs no game and no person: a good one to start
before leaving the PC.

Argument: `$ARGUMENTS` — optional. `skip:<part>` leaves a part out (`skip:gr`); a project name narrows the research
and Gold Digger parts to that project.

## 0. Rules

- **Never launch, drive or close an app**, in any part.
- **Each part keeps its own rules and its own clone root**, exactly as when it runs alone. This command only sets the
  order. Parts run one after another, never side by side, so two parts never share a tree at the same moment.
- **Run each part by following its own command**, through the Skill tool: the person's own short command when this
  PC has one (`/gd`, `/gr`, `/sr`, `/od`, `/gu`, `/ch`, `/gs`, `/sp`), otherwise the plugin's (`lanes:gd`, `lanes:gr`,
  `lanes:sr`, `lanes:od`, `lanes:gu`, `lanes:ch`, `lanes:gs`). A part that is not set up on this PC is skipped with one line saying so.
- **Questions wait until the end.** No part stops to ask mid-run; the weekly tool check's tick-box install question
  is asked last (step 7), so the person can leave the PC for the whole run.
- **A part that fails is reported and the run carries on** with the next part. It never retries in a loop.
- Between parts, one plain line saying which part is starting, so a person glancing at the screen knows where it is.

## 0b. Which PC, and only one run at a time (0.101.0)

When `python "${CLAUDE_PLUGIN_ROOT}/tools/features.py" is-on clash_guard` says on (exit 0), before anything else
(the clash guard, `tools/clash.py`; its hook has usually taken the lock already when the command was typed):

1. `python "${CLAUDE_PLUGIN_ROOT}/tools/fullscan_lock.py" here`. Exit 1 (only when `fullscan_here = no` on this PC): print
   its one line to the person and **stop the whole run**. Nothing else is done.
2. `python "${CLAUDE_PLUGIN_ROOT}/tools/clash.py" take fullscan`. Exit 1: another full scan, or one of its parts, is
   running on this PC or the other (or GitHub could not be reached to check): print its line and **stop**. Exit 0: the
   run is claimed on GitHub. The parts below run inside this session, so the guard lets them through.
3. **Give it back at the very end** (after step 8), and also whenever the run stops early for any reason:
   `python "${CLAUDE_PLUGIN_ROOT}/tools/clash.py" release fullscan`. The session's end gives it back too, and a claim
   that is never given back counts as left over after 12 hours, so a cut-off run blocks the next one for at most that long.

## 1. Save check first

`python "${CLAUDE_PLUGIN_ROOT}/tools/handover.py" close`. If this PC is NOT SAVED, save that work first (the
person's `/sp`, or commit and push in the lane root that holds it), so later parts start from GitHub's state. Note what
the other PC last reported.

## 2. Shelve

`python "${CLAUDE_PLUGIN_ROOT}/tools/gd.py" shelve --all`, then `gd.py list`. Anything a run left behind is on a shelf
before anything reads it.

## 3. Gold Digger (`/gd`)

Read every game with waiting items, shelf by shelf. It goes first so its findings are in the inboxes before the
research parts read the notes.

## 4. Research for each project (`/gr`), then the shared library (`/sr`)

Whole estate (or the named project), with each command's own tiers, so quiet projects get a short check-in.

## 4b. Out of Date (`/od`)

Added 2026-10-27 (the maintainer: *"it must run before /gu ... and then add this function to the /fullscan as well so
our github will always be shiny and has the latest stuff"*). Everything we published on GitHub is brought level with
the work behind it: downloads older than their program are rebuilt, tested and published, tools with no download get
one, descriptions, front pages, the catalog and skills pages are brought up to date, and a tool Lanes does not offer
yet is added. It needs no question (publishing our own tested tools is allowed), so it runs fully here; it goes
before the tool check so a download it publishes is already there for `/gu` to offer. Skipped with one line when
`features.py is-on out_of_date` says off.

## 5. The tool check (`/gu`): LOOK ONLY

Run it up to, but not including, its install question. Keep its list of installs and updates, each with its
"could break" line, for step 7. Pulls of our own clones and pushes of our own tool work need no question and happen here.

## 5b. Code health (`/ch`)

Added 2026-10-27 (the maintainer: *"please make a slash command /ch for Code health and also add this slash command
to the /fullscan function"*). It runs right after the tool check, in the same clone root, never beside it. Its own
rules hold: the working copy is saved first (`ch.py backup`), only changes that cannot alter behaviour are made, the
tests must pass after them, everything structural becomes a board row. Its questions (removing old plugin versions,
installing ruff and vulture) wait for step 7 with the rest. Skipped with one line when `features.py is-on code_health`
says off.

## 6. Tidiness pass (`/gs`)

Read-only, as always. It runs after everything above so it checks what this run wrote too.

## 7. Save, then the questions

1. Save everything: the person's `/sp` if this PC has it, otherwise commit and push each lane root's own work.
2. Ask the tool check's install question, with code health's questions after it, in its full shape (`/gu`'s rules, "The shape of that question"): first a
   plain numbered list of every update, each with what is in it, where it downloads from and what it could break; then
   the tick boxes, **"Everything" first**, then one per update. It covers every tool with a newer version: this plugin,
   our own apps, outside tools and connectors from other makers, installed Claude Code plugins and skills, PC programs
   and Python packages. Install what is ticked, with the test builds `/gu` uses. If nothing needs installing, say so
   and ask nothing.
3. Stamp the run: `python "${CLAUDE_PLUGIN_ROOT}/tools/gd.py" fullscan-done` and `python
   "${CLAUDE_PLUGIN_ROOT}/tools/gu.py" done` and `python "${CLAUDE_PLUGIN_ROOT}/tools/ch.py" done`.

## 8. Report

The close-out box first, then one short block per part, a line or two each: what it found, what it fixed, what it
left for a person. Anything that needs the person goes in the last section.
