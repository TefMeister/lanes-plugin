#!/usr/bin/env bash
# menu-o-matic-fixture.sh - runs Menu-o-matiC's offline route tests (no window, no app).
# Needs Pillow; without it the test is skipped, not failed, because Pillow is an optional tool.
#   bash tools/tests/menu-o-matic-fixture.sh
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TEST="$(cd "$HERE/.." && pwd)/menu-o-matic/test_menu_o_matic.py"
PY=""
for cand in python3 python py; do
  command -v "$cand" >/dev/null 2>&1 || continue
  "$cand" -c "" >/dev/null 2>&1 || continue
  PY="$cand"; break
done
[ -n "$PY" ] || { echo "skip: no python"; exit 0; }
"$PY" -c "import PIL" >/dev/null 2>&1 || { echo "skip: Pillow is not installed (python -m pip install pillow)"; exit 0; }
out=$("$PY" "$TEST" 2>&1); rc=$?
printf '%s\n' "$out" | grep "^FAIL" || true
n=$(printf '%s\n' "$out" | grep -c "^ok")
[ "$rc" -eq 0 ] && echo "menu-o-matic: $n checks passed" || { echo "menu-o-matic: FAILED"; exit 1; }
