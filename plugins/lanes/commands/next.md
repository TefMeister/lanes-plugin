---
description: "(Next) Hands the next job on to a fresh window: writes a long, exact prompt, opens the window, closes this one when safe."
---

`/next` — **the session hand-on.** Asked for by the maintainer, 2026-11-16: *"start a new session, type in a lengthy
and accurate prompt for the re3 job and close the re2 one, when it is safe to do so"*. A long session rereads its whole
history for every reply, so a new job in a fresh window costs less and starts clean. `tools/handon.py` says how it
works. On or off: `hand_on` (features.py); its partner `fresh_nudge` says when a fresh window is worth it.

**Only on the person's yes to a next job**, when the current one has ended (they typed `/lanes:next <job>`, or said yes
to doing the next job). Never in the middle of a job, never to get away from a hard one.

1. **Finish this job first:** its end steps as the lane says (notes, board row, save and hand over: `parcel.py send`
   on the Developer PC, the close-out box elsewhere). The new window starts from what is saved, not from this chat.
2. `python "${CLAUDE_PLUGIN_ROOT}/tools/handon.py" new "<the next job in a few words>"` prints the file to write and
   its outline.
3. **Write the prompt there** (the Write tool), every section of the outline in full: the job in the person's words
   (quoted), what is decided, what to read first by name, the builds and what is installed where (worn or not), what
   NOT to redo, the gate, the model and the first step. It is the new window's only memory of this one: long and exact
   beats short. No `<...>` line of the outline may be left; `start` refuses a prompt that is short or unfilled.
4. `python "${CLAUDE_PLUGIN_ROOT}/tools/handon.py" start "<that file>" --name "<a short window name>"` opens the new
   window with a first message pointing at the prompt, and waits (up to three minutes) until it has started on it.
5. **Say it in two plain lines:** the new window's name and what it is doing; and that this window closes by itself
   when this reply ends, if it is safe. End the reply there, with no question (a question keeps the window open).

When the reply ends, the Stop hook closes this window with the normal `/exit` (its end steps run), but only when all
of these hold: everything this PC saved is on GitHub (or the light line names only what waits), no game is running, no
background task of this session is still running, and the reply does not end with a question. If one fails, the
window stays open and one line says which. If `start` reports that the new window did not start, this window stays
open: say so and leave the prompt file where it is, so it can be started again.
