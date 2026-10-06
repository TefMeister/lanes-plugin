#!/usr/bin/env bash
# builds-fixture.sh - asserts builds.py keeps every build, keeps two PCs' numbers apart, and never
# pushes a local-only file. Plays two PCs against one bare "GitHub" repo in a temp folder, and never
# reads or writes the real lanes.conf (LANES_CONFIG points at a scratch file).
#   bash tools/tests/builds-fixture.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TOOL="$(cd "$HERE/.." && pwd)/builds.py"
PY=""
for cand in python3 python py; do
  command -v "$cand" >/dev/null 2>&1 || continue
  "$cand" -c "" >/dev/null 2>&1 || continue
  PY="$cand"; break
done
[ -n "$PY" ] || { echo "builds-fixture: no working python"; exit 2; }

T="$(mktemp -d)"; T="$(cygpath -m "$T" 2>/dev/null || echo "$T")"; trap 'rm -rf "$T"' EXIT
FAILED=0; N=0
ok()   { N=$((N+1)); printf '  ok    %s\n' "$1"; }
fail() { N=$((N+1)); printf '  FAIL  %s\n' "$1"; FAILED=1; }
has()  { case "$2" in *"$1"*) ok "$3" ;; *) fail "$3 (expected: $1)" ;; esac; }
hasnt(){ case "$2" in *"$1"*) fail "$3 (did NOT expect: $1)" ;; *) ok "$3" ;; esac; }

export GIT_AUTHOR_NAME=fixture GIT_AUTHOR_EMAIL=fixture@example.invalid
export GIT_COMMITTER_NAME=fixture GIT_COMMITTER_EMAIL=fixture@example.invalid
git init -q --bare -b main "$T/remote.git"
git clone -q "$T/remote.git" "$T/pc1" 2>/dev/null
git -C "$T/pc1" commit -q --allow-empty -m start && git -C "$T/pc1" push -q -u origin main 2>/dev/null
git clone -q "$T/remote.git" "$T/pc2" 2>/dev/null

APP="$T/app"; mkdir -p "$APP/mods/data" "$APP/mods/edited"
echo game > "$APP/game.exe"; echo v1 > "$APP/mod.dll"; echo cfg > "$APP/mods/data/a.txt"
echo edited-game-file > "$APP/mods/edited/level.pak"; echo noise > "$APP/mods/log.txt"
printf 'builds_app.proj = %s\n' "$APP" > "$T/lanes.conf"
export LANES_CONFIG="$T/lanes.conf"
pc() { local who="$1"; shift; LANES_BUILDS="$T/$who" "$PY" "$TOOL" "$@" 2>&1; }

echo "init + snap"
out=$(pc pc1 init proj --app "$APP" --ours mod.dll --ours mods --skip log.txt --local-only mods/edited --series 1.0.0)
has "PROJECT.conf" "$out" "init writes the project settings"
out=$(pc pc1 snap proj "first" --note "the first build")
has "v1.0.0-b001 - first" "$out" "first build is b001"
has "github: pushed" "$out" "the build is pushed"
B1="$T/pc1/proj/v1.0.0-b001 - first"
[ -f "$B1/mod.dll" ] && ok "our file is copied" || fail "our file is copied"
[ -f "$B1/game.exe" ] && fail "the app's own file is NOT copied" || ok "the app's own file is NOT copied"
[ -f "$B1/mods/log.txt" ] && fail "skipped file is not copied" || ok "skipped file is not copied"
[ -f "$B1/mods/edited/level.pak" ] && ok "local-only file is kept on the PC" || fail "local-only file is kept on the PC"
tracked=$(git -C "$T/pc1" ls-files)
hasnt "level.pak" "$tracked" "local-only file is never committed"
has "mods/data/a.txt" "$tracked" "an ordinary file of ours is committed"
has "mods/edited/level.pak" "$(cat "$B1/MANIFEST.sha256")" "local-only file is still in the manifest"

echo "which"
out=$(pc pc1 which proj); has "holds v1.0.0-b001" "$out" "which: the app folder matches b001"
echo v2 > "$APP/mod.dll"
out=$(pc pc1 which proj); has "matches NO saved build" "$out" "which: an unsaved change is reported"

echo "two PCs make the same number at the same moment"
git -C "$T/pc2" pull -q --rebase 2>/dev/null
out=$(pc pc1 snap proj "pc1 change" --note "from pc1"); has "b002" "$out" "pc1 makes b002 and pushes"
# pc2 has not seen it: skip its pull, the way a push from the other PC lands between pull and push
out=$(LANES_BUILDS_TEST_SKIP_FIRST_PULL=1 pc pc2 snap proj "pc2 change" --note "from pc2")
has "had already used b002" "$out" "pc2's push is refused and it notices the clash"
has "b003 - pc2 change" "$out" "pc2's build moves to b003"
has "github: pushed" "$out" "and is then pushed"
git -C "$T/pc1" pull -q --rebase 2>/dev/null
dups=$(ls "$T/pc1/proj" | grep -o '^v1.0.0-b[0-9]*' | sort | uniq -d)
[ -z "$dups" ] && ok "no two builds share a number" || fail "no two builds share a number ($dups)"

echo "result"
out=$(pc pc1 result proj 1 "worked fine"); has "result recorded" "$out" "result is recorded"
has "worked fine" "$(cat "$T/pc1/proj/INDEX.md")" "the index shows the result"

echo "restore on the other PC"
git -C "$T/pc2" pull -q --rebase 2>/dev/null
out=$(pc pc2 restore proj 1); has "dry run" "$out" "restore without --yes changes nothing"
has "kept on the other PC only" "$out" "restore names the local-only file that is missing"
out=$(pc pc2 restore proj 1 --yes); has "stopped: files missing" "$out" "restore refuses while a file is missing"
echo v9 > "$APP/mod.dll"
has "saved as a build first" "$(pc pc1 restore proj 1)" "dry run warns when the app folder is unsaved"
out=$(pc pc1 restore proj 1 --yes)
has "done: the app folder holds v1.0.0-b001" "$out" "restore puts b001 back"
[ "$(cat "$APP/mod.dll")" = "v1" ] && ok "the restored file is b001's" || fail "the restored file is b001's"
[ -f "$APP/game.exe" ] && ok "the app's own file is untouched" || fail "the app's own file is untouched"
has "before restoring b001" "$(ls "$T/pc1/proj")" "the unsaved app folder was kept as a build first"

echo "check (session start, 0.28.0)"
# pc1's app folder holds b001 while newer builds exist: an informational line, and no path in it
out=$(pc pc1 check)
has "a newer build" "$out" "check: says a newer build is saved when the folder holds an older one"
hasnt "$T" "$out" "check: never prints a folder path"
has "builds.py back proj 1" "$out" "check: says how to mark going back as on purpose"

echo "going back on purpose (0.32.0)"
out=$(pc pc1 back proj 99 "no such build"); has "no build b099" "$out" "back: refuses a build that does not exist"
out=$(pc pc1 back proj 1 "   "); has "say why" "$out" "back: refuses an empty reason"
out=$(pc pc1 back proj 1 "the later ones were tests that did not work")
has "stays on b001 on purpose" "$out" "back: notes the build"
has "github: pushed" "$out" "back: the note is pushed, so the other PC knows too"
has "b001 held on purpose while b" "$(cat "$T/pc1/proj/HELD.txt")" "back: HELD.txt carries the note"
out=$(pc pc1 check); [ -z "$out" ] && ok "check: silent while the folder holds the build noted as on purpose" \
                                  || fail "check: silent while the folder holds the build noted as on purpose (got: $out)"
has "noted as on purpose" "$(pc pc1 which proj)" "which: says staying behind is on purpose"
SRC="$T/newer-src"; mkdir -p "$SRC"; echo v-newer > "$SRC/mod.dll"
pc pc1 snap proj "made after the note" --note "a build saved after going back" --source "$SRC" >/dev/null
out=$(pc pc1 check)
has "a newer build" "$out" "check: a build saved AFTER the note is reported again"
echo v-unsaved > "$APP/mod.dll"
out=$(pc pc1 check)
has "matches NO saved build" "$out" "check: a swapped file is reported"
has "- proj:" "$out" "check: names the project"
hasnt "$T" "$out" "check: still no folder path when something differs"
pc pc1 snap proj "saved now" --note "the unsaved change, saved" >/dev/null
out=$(pc pc1 check); [ -z "$out" ] && ok "check: silent when the folder holds the newest build" \
                                  || fail "check: silent when the folder holds the newest build (got: $out)"
mv "$APP" "$T/app-moved"
out=$(pc pc1 check); has "is not there any more" "$out" "check: a missing app folder named in lanes.conf is reported"
mv "$T/app-moved" "$APP"
out=$(LANES_BUILDS="" LANES_CONFIG="$T/none.conf" "$PY" "$TOOL" check 2>&1)
[ -z "$out" ] && ok "check: silent when no builds repo is set" || fail "check: silent when no builds repo is set (got: $out)"

echo "a brand-new, empty builds repo (the first push sets it up)"
git init -q --bare -b main "$T/fresh.git"
mkdir -p "$T/fresh" && git -C "$T/fresh" init -q -b main && git -C "$T/fresh" remote add origin "$T/fresh.git"
pc fresh init proj --app "$APP" --ours mod.dll >/dev/null
out=$(pc fresh snap proj "first" --note "first ever"); has "github: pushed" "$out" "the first build is pushed to an empty repo"
out=$(pc fresh snap proj "second" --note "and again"); has "github: pushed" "$out" "and the next one pulls and pushes normally"

echo "one folder per feature (0.46.0)"
out=$(pc pc1 snap proj "ladder first try" --note "a feature build" --feature "Ladder climb")
has "Ladder climb/v1.0.0-b" "$out" "snap --feature saves into the feature's folder"
[ -d "$T/pc1/proj/Ladder climb" ] && ok "the feature folder exists" || fail "the feature folder exists"
FNUM=$(echo "$out" | grep -o 'b[0-9]\{3\} - ladder' | head -1 | grep -o '[0-9]\{3\}')
out=$(pc pc1 snap proj "after the feature" --note "a build with no feature")
NEXT=$(echo "$out" | grep -o 'b[0-9]\{3\} - after' | head -1 | grep -o '[0-9]\{3\}')
[ "$((10#$NEXT))" -eq "$((10#$FNUM + 1))" ] && ok "numbers run on across folders" || fail "numbers run on across folders ($FNUM then $NEXT)"
has "ladder first try" "$(pc pc1 list proj --feature "Ladder climb")" "list --feature shows that feature's builds"
hasnt "after the feature" "$(pc pc1 list proj --feature "Ladder climb")" "list --feature leaves the others out"
has "Ladder climb: 1 build(s)" "$(pc pc1 features proj)" "features: counts each folder"
has "Feature:** Ladder climb" "$(cat "$T/pc1/proj/Ladder climb/"*/CHANGES.md)" "CHANGES.md names the feature"
has "holds v1.0.0-b$NEXT" "$(pc pc1 which proj)" "which still works with feature folders"
out=$(pc pc1 restore proj "$((10#$FNUM))" --yes); has "done: the app folder holds Ladder climb/" "$out" "restore finds a build in a feature folder"
pc pc1 restore proj "$((10#$NEXT))" --yes >/dev/null

echo "the originals (0.46.0)"
echo original-settings > "$APP/mods/data/settings.ini"
out=$(pc pc1 vanilla proj mods/data/settings.ini); has "saved    mods/data/settings.ini" "$out" "vanilla: saves the original"
has "the hash list only" "$out" "vanilla: pushes the hash list"
V="$T/pc1/proj/_vanilla"
[ "$(cat "$V/mods/data/settings.ini")" = "original-settings" ] && ok "the copy is the original" || fail "the copy is the original"
tracked=$(git -C "$T/pc1" ls-files)
has "proj/_vanilla/MANIFEST.sha256" "$tracked" "the hash list is committed"
hasnt "_vanilla/mods" "$tracked" "an original file is NEVER committed"
echo modded-settings > "$APP/mods/data/settings.ini"
out=$(pc pc1 vanilla proj mods/data/settings.ini); has "first copy wins" "$out" "vanilla: never overwrites the first copy"
[ "$(cat "$V/mods/data/settings.ini")" = "original-settings" ] && ok "the original survives a second save" || fail "the original survives a second save"
out=$(pc pc1 vanilla proj mod.dll); has "matches one of our saved builds" "$out" "vanilla: refuses a file that is already ours"
pc pc1 snap proj "with modded settings" --note "settings changed" >/dev/null
has "holds" "$(pc pc1 which proj)" "a build after a vanilla save still matches"
out=$(pc pc1 vanilla-restore proj); has "dry run" "$out" "vanilla-restore without --yes changes nothing"
[ -f "$APP/mod.dll" ] && ok "dry run left our files in place" || fail "dry run left our files in place"
out=$(pc pc1 vanilla-restore proj --yes); has "1 original(s) put back" "$out" "vanilla-restore puts the original back"
[ "$(cat "$APP/mods/data/settings.ini")" = "original-settings" ] && ok "the app file is the original again" || fail "the app file is the original again"
[ -f "$APP/mod.dll" ] && fail "our files are gone after vanilla-restore" || ok "our files are gone after vanilla-restore"
[ -f "$APP/game.exe" ] && ok "the app's own other files are untouched" || fail "the app's own other files are untouched"
pc pc1 snap proj "plain app" --note "a build holding an untouched original" >/dev/null
hasnt "plain app/mods/data/settings.ini" "$(git -C "$T/pc1" ls-files)" "a build file identical to an original is never committed"
echo original-settings-2 > "$APP/mods/data/other.ini"
pc pc1 vanilla proj mods/data/other.ini >/dev/null
git -C "$T/pc2" pull -q --rebase 2>/dev/null
out=$(LANES_BUILDS="$T/pc2" "$PY" "$TOOL" check 2>&1); has "saved on the other PC but not on this one" "$out" "check: the other PC hears an original is missing there"
hasnt "$T" "$out" "check: no folder path in the originals line"
out=$(pc pc2 vanilla proj --fill); has "this PC's copy of the original" "$out" "vanilla --fill saves it on the other PC"
out=$(pc pc1 restore proj "$((10#$FNUM))" --yes); has "original app file(s) put back" "$out" "restore puts back an original a removed folder of ours held"

echo
[ "$FAILED" -eq 0 ] && echo "builds-fixture: $N checks, 0 failed" || echo "builds-fixture: FAILURES above ($N checks)"
exit "$FAILED"
