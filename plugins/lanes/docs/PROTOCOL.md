# The protocol

Six lanes, one board, and three rules that do the actual work. Everything else here follows from
them.

1. **Every file has exactly one lane that may edit it.** Reading is unrestricted.
2. **Anything crossing a lane boundary is a NEW file, never an edit.**
3. **One session per lane, one session per job.**

---

## 1. One writer per file

| Lane | Curates | Others may |
| --- | --- | --- |
| `/pd`, `/lm` | the project's working files, its notes, and `status/<project>.md` | drop into its `inbox/` |
| `/gr` | `<project>/external-research/` | drop into its `inbox/` |
| `/sr` | the shared cross-project library | drop into its `inbox/` |
| `/gs` | nothing — read-only everywhere | — |
| `/gates`, `/gate-watch` | nothing — read-only everywhere | — |

`/pd` and `/lm` are **the same lane**, split by whether the app is running. That is why they need
the live claim between them and the other lanes do not.

⚠️ **Because lanes share repos, the boundary is enforced by commit discipline, not permissions.**
**Stage only your own lane's paths. Never `git add -A` in a shared repo.** `git pull --rebase`
before pushing.

---

## 2. Hand-offs are create-only

A finding for another lane becomes a **new file** in that lane's `inbox/`:

```
inbox/YYYY-MM-DD-<lane>-<short-slug>.md
```

Date, author and slug, so **two sessions can never produce the same filename** — git merges
cleanly by construction rather than by discipline.

- **No session ever edits or deletes an existing inbox file** — not even its own from an earlier
  session. A non-empty inbox is a visible to-do, never a silent loss.
- **The owner drains its inbox at the start of every session:** fold each file into the curated
  docs, then delete it.
- **One ask per drop.** A drop that bundles three findings gets half-drained, and nothing shows
  which half.

### ⚠️ Drain by explicit list, never by glob

Record the exact filenames `ls inbox/` returns **before** folding anything in, and delete **only
those names**. Never `rm inbox/*`, never `git rm inbox/`, never stage `inbox/` as a directory.

The drain is a read-then-delete, so a concurrent session can drop a new file inside that window. A
glob deletes it unread — and because it was never committed, **nothing in git shows that a finding
ever existed.**

### Corrections point at what they replace

A correction is a **new file** carrying a greppable header line:

```
Supersedes: <filename, or doc §section>
```

Never an edit to the file being corrected. And before draining anything, **read the whole inbox
first** — `grep -rn "^Supersedes:" inbox/`. Draining oldest-first writes a claim into the library
and only then meets its withdrawal.

---

## 3. One session per lane, one session per job

**Per lane, per machine.** Clone roots partition lanes, not sessions. Two sessions of one lane land
in the same working tree and the same git index and fight over every git operation. It is slower,
not faster. Several projects in one session with several arguments is the supported way.

**Per job, across machines.** The live claim (see `BOARD-FORMAT.md`) serialises one project at a
time, with a 12-hour staleness rule and an explicit `force` override the user must type.

### Give each lane its own clone root

```
clones/          the live lane
clones-pd/       /pd
clones-gr/       /gr
clones-sr/       /sr
clones-gs/       /gs
```

Made with `git clone --local`, so the object stores are hardlinked and the extra sets cost almost
nothing. **Never operate in another lane's root.**

**Keep the roots complete.** A repo created or cloned into one root after the others were made is
invisible to every other lane, and nothing fails: a sweep reports on fewer projects than exist and
reads as a clean bill of health. `tools/root-sync.sh --fix` copies every repo that any root holds into
every root that lacks it (`--check` only lists the gaps). `/pd`, `/gr`, `/sr` and `/gs` run it first.
`[verified-live 2026-09-17, n=1]`: three sweeps found their roots missing 16-17 of 39 repos.

Why: the one-writer rule partitions *files*, but every git operation is *repo-wide*. A
`git pull --rebase` rewrites the entire working tree including another lane's uncommitted files;
`index.lock` collides however disjoint two sessions' paths are; a conflicted rebase leaves the tree
in a state a second session cannot detect. Separate roots make **the remote the only
synchronisation point**, and its ref updates are already atomic — a push either lands or is
rejected, and rejection means pull-rebase-retry against a private tree.

The trade-off is staleness: each root only learns what the others did by fetching. So **always
pull before drawing a conclusion about a repo's contents.** Auditing an unpulled clone reports the
state of that disk, not the state of the project.

### If you land in a conflicted shared root

**Nothing is lost.** Measured, not assumed:

| Step | Result |
| --- | --- |
| `git pull --rebase` (the default) against a dirty tree | **refuses outright** — the collision never happens |
| `git pull --rebase --autostash` | reproduces the incident: conflict markers, stash retained |
| then `git reset --hard` (git's own printed advice) | tree wiped, **stash survives**, `stash pop` fully recovers |
| then `git stash drop` too — the worst realistic case | **still recoverable** from the object store |

Work loss is structurally impossible short of `git gc --prune=now`. **Never pass `--autostash` in a
lane root** — it opts out of the guard git gives you for free. Do not "clean up" to make a conflict
go away, and never resolve a conflict in a file you do not own.

---

## 4. Claim hygiene

**Tag every durable claim with how well it is actually known** — next to the claim, not in a
preamble. These eight names are the whole vocabulary:

`[verified-live YYYY-MM-DD, n=K]` · `[measured YYYY-MM-DD]` ·
`[verified-numerically YYYY-MM-DD, n=K]` · `[compile-verified YYYY-MM-DD]` ·
`[inferred-static]` · `[reported]` · `[hypothesis]` · `[disproved YYYY-MM-DD]`

- **`n=1` is not verified.** Write `n=1` and let the reader judge. (`n=1` *is* enough for a
  **disproof** — one counter-example refutes a universal claim.)
- **An invented tag is worse than none:** it reads as a strong claim to a human and counts as
  untagged to every tool. Put the precision in the prose beside the tag, never inside it.
- **Untagged claims are treated as `[hypothesis]`.**

### The trap this exists to stop

**A fix that removes the symptom *and* stops the failing path from being exercised has proved
nothing about the cause.** Before writing "X caused it, because fixing X worked", ask whether the
failing path still runs. If it does not, the claim is a hypothesis however well the fix worked.

This whole section exists because a claim recorded as fact was wrong, and was acted on the next day
*because it read as settled*. The repo layout did not cause that; the missing provenance did.

### And after a tool turns out to have been broken

Re-check every conclusion drawn while it was in use. **A negative result is only evidence if the
test could have produced a positive one.**

---

## 5. Reporting

End every session by saying what the next step **requires**, in capitals, unprompted:

```
GATE: PD   — there is work that needs nothing running
GATE: FLAT — nothing further without the app
GATE: VR CLAUDE — nothing further until the hardware is connected (nobody need be there)
GATE: VR USER   — nothing further without a person actually using it
```

That claim is an **exhaustion** claim, so it has to be checkable rather than asserted: it is true
when the board holds no rows at a cheaper tag. Audit and re-date the block before saying it.

**Never trail off** into "that's probably everything for now". Either there is a cheaper item, or
there is a named wall. Both are answers; vagueness is not.

### Say which model the next step needs (0.5.0)

Whenever a session proposes or hands over a next step, it names the model tier that step needs, in
one line beside the gate line, with a few words of why:

```
GATE: FLAT — nothing further without the app
MODEL: STANDARD — a guided test, reading the log against a stated prediction
```

The person running the sessions picks the model before the work starts (`/model`); a session cannot
switch itself. Without this line they either run everything on the strongest model or guess.

| Tier | Use it for | At the time of writing |
| --- | --- | --- |
| `STRONGEST` | A problem that has already resisted several attempts; deriving behaviour or maths nobody has written down; a failure with no obvious cause; a design decision everything after it builds on. | Fable |
| `STANDARD` | Normal project work: guided test sessions, reading logs against a prediction, wiring together pieces that already work, static reading with a clear method, code from a settled plan. | Opus |
| `LIGHT` | Clerical work with no judgement calls: filing, saving and pushing, board tidying, re-running a known command. | Sonnet |

A session may write the current model's name instead of the tier (`MODEL: OPUS`) when the person
it reports to knows the names better than the tiers.

- **Getting the work to succeed outranks saving tokens.** When a step sits between two tiers, pick
  the stronger one. Under-powering a hard problem costs more sessions than it saves.
- **But do not spend the strongest tier where it does not help.** That is the point of the line.
- **Say when a step changes weight mid-way.** If a routine test turns up something baffling, say
  `MODEL: STRONGEST from here` rather than grinding on.
- When offering several next steps, give each its own line.

### Say it at the START of a session too, not only at the end (0.12.0)

The rule above only ever helped the **next** session. By the time a report is written, whatever
model was selected has already done the work — so a session that picks its own job can spend the
strongest tier on clerical work and only mention it afterwards.

**So: the moment a lane has picked its job and read the row, and before any of the work starts, it
prints one plain line naming the tier that row needs and whether it matches the model running.**
`/pd`, `/lm` and `/ms` all do this, whether the job was named or auto-picked.

⚠️ **It cannot come before the command is typed** — the pick needs a board read — so it lands a few
seconds in. Say so; do not imply otherwise. It is still the only moment when switching is cheap.

**The two mismatch cases are deliberately NOT symmetric:**

| what is running | what the session does |
| --- | --- |
| **weaker** than the job needs | **Stop and wait.** One plain line: the job, the tier it wants, what to re-type. Getting the work to succeed outranks saving tokens, and a hard problem answered badly costs more sessions than the pause costs minutes. |
| **stronger** than the job needs | **Say it in one line and carry on — never stop.** In the lanes where the person is away, a pause trades the whole session to save tokens, which is the wrong way round. Name the cheaper tier for next time, and if a different row on the same board suits the running model better, say which — but never silently swap the job. |
| matching | one line, carry on. No ceremony, no asking. |

⚠️ **One lane inverts the second row: a lane where the person is at the keyboard for every turn**
(`/ms` in the reference estate). A pause costs them seconds, not an hour, so stopping is cheap there
and worth doing on any real mismatch in either direction. Ask; do not decide for them.

Format: a plain single line at the start — the boxed grid below is for the **end** of the report.

### Make the two lines impossible to miss (0.5.1)

People skim long replies, and these two lines are the part they act on. Print them together as a
small two-row table near the end of the reply, gate in the header row, bold, with a fixed icon each:

```
| 🚦 **GATE: FLAT** | **NOTHING FURTHER WITHOUT THE APP** |
| --- | --- |
| 🧠 **MODEL: STANDARD** | ***a guided test, reading the log against a prediction*** |
```

Keep the icons fixed so the box is recognisable at a glance. Several next steps get one `MODEL` row
each, with the step named in a few words.

### The reply's own headings carry fixed icons too (0.19.0)

The gate and model box got icons in 0.5.1 because people skim. The rest of the reply did not, so a
session's answer opened with three or four bare headings that all looked alike, and the reader had
to actually read each one to find out which was the part that wanted something from them.

Give the standard three-part shape a fixed icon per heading, the same way the box has one:

```
🔧 **What I did**            - one to three plain lines
🎯 **What it means for you** - what changed from their side, or "nothing you need to do"
❓ **What I need from you**  - one block, or "nothing"
```

And for the section that does not always appear — something turned up that was not part of the job:

```
⚠️ **Worth knowing**
```

The icons are **fixed**, and that is the whole point. A reader who has seen two replies knows that
❓ is where their answer is needed and that they can skip to it; an icon chosen fresh each time is
just decoration and carries nothing. Same reasoning as 🚦 and 🧠 — recognisable at a glance, so the
reply can be navigated without being read end to end.

⚠️ **An icon is not a licence to write more under it.** The shape stays short. If the sections grow
to fill the extra visual weight, the icons have made the reply worse, not better.

_Asked for by the maintainer on 2026-09-20, marking the headings that still had none._

---

## 6. Code shape — small files, named numbers (0.7.0, 2026-09-17)

The rules above keep sessions from treading on each other's **records**. Nothing kept an eye on the
**code** they write, and it drifted the way long-running AI-written projects commonly do: three
hand-written files on one estate reached 5,600–6,800 lines, one Lua script sat at **exactly** Lua's
limit of 200 top-level locals (the next `local` anyone added would have stopped the mod loading),
and settings were scattered through the code as bare numbers `[measured 2026-09-17]`.

### Why it happens — the mechanics, so the rules make sense

1. **Every pass appends; no pass removes.** A session adds its probe, knob or fix as a new dated
   block in the file it is already working in. The superseded blocks stay, still wired to debug
   buttons. On the worst file, 60% of the lines were early tests nothing reached any more.
2. **Experiments ship in the production file.** A probe is quickest to write beside the code it
   probes, so tests, probes and the working path share one file and one namespace.
3. **Numbers are tuned where they are used.** Mid-debug, a distance or a timeout is edited in place;
   the session ends with the number still sitting inside a function, unnamed.
4. **Growth is fast and nobody measures it.** Several short passes a day each add a little. No
   single pass looks big, and no check looked at the total.
5. **Splitting feels risky mid-debug**, so it is put off — which makes the eventual split larger and
   riskier still.

### The rules

- **Size budget for hand-written source files: 800 lines soft, 1,500 hard.** When an edit would
  push a file past the soft line, split it first. A file already past the hard line gets split
  before anything else goes into it. Generated files are exempt, provided their header says they
  are generated — then fix the generator, not the output.
- **Split in its own commit, and prove it changed nothing.** A move-only commit, then the behaviour
  change in a separate one — never mixed. Prove the move against what was true before it: the
  build's exports, imports and strings (or an identical binary), every unit test at the same count,
  and for scripts a syntax check plus a check that every name the entry file used still resolves.
  The run with the app that confirms it is its own `[FLAT]` row.
- **Back up before restructuring.** Tag the pre-split commit (`pre-split-YYYY-MM-DD`), do the split
  on a branch in its own worktree, and merge only after the equivalence check and the `[FLAT]` run.
- **Experiments live apart from the working path.** A new probe or test goes in its own file,
  behind a named switch. **The session that disproves or supersedes it moves it to an `archive/`
  folder with a one-line README entry saying why** — archived, never deleted, and never left
  wired into the working file.
- **Numbers get names.** A distance, scale, timing, threshold, offset or address that someone might
  tune or that belongs to one build of the app is declared once, with a name and a comment, in one
  settings table per project (addresses: one table per app build). The code uses the name. A
  number changed while debugging is promoted to a name before the commit, not "later".
- **Mind the language's hard limits.** Lua: 200 locals per function, and a script's top level
  counts as one function; `luac -l -l` prints the count. Put new state in a table or a module
  instead of another top-level `local`.

### How it is checked

`tools/code-shape-scan.py` reports `OVER-HARD`, `OVER-SOFT`, `LUA-LOCALS` and `LOOSE-NUMS` across
every repo under a root. It is read-only. `/gs` runs it in its sweep; `/pd` and `/lm` run it on any
file they are about to edit, and a hit makes the split the first job of that session. Exclusions
for vendored code go in a `.code-shape-ignore` file at the repo root.

---

## 7. Work that only ONE machine can do (0.14.0, 2026-09-18)

If you work on two computers, some jobs cannot travel: an install, a config change, a build that has
to land on that disk, a test that needs hardware only one of them has. The obvious place to put those
is the shared board — and that is exactly where they rot.

**Why a note in a shared file is not a reminder.** Everything in `status/` and the open-actions block
is read by *every* machine. So a line saying "the other PC still needs this" nags **both** of them,
forever, and the one that can actually act has no way to tell its own rows from the other's. The
machine that can do nothing about it learns to skim past; by the time you are sitting at the machine
that can, the line has been background noise for a week.

A reminder has three properties a shared note does not: it is **addressed**, it **arrives on the
machine that can act**, and it **goes away when that machine acts**.

### The queue

```bash
tools/owed.sh                        # what THIS machine owes - silent when nothing
tools/owed.sh add HOME "<title>"     # raise one for another machine; body on stdin
tools/owed.sh list --all             # every machine
tools/owed.sh show <name>            # read one in full
tools/owed.sh done <name>            # clear one, then commit and push the board
```

Items live at `<board>/owed/<ROLE>/YYYY-MM-DD-<slug>.md`, where `ROLE` is a machine label from
`machine-assignments.tsv`. The `owed-brief` SessionStart hook prints **only this machine's** items,
and prints nothing when there are none — so its silence means something. `LANES_OWED=0` turns it off.

### Raise one automatically — do not wait to be asked

**Any lane, the moment it notices that something will not take effect until it happens on another
machine, raises an item there before it finishes.** Installs, registered servers, deployed builds,
config and registry changes, anything hardware-gated. The session that discovers it is the one that
knows why; a later session on the other machine will not.

Write two things into every item or it will never be cleared: **why it must be that machine**, and
**what observably proves it is done**. An item with no finish line is a note again.

### The rules that keep it safe

- **One file per item, create-only** — two machines raising work in the same minute cannot collide,
  by construction, for the same reason §2's inboxes cannot.
- **`add` refuses to address the machine you are sitting at.** Something you can do here is not a
  reminder; do it.
- **`done` takes one exact filename, never a pattern** — §2's drain-by-explicit-list rule. A glob can
  delete an item another session raised seconds ago and has not committed, and then nothing anywhere
  shows it ever existed.
- **The tool never commits.** It writes one file, or deletes one, and says to save it. A tool that
  commits inside a shared repo is how an unrelated lane's work gets swept into someone else's commit.
- **The check reads `origin/main`, not just this disk**, because an item raised elsewhere arrives only
  through git. An item on the remote but missing from this clone is reported as exactly that, with a
  nudge to pull — never as nothing.

## 8. Can a rule REACH the session that needs it? (0.15.0, 2026-09-19)

Every other check in this plugin looks at the **records** — confidence tags, inbox drains, board
blocks, code shape. This one looks at the **rules themselves**, and it exists because on this estate
a rule was written down correctly and still failed to arrive for fifteen days.

### What happened

The user gave a design instruction at the start of one project: *mod the game as natively as
possible*. It was filed the same day, in the right repo, with their words quoted and the reasoning
intact. Fifteen days later they had to give it again, because in between **not one session applied
it** — and the session that finally went looking found it only by grepping the body text.

It was not lost, and nobody ignored it. Three dull mechanical reasons:

| Fault | What it means | The real example |
| --- | --- | --- |
| **REACH** | the rule lives only in a file the harness does not auto-load | the project's `CLAUDE.md` said to *"skim as needed"* — so a rule governing every design decision depended on somebody deciding they needed it |
| **TITLE** | the heading carries none of the words a session would search for | it was headed *"Reach for the deep end"* — not *native*, not *C++*, not *Lua*, not *script* |
| **SPLIT** | the same subject is stated in full in two files, free to drift apart | the save-table rule had two complete copies |

⚠️ **The general shape is worth naming, because it is not specific to this estate:** an instruction
given conversationally is filed in the words it was *given* in, and those are rarely the words it
will be *looked for* in. The person giving it is describing a feeling; the session reading it back
is looking for a decision. The filing has to translate between the two.

### The rules

- **A universal rule belongs in the file that is ALWAYS read** — or, if it is too long for that, a
  one-line pointer to it does. Pointers, never second copies.
- **A heading must carry the words somebody would search for when the decision is live.** Write it
  for the reader who does not yet know the rule exists. `C++ OR LUA?` beats `Reach for the deep end`
  even though the second is better prose.
- **One subject, one full statement.** Everywhere else points at it.
- **When you add a universal rule, add its pointer row in the same commit.** A rule and its route
  are one change, not two.

### How it is checked

```
python tools/rule-reach-scan.py \
    --always <file the harness auto-loads> \
    --rules  <file of standing rules that it does not> \
    [--keywords extra-words.txt] [--json]
```

It reports the three faults separately and exits non-zero if any fire. `--keywords` widens the
findable vocabulary for an estate with its own jargon; widening it to silence a genuinely vague
heading is gaming the check, and the heading should be rewritten instead.

**Proof it can fail:** `tools/tests/rule-reach-fixture.sh` plants each fault in a throwaway pair of
files and asserts the scanner names it — including the literal `Reach for the deep end` heading that
started this. 8 checks, 0 failed `[verified-numerically 2026-09-19]`. It also asserts that a good
heading is left alone, so the checker cannot pass by flagging everything.

⚠️ **`--always` is per-harness and has no sensible default.** Point it at whatever your setup
actually loads every session; if you point it at the wrong file the scan is meaningless in the
quietest possible way.

## 9. A correction is a request until somebody drains it (0.16.0, 2026-09-19)

Section 8 asked whether a **rule** can reach the session that needs it. This one asks the same
question of a **correction**, and it comes from the same week and the same kind of failure.

### What happened

A research pass established that a sentence in a project's engine dossier was false, and filed an
inbox drop saying so. Two later hygiene sweeps re-flagged it. **Fifteen days and four flags after
the first, the sentence was still there, still false, and still serving as the stated evidence for
a live design decision.**

Nobody ignored it. Three things made it close to inevitable:

| Why | What it looks like |
| --- | --- |
| **A correction looks exactly like a contribution** | draining an inbox means reading a folder and folding it in; nothing marks one file as *"something you published is false"*. One bundle was **half-drained** — its tag half applied, its date half not — and nobody noticed for two days |
| **Volume hides it** | five undrained drops in that repo, thirty across the estate. A live falsehood was printed at the same volume as a research note |
| **Age is the wrong alarm** | *"this drop is N days old"* says nothing about whether the owner has been here, and nothing at all about whether the claim is still wrong |

### The rule

A correction aimed at a **curated document** carries one extra plain header line per false string:

```
Still-wrong: engine-research/ENGINE-DOSSIER.md :: last activity 2019-11-23
```

Path relative to the repo root, string matched literally, quoted the way the target actually has
it. Plain, never bolded — a bolded header renders identically to a human and is invisible to a grep.

⚠️ **A drop superseding another inbox file does not need one.** Draining both together resolves
those, and the sweep's supersession check already pairs them.

### How it is checked

```
python tools/inbox-correction-scan.py <repo-root> [<repo-root> ...] [--json]
```

It reports **LIVE FALSEHOODS** — the correction names a string and the target still contains it —
separately from **UNVERIFIABLE** drops, which correct a document but never say what must go. Exit
1 when anything is live.

**The whole point of the design is the change of question.** *"Has anyone drained this yet?"* is a
nudge, and competes with twenty-nine other nudges. *"Is the falsehood still live?"* is a **fact**,
and a fact can be escalated above the noise. ⚠️ It also means a drop that only states what is
**right** is weaker than one that states what is **wrong, verbatim** — only the second can be
checked by anything other than a human re-reading the whole document.

**Proof it can fail:** `tools/tests/inbox-correction-fixture.sh` — 12 checks, 0 failed
`[verified-numerically 2026-09-19]`. It plants the real Far Cry 2 shape and asserts the scanner
names the string, the target and the drop; asserts it goes quiet once the string is gone; asserts
an unverifiable drop is nudged but **not** called a falsehood; asserts an inbox-to-inbox
supersession is left alone; and asserts a missing target is reported rather than silently passed.

⚠️ **The tool is inert until drops adopt the convention.** On the day it shipped it reported zero
across seven repos — correctly, because no existing drop carried a `Still-wrong:` line. A checker
with nothing to check is not evidence of a clean estate, and should not be reported as one.

---

## 10. Handing a job to the person (0.18.0, 2026-09-20)

A `[USER]` row means a person has to do something the session cannot. Nearly always that person is
**not** a programmer, is wearing or holding something, and is reading on a phone or a second screen
with their hands full. What they get handed decides whether the answer comes back usable, comes back
wrong, or does not come back at all.

**Write it as numbered steps, in the order they happen, one action per step.** Not a paragraph
describing what you would like to find out.

### What a usable set of steps contains

1. **What must already be true before step 1.** State the preconditions as their own line. The most
   common wasted run is someone doing every step correctly with the wrong thing in their hands.
2. **Exactly what to run or press**, by its real name, spelled as they will see it.
3. **How long to wait, and what not to do while waiting.** If something finishes visibly before the
   process actually ends, say so — otherwise they will reasonably stop early. ⚠️ And check the
   reverse: if a step tells them they need not wait, make sure nothing important happens after the
   part they will see.
4. **A baseline before any variant.** "Is it better?" is unanswerable without "than what?", measured
   minutes earlier by the same person in the same place.
5. **The question, in their words, and what to IGNORE.** A test usually changes several things at
   once and only one of them is being asked about. Name the others and say to disregard them.
6. **What the failure modes look like**, each with what to do about it. Not just the pass case.
7. **Permission to answer vaguely.** "About halfway up" is a real measurement from a person holding
   a controller. Asking for a number they cannot produce gets either a guess or silence.
8. **How to put it back.**

### ⚠️ Writing the steps out is a TEST OF THE TOOLING, not just communication

This is the part worth keeping, and it is why this section exists rather than a style note.

On 2026-09-20 a three-way live A/B was prepared for a wearer: a baseline script and two variants.
Writing the numbered steps out — specifically step 8, *"how to put it back"* — exposed that the
**restore script undid only one of the two settings the variants changed.** Running the baseline
after the second variant would have left that variant half-applied, so the baseline and the variant
would have produced **identical results** — which is precisely the answer the test existed to
distinguish. The session would have concluded "no difference" and been wrong, with nothing in any
log to show why.

Nothing else had caught it. The scripts worked, ran cleanly, and reported success. **The defect was
only visible from the point of view of the person following the steps in order.**

So: write the steps **before** the run, not as a summary afterwards, and walk them yourself against
what the tooling actually does. A step you cannot write is usually a step the tooling cannot take.

### Put them in a file where the work happens

Leave the steps as a plain-text file beside the thing being tested, as well as in the reply. Someone
mid-test cannot scroll back through a conversation, and by the time they need step 12 the message
containing it is far above whatever arrived since. Commit that file with the scripts it describes,
so the two cannot drift apart.

### What to ask for back

Name the comparisons explicitly, one line each, in the order you want them. Then invite anything
else they noticed — a wearer's unprompted "it barely shows on the left side" has repeatedly been
worth more than the measurement that was actually requested.

---

## 11. Before you build a lever, say which step runs LAST (0.21.0, 2026-09-20)

You have traced how something works, you can see the value you want to change, and you know which
function carries it. **Say out loud, in writing, where your change lands in the ORDER of what happens
— and whether the thing you want to affect has already been decided by then.**

This sounds too obvious to be a rule. It is here because skipping it cost four builds and five live
test rounds in a single evening, with a correct trace sitting in the notes the whole time.

### The worked example

A weapon scattered its shots when fired from the hip and was accurate when aimed. A trace found the
function that carries the scatter: it is handed two rotations that differ by the exact scatter angle,
and they are identical on an accurate shot. A hook was built to make the two equal.

**It worked perfectly and changed nothing.** The log is unambiguous — `scatter 11.188 -> 0.000 deg
APPLIED` — and the shots stayed random.

The reason was in the same session's own trace, written down hours earlier: the call order put
**"make the projectile" before "the function that carries the scatter."** The projectile was finished
before the hook ran. That function reports the scatter; it does not decide it. Its numbers track the
aim state beautifully, which is exactly why they *measure* so well and why changing them achieves
nothing.

**The evidence was not missing, unclear, or contradicted. It was read, recorded, and then built on as
though the last step were the first.**

### The rule

Before writing a lever, write one line:

> *"This runs at step N of M. The thing I want to change is decided at step K. N is before/after K."*

If N is after K, you are not fixing it, you are annotating it. Stop and move upstream.

### Three companions, each from the same evening

- ⚠️ **A test must be able to tell "no effect" from "wrong choice."** Two attempts failed with
  identical symptoms — the value was unchanged either way — and the sessions could not distinguish
  "the write missed" from "the write landed on the wrong one of two candidates." Build the lever so it
  **proves its own effect**: measure, act, then RE-MEASURE and log both numbers. A lever that cannot
  report whether it did anything costs a round trip to a person every time it is wrong.
- ⚠️ **A guard must not be more dangerous than the thing it guards.** A safety check was added around
  a 16-byte write into memory that had already been read successfully for an hour. The check reached
  into the framework's *type metadata* through a cast the framework's own header says is invalid, and
  **crashed the application on the first call — before the write it was protecting ever ran.**
  Validate the **data you are about to touch** (does this look like the thing it should be?), not the
  framework's description of it. And make "switched off" genuinely inert: that build did its fatal
  checking *before* reading whether the feature was even enabled, so a copy sitting at "off" was still
  unsafe to use.
- ⚠️ **The bottleneck is usually reading what you already collected.** Five times in three days the
  answer was already in gathered evidence: a filename that stated the result, a number omitted from a
  summary of the output containing it, a field on line 73 of a dump that was quoted from line 71, a
  method listed six lines above the line being cited, and finally the call order above. **Volume hides
  things, and a summary written by the same session that gathered the data inherits its blind spot.**
  Before collecting more, re-read the last thing you collected **in full**, not the part you
  summarised.

### Why this belongs with the claim tags rather than with style

§4 asks how well a claim is known. This asks a different question about the same claim: **not "is this
true?" but "does this being true imply what I am about to do?"** Every claim in the worked example was
correct. The trace was right, the measurement was right, the write landed. The conclusion drawn from
them was still wrong, and no confidence tag would have caught it, because nothing was overstated —
only mis-sequenced.

## 12. Nobody's name is written down, except the one they chose (0.22.0, 2026-09-24)

**The rule.** In everything a session saves or publishes - notes, boards, inbox drops, commit
messages, READMEs, release notes, issues, file and folder names - the person using the machine is
**"User"**. If they chose a display name in `/lanes:setup`, they are that name, and only that name.
Never written, even when visible: their real name, login or account name, e-mail address, machine
or host names, home-folder paths. Other people appear only under a public handle they published
themselves (a tool author in credits, say), never under a name met privately. Talking to the person
in the chat itself is not affected; this is about what others can read later.

**How it reaches every session.** A session-start hook (`hooks/name-rule`) prints the rule, filled in
with the chosen name, into every session - so no lane, command or future rule has to remember it.
It has no off switch on purpose: a privacy rule that can be switched off is a suggestion.

**Where the name lives.** `display_name = ...` in `lanes.conf`, read and written by
`tools/display-name.py` (`set`, `clear`, `rule`). Letters, digits, spaces and `. _ -`, up to 40
characters; anything else is refused rather than mangled.

**Why one rule instead of guard lists.** Until 0.22.0 the plugin's own repo kept a list of the words
that must never be published - which meant publishing the list published the words. A default of
"User" for everyone, plus one name the person chose to make public, needs no list: there is nothing
secret to protect because nothing personal is written in the first place. `tools/scrub-scan.py` still
checks the shapes a leak takes (home paths, e-mails, session ids, this machine's name); any extra
words a maintainer wants it to refuse go in a **private** file on their own machine
(`~/.claude/lanes/never-publish.txt`), which is never part of the plugin.
