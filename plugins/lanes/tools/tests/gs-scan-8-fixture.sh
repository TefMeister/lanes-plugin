#!/usr/bin/env bash
# gs-scan-8-fixture.sh - does check 8 (lane attribution) still say the same thing after the 2026-11-11 speed-up?
#
#     bash tools/tests/gs-scan-8-fixture.sh
#
# WHY THIS EXISTS
#   Check 8 used to ask git two questions per commit and read its whole list once per file: about 25 of the
#   33 minutes a full /gs took on 2026-11-11. It now reads each repo with one `git log` and groups the files
#   in one awk pass. A faster check that says something different is worse than a slow one, so this pins
#   what it must say: a file two lanes wrote is named (lanes sorted), an inbox drop ADDED by one lane and
#   DELETED by another is the protocol working and is not named, a file touched once is ignored, a file
#   touched by a commit without the trailer counts as unattributed, and a line in a commit MESSAGE that
#   looks like a file line is not a file. GS_SCAN=<other copy> runs the same checks against another copy
#   (that is how the old and new versions were compared).
#
# Builds throwaway repos in a temp dir, runs the real scanner, and checks section 8. Touches nothing else.
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
SCAN="${GS_SCAN:-$HERE/../gs-scan.sh}"
[ -f "$SCAN" ] || { echo "cannot find gs-scan.sh"; exit 1; }

TMP=$(mktemp -d 2>/dev/null || echo "${TMPDIR:-/tmp}/gs8.$$")
mkdir -p "$TMP/alpha/eng/inbox" "$TMP/beta"
trap 'rm -rf "$TMP"' EXIT

c() {  # c <repo> <message...>: commit everything staged in that repo
  local r="$1"; shift
  git -C "$TMP/$r" -c user.email=t@t -c user.name=t commit -q "$@" >/dev/null 2>&1
}
for r in alpha beta; do
  git -C "$TMP/$r" init -q . >/dev/null 2>&1
  git -C "$TMP/$r" config core.autocrlf false
done

echo one > "$TMP/alpha/notes.md"; git -C "$TMP/alpha" add notes.md
c alpha -m "first" -m "Lane: /pd alpha"
echo two >> "$TMP/alpha/notes.md"; git -C "$TMP/alpha" add notes.md
c alpha -m "second" -m "$(printf 'M\tfake-file-in-a-message.md')" -m "Lane: /gr alpha"
echo drop > "$TMP/alpha/eng/inbox/drop.md"; git -C "$TMP/alpha" add eng/inbox/drop.md
c alpha -m "inbox: a drop" -m "Lane: /gr alpha"
git -C "$TMP/alpha" rm -q eng/inbox/drop.md
c alpha -m "drain" -m "lane: /pd alpha"
echo x > "$TMP/beta/other.md"; git -C "$TMP/beta" add other.md
c beta -m "no trailer here"
echo y >> "$TMP/beta/other.md"; git -C "$TMP/beta" add other.md
c beta -m "tagged" -m "Lane: /pd beta"
echo z > "$TMP/beta/single.md"; git -C "$TMP/beta" add single.md
c beta -m "single" -m "Lane: /pd beta"

out=$(cd "$TMP" && bash "$SCAN" "$TMP" 2000-01-01 </dev/null 2>/dev/null | sed -n '/^--- 8\./,/scan complete/p')

fail=0
want() { printf '%s\n' "$out" | grep -qxF -- "$1" || { echo "MISSING: $1"; fail=1; }; }
never() { printf '%s\n' "$out" | grep -qF -- "$1" && { echo "SHOULD NOT APPEAR: $1"; fail=1; }; }

want "  trailer coverage: 6 of 7 commits carry a Lane: line (85%)"
want "  ⚠️ FILES WRITTEN BY MORE THAN ONE LANE:"
want "  alpha/notes.md"
want "      /gr alpha"
want "      /pd alpha"
want "  1 multi-touch file(s) UNATTRIBUTED (a commit lacked the trailer) - not a pass"
never "drop.md"
never "fake-file-in-a-message"
never "single.md"
never "beta/other.md"
# lanes under a file are listed in order
printf '%s\n' "$out" | grep -A2 -xF "  alpha/notes.md" | tail -2 | tr '\n' '|' | grep -qxF "      /gr alpha|      /pd alpha|" ||
  { echo "lanes under alpha/notes.md not in order"; fail=1; }

if [ "$fail" -eq 0 ]; then echo PASS; else printf '%s\n' "--- section 8 as printed:" "$out"; echo FAIL; fi
exit "$fail"
