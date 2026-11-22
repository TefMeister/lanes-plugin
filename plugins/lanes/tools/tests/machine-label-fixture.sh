#!/usr/bin/env bash
# machine-label-fixture.sh - every PC has a plain name, and the computer's real name is never
# written down (0.24.0). An outside audit of 0.22.0 found claims and reminders writing it into the
# board and commits, against the plugin's own naming rule. This plays two PCs sharing one board,
# takes real claims, raises a real reminder, then searches every file and commit for the real name.
#   bash tools/tests/machine-label-fixture.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TOOLS="$(cd "$HERE/.." && pwd)"
PY=""
for cand in python3 python py; do
  command -v "$cand" >/dev/null 2>&1 || continue
  "$cand" -c "" >/dev/null 2>&1 || continue
  PY="$cand"; break
done
[ -n "$PY" ] || { echo "machine-label-fixture: no working python"; exit 2; }

T="$(mktemp -d)"; T="$(cygpath -m "$T" 2>/dev/null || echo "$T")"; trap 'rm -rf "$T"' EXIT
FAILED=0; N=0
ok()   { N=$((N+1)); printf '  ok    %s\n' "$1"; }
fail() { N=$((N+1)); printf '  FAIL  %s\n' "$1"; FAILED=1; }
unset GATE_ROLE LANES_BOARD
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t

REAL="$("$PY" -c 'import socket; print(socket.gethostname())')"
leaks() {   # any trace of the real name in files or commit messages under $1
  local n
  for n in "$REAL" "${COMPUTERNAME:-}"; do
    [ "${#n}" -ge 3 ] || continue
    grep -rIil --exclude-dir=.git -F "$n" "$1" 2>/dev/null
    git -C "$1" log --format=%B 2>/dev/null | grep -qi -F "$n" && echo "commit messages"
  done
}

# one board on a shared origin, cloned by two PCs, each with its own lanes.conf
git init -q -b main "$T/seed" 2>/dev/null || { git init -q "$T/seed"; git -C "$T/seed" checkout -q -b main; }
mkdir -p "$T/seed/status"; printf '# demo\n\nOPEN (2026-01-01): none\n' > "$T/seed/status/demo.md"
printf '# other\n\nOPEN (2026-01-01): none\n' > "$T/seed/status/other.md"
git -C "$T/seed" add -A && git -C "$T/seed" commit -qm init
git clone -q --bare "$T/seed" "$T/origin.git"
git clone -q "$T/origin.git" "$T/pc-a"; git clone -q "$T/origin.git" "$T/pc-b"
printf 'role = HOME\nboard = %s\n' "$T/pc-a" > "$T/a.conf"
printf 'role = DEV\nboard = %s\n'  "$T/pc-b" > "$T/b.conf"
claim_of() { grep '^LIVE:' "$1/status/$2.md" | awk '{print $NF}'; }

echo "looking never names"
LANES_CONFIG="$T/a.conf" bash "$TOOLS/lane-claim.sh" list --repo "$T/pc-a" >/dev/null 2>&1
LANES_CONFIG="$T/a.conf" bash "$TOOLS/lane-claim.sh" check demo --repo "$T/pc-a" >/dev/null 2>&1
LANES_CONFIG="$T/a.conf" LANES_BOARD="$T/pc-a" GATE_ROLE=HOME bash "$TOOLS/owed.sh" check >/dev/null 2>&1
if grep -q machine_name "$T/a.conf" || [ -e "$T/pc-a/machines.txt" ]; then
  fail "list/check picked a name - they run at every session start and must change nothing"
else
  ok "list and check pick no name and push nothing (they run at every session start)"
fi
# a settings file in the real home place, which a test pointed elsewhere must never read
mkdir -p "$T/fakehome/.claude"; printf 'machine_name = WRONG\n' > "$T/fakehome/.claude/lanes.conf"

echo "no name chosen: PC1, then PC2"
LANES_CONFIG="$T/a.conf" "$PY" "$TOOLS/machine-name.py" suggest >/dev/null
grep -q machine_name "$T/a.conf" && fail "suggest must change nothing" || ok "suggest changes nothing"
HOME="$T/fakehome" LANES_CONFIG="$T/a.conf" bash "$TOOLS/lane-claim.sh" take /lm demo --repo "$T/pc-a" >/dev/null 2>&1
[ "$(claim_of "$T/pc-a" demo)" = "PC1" ] && ok "the first PC's claim says PC1 (and a settings file elsewhere was ignored)" || fail "first claim: '$(claim_of "$T/pc-a" demo)'"
grep -q "^machine_name = PC1" "$T/a.conf" && ok "and PC1 is saved on that PC" || fail "PC1 not saved: $(cat "$T/a.conf")"
LANES_CONFIG="$T/b.conf" bash "$TOOLS/lane-claim.sh" take /pd other --repo "$T/pc-b" >/dev/null 2>&1
[ "$(claim_of "$T/pc-b" other)" = "PC2" ] && ok "the second PC becomes PC2, not a second PC1" || fail "second claim: '$(claim_of "$T/pc-b" other)'"
git -C "$T/pc-a" pull -q --rebase 2>/dev/null
grep -qx PC1 "$T/pc-a/machines.txt" && grep -qx PC2 "$T/pc-a/machines.txt" && ok "the board lists both names" || fail "machines.txt: $(cat "$T/pc-a/machines.txt" 2>/dev/null)"
LANES_CONFIG="$T/a.conf" bash "$TOOLS/lane-claim.sh" release /lm demo --repo "$T/pc-a" >/dev/null 2>&1
LANES_CONFIG="$T/a.conf" bash "$TOOLS/lane-claim.sh" take /lm demo --repo "$T/pc-a" >/dev/null 2>&1
[ "$(claim_of "$T/pc-a" demo)" = "PC1" ] && ok "the name stays the same every time" || fail "name changed to '$(claim_of "$T/pc-a" demo)'"

echo "choosing a name"
out=$(LANES_CONFIG="$T/b.conf" "$PY" "$TOOLS/machine-name.py" set PC1 2>&1); rc=$?
[ $rc -ne 0 ] && ok "refuses a name another PC already has" || fail "took a name in use: $out"
out=$(LANES_CONFIG="$T/b.conf" "$PY" "$TOOLS/machine-name.py" set "$REAL" 2>&1); rc=$?
[ $rc -ne 0 ] && ok "refuses the computer's real name" || fail "accepted the real name: $out"
out=$(LANES_CONFIG="$T/b.conf" "$PY" "$TOOLS/machine-name.py" set "attic box" 2>&1); rc=$?
[ $rc -ne 0 ] && ok "refuses a name with a space" || fail "accepted a space: $out"
out=$(LANES_CONFIG="$T/b.conf" "$PY" "$TOOLS/machine-name.py" set Attic 2>&1)
grep -q "^machine_name = Attic" "$T/b.conf" && ok "a chosen name is saved" || fail "not saved: $out"
grep -qx Attic "$T/pc-b/machines.txt" && ! grep -qx PC2 "$T/pc-b/machines.txt" && ok "and replaces the old one on the board" || fail "machines.txt: $(cat "$T/pc-b/machines.txt")"

echo "reminders"
printf 'Why here: x\nDone when: y\n' | LANES_CONFIG="$T/a.conf" LANES_BOARD="$T/pc-a" GATE_ROLE=HOME bash "$TOOLS/owed.sh" add DEV "a thing" >/dev/null 2>&1
f=$(ls "$T/pc-a/owed/DEV/"*.md 2>/dev/null | head -1)
grep -q "Raised: .* on PC1" "$f" 2>/dev/null && ok "a reminder says it was raised on PC1" || fail "reminder: $(cat "$f" 2>/dev/null)"

echo "never the real name"
for d in "$T/pc-a" "$T/pc-b"; do git -C "$d" pull -q --rebase 2>/dev/null; done
[ -z "$(leaks "$T/pc-a")$(leaks "$T/pc-b")" ] && ok "the computer's name is in no file and no commit" || fail "leaked into: $(leaks "$T/pc-a") $(leaks "$T/pc-b")"

echo "older claims"
out=$(bash -c 'source <(sed -n "/^classify_line()/,/^}$/p" "$1"); NOW=$(date +%s); MAX_AGE_S=43200; classify_line "LIVE: /lm 2026-01-01 10:00 SOME-OLD-NAME"; echo "$C_STATE"' _ "$TOOLS/lane-claim.sh" 2>&1)
[ "$out" = "STALE" ] && ok "a claim written before 0.24.0 still reads" || fail "an old claim no longer parses: $out"

echo "retiring a PC that left the board (0.120.0)"
git -C "$T/pc-a" pull -q --rebase 2>/dev/null
mkdir -p "$T/pc-a/handover" "$T/pc-a/installed"
printf 'machine = Attic\nrole = DEV\n' > "$T/pc-a/handover/Attic.txt"
printf '{}\n' > "$T/pc-a/installed/Attic.json"; printf 'g\n' > "$T/pc-a/installed/Attic-games.tsv"
printf 'machine = PC1\nrole = HOME\n' > "$T/pc-a/handover/PC1.txt"
git -C "$T/pc-a" add -A && git -C "$T/pc-a" commit -qm "two PCs' files" && git -C "$T/pc-a" push -q 2>/dev/null
out=$(LANES_CONFIG="$T/a.conf" "$PY" "$TOOLS/machine-name.py" retire PC1 2>&1); rc=$?
[ $rc -ne 0 ] && [ -f "$T/pc-a/handover/PC1.txt" ] && ok "refuses to retire this PC itself" || fail "retired itself: $out"
out=$(LANES_CONFIG="$T/a.conf" "$PY" "$TOOLS/machine-name.py" retire Attic 2>&1); rc=$?
r=$(ls -d "$T/pc-a/retired/Attic-"* 2>/dev/null | head -1)
[ $rc -eq 0 ] && [ -n "$r" ] && [ -f "$r/Attic.txt" ] && [ -f "$r/Attic.json" ] && [ -f "$r/Attic-games.tsv" ] \
  && ok "its files move to retired/, kept, not deleted" || fail "retire: rc=$rc $out"
[ ! -e "$T/pc-a/handover/Attic.txt" ] && [ ! -e "$T/pc-a/installed/Attic.json" ] && [ -f "$T/pc-a/handover/PC1.txt" ] \
  && ok "the other PCs' readers no longer find it; this PC's own file stays" || fail "left behind: $(ls "$T/pc-a/handover" "$T/pc-a/installed")"
! grep -qx Attic "$T/pc-a/machines.txt" && grep -qx PC1 "$T/pc-a/machines.txt" && ok "its name leaves machines.txt" || fail "machines.txt: $(cat "$T/pc-a/machines.txt")"
echo "$out" | grep -q "reminder(s) still wait in owed/DEV" && ok "says the reminders still waiting for its role" || fail "no owed line: $out"
git -C "$T/pc-b" pull -q --rebase 2>/dev/null
[ -n "$(ls -d "$T/pc-b/retired/Attic-"* 2>/dev/null)" ] && ok "committed and pushed: the other clone sees it" || fail "not pushed: $out"
out=$(LANES_CONFIG="$T/a.conf" "$PY" "$TOOLS/machine-name.py" retire Nobody 2>&1); rc=$?
[ $rc -ne 0 ] && ok "a name not on the board is refused" || fail "retired a stranger: $out"

echo "retiring on a board with no machines.txt (issue #13, 0.121.2)"
git -C "$T/pc-a" pull -q --rebase 2>/dev/null
git -C "$T/pc-a" rm -q machines.txt && git -C "$T/pc-a" commit -qm "a board from before machines.txt"
printf 'machine = Oldname
role = DEV
' > "$T/pc-a/handover/Oldname.txt"
git -C "$T/pc-a" add -A && git -C "$T/pc-a" commit -qm "an old name's file" && git -C "$T/pc-a" push -q 2>/dev/null
out=$(LANES_CONFIG="$T/a.conf" "$PY" "$TOOLS/machine-name.py" retire Oldname 2>&1); rc=$?
[ $rc -eq 0 ] && echo "$out" | grep -q "committed" && ! echo "$out" | grep -q "could not commit"   && [ -z "$(git -C "$T/pc-a" status --porcelain)" ] && ok "retires and commits with no machines.txt on the board"   || fail "no machines.txt: rc=$rc $out / $(git -C "$T/pc-a" status --porcelain)"

echo
[ "$FAILED" = 0 ] && echo "machine-label-fixture: $N checks, 0 failed" || { echo "machine-label-fixture: FAILED"; exit 1; }
