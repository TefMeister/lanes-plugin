---
description: "(Keeper) The Keeper's round: upload what was handed over, then bring the front page, the index and the downloads up to date."
---

`/keeper` — **the Keeper's round.** Asked for by the maintainer, 2026-11-11: one session builds and is left alone;
the Keeper is *"responsible only for maintaining the neatness and correctness of github"* and does all the
uploading, on a second PC or, with one PC, in a session that is *"opened and closed when needed"*. PROTOCOL §47,
`docs/TWO-PCS.md`. On or off: `keeper` (features.py).

**Who runs this:** a session on the Keeper PC (`keeper_mode = other_pc`, `keeper_role = keeper`), or the Keeper
session the building session opened on this PC (`keeper_mode = this_pc`). **Never the session that builds**: it hands
over (`parcel.py send`) and asks (`keeper.py ask`), and that is all it does.

**The Keeper writes no code and launches nothing.** It reads, checks, uploads and keeps the shop window right. A fault
it finds in code is reported to the session that builds in one line (and on the fault list when there is one); it is
never repaired here.

## The round

1. `python "${CLAUDE_PLUGIN_ROOT}/tools/parcel.py" receive` (two PCs; the doorman also does this by itself every
   minute, so usually nothing waits). A refused parcel is NOT forced: its receipt already tells the other side why.
2. `python "${CLAUDE_PLUGIN_ROOT}/tools/keeper.py" round` and work down its four lists:
   - **Jobs handed over:** do each, then `keeper.py finish <file>`.
   - **Uploaded since the last round:** for each project, look at what was uploaded (`git log` of those steps) and
     its note ("moved forward: ..."). With a note: refresh the project's front-page row (one sentence, "where it
     stands"), its stage in the machine-readable index, and add ONE dated line to the activity log. Without a note
     nothing moved forward: touch nothing (a tidy-up or a test is not news). Then check its download: is the
     published one older than the program now on GitHub? Say so (or run `/lanes:od` when that extra is on).
   - **Refused hand-overs:** nothing to do here but mention them in the report.
   - **Regular jobs due:** run each (it names the exact command), then `keeper.py done <job>`. A long one (the
     weekly check-up) may be left for the person to start: then it stays due and the other side keeps reminding.
3. Checks on everything uploaded this round: nothing that identifies a person (the privacy guard already refused
   such a push; read its refusal, never skip it), no untouched app file, nothing over the host's size limit, spelling
   of what a visitor reads.
4. `python "${CLAUDE_PLUGIN_ROOT}/tools/keeper.py" round --mark`, then the report: three or four plain lines (what
   was uploaded, what was refreshed, what is wrong, what is due). **Something wrong** is also sent to the session
   that builds as ONE line (the session list names it). Nothing wrong: stay quiet, it is working.

**One PC:** when the round is done and nothing waits, say so and stop; the session that builds closes this window
(`keeper.py close`). **Two PCs:** stay open and idle; this window is the link.

**The Keeper's own commits** (front page, index, activity log) are pushed by the Keeper itself, staged by exact path.
The session that builds never edits those files while the Keeper extra is on: one writer per file.
