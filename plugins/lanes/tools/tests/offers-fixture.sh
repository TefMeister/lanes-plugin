#!/usr/bin/env bash
# offers-fixture.sh - tools/offers.py and tools/thanks.py (0.75.0) in a scratch folder with a stand-in gh.
# An offer is made once whatever the answer; thanks is off until switched on, refuses without the follow permission,
# and stars + follows (and logs) once it has it. Exit 0 = all passed.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PY=""
for cand in python3 python py; do command -v "$cand" >/dev/null 2>&1 && "$cand" -c "" >/dev/null 2>&1 && { PY="$cand"; break; }; done
[ -n "$PY" ] || { echo "offers-fixture: no working Python"; exit 1; }
pass=0; fail=0
check() { if [ "$1" = "$2" ]; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $3 (got $1, wanted $2)"; fi; }
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
export LANES_STATE_DIR="$T/state" LANES_CONFIG="$T/lanes.conf"
OF="$HERE/../offers.py"; TH="$HERE/../thanks.py"

"$PY" "$OF" should thanks >/dev/null; check $? 0 "a new offer is to be made"
"$PY" "$OF" made thanks no >/dev/null
"$PY" "$OF" should thanks >/dev/null; check $? 3 "an offer answered no is not made again"
"$PY" "$OF" made shortcut yes >/dev/null
"$PY" "$OF" should shortcut >/dev/null; check $? 3 "an offer answered yes is not made again"
"$PY" "$OF" should openxr-sim >/dev/null; check $? 0 "another offer is still to be made"

# a stand-in gh: auth status prints the scopes in $T/scopes, api calls are written to $T/calls
cat > "$T/gh.py" <<'EOF'
import os, sys
T = os.path.dirname(os.path.abspath(__file__))
if sys.argv[1:3] == ["auth", "status"]:
    print("Logged in to github.com\n  - Token scopes: " + open(os.path.join(T, "scopes")).read().strip()); sys.exit(0)
open(os.path.join(T, "calls"), "a").write(" ".join(sys.argv[1:]) + "\n")
EOF
W() { if command -v cygpath >/dev/null 2>&1; then cygpath -w "$1"; else printf '%s' "$1"; fi; }
printf '@echo off\r\n"%s" "%s" %%*\r\n' "$(W "$(command -v "$PY")")" "$(W "$T/gh.py")" > "$T/gh.cmd"
printf '#!/usr/bin/env bash\nexec "%s" "%s" "$@"\n' "$(command -v "$PY")" "$T/gh.py" > "$T/gh"; chmod +x "$T/gh"
if [ "${OS:-}" = "Windows_NT" ]; then export LANES_GH="$(W "$T/gh.cmd")"; else export LANES_GH="$T/gh"; fi
echo "'gist', 'repo'" > "$T/scopes"

"$PY" "$TH" add someone/tool >/dev/null; check $? 2 "thanks does nothing while it is off"
"$PY" "$TH" on >/dev/null
grep -q "^thanks = yes" "$T/lanes.conf"; check $? 0 "on writes thanks = yes"
out=$("$PY" "$TH" add someone/tool); check $? 1 "without the follow permission it refuses"
printf '%s' "$out" | grep -q "user:follow"; check $? 0 "it names the permission to ask for"
[ -f "$T/calls" ]; check $? 1 "nothing was starred half-way"
echo "'gist', 'repo', 'user:follow'" > "$T/scopes"
"$PY" "$TH" add https://github.com/someone/tool/issues/3 --why "one useful fact" >/dev/null; check $? 0 "with it, add works"
grep -q "user/starred/someone/tool" "$T/calls"; check $? 0 "the project is starred"
grep -q "user/following/someone" "$T/calls"; check $? 0 "its owner is followed"
grep -q "one useful fact" "$LANES_STATE_DIR/thanks-log.tsv"; check $? 0 "the reason is logged"
"$PY" "$TH" off >/dev/null
grep -q "^thanks = no" "$T/lanes.conf"; check $? 0 "off writes thanks = no"

[ "$fail" -eq 0 ] || exit 1
echo "offers + thanks: $pass checks passed"
