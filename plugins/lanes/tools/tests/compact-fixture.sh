#!/usr/bin/env bash
# compact-fixture.sh - asserts the early summary (0.63.0): `on`/`off` write and remove the one setting with a backup
# and leave the rest of settings.json alone; the PreCompact hook prints what the summary must keep, saves a
# checkpoint with the person's last requests and copies the full log untouched; the SessionStart hook after a
# summary answers in the hook format; the close-out box offers "safe to /clear" only while the early summary is off.
# Never touches the real lanes.conf or settings.json (LANES_CONFIG and LANES_CLAUDE_SETTINGS point at scratch files).
#   bash tools/tests/compact-fixture.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TOOLS="$(cd "$HERE/.." && pwd)"
HOOKS="$(cd "$HERE/../../hooks" && pwd)"
PY=""
for cand in python3 python py; do
  command -v "$cand" >/dev/null 2>&1 || continue
  "$cand" -c "" >/dev/null 2>&1 || continue
  PY="$cand"; break
done
[ -n "$PY" ] || { echo "compact-fixture: no working python"; exit 2; }

T="$(mktemp -d)"; T="$(cygpath -m "$T" 2>/dev/null || echo "$T")"; trap 'rm -rf "$T"' EXIT
FAILED=0; N=0
ok()   { N=$((N+1)); printf '  ok    %s\n' "$1"; }
fail() { N=$((N+1)); printf '  FAIL  %s\n' "$1"; FAILED=1; }
has()  { case "$2" in *"$1"*) ok "$3" ;; *) fail "$3 (expected: $1)" ;; esac; }
hasnt(){ case "$2" in *"$1"*) fail "$3 (did NOT expect: $1)" ;; *) ok "$3" ;; esac; }

export GIT_AUTHOR_NAME=fixture GIT_AUTHOR_EMAIL=fixture@example.invalid
export GIT_COMMITTER_NAME=fixture GIT_COMMITTER_EMAIL=fixture@example.invalid
export LANES_CONFIG="$T/lanes.conf" LANES_CLAUDE_SETTINGS="$T/settings.json"

# a board with one project, pushed to a bare "GitHub" so the PC counts as saved
git init -q --bare -b main "$T/remote.git"
git clone -q "$T/remote.git" "$T/root/board" 2>/dev/null
mkdir -p "$T/root/board/status"
printf '## Demo\n\nOPEN (2026-10-13):\n  [PD]  write the thing\n  [FLAT] run it\n' > "$T/root/board/status/demo.md"
git -C "$T/root/board" add . && git -C "$T/root/board" commit -qm init && git -C "$T/root/board" push -q -u origin main 2>/dev/null
printf 'board = %s\nsession_logs = %s\ntranscripts = %s\nmachine_name = PC9\nearly_summary = 30\n' \
  "$T/root/board" "$T/logs" "$T/tx" > "$LANES_CONFIG"
printf '{\n  "model": "keep-me"\n}\n' > "$LANES_CLAUDE_SETTINGS"

# 1. on / off
out=$("$PY" "$TOOLS/compact.py" on 2>&1)
if case "$out" in *"does not have the setting"*) true ;; *) false ;; esac; then
  ok "this PC's Claude Code lacks the setting: on refuses and says so"
else
  has "on at 30%" "$out" "on: uses early_summary from lanes.conf"
  s=$(cat "$LANES_CLAUDE_SETTINGS")
  has '"CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "30"' "$s" "on: the setting is written"
  has '"keep-me"' "$s" "on: the rest of settings.json is kept"
  ls "$T"/settings.json.bak-lanes-* >/dev/null 2>&1 && ok "on: settings.json backed up first" || fail "on: no backup"
  out=$("$PY" "$TOOLS/compact.py" on 2>&1); has "already on" "$out" "on twice: changes nothing"
  out=$("$PY" "$TOOLS/compact.py" status 2>&1); has "on, at 30%" "$out" "status: reports it"
  box=$("$PY" "$TOOLS/handover.py" close 2>&1)
  hasnt "safe to /clear" "$box" "close-out box: no /clear row while the early summary is on"
  out=$("$PY" "$TOOLS/compact.py" off 2>&1); has "off" "$out" "off: says so"
  s=$(cat "$LANES_CLAUDE_SETTINGS")
  hasnt "AUTOCOMPACT" "$s" "off: the setting is gone"
  has '"keep-me"' "$s" "off: the rest of settings.json is kept"
fi
box=$("$PY" "$TOOLS/handover.py" close 2>&1)
has "SAVED - safe to /clear" "$box" "close-out box: the /clear row while the early summary is off"

# 2. the PreCompact hook (a project with no remote: not saved, on purpose)
mkdir -p "$T/root/demo" && git -C "$T/root/demo" init -q
mkdir -p "$T/cc/a-project-folder"
TR="$T/cc/a-project-folder/0000-session.jsonl"
cat > "$TR" <<'EOF'
{"type":"user","message":{"role":"user","content":"please build the board reader"}}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Built it; next is the test."}]}}
{"type":"user","message":{"role":"user","content":[{"type":"text","text":"and keep the word PELICAN"}]}}
EOF
out=$(printf '{"transcript_path":"%s","cwd":"%s","trigger":"auto"}' "$TR" "$T/root/demo" \
      | bash "$HOOKS/run-hook.cmd" py-hook compact-hook.py pre 2>&1)
has "THE SUMMARY MUST KEEP THESE" "$out" "pre: tells the summary what must survive"
has "Project: demo" "$out" "pre: names the project from the folder the session runs in"
has "write the thing" "$out" "pre: carries the board's next step"
has "demo: no remote" "$out" "pre: names work not on GitHub"
cp="$(ls "$T"/logs/demo/*summary-checkpoint.md 2>/dev/null | head -1)"
[ -n "$cp" ] && ok "pre: a checkpoint is saved in the project's session logs" || fail "pre: no checkpoint"
has "keep the word PELICAN" "$(cat "$cp" 2>/dev/null)" "pre: the checkpoint keeps the person's words"
cmp -s "$TR" "$(ls "$T"/tx/*/0000-session.jsonl 2>/dev/null | head -1)" && ok "pre: the full log is copied unchanged" \
  || fail "pre: the full log was not copied unchanged"

# 3. after the summary, and at the end
out=$(echo '{}' | bash "$HOOKS/run-hook.cmd" py-hook compact-hook.py post 2>&1)
has '"additionalContext"' "$out" "post: answers in the SessionStart hook format"
has "FIRST, before other work" "$out" "post: the session records what is missing first"
echo "one more line" >> "$TR"
printf '{"transcript_path":"%s"}' "$TR" | bash "$HOOKS/run-hook.cmd" py-hook compact-hook.py end
cmp -s "$TR" "$(ls "$T"/tx/*/0000-session.jsonl | head -1)" && ok "end: the copy is brought up to date" || fail "end: copy not updated"
out=$(echo 'not json' | LANES_COMPACT=1 bash "$HOOKS/run-hook.cmd" py-hook compact-hook.py pre; echo "rc=$?")
has "rc=0" "$out" "pre: bad input never blocks a summary"

[ "$FAILED" = 0 ] && echo "compact-fixture: all $N checks passed" || { echo "compact-fixture: FAILED"; exit 1; }
