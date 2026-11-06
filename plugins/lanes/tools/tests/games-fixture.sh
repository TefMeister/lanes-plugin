#!/usr/bin/env bash
# games-fixture.sh - tools/games.py (0.95.0) against a fake Steam folder, a scratch record folder and a scratch live
# root: a fresh record is silent; a store update, a game taken off, a changed main program, a new project folder and a
# project that left the root are each named; a Steam folder seen in another letter case is not a move; no login path
# is ever written into the record. Exit 0 = all passed.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TOOL="$HERE/../games.py"
PY=""
for cand in python3 python py; do command -v "$cand" >/dev/null 2>&1 && "$cand" -c "" >/dev/null 2>&1 && { PY="$cand"; break; }; done
[ -n "$PY" ] || { echo "games-fixture: no working Python"; exit 1; }
pass=0; fail=0
check() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; fi; }

T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
T="$(cygpath -m "$T" 2>/dev/null || printf '%s' "$T")"   # Windows Python reads the paths written into lanes.conf
S="$T/Steam"; mkdir -p "$S/steamapps/common/Game One" "$T/root/rec" "$T/root/p1/dev-archive" "$T/root/p2/dev-archive" \
  "$T/root/tool" "$T/nonsteam/bin"
for d in rec p1 p2 tool; do git init -q "$T/root/$d"; done
acf() { printf '"AppState"\n{\n\t"appid"\t\t"100"\n\t"name"\t\t"Game One"\n\t"StateFlags"\t\t"4"\n\t"installdir"\t\t"Game One"\n\t"buildid"\t\t"%s"\n}\n' "$1" > "$S/steamapps/appmanifest_100.acf"; }
acf 111
printf 'MZ-one' > "$T/nonsteam/bin/game.exe"
cat > "$T/lanes.conf" <<EOF
machine_name = PCT
games_record = $T/root/rec
game_dir.p2 = $T/nonsteam
game_exe.p2 = bin/game.exe
EOF
run() { LANES_CONFIG="$T/lanes.conf" LANES_STEAM_ROOTS="$S" "$PY" "$TOOL" "$@" 2>&1; }

out="$(run check)"
check "with no game list it says so instead of guessing" 'printf "%s" "$out" | grep -q "games.tsv is empty"'
run set p1 steam 100 >/dev/null
run set p2 folder Game Two >/dev/null
run set tool none >/dev/null
check "set takes the title from Steam when none is given" 'grep -q "Game One" "$T/root/rec/games.tsv"'
out="$(run check)"
check "a PC with no record is asked to make one" 'printf "%s" "$out" | grep -q "no games record yet"'
run record >/dev/null
check "the record is written under the PC's own name" '[ -f "$T/root/rec/PCT-games.tsv" ]'
out="$(run check)"
check "a fresh record is silent" '[ -z "$out" ]'

acf 222
out="$(run check)"
check "a store update is named with both build numbers" 'printf "%s" "$out" | grep -q "GAME UPDATED: Game One (p1).*111 -> 222"'
acf 111

printf 'MZ-two-longer' > "$T/nonsteam/bin/game.exe"
out="$(run check)"
check "a replaced main program of a game no store knows is named" 'printf "%s" "$out" | grep -q "GAME CHANGED: Game Two (p2)"'
run record >/dev/null

mv "$S/steamapps/common/Game One" "$S/steamapps/common/gone"
out="$(run check)"
check "a game taken off the PC is named" 'printf "%s" "$out" | grep -q "GAME GONE: Game One"'
mv "$S/steamapps/common/gone" "$S/steamapps/common/Game One"

mkdir -p "$T/root/p3/engine-research"; git init -q "$T/root/p3"
out="$(run check)"
check "a new project folder with no game set is named" 'printf "%s" "$out" | grep -q "NEW PROJECT: p3"'
rm -rf "$T/root/p3" "$T/root/p1"
out="$(run check)"
check "a project that left the root is named" 'printf "%s" "$out" | grep -q "GONE PROJECT: p1"'
check "the tool row (none) is never called gone" '! printf "%s" "$out" | grep -q "GONE PROJECT: tool"'
mkdir -p "$T/root/p1/dev-archive"; git init -q "$T/root/p1"
# 2026-11-05: which root holds the projects differs by PC. The dev PC's `root =` is its sweep root (missing new clones)
# while its board sits in the live root; the home PC's board sits in the home folder while `root =` is the live root.
# The root that holds most of the listed projects wins, so neither PC sees false GONE lines.
mkdir -p "$T/sweep/p1/dev-archive"; git init -q "$T/sweep/p1"
mkdir -p "$T/root/board"; git init -q "$T/root/board"
cp "$T/lanes.conf" "$T/lanes.conf.bak"
printf 'root = %s\nboard = %s\n' "$T/sweep" "$T/root/board" >> "$T/lanes.conf"
out="$(run check)"
check "a sweep root that lacks a clone does not call it gone (dev PC shape)" '! printf "%s" "$out" | grep -q "GONE PROJECT"'
mkdir -p "$T/elsewhere/board"; git init -q "$T/elsewhere/board"
cp "$T/lanes.conf.bak" "$T/lanes.conf"
printf 'root = %s\nboard = %s\n' "$T/root" "$T/elsewhere/board" >> "$T/lanes.conf"
out="$(run check)"
check "a board outside the clone root still finds every project (home PC shape)" '! printf "%s" "$out" | grep -q "GONE PROJECT"'
cp "$T/lanes.conf.bak" "$T/lanes.conf"; rm -rf "$T/sweep" "$T/home" "$T/root/board"
rm -rf "$T/root/p1"
mkdir -p "$T/root/p1/dev-archive"; git init -q "$T/root/p1"

UPPER="$(printf '%s' "$S" | tr '[:lower:]' '[:upper:]')"
if [ -d "$UPPER" ]; then   # case-insensitive disks (Windows): the same Steam seen in other letters is no move
  out="$(LANES_CONFIG="$T/lanes.conf" LANES_STEAM_ROOTS="$UPPER" "$PY" "$TOOL" check 2>&1)"
  check "the same folder in other letter case is not a move" '! printf "%s" "$out" | grep -q "GAME MOVED"'
fi

out="$(run overview)"
check "the overview counts the games on this PC" 'printf "%s" "$out" | grep -q "2 of 2 project games are on this PC"'
home="$("$PY" -c 'import os; print(os.path.expanduser("~"))')"
check "no home-folder path is written into the record" '! grep -qiF "$home" "$T/root/rec/PCT-games.tsv"'

echo "games-fixture: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
