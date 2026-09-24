# Your board

This is the shared memory the `lanes` plugin reads. Copy this folder into a **new private repo**,
delete the example project, and point the plugin at it:

```
# ~/.claude/lanes.conf
board = /path/to/this-repo
role  = DEV
```

Make it **private**. It is your working notes, and everything in it is yours — the tools only ever
read `status/*.md` and `machine-assignments.tsv`.

## What is here

| Path | What it is |
| --- | --- |
| `status/<project>.md` | one file per project: the `OPEN` block on top, the dated log below |
| `machine-assignments.tsv` | which machine owns which project |
| `.gate-snapshot` | written by `/gate-watch`, **gitignored**, per-clone by design |

## The one rule that makes it safe

**Only ever edit the file for the project you are working on, and stage only that path.** One file
per project is what lets several sessions run at once without ever touching the same file.

## The format

See `docs/BOARD-FORMAT.md` in the plugin. The short version:

- exactly one `OPEN (YYYY-MM-DD):` block per project file, above the log
- every row tagged `[PD]` / `[USER]` / `[FLAT]` / `[VR CLAUDE]` / `[VR USER]`
- idle is written `OPEN (YYYY-MM-DD): none` — never omit the block
- the date is when the block was last **audited**, not when its oldest row was added

Check a board at any time:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/tools/gate-scan.sh" --check .
```

## First run

```bash
git init -b main
git add -A
git commit -m "my board"
# then push it to a PRIVATE remote and set origin/main -
# the tools read origin/main, not your working tree
```

That last part is deliberate: reading the pushed state rather than this disk is what makes the
board safe to consult from any lane's clone root, and what stops a stale checkout reporting its own
past as the present.
