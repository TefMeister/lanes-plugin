#!/usr/bin/env bash
# gu-fixture.sh - tools/gu.py (0.67.0): twins that match and differ, a watched tool with an un-noted release, one of
# our clones behind GitHub, lessons from KNOWN.md since the last run, and the weekly nudge. No network.
# Exit 0 = all passed.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TOOL="$HERE/../gu.py"
PY=""
for cand in python3 python py; do command -v "$cand" >/dev/null 2>&1 && "$cand" -c "" >/dev/null 2>&1 && { PY="$cand"; break; }; done
[ -n "$PY" ] || { echo "gu-fixture: no working Python"; exit 1; }
pass=0; fail=0
check() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; fi; }

T="$(mktemp -d)"
command -v cygpath >/dev/null 2>&1 && T="$(cygpath -m "$T")"   # Windows Python reads the paths in lanes.conf
trap 'rm -rf "$T"' EXIT
export LANES_STATE_DIR="$T/state" LANES_GU_NO_NET=1 LANES_CONFIG="$T/lanes.conf"

# twins: one pair the same (line endings aside), one pair with a changed file and a file only in the master
mkdir -p "$T/a1" "$T/b1" "$T/a2" "$T/b2"
printf 'x\n' > "$T/a1/f.py"; printf 'x\r\n' > "$T/b1/f.py"
printf 'old\n' > "$T/b2/g.py"; sleep 1; printf 'new\n' > "$T/a2/g.py"; printf 'n\n' > "$T/a2/extra.py"
# a watched tool: release v2 out, v1 noted
printf '{"someone/tool": {"tag_name": "v2", "name": "Faster", "published_at": "2026-10-10T00:00:00Z"}}' > "$T/rel.json"
# one of our clones, one commit behind GitHub
git init -q --bare -b main "$T/remote.git"
git clone -q "$T/remote.git" "$T/w" 2>/dev/null
(cd "$T/w" && echo a > a && git add a && git -c user.name=t -c user.email=t@t commit -q -m a && git push -q origin HEAD:main) >/dev/null 2>&1
git clone -q "$T/remote.git" "$T/ours" 2>/dev/null
(cd "$T/w" && echo b > b && git add b && git -c user.name=t -c user.email=t@t commit -q -m b && git push -q origin HEAD:main) >/dev/null 2>&1
git -C "$T/ours" fetch -q origin 2>/dev/null
# lessons: one old, one new tool idea
mkdir -p "$T/routes/game"
printf '# game\n\n## Tool ideas\n\n- 2026-10-01: old idea\n- 2026-10-12: hold a key for a set time\n' > "$T/routes/game/KNOWN.md"

cat > "$T/lanes.conf" <<EOF
twin = $T/a1 | $T/b1
twin = $T/a2 | $T/b2   # a note
watch = Some Tool | someone/tool
ours = $T/ours
routes = $T/routes
EOF

LANES_GU_TODAY=2026-10-05 "$PY" "$TOOL" done >/dev/null
"$PY" "$TOOL" seen "Some Tool" v1 >/dev/null
out="$(LANES_GU_FAKE_RELEASES="$T/rel.json" "$PY" "$TOOL" scan)"
js="$(LANES_GU_FAKE_RELEASES="$T/rel.json" "$PY" "$TOOL" scan --json)"
check "matching twins say so (line endings ignored)" 'printf "%s" "$out" | grep -q "a1: both copies match"'
check "differing twins: counts and which side changed last" 'printf "%s" "$out" | grep -q "a2: 1 differ, 1 only in the master, 0 only in the copy; changed last: the master copy"'
check "a watched tool's new release is shown with its title" 'printf "%s" "$out" | grep -q "Some Tool: v2 (2026-10-10) Faster - not noted yet, last noted v1"'
check "our clone one commit behind GitHub" 'printf "%s" "$out" | grep -q "ours: 1 new on GitHub"'
check "only lessons since the last run" 'printf "%s" "$out" | grep -q "hold a key" && ! printf "%s" "$out" | grep -q "old idea"'
check "json report parses" 'printf "%s" "$js" | "$PY" -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d[\"twins\"][1][\"newer\"]==\"a\" else 1)"'
"$PY" "$TOOL" seen "Some Tool" v2 >/dev/null
out="$(LANES_GU_FAKE_RELEASES="$T/rel.json" "$PY" "$TOOL" scan)"
check "once noted, the release is no longer new" 'printf "%s" "$out" | grep -q "Some Tool: v2, already noted"'

check "nudge: silent within the week" '[ -z "$(LANES_GU_TODAY=2026-10-11 "$PY" "$TOOL" nudge)" ]'
check "nudge: one line after a week" 'LANES_GU_TODAY=2026-10-12 "$PY" "$TOOL" nudge | grep -q "7 days ago"'
rm -f "$LANES_STATE_DIR/gu.json"
check "nudge: never run but set up = one line" '"$PY" "$TOOL" nudge | grep -q "never run"'
check "nudge: never run and nothing set up = silent" '[ -z "$(LANES_CONFIG="$T/none.conf" "$PY" "$TOOL" nudge)" ]'

echo "gu-fixture: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
