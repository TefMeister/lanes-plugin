---
description: (Out of Date) Is everything we published on GitHub as new as the work behind it? Finds downloads older than their program, tools with no download, descriptions and front pages behind the work, catalog and skills pages missing something, and tools Lanes does not offer yet - then brings each up to date. Runs before /gu.
---

`/od` — **Out of Date: GitHub always shows the newest work.** Asked for by the maintainer, 2026-10-27, after one
afternoon found Hand Freeze's download still at v3.2 while v4 had been worn in a game, three apps with no download at
all and a skills page 67 days old: *"a slash command now actually, that scans if something is out of date across our
github ... it must run before /gu ... and then add this function to the /fullscan as well so our github will always be
shiny and has the latest stuff"*. The name was chosen the same day. PROTOCOL §41.

**When:** inside `/fullscan` every week, just before the tool check; on its own whenever something was built, renamed
or released. Never run it unasked. On or off: `out_of_date` (features.py).

## 0. Rules

- **Never launch, drive or close an app.** Building and testing one of our tools to publish it is fine; a test that
  needs a game or a headset is not done here: say so and leave that download for a session that can.
- **Clone root: the `/gu` one** (the folder `/gu` uses on this PC), never another lane's. Pull before changing a
  repo, stage only what you changed, push.
- **Publishing a download of our own tool needs no question** (the maintainer, 2026-10-27: *"please publish
  downloads for all the tools we use ourselves"*). It must pass its own tests first, carry a `SHA256SUMS.txt` beside
  the zip, and say plainly what was and was not tested. **Never** publish a mod for a game this way (mods are private
  zips for named people), never make a repo public, never publish something private.
- Short, plain report. Detail goes in the commits and release notes.

## 1. Look

```bash
python "${CLAUDE_PLUGIN_ROOT}/tools/od.py" scan
```

Four sections. Each clone is fetched first and read at GitHub's newest state, so an unpulled copy never makes a page
look older than it is.

## 2. Act, section by section

1. **Downloads behind the work.** A tool of ours whose program changed after its newest release (notes, docs, tests
   and ideas do not count). Read what changed (`git log <tag>..`); when it is real and tested (its own tests pass, and
   its notes say it was used), build it, run its tests, pack the zip the way its last release was packed (same file
   names, `install.ps1` inside, `SHA256SUMS.txt` beside), and publish a release whose notes say in plain words what is
   new and how far it was tested. Bring every page that names the version along (its README, the toolkit's catalog,
   the profile row). Not ready yet (half-done work on main): leave it and say why in the report.
2. **Tools with no download.** An app or add-on with none: as above, its first release. A library: add a "Download"
   section near the top of its README with the one-zip link (`https://github.com/<owner>/<repo>/archive/refs/heads/main.zip`,
   always the newest copy), and a line saying Lanes can get it too. A repo that is not meant to be downloaded goes in
   `od_skip =`.
3. **Texts on GitHub** (0.69.0, in /gu until 0.94.0; asked for by the maintainer after a finished mod's description still named v1.0.2
   and its front page sent people to an older download while v1.1.5 was out: *"go over the whole github and bring
   all the texts and descriptions up to date"*). Section 3 of the scan lists what the checks caught across every
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
   - **Catalog pages** (0.91.0, `catalog = <repo>/<file>` in lanes.conf, such as a toolkit's list of every tool): the
     scan names each tool of ours the page never mentions (a file in that repo's `tools/`, a public `ours =` repo, an
     app any PC has installed) and each tool it mentions whose repo moved on since the page last changed. Add the
     missing ones and bring the moved ones up to date, from each tool's own README and tested notes, in the page's
     own style; a private repo is never named on a public page. A new app of ours also gets its `ours =` line here.
     The maintainer (2026-10-27), after the toolkit page missed five of our apps: *"this should have been covered by
     the /fullscan and /gu, can you make a fix for it so next time something like this is not forgotten"*.
   - Rerun the scan after: section 3 should come back empty.
4. **Lanes and the skills page keep up** (0.93.0, in /gu until 0.94.0; scan section 4). Two gaps the scan names:
   - **A public tool of ours that Lanes does not offer** (an `ours =` repo that is neither shipped, installed nor in
     `tools/ours.py`): add it to `ours.py`'s list (label, repo, kind, a plain description), run the features doc,
     and release; a repo that is not a tool for others goes in `lanes_skip =`. Private repos are never named.
   - **The skills page** (`skills = <repo>/<file>`, such as the toolkit's SKILLS.md): each MCP server or Claude Code
     plugin in use on this PC that the page never names, and a page left unchanged for a long time. Add a connector
     only once it has done a real job (install, verify, what it is for, its maker and link, in the page's style);
     one not yet proven goes in the page's "offered but not proven" line; a private one goes in `skills_skip =`.
     Then read the page once against what is in use and fix what has moved on.
   The maintainer (2026-10-27), when the skills page and Lanes' optional extras had fallen behind: *"all this is what
   /fullscan and /gu are meant to do"*. Rerun the scan after: section 4 should say "nothing missing".


## 3. Finish

Rerun the scan: every section should come back empty or explained. Then the usual write-up: close-out box
(`handover.py close`), the gate/model box, and a short report: which downloads were published (name and version),
which pages changed, what was left and why. A front-page activity line only when something was released.
