---
description: (Good-standing Sweep) Periodic READ-ONLY hygiene pass over every repo. Verifies claims are tagged with confidence, corrections point at what they supersede, inboxes are being drained, and templates have not drifted. Curates NOTHING - it reports, and files create-only inbox drops for whatever an owner must fix. Safe to run alongside every other lane.
---

`/gs` — the hygiene pass.

Argument: `$ARGUMENTS` — optional. A date (`2026-08-20`) to override the delta window, or one
project name to sweep that project only. Empty sweeps everything since the last logged sweep.

## What this is for

Notes grow faster than anyone can re-read them. `/gs` exists so that **wrongness becomes visible
without re-reading everything** — it checks mechanical invariants across every repo and then reads
only what those checks flag.

It was created after a claim recorded as fact turned out to be wrong and was acted on the next day
*because it read as settled*. The repo layout did not cause that; the missing provenance did.

## ⚠️ Hard scope — this lane curates NOTHING

`/gs` is **read-only** everywhere, which is what lets it run safely beside every other session and
sidesteps the one-writer-per-file rule entirely.

| may do | may NOT do |
| --- | --- |
| read any file in any repo | edit any curated doc, in any repo |
| `git pull` | drain an inbox — that is the owner's job |
| create NEW files in `inbox/` folders | edit or delete an existing inbox file |
| append to its own sweep log | rewrite history, force-push, delete anything |

The **only** two things `/gs` may write: create-only inbox drops, and its own sweep-log entry.
Anything else you think needs changing goes into the report, or into the owning repo's `inbox/` as
a drop — never as a direct edit.

## 🤖 No background helpers in this lane

**Run every part of this sweep inline.** `/gr`, `/sr` and `/pd` may spawn helpers; `/gs` may not,
and neither may `/gate-watch`.

The reason bites hardest here: the value of `/gs` is that the session actually performed each check
and can show its working. A helper's entire product is a confident second-hand summary — precisely
the failure this command exists to catch. Fanning the checks out would hollow out the audit while
making it look faster. A sweep is short enough that a watcher would add nothing anyway.

## 0. Your clone root is not the live lane's

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

## Steps

### 1. Sync

```bash
for d in */; do git -C "$d" pull --quiet; done
```

This is the slow part — wall-clock, not thinking. If a pull fails, note it and move on; a stale
clone makes the scan **understate**, never overstate.

### 2. Run the mechanical scan

```bash
bash "${CLAUDE_PLUGIN_ROOT}/tools/gs-scan.sh"
```

It reports nine things, and each means something different — do not treat them as one list.

1. **Undrained inbox files.** Two weeks old means the owning lane has not run. That is a nudge, not
   an error. **`<-- STALLED` is the sharper flag:** the owning lane has committed to files it owns
   in that repo *since* the drop landed, so this is not "waiting for the owner" — it was either
   partly done and the rest forgotten, or missed entirely. Age alone cannot tell those apart, and
   that ambiguity once hid a wrong date for five consecutive sweeps.

2. **`Supersedes:` headers** — the highest-value check. Two cases needing **opposite** action:
   - the target is still in the inbox → drain both together, the correction wins;
   - the target has already been drained → **the wrong claim may already be live in the curated
     docs.** Go and look. This is the case the whole command was created for.

3. **Untagged claim-bearing docs.** Anything written before the tagging rule existed fails this by
   definition. It is a backlog that should trend down — not an emergency, and not something to fix
   by bulk-editing files you do not own.

   **3b. Off-vocabulary tags.** A tag that *reads* as a confidence claim but is not one of the
   eight valid names, so it looks strong to a human and counts as **nothing** to every tool. Check
   3 cannot see these — it is all-or-nothing per document, so a file with thirty good tags and
   three bad ones passes clean. Reported in three buckets, needing different treatment:
   - **DATED** — a real claim wearing an invented name. Usually a one-word fix.
   - **UNDATED** — **either** prose about a tag (a changelog line quoting one) **or a real tag
     missing its date as well as its name — both defects at once.** Read the line; do not assume
     prose. That bucket was once labelled "usually prose", and a real undated tag hid behind the
     label twice in one run.
   - **QUOTED IN CORRECTION PROSE** — dated, but the line also carries correction language, so it
     is usually a changelog recording a fix already made. It exists because a changelog must quote
     the old tag verbatim, which meant every correctly-drained tag drop was landing in DATED as a
     fresh violation — the check got noisier precisely as the estate did the right thing, and that
     taught sessions to fix tags silently.

   The buckets are named after **what was measured**, not after a guess at intent, because the
   original claim here — "a hit is nearly always real" — measured at about 46%.

4. **Weak evidence** — `n=1` claims, and `verified-live` with no date. Note that `n=1` is perfectly
   valid for a **disproof**: one counter-example refutes a universal claim.

5. **Template drift** — inbox READMEs diverging from the shared shape.

   **5b. Pasted-back preamble blocks.** The lane command files keep short stubs pointing at the one
   canonical copy of the shared text. This greps for phrases that existed only in the removed
   copies, and proves it can still fire by running the same phrases against the pre-deduplication
   version. A **`SENTINEL DEAD`** line means the check is blind, **not** that the estate is clean.

6. **Delta scope** — which repos actually changed, so the reading step knows where to look.

7. **`status/` OPEN blocks** — every project file carries exactly one dated `OPEN` block, every row
   is tagged, and no block is older than its own file's newest log entry. **A stale block is a
   session that logged work without re-auditing what is left**; a missing one makes the board
   understate, which is worse than it sounds, because the whole point of that board is an
   *exhaustion* claim the user schedules their day on. Delegated to `gate-scan.sh --check` rather
   than re-implemented — two parsers for one grammar drift, and the drift is silent.

### 2a. Is the code keeping its shape?

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/tools/code-shape-scan.py" .
```

Read-only, like everything in this lane. Four flags, worst first:
- **`LUA-LOCALS`** — a Lua file near the 200-locals limit. **Treat this as urgent**: the next
  `local` added stops that script loading, with no warning until the app runs. It is an estimate;
  `luac -l -l` gives the exact count.
- **`OVER-HARD`** / **`OVER-SOFT`** — past 1,500 / 800 lines. A backlog that should trend down.
- **`LOOSE-NUMS`** — many numbers written inline instead of named. Noisy by nature (array sizes,
  test vectors); read the example lines before believing it.

File one inbox drop per project for its owning lane, listing that project's hits. Never split or
edit a file from this lane. Rules and reasons: `docs/PROTOCOL.md` §6.

### 2b. Is the public front page keeping up?

```bash
bash "${CLAUDE_PLUGIN_ROOT}/tools/frontpage-scan.sh"
```

One line if the page is level with the boards, a warning if it has fallen behind the newest dated
board entry, and a quiet note if no front page is configured at all.

⚠️ **A lag is a reminder, not a violation** — a session may be mid-flight. And this lane curates
nothing, so if the page is behind, **file an inbox drop for the owning lane rather than editing the
page yourself.** The rule it enforces is that the page moves on *every* session, including the ones
that found nothing.

### 3. Read only what the scan flagged

Open the flagged files. Do not re-read the estate. The scan's job is to tell you where to spend
attention; spending it everywhere is the thing this command replaces.

### 4. Report, and file drops for what you cannot fix

Every defect that belongs to an owner becomes a **new** file in that lane's `inbox/`, named
`YYYY-MM-DD-gs-<short-slug>.md`. Never edit a curated doc, and never edit or delete an existing
inbox file — not even one an earlier `/gs` wrote.

Then append one entry to the sweep log so the next sweep knows where its delta window starts.

### 5. Re-run the checker after fixing the checker

If this sweep changes `gs-scan.sh` itself, **run it again**. Successive passes have each found a
defect in the previous pass's fix. Mechanical checks beat careful hand-greps, but only once they
have been shown to fire.

---

## The eight confidence tags

The whole vocabulary, and check 3b enforces exactly these:

`[verified-live YYYY-MM-DD, n=K]` · `[measured YYYY-MM-DD]` ·
`[verified-numerically YYYY-MM-DD, n=K]` · `[compile-verified YYYY-MM-DD]` ·
`[inferred-static]` · `[reported]` · `[hypothesis]` · `[disproved YYYY-MM-DD]`

**`n=1` is not verified** — write `n=1` and let the reader judge. An invented tag reads as a strong
claim to a human and counts as untagged to every tool: put the precision in the prose beside the
tag, never inside it. Untagged claims are treated as `[hypothesis]`.
