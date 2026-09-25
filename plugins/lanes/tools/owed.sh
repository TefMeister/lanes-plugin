#!/usr/bin/env bash
# owed.sh - things that can only be done on the OTHER machine, queued for that machine.
#
# WHY THIS EXISTS
#   2026-09-18: a session on the dev PC installed a runtime and registered an MCP server
#   that the home PC also needs. The only record was a paragraph in the board's open-actions
#   block -- a shared file every machine reads, so it nags BOTH machines forever, and the one
#   that can actually act on it has no way to tell its rows from the other machine's. The
#   maintainer asked for it to be automatic instead: "if something needs to be done on home pc
#   to take effect, please set a reminder automatically".
#
#   A note in a shared file is not a reminder. A reminder is addressed, it arrives on the
#   machine that can act, and it goes away when that machine acts. That is all this is.
#
# USAGE
#   owed.sh                         # check: SILENT unless THIS machine owes something
#   owed.sh add <ROLE> "<title>"    # raise one for a machine; body is read from stdin
#   owed.sh list [<ROLE>|--all]     # what is queued, for one machine or all of them
#   owed.sh show <file>             # print one item in full
#   owed.sh done <file>             # clear one, by its exact name - never a pattern
#
# ROLE is a machine label from your board's machine-assignments.tsv (the shipped pair is
# HOME and DEV). Items live at <board>/owed/<ROLE>/YYYY-MM-DD-<slug>.md, one file per item,
# create-only: two machines raising items at the same moment can never collide, by
# construction, the same way the research inboxes cannot.
#
# WHICH BOARD it writes to is resolved most-specific-first: $LANES_BOARD, then the clone this
# script lives in, then the clone you are standing in, then `board =` in lanes.conf. If you keep
# one clone per lane, run that lane's own copy and it will use that lane's clone. See find_board
# below for why that order, and what went wrong when the config came first.
#
# This script NEVER commits and never pushes. It writes one file, or deletes one file, and
# tells you to save it. A tool that commits on your behalf inside a shared repo is how an
# unrelated lane's work gets swept into someone else's commit.
set -uo pipefail

usage() { sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'; }

# ---- where is the board? -------------------------------------------------------------
# ORDER CHANGED 2026-09-18, and the reason matters.
#
# This used to read the machine-wide config BEFORE looking at where it was actually running,
# so `board = ...` in lanes.conf won every time. On a single-clone setup that is invisible.
# On a machine that keeps ONE CLONE PER LANE -- the whole point of the lane layout -- it means
# every lane's copy of this tool writes into whichever clone the config happens to name. A /pd
# session raised a reminder and the file landed in the live modding session's working tree,
# uncommitted, in a repo that session was mid-rebase on. Nothing was lost, but only because it
# was spotted by hand.
#
# A tool that WRITES must default to the clone it belongs to, never to a machine-wide name.
# (gate-scan.sh and frontpage-scan.sh still resolve config-first; they only READ, and gate-scan
# reads origin/main anyway, so the same order is harmless there.)
#
# The order is now, most specific first:
#   1. $LANES_BOARD                  -- an explicit override always wins
#   2. the clone THIS SCRIPT lives in -- `<script dir>/..`, the deployed.sh convention: a per-lane
#                                       copy of the tools operates on its own lane, whatever the
#                                       working directory is (so it works from a subfolder too)
#   3. the clone we are STANDING IN   -- walking up from $PWD, for an installed plugin copy run
#                                       while inside a board clone (the lane-claim.sh convention)
#   4. `board = <path>` in $LANES_CONFIG, ~/.claude/lanes.conf or ~/.config/lanes/lanes.conf
#                                    -- the machine-wide fallback, which is what the SessionStart
#                                       hook uses: it runs the INSTALLED plugin copy, which has no
#                                       .git and no status/, from whatever directory the session
#                                       opened in, so rules 2 and 3 correctly do not fire for it.
#
# Still deliberately no built-in path guesses.
is_board() { [ -d "$1/status" ] && [ -d "$1/.git" ]; }

find_board() {
  local b conf self here

  # 1. explicit override
  if [ -n "${LANES_BOARD:-}" ]; then echo "${LANES_BOARD}"; return; fi

  # 2. the clone this script is part of
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)" || self=""
  if [ -n "$self" ] && is_board "$self"; then echo "$self"; return; fi

  # 3. the clone the working directory is inside
  here="$(pwd 2>/dev/null)" || here=""
  while [ -n "$here" ]; do
    if is_board "$here"; then echo "$here"; return; fi
    case "$here" in
      */*) here="${here%/*}" ;;
      *)   break ;;
    esac
  done

  # 4. the machine-wide config
  for conf in "${LANES_CONFIG:-}" "$HOME/.claude/lanes.conf" "$HOME/.config/lanes/lanes.conf"; do
    [ -n "$conf" ] && [ -f "$conf" ] || continue
    b=$(sed -n 's/^[[:space:]]*board[[:space:]]*=[[:space:]]*//p' "$conf" | head -1 |
        sed 's/[[:space:]]*$//; s/^"//; s/"$//')
    [ -n "$b" ] && { echo "$b"; return; }
  done

  echo ""
}

# ---- which machine am I? -------------------------------------------------------------
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

BOARD="$(find_board)"
ROLE="$(detect_role)"
# ---- what this PC is CALLED in anything written down (0.24.0) -------------------------------
# Never the computer's real name: that breaks the naming rule (PROTOCOL.md section 12), and an
# outside audit of 0.22.0 found claims and reminders were writing it into the board and commits.
# The name comes from machine-name.py: chosen in /lanes:setup, or PC1, PC2 ... taken automatically.
# Kept inline, not in a shared file, because copies of these scripts are run on their own.
machine_label() {
  local conf v py here confs
  if [ -n "${LANES_CONFIG:-}" ]; then confs=("$LANES_CONFIG")   # a test's scratch file is the ONLY one
  else confs=("$HOME/.claude/lanes.conf" "$HOME/.config/lanes/lanes.conf"); fi
  for conf in "${confs[@]}"; do
    [ -f "$conf" ] || continue
    v=$(sed -n 's/^[[:space:]]*machine_name[[:space:]]*=[[:space:]]*//p' "$conf" | head -1 |
        sed 's/[[:space:]]*$//; s/^"//; s/"$//' | tr -cd 'A-Za-z0-9._-')
    [ -n "$v" ] && { echo "$v"; return; }
  done
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if [ -f "$here/machine-name.py" ]; then
    for py in python3 python py; do
      command -v "$py" >/dev/null 2>&1 && "$py" -c "" >/dev/null 2>&1 || continue
      v=$(LANES_BOARD="${REPO:-${BOARD:-${LANES_BOARD:-}}}" "$py" "$here/machine-name.py" 2>/dev/null | tr -cd 'A-Za-z0-9._-')
      [ -n "$v" ] && { echo "$v"; return; }
    done
  fi
  echo "$1"   # last resort: the role (HOME, DEV ...), still never the computer's name
}

HOST=""   # worked out only by add: working it out can save a name and push machines.txt
MODE="${1:-check}"
OWED="$BOARD/owed"

# In check mode every failure path is silent: this runs at session start, and a hook that
# can be the reason a session opens with an error will be switched off within the week.
quiet_ok() { [ "$MODE" = "check" ] && exit 0; }
[ -n "$BOARD" ] && [ -d "$BOARD" ] || { quiet_ok; echo "owed: no board found. Pass \$LANES_BOARD or set 'board =' in ~/.claude/lanes.conf." >&2; exit 2; }

slug() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]' |
    sed 's/[^a-z0-9]\+/-/g; s/^-//; s/-$//' | cut -c1-60
}

# titles_of <dir> -> "<file>\t<title>\t<raised line>" for each item, newest name last
item_line() {
  local f="$1" title raised
  title=$(sed -n 's/^#[[:space:]]\+//p' "$f" | head -1)
  [ -n "$title" ] || title="(untitled)"
  raised=$(sed -n 's/^Raised:[[:space:]]*//p' "$f" | head -1)
  printf '%s\t%s\t%s\n' "$(basename "$f")" "$title" "$raised"
}

# ---- the shared truth is origin/main, not this disk ----------------------------------
# An item raised on the OTHER machine reaches this one only through git, so a check that
# reads the working tree alone reports this disk's past. Fetch refs (which cannot disturb
# another lane's uncommitted files), read origin/main, and union in anything local that is
# not committed yet so an item raised seconds ago in this session still shows.
remote_items() {
  local role="$1"
  git -C "$BOARD" fetch -q origin 2>/dev/null
  local ref=origin/main
  git -C "$BOARD" rev-parse --verify -q "$ref" >/dev/null 2>&1 || ref=HEAD
  git -C "$BOARD" ls-tree --name-only "$ref" "owed/$role/" 2>/dev/null | sed 's#.*/##'
}
local_items() {
  local role="$1"
  [ -d "$OWED/$role" ] || return 0
  find "$OWED/$role" -maxdepth 1 -type f -name '*.md' 2>/dev/null | sed 's#.*/##'
}
all_items() { { remote_items "$1"; local_items "$1"; } | sort -u | grep -v '^$' || true; }

case "$MODE" in

  # ---------------------------------------------------------------- check (the hook) ---
  check)
    names=$(all_items "$ROLE")
    [ -n "$names" ] || exit 0
    count=$(printf '%s\n' "$names" | wc -l | tr -d ' ')
    # ASCII only, deliberately: this goes through a SessionStart hook, and on Windows the
    # Python that wraps it reads stdin in the locale encoding -- a UTF-8 emoji arrives as
    # mojibake in the session. gate-scan --brief keeps to ASCII for the same reason.
    echo "!! $count THING(S) ARE WAITING FOR **THIS** MACHINE ($ROLE) - and only this one can do them."
    echo
    n=0
    while IFS= read -r name; do
      [ -n "$name" ] || continue
      n=$((n + 1))
      f="$OWED/$ROLE/$name"
      if [ -f "$f" ]; then
        title=$(sed -n 's/^#[[:space:]]\+//p' "$f" | head -1)
        why=$(sed -n 's/^Why here:[[:space:]]*//p' "$f" | head -1)
        raised=$(sed -n 's/^Raised:[[:space:]]*//p' "$f" | head -1)
        echo " $n. ${title:-$name}"
        [ -n "$why" ] && echo "    why this machine: $why"
        [ -n "$raised" ] && echo "    raised: $raised"
        echo "    full item: owed/$ROLE/$name"
      else
        echo " $n. owed/$ROLE/$name  -- on GitHub but NOT in this clone; pull the board first."
      fi
    done <<< "$names"
    echo
    echo "Tell the user in plain words what is waiting and offer to do it now - do not just list filenames."
    echo "Read one in full with:  owed.sh show <name>"
    echo "When one is genuinely finished:  owed.sh done <name>   then commit and push the board."
    exit 0
    ;;

  # -------------------------------------------------------------------------- add ------
  add)
    role="${2:-}"; title="${3:-}"
    [ -n "$role" ] && [ -n "$title" ] || { usage; echo; echo "owed add: need a ROLE and a title." >&2; exit 2; }
    if [ "$role" = "$ROLE" ]; then
      echo "owed add: '$role' is THIS machine. Something you can do here is not a reminder - do it." >&2
      exit 2
    fi
    mkdir -p "$OWED/$role" || exit 2
    file="$OWED/$role/$(date +%F)-$(slug "$title").md"
    if [ -e "$file" ]; then
      echo "owed add: $file already exists. Items are create-only; pick a different title." >&2
      exit 2
    fi
    body=""
    [ -t 0 ] || body="$(cat)"
    {
      echo "# $title"
      echo
      echo "Machine: $role"
      echo "Raised: $(date +%F) on $(machine_label "$ROLE")${LANE:+, $LANE lane}"
      if [ -n "$body" ]; then echo; printf '%s\n' "$body"; fi
    } > "$file" || exit 2
    echo "$file"
    echo "Raised for $role. NOT committed - commit and push the board or that machine never sees it." >&2
    ;;

  # ------------------------------------------------------------------------- list ------
  list)
    want="${2:---all}"
    roles=""
    if [ "$want" = "--all" ]; then
      roles=$( { git -C "$BOARD" ls-tree --name-only "$(git -C "$BOARD" rev-parse --verify -q origin/main >/dev/null 2>&1 && echo origin/main || echo HEAD)" "owed/" 2>/dev/null | sed 's#owed/##; s#/$##'
                 [ -d "$OWED" ] && find "$OWED" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sed 's#.*/##'; } | sort -u | grep -v '^$' )
    else
      roles="$want"
    fi
    [ -n "$roles" ] || { echo "Nothing is owed by any machine."; exit 0; }
    found=0
    while IFS= read -r r; do
      [ -n "$r" ] || continue
      names=$(all_items "$r")
      [ -n "$names" ] || continue
      found=1
      marker=""; [ "$r" = "$ROLE" ] && marker="   <- THIS MACHINE"
      echo "$r$marker"
      while IFS= read -r name; do
        [ -n "$name" ] || continue
        f="$OWED/$r/$name"
        if [ -f "$f" ]; then
          printf '   %s\n' "$(sed -n 's/^#[[:space:]]\+//p' "$f" | head -1)"
          printf '      %s\n' "$name"
        else
          printf '   %s  (not pulled into this clone)\n' "$name"
        fi
      done <<< "$names"
      echo
    done <<< "$roles"
    [ "$found" = 1 ] || echo "Nothing is owed by any machine."
    ;;

  # ------------------------------------------------------------------------- show ------
  show)
    name="${2:-}"; role="${3:-$ROLE}"
    [ -n "$name" ] || { echo "owed show: name the item file." >&2; exit 2; }
    f="$OWED/$role/$(basename "$name")"
    [ -f "$f" ] || { echo "owed show: no such item: $f" >&2; exit 2; }
    cat "$f"
    ;;

  # ------------------------------------------------------------------------- done ------
  # By exact name only. Never a glob, never a directory - the drain-by-explicit-list rule:
  # a pattern can delete an item another session raised seconds ago, unread and uncommitted,
  # and there would then be nothing anywhere to show it ever existed.
  done)
    name="${2:-}"; role="${3:-$ROLE}"
    [ -n "$name" ] || { echo "owed done: name the item file." >&2; exit 2; }
    case "$name" in
      *'*'*|*'?'*|*/*) echo "owed done: give one exact filename, not a pattern or a path." >&2; exit 2 ;;
    esac
    f="$OWED/$role/$name"
    [ -f "$f" ] || { echo "owed done: no such item: $f" >&2; exit 2; }
    title=$(sed -n 's/^#[[:space:]]\+//p' "$f" | head -1)
    rm -f "$f" || exit 2
    echo "Cleared: ${title:-$name}"
    echo "NOT committed - commit and push the board, or it comes back at the next session." >&2
    ;;

  -h|--help|help) usage ;;
  *) usage; echo; echo "owed: unknown command '$MODE'." >&2; exit 2 ;;
esac
