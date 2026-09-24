# The board format

The board is an ordinary **private** git repo. Nothing in it is magic; the tools read three
things, and everything else in the repo is yours.

```
your-board-repo/
  status/
    project-one.md          one file per project
    project-two.md
  machine-assignments.tsv   which machine owns which project
```

`status/` is the only required folder. `machine-assignments.tsv` is only needed for `--mine` and
`--next`, and without it every project falls back to one role — the tools say so out loud rather
than quietly reporting "nothing is yours".

**One file per project, and only ever edit the file for the project you are working on.** That is
what lets two sessions run at once without touching the same file.

---

## 1. The `OPEN` block

Each `status/<project>.md` carries **exactly one** `OPEN` block, near the top, above the dated log.

```
OPEN (2026-09-02):
  [PD]   derive the parent case statically
  [FLAT] run the position probe - does it move with the player or the camera
  [VR CLAUDE] does a session open and hold steady for a minute
  [VR USER]   judge world scale at 0.6
  [USER] copy the new build to the other machine
```

The log below records what *happened*. The `OPEN` block records what each remaining step
**requires** — so a person can tell, without asking and without a session running, whether to do
static work, start the app, or put the hardware on.

### The five tags — the whole vocabulary

| Tag | Means | The test |
| --- | --- | --- |
| `[PD]` | Advanceable with **nothing running**, so it can proceed while the machine's one "app may run" slot is taken. | Could a session finish this without launching anything? |
| `[USER]` | Needs **a person**, not the app — a file copied between machines, an install, a decision. **Write it as numbered steps: PROTOCOL.md §10.** | Is the blocker a human action rather than a running process? |
| `[FLAT]` | Needs the **app running** — does it load, does the hook fire, do the logs read as predicted. | Would a screen and a keyboard answer it? |
| `[VR CLAUDE]` | Needs the hardware **connected and awake**, but nobody using it. The session drives it and reads the answer off a log, a capture or a crash. | Could a log or a screenshot state the outcome? |
| `[VR USER]` | Needs **a person using the hardware** — wearing it, holding it, judging how it feels. | Does answering it need human eyes, hands, or a judgement of feel? |

**An invented tag reads as meaningful to a human and counts as nothing to the scanner.** The
names came from VR game modding; read them as *needs nothing* / *needs a person* / *needs the app*
/ *needs the hardware* and they fit most work.

`FLAT` vs `VR` tiebreak: **if a screen can answer it, it is `[FLAT]`** — the cheaper mode wins.

### Rules that make the block mean something

- **The date is when the block was last *audited*,** not when its oldest row was added. A block
  older than the file's newest log entry is a session that logged work without re-auditing what is
  left. The hygiene scan flags exactly that.
- **Idle is written `OPEN (YYYY-MM-DD): none`.** Never omit the block. A missing block makes the
  board understate, which is worse than it sounds — the whole point of the board is an
  **exhaustion** claim, and a claim like "there is nothing left that needs no app" is only worth
  anything if every project answered.
- **Row grammar:** two spaces, `[TAG]`, one space, imperative text. An optional machine qualifier
  goes inside the brackets: `[PD @home]`.
- **A date suffix on the block is allowed** — `OPEN (2026-09-03c):`, `OPEN (2026-09-02, evening):`
  — because a project can be audited several times in a day and a bare date cannot say which. The
  scanner reads the first date on the line.
- **⚠️ Only current work goes on the list.** Long-tail "someday" ideas stay in the log below. This
  is the difference between the block working and rotting: if the wishlist gets enumerated, the
  `[PD]` bucket never empties, the "everything static is done, start the app" signal never fires,
  and the board becomes decoration. An item comes off when it is **done**, or when it is
  **deliberately deferred** — and deferral means moving it back into the log with a note, not
  leaving it to age in `OPEN`.

---

## 2. The `LIVE` claim

One line, directly above the `OPEN` block, written and pushed by whichever session is working that
project:

```
LIVE: /lm 2026-09-06 14:02 WORKSTATION
```

`<lane> <date> <time> <host>`. Written and removed by `lane-claim.sh`; never by hand.

- **`FRESH`** — under 12 hours old. That project is taken. Another same-lane session must not start
  on it.
- **`STALE`** — older than 12 hours. That session most likely died; the next `take` replaces it.
- The **host** matters as much as the lane: two sessions on *different* projects but the *same*
  machine still share one keyboard. See "one running app per machine" in `/lm`.

*(0.3.0 allowed a second `TANDEM:` line above it for a reader session. Retired in 0.4.0 — the
reader is a background agent inside the `/lm` session now and needs no line. A `TANDEM:` line left
in an old file is inert and can simply be deleted.)

**Why a written claim rather than "was there a commit recently".** A session once looked at another
lane's commit from twenty-seven minutes earlier, judged that session finished, and undid its fix.
Git was clean; the loss was semantic. The claim takes the judgement out of it. It serialises **one
project**, not a whole lane, and the push is what arbitrates — losing that race is normal, and the
answer is to re-pick, not to stop.

---

## 3. `machine-assignments.tsv`

Two tab-separated columns: the role, and the project it owns. `*` is the catch-all.

```
# role	project
HOME	project-one
DEV	project-two
DEV	*
```

Roles are labels **you** choose. This machine's role comes from `$GATE_ROLE`, then
`role = <name>` in `~/.claude/lanes.conf`, then `DEV`.

`[VR CLAUDE]` and `[VR USER]` rows are always given to the role that has the hardware, whoever owns the project.

⚠️ The file is read with CRLF tolerated, because it is usually edited on Windows. Without that, a
trailing carriage return makes **every** row fail to match, including `*`, and `--mine` silently
reports that nothing belongs to this machine.

---

## 4. Checking a board

```bash
bash tools/gate-scan.sh --check /path/to/board
```

Reports missing, malformed and stale blocks. It is the same parser the board itself uses — **two
parsers for one grammar drift, and the drift is silent**: the board would show items the checker
calls malformed, or pass a file the board renders wrongly.

Everything is read from `origin/main` via `git fetch` plus `git show`, never from the working tree,
so it is safe to run from any lane's clone root and it reports what was actually pushed rather than
what happens to be on this disk.
