---
description: (Gate watch) The one sanctioned background watcher - allowed in /gr, /sr, /pd and ordinary sessions, but NEVER in /lm or /gs. Reports board changes this session did NOT make - work pushed by another lane or another machine. Read-only, never launches anything, silent when nothing changed.
---

`/gate-watch` — **the constant known task.** One job, permanently: say when a project's status
changes, so the user can switch between working with nothing running, working with the app up, and
working in the headset at the right moment instead of guessing.

This is the **single** carve-out to the no-background-helpers rule, and it earns it by being
nameable: the user can say what it is doing at any moment. The line is **opacity, not
concurrency**. It is not a licence to spawn helpers for other work.

**🚫 Do NOT start this watcher from a `/lm` or `/gs` session.** Those two run fully inline — `/lm`
because it is driving a live app, `/gs` because its whole value is that the session did every
check itself. The watcher belongs to `/gr`, `/sr`, `/pd` and ordinary sessions.

## Run it

```bash
bash "${CLAUDE_PLUGIN_ROOT}/tools/gate-scan.sh" --watch
```

Print the output verbatim, capitals included. **Say nothing else when it reports `no change`** —
that is the correct outcome most of the time, and commentary on a quiet tick is exactly what
trains a person to stop reading the loud ones.

## What it is for, precisely

**Changes this session did not make.** Changes made here are announced as they happen, so a
watcher repeating those would be a slower second source for something already known. This covers
the gap that cannot: another lane pushing new rows, a research drop that unblocks a recorded
blocker, work done overnight on the other machine. Those reach `origin/main` and are invisible
locally until something fetches.

Do not oversell it as more than that.

## What it reports, in priority order

1. **A new `[PD]` row anywhere** — the highest-value event, because it means work opened up that
   needs nothing running, and the headset can come off. Capitals.
2. **The estate-wide `[PD]` count reaching zero** — the signal to start something that needs the
   app. Capitals.
3. Rows queued at other gates, and rows that disappeared (done, or deferred).
4. New violations — a block went stale or malformed, so the counts now understate.

Silence when nothing changed. The first run on a machine says `baseline established` rather than
reporting every existing row as new.

## Hard constraints

- **Read-only.** `fetch` and `git show` only. Never edit a status file, never commit, never push.
  A wrong gate gets reported, not fixed — the working lanes write.
- **Never launch anything.**
- **Never infer a gate.** Report changes to tags a session wrote; do not deduce new ones.
- **Exactly one watcher.** If one is already running, do not start a second.
- The snapshot lives at `<board>/.gate-snapshot`, is **gitignored**, and is per-clone by design —
  each machine tracks what *it* has seen. Never commit it.

## Cadence

Board changes arrive at human speed — a session pushes every twenty minutes at best. Poll about
every **20–30 minutes**. Anything faster burns tokens re-reading a board that has not moved.
