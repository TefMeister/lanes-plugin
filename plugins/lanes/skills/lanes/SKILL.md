---
name: lanes
description: Use when several Claude sessions work one set of repos at once, or before editing anything in a repo other sessions touch - the lane rules, the create-only inbox hand-off, the board format, and the confidence tags. Also use when asked what a gate tag means, why a session is blocked from a job, or how to hand a finding to another lane.
---

# Working in lanes

Several sessions share these repos. Left alone they will edit the same files, rebase over each
other's uncommitted work, and quietly undo one another's fixes. Three rules stop that, and a
fourth keeps everyone's names out of what they write.

## 1. Every file has exactly one lane that may edit it

Reading is unrestricted. **Editing is not.** Before changing a file, know which lane owns it.

- `/pd` and `/lm` own the project's working files, its notes, and its `status/<project>.md`. They
  are the **same lane**, split by whether the app is running.
- `/gr` owns each project's `external-research/`.
- `/sr` owns the shared cross-project library.
- `/gs`, `/gates` and `/gate-watch` own **nothing** — they are read-only everywhere, which is what
  makes them safe beside anything.

Lanes share repos, so this is enforced by commit discipline: **stage only your own lane's paths,
never `git add -A`**, and `git pull --rebase` before pushing.

## 2. Anything crossing a lane boundary is a NEW file, never an edit

```
inbox/YYYY-MM-DD-<lane>-<short-slug>.md
```

Date plus author plus slug means two sessions can never collide on a filename, so git merges
cleanly by construction. **Never edit or delete an existing inbox file** — not even your own from
an earlier session.

Draining your own inbox: **read the whole thing first** (`grep -rn "^Supersedes:" inbox/`), then
delete **only the filenames you listed before you started**. Never by glob — a concurrent session
can drop a file inside that window, and a glob deletes it unread with nothing in git to show it
existed.

Corrections are new files carrying a `Supersedes:` header naming what they replace.

## 3. One session per lane, one session per job

Two sessions of one lane share a working tree and fight over git. The live claim
(`tools/lane-claim.sh`) serialises one **job** across machines: check it before starting, take it,
release it when you finish. `FRESH` means stop and say who holds it.

---

## 4. Nobody's name is written down, except the one they chose

In anything saved or published - notes, boards, commit messages, READMEs, issues, file names - the
person at the machine is **"User"**, or the display name they chose in `/lanes:setup`
(`tools/display-name.py` prints it). Never their real name, login, e-mail, machine names or
home-folder paths, even when you can see them; other people appear only under a public handle they
published themselves. Chat is not affected. Full text: `docs/PROTOCOL.md` §12.

## The board

One file per project, an `OPEN` block on top saying what each remaining step **requires**:

| Tag | Means |
| --- | --- |
| `[PD]` | needs nothing running |
| `[USER]` | needs a person, not the app |
| `[FLAT]` | needs the app running |
| `[VR CLAUDE]` | needs the hardware connected — the session operates it alone |
| `[VR USER]` | needs a person actually using the hardware |

Those four names are the whole vocabulary. Read the board with `/gates`; check one with
`gate-scan.sh --check`. Full grammar: `docs/BOARD-FORMAT.md`.

End a session by saying what the next step requires, in capitals. That is an **exhaustion** claim,
so audit the block before making it.

Beside it, name the **model tier** the next step needs, `STRONGEST` / `STANDARD` / `LIGHT`, with a
few words of why (`MODEL: STANDARD — a guided test`). Getting the work to succeed comes first, so
round up when it is close, but never spend the strongest tier on clerical or routine work. Tiers
and examples: `docs/PROTOCOL.md` §5. Print the gate and model lines together as a bold two-row
table (🚦 gate on top, 🧠 model below) so they cannot be skimmed past.

Give the reply's own headings fixed icons for the same reason: 🔧 **What I did**,
🎯 **What it means for you**, ❓ **What I need from you**, and ⚠️ **Worth knowing** for
anything that turned up outside the job. Fixed, so a reader who has seen two replies can jump
straight to ❓ without reading the rest. ⚠️ The sections stay short -- an icon is not room to
write more. `docs/PROTOCOL.md` §5.

## Optional tools

Missing a debugger, a decompiler, Blender MCP or a build tool? `/lanes:setup` walks through them
with official links (`docs/TOOLS.md`); `tools/setup-scan.py` shows what this machine already has.

## Code shape

Keep hand-written source files under **800 lines** (split first when an edit would pass it; past
**1,500**, splitting is the job). Split in a move-only commit on a backed-up branch, proven to
change nothing, before any behaviour change. Probes and tests live in their own files and move to
`archive/` the session they are disproved. Tunable numbers and per-build addresses get a **name**
in one settings table instead of sitting inline. Check with `tools/code-shape-scan.py`. Full
reasons and rules: `docs/PROTOCOL.md` §6.

## Confidence tags

`[verified-live YYYY-MM-DD, n=K]` · `[measured YYYY-MM-DD]` ·
`[verified-numerically YYYY-MM-DD, n=K]` · `[compile-verified YYYY-MM-DD]` ·
`[inferred-static]` · `[reported]` · `[hypothesis]` · `[disproved YYYY-MM-DD]`

**`n=1` is not verified.** An invented tag reads as a strong claim to a human and counts as
untagged to every tool. Untagged is treated as `[hypothesis]`.

⚠️ **A fix that removes the symptom *and* stops the failing path from being exercised has proved
nothing about the cause.** If the failing path no longer runs, it is a hypothesis however well the
fix worked.

---

Full detail: `docs/PROTOCOL.md` and `docs/BOARD-FORMAT.md` in this plugin.
