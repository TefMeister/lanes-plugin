#!/usr/bin/env bash
# switch-off-fixture.sh - asserts the shutdown guard (0.112.0) refuses while something is unfinished, switches off
# when all is clear, waits and then switches off, gives up without forcing, and that the hook refuses a bare shutdown.
# Never switches anything off: LANES_SWITCH_OFF_CMD stands in for Windows' shutdown, in a temp state folder.
#   bash tools/tests/switch-off-fixture.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TOOLS="$(cd "$HERE/.." && pwd)"
HOOKS="$(cd "$TOOLS/../hooks" && pwd)"
PY=""
for cand in python3 python py; do
  command -v "$cand" >/dev/null 2>&1 || continue
  "$cand" -c "" >/dev/null 2>&1 || continue
  PY="$cand"; break
done
[ -n "$PY" ] || { echo "switch-off-fixture: no working python"; exit 2; }

T="$(mktemp -d)"; T="$(cygpath -m "$T" 2>/dev/null || echo "$T")"; trap 'rm -rf "$T"' EXIT
FAILED=0; N=0
ok()   { N=$((N+1)); printf '  ok    %s\n' "$1"; }
fail() { N=$((N+1)); printf '  FAIL  %s\n' "$1"; FAILED=1; }
has()  { case "$2" in *"$1"*) ok "$3" ;; *) fail "$3 (expected: $1)" ;; esac; }
hasnt(){ case "$2" in *"$1"*) fail "$3 (did NOT expect: $1)" ;; *) ok "$3" ;; esac; }

export LANES_STATE_DIR="$T/state" LANES_CONFIG="$T/lanes.conf" LANES_SWITCH_OFF_SKIP="board,games"
printf 'shutdown_guard = on\n' > "$T/lanes.conf"
mkdir -p "$T/state/projects-held" "$T/state/clash" "$T/lanes-sessions"
printf 'began me 2026-11-14 10:00 +0200\ndone me 2026-11-14 10:00 +0200\ndone other 2026-11-14 10:00 +0200\n' \
  > "$T/lanes-sessions/end-log.txt"
OFF="$T/switched-off"
export LANES_SWITCH_OFF_CMD="$PY -c \"open(r'$OFF','a').write('off\\n')\""
SAVED="$PY -c \"print('everything saved')\""
UNSAVED="$PY -c \"import sys; print('builds: 1 change not on GitHub'); sys.exit(1)\""
so() { "$PY" "$TOOLS/switch_off.py" "$@" 2>&1; }
now_s() { "$PY" -c "import time; print(time.time())"; }

echo "all clear"
out=$(LANES_SWITCH_OFF_SAVE_CMD="$SAVED" so check --session me); has "nothing stops it" "$out" "check: clear when nothing runs"
out=$(LANES_SWITCH_OFF_SAVE_CMD="$SAVED" so now --session me); has "switches off in" "$out" "now: switches off when clear"
[ -f "$OFF" ] && ok "the switch-off command ran" || fail "the switch-off command ran"
rm -f "$OFF"

echo "the asking session has not run its close-out (0.113.7)"
out=$(LANES_SWITCH_OFF_SAVE_CMD="$SAVED" so now --session fresh)
has "close-out has not run yet" "$out" "now: refuses before the asking session's own close-out"
[ -f "$OFF" ] && fail "nothing was switched off before the close-out" || ok "nothing was switched off before the close-out"
printf 'done fresh 2026-11-14 10:05 +0200\n' >> "$T/lanes-sessions/end-log.txt"
has "nothing stops it" "$(LANES_SWITCH_OFF_SAVE_CMD="$SAVED" so check --session fresh)" "check: clear once the close-out ran"

echo "work not saved"
out=$(LANES_SWITCH_OFF_SAVE_CMD="$UNSAVED" so check --session me); has "not saved: builds: 1 change" "$out" "check: names the unsaved work"
out=$(LANES_SWITCH_OFF_SAVE_CMD="$UNSAVED" so now --session me); has "NOT done" "$out" "now: refuses while work is unsaved"
[ -f "$OFF" ] && fail "nothing was switched off" || ok "nothing was switched off"

echo "another session still working"
printf '{"session": "other", "last": %s}' "$(now_s)" > "$T/state/projects-held/the-darkness-vr.json"
out=$(LANES_SWITCH_OFF_SAVE_CMD="$SAVED" so check --session me)
has "another session is working on the-darkness-vr" "$out" "check: another session's fresh hold stops it"
hasnt "$T" "$out" "check: never prints a folder path"
out=$(LANES_SWITCH_OFF_SAVE_CMD="$SAVED" so check --session other)
has "nothing stops it" "$out" "check: the asking session's own hold does not stop it"
printf '{"session": "other", "last": %s}' "$("$PY" -c "import time; print(time.time() - 4*3600)")" \
  > "$T/state/projects-held/the-darkness-vr.json"
has "nothing stops it" "$(LANES_SWITCH_OFF_SAVE_CMD="$SAVED" so check --session me)" "check: a hold older than three hours is ignored"
rm -f "$T/state/projects-held/the-darkness-vr.json"

echo "a lock held by another session"
NOWT=$("$PY" -c "import time; print(time.strftime('%Y-%m-%d %H:%M %z'))")
printf 'machine = PC2\nsince = %s\njob = fullscan\nproject = all\nsession = other\n' "$NOWT" > "$T/state/clash/fullscan.lock"
out=$(LANES_SWITCH_OFF_SAVE_CMD="$SAVED" so check --session me); has "still running on this PC: fullscan" "$out" "check: another session's lock stops it"
has "nothing stops it" "$(LANES_SWITCH_OFF_SAVE_CMD="$SAVED" so check --session other)" "check: the asking session's own lock does not"
rm -f "$T/state/clash/fullscan.lock"

echo "waiting, then switching off by itself"
FLAG="$T/saved-now"
WAITCMD="$PY -c \"import os,sys; sys.exit(0 if os.path.exists(r'$FLAG') else 1)\""
( sleep 2; touch "$FLAG" ) &
out=$(LANES_SWITCH_OFF_INLINE=1 LANES_SWITCH_OFF_POLL_S=1 LANES_SWITCH_OFF_SAVE_CMD="$WAITCMD" so now --session me --wait 1)
wait
[ -f "$OFF" ] && ok "wait: switched off once the work was saved" || fail "wait: switched off once the work was saved"
has "nothing stops it any more" "$(cat "$T/state/switch-off.log")" "wait: the log says why it switched off"
[ -f "$T/state/switch-off.json" ] && fail "wait: the request is gone afterwards" || ok "wait: the request is gone afterwards"
rm -f "$OFF"

echo "waiting runs out: it gives up, never forces"
"$PY" - "$T/state/switch-off.json" <<'EOF'
import json, sys, time
json.dump({"id": "x1", "session": "me", "until": time.time() - 1, "restart": False}, open(sys.argv[1], "w"))
EOF
LANES_SWITCH_OFF_POLL_S=1 LANES_SWITCH_OFF_SAVE_CMD="$UNSAVED" "$PY" "$TOOLS/switch_off.py" _watch x1 >/dev/null 2>&1
[ -f "$OFF" ] && fail "gave up: nothing was switched off" || ok "gave up: nothing was switched off"
has "GAVE UP, the PC stays on" "$(cat "$T/state/switch-off.log")" "gave up: the log says so and what was still open"

echo "status and cancel"
"$PY" - "$T/state/switch-off.json" <<'EOF'
import json, sys, time
json.dump({"id": "x2", "session": "me", "since": "10:00", "until": time.time() + 600, "until_text": "10:10"}, open(sys.argv[1], "w"))
EOF
has "waiting since 10:00" "$(so status)" "status: shows a waiting switch-off"
has "taken back" "$(so cancel)" "cancel: takes it back"
LANES_SWITCH_OFF_POLL_S=1 LANES_SWITCH_OFF_SAVE_CMD="$SAVED" "$PY" "$TOOLS/switch_off.py" _watch x2 >/dev/null 2>&1
[ -f "$OFF" ] && fail "a cancelled switch-off never fires" || ok "a cancelled switch-off never fires"

echo "the hook"
hook() { printf '{"tool_name": "%s", "tool_input": {"command": "%s"}}' "$1" "$2" | "$PY" "$HOOKS/switch-off-guard.py" 2>&1; echo "exit=$?"; }
has "exit=2" "$(hook Bash 'shutdown /s /t 0')" "hook: refuses shutdown /s"
has "switch_off.py" "$(hook Bash 'shutdown /s /t 0')" "hook: points at the guarded switch-off"
has "exit=2" "$(hook PowerShell 'Stop-Computer -Force')" "hook: refuses Stop-Computer"
has "exit=2" "$(hook Bash 'shutdown.exe -r -t 30')" "hook: refuses a restart"
has "exit=0" "$(hook Bash 'shutdown /a')" "hook: lets shutdown /a (stop a countdown) through"
# 0.113.7: the ways that got past it (2026-11-14 02:26, the Developer PC switched off with no end steps)
has "exit=2" "$(hook PowerShell 'shutdown /t 60 /s')" "hook: refuses the switch-off flag in second place"
has "exit=2" "$(hook PowerShell 'shutdown /f /s /t 0')" "hook: refuses /f /s"
has "exit=2" "$(hook PowerShell 'C:\\\\Windows\\\\System32\\\\shutdown.exe /s /t 0')" "hook: refuses a full path"
has "exit=2" "$(hook PowerShell "Start-Process shutdown -ArgumentList '/s /t 0'")" "hook: refuses Start-Process shutdown"
has "exit=2" "$(hook PowerShell '(Get-WmiObject Win32_OperatingSystem).Win32Shutdown(1)')" "hook: refuses the WMI switch-off"
has "exit=0" "$(hook Bash 'python switch_off.py now --wait')" "hook: the guarded switch-off itself is let through"
has "exit=0" "$(hook Bash 'git commit -m shutdown-guard')" "hook: a word inside another word is not a shutdown"
has "exit=0" "$(hook Bash 'grep -n shutdown notes.md')" "hook: a word in a search is not a shutdown"
has "exit=0" "$(hook Read 'shutdown /s')" "hook: only shell commands are looked at"
printf 'shutdown_guard = off\n' > "$T/lanes.conf"
has "exit=0" "$(hook Bash 'shutdown /s /t 0')" "hook: switched off, it lets everything through"

echo
[ "$FAILED" -eq 0 ] && echo "switch-off-fixture: $N checks, 0 failed" || echo "switch-off-fixture: FAILURES above ($N checks)"
exit "$FAILED"
