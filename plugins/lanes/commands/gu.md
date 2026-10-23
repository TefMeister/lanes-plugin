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
  plugin, Hand Freeze, an outside tool, a PC program, a Python package. **Look first, ask at the END of the run**:
  one question listing them all (AskUserQuestion, multi-select; split into several questions of up to four options
  when there are more), not one each, and install only what is ticked. **Each option says what it could break**, in
  plain words ("could break: the debugger's helper, it pins an older version"; "a compiler: every build changes";
  "needs a restart of Claude Code"), or "no known risk"; anything that even possibly breaks something is warned
  about, so the person can leave it unticked (0.82.1; asked for by the maintainer: "please warn if the updates would
  even possibly break something, so user can decide ... have them all optional at the end of the run as questions
  user can tick or leave unticked"). A test run that changes nothing (pip check, an import test in a scratch copy)
  may come before the question, so the warning is measured rather than guessed.
  **Sort them first** (0.83.0): `python "${CLAUDE_PLUGIN_ROOT}/tools/gu_guard.py" risk winget:<Id> ...
  pip:<name>:<have>:<new> ...` marks each BUILD-CRITICAL (a compiler, Visual Studio's build tools, CMake, Python
  itself, the debugger, Blender, a Python package's major jump, anything in `critical =`) or low risk. A critical
  one's option says "could break: <why>; test-built before it is kept"; a low one needs no test build.
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
   - RE Engine MCP or UEVR-MCP newer (`python "${CLAUDE_PLUGIN_ROOT}/tools/engine-mcp.py" status`, 0.82.0):
     `engine-mcp.py install re` or `install uevr`, the same as the first install. Not while a session is using it.
     A game that already holds the game half gets the new one from its own next session (`engine-mcp.py game ...`).
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
   package another tool pins below a major version stays where that pin allows. Update the same-major ones as one
   batch and each major jump on its own, putting back any that make `pip check` fail. ⚠️ **`pip check` only sees
   pins, not code** (0.73.2): on 2026-10-16 `mcp` 1.29 → 2.3 passed it while removing `FastMCP`, which a debugger's
   MCP server imports. After a major jump, import-test every Python MCP server listed in `~/.claude.json` (and any
   tool the jump touches); one that fails puts the package back.
   **Test build before keeping a build-critical update** (0.83.0; asked for by the maintainer: "is there a way to
   make our work VS Build Tools future proof? and any other program or tool we use", then "filter it to things
   that can actually break things and not simple win-zip"). Low-risk ticks install as before. For the ticked
   critical ones:
   1. `gu_guard.py before <every ticked critical item>`: notes the version each replaces and builds every
      `build_check =` once (the known-good result). A check already failing here cannot judge; say so.
   2. Install ONE of them, then `gu_guard.py after`. `SAFE` = keep it, go to the next. `BROKEN BY THE UPDATE`
      (exit 1) = `gu_guard.py putback <item>`, run `after` again to see it build, and tell the person what broke
      and that it was put back (its line under the check shows what failed). One at a time, so the culprit is
      never in doubt.
   3. No `build_check =` lines yet: offer once to add them, one per thing the person builds (a game add-on's
      build script, a Visual Studio project, `@msvc`, `@blender`, `@pip`), choosing scripts that only build and
      test, never ones that copy into a game folder. Until then a critical update is offered with the plain
      warning only.
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
