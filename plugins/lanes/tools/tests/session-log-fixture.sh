#!/usr/bin/env bash
# session-log-fixture.sh - asserts session-log.py saves a dated file per project, never overwrites,
# pushes only its own file to a git clone, and finds old logs by search. Uses a bare "GitHub" repo in a
# temp folder, and never reads or writes the real lanes.conf (LANES_CONFIG points at a scratch file).
#   bash tools/tests/session-log-fixture.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TOOL="$(cd "$HERE/.." && pwd)/session-log.py"
PY=""
for cand in python3 python py; do
  command -v "$cand" >/dev/null 2>&1 || continue
  "$cand" -c "" >/dev/null 2>&1 || continue
  PY="$cand"; break
done
[ -n "$PY" ] || { echo "session-log-fixture: no working python"; exit 2; }

T="$(mktemp -d)"; T="$(cygpath -m "$T" 2>/dev/null || echo "$T")"; trap 'rm -rf "$T"' EXIT
FAILED=0; N=0
ok()   { N=$((N+1)); printf '  ok    %s\n' "$1"; }
fail() { N=$((N+1)); printf '  FAIL  %s\n' "$1"; FAILED=1; }
has()  { case "$2" in *"$1"*) ok "$3" ;; *) fail "$3 (expected: $1)" ;; esac; }
hasnt(){ case "$2" in *"$1"*) fail "$3 (did NOT expect: $1)" ;; *) ok "$3" ;; esac; }

export GIT_AUTHOR_NAME=fixture GIT_AUTHOR_EMAIL=fixture@example.invalid
export GIT_COMMITTER_NAME=fixture GIT_COMMITTER_EMAIL=fixture@example.invalid
export LANES_CONFIG="$T/lanes.conf"

# 1. not configured: says so, writes nothing
: > "$LANES_CONFIG"
out=$(echo "hello" | "$PY" "$TOOL" write game one 2>&1)
has "is not set" "$out" "no session_logs key: says so"

# 2. a git clone as the logs folder
git init -q --bare -b main "$T/remote.git"
git clone -q "$T/remote.git" "$T/logs" 2>/dev/null
git -C "$T/logs" commit -q --allow-empty -m start && git -C "$T/logs" push -q -u origin main 2>/dev/null
echo "stray" > "$T/logs/not-mine.txt"
printf 'session_logs = %s\nmachine_name = PC9\n' "$T/logs" > "$LANES_CONFIG"

out=$(printf 'Did the shake test.\nTefa: no shake.\n' | "$PY" "$TOOL" write "my game" "shake test" 2>&1)
has "saved my-game/" "$out" "write: saved under the project's folder"
has "pushed" "$out" "write: pushed to the clone's remote"
f=$(ls "$T/logs/my-game/" | head -1)
case "$f" in [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]_[0-9][0-9][0-9][0-9]_shake-test.md) ok "file name is date_time_slug.md" ;; *) fail "file name shape: $f" ;; esac
has "on PC9" "$(cat "$T/logs/my-game/$f")" "file carries the time and this PC's name"
remote=$(git -C "$T/remote.git" log --name-only --format= main)
has "my-game/" "$remote" "the log reached the remote"
hasnt "not-mine.txt" "$remote" "a stray file in the clone was NOT pushed"

# 3. same minute, same slug: never overwrite
out=$(printf 'Second one.\n' | "$PY" "$TOOL" write "my game" "shake test" 2>&1)
has "shake-test-2.md" "$out" "same minute: a second file, not an overwrite"

# 4. list and search
printf 'Other game, the hunch is gone.\n' | "$PY" "$TOOL" write other hunch >/dev/null 2>&1
out=$("$PY" "$TOOL" list "my game" 2>&1)
has "my-game/" "$out" "list: shows the project's logs"
hasnt "other/" "$out" "list: only that project"
out=$("$PY" "$TOOL" search no shake 2>&1)
has "Tefa: no shake." "$out" "search: finds the line"
out=$("$PY" "$TOOL" search hunch --project "my game" 2>&1)
has "no log mentions" "$out" "search --project: stays in that project"

# 5. empty stdin: nothing written
out=$(printf '' | "$PY" "$TOOL" write "my game" empty 2>&1)
has "nothing on stdin" "$out" "empty summary: nothing written"

[ "$FAILED" -eq 0 ] && echo "session-log-fixture: all $N checks passed" || { echo "session-log-fixture: FAILED"; exit 1; }
