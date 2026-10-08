#!/usr/bin/env bash
# Tests for the guard hooks (pd-guard, reader-guard). Both are guards, so the important assertions
# are not only "it blocks the bad case" but "it stays out of the way otherwise"
# and "it fails OPEN when it cannot do its job".
#
#   bash tools/tests/hooks-test.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PLUGIN="$(cd "$HERE/../.." && pwd)"
HOOKS="$PLUGIN/hooks"
FIX="$HERE/fixture-board"
FAILED=0

PY=""
for cand in python3 python py; do
  command -v "$cand" >/dev/null 2>&1 || continue
  "$cand" -c "" >/dev/null 2>&1 || continue
  PY="$cand"; break
done
[ -n "$PY" ] || { echo "hooks-test: no working python found" >&2; exit 2; }

ok()   { printf '  ok    %s\n' "$1"; }
fail() { printf '  FAIL  %s\n' "$1"; FAILED=1; }
assert_contains()     { case "$2" in *"$1"*) ok "$3" ;; *) fail "$3 (expected: $1)";; esac; }
assert_not_contains() { case "$2" in *"$1"*) fail "$3 (did NOT expect: $1)" ;; *) ok "$3";; esac; }

# run_hook <script> <json> -> sets RC and OUT (stdout+stderr)
run_hook() {
  OUT=$(printf '%s' "$2" | "$PY" "$HOOKS/$1" 2>&1)
  RC=$?
}

echo "building fixture..."
"$PY" "$HERE/make-fixture-board.py" "$FIX" >/dev/null || { echo "fixture build failed"; exit 2; }

# ---------------------------------------------------------------- claim guard
echo "lane-claim-guard"

export LANE_CLAIM_REPO="$FIX"

run_hook lane-claim-guard.py '{"prompt":"/lm demo-alpha","session_id":"s1"}'
[ "$RC" = "2" ] && ok "blocks /lm on a job holding a FRESH claim" \
                || fail "should block /lm on a claimed job (rc=$RC, out=$OUT)"
case "$OUT" in *BLOCKED*) ok "and says why" ;; *) fail "the block must explain itself" ;; esac
case "$OUT" in *force*) ok "and names the override" ;; *) fail "the block must name the override" ;; esac

run_hook lane-claim-guard.py '{"prompt":"/lanes:lm demo-alpha","session_id":"s1"}'
[ "$RC" = "2" ] && ok "the long form /lanes:lm is blocked too" \
                || fail "/lanes:lm slipped past the claim guard (rc=$RC)"

run_hook lane-claim-guard.py '{"prompt":"/pd demo-alpha","session_id":"s1"}'
[ "$RC" = "2" ] && ok "blocks /pd on the same claimed job" \
                || fail "should block /pd too (rc=$RC)"

run_hook lane-claim-guard.py '{"prompt":"/lm force demo-alpha","session_id":"s1"}'
[ "$RC" = "0" ] && ok "the word force lets it through" || fail "force must pass (rc=$RC)"

run_hook lane-claim-guard.py '{"prompt":"/lm demo-beta","session_id":"s1"}'
[ "$RC" = "0" ] && ok "an unclaimed job passes" || fail "unclaimed job must pass (rc=$RC)"

run_hook lane-claim-guard.py '{"prompt":"what is going on","session_id":"s1"}'
[ "$RC" = "0" ] && ok "an ordinary prompt is ignored" || fail "ordinary prompts must pass (rc=$RC)"

run_hook lane-claim-guard.py '{"prompt":"/lm no-such-project-anywhere","session_id":"s1"}'
[ "$RC" = "0" ] && ok "an unknown name fails OPEN" || fail "unknown names must pass (rc=$RC)"

LANE_CLAIM_REPO="$HERE/definitely-not-a-board" \
  OUT=$(printf '%s' '{"prompt":"/lm demo-alpha","session_id":"s1"}' | "$PY" "$HOOKS/lane-claim-guard.py" 2>&1)
[ "$?" = "0" ] && ok "no board at all fails OPEN, silently" || fail "a missing board must not block"

unset LANE_CLAIM_REPO

# ------------------------------------------------------------------- pd guard
echo "pd-guard"

# Point the guard at a throwaway lock. Never touch the real one: a test run on a
# working machine would otherwise move a live session's lock aside, and a /pd
# prompt landing in that window would get the wrong answer.
LOCK="$(mktemp -u)"
export LANES_PD_LOCK="$LOCK"

run_hook pd-guard.py '{"hook_event_name":"UserPromptSubmit","prompt":"/pd alpha","session_id":"first"}'
[ "$RC" = "0" ] && ok "the first /pd takes the lock" || fail "first /pd must pass (rc=$RC)"

run_hook pd-guard.py '{"hook_event_name":"UserPromptSubmit","prompt":"/pd beta","session_id":"second"}'
[ "$RC" = "2" ] && ok "a second /pd from another session is blocked" \
                || fail "second /pd must be blocked (rc=$RC)"
case "$OUT" in *"PD GUARD"*) ok "and says why" ;; *) fail "the block must explain itself" ;; esac
run_hook pd-guard.py '{"hook_event_name":"UserPromptSubmit","prompt":"/lanes:pd beta","session_id":"second"}'
[ "$RC" = "2" ] && ok "the long form /lanes:pd is blocked too" \
                || fail "/lanes:pd slipped past the lock (rc=$RC)"

run_hook pd-guard.py '{"hook_event_name":"UserPromptSubmit","prompt":"/pd alpha","session_id":"first"}'
[ "$RC" = "0" ] && ok "the holder may keep working" || fail "the lock holder must not block itself"

run_hook pd-guard.py '{"hook_event_name":"UserPromptSubmit","prompt":"/pd force beta","session_id":"second"}'
[ "$RC" = "0" ] && ok "force steals the lock" || fail "force must pass (rc=$RC)"
case "$OUT" in *stole*) ok "and says it stole it" ;; *) fail "stealing must be said out loud" ;; esac

run_hook pd-guard.py '{"hook_event_name":"UserPromptSubmit","prompt":"/lm alpha","session_id":"third"}'
[ "$RC" = "0" ] && ok "/lm is not affected by the /pd lock" || fail "/lm must pass (rc=$RC)"

run_hook pd-guard.py '{"hook_event_name":"SessionEnd","session_id":"second"}'
[ "$RC" = "0" ] && ok "SessionEnd releases cleanly" || fail "SessionEnd must pass (rc=$RC)"
[ -f "$LOCK" ] && fail "SessionEnd should have removed the lock" || ok "and the lock is gone"

rm -f "$LOCK"
unset LANES_PD_LOCK
ok "the real lock was never touched"

# --------------------------------------------------------------- reader guard
echo "reader-guard"

# 0.4.0: the reader guard is STATELESS. It keys on `agent_id` in the payload, which a
# subagent's tool call carries and the parent session's never does (task zero,
# docs/specs/2026-09-10-task-zero-result.md). So there is no marker to protect; the
# only real file it can touch is its refusal log, which is pointed at a throwaway
# here and compared before/after, for the same reason as the lock above (fault 4).
REAL_RLOG="$HOME/.claude/lanes-reader-refusals.log"
REAL_RBEFORE="absent"
[ -f "$REAL_RLOG" ] && REAL_RBEFORE="$(wc -c < "$REAL_RLOG") $(date -r "$REAL_RLOG" +%s 2>/dev/null)"
RLOG="$(mktemp -u)"
CONF="$(mktemp -u)"
printf 'board = /nowhere/fixture-board\n' > "$CONF"
export LANES_READER_LOG="$RLOG"
export LANES_CONFIG="$CONF"

PARENT='{"hook_event_name":"PreToolUse","session_id":"s1","tool_name":"Write","tool_input":{"file_path":"/nowhere/fixture-board/status/alpha.md"}}'
READER='{"hook_event_name":"PreToolUse","session_id":"s1","agent_id":"a9","agent_type":"general-purpose","tool_name":"Write","tool_input":{"file_path":"/nowhere/fixture-board/status/alpha.md"}}'

run_hook reader-guard.py "$PARENT"
[ "$RC" = "0" ] && ok "the session itself may write the status file (no agent_id)" \
                || fail "a parent write must never be refused (rc=$RC)"

run_hook reader-guard.py "$READER"
[ "$RC" = "2" ] && ok "a subagent (agent_id present) is refused the status file" \
                || fail "the reader must be blocked (rc=$RC)"
case "$OUT" in *"READER GUARD"*) ok "and says why" ;; *) fail "the block must explain itself" ;; esac
case "$OUT" in *inbox*) ok "and names the way to hand the finding back" ;;
               *) fail "a block must say what to do instead" ;; esac
[ -f "$RLOG" ] && ok "and the refusal was recorded for run-log.sh --reader" \
              || fail "a refusal must be logged (no $RLOG)"

# Same session id in both payloads above: the discriminator is agent_id, NOT the session.
run_hook reader-guard.py '{"hook_event_name":"PreToolUse","session_id":"s1","agent_id":"","tool_name":"Write","tool_input":{"file_path":"/nowhere/fixture-board/status/alpha.md"}}'
[ "$RC" = "0" ] && ok "an EMPTY agent_id counts as the session itself" \
                || fail "empty agent_id must not refuse (rc=$RC)"

# A Windows-shaped path for the same file: separators and case must not matter.
run_hook reader-guard.py '{"hook_event_name":"PreToolUse","session_id":"s1","agent_id":"a9","tool_name":"Edit","tool_input":{"file_path":"C:\\X\\Fixture-Board\\Status\\Alpha.md"}}'
[ "$RC" = "2" ] && ok "a backslash path in the wrong case is the same file" \
                || fail "path matching must be separator- and case-insensitive (rc=$RC)"

run_hook reader-guard.py '{"hook_event_name":"PreToolUse","session_id":"s1","agent_id":"a9","tool_name":"Write","tool_input":{"file_path":"/nowhere/fixture-board/notes/alpha.md"}}'
[ "$RC" = "0" ] && ok "everything outside status/ is untouched" \
                || fail "the guard must stay narrow (rc=$RC)"

run_hook reader-guard.py '{"hook_event_name":"PreToolUse","session_id":"s1","agent_id":"a9","tool_name":"Write","tool_input":{"file_path":"/nowhere/fixture-board/status/alpha.md.bak"}}'
[ "$RC" = "0" ] && ok "a non-.md file under status/ is not the board" \
                || fail "only *.md under status/ is guarded (rc=$RC)"

run_hook reader-guard.py '{"hook_event_name":"PreToolUse","session_id":"s1","agent_id":"a9","tool_name":"Bash","tool_input":{"command":"echo x > /nowhere/fixture-board/status/alpha.md"}}'
[ "$RC" = "2" ] && ok "a redirect in Bash is caught too" || fail "Bash writes must be caught (rc=$RC)"

run_hook reader-guard.py '{"hook_event_name":"PreToolUse","session_id":"s1","agent_id":"a9","tool_name":"Bash","tool_input":{"command":"grep -i alpha /nowhere/fixture-board/status/alpha.md"}}'
[ "$RC" = "0" ] && ok "but READING it in Bash is not" || fail "a read must never be blocked (rc=$RC)"

run_hook reader-guard.py '{"hook_event_name":"PreToolUse","session_id":"s1","agent_id":"a9","tool_name":"Read","tool_input":{"file_path":"/nowhere/fixture-board/status/alpha.md"}}'
[ "$RC" = "0" ] && ok "the Read tool is never a write" || fail "Read must pass (rc=$RC)"

run_hook reader-guard.py '{"hook_event_name":"UserPromptSubmit","session_id":"s1","agent_id":"a9","prompt":"/pd alpha"}'
[ "$RC" = "0" ] && ok "any event other than PreToolUse is ignored" || fail "non-PreToolUse must pass (rc=$RC)"

# Fail-open: no board resolvable at all.
printf '\n' > "$CONF"
run_hook reader-guard.py "$READER"
[ "$RC" = "0" ] && ok "no board configured fails OPEN, silently" \
                || fail "a guard that cannot resolve a board must not block (rc=$RC)"

run_hook reader-guard.py 'this is not json'
[ "$RC" = "0" ] && ok "unreadable input fails OPEN" || fail "garbage input must not block (rc=$RC)"

rm -f "$RLOG" "$CONF"
unset LANES_READER_LOG LANES_CONFIG

REAL_RAFTER="absent"
[ -f "$REAL_RLOG" ] && REAL_RAFTER="$(wc -c < "$REAL_RLOG") $(date -r "$REAL_RLOG" +%s 2>/dev/null)"
[ "$REAL_RBEFORE" = "$REAL_RAFTER" ] && ok "the real refusal log was never touched" \
                                     || fail "this test disturbed $REAL_RLOG"

echo "theme-apply: the first session puts the plugin's look on the profile it runs in, once, and restore undoes it (0.41.0)"
TH="$(mktemp -d)"
THP="$(cygpath -m "$TH" 2>/dev/null || echo "$TH")"
mkdir -p "$TH/wt" "$TH/claude" "$TH/state"
printf '// Windows Terminal keeps comments here\n{\n  "defaultProfile": "{aaaa}",\n  "profiles": { "list": [\n    { "guid": "{aaaa}", "name": "Plain", "colorScheme": "Campbell", },\n    { "guid": "{bbbb}", "name": "Themed", "experimental.pixelShaderPath": "C:/their/own.hlsl" }\n  ] },\n  "schemes": []\n}\n' > "$TH/wt/settings.json"
printf '{\n  "theme": "dark"\n}\n' > "$TH/claude/settings.json"
export LANES_STATE_DIR="$THP/state" LANES_WT_SETTINGS="$THP/wt/settings.json" LANES_CLAUDE_DIR="$THP/claude" LANES_THEME_NO_FONT=1 WT_PROFILE_ID="{aaaa}"
unset LANES_CONFIG
out=$(bash "$HERE/../../hooks/theme-apply" 2>&1)
assert_contains "now has the plugin's look" "$out" "the hook says the look went on"
assert_contains "restart" "$out" "and that Claude Code's own colours follow after a restart"
grep -q 'lanes.hlsl' "$TH/wt/settings.json" && ok "the profile points at the shader" || fail "no shader path in the profile"
grep -q '"name": "RobCo"' "$TH/wt/settings.json" && ok "the RobCo scheme was added" || fail "no RobCo scheme"
grep -q 'their/own.hlsl' "$TH/wt/settings.json" && ok "the other profile's own look is untouched" || fail "the other profile was changed"
[ -f "$TH/wt/settings.json.lanes-backup" ] && ok "the terminal's settings were backed up first" || fail "no backup"
grep -q '"custom:robco"' "$TH/claude/settings.json" && ok "Claude Code's theme is RobCo" || fail "Claude Code's theme was not set"
[ -f "$TH/claude/themes/robco.json" ] && ok "the RobCo theme file is in place" || fail "no robco.json"
[ -f "$TH/state/theme/green-monitor-lanes/lanes.png" ] && ok "the style's files were copied to a folder that survives updates" || fail "style not copied"
assert_not_contains "$THP" "$out" "no path in what the user is told"
out=$(bash "$HERE/../../hooks/theme-apply" 2>&1)
[ -z "$out" ] && ok "once applied, the hook is silent" || fail "the hook repeats itself: $out"
out=$("$PY" "$HERE/../../tools/theme.py" restore 2>&1)
assert_contains "back as they were" "$out" "restore says so"
grep -q 'lanes.hlsl' "$TH/wt/settings.json" && fail "the shader path is still there after restore" || ok "the profile is back to plain"
grep -q '"colorScheme": "Campbell"' "$TH/wt/settings.json" && ok "its old scheme is back" || fail "the old scheme did not come back"
grep -q '"theme": "dark"' "$TH/claude/settings.json" && ok "Claude Code's old theme is back" || fail "Claude Code's theme did not come back"
[ -f "$TH/state/theme-state.json" ] && fail "the state file survived restore" || ok "restore cleared the state, so a later apply works again"
WT_PROFILE_ID="{bbbb}" out=$(bash "$HERE/../../hooks/theme-apply" 2>&1)
assert_contains "already has a look of its own" "$out" "a profile that already has a shader is left alone"
grep -q 'their/own.hlsl' "$TH/wt/settings.json" && ok "and really was left alone" || fail "the existing look was replaced"
rm -f "$TH/state/theme-state.json"
out=$(LANES_THEME=0 bash "$HERE/../../hooks/theme-apply" 2>&1)
[ -z "$out" ] && ok "LANES_THEME=0 switches the hook off" || fail "LANES_THEME=0 did not switch it off"
printf 'theme = off\n' > "$TH/lanes.conf"
out=$(LANES_CONFIG="$THP/lanes.conf" bash "$HERE/../../hooks/theme-apply" 2>&1)
[ -z "$out" ] && ok "theme = off in lanes.conf switches it off" || fail "theme = off did not switch it off"
out=$(LANES_WT_SETTINGS="$THP/nowhere.json" bash "$HERE/../../hooks/theme-apply" 2>&1)
assert_contains "needs Windows Terminal" "$out" "with no Windows Terminal it says so"
out=$(LANES_WT_SETTINGS="$THP/nowhere.json" bash "$HERE/../../hooks/theme-apply" 2>&1)
[ -z "$out" ] && ok "and says it once" || fail "the no-terminal line repeats"
# 0.41.1: a profile the plugin has to CREATE (no WT_PROFILE_ID, so not running inside Windows Terminal)
# gets a start folder, or the tab would open in system32
printf '{ "profiles": { "list": [ { "guid": "{cccc}", "name": "Plain" } ] }, "schemes": [] }\n' > "$TH/wt/fresh.json"
rm -rf "$TH/state"; mkdir -p "$TH/state"
out=$(env -u WT_PROFILE_ID LANES_WT_SETTINGS="$THP/wt/fresh.json" bash "$HERE/../../hooks/theme-apply" 2>&1)
grep -q '"startingDirectory"' "$TH/wt/fresh.json" && ok "a created Green Monitor Claude profile has a start folder" || fail "the created profile has no startingDirectory (it would open in system32)"
grep -qi 'system32' "$TH/wt/fresh.json" && fail "the start folder is system32" || ok "and it is not system32"
# 0.51.0: a PC still showing the old shipped starburst is moved to the banner once; a look of its own is kept
rm -rf "$TH/state"; mkdir -p "$TH/state"
printf '{ "profiles": { "list": [ { "guid": "{dddd}", "name": "Old", "experimental.pixelShaderPath": "C:/x/theme/green-monitor-starburst/starburst.hlsl", "experimental.pixelShaderImagePath": "C:/x/theme/green-monitor-starburst/starburst.png" } ] }, "schemes": [] }
' > "$TH/wt/old.json"
printf '{ "applied": true, "settings": "%s", "profile_guid": "{dddd}", "style_home": "C:/x/theme/green-monitor-starburst" }
' "$THP/wt/old.json" > "$TH/state/theme-state.json"
out=$(LANES_WT_SETTINGS="$THP/wt/old.json" bash "$HERE/../../hooks/theme-apply" 2>&1)
assert_contains "new picture" "$out" "a PC on the old starburst hears the picture changed"
grep -q 'green-monitor-lanes/lanes.hlsl' "$TH/wt/old.json" && ok "its profile now shows the banner" || fail "the old starburst profile was not moved over"
out=$(LANES_WT_SETTINGS="$THP/wt/old.json" bash "$HERE/../../hooks/theme-apply" 2>&1)
[ -z "$out" ] && ok "the move happens once" || fail "the upgrade repeats: $out"
printf '{ "profiles": { "list": [ { "guid": "{eeee}", "name": "Mine", "experimental.pixelShaderPath": "C:/their/own.hlsl" } ] }, "schemes": [] }
' > "$TH/wt/mine.json"
printf '{ "applied": true, "settings": "%s", "profile_guid": "{eeee}", "style_home": "C:/x/theme/green-monitor-starburst" }
' "$THP/wt/mine.json" > "$TH/state/theme-state.json"
out=$(LANES_WT_SETTINGS="$THP/wt/mine.json" bash "$HERE/../../hooks/theme-apply" 2>&1)
grep -q 'their/own.hlsl' "$TH/wt/mine.json" && ok "a look picked since is kept on upgrade" || fail "the upgrade replaced a look of their own"
unset LANES_STATE_DIR LANES_WT_SETTINGS LANES_CLAUDE_DIR LANES_THEME_NO_FONT WT_PROFILE_ID
rm -rf "$TH"
grep -q 'theme-apply' "$HERE/../../hooks/hooks.json" && ok "the theme hook is registered for session start" || fail "hooks.json does not run theme-apply"

echo
if [ "$FAILED" -eq 0 ]; then echo "hooks-test: all assertions passed"; else echo "hooks-test: FAILURES above"; fi
exit "$FAILED"
