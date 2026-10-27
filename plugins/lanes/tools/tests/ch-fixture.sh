#!/usr/bin/env bash
# ch-fixture.sh - tools/ch.py (0.89.0): the repo list, the working copy (a tag and a bundle per repo), code with no
# caller counted across tests and docs, a setting named in a plan but never read, a drifted twin, and the stamp.
# Exit 0 = all passed.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TOOL="$HERE/../ch.py"
PY=""
for cand in python3 python py; do command -v "$cand" >/dev/null 2>&1 && "$cand" -c "" >/dev/null 2>&1 && { PY="$cand"; break; }; done
[ -n "$PY" ] || { echo "ch-fixture: no working Python"; exit 1; }
pass=0; fail=0
check() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; fi; }

T="$(mktemp -d)"
command -v cygpath >/dev/null 2>&1 && T="$(cygpath -m "$T")"
trap 'rm -rf "$T"' EXIT
export LANES_STATE_DIR="$T/state" LANES_CONFIG="$T/lanes.conf" LANES_CH_TODAY=2026-10-27
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t

git init -q --bare "$T/origin.git"
git clone -q "$T/origin.git" "$T/tool" 2>/dev/null
mkdir -p "$T/tool/tests" "$T/tool/docs"
printf 'def used():\n    return 1\n\n\ndef only_tests():\n    return 2\n\n\ndef nobody():\n    return 3\n\n\nprint(used())\n' > "$T/tool/lib.py"
printf 'import lib\nassert lib.only_tests() == 2\n' > "$T/tool/tests/test_lib.py"
printf 'STEP_LIMIT_S = 600\nUSED_S = 5\n' > "$T/tool/settings.py"
printf 'import settings\nprint(settings.USED_S)\n' > "$T/tool/main.py"
printf 'The plan: stop a step after STEP_LIMIT_S seconds.\n' > "$T/tool/docs/plan.md"
git -C "$T/tool" -c core.autocrlf=false add -A && git -C "$T/tool" commit -qm one && git -C "$T/tool" push -q origin HEAD 2>/dev/null
mkdir -p "$T/a" "$T/b"
printf 'x = 1\n# by Tefa\n' > "$T/a/s.lua"; printf 'x = 1\n# by the maintainer\n' > "$T/b/s.lua"
printf 'y = 1\n' > "$T/a/t.lua"; printf 'y = 2\n' > "$T/b/t.lua"
printf 'display_name = Tefa\nch_repo = %s/tool\nch_backup = %s/backups\ntwin = %s/a | %s/b\n' "$T" "$T" "$T" "$T" > "$T/lanes.conf"

out=$("$PY" "$TOOL" repos)
check "the repo list comes from ch_repo" 'printf "%s" "$out" | grep -q "/tool"'
out=$("$PY" "$TOOL" backup)
check "the backup says every repo is saved" 'printf "%s" "$out" | grep -q "Every repo saved."'
check "the tag is on the remote" 'git -C "$T/origin.git" tag | grep -qx pre-ch-2026-10-27'
check "the bundle holds the history" '[ -f "$T/backups/pre-ch-2026-10-27/tool.bundle" ]'

if "$PY" -m vulture --version >/dev/null 2>&1; then
  out=$("$PY" "$TOOL" scan)
  check "a function nobody calls is listed" 'printf "%s" "$out" | grep -q "nobody"'
  check "a function only the tests call is not" '! printf "%s" "$out" | grep -q "only_tests"'
  check "a setting named only in a plan is listed as never read" 'printf "%s" "$out" | grep -A2 "never read" | grep -q STEP_LIMIT_S'
else
  echo "  (vulture not installed: the no-caller checks were skipped)"
fi
out=$("$PY" "$TOOL" scan)
check "a twin that differs is listed by file" 'printf "%s" "$out" | grep -q "differ: t.lua;"'
check "the display name and the maintainer read as the same" '! printf "%s" "$out" | grep -q "s.lua"'
"$PY" "$TOOL" done >/dev/null
check "the run is stamped" 'grep -q 2026-10-27 "$T/state/ch.json"'

echo "ch-fixture: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
