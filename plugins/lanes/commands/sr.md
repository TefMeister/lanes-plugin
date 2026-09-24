---
description: (Sweep Research) Cross-project research sweep. Reads every project's notes and the open web; curates ONLY the shared cross-project library, and hands everything else over as create-only inbox drops. Never launches the app. Safe beside every other lane.
---

`/sr` — **the cross-project research lane.**

Where `/gr` goes deep on one project, `/sr` looks for what is true across all of them, and puts it
somewhere every project can reach.

## Hard scope — the one-writer-per-file rule

| | |
| --- | --- |
| **This lane curates** | the shared cross-project library — and nothing else, in any repo |
| **This lane may create** | new files in any other lane's `inbox/` |
| **This lane must never** | edit a file another lane curates, drain someone else's inbox, or launch the app |

Drops are named `YYYY-MM-DD-sr-<short-slug>.md`. Create-only: no session ever edits or deletes an
existing inbox file, **not even its own from an earlier session**. A non-empty inbox is a visible
to-do, never a silent loss.

⚠️ **Stage only your own lane's paths, never `git add -A`**, and `git pull --rebase` before pushing.

⚠️ On the shared board repo, `/sr` may append one dated line to the changelog — **never to the
status board itself.**

## 🤖 Background helpers are allowed in this lane

Same test as `/gr`: could the user name this helper's job without asking? Small count, stated jobs,
reported results.

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

## 1. Orient

**Drain the library's `inbox/` first.** Read the whole inbox before draining any of it, and
`grep` for `Supersedes:` headers before you start — draining oldest-first writes a claim into the
library and only then meets its withdrawal. Drain by explicit filename list, never by glob.

## 2. Harvest the in-house repos — bounded by date, not by reading everything

Do **not** re-read every project's notes. Harvest by **git delta since the last sweep's logged
date**. That bound is the difference between a sweep that finishes and one that does not.

Read our own trial-and-error record before searching the web — especially the recorded dead ends,
which convert directly into search targets. Searching cold wastes the session re-finding what is
already known.

## 3. Curate the shared view

The library holds one page per topic family: the shared truth, linking out to each project's own
notes. **The unification is a view, not a relocation** — per-project notes stay where they are and
stay owned by their own lane. Never move a project's knowledge into the library; link to it.

## 4. Sweep the web

Fill the gaps the harvest exposed. **Tag every durable claim** with a confidence tag; untagged is
treated as `[hypothesis]`. Record dead ends as deliberately as successes — they are what makes the
next sweep cheap.

⚠️ **Never cite or link a source that distributes material illegitimately**, even when researching
a legitimate topic. Mainstream sources and legitimate tools only.

## 5. When done

- Anything that belongs to a project goes into **that project's `inbox/`** as a new file — one drop
  per finding, never duplicates.
- Corrections are **new files carrying a `Supersedes:` header line** naming what they replace,
  never edits to the file being corrected.
- Append one dated entry to the sweep log so the next `/sr` knows where its delta window starts.
- Stage only the library's paths and your inbox drops. `git pull --rebase`, push, report.
