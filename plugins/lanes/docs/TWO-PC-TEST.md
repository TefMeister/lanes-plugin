# The two-PC test

Lanes is used on two PCs that share their work only through GitHub. Before a bulk release (Tefa's rule, 2026-10-28:
"test everything first, then add a bulk of new features in one go"), both PCs run the test build side by side and
this list is worked through, both ways. One session per PC, both with Remote Control on, so the dev PC's session can
message the home PC's session (they find each other with ListAgents); Tailscale tells whether the other PC is on.

Each row is done on PC A, then looked for on PC B, then the same again the other way round. Record each result as
pass or fail with one line, in `docs/RELEASE-CHECKLIST.md` (usage log).

## Getting the test build onto both PCs (nothing published)

1. The dev PC pushes the work in progress to the private `staging` repo, branch `lanes-next`.
2. Each PC keeps a clone of that branch and points Claude Code's `lanes-plugin` marketplace at the clone
   (`claude plugin marketplace remove lanes-plugin`, `claude plugin marketplace add <clone>`,
   `claude plugin install lanes@lanes-plugin`). Restart Claude Code.
3. Both PCs report the same version and the same commit (`claude plugin list`, `git -C <clone> log -1`).
4. After the bulk release, point the marketplace back at GitHub (`TefMeister/lanes-plugin`).

## Sync

| # | On PC A | Expected on PC B |
| --- | --- | --- |
| S1 | commit + push a note to the board | the next session start pulls it; the handover line names A's last save |
| S2 | leave a file uncommitted, end the session | B's session start says A is NOT SAVED and names the repo |
| S3 | raise an owed item for B | B is greeted with it; A is not |
| S4 | B marks it done | A's list no longer shows it after a fetch |
| S5 | record the games list (`games.py record --push`) | B sees A's file, never compares it with its own games |
| S6 | install one of our apps (installed.py) | B's start-up lists it under "our apps on your other PCs" |

## Break it

| # | What is done | Expected |
| --- | --- | --- |
| B1 | both PCs edit different files of one repo, both push | the second push rebases cleanly and lands |
| B2 | both PCs edit the SAME line, both push | the second is refused, the conflict is named, nothing is lost |
| B3 | A takes a claim (/pd on a project); B starts /lm on the same project | B is blocked with a reason |
| B4 | A's clone is left unpulled for a day | B's start-up check still reads GitHub, not A's stale copy |
| B5 | A tries to commit B's login, home path or e-mail | refused on A too (private words) |
| B6 | a commit made with --no-verify carries a home path | refused at push |
| B7 | a game folder is renamed or moved on A | A's next session start says GAME MOVED/GONE; B says nothing |
| B8 | Steam updates a game on A | A's next session start says GAME UPDATED |
| B9 | A is switched off mid-session (window closed) | B's handover line says A did not report its session end |
| B10 | the network drops during a push | the push fails loudly; the close-out box says NOT SAVED |

## Pass

Every row passes both ways, both test suites pass from the installed test build on both PCs, and the close-out box
is SAVED on both. Only then is the bulk released.

## Runs

### Run 1 - 2026-10-28, both PCs over Tailscale + Remote Control, versions DIFFERENT on purpose

Dev PC (PC2) on 0.95.0, home PC (PC1) on 0.94.1, both from GitHub; the test build was not installed (Tefa: the
mismatch is a test of its own). One quiet session per PC, messages over Remote Control, scratch files in the board
repo's `two-pc-test/`. `[verified-live 2026-10-28, n=1]`

| # | Dev -> home | Home -> dev | Note |
| --- | --- | --- | --- |
| S1 | pass | pass | check words seen both ways; handover line named the other PC's save within a minute |
| S2 | pass | pass | NOT SAVED named the repo on the other PC, both ways |
| S3 | pass | pass | **fault fixed:** `owed.sh done <name>` refused the name without `.md` (the form a session naturally types); now accepts both |
| S4 | pass | pass | cleared items gone on both after a pull |
| S5 | pass | - | 0.94.1 (no games.py) read a board holding 0.95.0's games record with no error; home direction needs 0.95.0 |
| S6 | pass | pass, partial | Hand Poser shows "release unknown" for PC2 (no version recorded on the dev PC) |
| B1 | pass | - | different files, second push refused, pull --rebase merged clean |
| B2 | pass | - | same line: push refused, rebase stopped naming the file with both values in the markers; resolved by hand, nothing lost |

Seen on the home PC's session start, not yet explained: once, "this PC's copy of the board could not fetch: the
clone is probably damaged", while every pull and push after it worked (one-off? `[hypothesis]`); and the plugin
version check said the dev PC last recorded 0.94.2 while it ran 0.95.0 (its record lags).

Still to run after Run 1: B3 (with `/lm` on one PC and `/pd` on the other, the planned round 2), B4 to B10, S5 home
direction, and the whole list again on the test build installed on both PCs.

### Run 2 - 2026-11-01, both PCs on 0.95.0 from GitHub (commit 06373f2), messages over Remote Control

Same set-up as Run 1, versions now equal; the test build was still not installed. Tefa: "ok go ahead with the test",
then "do all please" for the riskier rows, each done the safe way described in its note. `[verified-live 2026-11-01, n=1]`

| # | Dev -> home | Home -> dev | Note |
| --- | --- | --- | --- |
| S5 | (Run 1) | pass | `games.py overview` on the dev PC shows a PC1 column; `games.py check` silent, no GONE/MOVED from the other PC's record |
| B3 | pass | pass | `lane-claim.sh take /lm` refused with the other PC's FRESH `/pd` line, exit 1, file untouched; the prompt hook blocked a typed `/lm <game>` (exit 2) and let `/lm force <game>` through; on home a second session on the same PC was blocked too |
| B4 | - | pass | home: a board clone reset 3 commits back still reported the claim FRESH (reads origin/main, with and without `--no-fetch`) |
| B5 | pass | pass | both private words refused as a path and bare; display-name path accepted; never-publish words refused as paths, bare ones accepted in a repo with no remote (by design: public repos only) |
| B6 | pass (stand-in) | - | `--no-verify` commit with a home path refused at push, nothing landed. ⚠️ A github.com URL that does not exist proves nothing (git fails at ref discovery before pre-push runs), and a repo we cannot write to is a public surface, so the remote was a LOCAL bare repo whose path contains `github.com` |
| B7 | - | pass (half) | home: `game_dir` pointed at a missing folder (copy of lanes.conf via `LANES_CONFIG`) gave GAME GONE; the other PC said nothing (dev S5 check) |
| B8 | pass (simulated) | - | copy of the games record with an older build number (`LANES_CONFIG`): GAME UPDATED with both build numbers. Like B7, `check` exits 0 when it reports |
| B10 | pass (simulated) | - | one push with the push URL at `github.invalid`: failed loudly (exit 128), close-out box NOT SAVED naming the repo; URL put back, push landed, box SAVED |
| B9 | - | pass, weak | home wrote a SAVED start at 11:48, then Tefa closed its window; the session went offline in ListAgents and the dev PC's handover line said "PC1 has not reported a session end". ⚠️ The dev PC printed the same line BEFORE the close, so it cannot tell a session still running from one closed without its end steps; it only says "no end since". The home half PASSES: the next home start said "the last session on this PC began its end report but was closed before it finished, so the other PC was not told how it ended" (closing the window most likely started the end hook and killed it `[hypothesis]`) |

**Faults found, all to be fixed on lanes-next (no release, Tefa's bulk rule):**

1. **FIXED on lanes-next.** `handover.py write_heartbeat`: a start report was held back for an hour by the file's age
   even when SAVED / NOT SAVED changed, so the other PC saw a stale red light for up to an hour (home wrote NOT SAVED at
   10:43; a SAVED start at 11:23 wrote nothing). Now a change of light is always written, and the hour is counted from
   the report's last commit, not the file's modified time. Two checks added to `handover-fixture.sh`; both fail on the
   old code and pass on the new.
2. **FOUND, not fixed (needs a design choice).** On the dev PC the start checks are CANCELLED, not missing: this
   session's own record shows 9 of 15 SessionStart hooks `hook_cancelled`, each at exactly its own time limit (board,
   owed, gate board 20 s; privacy 30 s; snapshot 60 s; handover 90 s, all counted from 08:02:20). About 25 start hooks
   (the plugin's plus the board's own in settings.json) run at once, several reading all 314 repos, and on this
   low-powered PC they starve each other. It is the usual case here, not a one-off: of the dev PC's last 25 session records, all 22 full starts
   lost 3 to 13 checks each, and the handover light was among them 6 times (both starts on
   2026-11-01). `[verified-numerically 2026-11-01, n=22 starts]` The home PC (67 repos) is not affected. The
   choice: move the save-report write into a background hook so a cancelled light still reports, and/or merge the
   board-reading start hooks so 314 repos are walked once, not five times.
3. **FIXED on lanes-next.** Text through the hook pipe was mojibake on Windows, on BOTH PCs: the ⚠️ arrived as
   `âš ...` because `emit_context.py` read stdin with the ANSI code page. It now reads the bytes as
   UTF-8 (falling back to the code page only for input that is not UTF-8); checked with a UTF-8 warning sign, a cp1252
   line and empty input.
4. **FIXED (board repo).** The board's own `tools/lane-claim.sh` was an old copy writing the Windows host name; it now
   writes `machine_name` (PC1 / PC2), as the plugin's copy has since 0.24.0. Its fixture: 36/36 (the old script failed
   25 there, because the privacy guard refuses the host name in a commit).
5. **FIXED (board repo).** `deployed.sh record` doubled every row when one file was named `/d/...` and `D:/...`;
   fixture 7/7.
6. Seen in B9: a PC's handover line cannot tell a session still running from one closed without its end steps; it
   only says "no end since".

Still to run: the whole list on the test build installed on both PCs, after the fixes above.

Note on commit `7bedfc7` (the fixes above): its message says the session that wrote the work "closed without its end
steps". It had not: it was still running, waiting for the smoke test (all passed). A second session on the same PC read
the handover line, took the work for abandoned and committed it. The content is the session's own, unchanged. It is a
live example of fault 6: the handover line cannot tell a running session from a closed one.

### Update hold for test runs (2026-11-01, dev PC)

Before a test round, put a hold on both PCs: `python tools/hold.py on "two-PC test round N"`. While it is on, no
session on that PC can update, reinstall or uninstall Lanes (the weekly tool check and `/fullscan` keep running and
simply say the update is waiting). Lift it with `hold.py off` when the round is over; it lifts by itself after 12
hours otherwise. PROTOCOL §43. Built because the maintainer asked for a lock instead of remembering `skip:gu`.

### /pd lock test (2026-11-01 16:22, dev PC): FAIL, cause found and fixed

A second window typed `/pd` 17 s after its start-up ended, while this PC's lock was 5.4 h old (fresh): it ran a
whole /pd on Window View. The guard itself refuses; the hook launcher turned its refusal into "all fine" on
Windows, for every Lanes guard. Fixed on lanes-next (`hooks/run-hook.cmd`); FAULTS.md has the measurements.
Re-test once the test build is installed: the same two-window `/pd` should be refused.

**Dev PC, 2026-11-01 17:25:** the fixed `run-hook.cmd` was copied into the installed 0.95.0 (old one kept in
`D:\claude video game stuff\backups\lanes-run-hook-2026-11-01\`). Through the installed launcher a refusal now
returns 2 and a pass 0; the old launcher returned 0 for the refusal [measured 2026-11-01, n=1]. Home PC queued
(owed). Note for testers: test the /pd guard with `LANES_PD_LOCK` pointed at a temporary file; a test run against
the real lock takes it once the real one is stale (it happened here, and was removed).

**/pd lock re-test, dev PC, 2026-11-01 ~17:30: PASS.** With the fixed launcher installed and this session holding
the lock, a second window's `/pd` was refused straight away (Tefa saw the refusal) [verified-live 2026-11-01, n=1].
Home PC: re-test after its owed launcher copy.

### Run 3 - 2026-11-01 evening, dev PC on the test build (Tefa: "can you do all of them one after another?")

| # | Test | Result |
| --- | --- | --- |
| 1 | Test build installed on the dev PC: marketplace pointed at the lanes-next worktree, plugin reinstalled (old copy kept in `D:\claude video game stuff\backups\lanes-0.95.0-*`) | **pass (dev half)**: `claude plugin list` reads it from the worktree; hooks-test and smoke-test pass from the installed copy. Home half queued (owed HOME) |
| 2 | Same-second claim race: two fresh board clones both `take /pd doom-2016-vr` in the same second | **pass**: one CLAIMED, the other REFUSED naming the holder; one claim commit on GitHub. Its release then hit a new fault (below), fixed |
| 3 | Start-up with no internet (web calls sent to a dead address) | **pass, with a note**: nothing hung, timings as online; the save line says GitHub could not be reached. The board, owed and ideas checks quietly used the last downloaded copy without saying so. The start note was kept and sent later |
| 4 | Window closed mid-save: leftover lock file, staged change, commit not pushed, pull stopped half-way | **pass after a fix**: all four were NOT SAVED, the clean copy was not; the lock file and the half-way pull now get their own plain line (`git_leftovers.py`) |
| 5 | /pd and /lm on one PC, the real prompt guards through the installed launcher, practice board | **pass**: 6 of 6 combinations as wanted (second /pd refused, /lm on a claimed game refused, /lm on another game and the /pd holder pass) |
| 6 | A PC off for days: board copy wound back to 2026-10-28 | **pass**: the reminders added since were still listed, marked "on GitHub but NOT in this clone; pull the board first"; the board summary read GitHub |

Faults found and fixed this run: the release check made an empty notes folder and then refused it (FAULTS.md);
a cut-off save was not named for what it left behind. Learned: with a folder marketplace Claude Code reads the
plugin straight from the worktree, so every edit there is live for the next new window, and the update hold
cannot stop that (it stops update commands only). A window keeps the hook LIST it started with: the new hold
guard is active only in windows opened after the install; launcher and tool fixes apply at once.
Not yet seen: the online start run of test 3 committed its start note and did not push it (the offline one is
expected not to); the cause was not found [hypothesis: a pull that timed out or met a lock, n=1].

### Run 4 - 2026-11-02, BOTH PCs on the test build (lanes-next), messages over Remote Control

Tefa: "please test things at your own pace and order as you see fit". Home: session "Lanes 2 PC test session".
Scratch files in the board's `two-pc-test/`, named `2026-11-02-run4-*`. `[verified-live 2026-11-02, n=1]`

| # | Dev -> home | Home -> dev | Note |
| --- | --- | --- | --- |
| S1 | pass | pass | check words seen both ways (`dev-s1-1026-quokka`, `home-s1-1040-pangolin`); each handover line named the other PC's last save |
| S2 | pass | pass | NOT SAVED named "claude-memory (/pd root): 1 file(s) never added" both ways |
| S3 | pass | pass | each reminder greeted only its PC. Home saw "raised on <host name> (DEV)": the board's `owed.sh` still writes the computer name (same fault as Run 2 #4); home fixing it on the board |
| S4 | pass | pass | cleared both ways, gone after a pull |
| S5 | (Run 1) | pass | PC2 column for all 39 projects, no GONE/MOVED from the other PC's record |
| S6 | (Run 1) | pass, partial | Hand Poser still "release unknown" for PC2 |
| B1 | pass (both clones on the dev PC, real GitHub) | - | same-second pushes: one refused ("cannot lock ref", GitHub's own race message), pull --rebase, landed |
| B2 | pass (same set-up) | - | same line: refused, rebase stopped naming the file with both values, kept both, landed |

**Safety checks in REAL new windows** (headless `claude -p`, sonnet, on the installed test build, dev PC): the repo
guard (no visibility flag), the update hold (`claude plugin update lanes`) and the privacy hook (a home path in an
issue body) each REFUSED; a typed `/pd` with another session's fresh lock and `/lm` on a claimed practice project were
BLOCKED at the prompt; the new start-up line "STRAIGHT TALK" was present. Test set-up lessons: Git Bash turns "/pd"
into a file path (run `claude -p "/pd"` from PowerShell), and `MSYS_NO_PATHCONV` breaks the hooks' own paths.

**Faults found in Run 4:**
1. FIXED (dev): a skill started by Claude itself (Skill tool) skipped both lane guards; `/ms` was never checked at all.
   New `hooks/skill-lane-guard.py`; `lane-claim-guard.py` matches /ms. Re-checked in a real window: asked in plain
   words to start pd while another session held the lock, Claude was refused with the reason.
2. FIXED (home, pushing): `games.py` guessed the clone root as the board's parent; the home PC keeps the board
   elsewhere, so every project read GONE PROJECT. Now uses the `root` setting first.
3. FIXED (home, pushing): `handover.py` found the lane roots (-pd, -gr ...) only beside the board, so on the home PC a
   file left in the /pd root never turned the light red. Now also beside `root`. It then showed real leftovers the
   home PC had hidden (visceral-re2-vr and the-evil-within-vr in its /pd root).
4. OPEN (board tool, home fixing): `owed.sh` writes the computer name.

**Run 4, second half (2026-11-02 late morning):**
- Home, real new window (PowerShell, `claude -p "/pd"` with another session's throwaway lock): BLOCKED, PD GUARD. pass.
- 5. FIXED (home): input piped from PowerShell starts with a byte-order mark, `json.load` failed and six hooks let the
  command through (begone-raw-guard, inspector-hook, lane-claim-guard, pd-guard, privacy-hook, reader-guard). Claude
  Code itself sends no BOM, so real use was not affected. Now read as bytes, utf-8-sig. The dev PC's two new hooks
  (update-hold-guard, skill-lane-guard) had the same hole: fixed (1f50404), both refuse with a BOM now.
- 4. FIXED (home, board 4ab7e617): `owed.sh` writes "PC1 (HOME)", not the computer name.
- Home caught its own test folder name being read as a real account's home path by scrub-scan, and the privacy guard
  refused the commit message quoting it: both checks did their job.
- Suites on the combined build 9efc5a9: home smoke PASS, hooks PASS. Dev hooks PASS; dev smoke failed ONE check once
  ("texts: not set up says so", gu-fixture), then gu-fixture passed 3 of 3 alone: a check that can fail under load on
  the low-powered dev PC `[measured 2026-11-02, n=1 of 4]`. Full smoke re-run below.
- Dev start-up on the test build, measured from six real new windows: every start lost 4 to 18 SessionStart checks to
  their time limits (Run 2 fault 2, unchanged), among them "both PCs in sync", the reminders and the board. Several of
  the lost ones are the personal copies in `~/.claude/settings.json` that duplicate Lanes' own (code-health row
  "Two copies of the lane guards", waiting on Tefa's go-ahead to remove them).
- Left for Tefa (home): what the corrected light now shows in the home PC's /pd root (visceral-re2-vr: 7 idea picks
  never committed; the-evil-within-vr: an untracked proxy-winmm/ folder).
- Dev smoke-test re-run on 9efc5a9: **PASS** (all assertions). Both suites now pass on both PCs on the same build. **Run 4 done.**
- Home /pd root leftovers, Tefa's decision: the 7 RE2 idea picks saved and pushed (visceral-re2-vr 19a326d); The Evil Within's proxy-winmm/ stays untouched for now.
