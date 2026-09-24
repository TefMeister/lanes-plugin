---
description: (Gate board) Prints every project's open work grouped by what it REQUIRES - work that needs nothing running, work that needs you, work that needs the app, work that needs special hardware. Read-only, reads origin/main, safe beside every other session type.
---

`/gates` — **the board**. It answers one question: *what can I do right now, and in which mode?*

Read-only. It writes nothing, launches nothing, and needs no clone of its own.

## Run it

```bash
bash "${CLAUDE_PLUGIN_ROOT}/tools/gate-scan.sh"
```

It finds the board repo from `$LANES_BOARD`, or from `board = <path>` in `~/.claude/lanes.conf`,
or from the current directory if that is itself a board clone. Pass the path as an argument to
override all of it.

Print the output verbatim. Do not summarise it, and do not re-order it — the ordering **is** the
recommendation: cheapest mode first.

## One machine, one list, one next task

The estate-wide board is still there, but the day-to-day interface is narrower — most people work
**one task at a time**, and each machine has its own list.

```
gate-scan.sh --next               # THE single next task for this machine
gate-scan.sh --next --tag FLAT    # ... restricted to one gate
gate-scan.sh --mine               # everything this machine can do
gate-scan.sh                      # the whole estate
```

**Lead with `--next` unless the user asks for the wide view.** It picks the cheapest gate first
(`PD` → `USER` → `FLAT` → `VR`), prefers a ⭐ row within a gate, prints the exact command to run,
and never hands a machine work its hardware cannot do. Which machine owns which project lives in
`machine-assignments.tsv` in the board repo; this machine's role comes from `$GATE_ROLE`, then
`role = <name>` in `~/.claude/lanes.conf`, then `DEV`.

**When you name the next task, name the model it needs too**, one line: `MODEL: STRONGEST`,
`STANDARD` or `LIGHT`, and why. Judge it from the row's text — a row that has resisted several
attempts or asks for something nobody has worked out is `STRONGEST`; a guided test or wiring up
known pieces is `STANDARD`; filing or re-running a known command is `LIGHT`. Round up when it is
close. `docs/PROTOCOL.md` §5.

If `--next` says **NOTHING QUEUED**, say so plainly and name what is left for the other machine —
that is a real answer, not a dead end.

## What the four gates mean

| Gate | Section heading | What it requires |
| --- | --- | --- |
| `PD` | PARALLEL DEVELOPMENT | Nothing running. Can proceed while the machine is busy with something else. This is `/pd`'s queue. |
| `USER` | NEEDS YOU, NOT THE APP | A human action — a file copied between machines, a download, a decision. |
| `FLAT` | QUEUED FOR A NORMAL RUN | Waiting for the next time the app is actually up. |
| `VR` | QUEUED FOR THE HEADSET | Waiting for special hardware. Batch these. |
| — | IDLE | Projects with nothing queued at all. |

The four names come from VR game modding, where this was built. Read them as *needs nothing* /
*needs a person* / *needs the app running* / *needs the hardware* and they fit most projects.
⚠️ They are currently **fixed**, not configurable — see the plugin README's limitations.

## Two things to say out loud

1. **If the PARALLEL DEVELOPMENT count is zero and there are no violations**, the script prints a
   `NO PARALLEL-DEVELOPMENT WORK LEFT ANYWHERE` banner. Repeat it in capitals. That is the signal
   to start something that needs the app, and it is the whole point of the command.
2. **If violations are listed**, say plainly that the counts are a floor rather than the truth,
   and name the projects whose blocks are missing or stale. A board that hides where it cannot be
   trusted is worse than no board.

## What this command must NOT do

- **Never edit a status file.** `/gates` reports; the working lanes write. If a gate looks wrong,
  say so — the fix belongs to a `/pd` or `/lm` session.
- **Never launch the app**, and never infer a gate the block does not state. A tag is written by a
  session that looked, never guessed by a reader.
- **Never run `git pull`** — the script uses `fetch` plus `git show origin/main:` precisely so that
  it cannot disturb another lane's working tree.
