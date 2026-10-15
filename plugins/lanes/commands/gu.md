---
description: (GitHub update) The weekly tool check. Finds what we rely on that has a newer version - our own apps and tools, two copies of the same tool that drifted apart, outside tools with a new release, lessons the tools should learn, and repo descriptions and front pages that fell behind the work - and brings each up to date, asking first before installing anything.
---

`/gu` — **keep everything we rely on fresh.** `/gs` only checks; `/gu` checks the things that may need updating
and updates them: a newer version on GitHub comes down to this PC, a newer version on this PC goes up to GitHub,
two copies of a tool are brought back in step, and what sessions learned goes into the tools.
Asked for by the maintainer, 2026-10-14. PROTOCOL §23.

**The habit: once a week.** A session-start line says when it has been 7 days or more on this PC. Never run it
unasked; mention it in one line and carry on.

## 0. Rules

- **Never launch, drive or close an app**, and never touch a project's own files (boards, notes, builds). This lane
  looks after tools, and since 0.69.0 also the texts the public reads (step 6): repo descriptions and front pages.
- **Ask before installing or updating anything on this PC** that is not a git pull of our own clone: the lanes
  plugin, Hand Freeze, an outside tool. One question listing them all (AskUserQuestion, multi-select), not one each.
  **Unless the person said not to ask:** `gu_ask = no` in lanes.conf (the scan's first lines say which). Then update
  everything that needs it without asking, and report what was done (0.68.0; asked for by the maintainer: "update
  everything that needs an update, no need to ask me, it's more for users who are not me").
- **Pushing our own work needs no question** (the same as every lane), but stage only the files you mean to.
- If a repo you need is claimed by a live session in the same clone root, leave it and say so.
- Short, plain report. Detail goes in the commits.

## 1. Look

```bash
python "${CLAUDE_PLUGIN_ROOT}/tools/gu.py" scan
```

Five sections. If one is empty because nothing is set up for it in `lanes.conf` (`twin =`, `watch =`, `ours =`,
`routes =`, `texts =` with `texts_owner =`), say so in one line and offer to set it up.

## 2. Act, section by section

1. **Our apps and tools.**
   - Lanes plugin newer: list each version in between with one plain line (from `/lanes:update`'s `changes`), then
     follow `/lanes:update` on a yes.
   - Hand Freeze newer: `python "${CLAUDE_PLUGIN_ROOT}/tools/hand-freeze.py" install` on a yes.
   - One of our clones **behind**: `git pull --rebase`. **Ahead or unsaved**: read what it is first. If it is
     finished work, commit what belongs together and push. If it may belong to a live session, leave it and say so.
2. **Two copies of the same thing.** Look at the files that differ (`git log` on both sides beats file dates). Copy
   the newer one over the older; keep the master copy (the left side of `twin =`) the one edits are made in. A copy
   inside the lanes plugin changes the plugin: bump the version and release with `tools/release.sh`.
3. **Outside tools.** For each release not noted yet: one plain line on what it brings (read its release notes). Ask
   which to install. After installing one, or deciding not to, note it:
   `python "${CLAUDE_PLUGIN_ROOT}/tools/gu.py" seen "<name>" <tag>`, so it is not offered again.
4. **Lessons for the tools.** Each "Tool ideas" line from an app's `KNOWN.md` since the last run: do it now if it is
   small (and test it), otherwise turn it into a board row or an issue on the tool's repo. Anything learned that
   other people's tools could use goes where those tools keep knowledge (the cross-engine library's `inbox/`, the
   toolkit's notes).
5. **The PC's own development tools** (0.68.0): `winget upgrade` lists programs with a newer version; update the
   ones used for the work (compilers and build tools, cmake, git hosting tools, runtimes, editors, packers, the
   debugger). Leave alone, and say why: anything running right now (the terminal this runs in, git while shells use
   it, an editor or tool another session has open), a compiler a live session is building with (a new major version
   changes every build), game stores and launchers (they update themselves), and the person's private apps.
   Then Python packages the tools use (`python -m pip list --outdated`): update them, and run `pip check` after; a
   package another tool pins below a major version stays where that pin allows.
6. **Texts on GitHub** (0.69.0; asked for by the maintainer after a finished mod's description still named v1.0.2
   and its front page sent people to an older download while v1.1.5 was out: *"go over the whole github and bring
   all the texts and descriptions up to date"*). Section 5 of the scan lists what the checks caught across every
   public repo of the account: a description or front page naming an older version than the newest release
   (pre-releases count when there is no full release), "nothing released" or "private" beside a public release, and
   a status part unchanged for weeks while work landed. **Then the part no check can do:** read every public repo's
   one-line description once against where the project stands, and the front-page rows that summarise them (a
   profile page or index, if the account has one). Where they disagree:
   - **Learn the true state first**, from the project's own board, notes and newest release, never from memory. A
     status line is a claim: write only what those say, in plain words, dated where it helps.
   - **Fix the text where it lives:** `gh repo edit <owner>/<repo> --description "..."` for a description; for a
     front page, edit the file in a clone, pull first, stage only that file, commit, push. A row in a grouped table
     moves to the group its icon now belongs to.
   - **Never change what a project IS** (visibility, a release, a decision); a text that disagrees with a decision
     is reported, not "fixed" by guessing. When the person knows something no file says (a mod site's version,
     say), take their word and write it in.
   - Rerun the scan after: section 5 should come back empty.

## 3. Finish

```bash
python "${CLAUDE_PLUGIN_ROOT}/tools/gu.py" done
```

Then the usual write-up: close-out box (`handover.py close`), the gate/model box, and a short report: what was
updated (texts included: which repos, in a few words each), what was left and why, and what needs the person. A front-page or activity line only when something was
released or changed for people (a tool update, a plugin release).
