---
description: (Manual Session) Hands-on work on ONE project with the person at the keyboard (and in the headset, if there is one). The assistant prints a short numbered set of steps, the person does them and says "done" (or describes what they see, or pastes a screenshot), the assistant reads the result, writes code in between, and prints the next set. The assistant NEVER launches, drives, captures or closes the app in this lane. Same claim, pre-flight and write-up as /lm; only the hands differ.
---

`/ms` — **Manual Session.** The person does the hands-on work; you give the steps and write the code.
It is the slowest lane, and that is the point: the person wants to see it happen, step by step, with
their own eyes. Do not try to speed it up by taking over.

Argument: `$ARGUMENTS` — a project name, however they say it. Resolve it the way `/lm` §1 does (fuzzy
match; list the candidates and ask if it is unclear). Empty means ask which project.

---

## 1. The one hard rule — your hands stay off the app

In this lane you do **not**:

- launch the app, or ask a launcher to;
- send any key, click or controller input to it;
- take screenshots or captures of it — **they** show you what they see;
- close it, kill it, or restart it after a build swap — you **ask them** to;
- start a background helper, watcher or monitor on it;
- run any `[FLAT]`, `[VR CLAUDE]` or `[VR USER]` test yourself. You describe it; they run it.

You **do**, freely, between their turns:

- read the app's own log files, and any screenshot or capture **they** made or named;
- write and build code, edit data files, and put files in place **while the app is closed** (ask
  "is it closed?" if the log does not tell you);
- all static work: reading, decompiling, measuring, planning.

If a file cannot be swapped while the app runs, say so and let them close it. Never work around them.

---

## 2. Pre-flight — the same as `/lm` §4, with the lane name changed

1. **Pull** the board and this project's repo.
2. **Take the claim as this lane:** `bash "${CLAUDE_PLUGIN_ROOT}/tools/lane-claim.sh" take /ms <project>`.
   Refused means another session holds the project: say so and stop. Only the person may `--force` it.
3. **Drain this project's `inbox/`** by explicit filename list, never by pattern.
4. **Read the status file** (`OPEN` block first) and the project's own notes, including dead ends.
5. **Show the project's fresh ideas**, if an ideas repo is set up (`/lanes:ideas`). The person is right
   there, so ask for the numbers and record them.
6. **State the gate in one line,** and say in one line what you will try first and why it is the
   cheapest useful thing on the board. They may redirect; their choice wins.
7. **Say which model this session needs** before the first steps. In this lane the person reads every
   turn, so a pause costs seconds: if the running model does not fit the work, in either direction, say
   so and let them choose.

---

## 3. The shape of every turn

Each reply while the session runs is one block, and nothing else:

```
NEXT
1. <one action, in plain words>  -> what you should see
2. ...
(at most 5 steps; more than that is two turns)

TELL ME: <the one or two things you need back: a number, yes/no, a screenshot, how it looked>
```

- **One action per step.** "Press F5, then look at the top-left corner" is two steps.
- **Say what to look for in their words,** not the log's. "The gun should follow your right hand",
  not "check the bridge reports ctl=1".
- **Read numbers from the log yourself.** Ask their eyes only for what a log cannot say: how it feels,
  whether it looks right.
- **Screenshots:** they paste one or give a file path. Read it. If a picture decides the step, ask for it.
- **After "done":** read the log, say in one or two plain lines what it means, do the code or data
  work that follows without narrating it, then print the next `NEXT` block.
- **When a build must be swapped:** step 1 is "close the app", the swap happens in your turn, and the
  next block starts with "start it again". Never assume it was closed.

Take as long as the work needs between their turns. During their turn, do nothing to the app.

---

## 4. Before the session ends — the same write-up as `/lm` §6

- Write up what was tried and what they saw (quote them), with a confidence tag on every claim. `n`
  counts **their** runs.
- Update the status file and re-date the `OPEN` block.
- **Release the claim last:** `bash "${CLAUDE_PLUGIN_ROOT}/tools/lane-claim.sh" release /ms <project>`.
- Commit only this lane's paths, never `git add -A`, with the trailer `Lane: /ms <project>`.
  `git pull --rebase` before pushing.
- **Report briefly.** They were there for all of it, so the summary is a reminder, not an account:
  what got proven, what got disproved, what is next, and what the next step requires.
