#!/usr/bin/env bash
# rule-reach-fixture.sh - prove rule-reach-scan.py can actually go RED.
#
# A checker that cannot fail is not evidence, and this one exists precisely because a rule
# passed every human eye on the estate for fifteen days. Each case below plants exactly one
# of the three faults in a throwaway pair of files and asserts the scanner names it.
#
# Usage: tests/rule-reach-fixture.sh
# Exit:  0 = every case behaved, 1 = the scanner missed something it must catch
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
SCAN="$HERE/../rule-reach-scan.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass=0; fail=0
check() { # check <name> <expect-substring> <file-with-output>
  if grep -q "$2" "$3"; then
    pass=$((pass + 1))
  else
    fail=$((fail + 1))
    printf 'FAIL: %s  (expected to see "%s")\n' "$1" "$2"
    sed 's/^/    /' "$3"
  fi
}

run() { python "$SCAN" --always "$TMP/always.md" --rules "$TMP/rules.md" > "$TMP/out" 2>&1; }

# ---------------------------------------------------------------- case 1: clean
cat > "$TMP/always.md" <<'EOF'
# always read
## C++ OR LUA? mod in native code
Universal. Every project.
EOF
cat > "$TMP/rules.md" <<'EOF'
# archive
## C++ OR LUA? the full reasoning
Universal, every game. The archive copy.
EOF
run
check "clean estate reports 0 faults" "0 fault(s)" "$TMP/out"

# ------------------------------------------------- case 2: UNREACHABLE universal rule
cat > "$TMP/always.md" <<'EOF'
# always read
## TONE: how to talk to me
Keep replies short.
EOF
cat > "$TMP/rules.md" <<'EOF'
# archive
## never spawn a subagent without saying so
Universal, every session, every lane.
EOF
run
check "unreachable universal rule is caught" "subagent" "$TMP/out"
check "unreachable is counted as a fault" "1 fault" "$TMP/out"

# --------------------------------------------- case 3: UNFINDABLE heading (the real one)
cat > "$TMP/always.md" <<'EOF'
# always read
## nothing here
EOF
cat > "$TMP/rules.md" <<'EOF'
# archive
## Reach for the deep end
Universal, all games from now on. This is the exact heading that failed on 2026-09-04.
EOF
run
check "the original 'Reach for the deep end' heading is caught" "Reach for the deep end" "$TMP/out"

# ------------------------------------------------------------------ case 4: SPLIT rule
cat > "$TMP/always.md" <<'EOF'
# always read
## save table on every commit
Print it whenever you push.
EOF
cat > "$TMP/rules.md" <<'EOF'
# archive
## save table on every commit
A second full copy, free to drift.
EOF
run
check "the same subject in two files is caught" "SPLIT" "$TMP/out"
check "split names the shared subject" "commit" "$TMP/out"

# --------------------------------------- case 5: a good heading must NOT be flagged
cat > "$TMP/always.md" <<'EOF'
# always read
## GATE LINE: say what the next step requires
Universal, every session.
EOF
cat > "$TMP/rules.md" <<'EOF'
# archive
## GATE LINE: the full reasoning behind PD / FLAT / VR
Universal. Every project.
EOF
run
check "a findable, reachable rule is left alone" "0 fault(s)" "$TMP/out"

# ------------------------------------------------------- case 6: usage errors are distinct
python "$SCAN" --always "$TMP/nope.md" > "$TMP/out" 2>&1
if [ "$?" = "2" ]; then pass=$((pass + 1)); else
  fail=$((fail + 1)); echo "FAIL: a missing file should exit 2, not be silently clean"
fi

printf '\nrule-reach-fixture: %d passed, %d failed\n' "$pass" "$fail"
[ "$fail" = "0" ]
