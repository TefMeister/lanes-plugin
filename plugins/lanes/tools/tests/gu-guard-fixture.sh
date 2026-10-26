#!/usr/bin/env bash
# gu-guard-fixture.sh - tools/gu_guard.py (0.83.0): updates sorted into build-critical and low risk, a baseline, an
# update that breaks a check caught by `after`, one that breaks nothing passing, and `putback` naming the old
# version. No installer is ever run (LANES_GUARD_FAKE_VERSIONS). Exit 0 = all passed.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TOOL="$HERE/../gu_guard.py"
PY=""
for cand in python3 python py; do command -v "$cand" >/dev/null 2>&1 && "$cand" -c "" >/dev/null 2>&1 && { PY="$cand"; break; }; done
[ -n "$PY" ] || { echo "gu-guard-fixture: no working Python"; exit 1; }
pass=0; fail=0
check() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; fi; }

T="$(mktemp -d)"
command -v cygpath >/dev/null 2>&1 && T="$(cygpath -m "$T")"
trap 'rm -rf "$T"' EXIT
export LANES_STATE_DIR="$T/state" LANES_CONFIG="$T/lanes.conf" LANES_GUARD_FAKE_VERSIONS="$T/versions.json"
mkdir -p "$T/proj"
printf '{"winget:MartinStorsjo.LLVM-MinGW.UCRT": "20260908", "pip:mcp": "1.29.0"}' > "$T/versions.json"
# the "build": passes while broken.txt is absent
printf '#!/bin/bash\n[ ! -f broken.txt ] && echo built || { echo "error: the compiler moved"; exit 1; }\n' > "$T/proj/build.sh"
cat > "$T/lanes.conf" <<EOF
build_check = proj | $T/proj | bash build.sh
build_check = always fails | - | bash -c "exit 3"
critical = 7zip | a test entry: named critical by hand
EOF

out=$("$PY" "$TOOL" risk winget:MartinStorsjo.LLVM-MinGW.UCRT winget:RARLab.WinRAR winget:7zip.7zip pip:mcp:1.29.0:2.3.0 pip:pillow:12.1:12.2 winget:Microsoft.VisualStudio.2022.BuildTools winget:Microsoft.VisualStudioCode 2>&1)
check "the compiler is build-critical" 'echo "$out" | grep -q "^BUILD-CRITICAL	winget:MartinStorsjo.LLVM-MinGW.UCRT"'
check "an archiver is low risk" 'echo "$out" | grep -q "^low	winget:RARLab.WinRAR	no known risk"'
check "lanes.conf critical = adds one" 'echo "$out" | grep -q "^BUILD-CRITICAL	winget:7zip.7zip	a test entry"'
check "a pip major jump is build-critical" 'echo "$out" | grep -q "^BUILD-CRITICAL	pip:mcp:1.29.0:2.3.0	a major version"'
check "a pip minor bump is low risk" 'echo "$out" | grep -q "^low	pip:pillow"'
check "Visual Studio build tools are build-critical" 'echo "$out" | grep -q "^BUILD-CRITICAL	winget:Microsoft.VisualStudio"'
check "VS Code (an editor) is low risk" 'echo "$out" | grep -q "^low	winget:Microsoft.VisualStudioCode	no known risk"'

out=$("$PY" "$TOOL" checks 2>&1)
check "checks lists both" 'echo "$out" | grep -q "proj: bash build.sh" && echo "$out" | grep -q "always fails"'

out=$("$PY" "$TOOL" before winget:MartinStorsjo.LLVM-MinGW.UCRT 2>&1)
check "before notes the version replaced" 'echo "$out" | grep -q "now 20260908"'
check "before: the project builds" 'echo "$out" | grep -q "proj: builds"'
check "before: an already-failing check is named" 'echo "$out" | grep -q "Already failing before any update (they cannot judge it): always fails"'

out=$("$PY" "$TOOL" after 2>&1); rc=$?
check "after with nothing broken says SAFE (exit 0)" '[ $rc -eq 0 ] && echo "$out" | grep -q "^SAFE"'
check "a check failing before AND after is not blamed on the update" '! echo "$out" | grep -q "BROKEN"'

touch "$T/proj/broken.txt"
out=$("$PY" "$TOOL" after 2>&1); rc=$?
check "after a breaking update: exit 1, names the check" '[ $rc -eq 1 ] && echo "$out" | grep -q "BROKEN BY THE UPDATE: proj"'
check "after shows what broke" 'echo "$out" | grep -q "the compiler moved"'
check "after names the version to go back to" 'echo "$out" | grep -q "winget:MartinStorsjo.LLVM-MinGW.UCRT: back to 20260908"'

out=$("$PY" "$TOOL" putback winget:MartinStorsjo.LLVM-MinGW.UCRT 2>&1)
check "putback installs the exact old version" 'echo "$out" | grep -q "would run: winget install --id MartinStorsjo.LLVM-MinGW.UCRT --exact --version 20260908 --force"'
out=$("$PY" "$TOOL" putback pip:never-noted 2>&1); rc=$?
check "putback of something not noted refuses" '[ $rc -eq 2 ] && echo "$out" | grep -q "cannot be put back"'

echo "gu-guard-fixture: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
