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

**Layout (0.42.1, 2026-10-03, user-directed): the two boxes go at the TOP of the write-up and the text after them,
ending on the "what I need from you" block.** The person reads the end of the reply in the terminal; with the boxes
last, the instructions sat above two tall tables and had to be scrolled up to. Order (0.42.2): close-out box (+ its
one-line notes) → gate/model box, right above the text → what was done → what it means → anything worth knowing → what is needed from the person, last.

End every session by saying what the next step **requires**, in capitals, unprompted:

```
GATE: PD   — there is work that needs nothing running
GATE: FLAT — nothing further without the app
GATE: VR CLAUDE — nothing further until the hardware is connected (nobody need be there)
GATE: VR USER   — nothing further without a person actually using it
```

That claim is an **exhaustion** claim, so it has to be checkable rather than asserted: it is true
when the board holds no rows at a cheaper tag. Audit and re-date the block before saying it, and read the board's lines above the block as well:
a fact there (where the repo is cloned, which PC has what) that the session found untrue is fixed
the same session, because nothing else ever re-reads it.

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

### The close-out box under it (0.40.0)

Until 0.39.1 the report ended with three pieces in three styles: a hand-written save table (one row per
repo pushed), the Inspector's sentence, and the HANDOVER line in capitals. The user asked for the end of
the report to be refurbished now that all three exist. It is now **one table in the same shape as the
gate/model box**, printed by `tools/handover.py close` from facts, so no row can be faked, and pasted
unchanged, first, with the gate/model box right under it (0.42.2: the gate/model box sits between the close-out box
and the text, so the next step is read together with the instructions):

```
| 🔦 **SAVED** | **EVERYTHING ON THIS PC IS ON GITHUB** |
| --- | --- |
| 📦 lanes-plugin | pushed · 2 new commits |
| 📦 the other 61 repos | nothing to push |
| 🔍 Inspector | 3 found · 3 fixed · 0 kept · 0 for later · 0 unanswered |
| 🔒 Claim | none held |
| 🖥️ PC1 (HOME) | last saved 21 h ago, ended SAVED |
```

- **The headline word is the signal, and the box prints after every session.** Before, the save table's
  *absence* meant "nothing was pushed, go save"; that inference needed the table to be left out of every
  read-only reply, and it only spoke for this session's clone root. Green `SAVED` now means every clone
  in every lane root is on GitHub; red `NOT SAVED` names the repo in the headline and means "save first,
  then end". A box that could not look says `UNKNOWN`, never `SAVED`.
- **Pushed rows come from a snapshot, not from memory.** `handover.py start` (the session-start hook)
  writes every repo's HEAD per session to `lanes-sessions/` beside `lanes.conf`; `close` lists each clean
  repo whose HEAD moved since, with how many new commits. The handover light's own board reports are
  not counted. With no snapshot nothing is claimed as pushed.
- **A problem repo gets a ⚠️ row**, a held claim gets a ⚠️ row, an unanswered Inspector note puts ⚠️ in
  its row: everything that still wants something from the person carries the same mark.
- **The Inspector's row prints even when it says "off"**: its absence would hide whether the Inspector is
  taking part (0.38.0, user-directed).
- **Under the box, one plain line each** for anything left unsaved on purpose and why, and the gate check
  result if an `OPEN` block was edited. Those are judgements; the box holds only facts.
- `handover.py check` still prints the old one-line form for scripts and hooks.

Checked by `tools/tests/handover-fixture.sh` (red and green boxes, the pushed row with its count, the
claim row both ways, the other PC's row, no path in the output, `UNKNOWN` with no setup).

### Talk, don't file: a short answer is just a few plain lines (0.57.0, 2026-10-10)

The headings, icons, numbers and boxes below are for **write-ups**: the end of a session, a test result, anything the
person will come back to. Everything else is conversation. A reply that is one short answer (a yes or no, an opinion,
a quick fact, "got it, waiting for you") is two or three plain lines with no headings, circles, numbers or boxes, the
way you would answer a person sitting next to you. Formatting a one-line answer as a report makes the exchange feel
like paperwork and slows both sides down.

_Asked for by the maintainer on 2026-10-10: "speaking to you is way more natural and i feel like i got a little too
much into putting things in order i forgot to slow down a little."_

### No "you're right": check, then say what you found (0.71.0, 2026-10-15)

When the person states, corrects or doubts a fact, the session does not open with "you're right" (or "you're correct",
"good catch"). It checks first and says what it found: "I checked: it is actually ...". When the fact cannot be checked
from where the session is, it asks one short question instead. When both sides were partly right, or both wrong, it
says exactly that. Only after checking, and only when it genuinely agrees, it says "agreed" or simply states the fact.

An automatic "you're right" reads as a checked answer when nothing was checked, and the person then builds on it. The
case that prompted this: a session said "you're right" about another PC's plugin version, and the person then found
they had not been right after all. Delivered to every session by the `talk-rule` session-start hook, like the naming
rule; no off switch.

_Asked for by the maintainer on 2026-10-15: "a lot of times when you say that i'm right, i'm actually not or we are both
right or wrong ... if you really have to say the i'm right, instead use - agreed - or something."_

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

**Two more fixed icons (0.48.0, 2026-10-07):**

```
🎬 **Recorded**   - what was recorded this session, how long, and where the file went
🎮 <project>      - in front of each project's name whenever a reply lists more than one project
```

A recording is something the person will want to find and use (progress videos), so it gets its own
heading instead of hiding under 🔧. And when a reply covers several projects, 🎮 in front of each name
lets the eye jump from one project to the next. Use 🎮 for any project, game or not; the icon marks "a
project starts here", not "this is a game".

_Asked for by the maintainer on 2026-10-07._

**The recorders (0.55.0, 2026-10-10):** `tools/obs-rec.py start <exe> <label> --game <project>` records only that window
and its sound (Windows Graphics Capture + the program's own audio, never a screen capture), `stop` and `done` end it and
put your OBS profile back. `tools/obs-autorec.py install` records any fullscreen game by itself. Both check the picture
every 10 s while recording and reconnect to the window after 30 s of black, so a capture that missed the window at start-up
does not run on black for the whole session. Since 0.72.0 `start` also records the OpenXR Simulator's preview window as a second file (`<label>_second_...`), adding it by itself when it opens later; `sim <exe>` says whether it is up.

**One more fixed icon (0.50.0, 2026-10-08): the tick that ends a hold.**

```
✅ **You can stop**   - the FIRST line of the reply, the moment the session has what it needed from a held test
```

Some tests need the person to hold something until the session has captured enough: controllers up,
the rifle on the sky, a pose, a button, a window in a certain state. From their side there is no way
to tell when "enough" has arrived; they hold until told, and a reply that opens with analysis keeps
them holding through all of it. So the tick comes first and alone, before any reading or thinking is
written down, and it means exactly one thing: lower the controllers, let go, relax -- the rest of the
reply needs nothing more from your hands. Print it even when the next question follows at once; the
question is for their eyes or their words, not their arms. If the capture failed and the hold must
go on, say that instead, in one line, so the hold is never silent.

_Asked for by the maintainer on 2026-10-08, after holding a rifle on the sky in the headset while the
session saved pictures and said nothing about when it had enough._

**The same tick for the app itself (0.56.0, 2026-10-10): say when it may be closed.**

```
✅ **You can quit the game now.**   - the FIRST line of the reply, the moment the session no longer needs the app open
```

When the person runs the app (a headset test, `/ms`), they cannot tell whether the session still wants it open to
read its log, or whether closing it would lose something. So: while the app is needed, the request ends with "keep it
running"; and the moment it is not (the log is read, or a change needs a restart), the reply opens with the tick on its
own line, adding the reason in a few words when there is one ("the fixes need a restart"). Say "game" or the app's
own name, whatever the person calls it. Never leave them guessing either way.

_Asked for by the maintainer on 2026-10-10: "it is such a relief to know that something is ok to turn off."_

**And the same for anything left running in the background (0.62.1, 2026-10-12).** Claude Code shows a background
shell as still running after the session started it, and from the person's side there is no telling whether closing
the session would cut off something important. So every write-up that ends a stretch of work says, in one line under
the close-out box, what is still running and whether it matters:

```
🐚 Nothing of this session is still running: safe to close.
🐚 Still running: the build (about 3 minutes more). Wait for it before closing.
🐚 Still running: the BeG0nE rider. It is meant to stay on and is not tied to this session: safe to close.
```

Name each task in plain words, and check before writing the line: a task whose finish was never reported is
"still running" until the session has looked. A background task the session no longer needs is stopped, not left.

_Asked for by the maintainer on 2026-10-12: "please add a check that tells the user if the shell is still doing
something important or can just be closed down."_

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

### The person's word clears it, on any machine (0.65.0, 2026-10-14)

What happened: an app was installed and tested on the home PC, its reminder was never cleared there, and
the other PC kept treating it as missing. **When the person says a reminder's job is done on the other
machine, the session that hears it clears it straight away**, quoting them:
`owed.sh done <name> <ROLE> "<their words>"`, then commits with those words in the message. Their report
is the proof (they were there; we were not). Without the words, `done` refuses another machine's item.
Before planning work around "the other PC still needs X", run `owed.sh list --all` and `installed.py list`,
and ask if the two disagree with what they have said.

### Which of our apps each PC has (0.65.0)

`tools/installed.py` keeps one small note per PC at `<board>/installed/<PC name>.json`: which of our own
apps it has, at which release. Install tools write it (`hand-freeze.py install` does), and every session
start looks at this PC, updates its note if anything changed, and prints one line for each app another PC
has that this one does not, or has at a different release. Silent when they match. Like `owed.sh` it never
commits; the close-out box shows the note as unsaved until the board is saved.

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

**If the step asks them to HOLD something** -- a pose, a button, the controllers up, a camera on one
spot -- say in the step how long, and the moment the session has what it needs, print `✅ **You can
stop**` as the first line of the reply (0.50.0; the icon list in §5). Never let a hold end only
because they gave up.

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

**PCs have plain names too (0.24.0).** A claim or reminder has to say which PC wrote it, and it says
so with a name like PC1 or one chosen in `/lanes:setup`, never the computer's own name.
`tools/machine-name.py` keeps it, and the board's `machines.txt` stops two PCs sharing one. Until
0.24.0 the computer's name was written; an outside audit caught it.

## 13. Ideas are filed first, and never lost (0.23.0, 2026-09-26)

**What it is for.** People have ideas away from the keyboard. They write them into their ideas repo's
`DUMP.md`, often from a phone, as `[project; part] the idea`. Until someone files them they help nobody,
and asking the person to do the filing is asking them to be a clerk.

**How it runs by itself.** A session-start hook (`hooks/ideas-brief`, running `tools/ideas.py check`)
looks at the dump and the repo's open issues. When anything waits, it tells the session to file it
**first**, with `/lanes:ideas`, before its other work, unless the person asked for something
time-critical. Silent when nothing waits, and off until `ideas = ...` is set in `lanes.conf`.

**The rules that keep the person's words safe.**

- **Capture is lossless; filing is a separate pass.** Every waiting line is copied verbatim into a
  new file in the ideas repo's `inbox/`. That folder is append-only. Filing can be wrong and fixed
  later, because the original words are always there.
- **A line leaves the dump only if it is already in an inbox file.** `ideas.py clear --from
  inbox/<file>` enforces it, so a line typed while a session is filing survives. It is the same reason
  inboxes are drained by explicit list (§2).
- **Only the person settles or drops an idea.** Sessions file, describe and judge feasibility, and say
  out loud when a verdict was not checked against the real project.

**How ideas reach the work.** `repos.tsv` in the ideas repo maps each page to project repos (`*` for
every active one, `-` for none yet). `ideas.py sync` copies undecided ideas into `<repo>/ideas/fresh/`;
`/pd` and `/lm` show them as a numbered list at the start; `ideas.py pick` keeps the chosen numbers and
drops the rest from that project, logging both. Silence is not an answer: nothing is dropped until the
person replies. Checked by `tools/tests/ideas-fixture.sh`.

## 14. Every change is a numbered build, on every PC (0.26.0, 2026-09-27)

**What it is for.** Finding what broke needs the exact earlier files, and a build that only exists on
one PC cannot be tested on the other. Both happened: a picture turned upside down some time after a
good run and the good build had been overwritten, and changes were tested on one PC with nothing on
the other to compare against. The person asked for it three times, the last in these words: *"each
new version, even the smallest change gets a new version of the mod ... and it also has to be pushed
on github, so the mod version is always in sync between the dev and home pc"*.

**How it works.** `tools/builds.py`, switched on by `builds = <clone of a private repo>` in `lanes.conf`.
Each project has `<builds>/<project>/PROJECT.conf` naming its app folder and which files in it are ours.
`snap` copies every file of ours into a new folder `v<series>-bNNN - <title>/` with a hash list and a
`CHANGES.md` (what changed since the last build, why, and later what was seen), adds a line to
`INDEX.md`, commits and pushes. Git stores an unchanged file once, so a full copy per build costs only
what changed. `result` fills in what was seen. `which` says which build the app folder holds right now.
`restore` puts one back, and saves the current folder first if it matches no build.

**The rules.**

- **The smallest change is a new number.** A file in or out, a setting, a rebuilt binary. Snap straight
  after the change and before the test, so the result has a number to belong to.
- **Never overwrite, never delete.** The tool has no delete. Old builds go only when the person says
  the project is finished.
- **Numbers never clash between PCs.** `snap` pulls before it numbers. If the other PC pushed in between,
  the push is refused; the tool undoes its own commit (keeping the files), takes the other PC's build,
  moves its own to the next free number and pushes again. No merge is ever needed.
- **What must not be published stays on the PC.** Files made from the app's own data are listed under
  `local_only`; they are copied and hashed but never committed, and `restore` on the other PC names
  exactly which ones it lacks. Files over 95 MB go up as a release asset with a stub left in the folder.
- **Drift is noticed at session start (0.28.0).** `hooks/builds-brief` runs `builds.py check`: for each
  project whose app folder this PC names in `lanes.conf`, it warns when the folder is gone, when it matches
  no saved build, or when a newer build is saved. Silent otherwise. It prints project and build names only,
  never a path, machine or person. `LANES_BUILDS_CHECK=0` turns it off.
- **Going back on purpose is not drift (0.32.0).** Test builds that did not work come back out, so the app
  folder often holds an older build than the newest saved one. `builds.py back <project> <N> "<why>"` (or
  `restore ... --why "..."`) writes one line to `<project>/HELD.txt`, and `check` stays silent while the
  folder holds that build. A build saved after the note is still reported: that one may really be missing.

- **One folder per feature (0.46.0).** The person, 2026-10-06: *"make separate builds of every different feature
  we work on, so all the ladder climb stuff is stored in a different place than running stop and so on, so it's
  easier to navigate different features within the mod"*. `snap --feature "Ladder climb"` saves the build as
  `<project>/Ladder climb/v<series>-bNNN - <title>/`. The numbers stay ONE sequence across every folder, so a
  number still names exactly one build, and `which`, `restore`, `result` and `check` find it wherever it is.
  `features <project>` lists the folders; `list <project> --feature "..."` lists one. Each feature's source
  belongs in its own file too (§6), so a feature can be read, tested and taken out on its own.
- **The app's originals are saved before anything of ours changes them (0.46.0).** The same day: *"add a folder
  that saves all the vanilla files before you change anything within them ... so reverting back to a working game
  is always doable, even late into modding"*. Builds keep every version of OUR files; a file of the app's own that
  a mod overwrites was kept nowhere. Now: before overwriting, editing or deleting any file the app shipped,
  `builds.py vanilla <project> <path>` copies it to `<project>/_vanilla/`. The first copy wins and is never
  overwritten; a file that already matches one of our builds is refused (it is not the original any more).
  **The copies never leave the PC** (they are the app's own files): the folder's `.gitignore` keeps them out and
  only the hash list is pushed, and any build file identical to a saved original is kept out of git as well.
  The other PC hears at session start that an original is saved elsewhere but not on it, and `vanilla --fill`
  saves it there while that PC's file is still untouched. `vanilla-restore <project> --yes` takes every file of
  ours out and puts every original back: a plain, working app at any point (the folder is saved as a build
  first if it matches none). `restore` also puts an original back when the build it restores no longer
  replaces it.

Checked by `tools/tests/builds-fixture.sh` (two PCs on one remote, including a same-number race, feature
folders and the originals; 75 checks).

## 15. (retired) Mint: the private copy of the app (0.27.0 to 0.42.2; removed in 0.43.0, 2026-10-04)

From 0.27.0 the plugin could keep the app's real install untouched and do all modding in a private copy
of it (`/lanes:mint`, `tools/mint.py`, `mint_*` keys in `lanes.conf`). The person who asked for it took it
out on 2026-10-04, unsure whether it was breaking things; by then the project it was made for had already
gone back to modding the real install. Modding happens in the app's own folder again, and `builds.py`
uses `builds_app.<project>` (or the project's own setting) as the app folder. Leftover `mint_*` and
`work_in_original.*` lines in `lanes.conf` are ignored; delete them. A copy folder made earlier is
the app's own files: it stays on that PC, and only the person decides whether to delete it.

## 16. The Inspector: every code edit is looked over (0.37.0, 2026-09-30)

**Optional, and off unless `inspector = on` in `lanes.conf`.** `/lanes:setup` asks; no answer means off.

**What it is for.** §6 sets the rules for code shape, and `/gs` checks them once a sweep. By then the mess
has had days to set. The cheapest moment to fix it is the minute it was written, by the session that wrote
it, while it still knows why. So: Claude writes code; the Inspector writes what is messy into **a separate
notes folder kept with the project**; Claude reads each note against the code and decides whether it is
really mess, or has to be that way to work. **It never edits code.** It only writes its notes folder.

**Where the notes live** (`tools/inspector_store.py`): `dev-archive/inspector/` in the project, or
`inspector/` at its top when there is no `dev-archive/`. One file per kind: `this-session.md`,
`waiting.md` (left by a session that ended first: answer these first), `decided.md`, `already-there.md`,
`cleared.md`. The folder travels between PCs with the project. With `inspector_notes_local = on` it stays on
this PC instead (listed in the clone's own `.git/info/exclude`), which suits a public repo.

**The verdicts.** Each note's `Verdict:` line takes one of:

| Verdict | Means |
| --- | --- |
| `waiting` | not answered yet |
| `fix now` | real; fix it in this session. **Only** for loose numbers, loose addresses and commented-out code, whose fix cannot change behaviour. On any other kind it counts as no answer. |
| `fix later: <board row>` | real; the named board row carries it. Structural fixes (splitting, moving, de-duplicating) go here and are done on their own, move-only and tested (§6). |
| `keep: <why it must stay>` | not mess, or needed to work (for example, tuned in the headset). Raised again only if it gets clearly worse. |

A `keep` needs a real reason and a `fix later` needs a row; an empty one still counts as `waiting`. The
"has to stay" answers are what protect hand-tuned code from being tidied into something broken.

**When it asks** (`inspector_mode`):

- **`end` (default):** notes are written silently after every edit. **Saving is never blocked.** Uploading
  is: `git push` waits while any note in that repo is unanswered or the notes folder is not committed, and
  each time an upload waits, a copy of the held work goes to the Inspector's own folder (`inspector_home`,
  as a git bundle). A lane releasing its claim (`lane-claim.sh release`) is held the same way, so the end of
  a session is where the notes get answered, then everything uploads.
- **`each`:** asks after every edit and holds each commit until its notes are answered.
- **Emergency only:** a commit or release whose command says `inspector: carry over` goes through with notes
  still waiting. The next session is told about them first.

**Only new or worse.** A file the Inspector has never seen is compared with its last commit: what was
already there is listed once in `already-there.md` and not raised. After that it raises what is new, and
what got worse since its verdict. A note that leaves the code moves to `cleared.md`.

**What it checks** (`tools/inspector_checks.py`): size past §6's 800 and 1,500 lines; Lua near its
200-locals limit; bare numbers and raw addresses written into the code instead of named settings; F-key
hotkeys (use the numpad); probe code left in a working file; commented-out code; very long or deeply nested
functions; and blocks of matching lines copied from another file of this project or a sibling project in the
same clone folder (`inspector_root`).

**Where it is limited.** `inspector_repos = a, b` limits it to those projects. `inspector_multi` names repos
that hold one folder per project, so each folder gets its own notes. Anything the hook cannot work out lets
the call through: a broken guard that blocks every commit is worse than none.

**Known ways it can make things worse, which is why the verdict step matters:** tidying working code to get
past the hold (hence the `fix now` limit); lazy `keep` verdicts that cost usage and give nothing; false
alarms, since it is a pattern checker. Answer each note against the code, not against the wish to upload.

**The end-of-session count (0.38.0; a row of the close-out box since 0.40.0).** So it is visible whether
the Inspector is an active part of the work, every lane session ends its report with its count: notes
found in this session's code, how many were fixed (left the code), kept on purpose, left for later, and
still unanswered. Since 0.40.0 it is the `🔍 Inspector` row of the close-out box (`handover.py close`,
§5); `tools/inspector.py summary` still prints the long one-line form, with the file edits looked over.
It counts by the Claude Code session id (`$CLAUDE_CODE_SESSION_ID`, the same id the hook stamps on each
note). Releasing a lane's claim also shows the line on screen. When the Inspector is off the row says so,
rather than disappearing.

Checked by `tools/tests/inspector-fixture.sh`, `tools/tests/inspector_faults_test.py` and
`tools/tests/inspector_summary_test.py`, all run by the smoke test. Design: `docs/specs/inspector-idea.md`.

## 10. The handover light — is it safe to carry on from the other PC? (0.39.0, 2026-10-01)

Two PCs share one GitHub account and hand work back and forth. GitHub is the only meeting point, and git
never overwrites anything quietly: a push either lands or is refused. What is NOT guarded by git is what
never reached it, and what was read before it was fetched.

### What happened

On 2026-10-01 a check across every clone on one PC found five helper scripts from the day before that
existed on that disk and nowhere else: written by a reader, never added, no error anywhere. Two days
earlier a session summary had said the other PC "had not been on for days" — it was this PC's own clone
of the board that had not been pulled. Both are the same gap: nothing was checking, so nothing was known.

### The rules

- **Every session opens with the handover light** (`hooks/handover-brief`, `tools/handover.py start`):
  1. `HANDOVER: SAVED` or `HANDOVER: NOT SAVED` — every clone in every lane root; a file never added, a
     change not committed, or a commit on no remote branch at all makes it red and names the repo.
  2. `HANDOVER: <PC> (<role>) last saved <when>, <how long ago>, and ended SAVED / NOT SAVED: …` — one
     line per other PC, **read from GitHub (`origin/main`), never from this disk**.
  3. with `handover.py fresh [ROOT]`: `FRESH` or `STALE` for one clone root, after fetching every repo in
     it; `--pull` brings it up, fast-forward only. Each lane's pre-flight pull is where this belongs.
- **Every session ends by reporting itself** (`hooks/handover-end`, `handover.py end --write`): one small
  file on the board, `handover/<machine>.txt`, committed on its own and pushed. That is how the other PC
  is told "ended NOT SAVED: staging: 5 files never added" before it starts work.
- **Every lane's write-up ends with the close-out box** (`handover.py close`, since 0.40.0; §5 shows it),
  pasted unchanged under the gate/model box: `SAVED` / `NOT SAVED` as the headline, then what this
  session pushed, the Inspector's count, any claim still held, and the other PC's last save. `NOT SAVED`
  at the end of a session is an instruction: save first, then end. **No box, no trust.**
- **Two things are kept on one PC on purpose and never count:** the Inspector's local notes (`inspector/`)
  and Python caches. Anything else untracked is red. Build leftovers belong in `.gitignore`, not in the
  light's blind spot.
- The tool never pulls, merges or resets anything in `check`, `start` or `end`; its only write is that one
  board file, and a refused push is reported, never forced. Output names repos, roots by lane and PCs by
  their plugin names — never a path or a computer's real name.

### How it is checked

`tools/tests/handover-fixture.sh`: two throwaway PCs sharing a throwaway remote. Red names the dirty clone
and not the clean one; the Inspector's notes do not count; green after saving; the end report reaches the
remote and the other PC reads it from there; a clone behind the remote is STALE and `--pull` makes it FRESH;
no setup at all gives a plain line and exit 2, never a crash. `release.sh` runs it.

## 17. Every session summary is kept, one folder per project (0.44.0, 2026-10-04)

The write-up at the end of a session is the clearest record of what happened: what was changed, what the
person saw, what is being waited on. It used to scroll away with the terminal. A user asked for every one to
be kept, "dated and time stamped, in their own folders for each different project", and for those logs to be
the place a session looks when a problem keeps coming back.

- **Where:** `session_logs = <folder>` in lanes.conf. Each summary becomes
  `<folder>/<project>/YYYY-MM-DD_HHMM_<slug>.md`, stamped with the time and this PC's name. Two in the same
  minute get `-2`, never an overwrite. Work that is not one project goes in a shared folder (`_shared`).
- **Pushed:** when the folder is a git clone, only the new file is staged, then pull --rebase and push, so the
  other PC has it. Keep that repo private; summaries describe unfinished work. Put the clone inside a lane
  root so the close-out box checks it too.
- **When:** every write-up that ends with the close-out box, written before `handover.py close` runs.
  Plain words, a few lines: what was done, what the person saw (their words where they gave them), what is
  waited on.
- **When stuck:** before a third attempt at the same problem, `session-log.py search <symptom words>
  --project <project>`. Earlier sessions often met the same thing; their summaries say what was tried and
  what the person saw.
- **Breakthroughs are marked IMPORTANT** (0.45.0): when the person says it finally works, or the session plainly
  cracked something after a long hunt, write that log with `--important`, unasked. `session-log.py important`
  lists only those. Never for routine progress, or the mark stops meaning anything.
- **Text, not screenshots:** a few hundred bytes each, searchable, and readable later without image cost.


## 18. Every early VR mod carries the jitter recorder (0.59.0, 2026-10-11)

Asked for by the maintainer after the first headset looks at three games in one evening, two of them jittery:
*"please automatically turn it on for any game that is in early development and have that as a rule in the Lanes
plugin as well"*.

### The rule

- **Every VR mod still in early development has BeG0nE's jitter recorder wired in, without being asked** (while the
  `begone_ride` extra is on: always on a PC that had Lanes before 0.82.0, chosen at setup on a new install). Copy
  `begone/camera-jitter/jitterlog.h` (or `jitterlog.lua` for REFramework) from the plugin into the mod's source
  (since 0.62.0; before, from the BeG0nE clone's `camera-jitter/ride-along/`), and call:
  `jl_init(<project>, <runtime>)` at load; `jl_vr_on()` / `jl_vr_off()` when the headset session starts and stops;
  `jl_pose_*()` where the head pose is read; `jl_camera_*()` where the game's camera takes it; `jl_present()` once
  per frame sent out.
- **A mod that reaches a headset without it gets it in that same session**, before or beside whatever else the
  session was doing, and the build that carries it is recorded like any other.
- It writes only while a headset session runs, so flat runs are untouched and nothing has to be switched on.
- "Early development" means anything not yet in the finished group: when in doubt, wire it in.

### Why

A recording shows THAT a camera steps; only the three timing streams show WHY (renewed less often than the
headset asks, a pose handed over twice, a frame behind). Without them every jitter report starts from nothing and
costs the person another headset session. Wired in from the first headset build, the evidence is already there
when they first say "jittery".

### How it reaches the session

The rule rides on the BeG0nE session-start lines (`tools/begone.py`), which every session prints. Since 0.62.0 the
tools ship in the plugin, so there is always something to wire in; `begone = ...` only says where reports are kept.


## 19. Gameplay only: every blur and screen effect off in VR (0.60.0, 2026-10-12)

Asked for by the maintainer: *"switch off any blur effects in VR, also any screen effects like blood spatter, rain,
low health red tint, so there is only gameplay during gameplay."*

### The rule

- **On or off per PC** (0.82.0): the `vr_effects_off` extra (`tools/features.py`). On for every PC that had Lanes
  before 0.82.0; a new install chooses at setup. When it is off, this whole section is skipped.
- **In VR, a game shows the world and nothing painted over it.** Every effect that sits on the screen rather than in
  the world is switched off: motion blur, depth of field, radial / speed / camera blur, film grain, vignette,
  chromatic aberration (colour fringing), lens flares and lens dirt, screen-space blood spatter, rain or water drops
  on the "lens", the low-health red tint or pulse, damage flashes, screen shake, flat-screen "lens" distortions
  (Panini and similar). Rain, blood and fog that exist IN the world stay; only what is painted on the camera goes.
- **Every game, as part of modding it, without being asked:** find the switches. Look in this order, cheapest first:
  the game's own options menu, its config / ini / registry settings, engine settings it still honours (Unreal
  `r.*` lines, console variables), command-line switches, then the shader or post-process pass that draws the
  effect (skip the draw, or zero its strength). Write down where each switch lives and whether it was proven, in
  the project's notes, the same way as the window setting (`/lm` §4b).
- **No game needed to look:** the search through settings files, string tables and shaders is `/pd` work. Turning
  them off and checking the picture is the first live session after the window is fixed.
- **If an effect cannot be switched off yet**, it goes on the board as a row of its own, so it is not forgotten.
- Flat-screen play is not covered: the person may want the effects there. When a switch is shared, the VR build
  turns it off when the headset session starts and leaves the flat setting alone.

### Why

On a flat screen these effects are a film language. In a headset they are glued to your eyes: blur and grain
cannot be focused past, a red tint or blood on the "lens" has no distance, and screen shake moves the world while
the head is still, which is a direct path to motion sickness. Worse, each one hides what the head is doing from
the person testing it, so comfort and jitter judgements get muddied. Gameplay only, during gameplay.

### How it reaches the session

`/lm` §4b step 4 (the first live session, right after the window), `/pd` step 5 (the static search, when a
project's notes have no screen-effects list yet) and `/ms` 5d.

## 20. The BeG0nE tools ship in Lanes, and reports are read, never raw numbers (0.62.0, 2026-10-12)

Asked for by the maintainer: *"please ship the occlusion drift height fix, jitter recorder and now Ghost hand in the
lanes plugin, and if we make a 4th BeG0nE tool, we'll add that too. make sure you also add to lanes for yourself, to
check what they record if a problem arises"*, then: *"is there a way for you to make it impossible to read the raw
numbers that would possibly fill the session by accident? or ... some sort of a program on the pc, that crunches all
these numbers and gives you a short summary of it"*.

### The tools

`begone/` holds every tool, each a folder with a `tool.json`: **Camera Jitter** (the stepped camera), **Ghost Hand**
(gaps between the real hand and the player's hand: lag, offset, jumps, lost tracking, gestures that miss) and
**Occlusion Drift** (no recorder of its own; read through Ghost Hand's tracked flags; per-game cure code in
`games/`). A fourth tool is a fourth folder: the rider, the reader and the lock find it by its `tool.json`.

### The rules

- **Wire the recorders in.** Every early VR mod carries the jitter recorder (section 18). **Any mod with hand
  gestures** (racking a slide, working a pump, grabbing, reloading by hand, two-handed aim) **also carries Ghost
  Hand**, with `gh.event(<gesture>, 'start' | 'done' | 'fail')` around every gesture and `gh.value('<gesture>_need',
  metres)` so a miss can be judged. `tools/begone.py tools` prints how to wire each one.
- **The PC counts, the session reads.** The rider files each recording the moment a headset session ends: the tool's
  filer writes a short `report.md` and a `summary.json`. A session never opens `summary.json` or a raw recording;
  `hooks/begone-raw-guard.py` refuses it (Read, Grep, and shell commands that read). Not airtight, by design: it
  stops the accident.
- **After every headset test, `begone.py new`.** One line per new report since this PC last looked; a bookmark per
  PC (`~/.claude/lanes/begone-seen.json`) means nothing is shown twice and nothing is missed. The session start
  prints the same lines.
- **Read in full when it matters.** Open a report (`begone.py report <tool> latest`) when its line looks wrong, or
  when the job is linked to that tool: `begone.py for "<job>"` says which (slide racking, grabbing, reloads ->
  Ghost Hand; walking, running, turning -> Camera Jitter; two-handed aim and shooting -> Ghost Hand and Occlusion
  Drift). Dig further only with `begone.py ask <tool> <run> <question>`, whose answers are capped at 60 lines.

### Why

One filed jitter session's `summary.json` is 600 KB and its report under 1 KB. Reading every report after every
session costs little; reading raw numbers by accident costs a session. The bookmark keeps the cheap part from
growing, and the lock keeps the dear part from happening by mistake.

## 21. Keep conversations short: an earlier summary that loses nothing (0.63.0, 2026-10-13)

Asked for by the maintainer: keep conversations short automatically; before each automatic summary save anything
important not yet written down and tell the summary what must survive; keep the full logs on the PC; and if the
early-summary setting does not exist, fall back to a "SAVED - safe to /clear" line in the close-out box.

### What was checked first

Claude Code 2.1.296 has the setting `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` (an environment value, also accepted in the
`env` block of `~/.claude/settings.json`). The summary point becomes the smaller of that share of the model's room
and the usual point, so it can only come earlier. Live, three short conversations with it set low were summarised;
text printed by the PreCompact hook was kept in the summary word for word; a SessionStart hook with source
`compact` reached the next turn; and the log file kept every earlier message. `[verified-live 2026-10-13, n=3]`
The summary is prepared in the background and lands one turn after the point is passed. The `autoCompactWindow`
setting did not trigger a summary from a settings file in the same test, so it is not used. `[measured 2026-10-13, n=1]`

### How it works

- **Switch:** `tools/compact.py on [PERCENT]` (default `early_summary` in lanes.conf, else 40), `off`, `status`.
  `/lanes:setup` offers it (step 0.11). It applies to sessions started after it is set.
- **Before every summary** (`hooks/compact-hook.py pre`, a PreCompact hook): a checkpoint goes into the session logs
  (§17) for the project - the claim this PC holds, else the repo the session runs in - with the claims, every repo
  holding work not on GitHub, the board's next OPEN row, the person's last requests word for word and the last reply.
  The hook's output is added to the summary's instructions: keep those facts, the model and gate last named, any
  question waiting for an answer, and every decision the person made.
- **Right after it** (`post`, SessionStart source `compact`): the session is told to write onto the board and the
  notes anything the summary says is not recorded yet, and to save anything not on GitHub, before other work. That
  part needs judgement, so the session does it, not the hook.
- **Full logs:** at every summary and every session end the conversation's log file is copied to `transcripts`
  (default `~/.claude/lanes-transcripts`), out of reach of Claude Code's 30-day clean-up. The original is never touched.
- **Fallback:** while the early summary is not on (or this Claude Code lacks the setting), a green close-out box gets
  one more row, `| 🧹 Clear | SAVED - safe to /clear |`.
- Every hook here is silent on failure and can never block a summary or a session end. `LANES_COMPACT=0` turns
  them off.

## 22. Get better at driving each app, every run (0.66.0, 2026-10-14)

Asked for by the maintainer: sessions should use the -o-matic tools themselves to get more and more familiar with
each game's menus and gameplay, keep what they learn per game, and improve the tools as they go.

- **Drive with routes first.** `/lm` uses the app's recorded routes (`/lanes:menu`); driving by hand is the fallback
  where no route exists yet, and that is the moment to record one.
- **One `KNOWN.md` per app, beside its routes**, with fixed sections: Menus, Controls, Save spot, Hazards, What
  failed, Tool ideas. `mom known <folder>` prints it and the route map (making it from a template the first time);
  `--add <Section> "..."` adds a dated line. Only app facts: no paths, machine names or people.
- **Read it in pre-flight** (`/lm` §4 step 8), so the session already knows how to reach the work.
- **Add the same session** anything new: a screen, a key that works, a route that broke after a patch.
- **Improve the tool** when it was missing something; the canonical copy is the toolkit's, copied into the plugin.
- Unchanged: the first setup of an app is done with the person (`/lanes:menu`), still-camera and mouse tests come
  before movement routes, and playing through levels stays the person's job.
- **0.74.0:** a VR game the person has handed over ("all yours") may have its first setup done by VR Bench's
  `learn` alone, every press preceded by a look and recorded; see §24.

### Plugin updates are described

When a session updates the plugin, or says an update is waiting (`/lanes:update`), it lists each version in between
with one plain line on what it adds, from `CHANGELOG.md`.

## 23. The weekly tool check: /lanes:gu (0.67.0, 2026-10-14)

Asked for by the maintainer: `/gs` only checks; `/gu` should check the things that might need updating and update
them, both ways: a newer version on GitHub comes to this PC, a newer version on this PC goes to GitHub, and new
knowledge goes into the tools.

- **Four things, one report** (`tools/gu.py scan`): our own apps and tools (the plugin, Hand Freeze, every
  `ours = <clone>`); two copies of one tool (`twin = A | B`, A is the master copy; line endings are ignored); outside
  tools on GitHub (`watch = name | owner/repo`, a release not yet noted is new); and the "Tool ideas" lines added to
  each app's `KNOWN.md` (§22) since the last run.
- **The tool changes nothing.** The session updates; it asks once, listing everything, before installing or
  updating anything on the PC that is not a pull of our own clone. `gu.py seen <name> <tag>` notes a release so it
  is not offered again; `gu.py done` stamps the run.
- **The habit is weekly.** The `gu-nudge` hook prints one line at session start when the last run on this PC is 7
  days old or more (or it never ran while something is set up). The session mentions it and carries on; it never
  runs it unasked. `LANES_GU_NUDGE=0` turns the line off.
- Never launches or drives an app, and never touches a project's own files. Test: `tools/tests/gu-fixture.sh`.
- **0.68.0:** `gu_ask = no` lets it update without asking (the maintainer's choice for their own PCs; everyone
  else is still asked). A fifth step covers the PC's own development tools (`winget upgrade`, Python packages),
  leaving alone anything running, a compiler a live session builds with, game stores and private apps.
- **0.69.0:** a sixth step keeps the texts the public reads in step with the work. `tools/gu_texts.py` (scan
  section 5) checks every public repo of the account (`texts_owner =`, front pages read from the clones under
  `texts =`): a description or front page naming a version older than the newest release (pre-releases count when
  there is no full release), "nothing released" or "private" beside a public release, and a status part unchanged
  for 21 days while 15 or more commits landed. The session then reads every description once against the
  project's own notes and rewrites what disagrees, in plain words, from those notes only. It never changes what a
  project is (visibility, a release, a decision). Its first run brought texts in 20 repos up to date.
- **0.91.0: catalog pages.** A page meant to name every tool of ours (`catalog = <repo>/<file>`, such as a
  toolkit's TOOLKIT.md) is checked too: every file in that repo's `tools/`, every public `ours =` repo and every
  app any PC has installed (installed.py's notes) must be named on it, and a tool it names whose repo had 10 or
  more commits since the page last changed is flagged for a look. Added after TOOLKIT.md had gone two weeks
  without Hand Poser, Grab Zones, Window View, VR Bench, BeG0nE, Menu-o-matiC and a dozen small tools, and still
  called Hand Freeze 64-bit only; the maintainer: *"this should have been covered by the /fullscan and /gu, can you
  make a fix for it so next time something like this is not forgotten"*. The full scan runs `/lanes:gu`, so it
  carries this too.

The test builds before an update are section 31.

## 24. VR Bench: learned by the robot, marked by the person (0.74.0, 2026-10-17)

Asked for by the maintainer, from an idea described on Discord: a robot player that, within an hour, has learned
how to drive a game's menus, move the character on a flat screen, and move the VR head, hands and buttons, by itself
and in the background, so the person only has to put the headset on to mark what is wrong.

- **The pieces.** The OpenXR Simulator plays the headset (webhead2oo9's fork, for its 32-bit runtime and command
  files); the VR Bench layer (TefMeister/vr-bench) answers the game's controller questions from
  `%LOCALAPPDATA%\VRBench\input.json`; `tools/vrbench/` writes that file, takes the pictures and keeps the run.
  `/lanes:bench` is the command; setup §3.6 and update steps 7-8 offer the three ways to install.
- **First setup by the robot.** A game handed over may be set up by `vrbench learn` without the person, instead of
  the guided setup of §22 and `/lanes:menu`. The rules that make that safe: every press is preceded by a look, every
  input sent is written to `input.jsonl`, every stage ends with a verdict and its reason, and a run always gives its
  claim back and switches the layer off, even after an error.
- **One run, one game, one bitness.** `vrbench start` registers the layer for the next run of that game only, in the
  32-bit or 64-bit OpenXR layer list as the game's own program says, and `stop` takes it out again. Left in the list
  for good it would sit in every OpenXR game on the PC, the person's own play included, and a layer of the wrong
  bitness is a silent no-op that reads as "the game ignores the controllers". Other layers are never touched.
- **Recording is for development** (the maintainer, 2026-10-17, an exception to their no-recording rule of
  2026-10-16): footage is kept in the person's transfer folder on each PC and never deleted by the tool. It comes
  with the wearing half (the real headset, OBS Mirror).
- **Not yet.** Background keyboard and mouse (until then the menus and flat stages need the game in front), the
  in-headset "look at this" chord (left grip + right grip + left trigger, marking where the index finger or gun tip
  points) and the debrief from marks are the next two plans in `docs/plans/`.
- Tests: `tools/tests/vrbench_test.py`, `tools/tests/vrbench-fixture.sh`. The layer's own 51 checks live in its repo.

## 25. Every offer is made once, and thanks on GitHub (0.75.0, 2026-10-17)

The maintainer: *"any offer has to be one time only on both install and also future updates on lanes plugin"*. An
offer of something new (a desktop shortcut, the pretend headset, thanks on GitHub, and every one added later) is made
on the first `/lanes:setup`, or once on the first `/lanes:update` that brings it to someone who installed Lanes
before it existed. Whatever the answer, `tools/offers.py made <name> <answer>` records it and it is never asked
again; `offers.py should <name>` is checked before asking. "Not now" to a plugin update quiets that version for good.
Updates of something already installed are not offers and are asked when a newer version appears. A new offer is
added to `KNOWN` in `offers.py`, to setup and to update in the same release.

**Thanks on GitHub** (`tools/thanks.py`, the maintainer: *"add a star and a follow to anyone who provides even the
smallest nugget of useful information or a tool, mod we can look at, anything like that"*). Off unless the person
said yes (`thanks = yes` in lanes.conf). When it is on, every session, research lanes included, runs
`thanks.py add <owner/repo> --why "<a few words>"` the moment a GitHub project gives the work something: a tool used,
a mod looked at, an issue or a note with one useful fact. An account with no project to star is followed with
`thanks.py add <owner>`. It is logged in `~/.claude/lanes/thanks-log.tsv`. Following needs GitHub's `user:follow`
permission once (`gh auth refresh -h github.com -s user:follow`); without it `thanks.py` says so and stars nothing
half-way. When it is off, sessions do nothing and do not ask again.

## 26. The recording and the jitter log, side by side (0.76.0, 2026-10-17)

The maintainer: *"are automated recordings and begone tools working in tandem, so that at the timestamp of a jitter,
you can also see the recording frame by frame where and how the jitter happened?"*, then *"please wire in the automated
recording and BeG0nE tools working together ... this is one of these things that gives us best data early on"*.

- **0.80.0: any tool's log starts it, one recording per session.** The maintainer: *"please have BeG0nE tools
  automatically log everything and automatically start video recording whenever we actually launch games in either
  openxr simulator or in vr"*. The rider now starts the recording when ANY tool's log starts growing (Ghost Hand as
  well as the jitter log), keeps it running while any tool's log grows, and stops it when none does. A Lua recorder's
  header says `pid=lua`; the recording then goes to the windowed program that has an OpenXR / OpenVR dll loaded. So a
  mod wired to the recorders (§20: every VR mod) is recorded whenever it runs in the headset or the OpenXR Simulator.
  **The headset picture:** REFramework games show both eyes side by side in their own window, which is what is
  recorded. Jabbah's OpenXR OBS Mirror layer was considered and left out: it supports Direct3D 11 only, and the RE
  games are Direct3D 12 (checked 2026-10-19).
- **Switched on by `begone_record = yes`** (offered once, §25; an optional extra in `features.py` since 0.90.0, paired with the video clean-up, §38). The rider (begone/rider.py) starts `tools/obs-rec.py`
  on the game's window the moment a jitter log starts growing, unless something is recording already; obs-rec adds
  the OpenXR Simulator's preview by itself. When the log ends the rider stops the recording first, then files.
- **One clock.** The log's header carries `wall_ms` (jitterlog.h since 0.76.0; an older mod's log uses the moment its
  file was made), and every saved recording has `<file>.json` beside it with `start_ms`, the moment its first frame
  was. Log second t is recording second (wall_ms - start_ms) / 1000 + t.
- **Every filing cuts the frames** (begone/camera-jitter/frames.py): the first three jittery stretches and one smooth
  turning second, from each recording that covers the log (headset view first), padded a quarter second either side.
  Each folder holds every frame (left eye of a side-by-side picture, 640 wide), `sheet.jpg` (half a second on one
  picture) and `frames.txt`: each frame's log second, recording time, and how much it changed from the one before,
  marked HELD (the picture stood still while the view around it moved) or JUMPED (it caught up). The report ends with
  "On the recording", naming the folders by their place under the recordings folder only.
- **Reading it.** Sessions open `sheet.jpg` and the frames named HELD/JUMP, never the video itself. `begone.py frames
  camera-jitter <run|latest> <from s> <to s>` cuts any other stretch; `attach` redoes a run (for example once a
  recording that was still running has stopped); `where` lists the folders.
- **Honest limits.** The recorder takes 60 pictures a second and the game draws its own rate, so one lone HELD
  picture every few seconds can be the recorder repeating a frame; a HELD picture followed by a JUMP is the game. The
  two clocks agree to about one frame. Only the game's own windows are recorded, never the screen; the frames stay
  off GitHub.
- **0.90.0: the videos do not stay for ever** (§38). Once nothing needs a video it is taken off the PC; the frames stay.

## 27. A new GitHub account, set up the Lanes way (0.78.0, 2026-10-18)

The maintainer asked whether Lanes offers to set up a dedicated GitHub account "with all the systems we have going
on, the folders, guards and countless other mechanics that make it all work"; it did not, and they said "add it",
then "it has to come with a step by step instructions on how to do it all".

- **The person's hands:** making the account, installing Git and gh, `gh auth login`. `docs/NEW-ACCOUNT.md` is the
  step-by-step guide; `/lanes:setup` §0.6.5 offers it once to anyone with no board yet.
- **`tools/estate.py make --root <folder>`** makes the private base repos from the plugin's templates (`board`,
  `ideas`, `staging`, `builds`, `session-logs`; `--skip` and `--name` change the set), clones them into the root,
  makes the four lane roots beside it and fills them with `root-sync.sh --fix`, and writes `root`, `board`,
  `ideas`, `builds` and `session_logs` into lanes.conf. `plan` shows the same without doing it.
- **`estate.py project <name>`** makes a project repo with `dev-archive/`, `notes/`, `engine-research/` (dossier +
  inbox) and `external-research/` (index + inbox), its board page with a first `[PD]` row, and its copy in every
  lane root. Private unless `--public`, which the repo guard asks about first (the 0.58.0 rule, `hooks/repo-guard.py`).
- **Never destructive.** A clone already there, or a repo already on GitHub, is used as it is (a second PC just
  clones); a folder that is not a clone stops it; a lanes.conf key already pointing elsewhere is left alone and
  reported. It never deletes and never makes anything public on its own. Tested by `tools/tests/estate-fixture.sh`
  against a stand-in GitHub.

## 28. Unlock everything before modding a game (0.81.0, 2026-10-19)

The maintainer: *"make it a rule to have all the weapons in the game from beginning, if it is so possible to enable
in developer settings, to check for it as one of the first things before modding any game, to be able to unlock
everything basically so i wouldn't be required to play through the game and unlock them first before modding."*
Offered once (section 25, `unlock-all`); `unlock_all = yes` in lanes.conf switches it on (`tools/unlock.py`).

When it is on, unlocking everything is one of the first jobs on a new game, right after the game runs windowed with
its music muted and its screen effects off:
- **`/pd`, no game running:** search the game's files for a route: a developer or debug mode, cheat and console
  commands (with the exact weapon and item names they take), a config or ini setting, a command-line switch, a
  registry value, a bonus or unlock file, the save format, or a script hook the mod already uses (REFramework Lua,
  UE4SS, a GZDoom `+give` on the launcher). Write each route down with how sure it is (`[inferred-static]` until it
  has worked in the game) and what exactly to type or set. "Nothing found" is written down too.
- **`/lm`, the first runs:** use the route, check in the game that every weapon and item is there, and put it into
  the project's launcher or settings so every later run starts that way. Give ammo by name rather than with a blanket
  "give all" when the game stores switches as ammo or items (Ashes 2063 keeps "the lantern is lit" as one).
- It is for testing the mod, never shipped: a release does not unlock anything for players.

## 29. Look inside the running game: RE Engine MCP and UEVR-MCP (0.82.0, 2026-10-23)

The maintainer: *"please bake these features into Lanes"*, with links to praydog's
[re-engine-mcp](https://github.com/praydog/re-engine-mcp) and elliotttate's [uevr-mcp](https://github.com/elliotttate/uevr-mcp).
Both put a small plugin inside a running game that answers on `localhost:8899`, and an MCP server that hands it to
Claude: the game's own objects, values and functions, read and changed live. RE Engine MCP is for RE Engine games with
a nightly REFramework and its C# add-on; UEVR-MCP for Unreal Engine 4.22 to 5.5 games with UEVR (also live Lua, head and
controller poses, screenshots from the graphics card, function hooks, a listener for every call the game makes, and
dumps of its class layout).

- **Two halves.** The PC half (`tools/engine-mcp.py install re|uevr`: fetch, build or unzip, register with Claude Code)
  is offered by `/lanes:setup` to people modding that kind of game and kept current by `/lanes:gu`. The game half
  (`engine-mcp.py game re <folder>` / `game uevr <exe>`) is put in only by that game's own live session (`/lm`, `/ms`),
  as a numbered build like any other file, and taken out with `--remove` (exactly the listed files) before a build
  goes to anyone, or when the project stops using it.
- **Ask the game before guessing.** Where a session would otherwise read memory and infer what a number means, it asks:
  which object holds the camera, the hands, the weapon; what a value is right now; what the game calls when a button
  is pressed. A finding read live is tagged `[measured]`; it still needs a test before it is `[verified-live]`.
- **Changing the game live is a lever** (section 11): say which step runs last, measure before and after, and say in the
  write-up what was written. A C# test plugin or Lua snippet sent in is a probe (section 6): its own file, archived when
  disproved.
- **`/pd` never calls the live tools.** It may read what a live session saved (dumps, listings) and UEVR-MCP's commands
  that read the game's .exe with nothing running (`ps-resolve`, `ps-symbols`, `ps-xref`, `ps-disasm`).
- **One at a time.** Both answer on the same port, so only one game with either plugin runs on a PC at once (section 3a
  already allows only one running app).
- UEVR-MCP's dumper mode (`game uevr <exe> --dumper`) turns UEVR's VR drawing off for that game: for dumping only, and
  `--remove` takes it out again.

## 30. Extras a new install chooses (0.82.0, 2026-10-23)

The maintainer: *"see if there are any features of Lanes plugin that are not optional right now, but can be made
optional at the first install. no need to make them optional for people updating the plugin as they already have
these features anyway."* Six things were on for everyone with no question: the green look put on the terminal,
the talk rule, the BeG0nE rider (and with it section 18), blur and screen effects off in VR (section 19), the weekly
tool-check reminder, and keeping full conversation logs (section 21). `tools/features.py` sorts each PC once:
- **A PC that had Lanes before** (its lanes.conf or state files are older than five minutes, since the other
  start-up hooks run at the same moment) keeps all six on and is asked nothing.
- **A new install** has all six off until `/lanes:setup` asks (section 0.6.2 there: two questions, the VR pair only
  for VR modders). Skipping setup leaves them off.
- `name = on|off` in lanes.conf always wins; `features.py on|off <name>` writes it. Hooks and commands ask
  `features.py is-on <name>`.
- Since 0.84.0 the test builds before updates (section 31) are a seventh extra, every extra carries a link and a
  set, and every future feature is one (section 32).
- Left out on purpose, because they protect the person or the work: the naming rule, new repos private, the guards,
  the close-out box, the update check. The Inspector, thanks, the shortcut and the unlock route were already offers.

## 31. Test build before keeping an update (0.83.0, 2026-10-23)

Asked for by the maintainer: *"is there a way to make our work VS Build Tools future proof? and any other program
or tool we use for that matter?"*, then *"is there any way to filter it to things that can actually break things
and not simple win-zip"*. An extra (`update_safety`, section 32).

- `tools/gu_guard.py risk` sorts each update the weekly tool check (section 23) finds into **build-critical** (a
  compiler, Visual Studio's build tools, CMake, Python itself, the debugger, Blender, a Python package's major
  jump, or a `critical = <part of the name> | <why>` line in lanes.conf) and **low risk** (an archiver, a small
  bump). The question at the end of the check says "could break: ..." beside each critical one.
- Only the critical ones are tested. `before` notes the version each replaces and builds every
  `build_check = <name> | <folder> | <command>` once; the update goes in; `after` builds them again. A check that
  built before and fails now is **broken by the update**: `putback` installs the exact old version again, and the
  person is told what broke.
- One update at a time, so the one to blame is never in doubt. A check already failing before cannot judge, and is
  named as such.
- Build checks name only scripts that build and test, never ones that copy into a game or app folder.

## 32. Every feature is optional, and says where to read more (0.84.0, 2026-10-23)

The maintainer: *"please make this and every future Lanes feature optional, so it is as modular as it can be, but
do suggest some features to be installed together, as they complement each other. also for the description,
please add a clickable link to either our Github or someone elses, should the user wish to read up more about it,
before installing."*

- **One list.** `tools/features.py` holds every extra: a short name, what it does in plain words, a link to read
  more (this plugin's own page for it, or the maker's GitHub), and the **set** it belongs to. `docs/EXTRAS.md` is
  written from that list (`features.py doc`) and the smoke test fails when it falls behind.
- **Sets.** Extras that make each other more useful sit in one set marked *best together*, and setup says so beside
  each of them ("Goes well with: ..."). Today: the weekly tool reminder with the test builds before updates, and
  the BeG0nE recorders with gameplay only in VR. The everyday helpers each stand alone.
- **Setup asks from the list** (`features.py ask --json`): one question per set, the set's note first, each choice
  with its description, its pairing and its link. A new extra appears there by itself.
- **Every future feature is one of them.** A new feature gets its entry, is gated with `features.py is-on`, and its
  CHANGELOG line ends with `On or off:` and its name (or "nothing new" for a fix). `release.sh` refuses a
  version whose CHANGELOG line has no `On or off:`, and `features.py lint` (in the smoke test) refuses an extra
  with no link, a link to a heading or file that is not there, or no set.
- **Updating keeps what you had** (section 30): a PC that had Lanes before has every extra on, a new extra included,
  and `features.py off <name>` takes any one away. A new install chooses each at setup.
- Still not optional, because they protect the person or the work: the naming rule, new repos private, the guards,
  the close-out box, the update check.

## 33. Use every tool you have, record what helps, grow the toolset (0.85.0, 2026-10-24)

The maintainer: *"please make it a lanes rule to use all the tools and skills at your disposal, to drive the menus
quicker, record things where needed and actually grow our arsenal of tools little by little by little."*

- **The tool first, by hand second.** Before a job is done by hand, the session checks what this PC already has for
  it: recorded menu routes and Move-o-matiC (§22, `/lanes:menu`) to get through menus and into play, VR Bench and the
  OpenXR Simulator for headset moves (§24), the BeG0nE reports for jitter and hands (§20), the live-game connectors
  (§29) and the debuggers for questions about a running game, and every installed skill whose description fits.
- **Record where it is needed.** A menu driven by hand becomes a route in the same session; what was learned about an
  app goes into its `KNOWN.md`; a run whose log the app will write over at the next launch gets that log copied to a
  keep folder on the PC before the next launch (never to GitHub: logs can hold paths and names).
- **Grow the toolset little by little.** A step done by hand twice, an input the tools could not send, a check that
  would have caught a mistake, a log read by eye that a script could sift: each becomes a small tool or a small
  improvement to one, in the canonical copy, then shipped. When there is no time, one dated line under *Tool ideas* in
  that app's `KNOWN.md` keeps it for later. Small and often: never a big rewrite in place of the job the person asked for.
- Delivered as one line at session start (`hooks/tools-rule`). Optional (`features.py`: `tools_rule`, in the everyday
  helpers); a PC that already had Lanes has it on.

## 34. The privacy guard: no login, no home paths, no e-mail on GitHub (0.86.0, 2026-10-25)

The maintainer, after finding the home PC's login and a home-folder path in published notes: *"please see to it that
these are never added and if possible, make an iron rule in Lanes and in general to not add any of the actual home pc
username or file paths anywhere. only name Tefa is fine"*.

**An iron rule, and a hook rather than a reminder.** The naming rule (given at every session start by
`hooks/name-rule`) had said so for weeks and the release scan (`tools/scrub-scan.py`) checked the plugin itself, yet
27 repos had collected the login, one note and one script at a time, each written by a session that could see the
rule. A rule the model applies is behavioural; a git hook is not.

- **Never on GitHub, in any repo, private ones included:** this PC's login name (unless it is the display name the
  person chose), a home-folder path naming anyone else (`C:\Users\<user>`, `C:/Users/<user>`, `/c/Users/<user>`,
  `/home/<user>`, `/Users/<user>`), and the e-mail address in git's settings. **In public repos also** every word in
  the PC's private never-publish list (machine names). Private repos may keep machine names, because some tools file
  their records by computer name.
- **What to write instead:** `~` for the home folder in notes; in code, the folder looked up when the code runs
  (`os.path.expanduser("~")`, `$HOME`, `%USERPROFILE%`), so the script keeps working on any PC. People are named only
  by the display name.
- **How it is enforced:** `tools/privacy-guard.py install` points git's machine-wide hook folder at
  `~/.claude/lanes/githooks/`; every commit's added lines, new file names and message are checked, and a commit that
  breaks the rule is refused with the line and the fix. Hooks that were set before (a push guard) still run after it.
  `hooks/privacy-rule` installs it at session start when it is missing and states the rule; `hooks/privacy-hook.py`
  checks `gh` commands that publish text without a commit (issues, pull requests, releases, gists, repo descriptions).
  A line holding `privacy-guard:allow` is skipped (deliberate test fixtures only).
- **Pushes are checked too (0.86.1):** before commits reach GitHub, none may carry a personal e-mail address as
  author or committer (only GitHub's no-reply addresses pass) or the login or a home-folder path in its message. This
  catches commits made around the commit check, and it stops an old copy from pushing old commits back after a
  repo's history was cleaned: every old commit carries the old e-mail. The refusal says how to move the copy over
  (`git fetch`, then `git reset --keep origin/<branch>`).
- **Never skip it** (`--no-verify`): fix the line and commit again. A repository with its own hook folder
  (`core.hooksPath` in its own settings) hides the machine-wide one; call `~/.claude/lanes/githooks/pre-commit` and
  `commit-msg` from its hooks.
- **What it cannot do:** it guards what is committed from now on. Old commits keep what they had; cleaning git
  history is a separate, deliberate job that rewrites every copy, so it is the person's decision.
- Optional (`features.py`: `privacy_guard`, in the everyday helpers); a PC that already had Lanes has it on.

## 35. Remote Control in every session (0.87.0, 2026-10-26)

The maintainer: *"remote control toggled on at every session start by default, and have that as an option in Lanes as
well - ask user if remote control should be on by default and tell them the slash command if they want it enabled
manually"*.

- **What it is:** Claude Code's own Remote Control. A session with it on can be watched and typed into from the
  Claude phone app or claude.ai/code, and a session on another PC of the same account can send it a job. It needs
  Claude Code signed in with a claude.ai account.
- **On for every session:** `tools/remote-control.py on` writes `remoteControlAtStartup` into the user's Claude Code
  settings (a repo's own settings cannot switch it on) and names the sessions after this PC's Lanes name
  (`machine-name.py`), never the computer's real name, which Claude Code would use otherwise. It starts with the next
  session. `off` takes both values out again; the settings file is backed up once before the first change.
- **By hand, one session:** `/remote-control` (short `/rc`) turns it on or off in the session it is typed in.
- **Asked once on every PC**, new install or not, because it changes how every session starts: setup asks it with
  the everyday helpers (§0.6.2) or on its own (§0.12.6), and `/lanes:update` asks it once on a PC that had Lanes.
  Both name the slash command, whatever the answer.
- Optional (`features.py`: `remote_control`, in the everyday helpers); unlike the other extras it stays off on a PC
  that had Lanes until it has been asked.

## 36. Gold Digger and the weekly full scan (0.88.0, 2026-10-26)

The maintainer, 2026-10-24: *"can you maybe save this info and logs and all of that on the pc and then we create a slash
command so that you go through all this info and filter out things we actually need?"*; 2026-10-26: *"categorizin and
"shelving" all the collected data after each run, without deleting any of it or even analizing any of it ... we need to
save all the collected data in the MEGA transfer folder so both pc's can access it freely"*, and one command for the
whole check-up, each part still available on its own.

- **Shelving, after every run, no model:** `tools/gd.py shelve` copies a game's logs (from the places listed per PC
  with `gd.py sources <game> add <glob> [<shelf>]`) and its new BeG0nE reports (report and chart, never the raw
  numbers) onto shelves in `<transfer>/Gold Digger/<game>/<shelf>/`. The shelf comes from the item's name; shelves
  whose words fill its contents are listed as "also". Same contents are never copied twice, a file changed in the last
  two minutes is left for next time, and nothing is ever deleted. It runs in the session-start and session-end hooks,
  and `/lm` and `/ms` run it right after the app closes. Every index file is written by one PC only
  (`INDEX-<PC>.tsv`, `SIFTED-<PC>.tsv`, `SOURCES-<PC>.txt`), so a synced folder never has two PCs editing one file.
- **`/lanes:gd` reads one shelf at a time** with `gd.py fold` (repeats folded into one line with a count, warnings
  marked, and with `--against` only what the earlier run did not have), and hands each new fact to one place through
  the doors that are safe beside every lane: the project's `engine-research/inbox/`, the game's `KNOWN.md`, a tool's
  inbox. Then it marks the items read.
- **`/lanes:fullscan`** runs, one after another: save check, shelving, `/gd`, `/gr`, `/sr`, `/gu` (looking only),
  `/gs`, saving, and last the tool check's install question. Each part keeps its own rules and clone root. Weekly; the
  session-start line replaces the tool check's own weekly line while the full scan is on.
- Optional (`features.py`: `gold_digger` and `fullscan`, the weekly check-up set, offered together).

## 37. Code health: re-read our own tools without breaking them (0.89.0, 2026-10-27)

The maintainer, 2026-10-27: *"it's been months of adding stuff and maybe a complete re-read of the code is in order, but
at the same time i hope this is not going to break things that actually work right now, so please save a working copy
of everything just in case something goes wrong"*, then *"please make a slash command /ch for Code health and also add
this slash command to the /fullscan function"*.

- **Working copy first, always:** `tools/ch.py backup` tags every repo `pre-ch-<date>`, pushes the tag, and saves a
  bundle of each repo's whole history in the backup folder (`ch_backup =`, else `<transfer>/Code health backups`).
  No change is made until it says every repo is saved.
- **The look:** `ch.py scan` (possible errors and unused imports with ruff; code with no caller left anywhere with
  vulture, a name counted as used when it appears anywhere else in the repo, tests and docs included; settings named
  but never read; twin copies that drifted, with the display name and "the maintainer" read as the same word; old
  cached plugin versions and stray files among the commands), plus `inspector.py review <repo>` for each repo.
  Repos: `ch_repo =` lines, else every `ours =`.
- **What may change:** only what cannot alter behaviour (unused imports, code with no caller, stale names in text, a
  twin brought up to its newer side, a frozen copy moved to `archive/` once its own condition is met). Everything else
  is a board row. A setting named but never read is a lead (a planned limit never wired in), never deleted. The tests
  run after the changes; a failure puts the change back.
- **First pass (2026-10-27, by hand):** unused imports and helpers in the plugin, the toolkit and VR Bench; BeG0nE's
  Village grip had a 2026-10-24 fix the Lanes copy never got (now in both); BeG0nE's frozen ride-along moved to its
  archive; VR Bench's per-stage time limit and footage warning found named but never wired in.
- Part of `/lanes:fullscan` (after the tool check). Optional (`features.py`: `code_health`, in the weekly check-up set).

## 38. BeG0nE videos clean up after themselves (0.90.0, 2026-10-27)

The maintainer, 2026-10-17: *"automatic recordings are now only for pairing with the BeG0nE tools and to be deleted
once they are no longer used"*. Ten days later nothing had ever deleted one, and asked *"see if the used ones we don't
need are actually also automatically removed from the pc?"*, they said yes to building it.

- **When a video goes** (`begone/video_tidy.py`), all three: it is finished (its `.json` says when it stopped); no
  jitter report of that game from that time is still waiting for its frames; and either the game was recorded again
  on a later day (the test was redone) or the video is older than two weeks (nobody came back to that job). So a game
  keeps the videos of its last test day until it is tested again, or two weeks pass.
- **What stays:** the cut frames (`sheet.jpg`, `frames.txt`, the pictures) and every report. Only the `.mp4` and its
  `.json` go, and each removal is written to `%LOCALAPPDATA%\BeG0nE\videos-removed.tsv`.
- **Who runs it:** the rider, once an hour while nothing records. `begone.py videos` shows what would go and what
  stays, and why; `begone.py videos tidy` does it now.
- Optional, as one set with the recording itself (`features.py`: `begone_record` and `begone_video_tidy`, the set
  "Recording the BeG0nE tests", offered as a pair). Both are off until the PC says yes: one films, the other deletes.
  Setup asks the clean-up right after the recording question (setup 0.13).
