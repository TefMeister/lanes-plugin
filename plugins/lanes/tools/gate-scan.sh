#!/usr/bin/env bash
# gate-scan.sh - parse the OPEN blocks out of <board>/status/*.md and
# either render the gate board (default) or report violations (--check).
#
# WHY IT READS origin/main AND NOT THE WORKING TREE
#   Every session type has its own clone root (CONVENTIONS.md, 2026-09-01)
#   because `git pull` rewrites a shared working tree. `git fetch` does not touch
#   the working tree at all, and `git show origin/main:<path>` reads the committed
#   blob rather than the checkout - so this is safe to run from ANY lane's root,
#   including the live modding one, and it reports GitHub's truth rather than this
#   disk's possibly-stale checkout. That staleness is the failure that produced the
#   retracted 2026-08-26 finding.
#
# WHY ONE SCRIPT SERVES BOTH /gates AND /gs
#   Two parsers for one grammar drift, and the drift is silent: the board would
#   show items the checker calls malformed, or pass a file the board renders
#   wrongly. One parser, two output modes, no drift by construction.
#
# NEVER WRITES. Reports only.
#
# Usage: gate-scan.sh [--check|--watch|--brief|--mine|--next] [--tag PD|USER|FLAT|VR-CLAUDE|VR-USER]
#                     [path-to-board]
#
#   --mine   only the work THIS machine can do (see machine-assignments.tsv)
#   --next   the single next task for this machine - one thing at a time
#   --tag    restrict --next to ONE gate, e.g. `--next --tag FLAT` for a bare /lm
#
# ---------------------------------------------------------------------------
# KNOWN LIMITATIONS - found repeatedly by /lm on 2026-09-08, recorded rather
# than patched, because four lanes depend on this script and an end-of-session
# change to it is not the place to find that out. Comments only; no behaviour
# has been altered.
# ---------------------------------------------------------------------------
#
# 1. [FIXED 2026-09-09 - `--tag` was added; kept for the reasoning]
#    `--next` IS LANE-AGNOSTIC, BUT ITS CALLERS ARE NOT.
#    It walks the tags in cheapest-first order (PD, USER, FLAT, VR-CLAUDE, VR-USER) and returns
#    whatever comes first. That is right for "what should this machine do next",
#    and wrong for /lm, whose own command file says a bare /lm "picks the next
#    [FLAT] game". So every bare /lm has to re-derive the FLAT pick by hand -
#    six times in one session on 2026-09-08, each by copying this script and
#    editing the tag loop. A `--tag FLAT` or `--lane lm|pd` flag would remove
#    the workaround entirely. The output line already knows the distinction: it
#    prints "-> run: /pd <proj>" for a PD row and "-> run: /lm <proj>" for FLAT.
#
# 2. ⚠️ THE CLAIM FILTER IS LOST SILENTLY IF THIS FILE IS RUN FROM A COPY.
#    CLAIM_TOOL is resolved as "$(dirname "$0")/lane-claim.sh" (see below), so a
#    copy of this script placed anywhere else finds no lane-claim.sh, reports NO
#    claims at all, and will happily recommend a game another session is holding
#    - with no SKIPPING line and no error to say the check did not happen. That
#    is exactly the failure mode --next's own comments warn about ("it picked
#    something else must never be mysterious"), inverted. Observed live on
#    2026-09-08: a copy recommended a project while a /pd held it, and only
#    copying lane-claim.sh alongside restored the SKIPPING line.
#    A fix would resolve CLAIM_TOOL relative to the repo path argument, or fail
#    loudly when lane-claim.sh is missing rather than treating it as "no claims".

set -uo pipefail

MODE=board
ONLY_TAG=""
while :; do
  case "${1:-}" in
    --check) MODE=check; shift ;;
    --watch) MODE=watch; shift ;;
    --brief) MODE=brief; shift ;;
    --mine)  MODE=mine;  shift ;;
    --next)  MODE=next;  shift ;;
    # --tag restricts --next to ONE gate (2026-09-09). See the note at the top of
    # the file: --next walks PD, USER, FLAT, VR-CLAUDE, VR-USER cheapest-first and returns the
    # first hit, which is right for "what should this machine do next" and wrong
    # for a bare /lm, whose own command file says it picks the next [FLAT] game.
    # Every bare /lm had to re-derive that by hand - six times in one session on
    # 2026-09-08, three more on 2026-09-09 - by copying this script and editing
    # the tag loop, which is exactly the copy that silently loses the claim
    # filter (limitation 2). One flag removes both problems.
    --tag)
      shift
      ONLY_TAG=$(printf '%s' "${1:-}" | tr '[:lower:]' '[:upper:]')
      case "$ONLY_TAG" in
        PD|USER|FLAT|VR-CLAUDE|VR-USER) ;;
        # Accept the board spelling too, so --tag "VR USER" does what it looks like.
        "VR CLAUDE") ONLY_TAG=VR-CLAUDE ;;
        "VR USER")   ONLY_TAG=VR-USER ;;
        *) echo "gate-scan: --tag takes one of PD, USER, FLAT, VR-CLAUDE, VR-USER (got '${1:-}')" >&2; exit 2 ;;
      esac
      shift ;;
    *) break ;;
  esac
done

# ---- where is the board? --------------------------------------------------
# Resolution order, most explicit first:
#   1. the path given as an argument
#   2. $LANES_BOARD
#   3. `board = <path>` in $LANES_CONFIG, ~/.claude/lanes.conf, or
#      ~/.config/lanes/lanes.conf
#   4. the current directory, if it is itself a board clone
# There are deliberately NO built-in path guesses. A guess that finds a stale
# clone reports this disk's past instead of the project's present, which is the
# single failure this script exists to avoid.
MEM="${1:-}"
[ -n "$MEM" ] || MEM="${LANES_BOARD:-}"
if [ -z "$MEM" ]; then
  for conf in "${LANES_CONFIG:-}" "$HOME/.claude/lanes.conf" "$HOME/.config/lanes/lanes.conf"; do
    [ -n "$conf" ] && [ -f "$conf" ] || continue
    MEM=$(sed -n 's/^[[:space:]]*board[[:space:]]*=[[:space:]]*//p' "$conf" | head -1 |
          sed 's/[[:space:]]*$//; s/^"//; s/"$//')
    [ -n "$MEM" ] && break
  done
fi
if [ -z "${MEM:-}" ] && [ -d "./status" ] && [ -d "./.git" ]; then MEM="."; fi
if [ -z "${MEM:-}" ] || [ ! -d "$MEM/status" ]; then
  echo "gate-scan: no board found. Pass its path, set \$LANES_BOARD, or write" >&2
  echo "             board = /path/to/board-repo" >&2
  echo "           into ~/.claude/lanes.conf. A board is a git clone with a status/ folder." >&2
  exit 2
fi

# fetch updates refs only - it cannot disturb another lane's uncommitted work.
FETCH_NOTE=""
git -C "$MEM" fetch -q origin 2>/dev/null || FETCH_NOTE="  (warning: fetch failed - reading last-known origin/main)"

REF=origin/main
git -C "$MEM" rev-parse --verify -q "$REF" >/dev/null 2>&1 || REF=HEAD

TODAY=$(date +%F)

ITEMS=$(mktemp); VIOL=$(mktemp); IDLE=$(mktemp); CUR=$(mktemp); CLAIMS=$(mktemp)
trap 'rm -f "$ITEMS" "$VIOL" "$IDLE" "$CUR" "$CLAIMS"' EXIT

# ---- which machine am I, and what is mine? --------------------------------
# Roles are labels you choose; machine-assignments.tsv maps each project to the
# role that owns it, and '*' is the catch-all. The shipped pair is HOME and DEV.
# Order: $GATE_ROLE (what the test fixture uses), then `role = <name>` in the
# config file, then DEV.
detect_role() {
  if [ -n "${GATE_ROLE:-}" ]; then echo "$GATE_ROLE"; return; fi
  local r="" conf
  for conf in "${LANES_CONFIG:-}" "$HOME/.claude/lanes.conf" "$HOME/.config/lanes/lanes.conf"; do
    [ -n "$conf" ] && [ -f "$conf" ] || continue
    r=$(sed -n 's/^[[:space:]]*role[[:space:]]*=[[:space:]]*//p' "$conf" | head -1 |
        sed 's/[[:space:]]*$//; s/^"//; s/"$//')
    [ -n "$r" ] && break
  done
  echo "${r:-DEV}"
}
ROLE="$(detect_role)"

# owner_of <project> -> HOME or DEV, from machine-assignments.tsv ('*' is the catch-all)
ASSIGN="$MEM/machine-assignments.tsv"
owner_of() {
  local proj="$1" role prefix fallback=DEV
  if [ ! -f "$ASSIGN" ]; then
    # Never fail silently here: with no assignments file EVERY project resolves to the fallback,
    # which on the home PC means "none of this is yours". Say so once, then answer.
    [ -n "${ASSIGN_WARNED:-}" ] || { echo "gate-scan: no machine-assignments.tsv in $MEM - treating every project as $fallback (pull that clone?)" >&2; ASSIGN_WARNED=1; }
    echo "$fallback"; return
  fi
  while IFS=$'	' read -r role prefix; do
    # This file is edited on Windows, so a CRLF copy is normal and must not silently break the
    # match. Without this, `prefix` carries a trailing CR, NO project matches, and the `*` row
    # fails too -- so every project fell back to DEV and `--mine` on the home PC reported that
    # its own two projects had no work. Found 2026-09-07.
    role="${role%$'\r'}"; prefix="${prefix%$'\r'}"
    case "$role" in ''|'#'*) continue ;; esac
    [ -n "${prefix:-}" ] || continue
    if [ "$prefix" = "*" ]; then fallback="$role"; continue; fi
    [ "$prefix" = "$proj" ] && { echo "$role"; return; }
  done < "$ASSIGN"
  echo "$fallback"
}

# Is this row mine? BOTH hardware tags are ALWAYS the hardware machine's - only
# matter who owns the project.
row_is_mine() {
  local tag="$1" proj="$2"
  case "$tag" in VR-CLAUDE|VR-USER) [ "$ROLE" = "HOME" ]; return ;; esac
  [ "$(owner_of "$proj")" = "$ROLE" ]
}

# LIVE claims - "LIVE: /lm 2026-09-06 14:02 WORKSTATION" above a project's OPEN line means a
# same-lane session (/lm or /pd) is on that game right now. lane-claim.sh is the one
# parser for that grammar (added 2026-09-06 after the /pd-over-/lm collision of 09-05);
# this script only relays what it says, so the board and the guard can never disagree.
CLAIM_TOOL="${LANES_TOOLS:-$(cd "$(dirname "$0")" && pwd)}/lane-claim.sh"
# Fail loudly rather than quietly reporting "no claims". A missing claim filter is
# invisible in the output, and a board without it recommends work that another
# session is holding right now -- observed live 2026-09-08, from a stray copy of
# this script that had no lane-claim.sh beside it.
if [ ! -f "$CLAIM_TOOL" ]; then
  echo "gate-scan: lane-claim.sh is not beside this script ($CLAIM_TOOL)." >&2
  echo "           Without it the live-claim filter is silently OFF. Run the copy that" >&2
  echo "           ships alongside it, or set LANES_TOOLS to the folder holding both." >&2
  exit 2
fi
if [ -f "$CLAIM_TOOL" ]; then   # always true past the guard above; kept so this stays a
                                # minimal diff from the original the lanes depend on
  bash "$CLAIM_TOOL" list --no-fetch --repo "$MEM" 2>/dev/null | grep -E ' (FRESH|STALE|MALFORMED) ' > "$CLAIMS" || true
  grep -E ' MALFORMED ' "$CLAIMS" | awk '{printf "  %-28s malformed LIVE line - expected \"LIVE: /lane YYYY-MM-DD HH:MM machine\"\n", $1}' >> "$VIOL"
fi
claims_brief() {
  # "game-one   FRESH  /lm since 2026-09-06 14:02 on WORKSTATION (0h ago) - ..." -> one short phrase each
  awk '$2=="FRESH" {printf "%s (%s since %s on %s)  ", $1, $3, $6, $8}
       $2=="STALE" {printf "%s (%s STALE since %s %s on %s)  ", $1, $3, $5, $6, $8}
       $2=="MALFORMED" {printf "%s (MALFORMED)  ", $1}' "$CLAIMS"
}

git -C "$MEM" ls-tree --name-only "$REF" status/ |
  grep -E '\.md$' | grep -v '_headlines-archive\.md' |
while IFS= read -r f; do
  proj=$(basename "$f" .md)
  body=$(git -C "$MEM" show "$REF:$f" 2>/dev/null)

  # The date may carry a SAME-DAY SUFFIX - "OPEN (2026-09-03c):", "OPEN (2026-09-02, evening):".
  # Sessions kept writing those because a project can be updated several times in a day and the
  # bare date cannot say which; the scanner rejected them and silently dropped the whole project
  # from every count. That happened THREE times in one day, so the format was
  # widened to fit the practice rather than the practice
  # policed to fit the format. `odate` below takes the FIRST date on the line, so a suffix never
  # affected the staleness comparison. Still required: "OPEN (", a real YYYY-MM-DD, and "):".
  n_open=$(printf '%s\n' "$body" | grep -cE '^OPEN[[:space:]]*\([0-9]{4}-[0-9]{2}-[0-9]{2}[^)]*\):' || true)
  n_any=$(printf '%s\n' "$body" | grep -cE '^OPEN' || true)
  if [ "$n_open" -eq 0 ]; then
    if [ "$n_any" -gt 0 ]; then
      printf '  %-28s OPEN line present but not "OPEN (YYYY-MM-DD):"\n' "$proj" >> "$VIOL"
    else
      printf '  %-28s NO "OPEN (date):" BLOCK\n' "$proj" >> "$VIOL"
    fi
    continue
  fi
  if [ "$n_open" -gt 1 ]; then
    printf '  %-28s %s OPEN blocks (must be exactly one)\n' "$proj" "$n_open" >> "$VIOL"
  fi

  hit=$(printf '%s\n' "$body" | grep -nE '^OPEN[[:space:]]*\([0-9]{4}-[0-9]{2}-[0-9]{2}[^)]*\):' | head -1)
  ln=${hit%%:*}
  odate=$(printf '%s' "$hit" | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}' | head -1)

  rows=0
  if printf '%s' "$hit" | grep -qE ':[[:space:]]*none[[:space:]]*$'; then
    printf '%s\n' "$proj" >> "$IDLE"
  else
    while IFS= read -r row; do
      case "$row" in
        "  ["*) ;;
        *) break ;;
      esac
      raw=${row#"  ["}
      tag=${raw%%]*}
      item=${raw#*]}
      # Trim ALL leading whitespace, not one space. Rows are commonly padded to
      # align the text under a mixed-width tag column ("[PD]   x" vs "[FLAT] x"),
      # and stripping a single space left the padding inside the item text - which
      # showed up as a ragged board and would have been stored in the snapshot the
      # --watch diff compares against.
      item="${item#"${item%%[![:space:]]*}"}"
      # TWO-WORD TAGS ARE MATCHED FIRST, BEFORE THE SPACE-SPLIT BELOW.
      # `base=${tag%% *}` exists because a row may carry a qualifier - [PD @home] -
      # and only the first word is the tag. When [VR] was split into [VR CLAUDE] and
      # [VR USER], that same line would have reduced BOTH to "VR": the two tags would
      # have merged back into one, silently, and the board would have looked healthy
      # while telling a session it could work alone on rows that need a person there.
      upper=$(printf '%s' "$tag" | tr '[:lower:]' '[:upper:]')
      case "$upper" in
        "VR CLAUDE"|"VR CLAUDE "*) base=VR-CLAUDE ;;
        "VR USER"|"VR USER "*)     base=VR-USER ;;
        *) base=${tag%% *} ;;
      esac
      case "$base" in
        PD|USER|FLAT|VR-CLAUDE|VR-USER) ;;
        VR) printf '  %-28s [VR] alone is no longer a tag - use [VR CLAUDE] (hardware connected, nobody present) or [VR USER] (a person must be using it)\n' "$proj" >> "$VIOL"
           base=BAD ;;
        *) printf '  %-28s bad tag [%s] - must be PD, USER, FLAT, VR CLAUDE or VR USER\n' "$proj" "$base" >> "$VIOL"
           base=BAD ;;
      esac
      if [ -z "$item" ]; then
        printf '  %-28s a [%s] row has no text\n' "$proj" "$base" >> "$VIOL"
      fi
      printf '%s\t%s\t%s\n' "$base" "$proj" "$item" >> "$ITEMS"
      rows=$((rows+1))
    done < <(printf '%s\n' "$body" | tail -n +$((ln+1)))
    if [ "$rows" -eq 0 ]; then
      printf '  %-28s OPEN block has no rows (write ": none" if idle)\n' "$proj" >> "$VIOL"
    fi
  fi

  # Newest log entry, for the staleness check. Three things this has to get right,
  # and the first two were found by running it rather than by reading it:
  #  1. Skip the OPEN block's OWN rows (ln+1+rows), not just the OPEN line. A date
  #     inside a row is an expiry or a deadline the row is about - a "GitHub
  #     drops it around 2026-11-29" - not a log entry, and reading it as one flagged
  #     a block written the same minute as stale.
  #  2. Ignore dates in the FUTURE. A log entry cannot be dated later than today, so
  #     any such date is prose. Without this, one forward-looking date anywhere in a
  #     49 KB file would pin that project permanently stale, and a permanently-red
  #     check is one nobody reads.
  #  3. Take the max of what remains, not the first, since a status file may be ordered
  #     oldest-first while every other status file is newest-first.
  newest=$(printf '%s\n' "$body" | tail -n +$((ln+1+rows)) |
           grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}' | sort -r |
           awk -v t="$TODAY" '$0<=t { print; exit }')
  if [ -n "$newest" ] && [[ "$newest" > "$odate" ]]; then
    printf '  %-28s STALE: OPEN dated %s, newest log entry %s\n' "$proj" "$odate" "$newest" >> "$VIOL"
  fi
done

nviol=$(wc -l < "$VIOL" | tr -d ' ')

if [ "$MODE" = check ]; then
  echo "=== gate-scan --check   ref=$REF ==="
  [ -n "$FETCH_NOTE" ] && echo "$FETCH_NOTE"
  if [ -s "$CLAIMS" ]; then
    echo "  LIVE NOW (same-lane claims; a STALE one is a dead session, replace it on the next take):"
    sed 's/^/    /' "$CLAIMS"
  fi
  if [ "$nviol" -gt 0 ]; then
    sort "$VIOL"
    echo
    echo "  ($nviol violations)"
    exit 1
  fi
  echo "  (clean - every project has a current, well-formed OPEN block)"
  exit 0
fi

# --brief: counts only, for the SessionStart hook. The full board measured 13,388
# characters once the backfill landed - a few thousand tokens injected into EVERY
# session, in every project, most of it long FLAT rows nobody needs at that moment.
# What a session actually needs on opening is which mode to be in and whether the
# board can be trusted; the detail is one `/gates` away.
if [ "$MODE" = brief ]; then
  b_pd=$(awk -F'\t' '$1=="PD"' "$ITEMS" | wc -l | tr -d ' ')
  b_us=$(awk -F'\t' '$1=="USER"' "$ITEMS" | wc -l | tr -d ' ')
  b_fl=$(awk -F'\t' '$1=="FLAT"' "$ITEMS" | wc -l | tr -d ' ')
  b_vrc=$(awk -F'\t' '$1=="VR-CLAUDE"' "$ITEMS" | wc -l | tr -d ' ')
  b_vru=$(awk -F'\t' '$1=="VR-USER"' "$ITEMS" | wc -l | tr -d ' ')
  b_pdp=$(awk -F'\t' '$1=="PD" {print $2}' "$ITEMS" | sort -u | wc -l | tr -d ' ')
  echo "GATE BOARD (summary) - $REF, $(date '+%Y-%m-%d %H:%M'). Run /gates for the full list."
  echo "  PARALLEL DEVELOPMENT (nothing running)  : $b_pd items across $b_pdp projects"
  echo "  NEEDS THE USER, not the app             : $b_us"
  echo "  QUEUED FOR A RUN WITH THE APP UP        : $b_fl"
  echo "  HARDWARE, SESSION ALONE (just connect it): $b_vrc"
  echo "  HARDWARE, A PERSON MUST BE THERE        : $b_vru"
  [ -s "$IDLE" ] && echo "  IDLE                                    : $(tr '\n' ' ' < "$IDLE")"
  cb=$(claims_brief)
  [ -n "$cb" ] && echo "  LIVE NOW (same lane, do not /pd or /lm) : $cb"
  if [ "$b_pd" -eq 0 ] && [ "$nviol" -eq 0 ]; then
    echo "*** NO PARALLEL-DEVELOPMENT WORK LEFT ANYWHERE - THE NEXT STEP NEEDS THE APP RUNNING ***"
  fi
  if [ "$nviol" -gt 0 ]; then
    echo "  !! $nviol project(s) have a missing, malformed or stale OPEN block, so these counts UNDERSTATE:"
    sort "$VIOL"
  fi
  exit 0
fi

if [ "$MODE" = watch ]; then
  SNAP="$MEM/.gate-snapshot"
  sort "$ITEMS" > "$CUR"

  # A first run has nothing to diff against. Reporting every row as "new" here
  # would be the watcher's loudest possible output on the one occasion it knows
  # the least - and would train the user to ignore it.
  if [ ! -f "$SNAP" ]; then
    cp "$CUR" "$SNAP"
    echo "gate-watch: baseline established ($(wc -l < "$CUR" | tr -d ' ') rows). No history yet - nothing to report."
    exit 0
  fi

  added=$(comm -13 "$SNAP" "$CUR")
  removed=$(comm -23 "$SNAP" "$CUR")
  n_add=$(printf '%s' "$added" | grep -c . || true)
  n_rem=$(printf '%s' "$removed" | grep -c . || true)
  pd_now=$(awk -F'\t' '$1=="PD"' "$CUR" | wc -l | tr -d ' ')
  pd_was=$(awk -F'\t' '$1=="PD"' "$SNAP" | wc -l | tr -d ' ')
  cp "$CUR" "$SNAP"

  # Silence when nothing changed. A watcher that speaks every tick is noise, and
  # noise is how a watcher gets ignored on the one tick that mattered.
  if [ "$n_add" -eq 0 ] && [ "$n_rem" -eq 0 ]; then
    echo "gate-watch: no change ($pd_now PD items)"
    exit 0
  fi

  echo "GATE CHANGE - $(date '+%Y-%m-%d %H:%M'), from $REF"

  # 1. New PD work is the highest-value event: it means the hardware can be put down.
  new_pd=$(printf '%s\n' "$added" | awk -F'\t' '$1=="PD" {printf "  %-26s %s\n", $2, $3}')
  if [ -n "$new_pd" ]; then
    echo
    echo "*** NEW PARALLEL-DEVELOPMENT WORK IS AVAILABLE - NOTHING NEED BE RUNNING ***"
    printf '%s\n' "$new_pd"
  fi

  # 2. The estate running out of no-game work is the signal to launch something.
  if [ "$pd_now" -eq 0 ] && [ "$pd_was" -gt 0 ]; then
    echo
    echo "*** THE LAST PARALLEL-DEVELOPMENT ITEM IS GONE ***"
    echo "*** EVERY REMAINING STEP NEEDS THE APP RUNNING ***"
  fi

  other_add=$(printf '%s\n' "$added" | awk -F'\t' '$1!="PD" && NF {printf "  + [%s] %-24s %s\n", $1, $2, $3}')
  if [ -n "$other_add" ]; then
    echo
    echo "queued elsewhere:"
    printf '%s\n' "$other_add"
  fi

  if [ "$n_rem" -gt 0 ]; then
    echo
    echo "no longer open (done, or deferred back into the log):"
    printf '%s\n' "$removed" | awk -F'\t' 'NF {printf "  - [%s] %-24s %s\n", $1, $2, $3}'
  fi

  if [ "$nviol" -gt 0 ]; then
    echo
    echo "!! $nviol block(s) missing, malformed or stale - the counts above UNDERSTATE:"
    sort "$VIOL"
  fi
  exit 0
fi

# ---- --mine / --next ------------------------------------------------------
# Cheapest gate first, which is the same order the board already recommends in.
# On a machine without the hardware, VR is skipped entirely; elsewhere it is last.
mine_rows() {
  local tag proj text
  while IFS=$'	' read -r tag proj text; do
    [ -n "${tag:-}" ] || continue
    row_is_mine "$tag" "$proj" && printf '%s\t%s\t%s\n' "$tag" "$proj" "$text"
  done < "$ITEMS"
}

if [ "$MODE" = mine ] || [ "$MODE" = next ]; then
  MINE=$(mktemp); trap 'rm -f "$ITEMS" "$VIOL" "$IDLE" "$CUR" "$CLAIMS" "$MINE"' EXIT
  mine_rows > "$MINE"

  if [ "$MODE" = next ]; then
    # ---- SKIP WHAT THE OTHER SAME-LANE SESSION IS ON (2026-09-08) -----------
    # /pd and /lm are the SAME lane, so a game carrying a FRESH claim is not
    # available to EITHER of them. --next is a DECISION, not a listing: if it
    # recommended a claimed game, the caller would take that recommendation and
    # then be blocked by lane-claim.sh (or by the UserPromptSubmit hook) for
    # doing exactly what it was told. So filter here, and SAY what was filtered
    # -- "it picked something else" must never be mysterious, because the whole
    # point of auto-pick is that nobody is watching it choose.
    #
    # STALE claims are deliberately NOT skipped: a stale claim is a dead session,
    # and lane-claim.sh already lets the next taker replace it.
    SKIPPED=""
    if [ -s "$CLAIMS" ]; then
      FREE=$(mktemp)
      while IFS=$'\t' read -r tag proj text; do
        [ -n "${tag:-}" ] || continue
        if awk -v p="$proj" '$1==p && $2=="FRESH" {f=1} END{exit !f}' "$CLAIMS"; then
          case " $SKIPPED " in *" $proj "*) ;; *) SKIPPED="$SKIPPED $proj" ;; esac
          continue
        fi
        printf '%s\t%s\t%s\n' "$tag" "$proj" "$text"
      done < "$MINE" > "$FREE"
      mv "$FREE" "$MINE"
    fi
    if [ -n "$SKIPPED" ]; then
      for sp in $SKIPPED; do
        who=$(awk -v p="$sp" '$1==p && $2=="FRESH" {print $3" since "$5" "$6" on "$8}' "$CLAIMS")
        echo "SKIPPING $sp - the same lane is on it now ($who)"
      done
      echo
    fi

    # One task. Starred rows first inside a tag - the boards use a star for "this is
    # the one that matters", so honour it rather than picking alphabetically.
    for t in PD USER FLAT VR-CLAUDE VR-USER; do
      [ -n "$ONLY_TAG" ] && [ "$t" != "$ONLY_TAG" ] && continue
      case "$t" in VR-CLAUDE|VR-USER) [ "$ROLE" != HOME ] && continue ;; esac
      line=$(awk -F'	' -v t="$t" '$1==t && $3 ~ /⭐/' "$MINE" | head -1)
      [ -z "$line" ] && line=$(awk -F'	' -v t="$t" '$1==t' "$MINE" | head -1)
      if [ -n "$line" ]; then
        tag=$(printf '%s' "$line" | cut -f1)
        proj=$(printf '%s' "$line" | cut -f2)
        text=$(printf '%s' "$line" | cut -f3)
        echo "NEXT on $ROLE  [$tag]  $proj"
        echo
        printf '%s\n' "$text" | fold -s -w 100 | sed 's/^/  /'
        echo
        case "$t" in
          PD)   echo "  -> run:  /pd $proj      (nothing needs to be running)" ;;
          USER) echo "  -> this one needs YOU, not the app." ;;
          FLAT) echo "  -> run:  /lm $proj      (needs the app running)" ;;
          VR-CLAUDE) echo "  -> run:  /lm $proj      (hardware connected; nobody needs to be there)" ;;
          VR-USER)   echo "  -> this one needs A PERSON using the hardware." ;;
        esac
        remaining=$(wc -l < "$MINE" | tr -d ' ')
        echo "  ($remaining item(s) queued for this machine in total)"
        exit 0
      fi
    done
    if [ -n "$SKIPPED" ]; then
      echo "NOTHING QUEUED FOR $ROLE${ONLY_TAG:+ AT [$ONLY_TAG]} THAT IS NOT ALREADY CLAIMED."
      echo "  Everything left for this machine${ONLY_TAG:+ at [$ONLY_TAG]} is on a job the same lane is working now."
      echo "  Wait for it to release, or pick a different lane (/gr, /sr, /gs all run alongside)."
      exit 0
    fi
    echo "NOTHING QUEUED FOR $ROLE${ONLY_TAG:+ AT [$ONLY_TAG]}."
    [ -n "$ONLY_TAG" ] && echo "  (only [$ONLY_TAG] was considered - drop --tag to see the cheapest row of any gate.)"
    other=$(wc -l < "$ITEMS" | tr -d ' ')
    mineN=$(wc -l < "$MINE" | tr -d ' ')
    echo "  The board holds $other item(s); $mineN are this machine's."
    # 2026-09-18: this used to add, when ROLE=DEV, "Anything left is the home PC's (its two
    # projects, or [VR] work)" -- the author's own two-machine arrangement, printed to every user
    # of the plugin. Nobody else has a home PC, two projects, or that split. Say what is true of
    # any board instead.
    [ "$other" -gt "$mineN" ] && echo "  The other $((other - mineN)) are assigned to another machine, or need a gate this one cannot meet."
    exit 0
  fi

  echo "GATE BOARD - $REF, $(date '+%Y-%m-%d %H:%M')  -  MINE ($ROLE)"
  [ -n "$FETCH_NOTE" ] && echo "$FETCH_NOTE"
  for t in PD USER FLAT VR-CLAUDE VR-USER; do
    case "$t" in VR-CLAUDE|VR-USER) [ "$ROLE" != HOME ] && continue ;; esac
    case "$t" in
      PD)   title="PARALLEL DEVELOPMENT - NOTHING RUNNING" ;;
      USER) title="NEEDS YOU, NOT THE APP" ;;
      FLAT) title="A RUN WITH THE APP UP" ;;
      VR-CLAUDE) title="HARDWARE CONNECTED - THE SESSION CAN DO IT ALONE" ;;
      VR-USER)   title="HARDWARE IN A PERSON'S HANDS - ONLY THEY CAN DO IT" ;;
    esac
    n=$(awk -F'	' -v t="$t" '$1==t' "$MINE" | wc -l | tr -d ' ')
    p=$(awk -F'	' -v t="$t" '$1==t {print $2}' "$MINE" | sort -u | wc -l | tr -d ' ')
    echo
    echo "=== $title - $n items, $p projects ==="
    if [ "$n" -eq 0 ]; then echo "  (none)"; continue; fi
    awk -F"\t" -v t="$t" '$1==t {printf "  %-26s %s\n", $2, $3}' "$MINE" | sort
  done
  echo
  notmine=$(( $(wc -l < "$ITEMS") - $(wc -l < "$MINE") ))
  echo "=== NOT THIS MACHINE - $notmine item(s) ==="
  echo "  Assigned elsewhere by machine-assignments.tsv, or hardware work that needs the other machine."
  exit 0
fi

section() {
  local t="$1" title="$2" n p
  n=$(awk -F'\t' -v t="$t" '$1==t' "$ITEMS" | wc -l | tr -d ' ')
  p=$(awk -F'\t' -v t="$t" '$1==t {print $2}' "$ITEMS" | sort -u | wc -l | tr -d ' ')
  echo
  echo "=== $title - $n items, $p projects ==="
  if [ "$n" -eq 0 ]; then echo "  (none)"; return; fi
  awk -F'\t' -v t="$t" '$1==t {printf "  %-26s %s\n", $2, $3}' "$ITEMS" | sort
}

echo "GATE BOARD - $REF, $(date '+%Y-%m-%d %H:%M')"
[ -n "$FETCH_NOTE" ] && echo "$FETCH_NOTE"
section PD   "PARALLEL DEVELOPMENT - NOTHING RUNNING"
section USER "NEEDS YOU, NOT THE APP"
section FLAT "A RUN WITH THE APP UP"
section VR-CLAUDE "HARDWARE CONNECTED - THE SESSION CAN DO IT ALONE"
section VR-USER   "HARDWARE IN A PERSON'S HANDS - ONLY THEY CAN DO IT"
echo
if [ -s "$IDLE" ]; then
  echo "=== IDLE - $(wc -l < "$IDLE" | tr -d ' ') projects ===  $(tr '\n' ' ' < "$IDLE")"
else
  echo "=== IDLE - none ==="
fi

if [ -s "$CLAIMS" ]; then
  echo
  echo "=== LIVE NOW - a same-lane session (/lm or /pd) holds these; do not start another on them ==="
  sed 's/^/  /' "$CLAIMS"
fi

pd_n=$(awk -F'\t' '$1=="PD"' "$ITEMS" | wc -l | tr -d ' ')
if [ "$pd_n" -eq 0 ] && [ "$nviol" -eq 0 ]; then
  echo
  echo "*** NO PARALLEL-DEVELOPMENT WORK LEFT ANYWHERE ***"
  echo "*** THE NEXT STEP ON EVERY PROJECT NEEDS THE APP RUNNING ***"
fi

if [ "$nviol" -gt 0 ]; then
  echo
  echo "!! THE BOARD IS INCOMPLETE - $nviol problems, so the counts above are a FLOOR, not the truth:"
  sort "$VIOL"
fi
