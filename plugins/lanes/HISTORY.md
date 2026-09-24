# How this was built

`CHANGELOG.md` says what each version changed. This says **why it went the way it did** — the
turns, the things that were built and then deleted, and the mistakes that shaped the design.

It exists because the commit history might not survive. The repo was private while it was written,
and private repos accumulate real paths, machine names and captured output in their documentation;
publishing a repo publishes all of that, in every past commit, for ever. Starting the public repo
fresh is the clean answer to that, and this file is what makes it a cheap one — the evidence of how
well the thing works lives elsewhere, in the boards and project repos it was tested against, so the
only thing a fresh repo would actually lose is the story below.

Nine days, 0.1.0 to 0.12.3.

---

## 2026-09-09 — the whole shape in one day

Five chunks, in order: the marketplace skeleton, the board, the four read-only lanes, the live lane
with its two guards, and the rulebook. Each one tested on a real estate before the next began.

The one decision worth recording from day one is a small one: **the board's paths came out of the
code immediately.** Everything the tools know about where things live arrives from a config file or
the command line. That is why the plugin was ever portable at all, and it was cheaper to do on day
one than it would have been on day two.

## 2026-09-10 — the day the best idea was killed

The plugin's original headline feature was the **tandem seat**: two sessions paired on the *same*
job, one writing and one reading, handing findings to each other mid-session. Version 0.3.0 built a
hook to enforce that the reader could not write the status file.

It was measured, and the measurement ended it: **1 clean run in 50 attempts**, and the two most
recent faults in the log had both come from it. Retired the same day. `/lm` now starts **one
background reader** inside a single session, which does the same job with none of the racing.

⚠️ **This is the part to keep in mind when reading anything else here.** The feature was
interesting, it worked in principle, it had a hook written for it — and the count said no. Nothing
else in this project has ever been as hard to give up, and the release bar exists so that the next
one is not.

The same day answered a question nobody had documented anywhere, by capturing it rather than
assuming — *do hooks fire for a background agent's tool calls?* They do, and the payload carries an
`agent_id` and `agent_type` the parent session's own calls do not. The reader guard rests on exactly
that fact. The first attempt got it wrong in an instructive way: parent and subagent share one
session id, so identity had to come from somewhere else.

## 2026-09-13 to 09-15 — saying what a session needs, and checking it

`MODEL:` beside the gate line (0.5.0), so whoever runs the session knows which model the next step
deserves before spending one on it. Then the same treatment for the public front page (0.6.0): the
rule was "every session adds a line, whether or not anything advanced", and **a rule nobody can
check is a wish**, so it got a tool.

Faults 9 and 10 closed in 0.6.2, and fault 10 is the one worth naming: a hand-typed cutoff date
counted two sessions from *earlier the same day* as reader runs, because the reader had actually
shipped at 15:35 that afternoon. A whole day of granularity hid a fifteen-hour gap. The count now
dates itself from the recorded moment, to the second.

## 2026-09-16 to 09-17 — the tools around the edges

`/lm` learned to quit an app through its own menu rather than killing the process. Then, in one day:
code-shape rules with a scanner, a pass-through proxy-DLL generator that survives being called
before `DllMain`, a guided first-run setup for optional tools, an update check, and a banner whose
version and notes are rebuilt on every release.

The banner is a small lesson in itself. It is generated, not drawn, because the two things on it
that go stale — the version number and *what's new* — go stale on **every** release, and a picture
freezes both.

## 2026-09-18 — four days' worth of faults in one day, all of the same kind

Three faults, found by ordinary use rather than by testing, and all three shaped identically:
**the failure was indistinguishable from success.**

- **Fault 11.** The version lives in two files and only one was ever bumped. The installer reads the
  other. So `claude plugin update` compared the installed version against a stale offer, correctly
  found nothing newer, and said *"already at the latest version"* — for **eighteen consecutive
  releases**. Six weeks of work unreachable, and nothing anywhere said so.
- **Fault 12.** The update check read its version from whichever copy of itself was running. Run
  from a repo checkout — which is what the command actually did — it reported the repo's version as
  installed and concluded there was no marketplace at all. A confident "you are up to date" about a
  machine it had never looked at.
- **Fault 13.** The check reads `origin/main`; the installer reads the marketplace clone's *working
  tree*. Push a release from a different clone and those disagree, so the installer names the old
  version and calls it the latest, one command after the check promised a new one.

**The pattern is the finding.** A check that reports on itself will always pass. Each fix moved the
thing being tested to a different object from the thing testing it.

The same day, the first real audit against the "no personal data" bar — a bar that had been in the
checklist from the start, worded *"grep the whole plugin folder"*. **Nobody had, in six weeks.** It
found a captured debug file carrying a username, a home path, a working directory, two session ids
and a slice of a personal settings file. That is now `scrub-scan`, a command, because the difference
between a checklist line and a command is whether it happens.

---

## 2026-09-24 — public, early, and nobody's name in it

The release bar below was never met: 38 of 50 clean runs, and the "no fault in the last five
sessions" row still counting. The author published anyway, as an **early version, still being
built**, on the reasoning that the bar was written for claiming the plugin is *proven*, and an
honest "early" label claims less. The bar stays, and now measures the road to 1.0.0.

The repo was started fresh for it, as this file was written to allow: the private repo's history
held a Windows username, home paths and a captured settings excerpt that scrubbing the files could
never remove. `TefMeister/claude-plugins` stays private and frozen; this is `TefMeister/lanes-plugin`.

And one design change came with it, the author's idea: **stop guarding names word by word, and stop
writing them.** The plugin had shipped a list of words that must never be published, which meant
publishing the plugin published the list. Now every session is told, by a hook, that the person at
the machine is "User" unless they chose a display name, and nothing else about them is written. A
rule that makes the leak impossible beats a check that catches it afterwards.

## What this project believes, in five lines

1. **A count beats an opinion, and a count that could have said no beats one that could not.**
2. **A check that reports on itself will always pass.**
3. **A rule nobody can check is a wish.** Write the tool, or drop the rule.
4. **The failure that looks like success is the expensive one.** Prefer a noisy failure every time.
5. **A fallback that gives something up must be able to get it back** through a path it controls.

## Where the evidence actually lives

Not here. The run counts come from the commit history of the **boards and project repos** the plugin
was used on — `tools/run-log.sh` harvests them by reading commit trailers, and refuses to count a
run that cannot be re-derived from git. That is why this file can exist without the repo's own
history, and why re-creating this repo costs the story but not the proof.
