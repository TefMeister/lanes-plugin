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

run_hook lane-claim-guard.py '{"prompt":"/ms demo-alpha","session_id":"s1"}'
[ "$RC" = "2" ] && ok "a typed /ms on a claimed job is blocked (2026-11-02)" || fail "/ms on a claimed job must be blocked (rc=$RC)"
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
# a PC that had Lanes before (the look is on there): without this, an empty state folder and a lanes.conf written in
# the last five minutes made features.py call this a NEW install, the look off, and every check below failed (0.90.0)
printf '{"kind": "update", "since": "0.84.0"}' > "$TH/state/features-state.json"
export LANES_STATE_DIR="$THP/state" LANES_WT_SETTINGS="$THP/wt/settings.json" LANES_CLAUDE_DIR="$THP/claude" LANES_THEME_NO_FONT=1 WT_PROFILE_ID="{aaaa}"
unset LANES_CONFIG
out=$(bash "$HERE/../../hooks/theme-apply" 2>&1)
assert_contains "now has the plugin's look" "$out" "the hook says the look went on"
assert_contains "restart" "$out" "and that Claude Code's own colours follow after a restart"
grep -q 'green-monitor-lanes/lanes-still.hlsl' "$TH/wt/settings.json" && ok "the profile points at the still shader (the default since 2026-11-01)" || fail "the profile is not on the still shader"
assert_contains "motion animated" "$out" "the user hears how to get the moving light"
grep -q '"name": "RobCo"' "$TH/wt/settings.json" && ok "the RobCo scheme was added" || fail "no RobCo scheme"
grep -q 'their/own.hlsl' "$TH/wt/settings.json" && ok "the other profile's own look is untouched" || fail "the other profile was changed"
[ -f "$TH/wt/settings.json.lanes-backup" ] && ok "the terminal's settings were backed up first" || fail "no backup"
grep -q '"custom:robco"' "$TH/claude/settings.json" && ok "Claude Code's theme is RobCo" || fail "Claude Code's theme was not set"
[ -f "$TH/claude/themes/robco.json" ] && ok "the RobCo theme file is in place" || fail "no robco.json"
[ -f "$TH/state/theme/green-monitor-lanes/lanes.png" ] && ok "the style's files were copied to a folder that survives updates" || fail "style not copied"
assert_not_contains "$THP" "$out" "no path in what the user is told"
out=$(bash "$HERE/../../hooks/theme-apply" 2>&1)
[ -z "$out" ] && ok "once applied, the hook is silent" || fail "the hook repeats itself: $out"
out=$("$PY" "$HERE/../../tools/theme.py" motion animated 2>&1)
grep -q 'green-monitor-lanes/lanes.hlsl' "$TH/wt/settings.json" && ok "motion animated puts the moving shader on" || fail "motion animated did not switch the shader"
assert_contains "a bit more of the processor" "$out" "and warns that it uses a bit more of the PC"
out=$(bash "$HERE/../../hooks/theme-apply" 2>&1)
[ -z "$out" ] && ok "a chosen moving light is never switched back by the hook" || fail "the hook undid the user's choice: $out"
out=$("$PY" "$HERE/../../tools/theme.py" motion still 2>&1)
grep -q 'green-monitor-lanes/lanes-still.hlsl' "$TH/wt/settings.json" && ok "motion still switches back" || fail "motion still did not switch back"
out=$("$PY" "$HERE/../../tools/theme.py" restore 2>&1)
assert_contains "back as they were" "$out" "restore says so"
grep -q 'green-monitor-lanes/' "$TH/wt/settings.json" && fail "the shader path is still there after restore" || ok "the profile is back to plain"
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
rm -rf "$TH/state"; mkdir -p "$TH/state"; printf '{"kind": "update", "since": "0.84.0"}' > "$TH/state/features-state.json"
out=$(env -u WT_PROFILE_ID LANES_WT_SETTINGS="$THP/wt/fresh.json" bash "$HERE/../../hooks/theme-apply" 2>&1)
grep -q '"startingDirectory"' "$TH/wt/fresh.json" && ok "a created Green Monitor Claude profile has a start folder" || fail "the created profile has no startingDirectory (it would open in system32)"
grep -qi 'system32' "$TH/wt/fresh.json" && fail "the start folder is system32" || ok "and it is not system32"
# 0.51.0: a PC still showing the old shipped starburst is moved to the banner once; a look of its own is kept
rm -rf "$TH/state"; mkdir -p "$TH/state"; printf '{"kind": "update", "since": "0.84.0"}' > "$TH/state/features-state.json"
printf '{ "profiles": { "list": [ { "guid": "{dddd}", "name": "Old", "experimental.pixelShaderPath": "C:/x/theme/green-monitor-starburst/starburst.hlsl", "experimental.pixelShaderImagePath": "C:/x/theme/green-monitor-starburst/starburst.png" } ] }, "schemes": [] }
' > "$TH/wt/old.json"
printf '{ "applied": true, "settings": "%s", "profile_guid": "{dddd}", "style_home": "C:/x/theme/green-monitor-starburst" }
' "$THP/wt/old.json" > "$TH/state/theme-state.json"
out=$(LANES_WT_SETTINGS="$THP/wt/old.json" bash "$HERE/../../hooks/theme-apply" 2>&1)
assert_contains "new picture" "$out" "a PC on the old starburst hears the picture changed"
grep -q 'green-monitor-lanes/lanes-still.hlsl' "$TH/wt/old.json" && ok "its profile now shows the banner, still" || fail "the old starburst profile was not moved over"
out=$(LANES_WT_SETTINGS="$THP/wt/old.json" bash "$HERE/../../hooks/theme-apply" 2>&1)
[ -z "$out" ] && ok "the move happens once" || fail "the upgrade repeats: $out"
printf '{ "profiles": { "list": [ { "guid": "{eeee}", "name": "Mine", "experimental.pixelShaderPath": "C:/their/own.hlsl" } ] }, "schemes": [] }
' > "$TH/wt/mine.json"
printf '{ "applied": true, "settings": "%s", "profile_guid": "{eeee}", "style_home": "C:/x/theme/green-monitor-starburst" }
' "$THP/wt/mine.json" > "$TH/state/theme-state.json"
out=$(LANES_WT_SETTINGS="$THP/wt/mine.json" bash "$HERE/../../hooks/theme-apply" 2>&1)
grep -q 'their/own.hlsl' "$TH/wt/mine.json" && ok "a look picked since is kept on upgrade" || fail "the upgrade replaced a look of their own"
# 2026-11-01: a PC on the shipped moving banner (state from before "motion" existed) is moved to the still one, once
printf '{ "profiles": { "list": [ { "guid": "{ffff}", "name": "Moving", "experimental.pixelShaderPath": "C:/x/theme/green-monitor-lanes/lanes.hlsl" } ] }, "schemes": [] }
' > "$TH/wt/moving.json"
printf '{ "applied": true, "settings": "%s", "profile_guid": "{ffff}", "style_home": "C:/x/theme/green-monitor-lanes" }
' "$THP/wt/moving.json" > "$TH/state/theme-state.json"
out=$(LANES_WT_SETTINGS="$THP/wt/moving.json" bash "$HERE/../../hooks/theme-apply" 2>&1)
assert_contains "still by default" "$out" "a PC on the moving banner hears it is still now"
assert_contains "motion animated" "$out" "and how to get the moving light back"
grep -q 'green-monitor-lanes/lanes-still.hlsl' "$TH/wt/moving.json" && ok "its profile now shows the still banner" || fail "the moving banner was not moved to the still one"
out=$(LANES_WT_SETTINGS="$THP/wt/moving.json" bash "$HERE/../../hooks/theme-apply" 2>&1)
[ -z "$out" ] && ok "that move happens once" || fail "the still move repeats: $out"
unset LANES_STATE_DIR LANES_WT_SETTINGS LANES_CLAUDE_DIR LANES_THEME_NO_FONT WT_PROFILE_ID
rm -rf "$TH"
grep -q 'theme-apply' "$HERE/../../hooks/hooks.json" && ok "the theme hook is registered for session start" || fail "hooks.json does not run theme-apply"

echo
echo "shortcut-offer: once the look is on, a desktop shortcut named Lanes is offered once; the tool makes it (0.53.0)"
SH="$(mktemp -d)"; SHP="$(cd "$SH" && pwd -W 2>/dev/null || pwd)"
mkdir -p "$SH/state" "$SH/desk"
export LANES_STATE_DIR="$SHP/state" LANES_DESKTOP="$SHP/desk" LANES_WT_EXE="C:/fake/wt.exe"
out=$(bash "$HERE/../../hooks/shortcut-offer" 2>&1)
[ -z "$out" ] && ok "with no look on this PC the hook stays silent" || fail "the hook offered a shortcut with no look to open"
printf '{ "applied": false, "reason": "no Windows Terminal on this PC" }\n' > "$SH/state/theme-state.json"
out=$(bash "$HERE/../../hooks/shortcut-offer" 2>&1)
[ -z "$out" ] && ok "a look that could not be applied gives no offer" || fail "offered although the look is not on"
printf '{ "applied": true, "profile_guid": "{dddd}", "style_home": "%s/state/theme/green-monitor-lanes" }\n' "$SHP" > "$SH/state/theme-state.json"
out=$(bash "$HERE/../../hooks/shortcut-offer" 2>&1)
assert_contains 'LANES SHORTCUT' "$out" "with the look on, the offer is made"
assert_contains 'Desktop' "$out" "and it is for the Desktop"
assert_contains 'shortcut.py' "$out" "and it names the tool"
out=$("$PY" "$HERE/../../tools/shortcut.py" create --dry-run --folder "$SHP/work" 2>&1)
assert_contains '-p "{dddd}"' "$out" "the shortcut opens the profile the look is on"
assert_contains 'claude' "$out" "and starts Claude Code"
assert_contains "$SHP/desk" "$out" "on the Desktop"
assert_contains 'Lanes.lnk' "$out" "named Lanes"
assert_contains 'dry run' "$out" "a dry run makes nothing"
[ -f "$SH/desk/Lanes.lnk" ] && fail "the dry run made a file" || ok "no file was made"
[ -f "$HERE/../../theme/green-monitor-lanes/lanes.ico" ] && ok "the icon ships with the style" || fail "lanes.ico is missing from the style"
out=$("$PY" "$HERE/../../tools/shortcut.py" decline 2>&1)
assert_contains 'not be offered again' "$out" "no is remembered"
out=$(bash "$HERE/../../hooks/shortcut-offer" 2>&1)
[ -z "$out" ] && ok "after a no the hook stays silent" || fail "the offer repeated after a no"
out=$("$PY" "$HERE/../../tools/shortcut.py" status 2>&1)
assert_contains 'declined' "$out" "status says it was declined"
rm -f "$SH/state/shortcut-state.json"
out=$(LANES_SHORTCUT=0 bash "$HERE/../../hooks/shortcut-offer" 2>&1)
[ -z "$out" ] && ok "LANES_SHORTCUT=0 switches the offer off" || fail "LANES_SHORTCUT=0 did not switch it off"
printf 'shortcut = off\n' > "$SH/lanes.conf"
out=$(LANES_CONFIG="$SHP/lanes.conf" bash "$HERE/../../hooks/shortcut-offer" 2>&1)
[ -z "$out" ] && ok "shortcut = off in lanes.conf switches it off" || fail "shortcut = off did not switch it off"
out=$("$PY" "$HERE/../../tools/shortcut.py" remove 2>&1)
assert_contains 'nothing to remove' "$out" "remove with nothing on record says so"
unset LANES_STATE_DIR LANES_DESKTOP LANES_WT_EXE
rm -rf "$SH"
grep -q 'shortcut-offer' "$HERE/../../hooks/hooks.json" && ok "the shortcut hook is registered for session start" || fail "hooks.json does not run shortcut-offer"

# ---------------------------------------------------------------- repo guard (0.58.0)
echo "repo-guard"
RG=$(mktemp -d); RGP=$(cygpath -m "$RG" 2>/dev/null || echo "$RG")
export LANES_CONFIG="$RGP/lanes.conf"; : > "$RG/lanes.conf"
rg_bash() { run_hook repo-guard.py "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":$(printf '%s' "$1" | "$PY" -c 'import json,sys;print(json.dumps(sys.stdin.read()))')}}"; }
rg_bash 'gh repo create someone/new-game --private --clone'
[ "$RC" = "0" ] && [ -z "$OUT" ] && ok "--private passes silently" || fail "--private should pass (rc=$RC, out=$OUT)"
rg_bash 'gh repo create someone/new-game --clone'
[ "$RC" = "2" ] && ok "no visibility flag is refused" || fail "no flag should be refused (rc=$RC)"
assert_contains '--private' "$OUT" "the refusal says to add --private"
rg_bash 'gh repo create someone/new-game --public'
[ "$RC" = "0" ] && assert_contains '"permissionDecision": "ask"' "$OUT" "--public asks the person" || fail "--public should ask (rc=$RC)"
rg_bash 'gh repo create a --private && gh repo create b --public'
assert_contains '"ask"' "$OUT" "a public repo later in the same line still asks"
rg_bash 'gh repo edit someone/x --visibility public --accept-visibility-change-consequences'
assert_contains '"ask"' "$OUT" "turning a repo public asks"
rg_bash 'gh api user/repos -f name=x'
[ "$RC" = "2" ] && ok "an API repo create without private=true is refused" || fail "API create should be refused (rc=$RC)"
rg_bash 'gh api user/repos -f name=x -F private=true'
[ "$RC" = "0" ] && [ -z "$OUT" ] && ok "an API create with private=true passes" || fail "API private create should pass (rc=$RC)"
rg_bash 'python "$P/tools/estate.py" project my-game --public'
assert_contains '"ask"' "$OUT" "a public project from estate.py asks"
rg_bash 'python "$P/tools/estate.py" project my-game'
[ "$RC" = "0" ] && [ -z "$OUT" ] && ok "a private project from estate.py passes" || fail "estate.py private project should pass (rc=$RC)"
rg_bash 'gh repo view someone/x; git push'
[ "$RC" = "0" ] && [ -z "$OUT" ] && ok "other gh commands pass" || fail "other gh commands should pass (rc=$RC)"
run_hook repo-guard.py 'this is not json'
[ "$RC" = "0" ] && ok "bad input passes (never fails closed)" || fail "bad input must pass (rc=$RC)"
printf 'new_repos = public\n' > "$RG/lanes.conf"
rg_bash 'gh repo create someone/new-game'
[ "$RC" = "0" ] && [ -z "$OUT" ] && ok "new_repos = public switches the guard off" || fail "new_repos = public should switch it off (rc=$RC)"
out=$(LANES_CONFIG="$RG/lanes.conf" bash "$HOOKS/repo-rule" 2>&1)
[ -z "$out" ] && ok "new_repos = public silences the session-start rule" || fail "repo-rule should be silent with new_repos = public"
: > "$RG/lanes.conf"
out=$(LANES_CONFIG="$RG/lanes.conf" CLAUDE_PLUGIN_ROOT=x bash "$HOOKS/repo-rule" 2>&1)
assert_contains 'private by default' "$out" "the session-start rule is printed by default"
unset LANES_CONFIG; rm -rf "$RG"
grep -q 'repo-guard.py' "$HOOKS/hooks.json" && grep -q 'repo-rule' "$HOOKS/hooks.json" \
  && ok "repo-guard and repo-rule are registered" || fail "hooks.json is missing repo-guard or repo-rule"

# ---------------------------------------------------------------- update hold (lanes-next, 2026-11-01)
echo "update-hold-guard"
UH=$(mktemp -d); UHP=$(cygpath -m "$UH" 2>/dev/null || echo "$UH")
export LANES_STATE_DIR="$UHP" LANES_CONFIG="$UHP/lanes.conf"; : > "$UH/lanes.conf"
uh_bash() { run_hook update-hold-guard.py "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":$(printf '%s' "$1" | "$PY" -c 'import json,sys;print(json.dumps(sys.stdin.read()))')}}"; }
uh_bash 'claude plugin update lanes@lanes-plugin'
[ "$RC" = "0" ] && [ -z "$OUT" ] && ok "no hold: an update passes" || fail "no hold should pass (rc=$RC)"
"$PY" "$HERE/../hold.py" status >/dev/null 2>&1; [ "$?" = "1" ] && ok "hold status says off (exit 1)" || fail "status should exit 1 with no hold"
"$PY" "$HERE/../hold.py" on >/dev/null 2>&1; [ "$?" = "2" ] && ok "a hold without a reason is refused" || fail "hold on with no reason should exit 2"
"$PY" "$HERE/../hold.py" on "two-PC test" --hours 2 >/dev/null 2>&1
"$PY" "$HERE/../hold.py" status >/dev/null 2>&1; [ "$?" = "0" ] && ok "hold on -> status says on" || fail "status should exit 0 with a hold"
uh_bash 'claude plugin update lanes@lanes-plugin'
[ "$RC" = "2" ] && ok "held: claude plugin update lanes is refused" || fail "held update should be refused (rc=$RC)"
assert_contains 'two-PC test' "$OUT" "the refusal names the reason"
uh_bash 'claude plugin marketplace update lanes-plugin && claude plugin update lanes@lanes-plugin'
[ "$RC" = "2" ] && ok "held: a marketplace update of Lanes is refused" || fail "held marketplace update should be refused (rc=$RC)"
uh_bash 'claude plugin marketplace update'
[ "$RC" = "2" ] && ok "held: updating every marketplace is refused" || fail "bare marketplace update should be refused (rc=$RC)"
uh_bash 'claude plugin install lanes@lanes-plugin'
[ "$RC" = "2" ] && ok "held: a reinstall is refused" || fail "held install should be refused (rc=$RC)"
uh_bash 'python "$P/tools/uninstall.py" --yes'
[ "$RC" = "2" ] && ok "held: uninstall.py is refused" || fail "held uninstall should be refused (rc=$RC)"
uh_bash 'claude plugin update superpowers@claude-plugins-official'
[ "$RC" = "0" ] && [ -z "$OUT" ] && ok "held: another plugin's update passes" || fail "other plugin update should pass (rc=$RC)"
uh_bash 'claude plugin marketplace update claude-plugins-official'
[ "$RC" = "0" ] && [ -z "$OUT" ] && ok "held: another marketplace's update passes" || fail "other marketplace should pass (rc=$RC)"
uh_bash 'python "$P/tools/update-check.py" --json; git pull'
[ "$RC" = "0" ] && [ -z "$OUT" ] && ok "held: checking for an update passes" || fail "update-check should pass (rc=$RC)"
printf 'update_hold = off\n' > "$UH/lanes.conf"
uh_bash 'claude plugin update lanes@lanes-plugin'
[ "$RC" = "0" ] && ok "update_hold = off ignores the hold" || fail "feature off should pass (rc=$RC)"
: > "$UH/lanes.conf"
"$PY" -c "import json,time;p=r'$UHP/update-hold.json';h=json.load(open(p));h['until']=time.time()-1;json.dump(h,open(p,'w'))"
uh_bash 'claude plugin update lanes@lanes-plugin'
[ "$RC" = "0" ] && ok "an expired hold no longer blocks" || fail "expired hold should pass (rc=$RC)"
"$PY" "$HERE/../hold.py" on "again" >/dev/null 2>&1; "$PY" "$HERE/../hold.py" off >/dev/null 2>&1
uh_bash 'claude plugin update lanes@lanes-plugin'
[ "$RC" = "0" ] && ok "hold off -> updates pass again" || fail "after off should pass (rc=$RC)"
run_hook update-hold-guard.py 'this is not json'
[ "$RC" = "0" ] && ok "bad input passes (never fails closed)" || fail "bad input must pass (rc=$RC)"
unset LANES_STATE_DIR LANES_CONFIG; rm -rf "$UH"
grep -q 'update-hold-guard.py' "$HOOKS/hooks.json" && ok "update-hold-guard is registered" || fail "hooks.json is missing update-hold-guard"

# ---------------------------------------------------------------- the launcher keeps a refusal (2026-11-01)
# Claude Code starts every hook through run-hook.cmd; on Windows that runs in cmd.exe. Until 2026-11-01 it handed
# back 0 whatever the guard said, so no refusal ever reached Claude Code. Checked through the real launcher here.
echo "run-hook.cmd exit code"
case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*)
    LH=$(mktemp -d); LHP=$(cygpath -m "$LH")
    printf '%s' '{"hook_event_name":"UserPromptSubmit","prompt":"/pd","session_id":"holder"}'       | LANES_PD_LOCK="$LHP/pd.lock" "$PY" "$HOOKS/pd-guard.py" >/dev/null 2>&1
    printf '%s' '{"hook_event_name":"UserPromptSubmit","prompt":"/pd","session_id":"second"}'       | LANES_PD_LOCK="$LHP/pd.lock" "$HOOKS/run-hook.cmd" py-hook pd-guard.py >/dev/null 2>&1; rc=$?
    [ "$rc" = "2" ] && ok "a refusal comes back through run-hook.cmd as exit 2" || fail "run-hook.cmd lost the refusal (rc=$rc, wanted 2)"
    printf '%s' '{"hook_event_name":"UserPromptSubmit","prompt":"hello","session_id":"second"}'       | LANES_PD_LOCK="$LHP/pd.lock" "$HOOKS/run-hook.cmd" py-hook pd-guard.py >/dev/null 2>&1; rc=$?
    [ "$rc" = "0" ] && ok "a pass comes back through run-hook.cmd as exit 0" || fail "run-hook.cmd pass should be 0 (rc=$rc)"
    rm -rf "$LH" ;;
  *) ok "not Windows: run-hook.cmd runs as a shell script, exit codes pass by exec" ;;
esac

# ---------------------------------------------------------------- skill-lane-guard (two-PC test, 2026-11-02)
# Claude starting the pd / lm / ms skill itself must meet the same checks as a typed command.
echo "skill-lane-guard"
SK=$(mktemp -d); SKP=$(cygpath -m "$SK" 2>/dev/null || echo "$SK")
export LANES_PD_LOCK="$SKP/pd.lock" LANE_CLAIM_REPO="$FIX"
sk() { run_hook skill-lane-guard.py "{\"hook_event_name\":\"PreToolUse\",\"tool_name\":\"Skill\",\"session_id\":\"$1\",\"tool_input\":{\"skill\":\"$2\",\"args\":\"$3\"}}"; }
sk first pd ""
[ "$RC" = "0" ] && ok "the first session's pd skill passes and takes the lock" || fail "first pd skill should pass (rc=$RC, out=$OUT)"
[ -f "$SK/pd.lock" ] && ok "and the lock file names a holder" || fail "the pd skill did not take the lock"
sk second pd ""
[ "$RC" = "2" ] && ok "a second session's pd skill is refused" || fail "second pd skill should be refused (rc=$RC)"
assert_contains 'PD GUARD' "$OUT" "the refusal carries the lock's reason"
sk second lanes:pd "demo-beta"
[ "$RC" = "2" ] && ok "the long name lanes:pd is refused too" || fail "lanes:pd should be refused (rc=$RC)"
sk first pd "demo-beta"
[ "$RC" = "0" ] && ok "the lock holder's own pd skill passes" || fail "holder should pass (rc=$RC, out=$OUT)"
sk third lm "demo-alpha"
[ "$RC" = "2" ] && ok "an lm skill on a claimed project is refused" || fail "lm on a claimed project should be refused (rc=$RC)"
assert_contains 'lane-claim-guard' "$OUT" "the refusal carries the claim guard's reason"
sk third ms "demo-alpha"
[ "$RC" = "2" ] && ok "an ms skill on a claimed project is refused" || fail "ms on a claimed project should be refused (rc=$RC, out=$OUT)"
sk third lm "demo-beta"
[ "$RC" = "0" ] && ok "an lm skill on an idle project passes" || fail "lm on an idle project should pass (rc=$RC, out=$OUT)"
sk third lm "force demo-alpha"
[ "$RC" = "0" ] && ok "lm force passes, as typed" || fail "lm force should pass (rc=$RC)"
sk third gates ""
[ "$RC" = "0" ] && [ -z "$OUT" ] && ok "other skills pass untouched" || fail "other skills should pass silently (rc=$RC)"
run_hook skill-lane-guard.py 'this is not json'
[ "$RC" = "0" ] && ok "bad input passes (never fails closed)" || fail "bad input must pass (rc=$RC)"
unset LANES_PD_LOCK LANE_CLAIM_REPO; rm -rf "$SK"
grep -q 'skill-lane-guard.py' "$HOOKS/hooks.json" && grep -q '"matcher": "Skill"' "$HOOKS/hooks.json" \
  && ok "skill-lane-guard is registered on the Skill tool" || fail "hooks.json is missing skill-lane-guard on Skill"

echo
if [ "$FAILED" -eq 0 ]; then echo "hooks-test: all assertions passed"; else echo "hooks-test: FAILURES above"; fi
exit "$FAILED"
