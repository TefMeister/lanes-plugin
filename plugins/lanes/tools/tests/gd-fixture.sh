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
# the same report on the other PC, its line endings changed by git on the way: still shelved once (2026-11-05)
printf 'transfer = %s/mega\nmachine_name = PCY\nbegone = %s/begone-y\n' "$T" "$T" > "$T/lanes-y.conf"
mkdir -p "$T/begone-y/camera-jitter/data/game-vr/2026-10-26_12-00-00_openxr"
printf '# report\r\n' > "$T/begone-y/camera-jitter/data/game-vr/2026-10-26_12-00-00_openxr/report.md"
LANES_CONFIG="$T/lanes-y.conf" LANES_STATE_DIR="$T/state-y" "$PY" "$TOOL" shelve game-vr >/dev/null
check "the same BeG0nE run from the other PC is not shelved again" '[ "$(ls "$G/jitter" | wc -l)" -eq 1 ]'

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
printf 'Game Module Addr: 7ff6160b0000\na facade opened\n' > "$T/c1.txt"
printf 'Game Module Addr: 7ff7a91c0000\na facade closed\n' > "$T/c2.txt"
out=$("$PY" "$TOOL" fold "$T/c2.txt" --against "$T/c1.txt")
check "--against ignores a moved address but keeps a changed word" '! printf "%s" "$out" | grep -q "Module Addr" && printf "%s" "$out" | grep -q "facade closed"'
{ echo "time,uptime_s,game_fps,game_stutters"; for s in $(seq 1 300); do if [ "$s" -gt 120 ] && [ "$s" -le 180 ]; then echo "x,$s,38,4"; else echo "x,$s,95,0"; fi; done; } > "$T/perf.csv"
out=$("$PY" "$TOOL" fold "$T/perf.csv")
check "a frame-rate table is read by minute and only the bad minute is shown" 'printf "%s" "$out" | grep -q "^! minute   2: game_fps 38" && [ "$(printf "%s" "$out" | grep -c "^! minute")" -eq 1 ]'
out=$("$PY" "$TOOL" fold "$T/not-there.txt" 2>&1)
check "a missing file is said in one line, no traceback" 'printf "%s" "$out" | grep -q "no such file" && ! printf "%s" "$out" | grep -q Traceback'

# the digest: each unread copy against every earlier copy of the same kind (2026-11-05)
mkdir -p "$T/dg"
printf 'start 1\nERROR: lamp missing\n' > "$T/dg/mod.log"; old "$T/dg/mod.log"
"$PY" "$TOOL" add dg-vr "$T/dg/mod.log" >/dev/null
printf 'start 2\nERROR: lamp missing\n' > "$T/dg/mod.log"; old "$T/dg/mod.log"
"$PY" "$TOOL" add dg-vr "$T/dg/mod.log" >/dev/null
printf 'start 3\nERROR: lamp missing\nnew gun found\n' > "$T/dg/mod.log"; old "$T/dg/mod.log"
"$PY" "$TOOL" add dg-vr "$T/dg/mod.log" >/dev/null
out=$("$PY" "$TOOL" digest dg-vr)
check "the digest counts a copy with nothing new as a repeat" 'printf "%s" "$out" | grep -q "3 copies, 3 not read; 2 add something new, 1 are only repeats"'
check "the digest shows only the line no earlier copy had" 'printf "%s" "$out" | grep -q "new gun found" && [ "$(printf "%s" "$out" | grep -c "start")" -eq 0 ]'
check "the digest shows the first copy's warnings once" '[ "$(printf "%s" "$out" | grep -c "lamp missing")" -eq 1 ]'

# ---- 0.112.0: rotated logs are one log, crash dumps are read as crash records, an older shelf name is joined ----
mkdir -p "$T/rot"
printf 'start\nall good\n' > "$T/rot/darknessrecomp_024.log"
printf 'start\nall good\nERROR: shader 7 failed\n' > "$T/rot/darknessrecomp_024.9.log"
printf 'start\nall good\nrun took 25 s\n' > "$T/rot/darknessrecomp_025.log"
for f in darknessrecomp_024.log darknessrecomp_024.9.log darknessrecomp_025.log; do
  "$PY" "$TOOL" add rot-vr "$T/rot/$f" --shelf logs >/dev/null; sleep 1
done
out=$("$PY" "$TOOL" digest rot-vr logs)
check "rotated logs (name_024.9.log, name_025.log) are copies of ONE log" 'printf "%s" "$out" | grep -q "darknessrecomp#.log: 3 copies"'
check "and only the new line of a rotated copy is shown" 'printf "%s" "$out" | grep -q "shader 7 failed" && ! printf "%s" "$out" | grep -q "all good"'
mkdir -p "$T/dumps"
"$PY" - "$T/dumps" <<'EOF'
import os, struct, sys
def dump(path, code, addr, steam_gone, thread=1):
    names = ["C:\\Game\\game.exe", "C:\\Game\\UEVRBackend.dll"] + ([] if steam_gone else ["C:\\Game\\steam_api64.dll"])
    gone = ["C:\\Steam\\steamclient64.dll"] if steam_gone else []
    blobs = b""
    def s(text):
        nonlocal blobs
        rva = 512 + len(blobs)
        raw = text.encode("utf-16-le")
        blobs += struct.pack("<I", len(raw)) + raw + b"\0\0"
        return rva
    mods = [(0x140000000, 0x100000, s(names[0])), (0x7FF800000000, 0x200000, s(names[1]))]
    if not steam_gone:
        mods.append((0x7FF900000000, 0x10000, s(names[2])))
    unl = [(0x7FFA00000000, 0x10000, s(n)) for n in gone]
    modlist = struct.pack("<I", len(mods)) + b"".join(struct.pack("<QIIII", b, z, 0, 0, r) + b"\0" * 84 for b, z, r in mods)
    unlist = struct.pack("<III", 12, 24, len(unl)) + b"".join(struct.pack("<QIIII", b, z, 0, 0, r) for b, z, r in unl)
    exc = struct.pack("<II", thread, 0) + struct.pack("<IIQQII", code, 0, 0, addr, 2, 0) + struct.pack("<15Q", 0, 0x58, *[0] * 13) + b"\0" * 8
    body_rva = 512 + len(blobs)
    streams, body = [], b""
    for kind, data in ((4, modlist), (6, exc), (14, unlist)):
        streams.append((kind, len(data), body_rva + len(body)))
        body += data
    head = b"MDMP" + struct.pack("<IIII", 0xA793, len(streams), 32, 0) + b"\0" * 12
    directory = b"".join(struct.pack("<III", *x) for x in streams)
    open(path, "wb").write((head + directory).ljust(512, b"\0") + blobs + body)
d = sys.argv[1]
dump(os.path.join(d, "game.exe.111.dmp"), 0xC0000005, 0x7FF800001234, False)
dump(os.path.join(d, "game.exe.222.dmp"), 0xC0000005, 0x7FF800001234, False, thread=2)
dump(os.path.join(d, "game.exe.333.dmp"), 0xC0000409, 0x7FF800005678, True)
EOF
for f in game.exe.111.dmp game.exe.222.dmp game.exe.333.dmp; do
  "$PY" "$TOOL" add dump-vr "$T/dumps/$f" --shelf crashes >/dev/null; sleep 1
done
out=$("$PY" "$TOOL" digest dump-vr crashes)
check "a dump is read as its crash record: code and module+offset" 'printf "%s" "$out" | grep -q "crash 0xC0000005 access violation.* in UEVRBackend.dll+0x1234"'
check "an access violation says what it touched" 'printf "%s" "$out" | grep -q "reading address 0x58 (a null pointer)"'
check "dumps of different processes are one kind" 'printf "%s" "$out" | grep -q "game.exe#.dmp: 3 copies"'
check "the same crash again is a repeat" 'printf "%s" "$out" | grep -q "2 add something new, 1 are only repeats"'
check "a dump says Steam was already unloaded" 'printf "%s" "$out" | grep -q "Steam was already unloaded: steamclient64.dll"'
check "no raw memory strings from a dump" '! printf "%s" "$out" | grep -q "MDMP"'
check "fold reads one dump the same way" '"$PY" "$TOOL" fold "$T/dumps/game.exe.333.dmp" | grep -q "crash 0xC0000409"'
"$PY" "$TOOL" add old-name "$T/rot/darknessrecomp_024.log" --shelf logs >/dev/null
out=$("$PY" "$TOOL" also rot-vr old-name)
check "an older shelf name is joined, nothing moved" 'printf "%s" "$out" | grep -q "now also reads the shelves named old-name (1 item" && [ -d "$T/mega/Gold Digger/old-name" ]'
out=$("$PY" "$TOOL" digest rot-vr logs)
check "the digest reads the older name's items too" 'printf "%s" "$out" | grep -q "darknessrecomp#.log: 4 copies"'
check "joining twice is said, not repeated" '"$PY" "$TOOL" also rot-vr old-name | grep -q "already read"'

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
