---
description: (Parallel Development) Advances a project as far as it can WITHOUT the app running - static analysis, code that can be written and compile-verified now, and unblocking work recorded as blocked. Never launches anything. Shares a lane with /lm, so it must not run against a job another session holds.
---

`/pd` — **Parallel Development**. Do everything that does **not** need the app running, so that the
next live session spends its scarce time on the things that genuinely require it.

Argument: `$ARGUMENTS` — optional. A bare `/pd` **auto-picks one job**; `/pd <name> …` works one or
more named projects; `/pd skip:<name> …` runs the full list minus some.

---

## 0. The one hard rule

**Never launch the app. Never start a debugger, never attach to a running process, never run
anything that needs the app up.** Not "prefer not to" — never. Launching belongs to `/lm` and to
nothing else.

Concretely: no debugger, no attach, no injection, no launcher script, no "just to check". Building
is fine. Deploying a built artifact is fine (back up what you overwrite). **Running it is not.**

This is the whole reason the lane exists: it is always safe to run while another session holds the
machine's one "the app may run" slot.

If the only remaining step needs the app up: **say so, write down exactly what to run and what each
outcome would mean, and move on.** A precise one-command test left for the next live session is a
real deliverable, not a failure.

---

## 1. A bare `/pd` picks ONE job and stops

```bash
bash "${CLAUDE_PLUGIN_ROOT}/tools/gate-scan.sh" --next
```

`--next` already knows this machine's role, already prefers starred rows, already skips work this
machine's hardware cannot do, and **skips any job carrying a live claim, naming who holds it** —
which is what makes a bare `/pd` safe beside a running `/lm`. Take the job it names and work it
exactly as `/pd <name>` would.

**Then STOP and report. Do not pick a second job.**

⚠️ **Why the stop is not negotiable.** The first version of this command fanned out one helper per
project simultaneously and burned an entire usage limit in under twenty minutes, most of it spent
re-doing work by helpers that resumed after the first wave died. The fan-out was the fault, not the
bare invocation. A loop through jobs is the same fan-out spread over time. The user types `/pd`
again when they want the next one, and that is the whole spend control.

⚠️ **Auto-pick makes the board's accuracy load-bearing** in a way that picking by eye did not: a
person skims past a bad row, auto-pick walks straight into it. If the row you are handed is not
really no-app-needed work, **say so, fix its gate, and take the next one.** Correcting the board is
a deliverable, not a detour.

`--next` only *chooses*; it does not claim. Someone can claim between the pick and your take. If
your take is rejected, **do not stop** — re-run `--next` and take what it names instead. The push is
the atomic arbiter; losing that race is normal.

---

## 2. Never run two `/pd` sessions at once

Not in two terminals, not for two different projects, not "to get through the list faster".

Clone roots partition **lanes, not sessions**. A second `/pd` lands in the same working tree and the
same git index as the first, so the two fight over `git pull`, over `index.lock`, and over every
shared file. **It is slower, not faster.** This has happened; it cost both sessions about ten
minutes of untangling, which is more than the second job would have taken.

**The right way to do several projects is one session with several arguments:** `/pd alpha beta`.

Four *different* lanes in parallel is the design and works. Two of the *same* lane is not a faster
version of it.

If you end up in a conflicted shared root anyway: **nothing is lost.** `git pull --rebase` against a
dirty tree refuses outright; only `--autostash` reaches the bad state, and even then the stash
survives a `reset --hard`, and a dropped stash is still recoverable from the object store. Never
pass `--autostash` in a lane root. Do not "clean up" to make it go away, and never resolve a
conflict in a file you do not own.

---

## 3. Lane ownership

**`/pd` is not a separate lane. It IS the working lane**, scoped to no-launch work — it writes the
same files a live session writes. So:

| Alongside | Safe? |
| --- | --- |
| `/gr`, `/sr` (research lanes) | ✅ different files |
| `/gs` (hygiene) | ✅ read-only |
| `/lm` on a **different** job | ✅ |
| `/lm` on the **same** job | ❌ **skip it.** Since 0.4.0 the `/lm` runs its own background reader; there is no second seat |

### The live claim

A same-lane session claims a job by writing one line above that project's `OPEN` block and pushing
it. Take it, check it, release it:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/tools/lane-claim.sh" check <project>
bash "${CLAUDE_PLUGIN_ROOT}/tools/lane-claim.sh" take /pd <project>
bash "${CLAUDE_PLUGIN_ROOT}/tools/lane-claim.sh" release /pd <project>
```

A `FRESH` claim means that job is skipped this session, full stop — say so in the report. Claims go
stale after 12 hours. It serialises **one job**, not a whole lane, and the push is what arbitrates.

---

## The reader lives inside `/lm` now (0.4.0, 2026-09-10)

Until 0.3.0 a second `/pd` window could take a **tandem seat** beside a live `/lm` on the same job.
That is gone. Pairing on one job happens **inside one `/lm` session**: it runs exactly one
background reader agent that does what the seat did — read, measure, analyse, build — while `/lm`
owns every write. See `commands/lm.md` → "The reader". Two sessions on one job never had a clean
run worth counting (1 in 50 attempts, the two most recent faults both from it), and one session
sharing itself needs none of the four mechanisms that pairing needed.

So for `/pd` the rule is simple again: **a job with a FRESH `/lm` claim is skipped**, full stop.
Nothing else about this lane changed — a bare `/pd` still sweeps solo, auto-picks, keeps full
rights, and may deploy.

---

## 4. Your clone root is not the live lane's

Work in this lane's own clone root. Never operate in another lane's root, and `git pull` early and
often — your root only learns what the other lanes did by fetching.

**First, make sure your root holds every repo.** A repo added to one lane's root after the others were
made is invisible to this lane, and nothing fails: the session just covers fewer projects than exist
and reads as complete.

```bash
bash "${CLAUDE_PLUGIN_ROOT}/tools/root-sync.sh" --fix
```

It copies in any repo another root has and this one lacks (a near-free local clone pointed at the real
remote), never touches an existing clone, and says `all N clone roots hold all M repos` when there was
nothing to do. Name anything it `SKIPPED` or `FAILED` in the write-up.

---

## 5. Session shape

1. **Pull the board repo and read it.** These clones go stale; auditing one without pulling reports
   the state of this disk, not of the project.
2. **Pull every repo you intend to touch.**
3. **Drain your lane's `inbox/`** — by explicit filename list, never by glob. Record what `ls`
   returned *before* folding anything in, and delete only those names. A concurrent session can drop
   a file inside that window, and a glob deletes it unread with nothing in git to show it existed.
4. **Claim each job** before touching it.
4b. **Name the model THIS job needs — before doing any of it** (0.12.0). One plain line: the tier
   the row in front of you needs, and whether it matches the model actually running. ⚠️ It cannot
   come before the command is typed, because the pick needs a board read — say so rather than
   implying otherwise. **Running weaker than the job needs → stop and wait**, naming the tier and
   what to re-type. **Running stronger → say it in one line and carry on**, never stop: in this lane
   the person is usually away, so a pause trades the whole session to save tokens. Matching → one
   line, carry on, no ceremony. `docs/PROTOCOL.md` §5.
5. **Work.** Prefer the static toolbox: reading, disassembly, config and data files, code that can
   be written and compile-verified now, and turning a blocker into a precise one-command test.
   **Before adding to a file, check its shape** (`tools/code-shape-scan.py`): over the size budget
   means the split — move-only, backed up, proven to change nothing — is this session's job first.
   New probes go in their own files, tunable numbers get names, disproved probes go to `archive/`.
   `docs/PROTOCOL.md` §6.
5b. **⚠ Before you build a lever, say which step runs LAST.** Write one line: *this runs at step N
   of M, the thing I want to change is decided at step K, N is before/after K.* If your change lands
   after the value is decided, you are annotating it, not fixing it — move upstream. Build it so it
   **proves its own effect**: measure, act, RE-MEASURE, log both numbers, so a run can tell "no
   effect" from "wrong choice" without asking a person to judge the result. And never guard a change
   with something riskier than the change — validate the data you are about to touch, not the
   framework's description of it. `docs/PROTOCOL.md` §11.
6. **Verify before writing it down.** A fix that removes the symptom *and* stops the failing path
   from being exercised has proved nothing about the cause. Before writing "X caused it, because
   fixing X worked", ask whether the failing path still runs. If it does not, the claim is a
   hypothesis however well the fix worked.
7. **Write it up** with a confidence tag on every durable claim, and update the board's `OPEN` block
   so the next session inherits an accurate gate.
8. **Commit only your own lane's paths.** Never `git add -A` in a shared repo. `git pull --rebase`
   before pushing.
9. **Release every claim you took.**
10. **Update the public front page** if this estate has one — see below.
11. **Report**, and end with what the next step requires — in capitals, unprompted.
12. **Name the model the NEXT step needs** in one line beside the gate: `MODEL: STRONGEST`,
    `STANDARD` or `LIGHT`, and why. Round up when it is close; never spend the strongest on routine
    work. This is the **second** time the session says a model — step 4b named the tier for the job
    it was about to do; this one is for whoever picks up next. `docs/PROTOCOL.md` §5.

---

## 📰 Keep the public front page moving — every session, not every success

If this estate has a public front page (a profile README, a landing page), **add a dated line to it
before you finish, whether or not anything advanced.** A dead end, a correction, a look that found
nothing — all of it counts.

⭐ **The reason is not vanity, and it changes what belongs there.** The point is that the page reads
as *alive*: work that is visibly ongoing invites collaboration and reuse, and a page that only moves
on good news is a press release rather than a record. A quiet day, written down honestly, is worth
more than a gap.

```bash
bash "${CLAUDE_PLUGIN_ROOT}/tools/frontpage-scan.sh"     # is the page behind the boards?
```

It compares the newest date on any board against the newest date on the page and says when the page
has fallen behind. It is **read-only and never writes the line for you** — an auto-generated entry
would be exactly the bland noise this rule exists to avoid. Configure it with `frontpage = <path>` in
`lanes.conf`; with nothing configured it says so and exits quietly.

⚠️ **Keep it in the page's own voice and keep it short.** One or two lines per item, plain language,
and say what it *means* rather than what was touched. Older entries roll off the bottom — the full
history already lives in each project's notes.
