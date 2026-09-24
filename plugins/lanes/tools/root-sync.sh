#!/usr/bin/env bash
# root-sync.sh - make every lane's clone root hold every repo.
#
# Each lane works in its own clone root (docs/PROTOCOL.md section 3):
#   clones/  clones-pd/  clones-gr/  clones-sr/  clones-gs/
# A repo created or cloned in one root after the others were made is invisible to
# every other lane. Nothing fails: a sweep just reports on fewer projects than exist,
# and reads as a clean bill of health. Found on 2026-09-17, when /gs, /gr and /sr each
# discovered their roots were missing 16-17 of 39 repos.
#
# Usage:
#   root-sync.sh --check [ROOT]   list what is missing where; exit 1 if anything is
#   root-sync.sh --fix   [ROOT]   copy the missing repos in; exit 1 if a copy failed
#
# ROOT is the live lane's root: the argument, else $LANES_ROOT, else `root` in
# lanes.conf. The lane roots are `lane_roots` in lanes.conf (comma- or space-separated
# paths), else whichever of ROOT-pd, ROOT-gr, ROOT-sr, ROOT-gs exist.
#
# The set of repos is the UNION over all roots, so a repo that only one lane has
# cloned spreads to the others too. A missing copy is made with `git clone --local`
# (hardlinked objects, near-free), its origin pointed at the source's real remote,
# then fast-forwarded. It never deletes anything and never touches an existing clone.
# A repo with no origin remote is reported but not copied: a local-only repo spreading
# silently is the kind of surprise this tool exists to prevent.

set -uo pipefail

MODE=""
case "${1:-}" in
  --check|--fix) MODE="${1#--}"; shift ;;
  *) echo "usage: root-sync.sh --check|--fix [ROOT]" >&2; exit 2 ;;
esac

read_conf() {
  local key="$1" conf v=""
  for conf in "${LANES_CONFIG:-}" "$HOME/.claude/lanes.conf" "$HOME/.config/lanes/lanes.conf"; do
    [ -n "$conf" ] && [ -f "$conf" ] || continue
    v=$(sed -n "s/^[[:space:]]*$key[[:space:]]*=[[:space:]]*//p" "$conf" | head -1 |
        sed 's/[[:space:]]*$//; s/^"//; s/"$//; s/\r$//')
    [ -n "$v" ] && break
  done
  printf '%s' "$v"
}

ROOT="${1:-${LANES_ROOT:-$(read_conf root)}}"
ROOT="${ROOT%/}"
if [ -z "$ROOT" ] || [ ! -d "$ROOT" ]; then
  echo "root-sync: no clone root found. Pass one, set LANES_ROOT, or write" >&2
  echo "             root = /path/to/folder-holding-your-clones" >&2
  echo "           into ~/.claude/lanes.conf." >&2
  exit 2
fi

ROOTS=("$ROOT")
LANE_ROOTS="$(read_conf lane_roots)"
if [ -n "$LANE_ROOTS" ]; then
  for r in ${LANE_ROOTS//,/ }; do
    r="${r%/}"
    if [ -d "$r" ]; then ROOTS+=("$r")
    else echo "root-sync: lane root $r does not exist - skipped" >&2; fi
  done
else
  for suffix in pd gr sr gs; do
    [ -d "$ROOT-$suffix" ] && ROOTS+=("$ROOT-$suffix")
  done
fi

if [ "${#ROOTS[@]}" -lt 2 ]; then
  echo "root-sync: only one clone root ($ROOT), nothing to compare"
  exit 0
fi

# Every repo name found in any root, and the first root holding it (the live root wins).
declare -A SOURCE
for r in "${ROOTS[@]}"; do
  for d in "$r"/*/; do
    [ -d "$d.git" ] || continue
    name="$(basename "$d")"
    [ -n "${SOURCE[$name]:-}" ] || SOURCE[$name]="$r"
  done
done

missing=0; added=0; failed=0
for name in $(printf '%s\n' "${!SOURCE[@]}" | sort); do
  src="${SOURCE[$name]}/$name"
  for r in "${ROOTS[@]}"; do
    [ -e "$r/$name" ] && continue
    missing=$((missing + 1))
    url="$(git -C "$src" remote get-url origin 2>/dev/null)"
    if [ "$MODE" = check ]; then
      echo "MISSING  $r/$name   (present in ${SOURCE[$name]})"
      continue
    fi
    if [ -z "$url" ]; then
      echo "SKIPPED  $r/$name   ($src has no origin remote; copy it by hand if that is intended)"
      failed=$((failed + 1))
      continue
    fi
    if git clone --quiet --local "$src" "$r/$name" 2>/dev/null &&
       git -C "$r/$name" remote set-url origin "$url"; then
      git -C "$r/$name" pull --quiet --ff-only 2>/dev/null ||
        echo "note     $r/$name was copied but could not be updated from $url (offline?)"
      echo "ADDED    $r/$name"
      added=$((added + 1))
    else
      echo "FAILED   $r/$name   (git clone --local from $src)"
      failed=$((failed + 1))
    fi
  done
done

total="${#SOURCE[@]}"
if [ "$missing" -eq 0 ]; then
  echo "root-sync: all ${#ROOTS[@]} clone roots hold all $total repos"
  exit 0
fi
if [ "$MODE" = check ]; then
  echo "root-sync: $missing missing copies across ${#ROOTS[@]} roots ($total repos). Run with --fix."
  exit 1
fi
echo "root-sync: added $added, could not add $failed, across ${#ROOTS[@]} roots ($total repos)"
[ "$failed" -eq 0 ]
