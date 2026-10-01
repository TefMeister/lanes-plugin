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
out=$(LANES_CONFIG="$TP/A/lanes.conf" "$PY" "$TOOL" close --session=fixture-s1 2>&1); rc=$?
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
assert_contains "PCA (DEV) last saved" "$out" "the other PC is named with its role"
assert_contains "and ended SAVED" "$out" "and how it ended"
assert_not_contains "PCB (HOME) last saved" "$out" "a PC is not told about itself"
hb=$(git -C "$T/A/clones/board" fetch -q origin && git -C "$T/A/clones/board" show origin/main:handover/PCB.txt 2>&1)
assert_contains "event = start" "$hb" "PC B's own start report reached the remote"
out=$(LANES_CONFIG="$TP/A/lanes.conf" "$PY" "$TOOL" start 2>&1)
assert_contains "PCB (HOME) last saved" "$out" "and PC A sees PC B's report"

echo "close: green, names what this session pushed, the claim released, the other PC's last save"
( cd "$T/seed-board" && q git pull -q --rebase && printf 'OPEN (2026-10-01):\n' > status/demo.md && q git commit -q -am "release" && q git push -q )
out=$(LANES_CONFIG="$TP/A/lanes.conf" "$PY" "$TOOL" close --session=fixture-s1 2>&1); rc=$?
assert_contains "| 🔦 **SAVED** | **EVERYTHING ON THIS PC IS ON GITHUB** |" "$out" "the green headline"
assert_contains "| 📦 demo-dirty | pushed · 1 new commit |" "$out" "the repo this session pushed is a row, with how much"
assert_not_contains "| 📦 demo-clean |" "$out" "a repo that did not move has no row of its own"
assert_contains "| 📦 the other 3 repos | nothing to push |" "$out" "the rest are one row"
assert_contains "| 🔒 Claim | none held |" "$out" "no claim held once it is released"
assert_contains "| 🖥️ PCB (HOME) | last saved 0 min ago, ended SAVED |" "$out" "the other PC's last save, read from the remote"
[ "$rc" = "0" ] && ok "exit 0 when green" || fail "exit 0 when green (got $rc)"
out=$(LANES_CONFIG="$TP/A/lanes.conf" "$PY" "$TOOL" close --session=never-started 2>&1)
assert_contains "| 📦 all 4 repos | nothing to push |" "$out" "with no snapshot, nothing is claimed as pushed"

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

[ "$FAILED" = "0" ] && echo "handover-fixture: ALL PASSED" || { echo "handover-fixture: FAILED"; exit 1; }
