# The Inspector — IDEA ONLY, NOT BUILT (2026-09-23)

> **Status: idea, parked on the author's instruction — "don't create anything just yet please."**
> Nothing below exists. Do not build it until the author says go.

## Where it came from

The author found `peteromallet/desloppify` (a code-quality scorer for AI-written code) on 2026-09-23. We
agreed to use it only as a read-only report (`claude-memory/PREFERENCES.md` → "DESLOPPIFY IS A
READ-ONLY REPORT"). The same morning the author proposed building our own version instead, designed around
how the lanes work. Their words:

> *"instead of a plugin someone has made and trying to fit it into our system, why not just take the
> idea - design something that recognizes messy tangled code, reports that there is messy code that
> needs sorting out, knows where it is, maybe also knows the solution and runs after every time you
> write code"*

## The author's design, in their three steps

1. Claude writes code.
2. The **Inspector** goes over that code and writes what is messy (and optionally a suggested fix)
   into **a separate file — the only thing it may ever write to, never the game or mod files** — so
   the findings survive if the session ends abruptly.
3. In the **same session**, Claude reads the Inspector's file and checks every finding against the
   code it just wrote: is it really messy, or does it have to be like that to work? The author accepts this
   makes sessions more expensive and slower.

## Claude's opinion (2026-09-23)

**Worth building, and better than fitting desloppify in.** Notes for whoever builds it:

- **It is the grown-up version of `tools/code-shape-scan.py`, not a new thing.** That scanner already
  checks file size, Lua's 200-locals limit and loose numbers. Grow it rather than start again.
- **Two halves, with different costs.**
  - *The checker* is a plain script: free, fast, deterministic. It can run automatically after every
    code write (a hook on file edits).
  - *The verdict* is Claude reviewing the findings: that is what costs tokens. Run it once per chunk
    of work, before the commit, not after every single edit, or a session spends more on reviewing
    than on building. Still inside the same session, as the author asked.
- **The verdict step is the most valuable part, and what desloppify lacks.** Each finding gets one of:
  *real, fix it* / *real, fix later (becomes a board row)* / *has to stay like this, because …*. The
  "has to stay" answers are remembered with their reason, so the same thing is never flagged twice.
  That is what protects headset-tuned code from being "tidied" into something broken.
- **Report only what is NEW or WORSE since the last check.** A report that repeats old findings every
  time trains everyone to skip it — the same lesson as `DUMP.md` in mod-ideas.
- **Check OUR rules, which no outside tool knows:**
  - files over 800 / 1,500 lines; bare numbers outside the settings table;
  - per-build addresses scattered instead of in one address table;
  - probes and tests still wired into the working file after they were disproved (should be archived);
  - hotkeys on F-keys instead of the numpad;
  - the same helper copy-pasted across several games' code;
  - a log limit that also switches off the behaviour it logs (the Far Cry 2 "stopped after ten shots"
    lesson from phunkaeg's playbook);
  - plus the general kinds desloppify finds: duplication, dead code, tangled functions.
- **Fixing stays under the existing rules.** The Inspector never edits code. A tidy-up it leads to is
  move-only, on a branch, with a `pre-split` tag, proven to change nothing — `PROTOCOL.md` §6.
- **Open questions for the author before building:**
  - Where the findings file lives: per project (e.g. `dev-archive/INSPECTOR.md`, committed with the
    work) is the obvious choice, so it follows the game between PCs.
  - Whether the verdict pass should be skippable when a session is short on quota
    (`feedback-usage-limit-small-batches`).

**Model to build it:** OPUS — design is settled enough; it is careful wiring, not new maths.
