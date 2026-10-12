#!/usr/bin/env bash
# uninstall-fixture.sh - tools/uninstall.py (0.61.0) on a scratch "PC": the plan lists what is there, `do` takes
# away exactly Lanes' own pieces, puts the settings aside rather than deleting them, keeps them with
# --keep-settings, and never touches a repo or note sitting next to them. No other tool and no `claude` command is
# run (LANES_UNINSTALL_DRY_TOOLS=1). Exit 0 = all passed.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TOOL="$HERE/../uninstall.py"
PY=""
for cand in python3 python py; do command -v "$cand" >/dev/null 2>&1 && "$cand" -c "" >/dev/null 2>&1 && { PY="$cand"; break; }; done
[ -n "$PY" ] || { echo "uninstall-fixture: no working Python"; exit 1; }
pass=0; fail=0
check() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; fi; }

T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
make_pc() {
  rm -rf "$T/pc"; mkdir -p "$T/pc/.claude/lanes" "$T/pc/.claude/lanes-inspector" "$T/pc/work/repo/.git"
  echo '{"applied": false}' > "$T/pc/.claude/lanes/theme-state.json"
  echo '{"choices": {"uv": "installed-by-claude", "7zip": "user"}}' > "$T/pc/.claude/lanes/setup-state.json"
  printf 'display_name = Someone  # a note\nmachine_name = PC1\n' > "$T/pc/.claude/lanes.conf"
  echo log > "$T/pc/.claude/lanes-reader-refusals.log"
  echo "my notes" > "$T/pc/work/repo/notes.md"
}
export LANES_STATE_DIR="$T/pc/.claude/lanes" LANES_CONFIG="$T/pc/.claude/lanes.conf"
export LANES_INSPECTOR_HOME="$T/pc/.claude/lanes-inspector" LANES_UNINSTALL_DRY_TOOLS=1

make_pc
out="$("$PY" "$TOOL" plan)"
check "plan lists the state folder as present" 'printf "%s" "$out" | grep -q "yes  Lanes. own state folder"'
check "plan lists the settings file" 'printf "%s" "$out" | grep -q "yes  the settings file"'
check "plan names the tool setup installed" 'printf "%s" "$out" | grep -q "installed for you: uv"'
check "plan does not list a tool the person installed" '! printf "%s" "$out" | grep -q "7zip"'
check "plan changed nothing" '[ -d "$LANES_STATE_DIR" ] && [ -f "$LANES_CONFIG" ]'

out="$("$PY" "$TOOL" do)"; rc=$?
check "do exits 0" '[ "$rc" -eq 0 ]'
check "state folder gone" '[ ! -d "$LANES_STATE_DIR" ]'
check "reader log gone" '[ ! -f "$T/pc/.claude/lanes-reader-refusals.log" ]'
check "default Inspector folder gone" '[ ! -d "$LANES_INSPECTOR_HOME" ]'
check "settings not read any more" '[ ! -f "$LANES_CONFIG" ]'
check "settings put aside, not deleted" 'ls "$T/pc/.claude/" | grep -q "^lanes.conf.uninstalled-"'
check "the plugin removal is the last step" 'printf "%s" "$out" | grep -q "claude plugin uninstall lanes@lanes-plugin"'
check "the person's own notes untouched" '[ "$(cat "$T/pc/work/repo/notes.md")" = "my notes" ]'

make_pc
"$PY" "$TOOL" do --keep-settings --keep-plugin >/dev/null
check "--keep-settings keeps lanes.conf" '[ -f "$LANES_CONFIG" ]'
check "--keep-plugin does not remove the plugin" '! "$PY" "$TOOL" do --keep-settings --keep-plugin | grep -q "claude plugin uninstall"'

echo "uninstall-fixture: $pass checks, $fail failed"
[ "$fail" -eq 0 ]
