#!/usr/bin/env bash
# gs-scan.sh - the mechanical half of /gs (GitHub Sweep). READ-ONLY.
#
# WHY THIS EXISTS
#   A weekly re-read of the whole estate is not sustainable and never will be.
#   But most hygiene questions are greppable invariants, not reading
#   comprehension - so this triages mechanically and leaves only the exceptions
#   for the session to actually read.
#
# WHY IT SCOPES BY FILE CLASS, NOT JUST BY DATE
#   Measured 2026-08-28: in a 7-day window, 100 of 100 repos were touched and
#   845 files changed - a date filter alone shrank nothing, because the estate
#   was scaffolded inside that window. But 431 of those 845 were boilerplate
#   (README/CREDITS/CONTRIBUTING/LICENSE) that cannot carry a claim. Filtering
#   by file class cut the real target to 93. Date narrows further once the
#   estate stops being new; file class is what makes it sustainable today.
#
# NEVER WRITES. Reports only. /gs files inbox drops for anything an owner must
# act on, which is what keeps it compatible with the one-writer-per-file rule.
#
# Usage: gs-scan.sh [backups-root] [since-date]
#   since-date defaults to the last date in gs-sweep-log.md, else 7 days ago.

set -uo pipefail

# ---- where are the repos? -------------------------------------------------
# Resolution order: an explicit argument, then $LANES_ROOT, then `root = <path>`
# in the config file, then the current directory if it actually holds clones.
# $PWD is checked before the config so that a lane running from its OWN root is
# never silently redirected into another lane's tree -- a read of a tree another
# session may be mid-write in, with the results attributed to the wrong root.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
read_conf() {
  local key="$1" conf v=""
  for conf in "${LANES_CONFIG:-}" "$HOME/.claude/lanes.conf" "$HOME/.config/lanes/lanes.conf"; do
    [ -n "$conf" ] && [ -f "$conf" ] || continue
    v=$(sed -n "s/^[[:space:]]*$key[[:space:]]*=[[:space:]]*//p" "$conf" | head -1 |
        sed 's/[[:space:]]*$//; s/^"//; s/"$//')
    [ -n "$v" ] && break
  done
  printf '%s' "$v"
}

if [ -n "${1:-}" ]; then ROOT="$1"
elif ls -d "$PWD"/*/.git >/dev/null 2>&1; then ROOT="$PWD"
else
  ROOT="${LANES_ROOT:-$(read_conf root)}"
fi
if [ -z "${ROOT:-}" ] || [ ! -d "$ROOT" ]; then
  echo "gs-scan: no repo root found. Pass one, set LANES_ROOT, or write" >&2
  echo "           root = /path/to/folder-holding-your-clones" >&2
  echo "         into ~/.claude/lanes.conf." >&2
  exit 2
fi

# The board repo is one of the clones under $ROOT. Its folder name comes from the
# basename of `board` in the config, so both scripts agree without repeating it.
BOARD_DIR="$(read_conf board_dir)"
if [ -z "$BOARD_DIR" ]; then
  _b="$(read_conf board)"
  [ -n "$_b" ] && BOARD_DIR="$(basename "$_b")"
fi
BOARD_DIR="${BOARD_DIR:-board}"

cd "$ROOT" || { echo "cannot cd to $ROOT"; exit 1; }

# ⚠️ COVERAGE GUARD - the difference between "clean" and "I could not see anything".
# Since the 2026-08-30 consolidation the estate is 22 repos, in five per-lane roots since
# 2026-09-01, each holding the full 22.
# CORRECTED 2026-09-08: this comment used to say those clones were on the DEV PC only, and
# that the home PC held "a partial set with no backups folder". Both machines are complete -
# the home PC's github-backups{,-pd,-gr,-sr,-gs} each hold all 22 with an origin remote
# [verified-numerically 2026-09-08]. The check below was always machine-agnostic: it counts
# what is actually under $ROOT, so it stays correct however the estate is laid out. The
# point of the banner is unchanged - a hygiene tool that silently understates is worse than
# no hygiene tool, so say so loudly.
REPO_COUNT=$(for d in */; do [ -d "$d/.git" ] && echo x; done | wc -l)
# How many clones this root SHOULD hold. Optional: set `expected_repos = N` in the
# config file once you know your number. Without it the banner never fires -- but a
# hygiene tool that silently understates is worse than no hygiene tool, so setting
# it is strongly recommended the moment your estate has a stable size.
EXPECTED_MIN="$(read_conf expected_repos)"
if [ -n "$EXPECTED_MIN" ] && [ "$REPO_COUNT" -lt "$EXPECTED_MIN" ]; then
  echo "###################################################################"
  echo "  !! PARTIAL ESTATE - RESULTS ARE NOT A CLEAN BILL OF HEALTH !!"
  echo "  found $REPO_COUNT git repos under $ROOT (expected >= $EXPECTED_MIN)"
  echo "  This machine probably does not hold every repo. Everything below is"
  echo "  scoped to what was visible, and NOTHING here should be read as"
  echo "  'the estate is fine'."
  echo "###################################################################"
fi

LOG="$BOARD_DIR/gs-sweep-log.md"
if [ -n "${2:-}" ]; then SINCE="$2"
elif [ -f "$LOG" ]; then
  SINCE=$(grep -oE '^## [0-9]{4}-[0-9]{2}-[0-9]{2}' "$LOG" | head -1 | awk '{print $2}')
  SINCE="${SINCE:-7 days ago}"
else SINCE="7 days ago"; fi

# ⚠️ TRAP, and it silently makes this whole script useless:
# git's approxidate fills UNSPECIFIED fields from the CURRENT TIME, so a bare
# --since=2026-08-28 means "since 14:57 today", not "since midnight". Measured
# on 2026-08-28 at 14:57 against a repo committed to at 14:55:
#     --since=2026-08-28            -> 0 commits
#     --since=2026-08-28T00:00:00   -> 5 commits
# A sweep reading its own log would therefore report "nothing changed" every
# time and read as a clean bill of health. Always pin the time explicitly.
case "$SINCE" in
  [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) SINCE="${SINCE}T00:00:00" ;;
esac

echo "==================================================================="
echo " /gs mechanical scan   root=$ROOT"
echo " delta since: $SINCE"
TMPF8=$(mktemp 2>/dev/null || echo "${TMPDIR:-/tmp}/gs8.$$")
echo "==================================================================="

# --- 1. INBOX BACKLOG ------------------------------------------------------
# Enumerate inbox dirs at ANY depth. Fixed-depth globbing was a silent disaster:
# written 2026-08-28, when lanes were separate repos and every inbox really was
# <repo>/inbox. The 2026-08-30 consolidation moved lanes into folders, making game
# inboxes <repo>/<lane>/inbox - so "*/inbox/*.md" saw 2 of 33, and checks 1, 2 and 5
# reported "clean" for every game repo until this was fixed 2026-09-01. Using find
# keeps it correct if the layout ever moves again.
inbox_dirs() {
  find . -type d -name inbox -not -path "*/.git/*" 2>/dev/null | sed "s|^./||" | sort
}

#
# 2026-09-07: AGE ALONE WAS AMBIGUOUS, and the ambiguity hid a live falsehood for
# five sweeps. one project's dossier carried a date /gr had corrected on 09-04.
# The 09-05 /gs drop reported it; a modding session committed to that repo at
# 15:06 the next day - 24 minutes after the drop landed - fixed the drop's cheap
# half (two tags), left its expensive half (the date), and left both drops in
# place. Every sweep since read them as "1d / 2d, the owner has not run yet",
# i.e. WAITING, which needs nobody. The truth was STALLED: the owner ran, saw it,
# and moved on.
#
# Computable with no new convention: a drop is STALLED when the owning lane has
# committed to files it owns in that repo, OUTSIDE any inbox, AFTER the drop
# landed. Owner paths are derived from WHICH lane's inbox it is, so a /gr commit
# to external-research/ cannot make a modding drop look stalled.
#
# It says nothing about whether the remaining work is large or small - only that
# someone with the authority to do it has been past since. That is exactly the
# distinction age could not express.
owner_paths() {
  case "$1" in
    */engine-research/inbox)   echo "dev-archive modding-notes engine-research mod" ;;
    */external-research/inbox) echo "external-research" ;;
    *)                         echo "." ;;
  esac
}
# A non-empty inbox is a visible to-do, never a silent loss - but an OLD one
# means the owning lane has not run in a while.
echo
echo "--- 1. undrained inbox files (owner must fold these in) ---"
found=0; stalled=0
now=$(date +%s)
while IFS= read -r dir; do
  for f in "$dir"/*.md; do
    [ -e "$f" ] || continue
    case "$(basename "$f")" in README.md) continue;; esac
    # git must run INSIDE the repo: ROOT is a plain folder of clones, not a repo
    # itself, so the old "git log" from here always failed and fell back to now.
    # Every file reported 0d and the STALE flag could never fire (fixed 2026-09-01).
    repo="${f%%/*}"; rel="${f#*/}"
    ts=$(git -C "$repo" log -1 --format=%ct -- "$rel" 2>/dev/null)
    [ -z "$ts" ] && ts="$now"
    age=$(( (now - ts) / 86400 ))
    flag=""; [ "$age" -ge 14 ] && flag="  <-- STALE (>=14d)"
    # STALLED outranks STALE in the label: an owner who has been past since is a
    # sharper signal than an owner who has not run at all.
    op=$(owner_paths "$dir")   # full path: the case patterns need the repo component
    lastown=$(cd "$repo" 2>/dev/null && git log -1 --format=%ct -- $op ":(exclude)*inbox/*" 2>/dev/null)
    if [ -n "$lastown" ] && [ "$lastown" -gt "$ts" ]; then
      od=$(( (now - lastown) / 86400 ))
      flag="  <-- STALLED (owner committed here ${od}d ago, AFTER this drop)"
      stalled=$((stalled+1))
    fi
    printf "  %-72s %3dd%s\n" "$f" "$age" "$flag"
    found=$((found+1))
  done
done < <(inbox_dirs)
[ "$found" -eq 0 ] && echo "  (none - all inboxes clean)"
if [ "$stalled" -gt 0 ]; then
  echo "  ^ $stalled STALLED: the owning lane has committed to files it owns in that"
  echo "    repo since the drop landed, so this is NOT \"waiting for the owner to run\"."
  echo "    Either the drop was partly done and the rest forgotten, or it was missed."
fi

# --- 2. SUPERSESSION -------------------------------------------------------
# A correction names its target. Two cases matter and they need OPPOSITE action,
# which is exactly why this cannot be left to a human skim.
echo
echo "--- 2. Supersedes: headers and whether their target is still pending ---"
sup=0
while IFS= read -r line; do
  [ -z "$line" ] && continue
  file="${line%%:*}"; rest="${line#*:}"; tgt="${rest#*Supersedes:}"
  # A BOLDED header ("**Supersedes:** x") leaves a stray "**" on the front of the
  # target; strip it so the filename test below sees the filename. See the grep at
  # the bottom of this loop for why the bolded form is accepted at all.
  tgt="${tgt#\*\*}"
  # Pure-shell trim. "| xargs" was used here until 2026-09-01 and CRASHED on any
  # target containing a quote or backtick ("xargs: unmatched double quote"), which
  # is common since CONVENTIONS.md allows a prose "doc section" target.
  tgt="${tgt#"${tgt%%[![:space:]]*}"}"
  tgt="${tgt%"${tgt##*[![:space:]]}"}"
  dir=$(dirname "$file")
  sup=$((sup+1))
  # CONVENTIONS.md allows "Supersedes: <filename, or doc section>", so the value may
  # carry a trailing comment or be prose. Test the FIRST token as a filename; never let
  # a suffix make a still-pending target look drained - the two verdicts below call for
  # opposite actions. (Fixed 2026-09-01 after exactly that misreport.)
  first=$(printf '%s' "$tgt" | awk '{print $1}')
  # A target may be written relative to the LANE ("inbox/<file>.md") rather than as a
  # bare filename - the conventions' own examples use that form. $dir already ENDS in
  # "inbox", so joining it produced ".../inbox/inbox/<file>.md", missed, and fell
  # through to the "ALREADY DRAINED" branch. Those two branches prescribe OPPOSITE
  # actions, so that was a silent verdict INVERSION. Fixed 2026-09-10, upstream in
  # claude-memory/tools/gs-scan.sh; keep the two copies in step.
  # The fallback is deliberately NARROW - it fires only when the target's own leading
  # folder names THIS directory, so "topics/<file>.md" is still correctly reported as
  # a curated doc even if a same-named file happens to sit in the inbox.
  tdir=$(dirname "$first")
  echo "  $file"
  if [ -e "$dir/$first" ] || { [ "$tdir" = "$(basename "$dir")" ] && [ -e "$dir/$(basename "$first")" ]; }; then
    echo "     -> target STILL IN INBOX ($first)"
    echo "        ACTION: drain BOTH together; the correction wins."
  elif [ "${first%.md}" != "$first" ]; then
    echo "     -> target ALREADY DRAINED ($first)"
    echo "        ACTION: the superseded claim may ALREADY BE LIVE in the"
    echo "                curated docs - go check and correct it there."
  else
    echo "     -> target is a doc/section reference, not an inbox file ($tgt)"
    echo "        ACTION: open that doc and check the claim is corrected there."
  fi
done < <(inbox_dirs | while IFS= read -r dir; do
           # ⚠️ 2026-09-08: this matched "^Supersedes:" ONLY, so a header written in
           # bold — "**Supersedes:** …", which markdown renders identically and which
           # CONVENTIONS.md does not forbid — was INVISIBLE to this check. A real
           # correction was missed that way: one project's research drop
           # superseded a live topic section, and the sweep that same day reported it as
           # carrying no Supersedes header at all. Six files estate-wide use the bolded
           # form. The whole point of check 2 is that a correction cannot go unnoticed,
           # so the pattern now accepts both. Author guidance is unchanged — write it
           # plain — but the check must not depend on the author getting that right.
           grep -rnE "^\*{0,2}Supersedes:" "$dir" --include=*.md --exclude=README.md 2>/dev/null
         done)
[ "$sup" -eq 0 ] && echo "  (no corrections pending)"

# --- 3. UNTAGGED CLAIM-BEARING DOCS ---------------------------------------
# Untagged == treated as [hypothesis]. Pre-convention docs are expected to fail
# this; the number should trend DOWN, and is not an emergency.
echo
echo "--- 3. claim-bearing docs with NO confidence tag (changed since $SINCE) ---"
# Must match CONVENTIONS.md -> 'Claim hygiene' exactly. It did not until 2026-09-01:
# commands/pd.md used verified-numerically and compile-verified, which neither this
# regex nor CONVENTIONS.md knew, so correctly-tagged /pd work reported as untagged.
TAG='\[(verified-live|verified-numerically|compile-verified|measured|inferred-static|reported|hypothesis|disproved)'
untagged=0; checked=0; vendored=0
for d in */; do
  [ -d "$d/.git" ] || continue
  while IFS= read -r rel; do
    [ -z "$rel" ] && continue
    case "$rel" in
      # INDEX.json IS in this class, and that took two goes to get right.
      # It failed check 3 in four consecutive sweeps as a known structural false
      # positive, was excluded 2026-09-01, then RE-ADMITTED the same day once its
      # `stage` strings were actually tagged - which is the fix the exclusion
      # comment had asked for. Tagging them honestly turned up three stale claims
      # (three separate projects), so the check was never noise: it was pointing
      # at a real gap in the estate's most-read file.
      # JSON strings are free text and hold a tag fine. If this ever starts failing
      # again, the answer is to tag the new claim, not to drop the class.
      *ENGINE-DOSSIER.md|*topics/*.md|*STATUS.md|*INDEX.json) ;;
      *) continue;;
    esac
    # VENDORED / RESCUED SOURCE TREES are carried verbatim, not curated, and this
    # check must not reach into them. Added 2026-09-02 for
    # staging/<project>/src/repo/docs/STATUS.md - a frozen 2026-08-19 (0.2.3)
    # snapshot inside a rescued vendored source tree. Its whole value is that
    # it is BYTE-IDENTICAL to the last pre-0.2.7 deployment, which is how it was
    # verified; editing a file inside it to add a confidence tag would destroy the
    # very property the verification rests on. The fix and the check were in direct
    # conflict, so the check yields.
    #
    # ⚠️ This is NOT the INDEX.json case (see gs-sweep-log 2026-09-01, 7th run), where
    # "structural false positive" was recorded four times and turned out to mean "we
    # have not tagged it yet" - one attempt fixed it and exposed three stale claims.
    # The test that tells the two apart: DOES SATISFYING THE CHECK COST SOMETHING REAL?
    # INDEX.json: no. A rescued tree: yes, it invalidates a verification.
    # Do not widen this arm to make an inconvenient flag go away.
    case "$rel" in
      */src/*) vendored=$((vendored+1)); continue ;;
    esac
    f="$d$rel"; [ -e "$f" ] || continue
    checked=$((checked+1))
    if ! grep -qE "$TAG" "$f" 2>/dev/null; then
      [ "$untagged" -lt 15 ] && echo "  $f"
      untagged=$((untagged+1))
    fi
  done < <(git -C "$d" log --since="$SINCE" --name-only --pretty=format: 2>/dev/null | sort -u)
done
[ "$untagged" -gt 15 ] && echo "  ... and $((untagged-15)) more (list capped; this is a backlog, not an emergency)"
echo "  ($untagged untagged of $checked claim-bearing docs changed in window)"
[ "$vendored" -gt 0 ] && echo "  ($vendored skipped: vendored/rescued source tree under */src/ - carried verbatim, must not be edited)"

# --- 3b. MALFORMED TAGS ----------------------------------------------------
# Check 3 above is all-or-nothing PER FILE: a document with thirty good tags and
# three bad ones passes clean. That is exactly how a project's dossier carried
# three `[verified from published first-party source, ...]` tags unnoticed - they
# read as "verified" to a human skimming and as NOTHING AT ALL to every tool,
# because the name is not in the vocabulary. Found by hand 2026-09-01; this makes
# it mechanical. Checks the TAG, not the document.
echo
echo "--- 3b. off-vocabulary confidence tags (read as a tag, count as nothing) ---"
# Docs that define or discuss the vocabulary quote every tag, valid and invalid, so
# they match everything. Excluding them is the difference between a check and noise.
# inbox/ is excluded on purpose: drops are create-only transients that frequently QUOTE
# a bad tag in order to report it, and their content is validated when the owner drains
# them. 3b is about CURATED docs. Check 1 already tracks the inboxes themselves.
VOCABDOCS='CONVENTIONS\.md|game-mod-rules\.md|PLAYBOOK\.md|gs-sweep-log\.md|commands/|/inbox/'
offv=0; offv_use=0; offv_mention=0; offv_quoted=0; uses=""; mentions=""; quoted=""
while IFS= read -r hit; do
  [ -z "$hit" ] && continue
  loc="${hit%%|*}"; name="${hit##*|}"
  # exact vocabulary members are correct - skip
  case "$name" in
    verified-live|verified-numerically|compile-verified|measured|inferred-static|reported|hypothesis|disproved) continue ;;
  esac
  # Everything else only matters if it LOOKS like a confidence claim. Matching every
  # backtick-bracket gave 26 hits of which 25 were noise - `[my_script_name]`,
  # `[Engine]`, `[BG2]` are Lua identifiers and INI sections, not tags. The real
  # failure mode is a PLAUSIBLE invented tag that reads as strong to a human, so
  # match on confidence-claiming stems only.
  printf '%s' "$name" | grep -qiE 'verif|measur|infer|report|hypoth|disprov|confirm|observ|validat|proven|establish' || continue

  # 2026-09-05: SPLIT USES FROM MENTIONS.
  #
  # The 09-05 sweep found 7 of 13 hits were prose ABOUT a bad tag rather than a
  # bad tag: changelog rows, "this pass corrected an off-vocabulary
  # `[verified-static]` tag", a note explaining a name is not one of the eight.
  # The command file's claim that "a hit is nearly always real" was measured at
  # ~46%. Worse, the error is SELF-REINFORCING: every time a lane correctly
  # documents a tag correction it adds a permanent false positive, so the check
  # gets noisier precisely as the estate does the right thing.
  #
  # Excluding those lines outright would be wrong - a real bad tag can sit on a
  # line that also discusses tags. So nothing is dropped; hits are CLASSIFIED
  # and printed in two groups, with the actionable group first.
  #
  # The discriminator, checked against all 13 hits of 2026-09-05: a real tag USE
  # carries arguments (a date, `n=`), because that is what the convention asks
  # for. A MENTION is bare - `[verified-static]` - because prose quotes the NAME,
  # not a whole claim. That split was clean on 12 of 13.
  #
  # ⚠️ RELABELLED the same evening, after the four-lane run produced the case the
  # first labelling got wrong. `[inferred]` was used as a REAL tag, twice, with
  # no date (one project's port map :411 and :909). Undated, it
  # landed in the second bucket, which then read "usually prose ABOUT a tag;
  # confirm before acting" - soft-pedalling a genuine defect in the one direction
  # that matters.
  #
  # The fix is NOT a cleverer date test. An undated off-vocabulary tag is not a
  # third case, it is BOTH defects at once: an invented name AND a missing date.
  # So the buckets are now DATED and UNDATED, named after what was actually
  # measured, and neither label tells the reader it is probably fine.
  # `loc` arrives as "./file.md:123:" WITH a trailing colon (the sed above replaced
  # the "`[" that followed it). Strip that first, or the line number parses as
  # empty and every hit silently lands in the "bare" bucket - which is exactly
  # what the first version of this patch did.
  loc2="${loc%:}"; lineno="${loc2##*:}"; fname="${loc2%:*}"
  line=$(sed -n "${lineno}p" "$fname" 2>/dev/null)
  # Text between the tag NAME and the closing bracket. Non-greedy is unavailable
  # in sed, so cut at the first occurrence by deleting up to and including it once,
  # then truncate at the first "]".
  #
  # ⚠️ It must be the whole body, not just what follows the name immediately.
  # The first version of this patch tested only the character after the name and
  # mis-filed the very case check 3b was created for - one project's
  # `[verified from published first-party source, 2026-08-30]`, where a prose
  # phrase sits between the name and the date. It was still printed, but in the
  # "usually prose" bucket, which is the opposite of what it deserved. Caught by
  # the fixture in tools/tests/, which exists for exactly this reason.
  after=${line#*"[$name"}
  body=${after%%]*}
  #
  # 2026-09-07: THIRD BUCKET - a DATED tag QUOTED inside correction prose.
  #
  # The 09-05 split keyed only on the tag body, so a changelog line recording a
  # fix - which must quote the OLD tag verbatim, date and all - was classified
  # DATED, i.e. "a real claim wearing an invented name. Fix these:". A lane that
  # correctly documented its own correction was therefore reported as having
  # committed a fresh violation. Observed on a status file the day
  # after that lane drained a tag drop exactly as asked.
  #
  # This is the SAME self-reinforcing error the 09-05 split was built to remove,
  # displaced one bucket along: the check got noisier precisely as the estate did
  # the right thing, and it taught sessions to fix tags SILENTLY - the opposite
  # of what claim hygiene is for.
  #
  # ⚠️ 2026-09-19: A WIDER WINDOW WAS TRIED AND REJECTED. KEEP THIS LINE-BASED.
  # There IS a real remaining false positive here, and it is worth understanding before
  # anyone "fixes" it again. Prose WRAPS. A changelog must quote the old tag verbatim,
  # so the quoted tag and the word "retagged" routinely land on DIFFERENT lines - which
  # means the word list can be perfect and the check still misfires.
  #
  # The obvious fix - classify on the hit line PLUS N lines either side - was written and
  # run against tools/tests/gs-scan-3b-fixture.sh, which caught what it actually does: in
  # dense text a correction word near an UNRELATED tag drags that tag into "already
  # fixed". That is a FALSE NEGATIVE and it HIDES a real bad tag. Reverted.
  #
  # The line-based failure mode is noise in the "fix these" bucket: visible and annoying.
  # The windowed failure mode is silence. ⚠️ When a check must choose, it errs toward the
  # noisy bucket. Paragraph-bounding by blank line does not help either - the fixture's
  # own cases, and most real changelog prose, sit on consecutive lines.
  #
  # The cure is author-side and costs nothing: when a changelog quotes a tag it has
  # corrected, KEEP THE QUOTED TAG AND THE CORRECTION WORD ON THE SAME LINE. The tool
  # cannot read paragraphs safely; a writer can trivially not split one.
  #
  # The discriminator is the LINE, not the tag: prose that corrects a tag says so
  # ("vocabulary", "retag", "corrected", "now reads", "drained", "supersedes", and since
  # 2026-09-19 also "became", "replaced by/with", "changed to", "should be/have been").
  #
  # WHY THE LIST KEEPS GROWING: every word missing from it turns a correctly-documented
  # fix into a permanent false positive - the same self-reinforcing error the earlier
  # DATED/UNDATED split was built to remove. A lane that does the right thing and writes
  # it down gets punished for it, and learns to fix tags silently instead.
  # A curated doc stating a real claim has no reason to use those words. Keyed on
  # correction language alone, NOT on "the line also holds a valid tag" - that
  # second signal misfires on a genuine bad tag sitting beside a genuine good one.
  #
  # Nothing is dropped, as ever. The bucket is printed, and its label does not
  # tell the reader it is fine - the 09-05 relabelling exists because a bucket
  # that reads "probably prose" hides the case it was meant to surface.
  is_quoted=0
  printf '%s' "$line" | grep -qiE 'vocabular|off-vocab|re-?tag|correct(ed|ion|s)|now reads?|drained|supersed|is not one of|was not in|became|replaced (by|with)|changed to|should (be|have been)' && is_quoted=1
  if printf '%s' "$body" | grep -qE '(v?[0-9]{4}-[0-9]{2}-[0-9]{2}|n=)'; then
    if [ "$is_quoted" -eq 1 ]; then
      quoted="$quoted  $loc2  ->  [$name ...
"
      offv_quoted=$((offv_quoted+1))
    else
    uses="$uses  $loc2  ->  [$name ...
"
    offv_use=$((offv_use+1))
    fi
  else
    mentions="$mentions  $loc2  ->  [$name]
"
    offv_mention=$((offv_mention+1))
  fi
  offv=$((offv+1))
done < <(grep -rnoE '`\[[a-zA-Z][a-zA-Z0-9_-]*' --include=*.md . 2>/dev/null |
         grep -Ev "$VOCABDOCS" | sed 's/`\[/|/')
if [ "$offv" -eq 0 ]; then
  echo "  (none - every tag name is in the vocabulary)"
else
  if [ "$offv_use" -gt 0 ]; then
    echo "  DATED - a real claim wearing an invented name. Fix these:"
    printf '%s' "$uses" | head -25
  else
    echo "  DATED: (none)"
  fi
  if [ "$offv_mention" -gt 0 ]; then
    echo "  UNDATED - EITHER prose about a tag (fine as written) OR a real tag"
    echo "  missing its date as well as a valid name, i.e. BOTH defects at once."
    echo "  Read the line before deciding; do not assume prose:"
    printf '%s' "$mentions" | head -25
  fi
  if [ "$offv_quoted" -gt 0 ]; then
    echo "  QUOTED IN CORRECTION PROSE - the line carries a dated invented tag AND"
    echo "  correction language, so it is usually a changelog recording a fix that"
    echo "  has already been made. Occasionally it is a real tag on a line that"
    echo "  happens to discuss tagging. Read it before dismissing:"
    printf '%s' "$quoted" | head -25
  fi
  echo "  ($offv_use dated, $offv_mention undated, $offv_quoted quoted. Valid names: verified-live,"
  echo "   verified-numerically, compile-verified, measured, inferred-static,"
  echo "   reported, hypothesis, disproved)"
fi

# --- 4. WEAK OR UNDATED EVIDENCE ------------------------------------------
# n=1 is not verified, and a verified-live with no date cannot be aged.
echo
echo "--- 4. claims worth a second look (n=1, or verified with no date) ---"
# The files that DEFINE the vocabulary quote every tag, so they match everything.
# Excluding them is the difference between a useful check and pure noise.
DEFN='CONVENTIONS\.md|game-mod-rules\.md|inbox/README\.md|PLAYBOOK\.md'
{
  grep -rnE '\[verified-live[^]]*n=1' --include=*.md . 2>/dev/null |
    grep -Ev "$DEFN" | head -20 | sed 's/^/  n=1:     /'
  grep -rnE '\[verified-live\]' --include=*.md . 2>/dev/null |
    grep -Ev "$DEFN" | head -10 | sed 's/^/  undated: /'
} > /tmp/gs_weak.txt 2>/dev/null
if [ -s /tmp/gs_weak.txt ]; then cat /tmp/gs_weak.txt; else echo "  (none)"; fi
echo "  (n=1 is legitimate for a DISPROOF - one counter-example refutes a rule)"

# --- 5. TEMPLATE DRIFT -----------------------------------------------------
# The estate has a "unified look" rule; drift is invisible without hashing.
echo
echo "--- 5. inbox READMEs missing the supersession/tag rules ---"
# DO NOT test these for hash-identity. Measured 2026-08-28: the 33 READMEs come
# in 4 variants, and that is CORRECT, not drift - an engine-research/ inbox is
# owned by the modding session, an external-research/ inbox by the research
# session, the cross-engine one by the sweep, and the public profiles repo by its
# maintainer. Each names a different owner and a different set of drop authors.
# An earlier version of this check compared hashes and advised "unify", which
# would have flattened away real information. The invariant is that every README
# CARRIES THE RULES, each in its own role's wording - not that they are the same
# file.
miss=0; tot_r=0
while IFS= read -r dir; do
  f="$dir/README.md"
  [ -e "$f" ] || continue
  tot_r=$((tot_r+1))
  if ! grep -q "Supersedes:" "$f" 2>/dev/null; then
    echo "  $f"
    miss=$((miss+1))
  fi
done < <(inbox_dirs)
echo "  ($miss of $tot_r inbox READMEs missing the 'Supersedes:' protocol)"

# --- 5b. PASTED-BACK PREAMBLE BLOCKS ---------------------------------------
# On 2026-09-04 the five lane command files were de-duplicated: the clone-root,
# background-agent, inbox-drain, layout and research-rules blocks became short
# stubs, and the full text lives once in CONVENTIONS.md ("Shared lane preamble")
# and PREFERENCES.md. Copies drift, so a block pasted back into a command file
# is drift, not emphasis. The sentinels below are phrases that existed ONLY in
# the removed copies - never in the stubs, never in the canonical text's own
# wording - so a hit means a block came back.
#
# POSITIVE CONTROL, and it is the point: a negative from a grep is only evidence
# if the grep could have found a positive (feedback rule, 2026-09-03). So every
# sentinel is also run against the pre-dedupe files at a319ae9^ - the commit that
# removed them - and a sentinel that never matched there is reported as DEAD,
# because a typo in it would otherwise read as "clean" forever.
#
# Matching is done on whitespace-normalised text: these files are hard-wrapped
# at ~100 columns and a phrase that spans a line break is invisible to a plain
# line grep (that is exactly how the first draft of this check found nothing).
echo
echo "--- 5b. lane command files carrying a block that now lives only in CONVENTIONS/PREFERENCES ---"
SENTINELS=(
  "GitHub the only synchronisation point"   # clone-root rationale
  "licence to fan out"                      # background-agents rationale
  "nothing in git to show"                  # drain-by-explicit-list rationale
  "as when they were separate"              # consolidated-layout note (gr wording)
  "is the .staging. monorepo"               # consolidated-layout note (sr wording)
  "restated because they matter"            # research non-negotiables list
  "can never produce the same"              # inbox-mechanics rationale
  "cloaked fake"                            # research rules, prompt-injection bullet
)
CMDDIR="$ROOT/$BOARD_DIR/commands"
DEDUPE_COMMIT="a319ae9"
pasted=0; dead=0
if [ -d "$CMDDIR" ]; then
  for f in "$CMDDIR"/*.md; do
    [ -e "$f" ] || continue
    for s in "${SENTINELS[@]}"; do
      if tr -s '[:space:]' ' ' < "$f" | grep -qE -- "$s"; then
        printf "  %-18s carries: \"%s\"\n" "commands/$(basename "$f")" "$s"
        pasted=$((pasted+1))
      fi
    done
  done
  # positive control: each sentinel must match at least one pre-dedupe file
  for s in "${SENTINELS[@]}"; do
    hit=0
    for c in gr sr pd gs; do
      git -C "$ROOT/$BOARD_DIR" show "${DEDUPE_COMMIT}^:commands/$c.md" 2>/dev/null |
        tr -s '[:space:]' ' ' | grep -qE -- "$s" && hit=1 && break
    done
    if [ "$hit" -eq 0 ]; then
      echo "  SENTINEL DEAD: \"$s\" never matched the pre-dedupe files - fix the phrase, the check is blind to that block"
      dead=$((dead+1))
    fi
  done
  if [ "$pasted" -eq 0 ] && [ "$dead" -eq 0 ]; then
    echo "  (none - every command file is a stub; positive control ${#SENTINELS[@]}/${#SENTINELS[@]} sentinels fire on ${DEDUPE_COMMIT}^)"
  else
    [ "$pasted" -gt 0 ] && echo "  ($pasted pasted-back block(s). Fix: cut it back to the stub - CONVENTIONS.md -> 'Shared lane preamble'. Owner: modding.)"
    [ "$dead" -gt 0 ] && echo "  ($dead dead sentinel(s): the check cannot see those blocks until the phrase is repaired)"
  fi
else
  echo "  ($BOARD_DIR/commands not found under $ROOT - check SKIPPED, which is NOT clean)"
fi

# --- 6. DELTA SCOPE --------------------------------------------------------
echo
echo "--- 6. repos with claim-bearing changes since $SINCE ---"
for d in */; do
  [ -d "$d/.git" ] || continue
  n=$(git -C "$d" log --since="$SINCE" --name-only --pretty=format: 2>/dev/null |
      grep -Ec 'ENGINE-DOSSIER\.md|topics/.*\.md|inbox/.*\.md|STATUS\.md' )
  [ "$n" -gt 0 ] && printf "  %-46s %3d\n" "${d%/}" "$n"
done

echo
# --- 7. GATE BLOCKS --------------------------------------------------------
# The OPEN block records what each remaining step REQUIRES (CONVENTIONS.md ->
# "The OPEN block"): every project file carries exactly one dated block, every
# row is tagged PD/USER/FLAT/VR, and no block is older than its own file's
# newest log entry. A stale block is a session that logged work without
# re-auditing what is left; a missing one makes /gates understate.
#
# DELEGATED to gate-scan.sh rather than re-implemented here. Two parsers for one
# grammar drift, and the drift is silent - the sweep would call a file malformed
# that the board renders happily, or pass one the board gets wrong. One parser,
# three consumers (/gates, /gs, the watcher), no drift by construction.
#
# Fixes here belong in gate-scan.sh, never in a second copy of the rules.
echo
echo "--- 7. status/ OPEN gate blocks (missing, malformed or stale) ---"
GATE_SCAN="$SCRIPT_DIR/gate-scan.sh"
if [ -f "$GATE_SCAN" ]; then
  bash "$GATE_SCAN" --check "$ROOT/$BOARD_DIR" 2>&1 | sed 's/^/  /'
else
  echo "  (gate-scan.sh not found at $GATE_SCAN - check SKIPPED, which is NOT clean)"
fi

# --- 8. LANE ATTRIBUTION ---------------------------------------------------
# Four concurrent-lane runs reported "no file was written by two different lanes"
# and on three of them that was INFERRED from commit subjects. On 2026-09-07 the
# inference failed: two /lm sessions shared a machine, CONVENTIONS.md took two
# commits, and nothing in git distinguishes two sessions of one lane - author and
# committer are identical everywhere, and a subject line is prose.
#
# CONVENTIONS.md -> "Every commit says which lane wrote it" now asks every lane to
# end each commit with `Lane: <command> <project>`. This check does two things:
# reports how much of the window actually carries it (it starts near zero and
# should climb), and, for files touched more than once, names any that were
# written by DIFFERENT lanes - which is the estate's central safety claim, stated
# as a measurement instead of an argument.
#
# Files with no trailer on one side are counted as UNATTRIBUTED, not as clean. A
# check that silently treats missing evidence as a pass is the failure mode this
# whole command exists to avoid.
echo
echo "--- 8. lane attribution of commits since $SINCE ---"
tot8=0; tagged8=0; crosslane=""; unattr=0
for d in */; do
  [ -d "$d/.git" ] || continue
  r="${d%/}"
  # one line per commit: <sha> <TAB> <lane or "?">
  while IFS= read -r sha; do
    [ -z "$sha" ] && continue
    tot8=$((tot8+1))
    lane=$(git -C "$r" log -1 --format=%B "$sha" 2>/dev/null |
           grep -oiE '^Lane:[[:space:]]*.*' | head -1 | sed 's/^[Ll]ane:[[:space:]]*//')
    [ -n "$lane" ] && tagged8=$((tagged8+1))
    # --name-status, not --name-only: an inbox drop is ADDED by one lane and
    # DELETED by another BY DESIGN (create-only + drain), so the status letter is
    # what separates the estate's own protocol from a real cross-lane write.
    while IFS= read -r fl; do
      [ -z "$fl" ] && continue
      st=${fl%%	*}; pth=${fl#*	}
      [ -z "$pth" ] && continue
      printf '%s	%s	%s
' "$r/$pth" "${lane:-?}" "${st%%[0-9]*}"
    done < <(git -C "$r" show --name-status --format= "$sha" 2>/dev/null)
  done < <(git -C "$r" log --since="$SINCE" --format=%H 2>/dev/null)
done > "$TMPF8" 2>/dev/null
# group by file; a file written under two DIFFERENT non-"?" lanes is the finding
while IFS= read -r f; do
  lanes=$(awk -F'	' -v F="$f" '$1==F && $2!="?" {print $2}' "$TMPF8" | sort -u)
  n=$(printf '%s
' "$lanes" | grep -c . )
  anyq=$(awk -F'	' -v F="$f" '$1==F && $2=="?" {print}' "$TMPF8" | head -1)
  # An inbox path touched by two lanes is the create-only protocol working: the
  # author ADDs, the owner DELETEs when draining. Only a MODIFY by a second lane
  # breaks the rule, so that is the only inbox case worth reporting. Found on
  # check 8's first real firing: /gr added a drop at
  # 17:30, /pd drained it at 17:46, and the check called the estate's own
  # designed workflow a cross-lane write. Pinned by the fixture.
  case "$f" in
    */inbox/*|inbox/*)
      if ! awk -F'	' -v F="$f" '$1==F && $3=="M" {found=1} END{exit !found}' "$TMPF8"; then
        n=1
      fi
      ;;
  esac
  if [ "$n" -gt 1 ]; then
    crosslane="$crosslane  $f
$(printf '%s
' "$lanes" | sed 's/^/      /')
"
  elif [ -n "$anyq" ]; then
    unattr=$((unattr+1))
  fi
done < <(awk -F'	' '{print $1}' "$TMPF8" | sort | uniq -d)
if [ "$tot8" -eq 0 ]; then
  echo "  (no commits in the window)"
else
  pct=$(( tagged8 * 100 / tot8 ))
  echo "  trailer coverage: $tagged8 of $tot8 commits carry a Lane: line (${pct}%)"
  if [ -n "$crosslane" ]; then
    echo "  ⚠️ FILES WRITTEN BY MORE THAN ONE LANE:"
    printf '%s' "$crosslane"
  else
    echo "  no file was written by two DIFFERENT tagged lanes"
  fi
  [ "$unattr" -gt 0 ] && echo "  $unattr multi-touch file(s) UNATTRIBUTED (a commit lacked the trailer) - not a pass"
fi
rm -f "$TMPF8"

echo "=== scan complete - READ ONLY, nothing was modified ==="
