#!/usr/bin/env bash
# scan-snapshot-fixture.sh - tools/scan_snapshot.py (0.113.0): a snapshot before and after, and a report that names
# every change, sorted: no saved step behind it, branch or history, board lines, saved steps by who made them, GitHub
# moving by itself. A pretend PC in a temp folder (LANES_CONFIG, LANES_STATE_DIR); nothing real is read or written.
#   bash tools/tests/scan-snapshot-fixture.sh
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TOOL="$HERE/../scan_snapshot.py"
PY=""
for cand in python3 python py; do command -v "$cand" >/dev/null 2>&1 && "$cand" -c "" >/dev/null 2>&1 && { PY="$cand"; break; }; done
[ -n "$PY" ] || { echo "scan-snapshot-fixture: no working Python"; exit 1; }
pass=0; fail=0
check() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; fi; }

T="$(mktemp -d)"
command -v cygpath >/dev/null 2>&1 && T="$(cygpath -m "$T")"
trap 'rm -rf "$T"' EXIT
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.invalid GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.invalid
export LANES_STATE_DIR="$T/state" LANES_CONFIG="$T/lanes.conf"
mkdir -p "$T/hub" "$T/root"
for r in proj other claude-memory; do
  git init -q --bare -b main "$T/hub/$r.git"
  git clone -q "$T/hub/$r.git" "$T/root/$r" 2>/dev/null
  git -C "$T/root/$r" checkout -q -b main 2>/dev/null
done
printf 'one\n' > "$T/root/proj/a.txt"; printf 'keep\n' > "$T/root/proj/b.txt"
mkdir -p "$T/root/claude-memory/status"
printf '# proj\n\nOPEN (2026-11-12):\n  - [PD] something\n' > "$T/root/claude-memory/status/proj.md"
printf '# watching\n\n- some game: someone else makes it\n' > "$T/root/claude-memory/WATCHING.md"
printf 'x\n' > "$T/root/other/x.txt"
for r in proj other claude-memory; do
  git -C "$T/root/$r" add -A && git -C "$T/root/$r" commit -q -m "first" && git -C "$T/root/$r" push -q -u origin main 2>/dev/null
done
git clone -q "$T/hub/other.git" "$T/elsewhere" 2>/dev/null
printf 'board = %s/root/claude-memory\n' "$T" > "$T/lanes.conf"

out=$("$PY" "$TOOL" take before)
check "a snapshot names how many copies it holds" 'printf "%s" "$out" | grep -q "snapshot .before.: 3 copies"'
out=$("$PY" "$TOOL" take after); "$PY" "$TOOL" diff >/dev/null; rc=$?
out=$("$PY" "$TOOL" diff)
check "nothing changed: every part says none, exit 0" '[ $rc -eq 0 ] && printf "%s" "$out" | grep -q "1. Changed with no saved step behind it (0): none"'

"$PY" "$TOOL" take before >/dev/null; sleep 1
printf 'note\n' > "$T/root/proj/research.md"; git -C "$T/root/proj" add research.md
git -C "$T/root/proj" commit -q -m "gr: a research note"
git -C "$T/root/proj" commit -q --allow-empty -m "gs: tidy"
printf 'two\n' > "$T/root/proj/a.txt"                                         # changed, not saved
printf 'stray\n' > "$T/root/proj/stray.txt"                                   # new, not saved
sed -i 's/^OPEN (2026-11-12):/PAUSED (2026-11-12): someone else makes it/' "$T/root/claude-memory/status/proj.md"
git -C "$T/root/claude-memory" commit -q -am "board: proj paused"
(cd "$T/elsewhere" && printf 'y\n' > y.txt && git add y.txt && git commit -q -m "other PC" && git push -q 2>/dev/null)
git -C "$T/root/other" checkout -q -b side
"$PY" "$TOOL" take after >/dev/null
out=$("$PY" "$TOOL" diff); rc=$?
check "a changed file with no saved step is flagged first" 'printf "%s" "$out" | grep -q "! live root | proj: a.txt changed and not saved"'
check "a new file nobody saved is flagged" 'printf "%s" "$out" | grep -q "proj: new file stray.txt, not saved"'
check "a saved step does not count as unexplained" '! printf "%s" "$out" | grep -q "research.md.*no saved step"'
check "steps are grouped by who made them" 'printf "%s" "$out" | grep -q "gr: [0-9a-f]* gr: a research note" && printf "%s" "$out" | grep -q "gs: [0-9a-f]* gs: tidy"'
check "the files a step touched are counted" 'printf "%s" "$out" | grep -q "proj: 2 step(s), 1 file(s)"'
check "a board line that changed is named, old and new" 'printf "%s" "$out" | grep -q "proj.md: + PAUSED" && printf "%s" "$out" | grep -q "proj.md: - OPEN"'
check "a branch switch is flagged" 'printf "%s" "$out" | grep -q "! live root | other: branch main -> side"'
check "GitHub moving by itself is told apart" 'printf "%s" "$out" | grep -q "other: GitHub moved on by itself"'
check "something unexplained: exit 1" '[ $rc -eq 1 ]'
check "no folder path in the report" '! printf "%s" "$out" | grep -qF "$T"'
check "the snapshots stay on this PC, in the state folder" '[ "$(ls "$T/state/scan-snapshots" | wc -l)" -ge 4 ]'
check "list shows them" '"$PY" "$TOOL" list | grep -q "_before.json"'

git -C "$T/root/other" checkout -q main
"$PY" "$TOOL" take before >/dev/null; sleep 1
git -C "$T/root/proj" reset -q --hard HEAD~2
git -C "$T/root/proj" commit -q --allow-empty -m "od: rewritten"
"$PY" "$TOOL" take after >/dev/null
out=$("$PY" "$TOOL" diff)
check "a history rewrite is flagged" 'printf "%s" "$out" | grep -q "proj: history rewritten"'

# 0.113.6: names with a space, and files moved in a saved step (the 2026-11-14 full scan called 7,664 such files
# "changed with no saved step": Fallout's run folders have spaces, and an owed note moved away named only its new place)
mkdir -p "$T/root/proj/runs/a run"; printf 'r\n' > "$T/root/proj/runs/a run/log.txt"
git -C "$T/root/proj" add "runs/a run/log.txt" && git -C "$T/root/proj" commit -q -m "lm: a run kept"
printf 'm\n' > "$T/root/proj/move-me.txt"; git -C "$T/root/proj" add move-me.txt && git -C "$T/root/proj" commit -q -m "pd: a note"
"$PY" "$TOOL" take before >/dev/null; sleep 1
git -C "$T/root/proj" mv move-me.txt moved.txt && git -C "$T/root/proj" commit -q -m "pd: moved"
mkdir -p "$T/root/proj/runs/b run"; printf 'r\n' > "$T/root/proj/runs/b run/log.txt"
git -C "$T/root/proj" add "runs/b run/log.txt" && git -C "$T/root/proj" commit -q -m "lm: another run kept"
"$PY" "$TOOL" take after >/dev/null
out=$("$PY" "$TOOL" diff)
check "a saved file in a folder with a space is not unexplained" '! printf "%s" "$out" | grep -q "b run/log.txt.*no saved step"'
check "a file moved in a saved step is not unexplained, old or new place" '! printf "%s" "$out" | grep -q "move-me.txt.*no saved step" && ! printf "%s" "$out" | grep -q "moved.txt.*no saved step"'

echo "scan-snapshot-fixture: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
