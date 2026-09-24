---
description: (Guided Research) Public-research sweep across every project. Reads each project's own notes first, then the open web; curates ONLY that project's external-research/ folder, and hands everything else over as create-only inbox drops. Never launches the app. Safe beside every other lane.
---

`/gr` — **the per-project research lane.**

Argument: `$ARGUMENTS` — optional. Bare `/gr` sweeps every project; `/gr <name> …` scopes it to
one or more; `/gr skip:<name>` excludes.

## Hard scope — the one-writer-per-file rule

Every file has exactly one lane that may edit it. Reading is unrestricted; editing is not.

| | |
| --- | --- |
| **This lane curates** | `<project>/external-research/` — and nothing else, in any repo |
| **This lane may create** | new files in any other lane's `inbox/` |
| **This lane must never** | edit a file another lane curates, drain someone else's inbox, or launch the app |

Cross-lane findings travel as **new, uniquely named files** dropped into the receiving lane's
`inbox/`, named `YYYY-MM-DD-gr-<short-slug>.md`. Because the filename carries a date, an author and
a slug, two sessions can never produce the same name — so git always merges cleanly, **by
construction rather than by discipline**.

⚠️ Since the lanes share one repo per project, that boundary is enforced by commit discipline
rather than by permissions: **stage only your own lane's paths, never `git add -A`**, and
`git pull --rebase` before pushing.

### Running alongside other sessions

Safe beside `/pd`, `/lm`, `/sr` and `/gs` — different files throughout. ⚠️ Two `/gr` runs must not
overlap on the same project.

**Never launch the app**, and never start a debugger or attach to a running process. A research
session that launches something collides with the live lane's one slot.

## 🤖 Background helpers are allowed in this lane

Ask before spawning one: *could the user name this helper's job without asking?* The line is
**opacity, not concurrency**. Keep the count small, give each a stated job, and say in the report
what each returned.

## 0. Your clone root is not the live lane's

Work in this lane's own clone root, and `git pull` early and often.

**First, make sure your root holds every repo.** A repo added to one lane's root after the others were
made is invisible to this lane, and nothing fails: the session just covers fewer projects than exist
and reads as complete.

```bash
bash "${CLAUDE_PLUGIN_ROOT}/tools/root-sync.sh" --fix
```

It copies in any repo another root has and this one lacks (a near-free local clone pointed at the real
remote), never touches an existing clone, and says `all N clone roots hold all M repos` when there was
nothing to do. Name anything it `SKIPPED` or `FAILED` in the write-up.

## 1. Orient once, before touching any project

1. **Drain your own inbox** — `<project>/external-research/inbox/` for every project in scope.
   **Read the whole inbox before draining any of it**, and check for `Supersedes:` headers first:
   draining oldest-first writes a claim into the library and only then meets its withdrawal.
2. **Drain by explicit filename list, never by glob.** Record what `ls` returned *before* folding
   anything in, and delete only those names. A concurrent session can drop a file inside that
   window, and a glob deletes it unread with nothing in git to show it existed.
3. Read the board so you know what each project is actually blocked on.

## 2. Read the in-house record BEFORE searching the web

For each project, in this order:

1. That project's own **`external-research/`** — the index and topic files, with their sources and
   dates. The point is to **skip duplicate research** and re-check known sources for updates only.
2. The **cross-project library**, for anything already known that is not project-specific.
3. That project's **own notes and dead ends.** Turn the dead ends into search targets.

**Searching cold wastes the session re-finding what is already known.** This step is not optional
and it is not a formality.

## 3. Scope and order

You will not reach every project at full depth, so choose deliberately.

- **FULL pass** — a project that is actively blocked, or has not been swept in a long time.
- **CHECK-IN pass** — a project that was swept recently: re-check known sources for updates, stop.

**Stamp every project you touch** with the date of this pass. That stamp is the rotation bookmark;
without it the next sweep cannot tell what it already covered, and the busiest projects quietly
starve the quiet ones.

**Stopping is a decision, not a failure.** Say which projects got a full pass, which got a
check-in, and which were not reached at all.

## 4. Write it up

- Findings about a project go into that project's **`external-research/`**, which you curate.
- Findings that answer another lane's open question go into **that lane's `inbox/`** as a new file.
- Anything project-agnostic goes into the **cross-project library's `inbox/`** — one drop per
  finding, whichever fits best, never duplicates.
- **Tag every durable claim** with a confidence tag. Untagged is treated as `[hypothesis]`.
- **Corrections are new files carrying a `Supersedes:` header line** naming what they replace —
  never edits to the file being corrected.

## 5. Finish

Stage only `external-research/` paths and your inbox drops. `git pull --rebase`, then push. Report
what was swept, what was found, and what is now worth someone else's time.

⚠️ **Never cite or link a source that distributes material illegitimately**, even when researching
a legitimate topic. Mainstream sources and legitimate tools only.
