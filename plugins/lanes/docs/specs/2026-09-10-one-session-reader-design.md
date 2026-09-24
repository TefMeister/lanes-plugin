# One session, one reader — retiring the two-session tandem seat

**Status:** approved by the user 2026-09-10. Not yet built.
**Written by:** `/pt` (test lane), from a design conversation the same day.
**Built by:** a `/pd` session on this repo. `/pt` may not touch code.
**Supersedes:** the tandem seat as shipped in 0.3.0 — `commands/pd.md` § "🚲 Tandem",
`hooks/tandem-guard.py`, the `--tandem` claim kind, and the rendezvous line in `gate-scan --next`.

---

## 1. The decision

**Two sessions will no longer pair on one job.** Pairing becomes something that happens *inside*
one `/lm` session: `/lm` runs **exactly one** background reader agent, which does what a tandem
`/pd` did — read, measure, analyse — while `/lm` does the live work and owns every write.

The user's words, 2026-09-10: *"what if we can have PD as a background agent and eliminate the 2
sessions all together … maybe all this work finally landed us here in the simplest version of the
plugin, where other people do not have to run more than 1 session at a time."*

### Why — the evidence, not the aesthetics

| Fact | Source |
| --- | --- |
| 2 of this plugin's 8 faults are tandem-seat faults, and they are the two most recent | `docs/FAULTS.md` 6, 8 |
| The only **open** fault is a tandem fault | `docs/FAULTS.md` § Still open |
| Pairing on one job: **1 clean run in 50**. Two lanes on different jobs: **18 in 50, none ever broken** | `tools/run-log.sh` `[verified-numerically 2026-09-10]` |
| Every collision on record — all three — is one file, `status/<project>.md`, written by both lanes | fault 6 |
| The design drafted to fix it needed **four** new mechanisms: a rendezvous, a 5-minute timer, a role swap, and a mid-step lock | this conversation, superseded by this document |

Four new mechanisms to let two sessions share one job is the signal. One session sharing itself
needs none of them.

### What this is NOT

It is **not** a rewrite of the plugin. It deletes one feature. `/pd` as a standalone lane, the claim
protocol, the board, the gate tags, `/gr`, `/sr`, `/gs`, the clone roots and both test suites all
stay exactly as they are. Section 5 lists what survives untouched, because the instinct on reading
section 3 will be that more is going than actually is.

---

## 2. ⚠️ Task zero — the assumption the whole design rests on

**Does a `PreToolUse` hook fire for a tool call made by a subagent?**

> ✅ **ANSWERED 2026-09-10 — read `2026-09-10-task-zero-result.md` before building anything.**
> Yes, hooks fire inside subagents. **But the answer does not select either branch below**, because
> a subagent's tool call carries **the same `session_id` as its parent** — so a guard keyed on the
> session, like `tandem-guard.py` is, cannot tell the reader's write from `/lm`'s own.
> **Resolved the same afternoon (that file § 6):** a subagent's payload carries `agent_id` and
> `agent_type`, which the parent's never does. **Build the `if yes` branch, with the guard keyed on
> the presence of `agent_id`** — no marker file, no latch.

Everything in section 4 about *enforcing* the reader's boundaries assumes yes. **Verify it before
building anything else.** Write a throwaway agent that attempts a write the guard should refuse, and
observe whether the guard runs.

- **If yes** — keep a guard (a much simpler successor to `tandem-guard.py`) that refuses
  `<board>/status/*.md` writes from the reader. The reader may then hold write tools, so it can
  build in a staging area as the tandem seat could.
- **If no** — the reader gets **no write tools at all** (`Read`, `Grep`, `Glob`, and no
  `Write`/`Edit`/`NotebookEdit`), and any building moves to the main session. That is a real loss of
  capability and should be recorded as such, not glossed.

Do not write the fallback and the main path both. Find out first, then build one.

> **Honesty note on the argument that sold this design.** It was pitched to the user as "a toolbox
> with no writing tools in it can't break the rule, unlike a hook that fails open". That is true only
> in the *no-write-tools* variant. The moment the reader keeps `Bash` or `Write` so it can build, the
> control is a hook again — better placed than before, but not absolute. Say which variant shipped
> in the README rather than repeating the stronger claim. `[hypothesis]` until task zero settles it.

---

## 3. What is deleted

| Thing | Why it goes |
| --- | --- |
| `hooks/tandem-guard.py` and its wiring in `hooks/hooks.json` | nothing to guard: one session, one owner of writes |
| its 14 assertions in `tools/tests/hooks-test.sh` | with it |
| `commands/pd.md` § "🚲 Tandem — riding along with a live `/lm`" | the seat no longer exists |
| `--tandem` in `tools/lane-claim.sh`, and the `TANDEM` claim kind | no second session to seat |
| the `TANDEM:` rendezvous lines in `tools/gate-scan.sh --next` | with it |
| the `A1a` / `A1b` split in `docs/RELEASE-CHECKLIST.md` | see § 6 |

**Fault 8 dissolves rather than being fixed** — with no `tandem` keyword there is no keyword for the
block message to drop, and `/pd` and `/lm` are never meant to share a job again, so blocking is
simply correct. ⚠️ **One real half of it survives and must still be fixed:** the block message
rebuilds the suggested command as `lane + " force " + jobs`, so it also silently drops `skip:`
arguments and any other modifier. Rebuild it from the user's own tokens.

---

## 4. What replaces it — the reader

### Shape

`/lm <project>` runs its pre-flight exactly as it does now. Immediately after stating the gate, it
starts **one** background agent and says so in plain language. One. Never two, never conditionally
more.

### The reader's job

The tandem seat's own table, unchanged in substance:

| | |
| --- | --- |
| read, analyse, measure, decide | ✅ **this is the job** |
| write code in a staging area and **build** it | ✅ — *only in the write-tools variant, see § 2* |
| **deploy — replace any file the app loads** | ⛔️ never |
| edit the curated notes | ⛔️ never |
| edit `<board>/status/*.md` | ⛔️ never |

The deploy ban keeps its original reason and it has not weakened: the live session may have the app
**running** on the current build, holding that code in memory. Swap the artifact and every
measurement belongs to a build that no longer exists, while a deployment check still reports OK.

### Visibility — this is the user's actual condition

The user's standing objection was never concurrency. Verbatim, 2026-09-10: *"that is only because
previously there was like 2-3, maybe more agents doing something i had no idea what they were
working on. If there is 1 background agent and i know it's PD doing what it's been doing so far,
that changes it."*

So the reader must be **legible**, and that is a hard requirement, not a nicety:

1. **Announced when it starts** — one plain line naming what it has been asked to look at.
2. **Announced when it finishes** — its findings relayed in plain English by `/lm`, not pasted raw.
3. **Never silent while working.** If `/lm` is waiting on it, say so.
4. **Exactly one.** If a second would ever help, that is a design change and needs asking.

### Talking to it mid-session

`/lm` can send the reader follow-up questions while it runs, and should, because that is what the
two-window shape was actually good at. Findings flow reader → `/lm` → user, and instructions the
other way.

---

## 5. What survives, untouched

- **`/pd` as a standalone lane.** Unchanged. The whole-estate sweep with nothing running is a real
  mode the user relies on daily (*"dev PC = all PD then all FLAT"*), and it is not what is being
  retired here.
- **The claim protocol.** Still needed for `/pd` vs `/pd`, `/lm` vs `/lm`, and two machines working
  at once. `lane-claim-guard.py` stays; only the `--tandem` kind goes.
- **The board, the gate tags, `gate-scan.sh`, `gs-scan.sh`, `run-log.sh`.**
- **`/gr`, `/sr`, `/gs`** and the create-only inbox hand-off.
- **One clone root per session type.** Still true: separate *lanes* still run in separate windows.
- **`smoke-test.sh`** in full.

---

## 6. Bars and counts

- **Retire `A1a`** (50 clean tandem runs). Do not mark it failed and do not carry it at 1/50 —
  the shape it measured will not exist. Replace the row with a one-line note saying it was retired
  on 2026-09-10 because the two-session pairing was deleted, and why. A bar quietly dropped is how a
  public claim goes bad; a bar openly retired with its reason is fine.
- **`A1` becomes the separate-projects count only** — 18/50 today, the shape that has never broken.
- **Add a new bar:** *N clean `/lm` runs with the reader*, harvested, not typed. `run-log.sh` needs a
  new mode for it: a run is clean when the reader wrote nothing it was not allowed to write.
- **Version bump to 0.4.0 is mandatory**, not optional — components are removed and added, and an
  installed plugin is a snapshot in a cache that does not update without it (fault 🔍 C).

---

## 7. Testing

1. Task zero (§ 2) — first, before any deletion.
2. Delete the tandem assertions from `hooks-test.sh`; both suites must still pass **from an installed
   copy**, on both machines (bar B1).
3. Add assertions for whichever enforcement variant task zero selects.
4. Re-run `/pt` afterwards: both suites, all six tool outputs against the originals in
   `claude-memory/tools/`, and the guards against the live claim state.
5. ⚠️ The originals in `claude-memory/tools/` **do not have this change**. After it, `/pt`'s
   tool-vs-original diff will show real differences in `lane-claim.sh` and `gate-scan.sh` for the
   first time. Either port the same deletions upstream, or record in `docs/FAULTS.md` that those
   specific differences are expected — otherwise the next `/pt` run reports a fault that is not one.

---

## 8. Risks, stated plainly

| Risk | What it would do | What reduces it |
| --- | --- | --- |
| Hooks may not fire inside subagents | the reader's boundaries would be unenforced while the README says otherwise | task zero, § 2 — settle it first |
| A reader that goes quiet | the exact opacity the user objected to, reintroduced | § 4 visibility rules are requirements |
| A reader that dies | less obvious than a window closing | `/lm` reports it and carries on alone, saying so |
| Losing the ability to talk to `/pd` directly | the two-window shape allowed a real conversation with the reader | mid-session messaging, § 4 |
| Over-deleting | `/pd` standalone and the claim protocol are load-bearing elsewhere | § 5 is the list; check it before removing anything not in § 3 |

---

## 9. One thing that must be recorded outside this repo

The user's standing note **`feedback-no-subagents-work-inline`** says background agents are
**NEVER** allowed in `/lm`. That is being lifted, deliberately, by the user — for **one** named
reader agent only, and for the reason given in § 4.

**`/pt` cannot write it** (it may not touch anything outside this repo). The `/pd` session that
builds this must update that note, and `claude-memory/PREFERENCES.md`, or a future session will read
the old rule and refuse to start the reader. This is the single most likely way the work gets
silently undone.
