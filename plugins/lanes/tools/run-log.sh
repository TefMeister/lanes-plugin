#!/usr/bin/env bash
# run-log.sh -- count the working-pattern runs, from git, without anyone typing a row.
#
# WHY THIS EXISTS
#   docs/RELEASE-CHECKLIST.md asks for 50 CLEAN runs of /pd + /lm before this goes
#   public, and that file's own warning is that "counts can be reached while the thing
#   is still breaking". A hundred rows written by hand would drift into assertion.
#   Everything needed to count them honestly is already in git: the claim commits say
#   who held what and when, and the Lane: trailers say who wrote which file. So the
#   count is HARVESTED -- anyone can re-run this and get the same number.
#
# WHAT A RUN IS
#   A window where a /pd claim and an /lm claim on the SAME MACHINE overlap in time,
#   on DIFFERENT projects. (0.4.0: two sessions on ONE project is no longer a shape --
#   the tandem seat was retired -- so a same-project overlap is listed as a collision
#   to review and never counted.)
#
# WHAT "CLEAN" MEANS
#   Zero files written by BOTH lanes inside the window. The 2026-09-05 collision was
#   exactly this and nothing else -- git was perfect throughout, both edits rebased
#   cleanly, and the later silently undid the earlier one's fix. Git cannot see that.
#   This can.
#
# --reader [--since YYYY-MM-DD]   (0.4.0)
#   The other count the checklist wants: clean /lm runs WITH the reader. Since 0.4.0
#   every /lm runs one background reader, and hooks/reader-guard.py appends a line to
#   ~/.claude/lanes-reader-refusals.log each time it refuses that reader a write to
#   <board>/status/*.md. So an /lm claim window is CLEAN when no refusal falls inside
#   it. Honest limit: the refusal log is LOCAL to the machine that ran the session, so
#   run this on that machine, and a window with no log at all is "clean as far as this
#   machine knows", which the output says.
#
#   The claim log is excluded: lane-claim.sh writes it automatically on behalf of both
#   lanes, so it is co-authored by construction and means nothing.
#
#   DEFAULT --since (fault 10, fixed): the original bug was a bare DATE ("2026-09-10"),
#   which still counted two sessions from earlier that same day as reader runs, because
#   the reader actually shipped at 15:35:09 that afternoon (commit f0c6a4e) -- a whole
#   day of granularity hid a 15-hour gap. Rather than hand-type a second guess, this
#   reads the exact commit TIMESTAMP that first added hooks/reader-guard.py, straight
#   from THIS repo's own git history. That only works from a working-tree checkout; a
#   plugin installed from the marketplace is a plain versioned folder with no .git
#   (checked 2026-09-15: ~/.claude/plugins/cache/*/lanes/<version>/ has none). For that
#   case only, it falls back to tools/reader-since.txt -- one ISO timestamp, committed
#   once, alongside this script, touched again only if the reader is ever rebuilt from
#   scratch (a new epoch), never on an ordinary version bump. Either source is named in
#   the report, so nobody has to take the number on faith.
#
# HONEST LIMIT, STATED RATHER THAN HIDDEN
#   A run is only visible here if both lanes took claims and their commits carry Lane:
#   trailers. Runs from before those habits are invisible, by design: a run nobody can
#   re-derive from git is not evidence. Trailer coverage is printed so the reader can
#   judge how much of the estate this actually saw.
#
# READ ONLY. Never fetches, never writes, never checks anything out.
set -uo pipefail

CLAIM_LOG="lane-claims.md"

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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

BOARD=""; ROOT=""; VERBOSE=0; MIN_MINS=5; READER=0; SINCE=""; SINCE_SRC=""
while [ $# -gt 0 ]; do
  case "$1" in
    --reader)     READER=1; shift ;;
    --since)      SINCE="${2:-}"; SINCE_SRC="--since"; shift 2 ;;
    --root)       ROOT="${2:-}"; shift 2 ;;
    --min-mins)   MIN_MINS="${2:-5}"; shift 2 ;;
    --verbose|-v) VERBOSE=1; shift ;;
    -h|--help)    sed -n '2,54p' "$0"; exit 0 ;;
    -*)           echo "run-log: unknown option $1" >&2; exit 2 ;;
    *)            BOARD="$1"; shift ;;
  esac
done
case "$MIN_MINS" in ''|*[!0-9]*) echo "run-log: --min-mins wants a whole number" >&2; exit 2 ;; esac

BOARD="${BOARD:-${LANES_BOARD:-$(read_conf board)}}"
if [ -z "$BOARD" ] || [ ! -d "$BOARD/.git" ]; then
  echo "run-log: no board repo found. Pass one, set \$LANES_BOARD, or write" >&2
  echo "         board = /path/to/your/board-repo   into ~/.claude/lanes.conf." >&2
  exit 2
fi
if [ -z "$ROOT" ]; then
  ROOT="${LANES_ROOT:-$(read_conf root)}"
  [ -n "$ROOT" ] || ROOT="$(dirname "$BOARD")"
fi
[ -d "$ROOT" ] || { echo "run-log: repo root $ROOT does not exist." >&2; exit 2; }

REF=origin/main
git -C "$BOARD" rev-parse --verify -q "$REF" >/dev/null 2>&1 || REF=HEAD

TMP=$(mktemp -d 2>/dev/null || echo "${TMPDIR:-/tmp}/run-log.$$")
mkdir -p "$TMP"
trap 'rm -rf "$TMP"' EXIT

# ---- 1. claim events -> epoch, lane, action, project, host ------------------
git -C "$BOARD" log "$REF" --grep='^claim: ' --pretty=$'%at\t%s' 2>/dev/null | sort -n |
awk -F'\t' '
{
  t=$1; s=$2
  lane = (index(s,"/pd")>0) ? "/pd" : ((index(s,"/lm")>0) ? "/lm" : "")
  if (lane=="") next
  if      (index(s,"riding tandem on")>0)       { act="take";    sub(/.*riding tandem on /,"",s) }
  else if (index(s,"left the tandem seat on")>0){ act="release"; sub(/.*left the tandem seat on /,"",s) }
  else if (index(s," live on ")>0)              { act="take";    sub(/.* live on /,"",s) }
  else if (index(s," released ")>0)             { act="release"; sub(/.* released /,"",s) }
  else next
  proj=s; sub(/ \(.*/,"",proj)
  host=s; sub(/^[^(]*\(/,"",host); sub(/ .*/,"",host)
  if (proj!="") print t"\t"lane"\t"act"\t"proj"\t"host
}' > "$TMP/events"

if [ ! -s "$TMP/events" ]; then
  echo "run-log: no claim commits on $REF - nothing to count yet."
  exit 0
fi

# ---- 2. take/release -> intervals ------------------------------------------
# An unreleased claim is capped at one hour rather than left open: a session that
# never released is a session we cannot vouch for, and a huge window would swallow
# every other run on that machine and score them all as one.
awk -F'\t' '
{
  key=$2 "|" $4 "|" $5
  if ($3=="take") {
    if (key in open) print open[key] "\t" ($1<open[key]+3600?$1:open[key]+3600) "\t" meta[key]
    open[key]=$1; meta[key]=$2 "\t" $4 "\t" $5
  } else if (key in open) {
    print open[key] "\t" $1 "\t" meta[key]; delete open[key]
  }
}
END { for (k in open) print open[k] "\t" (open[k]+3600) "\t" meta[k] }' "$TMP/events" | sort -n > "$TMP/intervals"

# ---- 2b. --reader: clean /lm windows with the reader (0.4.0) ----------------
if [ "$READER" = 1 ]; then
  # ⚠️ ORDER REVERSED 2026-09-18. The recorded file comes FIRST and git is the fallback, not the
  # other way round. When the reader shipped is a historical fact; `reader-since.txt` is the record
  # of it, and git was only ever the place that record was read from once.
  #
  # Why it matters: asking git "when was hooks/reader-guard.py added" answers about THIS repo. In a
  # repo re-created from scratch — which is a live option, because publishing a repo publishes its
  # whole history and this one's carried personal data — every file looks added on day one. git
  # would answer confidently with that date, the fallback would never fire, and the reader count
  # would silently drop to only the runs since the new repo was made. **A count that resets itself
  # when you tidy the repo is worse than no count**, because it resets at exactly the moment you are
  # trying to prove the thing is ready.
  if [ -z "$SINCE" ] && [ -f "$SCRIPT_DIR/reader-since.txt" ]; then
    SINCE=$(head -1 "$SCRIPT_DIR/reader-since.txt" | tr -d '[:space:]')
    SINCE_SRC="tools/reader-since.txt (the recorded date the reader shipped)"
  fi
  if [ -z "$SINCE" ]; then
    SINCE=$(git -C "$PLUGIN_ROOT" log --diff-filter=A --format=%ad --date=iso-strict -- hooks/reader-guard.py 2>/dev/null | tail -1)
    SINCE_SRC="this repo's own git history (commit that added hooks/reader-guard.py) -- no reader-since.txt found"
  fi
  if [ -z "$SINCE" ]; then
    echo "run-log: cannot tell when the reader shipped -- no git history here and no" >&2
    echo "         tools/reader-since.txt. Pass --since YYYY-MM-DD." >&2
    exit 2
  fi
  RLOG="${LANES_READER_LOG:-$HOME/.claude/lanes-reader-refusals.log}"
  since_s=$(date -d "$SINCE" +%s 2>/dev/null || echo 0)
  printf '=== /lm RUNS WITH THE READER - harvested from %s, refusals from %s ===\n' "$REF" "$RLOG"
  printf '(reader shipped %s, from %s)\n\n' "$SINCE" "$SINCE_SRC"
  printf '%-17s %5s  %-30s %-18s %s\n' "WHEN" "MINS" "PROJECT" "HOST" "VERDICT"
  printf -- '-%.0s' $(seq 1 90); printf '\n'
  clean_r=0; review_r=0; n_r=0
  while IFS=$'\t' read -r a b lane proj host; do
    [ "$lane" = "/lm" ] || continue
    [ "$a" -ge "$since_s" ] || continue
    n_r=$((n_r+1))
    hits=0
    if [ -f "$RLOG" ]; then
      # column 1 of the refusal log is an ISO timestamp; count those inside the window
      hits=$(awk -F'\t' -v a="$a" -v b="$b" '
        { cmd = "date -d \"" $1 "\" +%s 2>/dev/null"; t = ""; cmd | getline t; close(cmd)
          if (t != "" && t+0 >= a && t+0 <= b) n++ }
        END { print n+0 }' "$RLOG")
    fi
    if [ "$hits" = 0 ]; then verdict="CLEAN"; clean_r=$((clean_r+1))
    else verdict="REVIEW - $hits refusal(s): the reader tried to write the board"; review_r=$((review_r+1)); fi
    printf '%-17s %5s  %-30s %-18s %s\n' "$(date -d "@$a" '+%Y-%m-%d %H:%M' 2>/dev/null)" "$(( (b - a) / 60 ))" "$proj" "$host" "$verdict"
  done < "$TMP/intervals"
  printf '\n=== COUNT ===\n'
  printf '  A1r /lm runs with the reader since %s   %3d / 20 clean   %d need review   (%d windows)\n' "$SINCE" "$clean_r" "$review_r" "$n_r"
  [ -f "$RLOG" ] || printf 'No refusal log on this machine: every window above is clean AS FAR AS THIS MACHINE KNOWS.\nRun this where the /lm sessions ran.\n'
  printf 'A window is an /lm claim window (unreleased ones capped at one hour). A refusal is the\nguard WORKING, but it is evidence the reader tried, so the run is listed for review.\n'
  exit 0
fi

# ---- 3. overlaps: one /pd interval against one /lm interval, same machine ---
awk -F'\t' -v minsec="$((MIN_MINS * 60))" '
{ n++; s[n]=$1; e[n]=$2; lane[n]=$3; proj[n]=$4; host[n]=$5 }
END {
  for (i=1;i<=n;i++) {
    if (lane[i]!="/pd") continue
    for (j=1;j<=n;j++) {
      if (lane[j]!="/lm" || host[i]!=host[j]) continue
      a = (s[i]>s[j]) ? s[i] : s[j]
      b = (e[i]<e[j]) ? e[i] : e[j]
      # A brief overlap is a handover, not a run. Counting it would inflate the
      # total with windows too short for either lane to have done anything.
      if (b - a < minsec) continue
      shape = (proj[i]==proj[j]) ? "SAME-PROJ" : "SEPARATE"
      print a "\t" b "\t" shape "\t" proj[i] "\t" proj[j] "\t" host[i]
    }
  }
}' "$TMP/intervals" | sort -n -u > "$TMP/runs"

if [ ! -s "$TMP/runs" ]; then
  echo "run-log: claim commits exist, but no /pd window overlaps an /lm window yet."
  exit 0
fi

EARLIEST=$(head -1 "$TMP/runs" | cut -f1)

# ---- 4. every lane-attributed file write, once per repo ---------------------
# One pass per repo rather than one per run: 22 git logs instead of hundreds.
: > "$TMP/writes"
REPO_N=0; TRAILERED=0; TOTAL=0
for r in "$ROOT"/*/; do
  [ -d "$r/.git" ] || continue
  REPO_N=$((REPO_N + 1))
  name=$(basename "$r")
  counts=$(git -C "$r" log --all --since="@$EARLIEST" \
             --pretty=$'\x01%at\t%(trailers:key=Lane,valueonly,separator=%x2C )' --name-only 2>/dev/null |
    awk -v repo="$name" -v out="$TMP/writes" '
      BEGIN { RS="\x01"; tot=0; tr=0 }
      NF {
        split($0, part, "\n")
        split(part[1], head, "\t")
        t=head[1]; lanes=(2 in head)?head[2]:""
        tot++
        if (lanes=="") next
        tr++
        lane = (index(lanes,"/pd")>0) ? "/pd" : ((index(lanes,"/lm")>0) ? "/lm" : "")
        if (lane=="") next
        for (i=2; i<=length(part); i++)
          if (part[i] != "") print t "\t" lane "\t" repo "/" part[i] >> out
      }
      END { print tot "\t" tr }')
  TOTAL=$((TOTAL + $(printf '%s' "$counts" | cut -f1)))
  TRAILERED=$((TRAILERED + $(printf '%s' "$counts" | cut -f2)))
done

# ---- 5. score each run ------------------------------------------------------
printf '=== WORKING-PATTERN RUNS - harvested from %s, read only ===\n\n' "$REF"
printf '%-17s %-9s %5s  %-42s %s\n' "WHEN" "SHAPE" "MINS" "PROJECT(S)" "VERDICT"
printf -- '-%.0s' $(seq 1 100); printf '\n'

clean_t=0; clean_s=0; review_t=0; review_s=0; DETAIL=""
while IFS=$'\t' read -r a b shape p1 p2 host; do
  [ -n "${a:-}" ] || continue
  both=$(awk -F'\t' -v a="$a" -v b="$b" -v skip="$CLAIM_LOG" '
    $1>=a && $1<=b && index($3,skip)==0 { seen[$3] = seen[$3] $2 }
    END { for (f in seen) if (index(seen[f],"/pd")>0 && index(seen[f],"/lm")>0) print f }' "$TMP/writes" | sort)

  if [ "$shape" = "SAME-PROJ" ]; then
    # Two sessions on one job. Not a shape since 0.4.0 - listed, never counted.
    verdict="NOT COUNTED - two sessions on one job (pre-0.4.0 tandem, or a forced claim)"
    review_t=$((review_t+1))
  elif [ -z "$both" ]; then
    verdict="CLEAN"
    clean_s=$((clean_s+1))
  else
    verdict="REVIEW - $(printf '%s\n' "$both" | wc -l | tr -d ' ') file(s) written by both"
    review_s=$((review_s+1))
    DETAIL="$DETAIL  $(date -d "@$a" '+%Y-%m-%d %H:%M' 2>/dev/null) $shape ${p1}:"$'\n'"$(printf '%s\n' "$both" | sed 's/^/      /')"$'\n'
  fi

  if [ "$shape" = "SAME-PROJ" ]; then projs="$p1"; else projs="$p1 + $p2"; fi
  printf '%-17s %-9s %5s  %-42s %s\n' \
    "$(date -d "@$a" '+%Y-%m-%d %H:%M' 2>/dev/null)" "$shape" "$(( (b - a) / 60 ))" "$projs" "$verdict"
done < "$TMP/runs"

printf '\n'
if [ -n "$DETAIL" ]; then
  if [ "$VERBOSE" = 1 ]; then
    printf -- '--- files written by BOTH lanes (the claim log is excluded) ---\n'
    printf '%s\n' "$DETAIL"
  else
    printf -- '(re-run with --verbose to see which files the REVIEW runs share)\n\n'
  fi
fi

printf '=== COUNT ===\n'
printf '  A1  SEPARATE (different projects) %3d / 50 clean   %d need review\n' "$clean_s" "$review_s"
[ "$review_t" -gt 0 ] && printf '  (%d same-project window(s) listed above and NOT counted - the seat was retired in 0.4.0)\n' "$review_t"
printf '  A1r (clean /lm runs with the reader): run with --reader\n\n'

pct=0; [ "$TOTAL" -gt 0 ] && pct=$(( TRAILERED * 100 / TOTAL ))
printf 'Evidence base: %d repos, %d of %d commits carry a Lane: trailer (%d%%).\n' \
  "$REPO_N" "$TRAILERED" "$TOTAL" "$pct"
printf 'A run counts only if the two lanes overlapped for at least %d minutes.\n' "$MIN_MINS"
if [ "$pct" -lt 90 ]; then
  printf 'WARNING: below 90%%. A file written by an unattributed commit is invisible to\n'
  printf '         the both-lanes test, so a REVIEW run can be scored CLEAN. Treat the\n'
  printf '         count as an UPPER bound until coverage is higher.\n'
fi
printf 'Runs from before the claim protocol are not counted: a run nobody can\n'
printf 're-derive from git is not evidence.\n'
