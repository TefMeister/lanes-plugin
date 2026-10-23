#!/usr/bin/env bash
# features-fixture.sh - tools/features.py (0.82.0; links, sets, update safety 0.84.0): a new install has every extra off until setup answers, an
# update keeps them all on, lanes.conf wins either way, and the hooks it gates go quiet when off. Exit 0 = all passed.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PY=""
for cand in python3 python py; do command -v "$cand" >/dev/null 2>&1 && "$cand" -c "" >/dev/null 2>&1 && { PY="$cand"; break; }; done
[ -n "$PY" ] || { echo "features-fixture: no working Python"; exit 1; }
pass=0; fail=0
check() { if [ "$1" = "$2" ]; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $3 (got $1, wanted $2)"; fi; }
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
FE="$HERE/../features.py"
HEREW="$HERE"; command -v cygpath >/dev/null 2>&1 && HEREW="$(cygpath -m "$HERE")"

# a new install: nothing of Lanes here, except a file another hook made just now
export LANES_STATE_DIR="$T/new" LANES_CONFIG="$T/new.conf"
mkdir -p "$T/new"; touch "$T/new/theme-state.json"
"$PY" "$FE" is-on talk_rule; check $? 1 "a new install starts with the talk rule off"
"$PY" "$FE" pending >/dev/null; check $? 0 "a new install has extras to ask about"
out=$(bash "$HERE/../../hooks/talk-rule"); check "${#out}" 0 "the talk-rule hook is quiet while it is off"
"$PY" "$FE" on talk_rule >/dev/null
"$PY" "$FE" is-on talk_rule; check $? 0 "on switches it on"
out=$(bash "$HERE/../../hooks/talk-rule"); case "$out" in *TALK*) check 0 0 "";; *) check 1 0 "the hook speaks once it is on";; esac
out=$("$PY" "$FE" ask --json); check $? 0 "a new install has setup questions"
case "$out" in *update_safety*"Goes well with: Weekly tool reminder"*) check 0 0 "";; *) check 1 0 "update safety is asked, paired with the weekly reminder";; esac
case "$out" in *"https://github.com/TefMeister/BeG0nE"*) check 0 0 "";; *) check 1 0 "every choice carries its read-more link";; esac
"$PY" "$FE" is-on update_safety; check $? 1 "a new install starts with the test builds off"
"$PY" "$FE" off all >/dev/null
"$PY" "$FE" pending >/dev/null; check $? 1 "every extra answered: nothing pending"

# an update: Lanes was here before
export LANES_STATE_DIR="$T/old" LANES_CONFIG="$T/old.conf"
mkdir -p "$T/old"; touch -d "2 days ago" "$T/old/setup-state.json"
"$PY" "$FE" is-on begone_ride; check $? 0 "an update keeps BeG0nE on"
"$PY" "$FE" pending >/dev/null; check $? 1 "an update is asked nothing"
echo "begone_ride = off" > "$T/old.conf"
"$PY" "$FE" is-on begone_ride; check $? 1 "lanes.conf wins on an update too"
"$PY" "$FE" is-on nonsense >/dev/null 2>&1; check $? 1 "an unknown extra is refused"
"$PY" "$FE" is-on update_safety; check $? 0 "an update keeps the test builds on"
"$PY" "$FE" ask >/dev/null; check $? 1 "an update has no setup questions"
"$PY" "$FE" lint >/dev/null; check $? 0 "every extra has a link and a set"
"$PY" -c "import sys; sys.path.insert(0, r'$HEREW/..'); import features as f; f.FEATURES['x']={'label':'X','what':'x','set':'tools','link':f.PROTO_LINK+'99-no-such-section'}; sys.exit(3 if f.lint() else 0)"
check $? 3 "lint refuses a link to a heading that is not there"
"$PY" -c "import sys; sys.path.insert(0, r'$HEREW/..'); import features as f; f.FEATURES['x']={'label':'X','what':'x','set':'tools','link':''}; sys.exit(3 if f.lint() else 0)"
check $? 3 "lint refuses an extra with no link"

echo "features-fixture: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
