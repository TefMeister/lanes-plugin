---
description: (Plugin Test) The read-only lane that tests this plugin against real work. Runs both test suites from the INSTALLED copy, compares every tool's answer against the original it was extracted from, exercises the guards against the live claim state, and records what it finds. Writes ONLY to the plugin's own repo, never pulls, never launches anything - so it is safe to leave open beside every other lane.
---

`/pt` — **the plugin's own test lane.**

Leave it open in a third window beside the working pair — `/pd` and `/lm` on different projects, or
a single `/lm` session running its own background reader. Its whole job is to catch this plugin
being wrong, on real work, before anyone else does.

---

## 0. The hard rules

1. **Write nothing outside this plugin's repo.** Not a status file, not a note, not an inbox drop.
   The only files this lane may edit are `docs/FAULTS.md` and `docs/RELEASE-CHECKLIST.md` in the
   plugin repo, which no other lane touches — so it cannot collide with anything, ever.
2. **Never `git pull` anywhere.** `fetch` only. A pull rewrites a working tree another lane may be
   mid-write in; a fetch touches refs and nothing else.
3. **Never launch anything.** No app, no debugger. Same rule as the research lanes.
4. **Never take a claim.** This lane holds nothing and blocks nobody.

⚠️ **Because it reads working trees other lanes are writing, an odd result is not a fault yet.**
Re-run it before recording anything. A tester that cries wolf trains people to ignore it, which is
worse than no tester.

---

## 1. Test the installed copy, not the working copy

The install round trip is where files get mangled — line endings, permissions, missing pieces. So
test what is actually installed:

```bash
claude plugin list                      # find the install path
bash <install>/tools/tests/smoke-test.sh
bash <install>/tools/tests/hooks-test.sh
```

Both must pass in full. **Any failure is a fault** — record it before doing anything else.

## 2. Compare every tool against the original it came from

Where the machine still has the setup this plugin was extracted from, run both and diff. This is
the highest-value check, because it needs no judgement about what is *correct* — only about whether
two things agree.

```bash
bash <install>/tools/gate-scan.sh --next   <board>
bash <original>/gate-scan.sh    --next     <board>
```

Do this for the board, `--brief`, `--mine`, `--next`, `--check`, and the hygiene scan.

**Differences that are EXPECTED, and are not faults:**

- **Wording.** The plugin says *nothing running* / *needs you, not the app* / *a run with the app
  up* / *special hardware*, where the original says the game-specific equivalents.
- **Clocks.** A file age can differ by a day if the two runs straddle a whole-day boundary, and a
  header timestamp differs if they straddle a minute. **Confirm the cause before dismissing it** —
  check the commit time. Both have happened; both were checkable in a minute.
- **A board that changed between the two runs.** Another lane pushing mid-comparison is normal.
  Re-run rather than assume.

Anything else is a fault.

## 3. Exercise the guards against the live claim state

```bash
bash <install>/tools/lane-claim.sh list --repo <board>
```

- If a job is **claimed** right now, feed the claim-guard a prompt naming it and confirm it blocks
  with a reason and exits 2.
- If **nothing** is claimed, confirm a prompt naming any job passes silently.
- Confirm an ordinary sentence is ignored entirely.

Always pass `$LANES_PD_LOCK` when testing the `/pd` lock. **Never touch the real one** — a live
`/pd` prompt landing in that window would get the wrong answer, and that has already happened once.

## 4. Watch what the other lanes are doing

If you are beside a live `/pd` and `/lm`, that is free concurrency evidence for the separate-projects
shape:

- If a session was **blocked** by a guard, was it right to be?
- If the board **recommended** a job, was it one another lane was already on?
- If a claim went **stale**, did the next session take it cleanly?
- Did either board — yours or the original's — ever disagree with what actually happened?

## 4b. If an `/lm` session is running, watch its reader

The reader is part of the product since 0.4.0, and nothing checks it live unless this lane does.
While an `/lm` session is open, confirm — don't just trust the design doc:

- **It started.** Exactly one background reader for that `/lm` session, not zero, not two.
- **It announced itself.** The session said out loud that a reader is running, per the visibility
  requirement in the reader design.
- **It relayed something.** A finding from the reader reached the `/lm` session mid-session, not
  only in a final write-up.
- **It stayed read-only.** It never wrote `status/*.md` directly — the writer session did, after the
  reader handed it something.

If no `reader-guard.py` refusal shows up in `~/.claude/lanes-reader-refusals.log` for this session's
window, that is the **expected** result (the guard only logs when it blocks something) — not a sign
the reader never ran. Confirm the reader ran from what the session actually said and did, not from
the refusal log's silence.

## 5. Record it

**A fault goes in `docs/FAULTS.md` the moment it is found — before it is fixed, not after.** Say
what it would have *done* to someone, not just what it was. If investigation shows it was not a
fault, record it under "investigated, not a fault" with the cause. Both halves matter.

**Then add one row to the usage log in `docs/RELEASE-CHECKLIST.md`**, and re-check the counts at the
top of that file — including `A1r`, harvested with:

```bash
bash <install>/tools/run-log.sh --reader <board> --root <folder holding the clones>
```

Commit to the plugin repo only. `git pull --rebase` there is fine — nothing else uses it.

## 6. Report, and always end with where the release stands

Finish every run with the checklist counts, so progress is visible without anyone having to ask:

```
PLUGIN: 33/50 separate-project runs · 26/20 reader runs · 2/2 machines · 8/20 sessions · 2 open faults
```

Then the gate line, as every lane does.
