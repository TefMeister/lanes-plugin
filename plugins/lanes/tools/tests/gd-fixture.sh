#!/usr/bin/env bash
# gd-fixture.sh - tools/gd.py (0.88.0): shelving a run's logs by name, never twice, leaving a file still being
# written, BeG0nE reports without their raw numbers, read marks per PC, folding repeated lines, and the weekly nudge.
# Exit 0 = all passed.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TOOL="$HERE/../gd.py"
PY=""
for cand in python3 python py; do command -v "$cand" >/dev/null 2>&1 && "$cand" -c "" >/dev/null 2>&1 && { PY="$cand"; break; }; done
[ -n "$PY" ] || { echo "gd-fixture: no working Python"; exit 1; }
pass=0; fail=0
check() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; fi; }

T="$(mktemp -d)"
command -v cygpath >/dev/null 2>&1 && T="$(cygpath -m "$T")"
trap 'rm -rf "$T"' EXIT
export LANES_STATE_DIR="$T/state" LANES_CONFIG="$T/lanes.conf"
printf 'transfer = %s/mega\nmachine_name = PCX\nbegone = %s/begone\n' "$T" "$T" > "$T/lanes.conf"
G="$T/mega/Gold Digger/game-vr"
old() { touch -d '10 minutes ago' "$@"; }

mkdir -p "$T/game/logs"
for i in 1 2 3; do printf 'frame %s took 16.%s ms\n' "$i" "$i"; done > "$T/game/logs/framework_log.txt"
printf 'ERROR: could not open weapon_scope.pak\n' >> "$T/game/logs/framework_log.txt"
printf 'camera pose 1\n' > "$T/game/logs/camera_dump.txt"
old "$T/game/logs/framework_log.txt" "$T/game/logs/camera_dump.txt"
printf 'still writing\n' > "$T/game/logs/hot.log"

out=$("$PY" "$TOOL" where); out=$(printf '%s' "$out" | tr '\\' '/')
check "the folder is <transfer>/Gold Digger" '[ "$out" = "$T/mega/Gold Digger" ]'
"$PY" "$TOOL" sources game-vr add "$T/game/logs/*" >/dev/null
check "places are kept per PC" '[ -f "$G/SOURCES-PCX.txt" ]'
out=$("$PY" "$TOOL" shelve game-vr)
check "a game log goes on the logs shelf" 'ls "$G/logs" | grep -q "_PCX_framework_log.txt"'
check "a camera dump goes on the camera shelf" 'ls "$G/camera" | grep -q camera_dump.txt'
check "a file changed a moment ago is left for next time" '! ls -R "$G" | grep -q hot.log && printf "%s" "$out" | grep -q "left for next time"'
check "the original stays where it was" '[ -f "$T/game/logs/framework_log.txt" ]'
out=$("$PY" "$TOOL" shelve game-vr)
check "the same contents are not shelved twice" 'printf "%s" "$out" | grep -q "nothing new"'
printf 'frame 9 took 17.0 ms\n' >> "$T/game/logs/framework_log.txt"; old "$T/game/logs/framework_log.txt"
"$PY" "$TOOL" shelve game-vr >/dev/null
check "a changed log is shelved again (a new run)" '[ "$(ls "$G/logs" | wc -l)" -eq 2 ]'

mkdir -p "$T/begone/camera-jitter/data/game-vr/2026-10-26_12-00-00_openxr"
R="$T/begone/camera-jitter/data/game-vr/2026-10-26_12-00-00_openxr"
printf '# report\n' > "$R/report.md"; printf '{"raw": 1}' > "$R/summary.json"
"$PY" "$TOOL" shelve game-vr >/dev/null
check "a BeG0nE jitter report lands on the jitter shelf" 'ls "$G/jitter" | grep -q "begone-camera-jitter_2026-10-26_12-00-00_openxr"'
check "the raw numbers are not copied" '! ls -R "$G/jitter" | grep -q summary.json'
"$PY" "$TOOL" shelve game-vr >/dev/null
check "a BeG0nE report is shelved once" '[ "$(ls "$G/jitter" | wc -l)" -eq 1 ]'

out=$("$PY" "$TOOL" list game-vr)
check "list counts the unread items" 'printf "%s" "$out" | grep -q "4 item(s), 4 not read"'
out=$("$PY" "$TOOL" unsifted game-vr guns)
check "a log that mentions guns once is not put on the guns shelf" 'printf "%s" "$out" | grep -q "nothing waiting on guns"'
printf 'aim
reload
ammo 3
rifle
shotgun
' > "$T/game/console.txt"; old "$T/game/console.txt"
"$PY" "$TOOL" add game-vr "$T/game/console.txt" >/dev/null
out=$("$PY" "$TOOL" unsifted game-vr guns)
check "a log full of gun words is found from the guns shelf too" 'printf "%s" "$out" | grep -q "console.txt.*also: guns"'
id=$("$PY" "$TOOL" unsifted game-vr camera | grep camera_dump | cut -d" " -f1)
"$PY" "$TOOL" sifted game-vr "$id" >/dev/null
check "read marks are kept per PC" 'grep -q "$id" "$G/SIFTED-PCX.tsv"'
out=$("$PY" "$TOOL" list game-vr)
check "a read item no longer counts as waiting" 'printf "%s" "$out" | grep -q "5 item(s), 4 not read"'
check "nothing was ever deleted" '[ "$(find "$G" -mindepth 2 -maxdepth 2 -name "*_PCX_*" | wc -l)" -eq 5 ]'

out=$("$PY" "$TOOL" fold "$T/game/logs/framework_log.txt")
check "repeated lines fold into one with a count" 'printf "%s" "$out" | grep -q "x4 (1-5)"'
check "an error line is marked" 'printf "%s" "$out" | grep -q "^W .*could not open"'
printf 'frame 1 took 1 ms\nnew thing happened\n' > "$T/b.txt"
out=$("$PY" "$TOOL" fold "$T/b.txt" --against "$T/game/logs/framework_log.txt")
check "--against keeps only what the older run did not have" 'printf "%s" "$out" | grep -q "new thing" && ! printf "%s" "$out" | grep -q "frame 1"'

out=$("$PY" "$TOOL" nudge)
check "the nudge speaks when items wait and no full scan ever ran" 'printf "%s" "$out" | grep -q "never run"'
"$PY" "$TOOL" fullscan-done >/dev/null
out=$("$PY" "$TOOL" nudge)
check "the nudge is silent right after a full scan" '[ -z "$out" ]'
printf '{"last_fullscan": "2026-01-01"}' > "$T/state/gd.json"
out=$("$PY" "$TOOL" nudge)
check "the nudge speaks a week later" 'printf "%s" "$out" | grep -q "days ago"'

echo "gd-fixture: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
