#!/usr/bin/env bash
# ideas-fixture.sh - asserts the ideas tool does what its safety rules promise.
# Builds a throwaway ideas repo, board and project clones in a temp folder, and never reads or
# writes the real lanes.conf (LANES_CONFIG points at a scratch file).
#   bash tools/tests/ideas-fixture.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TOOL="$(cd "$HERE/.." && pwd)/ideas.py"
PY=""
for cand in python3 python py; do
  command -v "$cand" >/dev/null 2>&1 || continue
  "$cand" -c "" >/dev/null 2>&1 || continue
  PY="$cand"; break
done
[ -n "$PY" ] || { echo "ideas-fixture: no working python"; exit 2; }

T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
FAILED=0; N=0
ok()   { N=$((N+1)); printf '  ok    %s\n' "$1"; }
fail() { N=$((N+1)); printf '  FAIL  %s\n' "$1"; FAILED=1; }
has()  { case "$2" in *"$1"*) ok "$3" ;; *) fail "$3 (expected: $1)" ;; esac; }
hasnt(){ case "$2" in *"$1"*) fail "$3 (did NOT expect: $1)" ;; *) ok "$3" ;; esac; }

I="$T/ideas"; R="$T/root"; B="$T/board"
mkdir -p "$I/inbox" "$I/pages" "$R/proj-a" "$R/proj-b" "$R/proj-c" "$R/proj-frozen" "$B/status"
git -C "$I" init -q
printf 'display_name = Tester\nideas_skip = proj-frozen\n' > "$T/lanes.conf"
export LANES_CONFIG="$T/lanes.conf" LANES_IDEAS="$I" LANES_ROOT="$R" LANES_BOARD="$B"
for p in proj-a proj-b proj-frozen; do printf '# %s\n\nOPEN (2026-01-01): none\n' "$p" > "$B/status/$p.md"; done
printf '# proj-c\n\n\xe2\x8f\xb8\xef\xb8\x8f **PAUSED 2026-01-01:** someone else is making it\n' > "$B/status/proj-c.md"
printf -- '- **\xe2\x8f\xb8\xef\xb8\x8f PAUSED once, long ago** - resumed since\n' >> "$B/status/proj-b.md"
printf '# DUMP\n\nWrite below.\n\n<!-- write below this line -->\n' > "$I/DUMP.md"
run() { "$PY" "$TOOL" "$@" 2>&1; }

echo "check"
out=$(run check --no-issues); [ -z "$out" ] && ok "silent when nothing waits" || fail "silent when nothing waits (got: $out)"
printf '[a] first idea\n[b] second idea\n' >> "$I/DUMP.md"
out=$(run check --no-issues); has "2 line(s) in DUMP.md" "$out" "counts the waiting lines"
has "/lanes:ideas" "$out" "tells the session how to file them"
out=$(LANES_IDEAS="$T/nowhere" "$PY" "$TOOL" check --no-issues 2>&1; echo "rc=$?")
has "rc=0" "$out" "a missing ideas repo never fails the check"
hasnt "Traceback" "$out" "and prints no error"

echo "clear"
printf '[a] first idea\n\nfiled to pages/a.md\n' > "$I/inbox/2026-01-01-first.md"
out=$(run clear --from inbox/2026-01-01-first.md)
has "cleared 1 line" "$out" "clears the line that was saved"
has "[b] second idea" "$(cat "$I/DUMP.md")" "keeps the line that was NOT saved"
hasnt "[a] first idea" "$(cat "$I/DUMP.md")" "the saved line is gone from DUMP.md"
has "<!-- write below this line -->" "$(cat "$I/DUMP.md")" "the marker survives"
printf '[b] second idea\n' > "$T/outside.md"
out=$(run clear --from "$T/outside.md"); has "inbox/" "$out" "refuses a file outside inbox/"
has "[b] second idea" "$(cat "$I/DUMP.md")" "and clears nothing"

echo "sync"
cat > "$I/pages/a.md" <<'P'
# A
## Features
### Wanted thing
`[raw]` · `[not judged]`
body
### Already decided
`[settled]` · `[looks doable]`
### Sub-heading with no tags
text
P
cat > "$I/pages/all.md" <<'P'
# Everyone
### Shared thing
`[raw]` · `[not judged]`
P
printf 'a\tproj-a\nall\t*\nnone\t-\n' > "$I/repos.tsv"
out=$(run sync)
has "proj-a: 2 new" "$out" "a project gets its own raw idea plus the shared one"
has "proj-b: 1 new" "$out" "* reaches another active project, even one whose history mentions a pause"
hasnt "proj-c" "$out" "* skips a PAUSED project"
hasnt "proj-frozen" "$out" "* skips a project in ideas_skip"
[ -f "$R/proj-a/ideas/fresh/a--wanted-thing.md" ] && ok "the idea file is written" || fail "the idea file is written"
[ ! -f "$R/proj-a/ideas/fresh/a--already-decided.md" ] && ok "a settled idea is not offered" || fail "a settled idea is not offered"
out=$(run sync); has "nothing new" "$out" "a second sync adds nothing"

echo "list + pick"
out=$(run list proj-a)
has "1. Wanted thing" "$out" "list numbers the ideas in page order"
has "(an idea for every project)" "$out" "a shared idea is marked as shared"
out=$(run pick proj-a 1)
has "CHOSEN" "$out" "the picked number is kept"
has "DROPPED" "$out" "the rest are dropped"
has "Chosen by Tester" "$(cat "$R/proj-a/ideas/chosen/a--wanted-thing.md")" "the display name is recorded"
has "[settled]" "$(cat "$I/pages/a.md")" "a single-project idea's tag follows the pick"
has "Shared thing" "$(cat "$I/decisions.md")" "the decision is logged in the ideas repo"
out=$(run sync proj-a); has "nothing new" "$out" "a dropped idea is never offered again"
out=$(run pick proj-b 7); has "no idea numbered" "$out" "a wrong number is refused"
[ -f "$R/proj-b/ideas/fresh/all--shared-thing.md" ] && ok "and nothing is dropped" || fail "and nothing is dropped"

echo
[ "$FAILED" = 0 ] && echo "ideas-fixture: $N checks, 0 failed" || { echo "ideas-fixture: FAILED"; exit 1; }
