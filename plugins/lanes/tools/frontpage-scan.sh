#!/usr/bin/env bash
# frontpage-scan.sh - is the public front page keeping up with the work?
#
# WHY THIS EXISTS
#
# A public page that only changes on good news is not an honest record, and a
# page that has not moved in a fortnight reads as an abandoned project however
# busy the repos underneath it are. The person this account belongs to asked for
# the opposite: "even the smallest advancements or even changes, not necessarily
# advancements ... it's nice to see for me and others to see that things are
# constantly being worked on."
#
# That is a standing rule, and a standing rule nobody can check is a wish. So
# this compares two dates:
#
#   the newest dated entry on any board in status/   (what was actually worked)
#   the newest dated entry in the front page's log   (what the world can see)
#
# and reports when the second is behind the first. Being behind is not an error
# in itself -- a session may be mid-flight -- which is why it exits 0 on a lag
# and only fails on a missing configuration. It is a reminder, not a gate.
#
# READ-ONLY. It never edits the front page; writing the line is the session's
# job, and a tool that wrote it would produce exactly the bland auto-generated
# noise the rule exists to avoid.
#
# USAGE
#   frontpage-scan.sh [<board-path>]
#   frontpage-scan.sh --quiet     # print only when the page is behind
#
# CONFIG (~/.claude/lanes.conf)
#   frontpage = /path/to/profile-repo/README.md
# Overridden by $LANES_FRONTPAGE. If neither is set the script says so and exits
# 0: an estate with no public page is a normal thing to be.

set -u

QUIET=0
BOARD_ARG=""
for a in "$@"; do
  case "$a" in
    --quiet) QUIET=1 ;;
    *) BOARD_ARG="$a" ;;
  esac
done

conf_get() {
  local key="$1" conf v
  for conf in "${LANES_CONFIG:-}" "$HOME/.claude/lanes.conf" "$HOME/.config/lanes/lanes.conf"; do
    [ -n "$conf" ] && [ -f "$conf" ] || continue
    v=$(sed -n "s/^[[:space:]]*${key}[[:space:]]*=[[:space:]]*//p" "$conf" | head -1 |
        sed 's/[[:space:]]*$//; s/^"//; s/"$//')
    [ -n "$v" ] && { echo "$v"; return; }
  done
}

# ---- the board ------------------------------------------------------------
BOARD="$BOARD_ARG"
[ -n "$BOARD" ] || BOARD="${LANES_BOARD:-}"
[ -n "$BOARD" ] || BOARD="$(conf_get board)"
if [ -z "${BOARD:-}" ] && [ -d "./status" ] && [ -d "./.git" ]; then BOARD="."; fi
if [ -z "${BOARD:-}" ] || [ ! -d "$BOARD/status" ]; then
  echo "frontpage-scan: no board found. Pass its path, set \$LANES_BOARD, or write" >&2
  echo "                  board = /path/to/board-repo" >&2
  echo "                into ~/.claude/lanes.conf." >&2
  exit 2
fi

# ---- the front page -------------------------------------------------------
PAGE="${LANES_FRONTPAGE:-}"
[ -n "$PAGE" ] || PAGE="$(conf_get frontpage)"
if [ -z "${PAGE:-}" ]; then
  [ "$QUIET" -eq 1 ] || cat <<'EOF'
frontpage-scan: no front page configured, so there is nothing to keep up to date.
                If you have a public page that should reflect this work, add

                    frontpage = /path/to/profile-repo/README.md

                to ~/.claude/lanes.conf. If you do not, ignore this.
EOF
  exit 0
fi
if [ ! -f "$PAGE" ]; then
  echo "frontpage-scan: configured front page does not exist: $PAGE" >&2
  echo "                Fix the 'frontpage' path in ~/.claude/lanes.conf." >&2
  exit 2
fi

# ---- newest dated entry on any board --------------------------------------
# Boards carry ISO dates throughout; the newest one anywhere in status/ is a
# good proxy for "when was this estate last worked". Deliberately simple: a
# smarter parse would be a second thing to keep in step with the board format.
newest_date_in() {
  grep -rhoE '20[0-9]{2}-[01][0-9]-[0-3][0-9]' "$@" 2>/dev/null | sort | tail -1
}

BOARD_DATE="$(newest_date_in "$BOARD/status")"
PAGE_DATE="$(newest_date_in "$PAGE")"
TODAY="$(date +%F)"

if [ -z "$BOARD_DATE" ]; then
  [ "$QUIET" -eq 1 ] || echo "frontpage-scan: no dates found on any board - nothing to compare."
  exit 0
fi

# ---- report ---------------------------------------------------------------
if [ -z "$PAGE_DATE" ]; then
  echo "=== frontpage-scan ==="
  echo "  ⚠️  THE FRONT PAGE CARRIES NO DATED ENTRY AT ALL."
  echo "      page:  $PAGE"
  echo "      board: newest work $BOARD_DATE"
  echo "      Add a dated activity entry. Even 'looked, found nothing, here is why' counts."
  exit 0
fi

if [ "$PAGE_DATE" \< "$BOARD_DATE" ]; then
  echo "=== frontpage-scan ==="
  echo "  ⚠️  THE FRONT PAGE IS BEHIND THE WORK."
  echo "      newest on a board:      $BOARD_DATE"
  echo "      newest on the front page: $PAGE_DATE"
  echo "      page: $PAGE"
  echo
  echo "  Add a line for what happened. The rule is deliberately not 'when something"
  echo "  worked' - a dead end, a correction, or a quiet look that found nothing are all"
  echo "  part of an honest record, and they are what make the page read as alive."
  exit 0
fi

if [ "$QUIET" -eq 0 ]; then
  echo "=== frontpage-scan ==="
  if [ "$PAGE_DATE" = "$TODAY" ]; then
    echo "  ok - the front page carries today's date ($PAGE_DATE)."
  else
    echo "  ok - the front page ($PAGE_DATE) is level with the newest board entry ($BOARD_DATE)."
  fi
fi
exit 0
