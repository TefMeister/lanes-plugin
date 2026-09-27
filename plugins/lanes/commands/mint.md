---
description: (Mint) Keeps a project's untouched app in mint condition and moves all modding into a private copy on this PC. Walks the person through a truly clean reinstall (or does the steps with them), fingerprints the clean install, and offers to make the working copy - which stays on this PC only, because sharing the game's files is illegal. Never writes into the clean install. Safe beside every other lane.
---

`/lanes:mint <project>` — **keep the real app clean, and mod a copy of it.**

**Why this exists.** A bug once followed a game through three "clean" reinstalls. Every file that was
not the game's own was moved out, the store verified the rest, and the bug stayed. Only deleting the
whole game folder and installing it again removed it: something left over from months of modding had
survived every partial clean, and nobody could say which file. The person's fix, in their words:
*"keep the vanilla game in mint condition"*, and do the modding in a separate copy. Then the clean
install never changes, a fingerprint proves in seconds that it is still clean, and a test copy can be
thrown away and remade whenever a result stops making sense.

This is an **option**. Offer it; never switch it on without a yes. The tool is
`python "${CLAUDE_PLUGIN_ROOT}/tools/mint.py"`, and it never writes into the clean install.

## Steps, one at a time, in plain words

1. **Explain it in two or three lines** (the paragraph above, shortened) and ask whether they want it
   for this project. No means stop; say they can run `/lanes:mint` any time.

2. **Is the install already truly clean?** Only a complete reinstall counts: uninstalled, the leftover
   folder deleted, installed again. "Verified in the store" or "I moved the mod files out" does **not**
   count, and say why in one line: verifying leaves extra files where they are.
   If it is not, **offer two ways and let them choose:**
   - **Steps for them to do:** print `mint.py guide <project>` as short numbered steps.
   - **Help doing it:** first move everything of theirs out of the game folder into a dated folder
     outside it (nothing is deleted), and back up saves if they live in the game folder. Then open the
     store's own uninstall (for Steam, `start steam://uninstall/<appid>`); **they** confirm it in the
     store window. Afterwards look at the old folder, and if anything is left, **ask** before deleting
     it. Then open the install (`steam://install/<appid>`). They start the game once to the main menu
     and close it.
   Never uninstall, delete or reinstall anything without their yes for that step.

3. **Record where the clean install is**, in `lanes.conf` on this PC:
   `mint_vanilla.<project> = <game folder>`, and optionally `mint_normal.<project> = <pattern>` for
   each file the game rewrites itself (its settings file, its logs), one line each.
   Then run `mint.py fingerprint <project>`, and say how many files it recorded.

4. **Offer the private copy.** Before making it, show the notice in full (the dry run prints it):
   the copy is for modding on this PC only, and **sharing those files is illegal**. Ask where it should
   go (a plain local folder with room for the whole game; suggest a different drive if they have one).
   Then `mint.py copy <project> --to "<folder>" --yes` (add `--steam-appid <id>` for a Steam game, so the
   copy starts itself instead of Steam starting the real one). The tool refuses a folder inside a git
   repo, a cloud-synced folder, the clean install itself, or a folder that is not empty.
   Then add `mint_copy.<project> = <folder>` to `lanes.conf`: from then on `builds.py` works in the copy,
   and refuses to restore into the clean install.

5. **Prove the copy before any mod goes in.** Ask them to start the game from the copy (its own exe,
   not the store's button, with the store running) and check the thing that matters to them. Read the
   copy's log afterwards to confirm the copy is what ran.

6. **Record it** on the project's board: where the clean install and the copy are, the fingerprint's
   date, and that nothing of ours goes into the clean install.

## Standing rules once it is on

- **Nothing of ours is ever written into the clean install.** Every install, test file, setting and
  restore goes into the copy.
- **At the start of `/lm`, `/ms` and `/pd` on the project**, run `mint.py check <project>`. Not mint any
  more means something wrote into it: say so plainly and find out what before trusting any test.
- **When results stop making sense**, compare the copy with `mint.py check <project> --copy`, and offer
  to throw the copy away and make a fresh one from the clean install.
- **The copy never leaves this PC.** Never commit it, upload it, sync it or pack it into a release.
  Only files we made go to GitHub or into a mod package.
