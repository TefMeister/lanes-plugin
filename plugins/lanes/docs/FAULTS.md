# Faults found, and what happened to them

Every fault found in this plugin, in one place, so nobody has to read commit messages to know what
state it is in. **Kept honest deliberately**: a tool whose whole subject is claim hygiene cannot
have a hidden defect list.

Add a row the moment a fault is found — before it is fixed, not after.

## Legend

| | |
| --- | --- |
| ✅ | fixed, and something now prevents it coming back |
| ⚠️ | known, not fixed — see "Known limitations" in the README |
| 🔍 | investigated and found NOT to be a fault |

---

## Fixed

### ✅ 1. The board silently stopped checking whether a job was taken

**Found** 2026-09-08, in the original, before the port. **What it did:** `gate-scan.sh` looked for
`lane-claim.sh` next to itself. A copy of the script placed anywhere else found no claim tool,
reported **no claims at all**, and would happily recommend a job another session was holding — with
no warning line and no error. Observed live: a stray copy recommended a project a `/pd` was on.

**Why it mattered more than it looks:** the failure is invisible in the output. Everything reads
normal; the check simply did not happen.

**Fix:** it now refuses to run and says why. **Prevented by:** `smoke-test.sh` runs a stray copy
and asserts it both complains and exits non-zero.

### ✅ 2. The session-start hook would have pasted a Microsoft Store advert into every session

**Found** 2026-09-09, during the port. **What it did:** the hook picked a Python interpreter by
finding one on `PATH`. On a clean Windows machine, `python3` and `python` resolve to Microsoft
Store "app execution alias" stubs, which exist, print an advertisement to stdout and exit
non-zero. That advertisement would have been injected as session context.

**Fix:** candidates are now tested by **running** them, not by existence. **Prevented by:** the
same check is used in both hook launchers, and the hook exits silently when no interpreter works.

### ✅ 3. Two hook scripts would have arrived broken on any fresh Windows checkout

**Found** 2026-09-09. **What it did:** `board-brief` and `py-hook` are extensionless on purpose, so
neither the `*.sh` nor the `*.py` line-ending rule caught them, and git was about to hand a fresh
Windows checkout CRLF copies. Bash rejects those. The symptom would have been "the hooks just
don't work", with nothing to point at.

**Fix:** named explicitly in `.gitattributes`. **Prevented by:** verified against the **committed
blobs** rather than the working tree — zero CR bytes — and re-checked after a real install.

### ✅ 4. The plugin's own test moved a live session's lock aside

**Found** 2026-09-09, immediately after writing the test. **What it did:** `hooks-test.sh` deleted
`~/.claude/pd-session.lock`, ran its assertions, then restored it. A real `/pd` prompt landing in
that window would have got the wrong answer.

**Fix:** `pd-guard.py` takes a `$LANES_PD_LOCK` override and the test uses a throwaway path.
**Prevented by:** an assertion that the real lock was never touched.

**Worth stating plainly:** the test was the dangerous thing, not the code under test.

### ✅ 5. A modifier would have been read as a project name

**Found** 2026-09-09. **What it did:** `/lm i launch` sent name resolution hunting for a project
called "i launch". `force` had the same latent problem and had simply never been typed with an
ambiguous name.

**Fix:** both are named as modifiers to strip before resolving. **Note:** the prompt guard was
unaffected — two tokens matching no project resolve to nothing and it passes silently, which is its
fail-open behaviour working as designed.

### ✅ 7. A shipped tool gave the OPPOSITE answer about whether a correction was still pending

**Found** 2026-09-10, by running the lane it belongs to against the real estate rather than a
fixture. **What it did:** `tools/gs-scan.sh` check 2 reports, for every correction found, whether
the thing it corrects is **still pending** (drain both together, the correction wins) or
**already drained** (go hunt the curated docs for a claim that may now be live). Those two verdicts
prescribe **opposite actions**. A target written relative to the lane — `Supersedes: inbox/<file>.md`, the form the conventions’ own examples use — was probed at
`.../inbox/inbox/<file>.md`, missed, and fell through to **already drained** while **check 1 in the
same run listed that very file as pending**. The scan contradicted itself on one screen. **2 of 4
live rows were wrong on the day it was found.**

**Not introduced here — inherited.** The line dates from the original tool’s first commit,
**2026-08-28**, twelve days before this repo existed; the extraction copied it faithfully. Recorded
anyway, because it **shipped in 0.2.0 and was giving wrong answers to anyone who installed it**,
and because "we copied the bug correctly" is not a defence a user of the plugin cares about.

**Fix:** the check now also tries the basename — but **only when the target’s own leading folder
names the directory being scanned**, so a `topics/<file>.md` target is still correctly reported as a
curated doc even when a same-named file happens to sit in the inbox. Fixed upstream and here in the
same session, so `/pt`’s tool-vs-original diff stays clean.

**What prevents it coming back:** the upstream fixture
(`claude-memory/tools/tests/gs-scan-2-supersedes-fixture.sh`) gains case **(d)**, the regression
itself, and case **(e)**, a **narrowness control** proving the fallback does not reach into another
folder. It was proved able to fail before the fix went in: reverted to the old classifier it reports
`1 CHECK(S) FAILED`; restored, `ALL CHECKS PASSED`. ⚠️ **The old fixture could not have caught
this** — every target it used was a bare filename, so the one form that breaks was the one form it
never tested. That is the transferable lesson: a fixture built from the shapes you thought of
reports green about the shapes you did not.

### ✅ 6. The tandem seat's most important restriction was written down but nothing enforced it

**Found** 2026-09-10, by `/pt`, from the git record rather than from reading the code.

`commands/pd.md` already says it, in a table, in bold: in the tandem seat, `/pd` may **never** edit
the curated notes or the status file. **Nothing checks.** It is a rule a session applies to itself,
and sessions have not applied it:

| When | What happened |
| --- | --- |
| 2026-09-05 | `/lm` re-gated the OPEN block at 11:36 ("bad tags fixed"); `/pd` reintroduced three bad gate tags at 12:03; `/lm` was still live at 13:20. Caught by `gate-scan --check` about two hours later `[verified-numerically 2026-09-05, from the commit timeline]` |
| 2026-09-09 17:11 | a 7-minute tandem run on doom-2016-vr; both lanes wrote `status/doom-2016-vr.md` `[verified-numerically 2026-09-10]` |

**What it does to someone:** two edits that each rebase cleanly, the later silently undoing the
earlier one's fix. **Git behaves perfectly throughout** — no conflict, no revert, nothing lost from
git's point of view. The damage is semantic, so no git rule would ever catch it, and the person who
loses work gets no warning at all.

**The collision surface is exactly one file.** Every tandem clash on record — all three — is
`status/<project>.md` and nothing else. Not source, not notes, not recon evidence. Those never
overlap, because the two lanes genuinely do different work.

**Measured, not asserted:** `tools/run-log.sh` scores every `/pd` + `/lm` overlap in the history.
**18 SEPARATE runs, all clean. 0 clean TANDEM runs**, from every tandem window long enough to
count. The shape that shares a project has never once completed cleanly.

**Fixed 2026-09-10, the same day**, by `hooks/tandem-guard.py`. **No rule was rewritten and no rule
was added** — the written one got a machine instead of a memory. A session that types `/pd … tandem`
is marked; while marked, a write to any `<board>/status/*.md` is refused with a reason and exit 2.
The mark is dropped by a bare `/pd` (which keeps full rights, deliberately), by `/lm`, and at
`SessionEnd`.

**It stays narrow on purpose.** All three collisions on record are that one path shape, so that is
all it guards. Source, notes and recon evidence never overlap, because the two lanes genuinely do
different work. A guard that grew to cover things it had no evidence for would be the tangle it
exists to prevent.

**Prevented by:** 14 assertions in `hooks-test.sh` — that it blocks the write, explains itself, names
the inbox as the way to hand the finding over, treats a Windows backslash path in the wrong case as
the same file, leaves everything outside `status/` alone, does not touch another session in the same
window, catches a Bash redirect but **not** a Bash read, drops the seat on a bare `/pd` and at
`SessionEnd`, and **fails OPEN with no board configured**. The real marker file's size and mtime are
recorded before the run and compared after, so the suite cannot repeat fault 4.

**Worth stating plainly:** the rule was already correct and already written in bold. Being written
down is not a control.

---

### ✅ 8. The block message handed you the one command that undid the tandem latch

**Found** 2026-09-10, by `/pt`, against a live `/lm` + tandem `/pd` pair on one project.

`lane-claim-guard.py` refuses a `/pd <job> tandem` prompt whenever an `/lm` already holds a FRESH
claim on that job, and prints one remedy: **`type exactly: /pd force <job>`**. It builds that string
as `lane + " force " + jobs`, so **every other token is dropped — including the word `tandem`.**

**What it does to someone.** They wanted the passenger seat. They are told to type a command that is
not the passenger seat. `tandem-guard.py` latches only on a prompt matching `tandem`, so the
suggested command seats nobody: the session lands on a job a live `/lm` owns with **full write
rights over `<board>/status/<project>.md`** — precisely the state fault 6 exists to prevent, reached
by following the guard's own instruction. The two guards shipped in the same release and neither
knows about the other.

**Verified live, twice** `[verified-live 2026-09-10, n=2]`:

| Prompt | claim-guard | tandem seat after |
| --- | --- | --- |
| `/pd manhunt-2003-vr tandem` | **exit 2**, blocked | — |
| `/pd force manhunt-2003-vr` *(the printed remedy)* | exit 0 | **`{}` — no seat, full rights** |
| `/pd manhunt-2003-vr tandem force` | exit 0 | seat taken correctly |

So a working incantation exists — keep `tandem` **and** add `force` — but it is neither documented
nor what the block tells you to type. Driven from payload files with `hook_event_name` present
(fault 🔍 E), and with `$LANES_TANDEM_MARKER` pointed at a throwaway path; the real marker's size
and mtime were unchanged across the whole run (fault ✅ 4).

**Inherited in part.** The original guard blocks the same prompt with the same wording
`[verified-live 2026-09-10, n=1]`, so the tool-vs-original diff stays clean — but the original ships
no latch, so the *consequence* is new in 0.3.0.

**Not obviously one bug.** `commands/pd.md` says **"`/pd` goes first"**, so refusing a late joiner may
be the intended order rather than a defect; the live pair seated itself in that order, `/pd` at
12:23:06 and `/lm` 33 seconds later, and the seat was granted. What is **not** defensible either way
is the remedy text. Left open rather than fixed: `/pt` may not edit anything outside this file and
the checklist, and which half to change — the ordering rule, the message, or both — is the owner's
call.

**Suggested shape of a fix, for whoever takes it:** rebuild the remedy from the original tokens
rather than from `lane + force + jobs`, so `tandem` survives; and if late joining is meant to be
refused, say so in the message instead of offering `force`.

**Update, later the same day:** the user approved deleting the two-session tandem seat entirely
(`docs/specs/2026-09-10-one-session-reader-design.md`). Most of this fault dissolves with it — no
`tandem` keyword, nothing for the message to drop. ⚠️ **The token-dropping itself is real and
survives:** the same line also discards `skip:` arguments and any other modifier. Keep that half.

Known **limitations** — things that work as designed but are narrower than they could be — are
listed in the README rather than here.

**Closed 2026-09-10, in 0.4.0, in two halves.** The *latch* half **dissolved**: the tandem seat was
deleted (`docs/specs/2026-09-10-one-session-reader-design.md`), so there is no keyword for the
message to drop and no seat to land unlatched in — and blocking a `/pd` on a job a live `/lm` holds
is now simply correct. The *remedy* half was **fixed**: `lane-claim-guard.py` now rebuilds the
suggested command from the user's **own tokens** (`lane + " force " + <what they typed>`), so
`skip:` lists, `i launch` and any future modifier survive into the printed remedy. The ordering
question the entry left open ("is refusing a late joiner a defect?") is moot: there are no joiners.

### ✅ 9. The test lane's instructions were not updated for what 0.4.0 added

**Found** 2026-09-10, by `/pt`, just after 0.4.0 was committed; narrowed the same hour (the first
version overstated it — see the correction kept below). **What it did:** `commands/pt.md` had not
been touched since the day it was written. 0.4.0 deleted the tandem seat and added the **reader**
and `hooks/reader-guard.py`, and neither was named in the test lane's checklist. The guard itself
*was* covered — `hooks-test.sh` carries 16 reader-guard assertions — but nothing told `/pt` to check
the reader **live** (that a real `/lm` starts exactly one, announces it, relays findings, stays
read-only), nothing mentioned the `A1r` bar or `run-log.sh --reader`, and the framing ("a third
window beside `/pd` and `/lm`") described only the separate-projects shape.

**Fix (2026-09-15, 0.6.2):** `pt.md` gained a §4b — four live checks on the reader, plus the note
that a silent refusal log is the *expected* state and not evidence the reader never ran — §5 now
names `run-log.sh --reader` as part of re-checking the counts, the intro and §4 heading cover both
shapes, and the closing report line carries the reader count. **Prevented by:** nothing mechanical
— it is wording. What stops it recurring is the lesson written into the entry: *when a release
changes what the product does, the thing that tests it is part of the release.*

#### Kept from the original entry — the correction of 2026-09-10

The first version claimed a `/pt` run following the checklist would finish and report clean
*"having never once exercised the reader or its guard."* That was wrong and checkable in under a
minute: § 1 of `pt.md` runs both suites, and the hooks suite covers the guard
`[verified-live 2026-09-10, n=1]`. Recorded rather than quietly edited, because the overstatement
had the shape this plugin keeps punishing: a confident negative asserted without running the thing
that would have disproved it.

### ✅ 10. The reader bar counted sessions that ran before the reader existed

**Found** 2026-09-10, by `/pt`, the first time `run-log.sh --reader` ran against real history.
**What it did:** it reported **3 / 20 clean** where the true figure was **1**. The cutoff was a
bare hand-typed date, `SINCE="2026-09-10"` — but 0.4.0 shipped at **15:35:09** that afternoon
(commit `f0c6a4e`), so two `/lm` windows from earlier the same day (10:00 and 12:23, one of them
the very tandem pair 0.4.0 deleted) were counted as reader runs. A whole day of granularity hid a
15-hour gap. The output was entirely truthful line by line and the total was wrong — and it would
have been the README's headline number.

**Fix (2026-09-15, 0.6.2):** the default cutoff is no longer typed. `run-log.sh --reader` reads
the **exact commit timestamp** that first added `hooks/reader-guard.py`, from the plugin's own git
history. **One honest limit found while fixing it:** a plugin installed from the marketplace is a
plain versioned folder with **no `.git`** (`~/.claude/plugins/cache/<marketplace>/lanes/<version>/`,
checked 2026-09-15), so from an installed copy there is no history to read. For that case only it
falls back to `tools/reader-since.txt` — one ISO timestamp, committed once, to be touched again
only if the reader is ever rebuilt from scratch, never on a version bump. Either source is named in
the report. Re-harvested with the fix: **24 / 20**, the two pre-reader windows gone
`[verified-numerically 2026-09-15]`.

**Prevented by:** `smoke-test.sh` builds a throwaway board with one `/lm` window either side of
that exact moment and asserts the earlier one is **excluded** — the precise failure above — asserts
the date is read from git and printed as a full timestamp, asserts `reader-since.txt` **equals**
the git-derived value (so the fallback file cannot drift), and runs a `.git`-less copy to prove the
fallback fires and says so. 8 assertions, all passing `[verified-numerically 2026-09-15]`.

**The "no refusal log" wording** the entry also flagged is unchanged and still reads as a warning
about the wrong thing; it is cosmetic, and `pt.md` §4b now tells the tester what that silence means.

### ✅ 11. Every release after 0.5.1 was invisible to `claude plugin update`

**Found** 2026-09-18 on the dev PC, by the author trying to install the version the board said to install.
`claude plugin marketplace update tefmeister-plugins` succeeded, and then
`claude plugin update lanes@tefmeister-plugins` answered **"lanes is already at the latest version
(0.6.4)"** — while the repo was at **0.11.0** `[verified-live 2026-09-18, n=1]`.

**What it did:** the plugin's version lives in **two** files, and only one of them was ever bumped.
`plugins/lanes/.claude-plugin/plugin.json` went 0.5.1 → 0.11.0 across eighteen releases;
`.claude-plugin/marketplace.json` — **the file the installer actually reads** — still said `0.5.1`.
Its last touch was commit `1c6babc`, the 0.5.1 release itself. So the updater compared the installed
0.6.4 against an offered 0.5.1, correctly concluded there was nothing newer, and said so.

**Why it mattered more than it looks — three ways, and the third is the worst:**

1. **The failure is a success message.** Nothing errors, nothing warns. The updater says the
   reassuring thing, and the only way to notice is to know the real version independently.
2. **It silently ate six weeks of releases** — everything from 0.5.2 to 0.11.0, including the
   `[PD]`-visible ones the boards told people to install.
3. ⚠️ **It made a board claim false without anyone lying.** `STATUS.md` said the home PC was on
   0.10.0 and the dev PC owed an update. The dev PC then ran exactly the two commands it was told to
   and was told it was up to date. **A machine can now be recorded as updated when its updater
   refused to update it** — which is the standing "deployed is prose, not evidence" trap arriving
   through a new door. ⚠️ **The home PC's recorded 0.10.0 has NOT been re-checked against its real
   installed version** and should be treated as `[reported]` until it is; if it was installed the same
   way, it is not on 0.10.0 either.

**Fix:** `marketplace.json` now carries 0.11.0, and its description is copied from `plugin.json` so
the two cannot drift in wording either.

**Prevented by:** `smoke-test.sh` now reads the lanes entry out of `marketplace.json` and asserts it
**equals** `plugin.json`, beside the existing CHANGELOG and banner version checks — the three files a
release must move together. The assertion was proved to fail on the real defect by putting `0.5.1`
back and watching it report the exact sentence above `[verified-live 2026-09-18, n=1]`; the suite is
green with the fix. An installed copy carries no `marketplace.json`, so the check skips there and says
so, the same way the banner check does.

**No version bump.** Nothing the plugin *does* changed — this is the release metadata plus a test.
0.11.0 is now genuinely offered, which is the whole point.

**Also fixed, because it is the actual root cause:** `RELEASE-CHECKLIST.md` never mentioned
`marketplace.json` — not once, in 16 KB of checklist. Bumping only `plugin.json` was the documented
procedure, so eighteen releases followed it correctly. There is now a step for it.


### ✅ 12. The update check answered about a repo checkout, not about this machine

**Found** 2026-09-18 on the dev PC, running `/lanes:update` immediately after fault 11 was fixed.
The check reported `installed: 0.12.0` and `newer: false` — a clean "you are up to date" — while the
newest copy actually installed under `~/.claude/plugins/cache/` was **0.11.2**
`[verified-live 2026-09-18, n=1]`.

**What it did:** `update-check.py` set `PLUGIN_ROOT` to its own location
(`os.path.dirname(os.path.dirname(os.path.abspath(__file__)))`) and read the version out of that.
`/lanes:update` invokes it as `${CLAUDE_PLUGIN_ROOT}/tools/update-check.py`, and **for a marketplace
registered as a local directory Claude Code sets `CLAUDE_PLUGIN_ROOT` to the marketplace directory**
— a repo checkout. So the check read the repo's `plugin.json`, found no `cache` segment in the path,
concluded there was no marketplace at all, and compared the repo against nothing.

**Why it mattered:** it is fault 11's shape again, one layer up. The answer is `newer: false`, which
is the same answer a genuinely up-to-date machine gets, so there is no symptom to notice. Worse,
this one *reads* the reassuring value from a file that is by definition always current — a repo
checkout of the plugin is the newest version by construction, so it can never report an update is
needed.

**The general lesson, and it is the third time this estate has met it:** *a check that reports on
itself will always pass.* The fix is not care, it is making the thing under test a different object
from the thing testing.

**Fixed in 0.12.1** (`update-check.py`): `in_cache()` decides whether a root is an installed copy,
and `newest_installed()` walks `~/.claude/plugins/cache/*/lanes/*` to find the real one when it is
not. The JSON now carries `installed_root` and `ran_from_repo`, so the answer says which copy it is
about. `smoke-test.sh` asserts the discriminator against four paths; confirmed to fail against the
old code before the fix was kept.

---

### ✅ 13. The installer read a stale clone and called it "already at the latest version"

**Found** 2026-09-18, minutes after fault 12, while installing 0.12.0. The check correctly said
0.12.0 was available; `claude plugin update lanes@tefmeister-plugins` then answered **"lanes is
already at the latest version (0.11.2)"** `[verified-live 2026-09-18, n=1]`. Two commands, run in
the order the command file gives them, one promising an update and the next denying it exists.

**What it did:** the two halves read different things.

- `update-check.py` runs `git fetch` in the marketplace clone and reads the manifest from
  **`origin/main`** — so it sees a release the moment it is pushed.
- `claude plugin update` installs from that clone's **working tree**.

This marketplace is registered as `source: directory` pointing at one specific clone of the repo. The
0.12.0 release had been pushed from a **different clone root**, so the marketplace's clone was two
commits behind and its working tree still held 0.11.2. Everything reported success.

**⚠️ This is a standing hazard of the one-clone-root-per-lane rule, not a one-off.** The marketplace
can only point at one root; every other lane pushes somewhere else. So **any lane that releases the
plugin leaves the installer reading a stale tree** unless that root is pulled first. Nothing about
the lane rules is wrong — they partition working trees on purpose — but this is the one place where
a tool outside the lanes reads one of those trees directly.

**Fixed in 0.12.1** (`update-check.py`): `commits_behind()` measures the gap when the marketplace
source is a directory, and a `git -C "<clone>" pull --ff-only` is then prepended to
`update_commands`, so the pull is part of the update rather than a step someone has to know about.
`commands/update.md` also now says to re-check the version after updating rather than trusting the
installer's own summary. `smoke-test.sh` covers both the stale case and that a `github`-sourced
marketplace is *not* given a pointless pull; both confirmed to fail against the old code.

---

## Investigated, not a fault

### 🔍 A. Two hard errors in a port comparison

`unbound variable` and `command not found`, which looked exactly like a botched port. Cause: the
scripts were **rewritten while the test was still executing them**. Bash reads a script
incrementally and resumed at a shifted byte offset. Re-run clean, no errors.

Recorded because it is a convincing false positive, and because the lesson generalises: **do not
edit a script while something is running it.**

### 🔍 B. Two file ages differing by one day between two runs

Looked like the ported scanner disagreeing with the original. Cause: both files had been committed
at 19:11 and 19:12 five days earlier, and the two runs straddled that minute — so one saw 4 days
and the other 5. Confirmed against the commit timestamps.

Recorded because the honest response to a one-line diff is to find the cause, not to wave it away
as noise — and in this case the cause was checkable in about a minute.

---

### 🔍 C. A new command did not appear after being added

Not a fault in the plugin — a fact about developing one. An installed plugin is a **snapshot in a
cache**, so adding a command to the source folder changes nothing until the **version number**
changes; `claude plugin update` will otherwise report "already at the latest version" and do
nothing. Confusingly, `claude plugin details` reads the source and *does* list the new component,
so the inventory says yes while the running session says no.

**Bump the version whenever a component is added or removed.** Recorded here because the failure is
silent and the diagnostic output actively misleads.

### 🔍 D. A 134-line "difference" between the ported hygiene scan and the original

**Found** 2026-09-10, by `/pt`. The ported `gs-scan.sh` produced 213 lines where the original
produced 79 — the original's output was a strict prefix, which reads exactly like a port that
crashes half way through a check.

**Cause: the test harness judged a file that was still being written to.** The waiter polled
`pgrep -f gs-scan.sh`, which matches nothing under MSYS because the process shows as `/usr/bin/bash`,
so the wait fell through and the diff ran while the original was still on check 3b. Left to finish,
both runs produced 213 lines.

Recorded because this is fault ✅ 4's shape again — **the test was the dangerous thing, not the code
under test** — and because a prefix-shaped diff is the single most convincing false positive this
lane can produce. **Wait on the writer's own exit, never on a process-name guess.**

### 🔍 E. The `/pd` lock guard appeared to let a second session straight through

**Found** 2026-09-10. Driven by hand, `pd-guard.py` exited 0 for every prompt — including a second
`/pd` from a different session, which should have been blocked. The fixture suite passed at the same
moment.

**Cause: the hand-written payloads omitted `hook_event_name`.** The guard keys off it and correctly
does nothing without it; Claude Code always sends it. Re-driven with the field present, the whole
sequence is right: lock taken, second session blocked with a reason and exit 2, holder allowed to
continue, `/lm` unaffected, `force` steals and says so, `SessionEnd` releases.

Recorded because "the guard is dead" and "my payload was malformed" look identical from the outside,
and the fixture suite is the tie-breaker: **when hand-driving disagrees with the suite, suspect the
hand-driving.**

**It happened again the same day, fitting the tandem latch.** A hand-typed payload carrying a
Windows path is **invalid JSON** — a lone backslash is not a legal escape — so `json.load` raised
and the guard failed OPEN, looking exactly like a latch that does not work. The suite's own
backslash-path assertion passed throughout. **Twice now the tie-breaker has been right.** Drive a
hook from a FILE, not from a shell string.

### 🔍 F. Two more self-inflicted results from the same run

`emit_context.py` echoed a hook payload back as session context — it is a **filter**, not a hook entry
point, and `hooks.json` wires `board-brief`, which pipes the scan's output through it. Feeding it
hook JSON is not a path that exists.

An "unconfigured machine" test pointed `$LANES_CONFIG` at an empty file and still got a full board.
`read_conf` takes the first config that **defines the key**, not the first that exists, so it fell
through to the real one. That is the documented fallback chain working; reproducing C6 needs `$HOME`
moved, not an empty file.

Recorded together because both are the same error — **testing a shape the product never produces** —
and both cost more time than the real checks did.

### 🔍 G. Two tool comparisons that disagreed, on a board that moved underneath them

**Found** 2026-09-10, by `/pt`. `--next` and `--check` differed between the installed copy and the
original by whole lines, not wording: the original announced a tandem seat and listed a live claim,
the installed copy showed neither. That is the shape of a port that lost the claim filter — fault
✅ 1 exactly.

**Cause: the board gained a claim between the two runs.** The installed copy ran at 12:21, the
`/pd … --tandem` claim commit landed at 12:23:06 and the `/lm` claim at 12:23:39, and the original
ran after both. Confirmed from the commit timestamps, not assumed. Re-run back to back with a
same-copy control pair, the two agree on every line except the wording swaps.

Recorded because this lane runs beside live lanes **on purpose**, so a board that moves mid-run is
its normal condition rather than bad luck — and because "the ported tool lost its claim filter" is
the most alarming diff it can produce. **Always run the two copies back to back, and keep a
same-copy pair as the drift control.**


### 🔍 H. The ported tools and the originals have started to diverge, and it does not show

**Not a fault.** The design's § 7.5 warned that after 0.4.0 the plugin's `lane-claim.sh` and
`gate-scan.sh` would no longer match the originals in the user's own `claude-memory/tools/`, and that
the next `/pt` run would report a difference that is not one.

**Checked, and it has not happened.** The rendezvous was removed upstream too; one `--tandem` mention
survives in the upstream `lane-claim.sh` but changes no output. All four comparisons run against the
live board — `--brief`, `--next`, `--check` and the claim listing — differ only in the expected
wording swaps, each with a zero-line same-copy drift control `[verified-live 2026-09-10, n=1]`.

Recorded so the next run does not re-chase a divergence that was predicted but never arrived — and so
that if it *does* arrive later, there is a dated baseline saying when it did not.

---

## Still open

### Two PCs copying the same ideas leave a project repo stuck mid-rebase (found 2026-09-26)

**What happened.** `ideas.py sync --commit` ran on both PCs for the same ideas. Each wrote the same idea file with a
different `copied <date>` line, so the second PC's `pull --rebase` hit an add/add conflict and stopped. 24 project
repos on one PC were left mid-rebase, unnoticed for days. Every clashing copy was identical apart from that line;
they were resolved by keeping one copy. Nothing was lost `[verified-live 2026-09-26, n=24 repos]`.

**Fix to make.** Write nothing machine- or date-specific into the idea file, so two PCs produce byte-identical
files and git merges them silently. And have `git_commit` in `ideas.py` abort the rebase and say so when it fails,
instead of leaving the repo stuck.
