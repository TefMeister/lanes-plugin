#!/usr/bin/env bash
# installed-fixture.sh - tools/installed.py (0.65.0) with two scratch PCs sharing one scratch board: the PC with
# Hand Freeze notes it, the note travels through git, and the other PC's start-up line says it has it; a PC whose
# apps match says nothing. Also owed.sh: another machine's reminder clears only with the person's words.
# Exit 0 = all passed.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TOOL="$HERE/../installed.py"
OWED="$HERE/../owed.sh"
PY=""
for cand in python3 python py; do command -v "$cand" >/dev/null 2>&1 && "$cand" -c "" >/dev/null 2>&1 && { PY="$cand"; break; }; done
[ -n "$PY" ] || { echo "installed-fixture: no working Python"; exit 1; }
pass=0; fail=0
check() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; fi; }

T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
git init -q --bare "$T/remote.git"
git clone -q "$T/remote.git" "$T/a" 2>/dev/null
git clone -q "$T/remote.git" "$T/b" 2>/dev/null
mkdir -p "$T/a/status" "$T/hf"
printf x > "$T/hf/HandFreeze.exe"; echo v9 > "$T/hf/lanes-release.txt"
printf 'machine_name = PCA\n' > "$T/a.conf"; printf 'machine_name = PCB\n' > "$T/b.conf"

out="$(LANES_BOARD="$T/a" LANES_CONFIG="$T/a.conf" LANES_HANDFREEZE_DIR="$T/hf" "$PY" "$TOOL" brief)"
check "the PC with the app writes its note" '[ -f "$T/a/installed/PCA.json" ] && grep -q v9 "$T/a/installed/PCA.json"'
check "and says the note is not saved yet" 'printf "%s" "$out" | grep -q "saved with the board"'
(cd "$T/a" && git add installed status 2>/dev/null; git -c user.name=t -c user.email=t@t commit -q -m a && git push -q origin HEAD:main) >/dev/null 2>&1

out="$(LANES_BOARD="$T/b" LANES_CONFIG="$T/b.conf" LANES_HANDFREEZE_DIR="$T/none" "$PY" "$TOOL" brief)"
check "the other PC learns it from GitHub's copy" 'printf "%s" "$out" | grep -q "PCA has Hand Freeze (v9"'

out="$(LANES_BOARD="$T/a" LANES_CONFIG="$T/a.conf" LANES_HANDFREEZE_DIR="$T/hf" "$PY" "$TOOL" brief)"
check "a PC that matches everyone says nothing" '[ -z "$out" ]'

mkdir -p "$T/a/owed/OTHERPC"; echo "# Install X" > "$T/a/owed/OTHERPC/2026-10-14-x.md"
LANES_BOARD="$T/a" GATE_ROLE=DEV bash "$OWED" done 2026-10-14-x.md OTHERPC >/dev/null 2>&1
check "another machine's reminder does not clear without the person's words" '[ -f "$T/a/owed/OTHERPC/2026-10-14-x.md" ]'
LANES_BOARD="$T/a" GATE_ROLE=DEV bash "$OWED" done 2026-10-14-x.md OTHERPC "tested it there" >/dev/null 2>&1
check "and clears with them" '[ ! -f "$T/a/owed/OTHERPC/2026-10-14-x.md" ]'

echo "installed-fixture: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
