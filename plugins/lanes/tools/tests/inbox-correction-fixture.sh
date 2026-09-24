#!/usr/bin/env bash
# inbox-correction-fixture.sh - prove inbox-correction-scan.py can go RED.
#
# The tool exists because a correction went four rounds of review and lost. A checker built for
# that failure had better be able to fail itself, so each case below plants a known state and
# asserts the scanner names it.
#
# Usage: tests/inbox-correction-fixture.sh
# Exit:  0 = every case behaved, 1 = the scanner missed something
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
SCAN="$HERE/../inbox-correction-scan.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass=0; fail=0
check() {
  if grep -q "$2" "$3"; then pass=$((pass + 1)); else
    fail=$((fail + 1)); printf 'FAIL: %s (expected "%s")\n' "$1" "$2"; sed 's/^/    /' "$3"
  fi
}
absent() {
  if grep -q "$2" "$3"; then
    fail=$((fail + 1)); printf 'FAIL: %s (did NOT expect "%s")\n' "$1" "$2"
  else pass=$((pass + 1)); fi
}

mk() { mkdir -p "$TMP/repo/docs" "$TMP/repo/docs/inbox"; }

# ------------------------------------------- case 1: the real Far Cry 2 shape - still present
rm -rf "$TMP/repo"; mk
printf 'last activity 2019-11-23 and it is untouched\n' > "$TMP/repo/docs/DOSSIER.md"
cat > "$TMP/repo/docs/inbox/2026-09-04-gr-the-date-is-wrong.md" <<'EOF'
Supersedes: `docs/DOSSIER.md` the last-activity clause
Still-wrong: docs/DOSSIER.md :: last activity 2019-11-23
EOF
python "$SCAN" "$TMP/repo" > "$TMP/out" 2>&1
check "a live falsehood is caught"           "STILL PRESENT" "$TMP/out"
check "it names the exact string"            "last activity 2019-11-23" "$TMP/out"
check "it names who said so"                 "2026-09-04-gr-the-date-is-wrong" "$TMP/out"
python "$SCAN" "$TMP/repo" > /dev/null 2>&1
[ "$?" = "1" ] && pass=$((pass + 1)) || { fail=$((fail + 1)); echo "FAIL: a live falsehood must exit 1"; }

# --------------------------------------------- case 2: the fix landed - must go quiet
printf 'last activity 2020-04-22, one community bump\n' > "$TMP/repo/docs/DOSSIER.md"
python "$SCAN" "$TMP/repo" > "$TMP/out" 2>&1
absent "once the string is gone it is not reported" "STILL PRESENT" "$TMP/out"
check  "and it counts as resolved"                  "resolved (string is gone" "$TMP/out"
python "$SCAN" "$TMP/repo" > /dev/null 2>&1
[ "$?" = "0" ] && pass=$((pass + 1)) || { fail=$((fail + 1)); echo "FAIL: no live falsehood must exit 0"; }

# ------------------------------- case 3: corrects a doc but does not say what is wrong
rm -rf "$TMP/repo"; mk
printf 'some prose\n' > "$TMP/repo/docs/DOSSIER.md"
cat > "$TMP/repo/docs/inbox/2026-09-05-gs-vague.md" <<'EOF'
Supersedes: `docs/DOSSIER.md` section 4, the bit about the camera
EOF
python "$SCAN" "$TMP/repo" > "$TMP/out" 2>&1
check "an unverifiable correction is nudged" "2026-09-05-gs-vague" "$TMP/out"
absent "but it is NOT called a live falsehood" "STILL PRESENT" "$TMP/out"

# --------------------- case 4: superseding another INBOX file is fine, not a nudge
rm -rf "$TMP/repo"; mk
printf 'x\n' > "$TMP/repo/docs/inbox/2026-09-01-a.md"
cat > "$TMP/repo/docs/inbox/2026-09-02-b.md" <<'EOF'
Supersedes: `inbox/2026-09-01-a.md` - drain both together
EOF
python "$SCAN" "$TMP/repo" > "$TMP/out" 2>&1
absent "an inbox-to-inbox supersession is left alone" "2026-09-02-b" "$TMP/out"

# ---------------------------------------- case 5: a named target that does not exist
rm -rf "$TMP/repo"; mk
cat > "$TMP/repo/docs/inbox/2026-09-06-gs-moved.md" <<'EOF'
Still-wrong: docs/GONE.md :: something
EOF
python "$SCAN" "$TMP/repo" > "$TMP/out" 2>&1
check "a missing target is reported, not silently passed" "TARGET MISSING" "$TMP/out"

# ------------------------------------------------- case 6: usage error is distinct
python "$SCAN" > /dev/null 2>&1
[ "$?" = "2" ] && pass=$((pass + 1)) || { fail=$((fail + 1)); echo "FAIL: no args should exit 2"; }

printf '\ninbox-correction-fixture: %d passed, %d failed\n' "$pass" "$fail"
[ "$fail" = "0" ]
