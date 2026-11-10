#!/usr/bin/env bash
# handover-fixture.sh - tools/handover.py against two throwaway PCs sharing one throwaway "GitHub".
#
#   bash tools/tests/handover-fixture.sh
#
# Builds, in a temp folder: a bare remote for a board and for two project repos; PC "PCA" with a clone
# root holding one clean clone and one with a file never added plus a commit never pushed; PC "PCB"
# with its own board clone. Then checks: red names the dirty repo and not the clean one; the Inspector's
# local notes do not count; after saving it goes green; `end --write` reports on the board; PCB's `start`
# reads PCA's report from the remote; `fresh` sees a repo that is behind and `--pull` brings it up.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TOOL="$HERE/../handover.py"
FAILED=0
ok()   { printf '  ok    %s\n' "$1"; }
fail() { printf '  FAIL  %s\n' "$1"; FAILED=1; }
assert_contains()     { case "$2" in *"$1"*) ok "$3" ;; *) fail "$3 (expected: $1)";; esac; }
assert_not_contains() { case "$2" in *"$1"*) fail "$3 (did NOT expect: $1)" ;; *) ok "$3";; esac; }

PY=""
for cand in python3 python py; do
  command -v "$cand" >/dev/null 2>&1 || continue
  "$cand" -c "" >/dev/null 2>&1 || continue
  PY="$cand"; break
done
[ -n "$PY" ] || { echo "handover-fixture: no working python found" >&2; exit 2; }

T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
# Python on Windows cannot open Git Bash's /tmp/... spelling; give it the native one for the conf files.
TP="$(cygpath -m "$T" 2>/dev/null || echo "$T")"
export GIT_AUTHOR_NAME=fixture GIT_AUTHOR_EMAIL=fixture@example.invalid
export GIT_COMMITTER_NAME=fixture GIT_COMMITTER_EMAIL=fixture@example.invalid
q() { "$@" >/dev/null 2>&1; }

# a bare remote whose default branch is main, like GitHub's (an older git would otherwise point HEAD
# at a master that never exists, and every clone of it would start on an unborn branch)
mkremote() { q git init -q --bare "$1"; q git -C "$1" symbolic-ref HEAD refs/heads/main; }
seed() {  # seed <remote> <workdir>: one pushed commit on main
  q git clone -q "$1" "$2"; ( cd "$2" && echo a > a.txt && q git add a.txt && q git commit -q -m seed && q git branch -M main && q git push -q -u origin main )
}
mkremote "$T/remote-board"; mkremote "$T/remote-clean"; mkremote "$T/remote-dirty"
seed "$T/remote-board" "$T/seed-board"; seed "$T/remote-clean" "$T/seed-clean"; seed "$T/remote-dirty" "$T/seed-dirty"
# the board holds one project whose claim PC A still holds (the close-out box must say so)
( cd "$T/seed-board" && mkdir -p status && printf 'LIVE: /pd 2026-10-01 10:00 PCA\nOPEN (2026-10-01):\n' > status/demo.md \
  && q git add status && q git commit -q -m "claim" && q git push -q )

# PC A: a live root with the board and two project clones, plus a -pd root with one clone
mkdir -p "$T/A/clones" "$T/A/clones-pd"
q git clone -q "$T/remote-board" "$T/A/clones/board"
q git clone -q "$T/remote-clean" "$T/A/clones/demo-clean"
q git clone -q "$T/remote-dirty" "$T/A/clones/demo-dirty"
q git clone -q "$T/remote-clean" "$T/A/clones-pd/demo-clean"
mkdir -p "$T/A/clones/demo-clean/dev-archive/inspector" && echo n > "$T/A/clones/demo-clean/dev-archive/inspector/this-session.md"
echo forgotten > "$T/A/clones/demo-dirty/notes.md"
( cd "$T/A/clones/demo-dirty" && echo b > b.txt && q git add b.txt && q git commit -q -m "local only" )
printf 'board = %s\nroot = %s\nmachine_name = PCA\nrole = DEV\n' "$TP/A/clones/board" "$TP/A/clones-pd" > "$T/A/lanes.conf"
# PC B: only a board clone
mkdir -p "$T/B/clones"; q git clone -q "$T/remote-board" "$T/B/clones/board"
printf 'board = %s\nmachine_name = PCB\nrole = HOME\n' "$TP/B/clones/board" > "$T/B/lanes.conf"

# HANDOVER_DEBUG=1 shows the throwaway setup when an assertion is a mystery
[ -n "${HANDOVER_DEBUG:-}" ] && { echo "--- conf:"; cat "$T/A/lanes.conf"; echo "--- clones:"; ls "$T/A/clones" "$T/A/clones-pd"; }

echo "start: remembers where every repo stood, so close can later say what this session pushed"
out=$(LANES_CONFIG="$TP/A/lanes.conf" "$PY" "$TOOL" start --session=fixture-s1 2>&1)
assert_contains "NOT SAVED" "$out" "start is red while something is unsaved"
[ -f "$T/A/lanes-sessions/handover-fixture-s1.json" ] && ok "the session's snapshot is written beside lanes.conf" || fail "no snapshot written"

echo "close: the close-out box while something is unsaved"
out=$(LANES_CONFIG="$TP/A/lanes.conf" "$PY" "$TOOL" close --no-write --session=fixture-s1 2>&1); rc=$?
assert_contains "| 🔦 **NOT SAVED** | **DEMO-DIRTY: 1 FILE NEVER ADDED, 1 COMMIT NOT PUSHED** |" "$out" "the headline names the repo and what is wrong"
assert_contains "| 📦 demo-dirty | ⚠️ 1 file never added, 1 commit not pushed |" "$out" "the dirty repo gets a warning row"
assert_contains "| 📦 the other 3 repos | nothing to push |" "$out" "the clean repos are one row"
assert_contains "| 🔍 Inspector | off" "$out" "the Inspector row says it is off rather than vanishing"
assert_contains "| 🔒 Claim | /pd demo still held ⚠️ |" "$out" "a claim this PC still holds is a warning row"
assert_contains "| 🖥️ Other PC | has not reported yet |" "$out" "the other PC row says nothing was reported yet"
[ "$rc" = "1" ] && ok "exit 1 when red" || fail "exit 1 when red (got $rc)"
assert_not_contains "$TP" "$out" "no path in the box"

echo "check: a dirty clone is red, a clean one is not named, the Inspector's notes do not count"
out=$(LANES_CONFIG="$TP/A/lanes.conf" "$PY" "$TOOL" check 2>&1); rc=$?
assert_contains "NOT SAVED" "$out" "red when something is not on GitHub"
assert_contains "demo-dirty (live root): 1 file(s) never added, 1 commit(s) not pushed" "$out" "the dirty clone is named with what is wrong"
assert_not_contains "demo-clean" "$out" "the clean clone is not named (and its inspector/ notes do not count)"
[ "$rc" = "1" ] && ok "exit 1 when red" || fail "exit 1 when red (got $rc)"
assert_not_contains "$TP" "$out" "no path in the output"

echo "end --write: the board gets this PC's report, NOT SAVED"
out=$(LANES_CONFIG="$TP/A/lanes.conf" "$PY" "$TOOL" end --write 2>&1)
assert_contains "reported NOT SAVED on the board" "$out" "the report is pushed"
hb=$(git -C "$T/A/clones/board" show origin/main:handover/PCA.txt 2>&1)
assert_contains "state = NOT SAVED: demo-dirty" "$hb" "the board file says what was left unsaved"

echo "save it: green"
( cd "$T/A/clones/demo-dirty" && q git add notes.md && q git commit -q -m notes && q git push -q )
out=$(LANES_CONFIG="$TP/A/lanes.conf" "$PY" "$TOOL" check 2>&1); rc=$?
assert_contains "SAVED - everything on this PC is on GitHub (4 repos in 2 folders)" "$out" "green names the counts"
[ "$rc" = "0" ] && ok "exit 0 when green" || fail "exit 0 when green (got $rc)"
out=$(LANES_CONFIG="$TP/A/lanes.conf" "$PY" "$TOOL" end --write 2>&1)
assert_contains "reported SAVED on the board" "$out" "the green report is pushed"

echo "start on the other PC: reads PC A's report from the remote, not from its own disk"
out=$(LANES_CONFIG="$TP/B/lanes.conf" "$PY" "$TOOL" start --write 2>&1)
assert_contains "PCA (DEV) last session ended" "$out" "the other PC is named with its role, and its last report was an end"
assert_contains "min ago, SAVED (" "$out" "and how it ended"
assert_not_contains "PCB (HOME)" "$out" "a PC is not told about itself"
hb=$(git -C "$T/A/clones/board" fetch -q origin && git -C "$T/A/clones/board" show origin/main:handover/PCB.txt 2>&1)
assert_contains "event = start" "$hb" "PC B's own start report reached the remote"
out=$(LANES_CONFIG="$TP/A/lanes.conf" "$PY" "$TOOL" start 2>&1)
assert_contains "PCB (HOME) last seen starting a session" "$out" "and PC A sees PC B's report, a start not called an ending (0.94.2)"
assert_not_contains "has not reported a session end" "$out" "a PC new to the board is not warned about missing ends"

echo "close: green, names what this session pushed, the claim released, the other PC's last save"
( cd "$T/seed-board" && q git pull -q --rebase && printf 'OPEN (2026-10-01):\n' > status/demo.md && q git commit -q -am "release" && q git push -q )
out=$(LANES_CONFIG="$TP/A/lanes.conf" "$PY" "$TOOL" close --no-write --session=fixture-s1 2>&1); rc=$?
assert_contains "| 🔦 **SAVED** | **EVERYTHING ON THIS PC IS ON GITHUB** |" "$out" "the green headline"
assert_contains "| 📦 demo-dirty | pushed · 1 new commit |" "$out" "the repo this session pushed is a row, with how much"
assert_not_contains "| 📦 demo-clean |" "$out" "a repo that did not move has no row of its own"
assert_contains "| 📦 the other 3 repos | nothing to push |" "$out" "the rest are one row"
assert_contains "| 🔒 Claim | none held |" "$out" "no claim held once it is released"
# 0 or 1 min: on a slow PC the minute can turn between that save and this read (0.79.0)
assert_contains "| 🖥️ PCB (HOME) | last seen starting a session " "$out" "the other PC's last report, read from the remote"
assert_contains " min ago, SAVED at that point |" "$out" "the other PC's last report: how long ago, and how it stood"
[ "$rc" = "0" ] && ok "exit 0 when green" || fail "exit 0 when green (got $rc)"
assert_not_contains "🪧" "$out" "no front-page row when no front page is set up"
echo "close: work PULLED during the session is not this session's (0.99.2: the box had listed ~70 such repos)"
( cd "$T/seed-clean" && echo c > c.txt && q git add c.txt && q git commit -q -m "another PC's work" && q git push -q )
( cd "$T/A/clones/demo-clean" && q git pull -q --rebase )
out=$(LANES_CONFIG="$TP/A/lanes.conf" "$PY" "$TOOL" close --no-write --session=fixture-s1 2>&1)
assert_not_contains "| 📦 demo-clean |" "$out" "a repo that only pulled has no row"
assert_contains "| 📦 demo-dirty | pushed · 1 new commit |" "$out" "the repo this session committed in still has its row"
out=$(LANES_CONFIG="$TP/A/lanes.conf" "$PY" "$TOOL" close --no-write --session=never-started 2>&1)
assert_contains "| 📦 all 4 repos | nothing to push |" "$out" "with no snapshot, nothing is claimed as pushed"

echo "close: another session's commit in the same clone is not this session's (2026-11-05)"
mine=$(git -C "$T/A/clones/demo-dirty" log -1 --format=%H --grep='^notes$')
( cd "$T/A/clones/demo-dirty" && echo s2 > s2.cpp && q git add s2.cpp && q git commit -q -m "the other session" && q git push -q )
theirs=$(git -C "$T/A/clones/demo-dirty" rev-parse HEAD)
printf 'fixture-s1\t%s\nfixture-s2\t%s\n' "$mine" "$theirs" > "$T/session-commits.txt"
out=$(LANES_SESSION_COMMITS="$TP/session-commits.txt" LANES_CONFIG="$TP/A/lanes.conf" "$PY" "$TOOL" close --no-write --session=fixture-s1 2>&1)
assert_contains "| 📦 demo-dirty | pushed · 1 new commit |" "$out" "only the commit git noted for this session counts"
out=$(LANES_CONFIG="$TP/A/lanes.conf" "$PY" "$TOOL" close --no-write --session=fixture-s1 2>&1)
assert_contains "| 📦 demo-dirty | pushed · 2 new commits |" "$out" "with no notes from git, every commit made here since the start still counts"
cell=$(cd "$HERE/.." && PYTHONIOENCODING=utf-8 "$PY" -c "import sys, handover; print(handover.inspector_check('on, no code was written', [{'repo': sys.argv[1], 'made': [sys.argv[2]]}]))" "$TP/A/clones/demo-dirty" "$theirs")
assert_contains "this session committed 1 code file" "$cell" "an Inspector that saw no edits is not believed over a committed code file"

echo "close: the front-page row of a repo this session pushed work to (0.94.2)"
mkdir -p "$T/A/profile"; echo "# log" > "$T/A/profile/ACTIVITY.md"
printf '| Project | Where it stands | Updated |\n| --- | --- | --- |\n| **Demo dirty** | [demo](https://github.com/someone/demo-dirty) worked on | 01-01 |\n' > "$T/A/profile/README.md"
cp "$T/A/lanes.conf" "$T/A/lanes-fp.conf"; printf 'frontpage = %s\n' "$TP/A/profile/ACTIVITY.md" >> "$T/A/lanes-fp.conf"
cp "$T/A/lanes-sessions/handover-fixture-s1.json" "$T/A/lanes-sessions/handover-fixture-fp.json"
out=$(LANES_CONFIG="$TP/A/lanes-fp.conf" "$PY" "$TOOL" close --no-write --session=fixture-fp 2>&1)
assert_contains "| 🪧 Front page | ⚠️ this session's work is not on its row yet: \"Demo dirty\" (01-01)." "$out" "a row older than today is named"
sed -i "s/| 01-01 |/| $(date +%m-%d) |/" "$T/A/profile/README.md"
out=$(LANES_CONFIG="$TP/A/lanes-fp.conf" "$PY" "$TOOL" close --no-write --session=fixture-fp 2>&1)
assert_contains "| 🪧 Front page | 1 row up to date |" "$out" "a row dated today is fine"
# 0.107.0: a session that runs past midnight. Its work and its row are both dated yesterday; the row is right.
YDAY=$("$PY" -c "import datetime; print((datetime.date.today() - datetime.timedelta(days=1)).isoformat())")
mkdir -p "$T/midnight/demo-late" "$T/midnight/profile"
( cd "$T/midnight/demo-late" && q git init -q . && echo late > late.cpp && q git add late.cpp   && GIT_AUTHOR_DATE="${YDAY}T23:30:00" GIT_COMMITTER_DATE="${YDAY}T23:30:00" q git -c user.name=t -c user.email=t@example.invalid commit -q -m "work late last night" )
late=$(git -C "$T/midnight/demo-late" rev-parse HEAD)
printf '| Project | Where it stands | Updated |
| --- | --- | --- |
| **Demo late** | [demo](https://github.com/someone/demo-late) worked on | %s |
' "${YDAY:5}" > "$T/midnight/profile/README.md"
cell=$(cd "$HERE/.." && PYTHONIOENCODING=utf-8 "$PY" -c "import sys, handover; print(handover.profile_cell({'frontpage': sys.argv[1]}, [{'name': 'demo-late', 'repo': sys.argv[2], 'made': [sys.argv[3]]}], None))" "$TP/midnight/profile" "$TP/midnight/demo-late" "$late")
assert_contains "1 row up to date" "$cell" "past midnight: a row dated the day of the session's last work is not called behind"

echo "close: the other places that speak about a repo this session pushed work to (0.107.0)"
printf '{"projects": [{"repo": "demo-dirty", "stage": "First light (2000-01-01)."}]}\n' > "$T/A/profile/INDEX.json"
out=$(LANES_CONFIG="$TP/A/lanes-fp.conf" "$PY" "$TOOL" close --no-write --session=fixture-fp 2>&1)
assert_contains "| 📣 Also mentioned | ⚠️ demo-dirty: its INDEX.json stage is dated 2000-01-01" "$out" "an index entry older than the session's work is named"
printf '{"projects": [{"repo": "demo-dirty", "stage": "Moved on (%s)."}]}\n' "$(date +%Y-%m-%d)" > "$T/A/profile/INDEX.json"
out=$(LANES_CONFIG="$TP/A/lanes-fp.conf" "$PY" "$TOOL" close --no-write --session=fixture-fp 2>&1)
assert_not_contains "📣" "$out" "an index entry dated the day of the work: no row"
mkdir -p "$T/A/texts/demo-tools"; echo "# Tools: Hand Freeze, Window View" > "$T/A/texts/demo-tools/TOOLKIT.md"
cp "$T/A/lanes-fp.conf" "$T/A/lanes-pl.conf"
printf 'texts = %s\nours = %s\ncatalog = demo-tools/TOOLKIT.md\n' "$TP/A/texts" "$TP/A/clones/demo-dirty" >> "$T/A/lanes-pl.conf"
out=$(LANES_CONFIG="$TP/A/lanes-pl.conf" "$PY" "$TOOL" close --no-write --session=fixture-fp 2>&1)
assert_contains "| 📣 Also mentioned | ⚠️ demo-dirty: TOOLKIT.md never names it" "$out" "a tool of ours the tool list page never names"
echo "# Tools: Hand Freeze, Window View, Demo Dirty" > "$T/A/texts/demo-tools/TOOLKIT.md"
( cd "$T/A/clones/demo-dirty" && q git tag v0.1 HEAD~1 && q git push -q origin v0.1 )
out=$(LANES_CONFIG="$TP/A/lanes-pl.conf" "$PY" "$TOOL" close --no-write --session=fixture-fp 2>&1)
assert_contains "| 📣 Also mentioned | ⚠️ demo-dirty: its download v0.1 is 1 change older than the program" "$out" "a download older than the program it is made from"
( cd "$T/A/clones/demo-dirty" && q git tag v0.2 HEAD && q git push -q origin v0.2 )
out=$(LANES_CONFIG="$TP/A/lanes-pl.conf" "$PY" "$TOOL" close --no-write --session=fixture-fp 2>&1)
assert_not_contains "📣" "$out" "named on the tool list, download as new as the program: no row"

echo "close: jobs raised for this PC that are still open (0.107.0: finished jobs came back and read as lost work)"
mkdir -p "$T/owed-board/owed/DEV"
printf '# Build the connector\n\nMachine: DEV\n' > "$T/owed-board/owed/DEV/2099-01-01-build-the-connector.md"
cell=$(cd "$HERE/.." && PYTHONIOENCODING=utf-8 "$PY" -c "import sys, handover; print(handover.owed_cell({'board': sys.argv[1], 'role': 'dev'}))" "$TP/owed-board")
assert_contains "1 job still open: Build the connector. Tick off any this session finished" "$cell" "an open job for this PC is named at the close-out"
cell=$(cd "$HERE/.." && PYTHONIOENCODING=utf-8 "$PY" -c "import sys, handover; print(repr(handover.owed_cell({'board': sys.argv[1], 'role': 'HOME'})))" "$TP/owed-board")
assert_contains "''" "$cell" "none for this PC: no row"

echo "close: writes this session's END on the board (2026-11-05: the end hook was always cut off, on both PCs)"
out=$(LANES_CONFIG="$TP/A/lanes.conf" "$PY" "$TOOL" close --session=fixture-close 2>&1)
assert_contains "on the board" "$out" "the close-out pushes its end report"
case "$out" in *"on the board"*) ;; *) printf '%s\n' "$out" | grep -v '^|' | sed 's/^/        /' ;; esac
git -C "$T/A/clones/board" fetch -q 2>/dev/null
hb=$(git -C "$T/A/clones/board" show origin/main:handover/PCA.txt 2>&1)
assert_contains "event = end" "$hb" "GitHub's record for this PC is an END"
grep -q "^done fixture-close " "$T/A/lanes-sessions/end-log.txt" && ok "the end log says the end report finished" \
  || fail "the end log says the end report finished"

echo "the Lanes version: each report carries it, and a PC on another version is warned about (2026-11-05)"
MINE=$("$PY" "$(dirname "$TOOL")/lanes_version.py")
assert_contains "lanes = $MINE" "$hb" "the report says which Lanes this PC runs"
out=$(LANES_CONFIG="$TP/B/lanes.conf" "$PY" "$TOOL" check 2>&1; LANES_CONFIG="$TP/B/lanes.conf" "$PY" "$TOOL" start --session=fixture-v1 2>&1)
assert_not_contains "runs Lanes" "$out" "the same version on both PCs: no warning"
# a third, pretend PC (each PC writes only its own file, so PCA's is never touched here)
pcv() { ( cd "$T/seed-board" && q git pull -q --rebase && mkdir -p handover \
  && printf 'machine = PCV\nrole = LAB\nlast_saved = %s\nevent = end\nstate = SAVED\n%s' "$(date '+%Y-%m-%d %H:%M %z')" "$1" > handover/PCV.txt \
  && q git add handover && q git commit -q -m "handover: PCV (LAB) end, SAVED" && q git push -q ); }
pcv "lanes = 0.0.1
"
out=$(LANES_CONFIG="$TP/B/lanes.conf" "$PY" "$TOOL" start --session=fixture-v2 2>&1)
assert_contains "PCV runs Lanes 0.0.1, this PC runs $MINE: PCV is behind, update it" "$out" "a PC on an older Lanes is named"
pcv ""
out=$(LANES_CONFIG="$TP/B/lanes.conf" "$PY" "$TOOL" start --session=fixture-v3 2>&1)
assert_contains "PCV runs a Lanes older than 0.100.0" "$out" "a report with no version is named as an older Lanes"
( cd "$T/seed-board" && q git rm -q handover/PCV.txt && q git commit -q -m "drop the pretend PC" && q git push -q )

echo "start: says when this PC's previous session stopped without its end report (0.94.2)"
touch -d "2 hours ago" "$T/A/lanes-sessions/"handover-*.json
touch "$T/A/lanes-sessions/handover-fixture-s1.json"
out=$(LANES_CONFIG="$TP/A/lanes.conf" "$PY" "$TOOL" start --session=fixture-s2 2>&1)
assert_contains "the last session on this PC ended without its end steps" "$out" "a session with no end report is named"
LANES_CONFIG="$TP/A/lanes.conf" "$PY" "$TOOL" end --session=fixture-s2 >/dev/null 2>&1
out=$(LANES_CONFIG="$TP/A/lanes.conf" "$PY" "$TOOL" start --session=fixture-s3 2>&1)
assert_not_contains "the last session on this PC" "$out" "a session that reported its end is not named"
echo "began fixture-s3 2026-10-28 10:00 +0000" >> "$T/A/lanes-sessions/end-log.txt"
out=$(LANES_CONFIG="$TP/A/lanes.conf" "$PY" "$TOOL" start --session=fixture-s4 2>&1)
assert_contains "was closed before it finished" "$out" "an end report cut off half-way is told apart"

echo "a PC that keeps starting sessions with no end is warned about (0.94.2)"
( cd "$T/seed-board" && q git pull -q --rebase && mkdir -p handover \
  && printf 'machine = PCC\nrole = LAB\nlast_saved = %s\nevent = start\nstate = SAVED\n' "$(date '+%Y-%m-%d %H:%M %z')" > handover/PCC.txt \
  && q git add handover && GIT_COMMITTER_DATE="$(date -d "10 days ago" "+%Y-%m-%dT%H:%M:%S%z")" q git commit -q -m "handover: PCC (LAB) start, SAVED" && q git push -q )
out=$(LANES_CONFIG="$TP/A/lanes.conf" "$PY" "$TOOL" close --no-write --session=fixture-s4 2>&1)
assert_contains "| 🖥️ PCC | ⚠️ PCC has not reported a session end on the board yet" "$out" "ten days of starts with no end is a warning row"
assert_not_contains "PCB has not reported" "$out" "a PC new to the board still is not"
[ -n "${HANDOVER_DEBUG:-}" ] && { echo "$out"; git -C "$T/seed-board" log --format="%cI %s" -3; }

echo "fresh: a clone behind GitHub is STALE, --pull brings it up"
( cd "$T/seed-clean" && echo c > c.txt && q git add c.txt && q git commit -q -m more && q git push -q )
out=$(LANES_CONFIG="$TP/A/lanes.conf" "$PY" "$TOOL" fresh "$TP/A/clones-pd" 2>&1); rc=$?
assert_contains "STALE - 1 repo(s) in the /pd root are behind GitHub: demo-clean (1)" "$out" "the stale clone is named with how far behind"
[ "$rc" = "1" ] && ok "exit 1 when stale" || fail "exit 1 when stale (got $rc)"
out=$(LANES_CONFIG="$TP/A/lanes.conf" "$PY" "$TOOL" fresh "$TP/A/clones-pd" --pull 2>&1)
assert_contains "FRESH - the /pd root has everything GitHub has (1 repos, 1 pulled now)" "$out" "--pull brings it up and says so"

echo "no board: says so, never crashes"
out=$(LANES_CONFIG="$TP/nowhere.conf" "$PY" "$TOOL" check 2>&1); rc=$?
assert_contains "could not run" "$out" "a PC with no plugin setup gets a plain line"
[ "$rc" = "2" ] && ok "exit 2 when it could not run" || fail "exit 2 when it could not run (got $rc)"
out=$(LANES_CONFIG="$TP/nowhere.conf" "$PY" "$TOOL" close 2>&1); rc=$?
assert_contains "| 🔦 **UNKNOWN** |" "$out" "the box says UNKNOWN rather than SAVED when it could not look"
[ "$rc" = "2" ] && ok "close exits 2 when it could not run" || fail "close exits 2 when it could not run (got $rc)"

echo "a damaged clone is named as damaged, not as having no remote (0.41.2)"
q git clone -q "$T/remote-clean" "$T/A/clones/demo-broken"
# a fetch that died half-way leaves exactly this: a remote ref pointing at a commit that never arrived
mkdir -p "$T/A/clones/demo-broken/.git/refs/remotes/origin"
echo 0123456789abcdef0123456789abcdef01234567 > "$T/A/clones/demo-broken/.git/refs/remotes/origin/main"
out=$(LANES_CONFIG="$TP/A/lanes.conf" "$PY" "$TOOL" check 2>&1)
assert_contains "demo-broken (live root): damaged clone" "$out" "the broken clone is called damaged"
assert_not_contains "demo-broken (live root): no remote" "$out" "and not blamed on a missing remote"

echo "0.95.0: the -gu root is read, a side branch's unpushed work counts, an old rewritten copy does not"
mkdir -p "$T/A/clones-gu"; q git clone -q "$T/remote-clean" "$T/A/clones-gu/demo-clean"
( cd "$T/A/clones-gu/demo-clean" && q git checkout -q -b side && echo s > s.txt && q git add s.txt \
  && q git commit -q -m "side work" && q git checkout -q main )
( cd "$T/A/clones/demo-clean" && q git checkout -q -b oldcopy && q git commit -q --amend -m "seed, as before a rewrite" \
  && q git checkout -q main )
out=$(LANES_CONFIG="$TP/A/lanes.conf" "$PY" "$TOOL" check 2>&1)
assert_contains "demo-clean (/gu root): 1 commit(s) not pushed" "$out" "work on a side branch in the -gu root is not on GitHub"
assert_not_contains "demo-clean (live root)" "$out" "a branch GitHub holds in rewritten form is nothing to save"

echo "lanes-next (two-PC test Run 2): a start report is held back for an hour, but never when the light changed"
# PC A's board file says SAVED (its last written report was the green end above); PC A is red now (the side branch
# and the damaged clone). A start within the hour must still be written, because the light changed.
reports() { git -C "$T/A/clones/board" fetch -q origin && git -C "$T/A/clones/board" log --oneline origin/main -- handover/PCA.txt | wc -l | tr -d ' '; }
before=$(reports)
out=$(LANES_CONFIG="$TP/A/lanes.conf" "$PY" "$TOOL" start --write 2>&1)
assert_contains "reported NOT SAVED on the board" "$out" "a start whose light changed is written at once"
after=$(reports)
[ "$after" -eq $((before + 1)) ] && ok "one new report on the remote" || fail "one new report on the remote ($before -> $after)"
hb=$(git -C "$T/A/clones/board" show origin/main:handover/PCA.txt 2>&1)
assert_contains "state = NOT SAVED" "$hb" "and it says NOT SAVED"
out=$(LANES_CONFIG="$TP/A/lanes.conf" "$PY" "$TOOL" start --write 2>&1)
assert_not_contains "this PC (PCA) reported" "$out" "the same light again within the hour is held back"
[ "$(reports)" -eq "$after" ] && ok "no second report on the remote" || fail "no second report on the remote"

echo "board cloned outside the root (the home PC's layout): the lane roots beside 'root' are still read"
# Two-PC test Run 4: with the board in the home folder, a file left in the /pd root never turned the light red.
mkdir -p "$T/C/userdir" "$T/C/clones" "$T/C/clones-pd"
q git clone -q "$T/remote-board" "$T/C/userdir/board"
q git clone -q "$T/remote-clean" "$T/C/clones/demo-clean"
q git clone -q "$T/remote-clean" "$T/C/clones-pd/demo-clean"
echo leftover > "$T/C/clones-pd/demo-clean/leftover.txt"
printf 'board = %s\nroot = %s\nmachine_name = PCC\nrole = HOME\n' "$TP/C/userdir/board" "$TP/C/clones" > "$T/C/lanes.conf"
out=$(LANES_CONFIG="$TP/C/lanes.conf" "$PY" "$TOOL" check 2>&1); rc=$?
assert_contains "demo-clean (/pd root): 1 file(s) never added" "$out" "a file left in the /pd root beside 'root' is named"
[ "$rc" = "1" ] && ok "exit 1 when red" || fail "exit 1 when red (got $rc)"

echo "level: a copy that is only behind GitHub is brought up to it; anything with work of its own is left (0.107.0)"
# PC D: three copies of one repo's kind, each one commit behind: a clean one, one with a changed file, one a session
# on this PC is writing into (the project guard's hold). And a repo that exists on GitHub only.
mkremote "$T/remote-held"; seed "$T/remote-held" "$T/seed-held"
mkremote "$T/remote-edit"; seed "$T/remote-edit" "$T/seed-edit"
mkremote "$T/remote-new"; seed "$T/remote-new" "$T/seed-new"
mkdir -p "$T/D/clones" "$T/D/state/projects-held"
q git clone -q "$T/remote-board" "$T/D/clones/board"
q git clone -q "$T/remote-clean" "$T/D/clones/demo-clean"
q git clone -q "$T/remote-held" "$T/D/clones/demo-held"
q git clone -q "$T/remote-edit" "$T/D/clones/demo-edit"
for n in clean held edit; do
  ( cd "$T/seed-$n" && q git pull -q; echo more > "more-$n.txt" && q git add . && q git commit -q -m "the other PC's work" && q git push -q )
  q git -C "$T/D/clones/demo-$n" fetch -q origin
done
echo changed >> "$T/D/clones/demo-edit/a.txt"
"$PY" -c "import json, sys, time; json.dump({'session': 's', 'since': time.time(), 'last': time.time()}, open(sys.argv[1], 'w'))" "$TP/D/state/projects-held/demo-held.json"
printf 'board = %s\nmachine_name = PCD\nrole = DEV\n' "$TP/D/clones/board" > "$T/D/lanes.conf"
LIST="[[\"demo-new\", \"$TP/remote-new\"], [\"demo-clean\", \"$TP/remote-clean\"]]"
out=$(LANES_STATE_DIR="$TP/D/state" LANES_LEVEL_REPOS="$LIST" LANES_CONFIG="$TP/D/lanes.conf" "$PY" "$TOOL" level 2>&1)
assert_contains "1 copy brought level with GitHub: demo-clean (1)" "$out" "the clean copy that was behind is brought level"
[ -f "$T/D/clones/demo-clean/more-clean.txt" ] && ok "its files are GitHub's now" || fail "the clean copy was not moved"
[ ! -f "$T/D/clones/demo-edit/more-edit.txt" ] && ok "a copy with a changed file is left alone" || fail "a copy with a changed file was moved"
[ ! -f "$T/D/clones/demo-held/more-held.txt" ] && ok "a project a session is writing into is left alone" || fail "a held project was moved"
assert_contains "new on GitHub, copied to this PC: demo-new" "$out" "a repo this PC had no copy of is copied over"
[ -f "$T/D/clones/demo-new/a.txt" ] && ok "and it is a real copy" || fail "the new repo was not cloned"
out=$(LANES_STATE_DIR="$TP/D/state" LANES_LEVEL_REPOS="$LIST" LANES_CONFIG="$TP/D/lanes.conf" "$PY" "$TOOL" level 2>&1)
assert_contains "every copy that could be brought level with GitHub already is" "$out" "a second run finds nothing to do"

[ "$FAILED" = "0" ] && echo "handover-fixture: ALL PASSED" || { echo "handover-fixture: FAILED"; exit 1; }
