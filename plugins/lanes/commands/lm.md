---
description: (Live Modding) A hands-on session on ONE project - the only lane allowed to launch the app, attach a debugger, or drive special hardware. Typing /lm hands the whole session over: the assistant launches the app itself, drives it, relaunches it after build swaps and closes it, without pausing to ask. Takes a project name (fuzzy-matched), runs the pre-flight, then works as autonomously as that project's automation profile allows. Must not run against a job another same-lane session has claimed.
---

`/lm` — **the live lane.** The only one allowed to run the thing.

Argument: `$ARGUMENTS` — optional. A project name, however you would naturally say it. If it
matches more than one project, **list the candidates and ask** — never guess silently on an
ambiguous name. If it is empty, auto-pick the next job for this machine.

**⚠️ Strip the modifiers before resolving a name.** `force` and `i launch` are instructions to this
command, not project names. Remove them first and treat what is left as the name — possibly
nothing, which means auto-pick. `/lm i launch` on its own is a bare `/lm` that the user is
starting themselves.

---

## 0. ⭐ What typing `/lm` tells you about the user

**This is the most important thing in this file. It changes how you work, not just what you work
on.**

| | **`/lm` typed** | **no `/lm` — an ordinary conversation** |
| --- | --- | --- |
| Where they are | **Busy, elsewhere.** | With you, relaxed. |
| What they can do | **Nothing, and nothing is expected of them.** | Sit with you and test whatever you ask, live. |
| Who drives the app | **You do.** Launching, menus, movement, commands, relaunching, closing. | **They do**, and report back how it went. |
| Your job | Write the code *and* drive the app, then report in writing. | Write the code; they test; you read their feedback and iterate. |
| Tone | An efficient written report they read between other things. | Conversational, back and forth. |
| Asking them things | **Only** what needs human senses (does it feel right, does it look off) or is literally impossible for you. Batch it into one message. | Ask freely — they are right there. |

**The whole machine is yours in this mode: launching, relaunching and closing all included.** Do
not stop to offer "shall I launch it?" — typing `/lm` was that permission. Close it yourself the
moment it is no longer needed, or the moment a build swap requires a restart — **through its own
menu's Quit / Exit, not by killing it** (see §5).

### The `i launch` modifier

If the user types **`/lm i launch`**, they are starting the app themselves. Everything else about
the lane is unchanged, with one addition: **once you close the app, ask before relaunching it.**
Their machine, their timing.

---

## 1. A bare `/lm` picks one job, claims it, and starts

```bash
bash "${CLAUDE_PLUGIN_ROOT}/tools/gate-scan.sh" --next --tag FLAT
```

`--tag FLAT` is what makes it an `/lm` pick rather than a generic one. Without it, `--next` walks
`PD → USER → FLAT → VR` and hands back the cheapest row of **any** gate, which is right for "what
should this machine do next" and wrong here.

It knows this machine's role, prefers starred rows, and **skips any job a `/pd` — or another `/lm`
— is on right now, naming who holds it.** That is the cross-lane check that makes auto-pick safe,
and it reads the same `lane-claim.sh` the prompt guard hook uses, so the board and the hook can
never disagree.

Name the job you took and state its gate in one line, so the choice stays visible. Then start.
**Work that one job and stop.** Do not move on to a second on your own.

If `lane-claim.sh take` is rejected because someone claimed first, re-run `--next` and take what it
names rather than stopping.

---

## 2. The one hard fact that makes this lane different

**This is the only lane allowed to launch the app, attach a debugger, or drive special hardware.**
`/pd`, `/gr`, `/sr` and `/gs` exist precisely so they are *always* safe to run without touching a
running process. This command is the other half of that split.

The permission belongs to **this lane, running inline**. **No background helper ever launches or
drives a live app** — see below.

## 🤖 The reader — your ONE background helper (0.4.0, 2026-09-10)

**Start exactly one background agent, right after you state the gate (pre-flight step 6), and say
so in one plain line.** It does what a `/pd` in a second window used to do: read, measure,
analyse, and build in a staging area — while you drive the app and own every write. This replaces
the two-session tandem seat, which never had a clean run worth counting.

**One. Never two, never "one more just for this bit".** The user's condition, verbatim: *"if it's
only PD, then i kind of know what it is."* Three agents nobody could name was the problem this
rule remembers; one named reader is not that. If a second would ever help, that is a design change
and needs asking.

### Starting it

Use the Agent tool, background, general-purpose. Build its brief from these parts, in plain prose:

1. **The job:** project name, its repo path, the board path, and the one question you most want
   answered — or the `[PD]` rows from its `OPEN` block if you have none yet.
2. **What it may do:** read anything; analyse; measure from files, logs and dumps; write and build
   code in the project's staging area.
3. **What it must never do:** launch the app or attach anything to it; deploy or replace any file
   the app loads; edit the curated notes; edit `<board>/status/*.md`. Say that a hook refuses the
   last one, so it is not a judgement call.
4. **How it hands work back:** in its report, and as **new, uniquely named files** in the
   project's `inbox/` — never by editing a file it does not own.
5. **How to report:** plain English, findings tagged with how well they are known, and the
   difference between what it measured and what it inferred stated outright.

Then tell the user, in one line, what it has been asked to look at.

### While it runs — AND IT MUST NOT GO IDLE (tightened 2026-09-10, user-directed)

**⚠️ THE READER FINISHES ITS JOB AND STOPS. That is normal, and it is exactly what catches you
out.** It is not a passenger that stays awake for the session; it is a colleague handed one sheet
of paper. In the run that produced this rule the reader answered its question in twelve minutes
and ended while the session continued for another forty — and nobody noticed, because from the
outside a finished agent looks identical to a working one. The user asked afterwards why it had
"disappeared". It had not: it had finished, and nobody gave it anything else to do.

**So this is a TRIGGER, not an intention:**

- **The moment its report arrives, do exactly one of two things: send it the next question, or say
  in your reply that there is nothing static left for it, and why.** Never let a report be the
  silent end of it. "I'll keep it in mind" is how the last one died.
- **Keep a reader queue, and say it out loud.** Every static question that comes up which you are
  not doing yourself this minute — a file to read, a value to measure, a derivation, a build —
  goes to the reader rather than into your own head. An empty queue is a fact worth stating, not a
  silence.
- **If the session moves to a second project, that project gets its own reader.** A fresh `/lm` is
  a fresh session, and the old reader knows the old project and nothing about the new one. Running
  the second half of a session with no reader at all is the same failure in a different costume.
- **Give it work it can actually do.** It can read anything, measure from files and dumps, derive,
  and build in the staging area. It can never launch or touch the running app. A question that
  needs the screen is yours by definition, so do not park it with the reader and then wait.

- **Never let it go quiet.** If you are waiting on it, say so. If it dies, say so and carry on
  alone — that is less obvious than a window closing, so it has to be said.
- **Relay what it finds in plain English**, and say what you are doing with it. Its report is
  second-hand; treat a confident claim from it the way you would treat one in a note: verify what
  matters before acting on it.
- **Send it follow-up questions** mid-session (SendMessage). That is what the two-window shape was
  actually good at, and it survives here.
- **Drain the project's `inbox/` more than once**, not only at session start — the reader drops
  findings while you drive, and a drop that sits unread until tomorrow has bought nothing.
- **Keep feeding it.** Static questions, builds, derivations — hand them over as they come up.
- **In the write-up, say what it returned**, and what you did with each finding.

### ⚖️ If the quota starts to show — the escape hatch is the user's to pull

Keeping one reader alive for a whole session costs more than spawning one per question. The user's
instruction when this default was set: if usage climbs noticeably they will say so, and the reader
should then be spawned when it is needed rather than kept around waiting for the next assignment.

**Always-on is the default, and withdrawing it is their call, not yours.** If they say usage is
climbing, switch to **spawn-on-demand**: start a reader when a real question exists, let it end
when it answers, start the next one when the next question comes. Do not pre-empt that switch, and
do not quietly drift into it — an idle reader is waste, but a reader you never started is the
failure this whole section exists to stop.

### What keeps it honest

The reader keeps its write tools so it can build. That means the control is a **hook**, not the
absence of tools: `hooks/reader-guard.py` refuses any write to `<board>/status/*.md` from a tool
call that carries an `agent_id` — which a subagent's calls always do and yours never do
(`docs/specs/2026-09-10-task-zero-result.md`, measured). It fails open, so it can never block
*you*. Everything else it must not do is behavioural and is written into its brief.

**No background helper ever launches or drives the app.** That permission is yours, inline.

---

## 3. The live claim — check before you start

A same-lane session (`/lm` or `/pd`) claims a job with one line above that project's `OPEN` block,
pushed. The check is a script — not the prose in the notes, and never a guess from commit
timestamps:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/tools/lane-claim.sh" check <project>
```

1. **`NONE` or `STALE`** (older than 12 h — that session most likely died) → the job is yours. Take
   it in pre-flight.
2. **`FRESH`** → another same-lane session is on it right now. Say who holds it and since when, and
   stop. The only override is the user typing **`/lm force <project>`**; then take it with
   `--force` and say out loud that you took it over.
3. A prompt hook runs this check before the prompt reaches you, so if you are reading this it got
   through — but the hook cannot resolve every fuzzy name. **Run the check yourself anyway.**

**Why a written claim and not "was there a commit recently".** A session once looked at another
lane's commit from twenty-seven minutes earlier, judged that session finished, and undid its fix.
Git was clean; the loss was semantic. The claim takes the judgement out of it.

## 3a. 🔒 One running app per machine

`lane-claim.sh` stops two sessions taking the same **job**. It does not stop two `/lm` sessions
sharing one **keyboard** — two `/lm` on different projects both read `NONE` and both proceed.

**Before launching or driving anything:**

```bash
bash "${CLAUDE_PLUGIN_ROOT}/tools/lane-claim.sh" list
```

The claim line carries the **machine label**. If another `/lm` claim shows the **same machine**, **do not
launch.** Name the job holding the machine and since when, then take static work instead or put it
to the user.

⚠️ **Why clone roots cannot fix this, and why the failure is silent.** Both sessions drive their app
by giving it focus and sending input, and virtual gamepads are global to the machine. Two live apps
steal focus from each other, and the result is that **key bursts partly land while single keypresses
vanish** — so each session records "this app ignores that input" as a finding. That exact signature
has been produced in practice: movement sent 10–15 at a time worked, single keys did not, and
neither session could rule the other out afterwards. **Two sessions that must both drive need two
machines.**

---

## 4. Pre-flight — before touching the app

1. **`git pull`** the board, this project's repo, and any staging area. These clones go stale, and a
   read of a stale clone reports the state of this disk, not of the project.
2. **Take the claim.**
3. **Drain this project's `inbox/`** — by explicit filename list, never by glob.
4. **Read the status file and the project's own notes**, including the recorded dead ends.
4a. **Show the project's fresh ideas first**, if an ideas repo is set up: `/lanes:ideas` → "When a
   session starts work on a project". Print the numbered list and carry on; drop nothing until the
   person answers with numbers.
5. **⚠️ Verify what is actually deployed, by hash.** "Deployed" written on a board is prose, not
   evidence. Check the installed artifact against the source you are about to reason from, and
   **regenerate rather than reuse** a staged build you cannot account for. A session that measures
   a build it did not deploy learns nothing and records it as fact.
6. **State the gate in one line** before you start.
6b. **Name the model this session needs, beside that gate line, before driving anything** (0.12.0).
   One plain line: the tier the work in front of you needs, and whether it matches the model
   actually running. ⚠️ It cannot come before the command is typed, because the pick needs a board
   read — say so. **Running weaker than the session needs → stop and wait**, naming the tier and
   what to re-type: a live session driven badly wastes a launch as well as the tokens. **Running
   stronger → say it in one line and carry on**, never stop — the person is usually away and the app
   is about to launch, so a pause wastes the slot. `docs/PROTOCOL.md` §5.
7. **Start the reader** (one line to the user saying what it is looking at) — see above.

## 4b. ⭐ The first job on a new app: does it run, does it run with our file, then a FIXED WINDOW (0.7.0)

The first live session on any app goes in this order, and nothing else starts until all three are
done:

1. **Does it run as shipped?** Launch it untouched and reach its main menu.
2. **Does it still run with our own file added?** Put the smallest possible file of ours in place
   and reach the same menu. Read its log to confirm it loaded. **Use `tools/proxy-gen/`**: it
   generates a pass-through proxy DLL that forwards every export and logs which ones the app uses,
   and it already survives the Windows compatibility engine calling it before `DllMain` (a crash
   that looks like "this app rejects our file" but is not). If it still crashes, read that tool's
   README before concluding the app blocks injection.
3. **Make it playable in a window of a fixed size — 1280×720 unless the project says otherwise —
   immediately after the launch test.** Find the app's own setting (in-app menu, config file,
   registry key or command-line switch), prove it by measuring the window's client area, and write
   down where it lives.

Why the window comes before any real work:
- **Measurements carry between machines only if the picture is the same shape.** Anything keyed to
  the aspect ratio (projection matrices, screenshot comparisons) is meaningless when copied from a
  16:9 machine to a 21:9 one. A fixed window makes every machine 16:9.
- **Unattended driving needs a window.** Fullscreen apps minimise, stop drawing, or swallow input
  the moment anything else takes focus — a system prompt, a notification, another app.
- **Screenshots and captures stay cheap and predictable.**

Prefer a config-file or command-line route over clicking through menus: in-app settings pages
often end in a timed "keep these settings?" prompt that reverts unattended runs. Back up any file
or registry key before changing it.

## 5. During the session

- **Launch it yourself**, and relaunch whenever a build swap or a startup-only setting requires it
  (unless the user typed `i launch` — then ask first).
- **Build several input routes and measure which one the app obeys, against a no-input control.**
  One API is never enough, and a single failed route is not evidence the app ignores input.
- **Judge by eye where eyes are the right instrument.** A statistic that disagrees with what is
  plainly on screen is a broken statistic.
- **Every install stays a dev build.** Never revert a change to make something usable again, and
  never trade progress for a working save or a smoother run. That is what backups are for.
- **Check the shape of any file before you add to it** (`tools/code-shape-scan.py`). If it is over
  the size budget, the split is the first job; see `docs/PROTOCOL.md` §6.
- **⚠ Before you build a lever, say which step runs LAST**, and make it prove its own effect —
  measure, act, re-measure, log both numbers — so a run can tell "no effect" from "wrong
  choice" without a person judging the result. A change landing after the value is decided
  annotates it, it does not fix it. `docs/PROTOCOL.md` §11. Put a new probe in its
  own file, give any tunable number a name, and archive the probes this session disproves.
- **⚠️ If any part needs the PERSON — a wearer, a hand on a controller, an eye on the screen — hand
  it over as NUMBERED STEPS, written before the run, not as a summary after it.** Preconditions
  first, one action per step, a baseline before any variant, what to ignore, what the failure
  modes look like, and how to put it back. `docs/PROTOCOL.md` §10. Walking your own steps
  in order is a test of the tooling: it is how a restore script that undid only half of what the tests
  changed was caught, which would have made the baseline and the variant give identical results.
- **Close it yourself** the moment it is no longer needed.
- **⚠️ Close it the way a player would, whenever you can: through the app's own menu.** Open the
  pause or main menu and pick its own Quit / Exit option, confirming any prompt. Killing the process
  (`taskkill`, `Stop-Process`, closing the window) can land mid-write and **corrupt save files and
  settings**. Force-closing is only for when the app cannot be quit normally — it is hung, crashed,
  has no reachable menu, or the menu route has failed twice — and when you do, **say so in the
  write-up**, so a corrupted save later has an explanation. Wait for the process to exit on its own
  before swapping a build.

## 6. Before the session ends

1. **Write it up** — what was done, what it means, and a confidence tag on every durable claim.
2. **Re-audit the `OPEN` block** and re-date it. A stale block is a session that logged work without
   re-auditing what is left, and it makes the board understate.
3. **⚠️ Verify before you write it down.** A fix that removes the symptom *and* stops the failing
   path from being exercised has proved nothing about the cause. If the failing path no longer
   runs, the claim is a hypothesis however well the fix worked.
4. **Commit only your own lane's paths.** Never `git add -A` in a shared repo. `git pull --rebase`
   before pushing.
5. **Release the claim.**
6. **Update the public front page** if this estate has one — see below.
7. **Report**, and end with what the next step requires — in capitals, unprompted. Either there is a
   cheaper item, or there is a named wall. Both are answers; trailing off is not.
8. **Name the model the NEXT step needs** in one line beside the gate: `MODEL: STRONGEST`,
   `STANDARD` or `LIGHT`, and why. Round up when it is close; never spend the strongest on routine
   work. If this session's own work turned baffling part-way, say so here too. This is the **second**
   time the session says a model — pre-flight step 6b named the tier for the work it was about to do;
   this one is for whoever picks up next. `docs/PROTOCOL.md` §5.

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
