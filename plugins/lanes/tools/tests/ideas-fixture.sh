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
# 0.110.0: its own state folder too. Without it the fixture read this PC's real clash locks, and a lock left by a
# session that was cut off ("filing ideas is running on this PC") failed twenty checks here that had nothing wrong.
export LANES_STATE_DIR="$T/state"
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
has "(every-project reminder, not new)" "$out" "a shared idea is marked as a reminder, not new"
has "dropped for proj-a only" "$out" "the header says a drop is for this project only"
out=$(run pick proj-a 1)
has "CHOSEN" "$out" "the picked number is kept"
has "DROPPED" "$out" "the rest are dropped"
has "Chosen by Tester" "$(cat "$R/proj-a/ideas/chosen/a--wanted-thing.md")" "the display name is recorded"
has "[settled]" "$(cat "$I/pages/a.md")" "a single-project idea's tag follows the pick"
has "Shared thing" "$(cat "$I/decisions.md")" "the decision is logged in the ideas repo"
[ -f "$R/proj-b/ideas/fresh/all--shared-thing.md" ] && ok "a shared idea answered in one project stays waiting in the others" || fail "a shared idea answered in one project stays waiting in the others"
out=$(run sync proj-a); has "nothing new" "$out" "a dropped idea is never offered again"
out=$(run pick proj-b 7); has "no idea numbered" "$out" "a wrong number is refused"
[ -f "$R/proj-b/ideas/fresh/all--shared-thing.md" ] && ok "and nothing is dropped" || fail "and nothing is dropped"

echo "sync downloads the ideas copy first (0.107.0: an idea filed from another copy was 'nothing new')"
g() { git -c user.name=t -c user.email=t@example.invalid "$@" >/dev/null 2>&1; }
g init -q --bare "$T/ideas-remote.git"; g -C "$T/ideas-remote.git" symbolic-ref HEAD refs/heads/main
g -C "$I" add -A; g -C "$I" commit -q -m "the ideas so far"; g -C "$I" branch -M main
g -C "$I" remote add origin "$T/ideas-remote.git"; g -C "$I" push -q -u origin main
g clone -q "$T/ideas-remote.git" "$T/ideas-second"       # the copy `ideas =` names; nobody works in it
printf '\n### Filed from the other copy\n`[raw]` \xc2\xb7 `[not judged]`\nA new idea.\n' >> "$I/pages/a.md"
g -C "$I" add -A; g -C "$I" commit -q -m "one more idea"; g -C "$I" push -q
out=$(LANES_IDEAS="$T/ideas-second" "$PY" "$TOOL" sync proj-a 2>&1)
[ -f "$R/proj-a/ideas/fresh/a--filed-from-the-other-copy.md" ] && ok "an idea pushed from another copy reaches the project's list" \
  || fail "an idea pushed from another copy reaches the project's list (got: $out)"
out=$(LANES_IDEAS="$T/ideas-second" LANES_IDEAS_NO_PULL=1 "$PY" "$TOOL" sync proj-a 2>&1)
has "nothing new" "$out" "and is offered once"

echo "sync --commit on the PC that builds (0.113.3)"
# with the Keeper extra on and this PC the Developer side, the new step is handed over as a parcel, never pushed
g init -q --bare "$T/proj-k-remote.git"; g -C "$T/proj-k-remote.git" symbolic-ref HEAD refs/heads/main
mkdir -p "$R/proj-k"; g -C "$R/proj-k" init -q; printf '# k\n' > "$R/proj-k/README.md"
g -C "$R/proj-k" add -A; g -C "$R/proj-k" commit -q -m first; g -C "$R/proj-k" branch -M main
g -C "$R/proj-k" remote add origin "$T/proj-k-remote.git"; g -C "$R/proj-k" push -q -u origin main
printf '# proj-k\n\nOPEN (2026-01-01): none\n' > "$B/status/proj-k.md"
printf 'k\tproj-k\n' >> "$I/repos.tsv"
printf '# k\n\n### Something for k\n`[raw]` `[not judged]`\nA new idea.\n' > "$I/pages/k.md"
mkdir -p "$T/transfer"; TW=$(cygpath -m "$T/transfer" 2>/dev/null || echo "$T/transfer")
printf 'display_name = Tester\nideas_skip = proj-frozen\nkeeper = on\nkeeper_mode = other_pc\nkeeper_role = developer\ntransfer = %s\n' \
  "$TW" > "$T/lanes-dev.conf"
before=$(git -C "$T/proj-k-remote.git" rev-parse main)
out=$(LANES_CONFIG="$T/lanes-dev.conf" LANES_IDEAS_NO_PULL=1 GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.invalid \
      GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.invalid "$PY" "$TOOL" sync proj-k --commit 2>&1)
has "handed over proj-k" "$out" "the new step is handed over"
[ "$(git -C "$T/proj-k-remote.git" rev-parse main)" = "$before" ] && ok "and nothing was pushed from this PC" \
  || fail "and nothing was pushed from this PC"
ls "$T/transfer/parcels/outbox/"proj-k__*.json >/dev/null 2>&1 && ok "a parcel for the Keeper waits in the transfer folder" \
  || fail "a parcel for the Keeper waits in the transfer folder (got: $out)"

echo
[ "$FAILED" = 0 ] && echo "ideas-fixture: $N checks, 0 failed" || { echo "ideas-fixture: FAILED"; exit 1; }
