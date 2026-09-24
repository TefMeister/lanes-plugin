# Task zero, answered — hooks DO fire inside subagents, but the payload cannot tell the reader from its parent

**Answers:** `2026-09-10-one-session-reader-design.md` § 2.
**Run by:** a `/pd` session on the dev PC (`<DEV-HOST>`), 2026-09-10.
**Status:** SETTLED, both halves — see § 6, added the same afternoon after the user approved the
experiment § 3 asked for. **The `if yes` branch IS buildable**, with the guard keyed on a field the
session-keyed original never looked at. Nothing has been deleted and no code has been changed.

---

## 1. The question

> **Does a `PreToolUse` hook fire for a tool call made by a subagent?**

## 2. Yes. Verified against a live hook, not a mock

The probe deliberately used a **real, already-wired `PreToolUse` hook** rather than a throwaway one,
because a throwaway needs a settings change and would have proved only that the throwaway worked.
This machine wires `rtk hook claude` (rtk: a third-party tool that shortens command output before
Claude reads it) on `PreToolUse` with matcher `Bash`, and that hook **rewrites**
the command, so its output is visibly different from the unhooked command. That makes the hook's
presence observable from the outside with nothing installed.

| | command | output |
| --- | --- | --- |
| control (main session) | `git status` | `* main...origin/main` / `clean — nothing to commit` \u2014 **2 lines, rewritten** |
| probe (subagent) | `git status`, identical cwd | **byte-identical 2 lines** |

Unhooked, the same command in the same directory prints **four** lines beginning `On branch
main` — measured in this session via `rtk proxy git status`, which runs the raw command with the
filtering bypassed, rather than assumed from how git usually behaves `[verified-live 2026-09-10]`.
Both the control and the subagent got the rewritten two.
**`PreToolUse` fires for a subagent's tool call** `[verified-live 2026-09-10, n=1]`.

\u26a0\ufe0f `n=1`, one hook, one tool (`Bash`). It was **not** shown for `Write`/`Edit`, which is the matcher
the reader's guard would actually use. Nothing suggests they differ, but nothing here demonstrates it
either, so treat "the guard's own matcher fires" as `[hypothesis]` until a `Write` is tried the same
way.

## 3. \u26a0\ufe0f The finding that matters more: parent and subagent share ONE session id

A second probe compared the identifiers a `Bash` call sees:

| | `CLAUDE_CODE_SESSION_ID` | OS pid |
| --- | --- | --- |
| main session | `11111111-1111-4111-8111-111111111111` | 20652 |
| subagent | **the same, character for character** | 19644 (different) |

`[verified-live 2026-09-10, n=1]`

**Why this breaks the `if yes` branch.** `tandem-guard.py` — the guard the spec proposes to keep a
"much simpler successor to" — decides entirely on the payload's `session_id`: it looks the session up
in the marker file and refuses if it is marked. With one id covering both, such a guard has **no way
to tell the reader's write from the `/lm`'s own**. It would either:

- refuse both, which breaks `/lm` — and `/lm` writing `status/<project>.md` is its whole job; or
- allow both, which is no guard at all.

The spec's § 2 fork offers "keep a guard" or "no write tools". **This is a third case it does not
cover:** hooks fire, but the thing the guard keys on does not discriminate. Picking the `if yes`
branch and building the simple successor would have produced a guard that looks right, passes a
unit test against synthetic payloads, and protects nothing.

\u26a0\ufe0f **One honest gap in this measurement.** What was compared is the **environment variable seen by
`Bash`**, not the `session_id` **field of the hook's stdin payload**. They agree for the parent —
`pd-guard.py` writes the payload's `session_id` into `~/.claude/pd-session.lock`, and that file holds
exactly the env var's value — so the two agree where they can be compared `[verified-numerically 2026-09-10, n=1]`.
That the **subagent's payload** field also matches is `[inferred-static]`, not measured. It is the
likeliest reading by some distance, but the design should not rest on it unexamined.

**The one experiment that settles it**, and it needs the user's permission because it edits
`~/.claude/settings.json`: add a `PreToolUse` hook on `Write|Edit` that appends its whole stdin
payload to a log, have a subagent attempt a `Write`, and read the logged `session_id`. Auto-mode's
classifier refused every write into `~/.claude/` during this session, which is why it was not done —
that is a permission boundary, not a technical one.

## 4. What this means for the build — do NOT pick a branch yet

The spec says *"Do not write the fallback and the main path both. Find out first, then build one."*
That instruction still holds, and the honest position is that **the answer selects neither branch as
written**. Three ways forward, in the order they look best from here:

1. **Find a discriminator in the payload other than `session_id`.** If the `PreToolUse` payload
   carries anything naming the agent (an agent id, a tool-use id chain, an `agent_type`), the guard
   keys on that instead and the `if yes` branch works essentially as intended. **This is the same
   experiment as § 3's** — one logging hook answers both questions at once. Cheapest, and it is the
   only option that preserves the reader's ability to build.
2. **Take the `no write tools` branch** — the reader gets `Read`/`Grep`/`Glob` only. Enforcement
   stops being a hook at all, which is the stronger guarantee the design was originally pitched on,
   and § 2's honesty note then applies without qualification. The cost is real and § 2 already names
   it: building moves to the main session.
3. **Guard on the path's lane root instead of the session.** Weakest of the three and listed for
   completeness: it would refuse status writes from any clone root the reader works in. It fails the
   moment both use the same root, which they do.

**Recommendation: run the § 3 experiment before choosing**, because option 1 is strictly better than
option 2 if it is available, and one hook and one subagent settle whether it is. It needs one
approval from the user.

## 5. What was NOT done, deliberately

- **Nothing was deleted.** § 3 of the design (`tandem-guard.py`, the `--tandem` claim kind, the
  rendezvous lines, the 14 assertions) is untouched, because the spec puts task zero first and task
  zero has just changed what the replacement must look like.
- **The `feedback-no-subagents-work-inline` note and `PREFERENCES.md` are untouched** (design § 9).
  That rule is lifted for a reader agent that does not exist yet; lifting it now would leave the
  estate permitting something nothing implements.
- **No settings, marker or config file was modified.** Two writes into `~/.claude/` were attempted
  and refused by the auto-mode classifier; both were abandoned rather than worked around, and the
  probe was redesigned to need neither. `~/.claude/lanes-tandem.json` was read and is still `{}`.

---

## 6. ✅ The experiment from § 3 was run, and it answers everything above

The user approved the settings change at 15:00. A temporary `PreToolUse` hook on `Write|Edit`
dumped its **entire stdin payload** to a log; the main session made one `Write`, then **one**
subagent made one `Write`. The hook was removed and `settings.json` verified byte-identical to its
backup afterwards. Raw payloads: `2026-09-10-task-zero-payloads.txt` (file contents elided, nothing
else).

| field | main session | subagent |
| --- | --- | --- |
| `session_id` | `11111111-…` | **identical** |
| `transcript_path`, `cwd`, `scratchpad_dir`, `prompt_id`, `permission_mode` | … | **all identical** |
| **`agent_id`** | **absent** | `ad8ab8b2746c15308` |
| **`agent_type`** | **absent** | `general-purpose` |

`[verified-live 2026-09-10, n=1 each]`

**What this closes:**

- § 2's hypothesis — that the guard's own `Write|Edit` matcher fires for a subagent — is now
  **verified**, not inferred. And the hook was picked up **mid-session**, without a restart.
- § 3's honest gap — whether the *payload's* `session_id` matches, not just the env var — is now
  **verified**: it matches. A session-keyed guard genuinely cannot discriminate.
- § 4's option 1 — *find a discriminator other than `session_id`* — **exists.** Two fields appear
  **only** in a subagent's payload: `agent_id` and `agent_type`.

**So the design's `if yes` branch is buildable, with one change to what the successor guard keys
on.** Not the session marker — the **presence of `agent_id`** in the payload. The rule becomes:
*a `Write`/`Edit`/`Bash`-write to `<board>/status/*.md` whose payload carries `agent_id` is refused;
the same write without one is the `/lm` itself and passes.* No marker file, no `UserPromptSubmit`
latch, no `SessionEnd` cleanup — three of the four pieces `tandem-guard.py` needed disappear, because
the discriminator is in every call rather than remembered between calls. `agent_type` can narrow it
further if the reader is launched as a named agent type, but presence of `agent_id` is the safer
default: no subagent should ever write the board's status files.

⚠️ Still `n=1`, one agent type, one tool. Before the guard is trusted, its test fixture should
feed it (a) a parent payload, (b) a subagent payload with `agent_id`, and (c) a subagent `Bash`
payload with a write construct — and the real thing should be tried once from an installed copy.
The README should say plainly that the reader keeps write tools and the control is therefore a hook
(§ 2's honesty note), and that the hook now keys on a documented payload field.

## 7. The user's condition, restated correctly (2026-09-10, later the same afternoon)

An earlier version of this section read the user's words as a demand to be *included in each step*.
**That was wrong, and the user corrected it:** *"i over complicated this. LM running on its own with
the background helper, as automated as possible IS the outcome i wanted. i was describing how it
felt when 3 agents were doing stuff developing a mod that i had no idea of, what these agents are.
if it's only PD, then i kind of know what it is."*

So the condition is the one the design's § 4 already states — **legibility**: one helper, named,
announced, whose job the user could state without asking. Not inclusion. The build target is the
opposite of a gate: *"the less i have to come to dev pc, the better, because i am at work at the same
time."* `/lm` launches and closes the game as it pleases, runs the reader alongside, and reports.
The user's recap of the whole estate after this change:

- **`/lm`** — picks the next game needing flat work, runs as automated as possible, **includes the
  PD reader as its one background helper**.
- **`/pd`** on its own — unchanged: no-game work, auto-picks the next game.
- **`/gs`, `/gr`, `/sr`** — unchanged; likely run at the start of an `/lm`.
- **`/lm i launch`** — unchanged: ask when the game is needed, the user launches when convenient
  and says *all yours*.
