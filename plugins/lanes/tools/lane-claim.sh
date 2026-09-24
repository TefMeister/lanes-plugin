#!/usr/bin/env bash
# lane-claim.sh - the per-job LIVE claim that stops /pd and /lm colliding on one job.
#
# 0.4.0 (2026-09-10): the tandem seat is gone. Pairing now happens INSIDE one /lm
# session (a background reader agent), so there is no second session to seat. One
# claim kind, LIVE, and nothing else.
#
# WHY THIS EXISTS (2026-09-06)
#   /pd and /lm are the SAME lane. Until today the only thing keeping them off one game
#   was a behavioural rule ("skip a game whose status file was touched today"), and naming
#   the game on the /pd command line overrode it. On one occasion a /pd named a project,
#   saw an /lm commit from 27 minutes earlier, judged that session finished, and undid its
#   fix. Git was fine; the collision was semantic, so no git rule could catch it. A claim
#   that is WRITTEN at session start and CHECKED by a script (and by a prompt hook) is
#   the structural version of that rule: the check is the same for every session, and the
#   override has to be typed by the user ("force"), never inferred by the model.
#
# THE CLAIM
#   One line in <board>/status/<project>.md, directly above the "OPEN (date):" line:
#
#       LIVE: /lm 2026-09-06 14:02 WORKSTATION
#       LIVE: <lane> <YYYY-MM-DD> <HH:MM> <host>
#
#   Taken by the session at its start (one commit, one push - the push IS the claim, and a
#   rejected push means someone else got there first). Released by the same session in its
#   write-up. A claim older than MAX_AGE_H hours is STALE: the session that wrote it most
#   likely died, so it warns but does not block, and the next taker replaces it.
#
#   Why in the status file and not a lock file: the status file is already the one
#   per-project file every lane reads at session start, gate-scan.sh already parses it from
#   origin/main in every SessionStart, and it lives in git, so the claim is visible from
#   BOTH machines and the whole history of who held what is in the log.
#
# COMMANDS
#   lane-claim.sh check   <prefix>...              exit 1 if any FRESH claim exists
#   lane-claim.sh take    <lane> <prefix> [--force] write the claim, commit, push
#   lane-claim.sh release <lane> <prefix> [--force] remove this lane's claim, commit, push
#   lane-claim.sh list                              every claim on origin/main
#
#   Options anywhere: --repo <path-to-board-clone>   --max-age <hours>   --no-fetch
#   `check` and `list` read origin/main only (fetch, never pull) so they are safe from any
#   lane's root. `take` and `release` commit in the given clone's working tree, so call them
#   from YOUR OWN lane root, never another lane's.

set -uo pipefail

MAX_AGE_H="${LANE_CLAIM_MAX_AGE_H:-12}"
REPO=""
FORCE=0
DO_FETCH=1
ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --repo)     REPO="$2"; shift 2 ;;
    --max-age)  MAX_AGE_H="$2"; shift 2 ;;
    --force)    FORCE=1; shift ;;
    --no-fetch) DO_FETCH=0; shift ;;
    *)          ARGS+=("$1"); shift ;;
  esac
done
set -- "${ARGS[@]+"${ARGS[@]}"}"

CMD="${1:-}"; shift || true

# ---- where is the board? --------------------------------------------------
# Same resolution order as gate-scan.sh, and deliberately no built-in guesses:
#   --repo <path>, then $LANES_BOARD, then `board = <path>` in the config file,
#   then the current directory if it is itself a board clone.
if [ -z "$REPO" ]; then REPO="${LANES_BOARD:-}"; fi
if [ -z "$REPO" ]; then
  for conf in "${LANES_CONFIG:-}" "$HOME/.claude/lanes.conf" "$HOME/.config/lanes/lanes.conf"; do
    [ -n "$conf" ] && [ -f "$conf" ] || continue
    REPO=$(sed -n 's/^[[:space:]]*board[[:space:]]*=[[:space:]]*//p' "$conf" | head -1 |
           sed 's/[[:space:]]*$//; s/^"//; s/"$//')
    [ -n "$REPO" ] && break
  done
fi
if [ -z "$REPO" ] && [ -d "./status" ] && [ -d "./.git" ]; then REPO="."; fi
if [ -z "$REPO" ] || [ ! -d "$REPO/status" ]; then
  echo "lane-claim: no board found. Pass --repo <path>, set LANES_BOARD, or write" >&2
  echo "              board = /path/to/board-repo" >&2
  echo "            into ~/.claude/lanes.conf." >&2
  exit 2
fi

HOST="$(hostname 2>/dev/null || echo unknown-host)"
MARK="LIVE"
NOW=$(date +%s)
MAX_AGE_S=$(( MAX_AGE_H * 3600 ))

fetch_ref() {
  REF=origin/main
  if [ "$DO_FETCH" -eq 1 ]; then
    git -C "$REPO" fetch -q origin 2>/dev/null || echo "lane-claim: warning - fetch failed, reading last-known origin/main" >&2
  fi
  git -C "$REPO" rev-parse --verify -q "$REF" >/dev/null 2>&1 || REF=HEAD
}

# classify_line "<LIVE line>" -> sets C_STATE (FRESH|STALE|MALFORMED), C_LANE, C_WHEN, C_HOST, C_AGE_H
classify_line() {
  local line="$1" lane d t host when
  C_STATE=MALFORMED; C_LANE=""; C_WHEN=""; C_HOST=""; C_AGE_H=""
  # LIVE: /lm 2026-09-06 14:02 WORKSTATION
  if [[ "$line" =~ ^(LIVE):[[:space:]]+(/[a-z]+)[[:space:]]+([0-9]{4}-[0-9]{2}-[0-9]{2})[[:space:]]+([0-9]{2}:[0-9]{2})[[:space:]]+([^[:space:]]+)[[:space:]]*$ ]]; then
    lane="${BASH_REMATCH[2]}"; d="${BASH_REMATCH[3]}"; t="${BASH_REMATCH[4]}"; host="${BASH_REMATCH[5]}"
    when=$(date -d "$d $t" +%s 2>/dev/null) || return 0
    C_LANE="$lane"; C_WHEN="$d $t"; C_HOST="$host"
    C_AGE_H=$(( (NOW - when) / 3600 ))
    if [ $(( NOW - when )) -lt "$MAX_AGE_S" ]; then C_STATE=FRESH; else C_STATE=STALE; fi
  fi
}

# claim_of_blob <prefix> -> prints the LIVE line from origin/main (empty if none)
claim_of_blob() {
  git -C "$REPO" show "$REF:status/$1.md" 2>/dev/null | grep -m1 -E '^LIVE:' || true
}

report_one() {
  local prefix="$1" line="$2"
  if [ -z "$line" ]; then
    printf '%-28s NONE\n' "$prefix"
    return 0
  fi
  classify_line "$line"
  case "$C_STATE" in
    FRESH) printf '%-28s FRESH  %s since %s on %s (%sh ago) - the same lane is on this job NOW\n' "$prefix" "$C_LANE" "$C_WHEN" "$C_HOST" "$C_AGE_H"; return 1 ;;
    STALE) printf '%-28s STALE  %s since %s on %s (%sh ago, >%sh) - that session most likely died; the next take replaces it\n' "$prefix" "$C_LANE" "$C_WHEN" "$C_HOST" "$C_AGE_H" "$MAX_AGE_H"; return 0 ;;
    *)     printf '%-28s MALFORMED  "%s" - expected "LIVE: /lane YYYY-MM-DD HH:MM host"; treated as live until fixed\n' "$prefix" "$line"; return 1 ;;
  esac
}

case "$CMD" in
  check)
    [ $# -gt 0 ] || { echo "usage: lane-claim.sh check <prefix>..." >&2; exit 2; }
    fetch_ref
    rc=0
    for p in "$@"; do
      if ! git -C "$REPO" cat-file -e "$REF:status/$p.md" 2>/dev/null; then
        printf '%-28s NO STATUS FILE on %s\n' "$p" "$REF"
        continue
      fi
      report_one "$p" "$(claim_of_blob "$p")" || rc=1
    done
    exit $rc
    ;;

  list)
    fetch_ref
    any=0
    while IFS= read -r f; do
      p=$(basename "$f" .md)
      line=$(claim_of_blob "$p")
      [ -n "$line" ] || continue
      any=1
      report_one "$p" "$line" || true
    done < <(git -C "$REPO" ls-tree --name-only "$REF" status/ | grep -E '\.md$' | grep -v '_headlines-archive\.md')
    [ "$any" -eq 1 ] || echo "(no LIVE claims on $REF)"
    exit 0
    ;;

  take|release)
    lane="${1:-}"; prefix="${2:-}"
    [[ "$lane" =~ ^/[a-z]+$ ]] && [ -n "$prefix" ] || { echo "usage: lane-claim.sh $CMD </lane> <prefix> [--force]" >&2; exit 2; }
    file="status/$prefix.md"
    [ -f "$REPO/$file" ] || { echo "lane-claim: $REPO/$file does not exist" >&2; exit 2; }

    # A dirty status file here means another session is mid-edit in THIS root - the one
    # thing the one-root-per-lane rule exists to prevent. Stop, do not stash, do not pull.
    if ! git -C "$REPO" diff --quiet -- "$file" || ! git -C "$REPO" diff --cached --quiet -- "$file"; then
      echo "lane-claim: $file has uncommitted changes in $REPO - another session is editing it in this root. Not touching it." >&2
      exit 1
    fi
    if ! git -C "$REPO" pull -q --rebase 2>/dev/null; then
      echo "lane-claim: git pull --rebase refused in $REPO (dirty tree or conflict). That is git protecting someone else's work - resolve or use a different clone." >&2
      exit 1
    fi

    stamp="$(date '+%Y-%m-%d %H:%M')"
    attempt=0
    while :; do
      attempt=$((attempt+1))
      existing=$(grep -m1 -E "^$MARK:" "$REPO/$file" || true)
      if [ -n "$existing" ]; then
        classify_line "$existing"
        if [ "$CMD" = take ] && [ "$FORCE" -eq 0 ] && { [ "$C_STATE" = FRESH ] || [ "$C_STATE" = MALFORMED ]; }; then
          echo "REFUSED: $prefix is claimed - \"$existing\" ($C_STATE). The same lane is already on this job. Wait for it to finish, or the user types \"$lane force $prefix\" to take over." >&2
          exit 1
        fi
        if [ "$CMD" = release ] && [ "$FORCE" -eq 0 ] && [ "$C_LANE" != "$lane" ] && [ "$C_STATE" = FRESH ]; then
          echo "REFUSED: the claim on $prefix belongs to $C_LANE (\"$existing\"), not $lane. Not releasing someone else's live session." >&2
          exit 1
        fi
      elif [ "$CMD" = release ]; then
        echo "lane-claim: no LIVE claim on $prefix - nothing to release."
        exit 0
      fi

      # Rewrite: drop any LIVE line; for take, insert the new one above the first OPEN line
      # (or, failing that, after the first "## " heading, or at the top).
      tmp=$(mktemp)
      awk -v cmd="$CMD" -v mark="$MARK" -v newline="$MARK: $lane $stamp $HOST" '
        $0 ~ ("^" mark ":") { next }
        cmd=="take" && !done && /^OPEN[[:space:]]*\(/ { print newline; done=1 }
        { print }
        END {
          if (cmd=="take" && !done) { }
        }' "$REPO/$file" > "$tmp"
      if [ "$CMD" = take ] && ! grep -q -E '^LIVE:' "$tmp"; then
        # no OPEN line: put it after the first heading, else at the top
        awk -v newline="LIVE: $lane $stamp $HOST" '
          !done && /^## / { print; print ""; print newline; done=1; next }
          { print }
          END { if (!done) print newline }' "$REPO/$file" > "$tmp"
        if ! grep -q -E '^LIVE:' "$tmp"; then { printf '%s\n' "LIVE: $lane $stamp $HOST"; cat "$REPO/$file"; } > "$tmp"; fi
      fi
      # Preserve the file's own line endings (this repo checks out CRLF on Windows).
      if head -c 4000 "$REPO/$file" | grep -q $'\r'; then sed -i 's/\r$//; s/$/\r/' "$tmp"; fi
      cp "$tmp" "$REPO/$file"; rm -f "$tmp"

      if [ "$CMD" = take ]; then
        msg="claim: $lane live on $prefix ($HOST $stamp)"
      else
        msg="claim: $lane released $prefix ($HOST $stamp)"
      fi
      # CONVENTIONS.md -> "Every commit says which lane wrote it". These commits are
      # GENERATED, so they can never adopt the rule by a session reading it - the
      # trailer has to be emitted here. Without it /gs check 8's coverage carries a
      # permanent ceiling below 100% that is not any lane's fault and reads as
      # non-adoption on every sweep. $lane already holds the command name ("/pd"),
      # $prefix the project, which is exactly the trailer's shape.
      msg="$msg

Lane: $lane $prefix"
      git -C "$REPO" add -- "$file"
      if git -C "$REPO" diff --cached --quiet -- "$file"; then
        echo "lane-claim: nothing changed on $file."
        exit 0
      fi
      git -C "$REPO" commit -q -m "$msg" -- "$file" || { echo "lane-claim: commit failed" >&2; exit 1; }

      if git -C "$REPO" push -q 2>/dev/null; then
        if [ "$CMD" = take ]; then
          echo "CLAIMED: LIVE: $lane $stamp $HOST -> $file (pushed). Release it in your write-up: lane-claim.sh release $lane $prefix"
        else
          echo "RELEASED: $lane no longer claims $prefix (pushed)."
        fi
        exit 0
      fi

      # Push rejected: someone landed first. Undo OUR commit (only this file is touched),
      # rebase onto theirs, and look again - if they claimed the game, we lost the race.
      git -C "$REPO" reset -q --soft HEAD~1
      git -C "$REPO" restore --staged --worktree -- "$file" 2>/dev/null || git -C "$REPO" checkout -q HEAD -- "$file"
      if ! git -C "$REPO" pull -q --rebase 2>/dev/null; then
        echo "lane-claim: push rejected and the rebase after it failed - leaving $REPO as is. Run git status there." >&2
        exit 1
      fi
      if [ "$attempt" -ge 3 ]; then
        echo "lane-claim: push rejected 3 times on $file - giving up; check origin/main by hand." >&2
        exit 1
      fi
      # loop: re-read the file (now at origin/main) and re-apply
    done
    ;;

  *)
    sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac
