# When is it 1.0.0?

> **Published 2026-09-24 as 0.22.0, an early version, before this bar was met** - the author's
> decision: the bar below was written for calling the plugin *proven*, and "early, still being
> built" claims less. It now measures the road to **1.0.0**. The history problem in B2 was solved
> by starting the public repository fresh (`HISTORY.md` tells that story).

Not "when it feels ready". When the boxes below are ticked, and every one of them is something
you can check rather than something someone asserts. The README's headline numbers must match
this file.

---

## A. The evidence bar

| # | Must be true | How you check it | Now |
| --- | --- | --- | --- |
| A1 | **50 clean runs** — `/pd` and `/lm` live at once **on different projects** | `tools/run-log.sh` | **38 / 50** — 2026-09-18, 0 need review. ⚠️ Trailer coverage has FALLEN to **32%**, so this is further from being a real number than it was in September, not closer: an unattributed commit is invisible to the both-lanes test, so a run that should be reviewed can score CLEAN. Raising coverage is now worth more than adding runs. |
| A1r | **20 clean `/lm` runs with the reader** — the background reader wrote nothing it may not write | `tools/run-log.sh --reader` | **37 / 20 ✅** — 2026-09-18; ⚠️ still the dev PC's refusal log only, so "clean" here means "as far as this machine knows". The home PC has still not run `--reader` on its own log. |
| ~~A1a~~ | ~~50 clean TANDEM runs on the same project~~ **RETIRED 2026-09-10** — the two-session pairing was deleted in 0.4.0 (1 clean in 50 attempts; both latest faults came from it). Not failed, not carried at 1/50: the shape it measured no longer exists | — | — |
| A2 | Installed and exercised on **both machines**, not just the one it was built on | a row per machine below | **2 / 2** — home PC row 9, 2026-09-10 |
| A3 | **20 sessions** have used the plugin's own commands for real work | count the rows in the usage log below | **10 / 20** — ⚠️ undercounts: `run-log.sh` sees dozens of `/lm` and `/pd` sessions since row 9 that nobody logged here |
| A4 | **Zero open faults** attributable to the plugin | `docs/FAULTS.md` "Still open" is empty | **0 open ✅** — 2026-09-18: 11, 12 and 13 all found AND fixed the same day. ⚠️ "Zero open" is a weak signal on a day that opened three; A5 is the row that reads that correctly. |
| A5 | No fault found in the **last 5** logged sessions | `docs/FAULTS.md` dates vs the usage log | **0 / 5 ⚠️ RESET 2026-09-18** — faults 12 and 13 were both found today, in the updater, during an ordinary `/lanes:update`. Five clean logged sessions must now pass before this row is green again. **This is the row that says the plugin is not ready, and it is doing its job.** |

**A5 is the one that actually decides it.** A1–A3 are counts, and counts can be reached while the
thing is still breaking. A5 says the curve has flattened. If a fault turns up at session 19, the
count keeps going and A5 resets.

## B. The hygiene bar

| # | Must be true | How you check it |
| --- | --- | --- |
| B1 | Both test suites pass **from an installed copy**, on both machines | `bash <install>/tools/tests/smoke-test.sh` and `hooks-test.sh`  — ✅ dev 2026-09-10 (row 6), ✅ home 2026-09-10 (row 9) |
| B2 | No personal data anywhere — no project names, machine names, account names, paths | **`python tools/scrub-scan.py`** (0.12.2), asserted in `smoke-test.sh`. It was "grep the whole plugin folder" for six weeks and nobody did it once — which is the argument for a command rather than a line in a list. — **⚠️ FAILED and partly fixed 2026-09-18**, first proper audit of all 76 tracked files. Fixed: `docs/specs/2026-09-10-task-zero-payloads.txt` held the owner's username, home path, working directory, two session UUIDs and an excerpt of their personal `~/.claude/settings.json` — scrubbed to placeholders, the field names being the only part with evidence value; the hostname in `task-zero-result.md`; and `gate-scan.sh` printed the author's own two-machine arrangement to every user. **✅ The contact email STAYS — decided 2026-09-18 by the maintainer:** *"the email is fine, makes it look more authentic and it can stay."* It is the security contact on a page inviting strangers to audit the code, and it is in every commit's author field regardless. Marked `scrub-scan:allow`; do not raise it again. **✅ The personal handle is gone** (0.13.0) and `tools/scrub-names.txt` now enforces it. **Still open, all judgement calls:** `rtk` named in a spec with no explanation. ✅ **Game names, the two-machine arrangement and the estate layout are explicitly FINE** — the maintainer's own line, 2026-09-18: *"all the game related stuff can stay, the dev pc and home pc setup too, as long as PC names, usernames and other info like this is kept out of it."* Dropped from this list rather than carried as unresolved. Remaining: `rtk` named in a spec with no explanation; Steamless in `TOOLS.md` (DRM-adjacent). ⚠️ **THE BIG ONE, STILL OPEN: none of this leaves git HISTORY.** — and the maintainer has said the whole thing gets re-checked several times before publishing, so this is a decision to make then, not an assumption to carry. `HISTORY.md` (0.13.0) is what makes re-creating the repo cheap if that is the answer.  The payloads file is in it, and all 60 commits are authored by a real address. <!-- scrub-scan:allow --> Scrubbing files does not unpublish them — a fresh repo, or accepting the exposure, is the real choice. |
| B3 | The shipped template board passes the shipped validator | asserted inside `smoke-test.sh` |
| B4 | Zero CR bytes in every script, checked against the **committed blobs** | `git show :<path> \| tr -cd '\r' \| wc -c` |
| B5 | Every durable claim in the README carries a confidence tag, and the headline `n=` matches A1 | read it |
| B6 | Credits complete, with the note that anyone missing can ask to be added | read it |
| B7 | The GitHub **repo description** and the README tell anyone modding games to look at the author's GitHub for the index of games already in progress and the shared library — **outside** the plugin, so B2 still holds (decided 2026-09-15: the plugin stays neutral, the pointer lives on the repo) | read the repo's About box and the README |
| B8 | **The version moves in all four files at once**: `plugins/lanes/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `CHANGELOG.md` and the banner. ⚠️ **`marketplace.json` is the one the installer actually reads** — bumping only `plugin.json` makes the release invisible to `claude plugin update`, which then reports "already at the latest version" and looks like success. That is exactly what happened to eighteen releases (fault 11, 2026-09-18), because this checklist did not mention the file | asserted inside `smoke-test.sh` — three assertions, one per companion file |

## C. The stress bar — what "really put it through it" means

These are the situations that have actually caused trouble, so these are the ones worth
reproducing on purpose.

| # | Scenario | What must happen |
| --- | --- | --- |
| C1 | `/pd` and `/lm` live at once on one machine — **the working pattern** | no conflict, no lost work, every push lands |
| C2 | Two machines working different projects at the same time | both boards agree after a fetch |
| C3 | Two sessions racing for the **same** job | one takes the claim, the other is told and re-picks |
| C4 | A session killed mid-work (closed terminal, power loss) | the claim goes stale on its own; the next session takes it |
| C5 | A stale clone that has not been pulled for days | the board reports what was pushed, not what is on that disk |
| C6 | A machine with **no board configured at all** | every hook stays silent; nothing errors |
| C7 | A fresh machine, installing from the marketplace cold | works with no manual repair |
| C8 | A tandem pair — reader plus writer on one job | reader never deploys, and **cannot** write the status file; findings reach the writer mid-session |
| C9 | The read lanes run **in sequence** — `/gs`, then `/gr`, then `/sr` — before the working pair | each drains the inbox the one before it filled; no drop is read twice or lost |

---

## How the rows get filled in

By running **`/pt`** — the read-only test lane — in a third window beside the working lanes.
It runs both suites from the installed copy, diffs every tool against the original it came
from, exercises the guards against the live claim state, and writes a row here plus any fault
into `FAULTS.md`. It ends every run by printing these counts, so progress is visible without
anyone having to ask for it.

## Usage log

One row per session that used the plugin's own commands for real work. Keep it truthful — this is
the number the README's headline cites.

| # | Date | Machine | Lanes used | Result |
| --- | --- | --- | --- | --- |
| 1 | 2026-09-10 | dev | install + `lanes:gates` + both suites | clean; 5 faults found and fixed during the build itself, none during use `[verified-live 2026-09-10, n=1]` |
| 2 | 2026-09-10 | dev | `lanes:pt` | clean; both suites pass from the installed copy, all six tool outputs agree with the original, both guards correct against the live board. Zero plugin faults; three false positives, all self-inflicted (D, E, F) `[verified-live 2026-09-10, n=1]` |
| 3 | 2026-09-10 | dev | `lanes:pt` | built `run-log.sh` so the count harvests itself; found fault 6 (the tandem seat's status-file ban was written but unenforced) and fitted the latch the same day. 18 SEPARATE clean, 0 TANDEM `[verified-numerically 2026-09-10]` |
| 4 | 2026-09-10 | dev | `lanes:pt`, beside a live `/lm` + tandem `/pd` on one project | both suites pass from the installed copy; all six tool outputs agree with the original (wording swaps only, incl. the 155-line hygiene scan); guards correct against the live claim state. **Found fault 8** — the claim block's printed remedy drops the word `tandem` and lands you unlatched. One false positive (🔍 G, board drift), confirmed from commit times `[verified-live 2026-09-10, n=1]` |
| 5 | 2026-09-10 | dev | `/pd` on this repo — task zero, then the 0.4.0 build | hooks DO fire for a subagent, and its payload carries `agent_id` the parent's never does `[verified-live, n=1 each]`; tandem seat deleted, reader guard added and tested, fault 8 closed. **Both suites pass from the working copy; the installed-copy pass (B1) on both machines is still owed** |
| 6 | 2026-09-10 | dev | `lanes:pt`, first run against 0.4.0 | **B1 met on this machine**: both suites pass from the installed 0.4.0 copy — smoke 13/13, hooks 35/35 including all **16 reader-guard assertions** `[verified-live 2026-09-10, n=1]`. Four tool comparisons against the originals differ only in wording, each with a zero-line drift control (🔍 H). Logged fault 9, then **corrected it the same hour for overstating** — the guard *is* covered by the suite; what is missing is any live check of the reader. ⚠️ The reader has still never run |
| 7 | 2026-09-10 | dev | `lanes:lm` on alice-madness-returns-vr, 0.4.0 | ⭐ **the first live reader run.** It announced itself, cleared a suspect the session had been chasing, wrote a fix for a misleading log readout, and `/lm` built, deployed and confirmed it — the exact division of labour the design asks for, and the visibility requirement met `[verified-live 2026-09-10, n=1]` |
| 8 | 2026-09-10 | dev | `lanes:pt` | harvested the reader bar for the first time and **found fault 10** — it counts `/lm` windows from before 0.4.0 existed, reporting 3 clean runs where there was 1. `A1r` corrected by hand |
| 9 | 2026-09-10 | **home** | install (`claude plugin marketplace add` + `install`, 0.4.1) + both suites from the installed copy + session-start hook through the Windows shim | **B1 and A2 met on the second machine**: smoke and hooks suites both pass from `~/.claude/plugins/cache/tefmeister-plugins/lanes/0.4.1`; `run-hook.cmd board-brief` returns the live board `[verified-live 2026-09-10, n=1]`. ⚠️ One finding for `/pt`, NOT logged as a fault by this session: the committed blobs are CR-free (B4 holds) but the CHECKOUT here has CRLF in `hooks/board-brief` (30), `hooks/py-hook` (40), `hooks/hooks.json` (67) — the root `.gitattributes` patterns `hooks/board-brief` / `hooks/py-hook` / `run-hook.cmd` are root-relative and match nothing under `plugins/lanes/hooks/` (`git check-attr` confirms; the `*.sh` / `*.py` rules do match). Nothing broke, both hooks ran clean `[measured 2026-09-10]`. First live `/lm`-with-reader run on this machine still owed |
| 10 | 2026-09-15 | dev | `/pd`-shaped fix session on this repo: `run-log.sh` (both modes), both suites | **Faults 9 and 10 closed → 0.6.2.** Fault 10's real cause was day-level granularity (the reader shipped at 15:35, the cutoff was a bare date); the cutoff is now the exact commit timestamp read from git, with a committed `tools/reader-since.txt` fallback because an installed copy has no `.git` — a limit found, not assumed. 8 new smoke assertions cover it; smoke and hooks suites both pass from the working copy. Harvested: A1 **33/50**, A1r **24/20** `[verified-numerically 2026-09-15]`. **Later the same day: 0.6.2 installed here via marketplace update, both suites pass from `~/.claude/plugins/cache/tefmeister-plugins/lanes/0.6.2`, zero CR bytes — B1 met on the dev PC for 0.6.2** `[verified-live 2026-09-15, n=1]`. ⚠️ Found while doing it: the new fault-10 assertions were all inside an `if git history exists` block, so an installed copy **skipped the very fallback path an install uses**. Fixed in 0.6.3 — the windowing and fallback checks now always run; only the file-matches-git drift check needs a checkout. Home PC: **0.6.1 per the author** `[reported 2026-09-15]` — an earlier version of this row said 0.4.1, copied from a 2026-09-10 note no later update touched. Per-PC versions are now recorded in `claude-memory/deployed/<HOST>/plugins.tsv`; the home PC has not recorded yet |

## Working-pattern run log

**The bar changed on 2026-09-10, because the workflow did — twice in one day.** Four lanes at once
is no longer how this is run: the read lanes go **in sequence** — `/gs`, then `/gr`, then `/sr` —
and only then `/pd` and `/lm`. So `/pd` + `/lm` is the pair that actually overlaps, and A1 counts
that. **Then, the same afternoon, the same-project half of it was deleted:** pairing on one job now
happens *inside* one `/lm` session as a background reader (`docs/specs/2026-09-10-one-session-
reader-design.md`), so A1 is the different-projects count only, and A1r counts the reader.

**Why the split matters, and it already paid for itself:** the two shapes have different risk.
**Separate** projects share the clone root, the board and the git index — contention is mechanical,
and git catches it. **Tandem** on one project means both lanes edit the same status file and the
same dossier, where a clash is **semantic**: two edits that each rebase cleanly, the later silently
undoing the earlier. Git cannot see that. Splitting the count immediately showed that **the risky
half has never had a clean run** — A1a is 0, off two attempts, both failures.

### The count is harvested, not typed

```bash
bash tools/run-log.sh [board] --root <folder holding the clones> [--verbose]
```

**Nobody writes a row into this file any more.** `run-log.sh` reads the claim commits to find every
window where a `/pd` and an `/lm` overlapped on one machine, classifies each as TANDEM or SEPARATE
by whether the projects match, and scores it CLEAN when **no file was written by both lanes** inside
the window. That one test serves both shapes, and for TANDEM it *is* the safety rule.

Hand-written rows were the risk this replaces: this file's own warning is that counts can be reached
while the thing is still breaking, and a hundred rows typed by hand drift into assertion. Harvested,
the public claim is something a stranger can re-derive.

**What it deliberately will not count:** a run where either lane never took a claim, or whose commits
carry no `Lane:` trailer, or where the two lanes overlapped for under five minutes (a handover, not a
run). It prints trailer coverage every time, and says the count is an **upper bound** while coverage
is below 90%. `[verified-live 2026-09-10, n=1]`

### A1a — RETIRED 2026-09-10

Two sessions pairing on one project was deleted in 0.4.0, so this row measures a shape that no
longer exists. It is **retired, not failed, and not carried at 1 / 50** — a bar quietly dropped is
how a public claim goes bad; one openly retired with its reason is fine. The reason: 1 clean run in
50 attempts, every collision on the same single file (`status/<project>.md`), the two most recent
faults (6, 8) both from the seat, and the design drafted to fix it needed four new mechanisms. One
session sharing itself needs none of them. History stays in `run-log.sh`'s output as
`SAME-PROJ … NOT COUNTED` rows.

### A1r — `/lm` runs with the reader (24 / 20 ✅ — 2026-09-15, dev PC's log only)

New in 0.4.0. Harvested by `run-log.sh --reader`: every `/lm` claim window since 2026-09-10, scored
CLEAN when `hooks/reader-guard.py` recorded no refusal inside it. ⚠️ **Honest limit:** the refusal
log is local to the machine that ran the session, so run it there; a machine with no log reports
"clean as far as this machine knows", and says so. Twenty because that is A3's bar too — enough to
see whether the curve has flattened, not so many the count outlives the interest. **Zero live runs
so far**: the build was compile- and test-verified on 2026-09-10, and the first real `/lm` with a
reader is still owed.

### A1 — separate projects (33 / 50 — 2026-09-15)

Eighteen clean runs, zero needing review, across seven projects and two machines
`[verified-numerically 2026-09-10]`. This shape is working. Run `run-log.sh` for the current list.

### Failure rows — not counted

**2026-09-05, tandem on re-village-scope-vr.** The collision the claim guard was built for. 11:36
`/lm` re-gated the OPEN block ("bad tags fixed"); 12:03 `/pd` reintroduced three bad gate tags;
13:20 `/lm` was still live. Git was perfect throughout — clean rebase, no conflict, nothing lost.
The clash was **semantic**, and only `gate-scan --check` caught it, about two hours later
`[verified-numerically 2026-09-05, from the commit timeline]`.

**2026-09-01 four-lane run — no evidence for either bucket.** Lanes were `/pd`, `/gr`, `/sr`,
`/gs`; **no `/lm`**. It still produced the drain-by-explicit-list rule
`[verified-live 2026-09-01, n=1]`.

**2026-09-02 same-lane collision.** Two sessions of one lane in one clone root. Cost about ten
minutes each, lost nothing. The reason rule 1 exists.

**Corrected 2026-09-10.** An earlier version of this table logged 2026-09-05 as a *clean tandem*
run and 2026-09-07 as a second one. Both were wrong: 09-05 has **two** sweep entries and the
tandem one is the collision above, while every clean run on record is the **separate** shape. The
error came from reading a sweep entry by date instead of by heading. Recorded here rather than
quietly fixed, because a wrong row in this table is precisely how a public "tested on 100 runs"
claim would become false.

**Pending an audit, not yet counted:** `/pd` and `/lm` were both active on **2026-09-06, 09-08,
09-09 and 09-10**, confirmed mechanically from the board's `Lane:` trailers and claim commits
`[verified-numerically 2026-09-10]`. Each needs its sweep verdict read, **and its shape
determined**, before it becomes a row.

**2026-09-10 10:00, tandem on manhunt-2003-vr.** Claims taken and released cleanly in one minute,
but **no work commits landed**, and it immediately produced a fix (`/pd` was reading the word
`tandem` as the project name). A mechanism test that found a bug, not a clean run
`[verified-live 2026-09-10, n=1]`.
