#!/usr/bin/env bash
# gs-scan-3b-fixture.sh - does check 3b still catch a real invented tag after the
# 2026-09-05 use/mention split?
#
#     bash tools/tests/gs-scan-3b-fixture.sh
#
# WHY THIS EXISTS
#   On 2026-09-05 check 3b was measured at ~46% signal: 7 of 13 hits were prose
#   ABOUT a bad tag rather than a bad tag, and the error is self-reinforcing -
#   every time a lane correctly documents a tag correction it adds a permanent
#   false positive. The fix splits hits into IN USE and BARE instead of dropping
#   any, so nothing is lost and the actionable ones stop being buried.
#
#   A filter that quiets a check is exactly the kind of change that can silently
#   blind it, so this fixture pins the behaviour. Both versions of that patch
#   were wrong and this caught both:
#     1. the line number parsed as empty, so EVERYTHING landed in "bare";
#     2. the date test looked only at the character after the tag name, which
#        mis-filed DOOM's own `[verified from published first-party source,
#        2026-08-30]` - the very case check 3b was created for.
#     4. a DATED tag QUOTED inside correction prose landed in DATED, so a
#        lane that correctly documented its own fix was reported as having
#        committed a fresh violation - found 2026-09-07. Third bucket added.
#     3. the second bucket was labelled "usually prose ABOUT a tag", which
#        soft-pedalled a REAL undated tag - found by the four-lane run the same
#        evening. An undated off-vocabulary tag is BOTH defects at once, so the
#        buckets are now DATED / UNDATED and neither reads as harmless.
#
# Builds a throwaway repo in a temp dir, runs the real scanner against it, and
# asserts the classification. Touches nothing in the estate.
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
SCAN="$HERE/../gs-scan.sh"
[ -f "$SCAN" ] || { echo "cannot find gs-scan.sh next to this test"; exit 1; }

TMP=$(mktemp -d 2>/dev/null || echo "${TMPDIR:-/tmp}/gs3b.$$")
mkdir -p "$TMP/fakerepo/modding-notes" "$TMP/board-repo"
trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/fakerepo/modding-notes/fixture.md" <<'EOF'
# fixture

REAL, and the historic case this check was built for - a prose phrase sits
between the name and the date: the MVP is at +0
`[verified from published first-party source, 2026-08-30]`.
REAL, a plausible invented dated tag: the offset is 0x40 `[confirmed-static 2026-09-01, n=3]`.
VALID, must NOT fire: the basis is column-major `[verified-numerically 2026-09-03]`.
VALID, must NOT fire: `[inferred-static 2026-09-02]` and `[hypothesis]`.
MENTION, lands in UNDATED: this pass corrected an off-vocabulary `[verified-static]` tag.
REAL but UNDATED - the 2026-09-05 four-lane case: the branch is absent `[inferred]` intentional.
CHANGELOG, a DATED tag QUOTED inside correction prose - the 2026-09-07 case: drained the tag drop, `[inferred 2026-09-02, n=1, by eye]` was not in the eight-name vocabulary, both copies now read `[measured 2026-09-02]`.
EOF

( cd "$TMP/fakerepo" && git init -q . && git add -A &&
  git -c user.email=t@t -c user.name=t commit -qm fixture ) >/dev/null 2>&1

out=$(cd "$TMP" && bash "$SCAN" "$TMP" 2>&1 | sed -n '/3b\./,/^--- 4\./p')

fail=0
expect() {  # expect <description> <regex>
  if printf '%s' "$out" | grep -qE "$2"; then
    echo "  ok   $1"
  else
    echo "  FAIL $1"; fail=1
  fi
}
refute() {
  if printf '%s' "$out" | grep -qE "$2"; then
    echo "  FAIL $1 (should not appear)"; fail=1
  else
    echo "  ok   $1"
  fi
}

echo "check 3b fixture"
expect "the historic DOOM-shaped tag is DATED"       '\[verified \.\.\.'
expect "a dated invented tag is DATED"               '\[confirmed-static \.\.\.'
expect "the prose mention lands in UNDATED"          '\[verified-static\]'
expect "an UNDATED real use is still printed"        '\[inferred\]'
expect "a dated tag quoted in correction prose is NOT dated" '\(2 dated, 2 undated, 1 quoted'
# prints as "[inferred ..." (dated form); the UNDATED real use prints as
# "[inferred]", so this regex matches the quoted one and only it.
expect "the quoted changelog tag is still printed"   '\[inferred \.\.\.'
expect "the QUOTED bucket does not read as harmless" 'Read it before dismissing'
expect "the UNDATED label does not say 'usually prose'" 'BOTH defects at once'
refute "no valid vocabulary name is reported"        '\[(verified-numerically|inferred-static|hypothesis)'

printf '%s\n' "$out" | tail -4
if [ "$fail" -eq 0 ]; then echo "PASS"; else echo "FAILED"; fi
exit "$fail"
