# lanes

![lanes plugin banner](../../assets/banner/banner.png)

**Run several Claude Code sessions at once without them treading on each other.**

Open two or three terminals, start a Claude session in each, and they will happily edit the
same files, rebase over each other's uncommitted work, and quietly undo one another's fixes.
`lanes` is the protocol that stops that: every session declares which **lane** it is, each lane
owns a fixed set of files, and everything else travels as create-only hand-offs that git can
always merge.

It also gives you a shared **work board** so a session can answer the only question that
matters at the start of a session: *what can I actually do right now?*

---

> 🚧 **Early version, still being built.** It has been in daily use since 2026-09-09, on two
> machines, through twenty-odd versions - but it is one person's working tool, made public so
> others can use it and find what breaks. Expect changes. `/lanes:update` tells you when there is
> a new version and what changed, and never installs anything without asking.

> 🔍 **Check it yourself before you install.** Ask your own Claude Code to audit every file and
> link first: [`AUDIT.md`](../../AUDIT.md) has a request to copy and paste.

## The lanes

| Lane | Command | What it is | Touches the app under test? |
| --- | --- | --- | --- |
| Board | `/gates` | Prints all open work, grouped by what it **requires**. Read-only. | no |
| Watch | `/gate-watch` | Background watcher; reports work landed by *other* sessions. Read-only. | no |
| Hygiene | `/gs` | Read-only sweep: are claims tagged, are hand-offs being drained, has anything drifted? | no |
| Research | `/gr` | Public research per project. Curates one folder, hands off to the rest. | no |
| Sweep | `/sr` | Cross-project research. Curates the shared library only. | no |
| Static | `/pd` | Picks the next job and advances it **as far as it can with nothing running**. | no |
| Live | `/lm` | The one lane allowed to drive the running app. | **yes** |
| Setup | `/setup` | First-run walk-through of the **optional tools** (debuggers, decompilers, Blender MCP, build tools, VR runtimes): installs what you say yes to, or gives you the official link. | no |
| Update | `/update` | Checks GitHub for a newer version of this plugin, says what changed, and updates it **after you say yes**. Also checked by itself at session start. | no |
| Ideas | `/ideas` | Files ideas you wrote down in your ideas repo, word for word, onto each project's page, and hands them to that project's next session as a numbered list. Runs by itself when ideas are waiting. | no |
| Test | `/pt` | Tests **this plugin** against real work; writes only to the plugin's own repo. | no |
| Manual | `/ms` | You drive: the session gives you a few numbered steps at a time, reads the logs after, and writes the code in between. | you do |

`/gs`, `/gr`, `/sr` are the three you run **before** starting work. `/pd` and `/lm` are the two
that do it.

### The two rules that matter most

1. **One session per lane.** Four *different* lanes in parallel is the design. Two of the same
   lane is not a faster version of it — it is slower, and it is the only configuration that has
   ever gone wrong here.
2. **One session per job.** `/lm` takes a **live claim** on the job it is working; `/pd` sees the
   claim and skips that job. The claim is released in the session's write-up. Static work on the
   *same* job happens **inside** the `/lm` session, as its one background reader (below) — never as
   a second session.

---

## How well is this actually proven?

This project tags every durable claim with how well it is known, and applies that to its own
README rather than exempting it.

- Four lanes running simultaneously, clean: **`[verified-live, n=2]`** — 2026-09-01, and again
  2026-09-05 where it was checked mechanically afterwards `[verified-numerically 2026-09-05, n=1]`
- Two lanes running simultaneously, clean: **`[verified-live, n=3]`** (2026-09-02 ×2, 2026-09-03)
- Two sessions of the **same** lane: **failed once, 2026-09-02** — ~10 minutes lost each, **no
  work lost**. This is why rule 1 exists.
- Two sessions paired on **one job** (the 0.3.0 tandem seat): **1 clean run in 50 attempts**, and
  the two most recent faults both came from it. Retired in 0.4.0 in favour of one session running
  one background reader `[verified-numerically 2026-09-10]`
- That a `PreToolUse` hook fires for a background agent's tool call, and that the call carries an
  `agent_id` the session's own calls do not: **`[verified-live 2026-09-10, n=1 each]`** — the fact
  the reader guard rests on
- The board tool as shipped here, versus the original it was extracted from: **byte-identical
  output across all six modes**, plus `lane-claim list`, against a live board
  `[verified-numerically 2026-09-09, n=7 comparisons]`
- The hygiene scanner, same test against a 22-repo estate: **identical but for two file-age
  values that crossed a whole-day boundary between the two runs**, confirmed against the
  commit timestamps `[verified-numerically 2026-09-09, n=1]`
- Shipped smoke test: 14 assertions, all passing — including that the **template board**
  shipped here passes the validator shipped here `[verified-numerically 2026-09-09, n=14]`
- **Installed for real and tested from the installed copy**, not the working tree: marketplace
  add, install, all 8 commands registered under a `lanes:` prefix (so they sit alongside
  same-named local commands rather than shadowing them), all three hooks firing correctly
  through the Windows shim, both test suites passing, and no CR bytes anywhere after the
  round trip `[verified-live 2026-09-10, n=1 machine]`
- Shipped hooks test: 20 assertions covering both guards — that they block the collision,
  that they stay out of the way otherwise, and that they fail OPEN when they cannot do their
  job at all `[verified-numerically 2026-09-09, n=20]`
- Work loss under a lane collision: **`[measured 2026-09-02, n=1 sandbox replay]`** — structurally
  impossible short of `git gc --prune=now`. A collision costs minutes, not work.

**Where it is up to:** the bar for going public is in `docs/RELEASE-CHECKLIST.md`, and the
faults found so far — five, all fixed — are in `docs/FAULTS.md`. Neither is a summary; both
are the working record.

**`n=1` is not "verified".** The honest headline today is *"it has run clean four-ways once, and
two-ways repeatedly."* This README's numbers get updated as the count grows; it is not released
publicly until they justify it.

---

## Build state

Built in chunks, each tested on a live estate before the next begins.

| # | Chunk | State |
| --- | --- | --- |
| 1 | Skeleton — marketplace, manifest, licence | ✅ done |
| 2 | The board — `/gates`, `/gate-watch`, the config file, the session-start hook | ✅ done |
| 3 | The start-of-session lanes — `/gs`, `/gr`, `/sr`, `/pd`, plus a smoke test | ✅ done |
| 4 | The live lane — `/lm`, the live claim, both guard hooks | ✅ done |
| 4b | **0.4.0** — the two-session tandem seat retired; `/lm` runs one background reader instead, with its own guard | ✅ done, 2026-09-10 — first live runs still owed |
| 4c | **0.5.0** — every session names the model tier the next step needs (`MODEL:` line beside the gate); **0.5.1** prints the two together as a bold boxed grid | ✅ done, 2026-09-13 — wording only, never run live |
| 5 | The rulebook — board format, protocol, a template board, the `lanes` skill | ✅ done |
| 6 | **0.22.0** — first public release, as an early version still being built; the naming rule ("User" unless you choose a name) | ✅ 2026-09-24 |

---

## Setup

```
/plugin marketplace add TefMeister/lanes-plugin
/plugin install lanes@lanes-plugin
```

Then tell it where your board is. The board is an ordinary **private** git repo with a `status/`
folder holding one `<project>.md` per project — your working notes, in a shape the tools can read.

```
cp lanes.conf.example ~/.claude/lanes.conf   # then edit `board = ...`
```

`$LANES_BOARD` overrides the config file, and a path passed on the command line overrides both.
There are deliberately **no built-in path guesses**: a guess that finds a stale clone reports your
disk's past instead of the project's present, which is the one failure the board exists to avoid.

**What sessions call you.** In everything a session saves or publishes - notes, boards, commit
messages, READMEs - you are **"User"**. Your real name, login, e-mail, machine names and
home-folder paths are never written. If you would rather be called something else (a handle you
use publicly, say), `/lanes:setup` asks first thing, and that one name is then used everywhere.
The same goes for your computers: each PC is PC1, PC2 and so on, or a name you pick in setup,
never the computer's own name.

**Optional tools.** The first session after installing offers a guided setup, `/lanes:setup`: for
every tool the lanes have used (Git, Python and its packages, llvm-mingw, CMake, MSVC build tools,
Rust, Lua, x64dbg and x64dbg-automate, Ghidrust, Blender + Blender MCP, a virtual gamepad driver,
SteamVR and Virtual Desktop) it offers to install it, gives you the official download link to do it
yourself, or skips it. The catalog with every link is `docs/TOOLS.md`; the offer is made once per
machine, and `LANES_SETUP_NUDGE=0` turns it off.

**Staying up to date.** At session start (at most every few hours) the plugin checks GitHub for a
newer version. If there is one, the session tells you what changed, in plain words, and offers to
update it; it only runs the update if you say yes, and the new version applies after a restart.
"Not now" keeps it quiet about that version for a day. `/lanes:update` checks on demand;
`LANES_UPDATE_NUDGE=0` turns the automatic check off. Each version's changes are in `CHANGELOG.md`;
[`HISTORY.md`](HISTORY.md) is the other half — why it went the way it did, including the headline
feature that was measured, found to work once in fifty runs, and deleted.

Once configured, every session opens with a one-line summary of what is queued. If no board is
configured the hook stays completely silent — it never makes a session start with an error.

### Where things are

| | |
| --- | --- |
| `docs/BOARD-FORMAT.md` | the `OPEN` block, the `LIVE` claim, `machine-assignments.tsv` |
| `docs/TOOLS.md` | every optional tool: what it is for, official link, install command, check |
| `docs/PROTOCOL.md` | lane ownership, create-only hand-offs, clone roots, confidence tags |
| `template-board/` | copy this into a new **private** repo to start a board |
| `template-ideas/` | copy this into a new **private** repo to keep ideas in (`ideas = ...` in `lanes.conf`) |
| `tools/ideas.py` | the ideas inbox: `check`, `waiting`, `clear`, `sync`, `list`, `pick`, `done` |
| `skills/lanes/` | the short form, loaded on demand when a session needs the rules |
| `tools/root-sync.sh` | keeps every lane's clone root holding every repo (`--check` lists gaps, `--fix` fills them) |
| `tools/owed.sh` | work only one named machine can do, queued for that machine (`add` / `list` / `show` / `done`) |
| `tools/tests/` | `smoke-test.sh` and `hooks-test.sh` — run both after touching anything |
| `docs/FAULTS.md` | every fault found, what it would have done, and what stops it coming back |
| `docs/RELEASE-CHECKLIST.md` | the countable bar this has to clear before it goes public |

### Work only your OTHER computer can do

An install, a config change, a build that has to land on that disk, a test that needs hardware only
one machine has — those cannot travel, and a line about them in the shared board nags **both**
machines forever while neither owns it.

```bash
tools/owed.sh add HOME "Install the new runtime"   # body on stdin
tools/owed.sh                                      # what THIS machine owes; silent when nothing
tools/owed.sh done <name>                          # clear it, then commit and push
```

The item is addressed to one machine, greets **only that machine** at session start, and goes away
when that machine does it. Any lane that notices such a job is expected to raise one before it
finishes, rather than writing a note and hoping. Full rules — including why `done` refuses a
pattern — in `docs/PROTOCOL.md` §7.

### What installs itself

Six hooks come with the plugin. All six **fail open**: if anything about them cannot run,
work is allowed through rather than blocked.

| Hook | What it does |
| --- | --- |
| board summary | puts the one-line board in front of every new session |
| owed check | greets this machine with work queued for it, and stays silent when there is none |
| ideas check | when ideas are waiting in your ideas repo, has the session file them first; silent otherwise, and off until `ideas = ...` is set |
| `/pd` lock | stops a second `/pd` starting on this machine while one is live |
| live-claim guard | blocks `/pd` or `/lm` naming a job another same-lane session holds |
| reader guard | refuses the `/lm` session's background reader any write to the board's status files |

**The reader guard is a hook, not a missing toolbox — said plainly.** The reader keeps its write
tools so it can build in a staging area, so the control is a hook keyed on a documented payload
field: a tool call made by a subagent carries `agent_id`, the session's own calls never do
`[verified-live 2026-09-10, n=1 each]`. A hook fails open; a toolbox with no writing tools cannot
be argued with. That trade was made knowingly, for the building. Evidence and the alternative not
taken: `docs/specs/2026-09-10-task-zero-result.md`.

The guards exist because the collision they prevent was **a session that read the rule,
looked at the evidence, and judged wrong.** A rule the assistant applies is behaviour; a hook
is the same check for every session, and it runs before the model sees the prompt. The
command files still carry the rules — the hooks are the floor under them.

## Known limitations

Recorded rather than hidden, in the same spirit as the confidence tags above.

1. **The five gate tags are fixed** (`PD` / `USER` / `FLAT` / `VR CLAUDE` / `VR USER`). They are
   the on-disk grammar, so renaming them would invalidate every existing board. The prose the board
   *prints* has been generalised — *nothing running* / *needs you* / *needs the app up* /
   *needs special hardware* — but the tags you write in a status file have not.
2. **Roles are a flat list of labels.** Two machines is what this has been run on; more should
   work, and has not been tried.
3. **It was built for one person's game-modding work** and shows it: the optional tools, the gate
   tags and many examples come from reverse-engineering games. The lane rules themselves are
   general, but expect the rest to lean that way.

## Credits

- The Windows hook shim is adapted from **[Superpowers](https://github.com/obra/superpowers)** by
  Jesse Vincent (MIT), which solved the cmd/bash polyglot problem first.
- Built and proven on a long-running flat-to-VR game-modding estate, where the failures that
  shaped every rule here actually happened.

If you think you should be credited here and are not, open an issue and it will be fixed.

## Licence

MIT.
