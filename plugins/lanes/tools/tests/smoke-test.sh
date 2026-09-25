#!/usr/bin/env bash
# Smoke test for the lanes tools. Builds a throwaway board and asserts the
# things that have actually broken before, rather than everything that could.
#
# Run it after touching gate-scan.sh or lane-claim.sh:
#   bash tools/tests/smoke-test.sh
#
# Exits non-zero on the first failure and says which assertion failed.

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TOOLS="$(cd "$HERE/.." && pwd)"
FIX="$HERE/fixture-board"
FAILED=0

PY=""
for cand in python3 python py; do
  command -v "$cand" >/dev/null 2>&1 || continue
  "$cand" -c "" >/dev/null 2>&1 || continue
  PY="$cand"; break
done
if [ -z "$PY" ]; then
  echo "smoke-test: no working python found; cannot build the fixture" >&2
  exit 2
fi

ok()   { printf '  ok    %s\n' "$1"; }
fail() { printf '  FAIL  %s\n' "$1"; FAILED=1; }

assert_contains() {
  case "$2" in
    *"$1"*) ok "$3" ;;
    *)      fail "$3 (expected to find: $1)" ;;
  esac
}
assert_not_contains() {
  case "$2" in
    *"$1"*) fail "$3 (did NOT expect: $1)" ;;
    *)      ok "$3" ;;
  esac
}

echo "building fixture..."
"$PY" "$HERE/make-fixture-board.py" "$FIX" >/dev/null || { echo "fixture build failed"; exit 2; }

echo "gate-scan --check"
out=$(bash "$TOOLS/gate-scan.sh" --check "$FIX" 2>&1)
assert_contains "clean" "$out" "a well-formed board reports clean"
assert_contains "LIVE NOW" "$out" "a live claim is reported"
assert_contains "demo-alpha" "$out" "the claim names the project holding it"
assert_not_contains "unbound variable" "$out" "no unset-variable errors"

echo "gate-scan board"
out=$(bash "$TOOLS/gate-scan.sh" "$FIX" 2>&1)
assert_contains "demo-beta" "$out" "an idle project is listed as idle"
assert_not_contains "unbound variable" "$out" "no unset-variable errors"

echo "gate-scan --next --tag FLAT"
out=$(bash "$TOOLS/gate-scan.sh" --next --tag FLAT "$FIX" 2>&1)
assert_not_contains "unbound variable" "$out" "no unset-variable errors"

echo "the claim filter refuses to run silently"
TMPDIR_COPY="$(mktemp -d)"
cp "$TOOLS/gate-scan.sh" "$TMPDIR_COPY/gate-scan.sh"
out=$(bash "$TMPDIR_COPY/gate-scan.sh" --brief "$FIX" 2>&1)
rc=$?
rm -rf "$TMPDIR_COPY"
assert_contains "lane-claim.sh is not beside this script" "$out" \
  "a stray copy refuses rather than reporting no claims"
[ "$rc" -ne 0 ] && ok "and it exits non-zero" || fail "a stray copy must exit non-zero"

echo "no board configured is a clear error, not a guess"
out=$(HOME="$FIX" LANES_CONFIG="$FIX/does-not-exist.conf" bash -c \
      'cd "$1" 2>/dev/null; cd ..; bash "$2" --brief' _ "$FIX" "$TOOLS/gate-scan.sh" 2>&1)
assert_contains "no board found" "$out" "an unconfigured board says so"

echo "the shipped template board passes its own checker"
# Shipping a template that the validator rejects would be the worst kind of
# broken: it fails for the one person who followed the instructions exactly.
TMPL_SRC="$(cd "$HERE/../../template-board" && pwd)"
TMPL="$(mktemp -d)/template-board"
mkdir -p "$TMPL" && cp -r "$TMPL_SRC/." "$TMPL/"
(
  cd "$TMPL" || exit 1
  git init -q -b main
  git config user.email "fixture@example.invalid"
  git config user.name "fixture"
  git add -A && git commit -q -m "template"
  git update-ref refs/remotes/origin/main HEAD
) >/dev/null 2>&1
out=$(bash "$TOOLS/gate-scan.sh" --check "$TMPL" 2>&1)
rc=$?
assert_contains "clean" "$out" "the template validates"
[ "$rc" -eq 0 ] && ok "and exits 0" || fail "the template must exit 0 (rc=$rc)"
out=$(bash "$TOOLS/gate-scan.sh" --brief "$TMPL" 2>&1)
assert_contains "PARALLEL DEVELOPMENT" "$out" "and renders as a board"

echo "every lane that hands over a next step names the model it needs"
# 0.5.0: the MODEL line is wording, not code, so the only thing a test can hold is that the
# wording is still there. Dropping it from one command file is exactly how it would rot.
for f in "$HERE/../../commands/lm.md" "$HERE/../../commands/pd.md" "$HERE/../../commands/gates.md"          "$HERE/../../skills/lanes/SKILL.md" "$HERE/../../docs/PROTOCOL.md"; do
  assert_contains "MODEL:" "$(cat "$f")" "$(basename "$f") carries the MODEL line"
done
rm -rf "$(dirname "$TMPL")"

echo "the front page check reports level, behind, and unconfigured"
# 0.6.0: the rule is "every session adds a line to the public page, whether or not
# anything advanced". A rule nobody can check is a wish, so the tool is what makes
# it checkable -- and these three states are the whole of its behaviour. The
# unconfigured case matters most: an estate with no public page is normal, and a
# check that nagged about it would be turned off, taking the other two with it.
FPTMP=$(mktemp -d)
mkdir -p "$FPTMP/board/status"
printf 'OPEN (2026-09-14):\n  [PD] something\n' > "$FPTMP/board/status/demo.md"

printf 'page last touched 2026-09-14\n' > "$FPTMP/level.md"
out=$(HOME="$FPTMP/home" LANES_CONFIG=/nonexistent LANES_BOARD="$FPTMP/board" LANES_FRONTPAGE="$FPTMP/level.md" \
      bash "$TOOLS/frontpage-scan.sh" 2>&1)
assert_contains "ok" "$out" "a level page reports ok"

printf 'page last touched 2026-08-01\n' > "$FPTMP/stale.md"
out=$(HOME="$FPTMP/home" LANES_CONFIG=/nonexistent LANES_BOARD="$FPTMP/board" LANES_FRONTPAGE="$FPTMP/stale.md" \
      bash "$TOOLS/frontpage-scan.sh" 2>&1)
assert_contains "BEHIND THE WORK" "$out" "a stale page is reported as behind"
assert_contains "2026-08-01" "$out" "and it names the date it is stuck on"

# HOME is isolated here, not just LANES_CONFIG. The tool legitimately falls back to
# ~/.claude/lanes.conf and ~/.config/lanes/lanes.conf, so pointing LANES_CONFIG at a
# dead path does NOT isolate it -- a developer who has configured a real front page
# would see this assertion fail for the right reason and the wrong cause. Caught by
# running the suite from the INSTALLED copy on a machine where the key was set; it had
# passed from the repo an hour earlier only because the key did not exist yet.
out=$(HOME="$FPTMP/home" LANES_CONFIG=/nonexistent LANES_BOARD="$FPTMP/board" LANES_FRONTPAGE="" \
      bash "$TOOLS/frontpage-scan.sh" 2>&1)
rc=$?
assert_contains "no front page configured" "$out" "an unconfigured page says so"
[ "$rc" -eq 0 ] && ok "and exits 0 rather than nagging" || fail "unconfigured must exit 0 (rc=$rc)"

# It must never edit the page - writing the line is the session's job, and an
# auto-generated entry is exactly the bland noise the rule exists to avoid.
before=$(cat "$FPTMP/stale.md")
HOME="$FPTMP/home" LANES_CONFIG=/nonexistent LANES_BOARD="$FPTMP/board" LANES_FRONTPAGE="$FPTMP/stale.md" \
  bash "$TOOLS/frontpage-scan.sh" >/dev/null 2>&1
[ "$(cat "$FPTMP/stale.md")" = "$before" ] && ok "and it never writes to the page" \
  || fail "frontpage-scan must be read-only"
rm -rf "$FPTMP"

echo "run-log --reader dates itself precisely, and never drifts from the truth"
# Fault 10: a hand-typed cutoff ("2026-09-10", a bare DATE) still counted two sessions
# from earlier that same day as reader runs, because the reader actually shipped at
# 15:35:09 that afternoon (commit f0c6a4e) - a whole day of granularity hid a 15-hour
# gap. Fixed by reading the exact commit TIMESTAMP that first added
# hooks/reader-guard.py, straight from this repo's own git history, falling back to
# tools/reader-since.txt only when there is no .git at all (an installed copy). This
# builds a throwaway board with one claim window either side of that exact moment and
# asserts the pre-shipping one is excluded - the precise failure fault 10 described.
RGTMP=$(mktemp -d)
(
  cd "$RGTMP" || exit 1
  git init -q -b main
  git config user.email "fixture@example.invalid"
  git config user.name "fixture"
  commit() { # date message
    echo x >> f.md; git add f.md
    GIT_AUTHOR_DATE="$1" GIT_COMMITTER_DATE="$1" git commit -q -m "$2"
  }
  # one full window BEFORE the reader shipped
  commit "2026-09-10T10:00:00+03:00" "claim: /lm live on demo-before (RIGFIX 10:00)"
  commit "2026-09-10T10:30:00+03:00" "claim: /lm released demo-before (RIGFIX 10:30)"
  # one full window well AFTER it shipped
  commit "2026-09-10T16:00:00+03:00" "claim: /lm live on demo-after (RIGFIX 16:00)"
  commit "2026-09-10T16:30:00+03:00" "claim: /lm released demo-after (RIGFIX 16:30)"
  git update-ref refs/remotes/origin/main HEAD
) >/dev/null 2>&1

# Whichever source the date came from, the WINDOWING must be right. Runs from a
# checkout and from an installed copy alike.
out=$(bash "$TOOLS/run-log.sh" --reader "$RGTMP" 2>&1)
assert_contains "reader shipped 2026-09-10T15:35:09" "$out" \
  "the cutoff is a full timestamp, not a bare date, and it names its source"
assert_contains "demo-after" "$out" "a claim window after the reader shipped is counted"
assert_not_contains "demo-before" "$out" \
  "a claim window from before the reader shipped that same day is excluded (the fault itself)"

# 2026-09-18: reader-since.txt is now the FIRST source and git the fallback, so these assertions
# were inverted with it. When the reader shipped is a historical fact; the file is the record of
# it. Asking git instead answers about THIS repo, and in a repo re-created from scratch every file
# looks added on day one - which would silently reset the reader count at exactly the moment
# someone is trying to prove the plugin is ready.
assert_contains "the recorded date the reader shipped" "$out" \
  "the cutoff comes from the recorded file, so re-creating the repo cannot reset the count"

# The file being authoritative makes the drift check the thing that keeps it honest, so it matters
# MORE than before, not less.
PLUGIN_ROOT="$(cd "$HERE/../.." && pwd)"
RG_ADDED=$(git -C "$PLUGIN_ROOT" log --diff-filter=A --format=%ad --date=iso-strict -- hooks/reader-guard.py 2>/dev/null | tail -1)
RSINCE_FILE="$(head -1 "$TOOLS/reader-since.txt" 2>/dev/null | tr -d '[:space:]')"
if [ -z "$RG_ADDED" ]; then
  ok "(no git history beside this copy - the drift check only runs from a checkout)"
elif [ "$RSINCE_FILE" = "$RG_ADDED" ]; then
  ok "tools/reader-since.txt matches git exactly (has not drifted)"
elif [ "$RG_ADDED" \> "$RSINCE_FILE" ]; then
  # git says the file was added LATER than the recorded date: this history does not go back that
  # far, so it is a re-created repo rather than a drifted file. Exactly the case the reorder is for.
  ok "git history starts after the recorded date - a re-created repo, and the recorded date rightly wins"
else
  fail "tools/reader-since.txt ($RSINCE_FILE) predates git history ($RG_ADDED) - one of them is wrong"
fi

echo "run-log --reader falls back cleanly with no git history at all (an installed copy)"
# Board still needs its own .git (that's a separate requirement, checked earlier in
# the script) - what must be ABSENT here is .git next to run-log.sh itself, which is
# what an install from the marketplace actually looks like. Always runs: an installed
# copy is exactly this shape, and it must not be allowed to skip itself.
NOGIT=$(mktemp -d)
cp -r "$TOOLS" "$NOGIT/tools"
out=$(bash "$NOGIT/tools/run-log.sh" --reader "$RGTMP" 2>&1)
assert_contains "the recorded date the reader shipped" "$out" \
  "with no .git beside the script, the shipped date file still answers, and says where the date came from"
assert_not_contains "cannot tell when the reader shipped" "$out" \
  "the fallback file means an installed copy is never left guessing"
assert_contains "demo-after" "$out" "and the fallback still counts the post-shipping window"
assert_not_contains "demo-before" "$out" "and still excludes the pre-shipping one"
rm -rf "$NOGIT" "$RGTMP"

echo "code-shape-scan flags big files, a Lua file near its locals limit, and loose numbers"
# 2026-09-17: a 6,758-line Lua script was sitting at exactly 200 top-level locals. These are the
# shapes the scan exists to catch, plus the two it must NOT report (generated and archived code).
CSTMP=$(mktemp -d)
(
  cd "$CSTMP" && git init -q . && mkdir -p src archive
  { for i in $(seq 1 1600); do echo "int f$i(void) { return 0; }"; done; } > src/big.c
  { for i in $(seq 1 170); do echo "local v$i = 0"; done; } > src/many_locals.lua
  { for i in $(seq 1 60); do echo "  move(x, 37.5, 900);"; done; } > src/loose.c
  { echo "/* GENERATED FILE - do not edit */"; for i in $(seq 1 1600); do echo "int g$i;"; done; } > src/gen.c
  { for i in $(seq 1 1600); do echo "int old$i;"; done; } > archive/old.c
  git add -A >/dev/null 2>&1
)
out=$("$PY" "$TOOLS/code-shape-scan.py" "$CSTMP" 2>&1)
assert_contains "OVER-HARD" "$out" "a 1,600-line hand-written file is over the hard line"
assert_contains "LUA-LOCALS" "$out" "a Lua file with 170 top-level locals is flagged"
assert_contains "LOOSE-NUMS" "$out" "inline numbers are flagged"
assert_not_contains "gen.c" "$out" "a file that says it is generated is skipped"
assert_not_contains "archive/old.c" "$out" "archived code is skipped"
rm -rf "$CSTMP"

echo "setup: the scan reports every catalog tool, and the first-run offer is made once per machine"
SUTMP=$(mktemp -d)
out=$(LANES_STATE_DIR="$SUTMP" "$PY" "$TOOLS/setup-scan.py" --json 2>&1)
assert_contains '"id": "blender-mcp"' "$out" "the scan covers Blender MCP"
assert_contains '"id": "ghidrust"' "$out" "the scan covers Ghidrust"
printf '%s' "$out" | "$PY" -c "import json,sys; d=json.load(sys.stdin); assert len(d['tools'])>=20" >/dev/null 2>&1   && ok "the scan's JSON parses and lists the whole catalog" || fail "setup-scan --json is not valid JSON with the full catalog"

# The Blender probe must be able to say NO. A check that can only answer yes would send setup
# straight past the two in-Blender clicks and report a link that is not there.
"$PY" - "$TOOLS/setup-scan.py" <<'PYEOF' >/dev/null 2>&1 && ok "the Blender link probe says no when nothing, or the wrong thing, is listening" || fail "blender_link_live() does not reject a dead or wrong port"
import importlib.util, socket, sys, threading
spec = importlib.util.spec_from_file_location("ss", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.BLENDER_PORT = 9
assert m.blender_link_live() is False, "claimed a live link with nothing listening"
srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1)
m.BLENDER_PORT = srv.getsockname()[1]
def junk():
    conn, _ = srv.accept(); conn.recv(1024); conn.sendall(b"not json"); conn.close()
threading.Thread(target=junk, daemon=True).start()
assert m.blender_link_live() is False, "claimed a live link from a server that is not Blender"
PYEOF
out=$(LANES_STATE_DIR="$SUTMP" bash "$HERE/../../hooks/setup-nudge" 2>&1)
assert_contains "FIRST RUN of the lanes plugin" "$out" "a machine with no setup state gets the offer"
LANES_STATE_DIR="$SUTMP" "$PY" "$TOOLS/setup-scan.py" --mark-done >/dev/null 2>&1
out=$(LANES_STATE_DIR="$SUTMP" bash "$HERE/../../hooks/setup-nudge" 2>&1)
[ -z "$out" ] && ok "once offered, the hook is silent" || fail "the setup offer repeats after --mark-done: $out"
out=$(LANES_SETUP_NUDGE=0 LANES_STATE_DIR="$(mktemp -d)" bash "$HERE/../../hooks/setup-nudge" 2>&1)
[ -z "$out" ] && ok "LANES_SETUP_NUDGE=0 silences it" || fail "LANES_SETUP_NUDGE=0 did not silence the offer"
while read -r url; do
  case "$url" in https://*) ;; *) fail "catalog link is not https: $url" ;; esac
done < <(grep -o 'https\?://[^ )|`]*' "$HERE/../../docs/TOOLS.md")
ok "every catalog link is https"
rm -rf "$SUTMP"


echo "scrub-scan: nothing shipped identifies a real person, and the check can say no"
# B2 used to be "grep the whole plugin folder", done by hand. Nobody did it for six weeks, and the
# first real audit found a captured hook payload carrying a username, a home path, a working
# directory, two session UUIDs and a slice of a personal settings.json. This is that bar, mechanised.
SCTMP=$(mktemp -d)
printf 'transcript: C:\\Users\\Alice\\.claude\\x.jsonl\n' > "$SCTMP/leaky.md"  # scrub-scan:allow (deliberate fixture)
printf 'write to real.person@gmail.com\n' >> "$SCTMP/leaky.md"  # scrub-scan:allow (deliberate fixture)
printf 'session 7c9e1f20-3a4b-4c5d-8e6f-0a1b2c3d4e5f\n' >> "$SCTMP/leaky.md"  # scrub-scan:allow (deliberate fixture)
printf 'captured on FAKEBOX-9911\n' >> "$SCTMP/leaky.md"  # scrub-scan:allow (deliberate fixture)
out=$("$PY" "$TOOLS/scrub-scan.py" --hostname FAKEBOX-9911 "$SCTMP" 2>&1); rc=$?  # scrub-scan:allow (deliberate fixture)
[ $rc -ne 0 ] && ok "a leaky folder is rejected (exit $rc)" || fail "scrub-scan passed a folder holding a username, an email, a session id and a hostname"
assert_contains "C:\\Users\\Alice" "$out" "it catches a home path naming a real account"  # scrub-scan:allow (deliberate fixture)
assert_contains "real.person@gmail.com" "$out" "it catches a real email address"  # scrub-scan:allow (deliberate fixture)
assert_contains "7c9e1f20" "$out" "it catches a session UUID"  # scrub-scan:allow (deliberate fixture)
assert_contains "FAKEBOX-9911" "$out" "it catches this machine's own hostname"  # scrub-scan:allow (deliberate fixture)

# ...and must not cry wolf over the placeholders that are supposed to be there.
printf 'path C:\\Users\\<user>\\thing, mail fixture@example.invalid\n' > "$SCTMP/clean.md"
printf 'uuid 11111111-1111-4111-8111-111111111111\n' >> "$SCTMP/clean.md"
rm -f "$SCTMP/leaky.md"
out=$("$PY" "$TOOLS/scrub-scan.py" --hostname FAKEBOX-9911 "$SCTMP" 2>&1); rc=$?  # scrub-scan:allow (deliberate fixture)
[ $rc -eq 0 ] && ok "placeholders and example addresses are not flagged" || fail "scrub-scan flagged its own placeholders: $out"

# An explicit allow marker excuses the NEXT line too, because Markdown has no inline comment.
printf 'scrub-scan:allow - deliberate, this is the contact address\n' > "$SCTMP/allowed.md"
printf 'mail **someone@realdomain.com**\n' >> "$SCTMP/allowed.md"
out=$("$PY" "$TOOLS/scrub-scan.py" --hostname FAKEBOX-9911 "$SCTMP" 2>&1); rc=$?  # scrub-scan:allow (deliberate fixture)
[ $rc -eq 0 ] && ok "an allow marker excuses the line under it" || fail "the allow marker did not cover the following line: $out"
assert_contains "allow marker" "$out" "and every allowed line is REPORTED, so the list cannot grow quietly"


# Private names: a nickname, another machine. These have no SHAPE to detect - they are ordinary
# words - so each machine's owner may list them in a PRIVATE file (~/.claude/lanes/never-publish.txt),
# never inside the plugin (0.22.0: a shipped list published the very words it listed).
# The fixture words below are invented; they belong to nobody.
DECL=$(mktemp -d); NAMES="$DECL/never-publish.txt"
printf '# private list
Zorvanna
QUILLBOX-77
' > "$NAMES"
mkdir -p "$DECL/tree"
printf 'the layout was a Zorvanna decision, made on QUILLBOX-77
' > "$DECL/tree/doc.md"
out=$("$PY" "$TOOLS/scrub-scan.py" --hostname NOTTHISBOX --names "$NAMES" "$DECL/tree" 2>&1); rc=$?
[ $rc -ne 0 ] && ok "a privately listed name is caught even though it has no detectable shape" || fail "scrub-scan passed a file holding a privately listed name and machine"
assert_contains "private never-publish list" "$out" "and it says WHY - the word is on this machine's private list"

# ...and a longer word that merely CONTAINS a listed one is left alone (whole words only).
printf 'install with /plugin marketplace add ZorvannaWorks/some-plugin
' > "$DECL/tree/doc.md"
out=$("$PY" "$TOOLS/scrub-scan.py" --hostname NOTTHISBOX --names "$NAMES" "$DECL/tree" 2>&1); rc=$?
[ $rc -eq 0 ] && ok "an account name that merely begins with a listed word is NOT flagged" || fail "scrub-scan flagged a longer word containing a listed one: $out"

# The plugin must never ship such a list again.
[ ! -e "$TOOLS/scrub-names.txt" ] && ok "no word list ships inside the plugin" || fail "tools/scrub-names.txt is back - a shipped never-publish list publishes its own words"
rm -rf "$DECL"

# The naming rule: every session is told to call the person "User" unless they chose a name.
NR=$(mktemp -d)
out=$(LANES_CONFIG="$NR/lanes.conf" "$PY" "$TOOLS/display-name.py"); [ "$out" = "User" ] && ok "with nothing set, the person is User" || fail "display-name default was '$out', not User"
LANES_CONFIG="$NR/lanes.conf" "$PY" "$TOOLS/display-name.py" set "Sam K" >/dev/null
out=$(LANES_CONFIG="$NR/lanes.conf" "$PY" "$TOOLS/display-name.py"); [ "$out" = "Sam K" ] && ok "a chosen display name is saved and read back" || fail "display-name set/get gave '$out'"
LANES_CONFIG="$NR/lanes.conf" "$PY" "$TOOLS/display-name.py" set 'a$b' >/dev/null 2>&1 && fail "display-name accepted a name with a \$ in it" || ok "a display name with odd characters is refused, not mangled"
out=$(LANES_CONFIG="$NR/lanes.conf" CLAUDE_PLUGIN_ROOT="$HERE/../.." bash "$HERE/../../hooks/name-rule")
assert_contains "NAMING RULE" "$out" "the session-start hook emits the naming rule"
assert_contains "Sam K" "$out" "and fills in the chosen name"
LANES_CONFIG="$NR/lanes.conf" "$PY" "$TOOLS/display-name.py" clear >/dev/null
out=$(LANES_CONFIG="$NR/lanes.conf" CLAUDE_PLUGIN_ROOT="$HERE/../.." bash "$HERE/../../hooks/name-rule")
assert_contains '\"User\"' "$out" "and after clearing it, the person is User again"
grep -q '"name-rule"\|name-rule' "$HERE/../../hooks/hooks.json" && ok "the naming hook is registered for session start" || fail "hooks.json does not run name-rule"
rm -rf "$NR"

# The shipped plugin itself must be clean. This is the assertion that matters.
out=$("$PY" "$TOOLS/scrub-scan.py" "$HERE/../.." 2>&1); rc=$?
[ $rc -eq 0 ] && ok "the shipped plugin folder carries no personal identifiers" || fail "scrub-scan found personal data in the plugin that would be published: $out"
rm -rf "$SCTMP"

echo "update check: a newer published version is announced once, with what changed, and never installs anything"
UPTMP=$(mktemp -d)
(
  set -e
  cd "$UPTMP"
  git init -q --bare remote.git
  git clone -q remote.git work 2>/dev/null
  cd work
  mkdir -p plugins/lanes/.claude-plugin
  echo '{"name":"lanes","version":"9.9.0"}' > plugins/lanes/.claude-plugin/plugin.json
  printf '%s
' '# Changes' '' '- **9.9.0** (2099-01-01): the newest thing.' '- **9.8.0** (2099-01-01): an older thing.' '- **0.0.1** (2000-01-01): ancient.' > plugins/lanes/CHANGELOG.md
  git add -A && git -c user.name=t -c user.email=t@t commit -q -m "lanes 9.9.0: test" && git push -q origin HEAD:main 2>/dev/null
  git -C "$UPTMP/remote.git" symbolic-ref HEAD refs/heads/main
  cd .. && git clone -q remote.git market 2>/dev/null
  mkdir -p installed/.claude-plugin && echo '{"version":"9.7.0"}' > installed/.claude-plugin/plugin.json
) >/dev/null 2>&1
UPENV=(LANES_STATE_DIR="$UPTMP/state" LANES_PLUGIN_ROOT="$UPTMP/installed" LANES_UPDATE_MARKETPLACE=demo-market LANES_UPDATE_MARKETPLACE_DIR="$UPTMP/market")
out=$(env "${UPENV[@]}" "$PY" "$TOOLS/update-check.py" 2>&1)
assert_contains "A NEW VERSION of the lanes plugin is available: 9.9.0 (this machine has 9.7.0)" "$out" "a newer version is announced"
assert_contains "the newest thing" "$out" "it says what changed"
assert_contains "an older thing" "$out" "including every version the machine missed"
assert_not_contains "ancient" "$out" "but not versions it already has"
assert_contains "claude plugin update lanes@demo-market" "$out" "it names the exact update command"
assert_contains "ASK whether you may update" "$out" "and asks before updating"
assert_contains "New plugin update available! Would you like to install it now?" "$out" "and asks it in the fixed words"
env "${UPENV[@]}" "$PY" "$TOOLS/update-check.py" --dismiss >/dev/null 2>&1
out=$(env "${UPENV[@]}" "$PY" "$TOOLS/update-check.py" 2>&1)
[ -z "$out" ] && ok "after 'not now' it stays quiet about that version" || fail "the update offer repeated after --dismiss: $out"
echo '{"version":"9.9.0"}' > "$UPTMP/installed/.claude-plugin/plugin.json"
out=$(env "${UPENV[@]}" "$PY" "$TOOLS/update-check.py" --force 2>&1)
[ -z "$out" ] && ok "an up-to-date machine hears nothing" || fail "an up-to-date machine was told to update: $out"
out=$(LANES_STATE_DIR="$UPTMP/s3" LANES_PLUGIN_ROOT="$UPTMP/installed" LANES_UPDATE_MARKETPLACE_DIR="$UPTMP/nope" "$PY" "$TOOLS/update-check.py" 2>&1); rc=$?
[ -z "$out" ] && [ $rc -eq 0 ] && ok "no clone / offline: silent, exit 0" || fail "update-check is not silent when it cannot reach the marketplace: $out"

# --- the two ways this check has answered "you are up to date" while being wrong (2026-09-18) ---
# Both were found by running /lanes:update for real: it reported success twice and installed
# nothing. Each failure is invisible, so each gets a test.

# 1. A marketplace registered as a local DIRECTORY installs from that clone's WORKING TREE, while
#    this script reads origin/main. Push a release from a different clone of the same repo and the
#    two disagree: the check promises a new version the installer then refuses to find.
(
  set -e
  cd "$UPTMP/work"
  echo '{"name":"lanes","version":"9.9.1"}' > plugins/lanes/.claude-plugin/plugin.json
  printf '%s\n' '# Changes' '' '- **9.9.1** (2099-01-01): pushed from somewhere else.' '- **9.9.0** (2099-01-01): the newest thing.' > plugins/lanes/CHANGELOG.md
  git add -A && git -c user.name=t -c user.email=t@t commit -q -m "lanes 9.9.1" && git push -q origin HEAD:main
  git -C "$UPTMP/market" fetch -q origin
) >/dev/null 2>&1
echo '{"version":"9.9.0"}' > "$UPTMP/installed/.claude-plugin/plugin.json"
out=$(env "${UPENV[@]}" LANES_UPDATE_MARKETPLACE_SOURCE=directory LANES_STATE_DIR="$UPTMP/s4" \
      "$PY" "$TOOLS/update-check.py" --json --force 2>&1)
assert_contains '"marketplace_behind": 1' "$out" "a stale local-directory marketplace is noticed, not ignored"
assert_contains 'pull --ff-only' "$out" "and pulling it is the FIRST update command, so the install is not a no-op"
first_cmd=$(printf '%s' "$out" | "$PY" -c "import json,sys; print(json.load(sys.stdin)['update_commands'][0])")
case "$first_cmd" in
  git\ -C*) ok "the pull really is first, before either claude command" ;;
  *) fail "the update commands start with '$first_cmd', so the stale tree is installed again" ;;
esac

# A marketplace fetched from GitHub has no such gap, and must not be given a pointless pull.
out=$(env "${UPENV[@]}" LANES_UPDATE_MARKETPLACE_SOURCE=github LANES_STATE_DIR="$UPTMP/s5" \
      "$PY" "$TOOLS/update-check.py" --json --force 2>&1)
assert_not_contains 'pull --ff-only' "$out" "a github marketplace is not told to pull a clone it does not own"

# 2. PLUGIN_ROOT defaults to wherever this file lives, so running the copy inside a REPO CLONE
#    reported the REPO's version as installed and found no marketplace at all - a confident
#    "up to date" about a machine it had never looked at. in_cache() is the discriminator.
out=$("$PY" - "$TOOLS/update-check.py" <<'PYEOF'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("uc", sys.argv[1])
uc = importlib.util.module_from_spec(spec); spec.loader.exec_module(uc)
cases = [
    ("/home/x/.claude/plugins/cache/some-market/lanes/1.2.3", True),
    ("C:\\Users\\x\\.claude\\plugins\\cache\\some-market\\lanes\\1.2.3", True),
    ("/repos/claude-plugins/plugins/lanes", False),
    ("/tmp/lanes", False),
]
bad = [(p, want) for p, want in cases if uc.in_cache(p) != want]
print("BAD" if bad else "GOOD", bad)
PYEOF
)
assert_contains "GOOD" "$out" "an installed copy and a repo checkout are told apart"

rm -rf "$UPTMP"

echo "root-sync: every lane's clone root ends up holding every repo, and nothing existing is touched"
RSTMP="$(mktemp -d)"
(
  cd "$RSTMP" || exit 1
  for n in alpha beta gamma; do
    git init -q --bare "remote-$n.git"
    git clone -q "remote-$n.git" "seed-$n" 2>/dev/null
    (cd "seed-$n" && echo "$n" > f && git add f && git -c user.name=t -c user.email=t@t commit -q -m init && git push -q origin HEAD 2>/dev/null)
  done
  mkdir clones clones-pd clones-gr
  git clone -q remote-alpha.git clones/alpha 2>/dev/null
  git clone -q remote-beta.git clones/beta 2>/dev/null
  git clone -q remote-alpha.git clones-pd/alpha 2>/dev/null
  git clone -q remote-gamma.git clones-gr/gamma 2>/dev/null
  echo "uncommitted" > clones-pd/alpha/local-work.txt
  mkdir clones/no-remote && git -C clones/no-remote init -q
) >/dev/null 2>&1
RSENV=(LANES_CONFIG=/nonexistent LANES_ROOT="$RSTMP/clones")
out=$(env "${RSENV[@]}" bash "$TOOLS/root-sync.sh" --check 2>&1); rc=$?
[ $rc -eq 1 ] && ok "--check exits 1 when a root is missing repos" || fail "--check exit was $rc: $out"
assert_contains "MISSING  $RSTMP/clones-pd/beta" "$out" "a repo only the live root has is missing from a lane root"
assert_contains "MISSING  $RSTMP/clones/gamma" "$out" "a repo only a lane root has is missing from the live root too"
[ -e "$RSTMP/clones-gr/beta" ] && fail "--check copied something" || ok "--check changes nothing"
out=$(env "${RSENV[@]}" bash "$TOOLS/root-sync.sh" --fix 2>&1); rc=$?
assert_contains "ADDED    $RSTMP/clones-gr/alpha" "$out" "--fix copies the missing repos in"
assert_contains "SKIPPED  $RSTMP/clones-pd/no-remote" "$out" "a repo with no remote is reported, not spread"
u=$(git -C "$RSTMP/clones-pd/beta" remote get-url origin 2>/dev/null)
case "$u" in *remote-beta.git) ok "a copied repo points at the real remote, not the local copy" ;; *) fail "copied origin is '$u'" ;; esac
[ -f "$RSTMP/clones-pd/alpha/local-work.txt" ] && ok "an existing clone's uncommitted work is untouched" || fail "root-sync touched an existing clone"
rm -rf "$RSTMP/clones/no-remote"
out=$(env "${RSENV[@]}" bash "$TOOLS/root-sync.sh" --check 2>&1); rc=$?
[ $rc -eq 0 ] && ok "after --fix, --check is clean" || fail "still missing after --fix: $out"
assert_contains "all 3 clone roots hold all 3 repos" "$out" "and says so in plain words"
rm -rf "$RSTMP"

echo "the newest CHANGELOG line matches plugin.json (every version bump must say what changed)"
cl=$(grep -m1 -o '^- \*\*[0-9][0-9.]*\*\*' "$HERE/../../CHANGELOG.md" | tr -d '*' | sed 's/^- //')
pv=$("$PY" -c "import json,sys; print(json.load(open(sys.argv[1]))['version'])" "$HERE/../../.claude-plugin/plugin.json")
[ "$cl" = "$pv" ] && ok "CHANGELOG.md starts with $pv" || fail "CHANGELOG.md's newest line is '$cl' but plugin.json says $pv"

echo "the marketplace listing matches plugin.json (this is the version the installer actually reads)"
MKT="$HERE/../../../../.claude-plugin/marketplace.json"
if [ -f "$MKT" ]; then
  mkv=$("$PY" -c "
import json,sys
d=json.load(open(sys.argv[1],encoding='utf-8'))
print(next(p['version'] for p in d['plugins'] if p['name']=='lanes'))
" "$MKT" 2>&1)
  [ "$mkv" = "$pv" ] && ok "marketplace.json offers $pv" || fail "marketplace.json offers '$mkv' but plugin.json is $pv - 'claude plugin update' reads the MARKETPLACE, so every release after '$mkv' is invisible to it"
else
  printf '  skip  %s
' "no marketplace.json here (an installed copy does not carry it)"
fi


echo "the repo front page names this version (it is what a visitor reads first)"
RROOT="$HERE/../../../../README.md"
if [ -f "$RROOT" ]; then
  # The lanes row of the Plugins table, e.g. "| [`lanes`](plugins/lanes/) | ... | `0.12.1` - ... |"
  rmv=$(grep -m1 '\[`lanes`\](plugins/lanes/)' "$RROOT" | grep -o '`[0-9][0-9.]*`' | tr -d '`')
  if [ -z "$rmv" ]; then
    fail "the root README has no version in its lanes row - it went stale silently once already"
  else
    # Found 2026-09-18: it said 0.10.1 while the plugin was 0.12.1, four releases behind, and
    # nothing checked it. Same shape as fault 11, on the page a stranger reads before anything else.
    [ "$rmv" = "$pv" ] && ok "the root README says $pv" || fail "the root README says '$rmv' but plugin.json is $pv - the first page anyone reads is advertising a version that does not exist"
  fi
else
  printf '  skip  %s\n' "no root README here (an installed copy does not carry it)"
fi

echo "the front page lists every command (it is where a visitor learns what each one does)"
# Until 0.24.0 the banner carried the command list and this check read it. The banner is now plain
# artwork, so the list lives on the front page and is checked there instead.
if [ -f "$RROOT" ]; then
  missing=""
  for c in "$HERE"/../../commands/*.md; do
    n=$(basename "$c" .md)
    grep -q "\`/$n\`" "$RROOT" || missing="$missing /$n"
  done
  [ -z "$missing" ] && ok "every command is on the front page" || fail "the front page does not list:$missing"
else
  printf '  skip  %s
' "no root README here (an installed copy does not carry it)"
fi

echo "proxy-gen self-test (an export called before DllMain must not crash the app)"
out=$(bash "$TOOLS/proxy-gen/test/run_tests.sh" 2>&1); rc=$?
case $rc in
  0)  assert_contains "ALL TESTS PASSED" "$out" "generated proxies forward every argument, and survive an early call" ;;
  77) printf '  skip  %s
' "$(printf '%s' "$out" | tail -1)" ;;
  *)  fail "proxy-gen self-test failed (exit $rc): $(printf '%s' "$out" | grep -E 'FAIL' | head -3)" ;;
esac

echo "owed.sh - work queued for ONE named machine (0.14.0)"
OWEDBOARD=$(mktemp -d); mkdir -p "$OWEDBOARD/status"; (cd "$OWEDBOARD" && git init -q . 2>/dev/null)
run_owed() { LANES_BOARD="$OWEDBOARD" LANES_CONFIG=/nonexistent GATE_ROLE="$1" bash "$TOOLS/owed.sh" "${@:2}" 2>&1; }

out=$(run_owed DEV check)
[ -z "$out" ] && ok "silent when this machine owes nothing (it is a session-start hook)" \
              || fail "check printed something with an empty queue: $out"

printf 'Why here: the hardware is here\nDone when: it prints PASS\n' | run_owed DEV add HOME "install the thing" >/dev/null
out=$(run_owed HOME check)
assert_contains "install the thing" "$out" "the addressed machine is told"
assert_contains "the hardware is here" "$out" "and told why it has to be that machine"
out=$(run_owed DEV check)
[ -z "$out" ] && ok "the OTHER machine is not nagged by it - the whole point" \
              || fail "an item for HOME showed up on DEV: $out"

# Addressing yourself is the commonest way this turns back into a to-do list nobody owns.
out=$(run_owed HOME add HOME "should be refused"); rc=$?
if [ "$rc" -ne 0 ]; then
  assert_contains "THIS machine" "$out" "refuses to raise an item for the machine you are sitting at"
else
  fail "add let a machine address itself (exit $rc)"
fi

# Fault shape from PROTOCOL 2: a glob deletes an item raised seconds ago and never committed.
out=$(run_owed HOME done "2026-*.md"); rc=$?
if [ "$rc" -ne 0 ]; then
  assert_contains "not a pattern" "$out" "done refuses a pattern, and says so"
else
  fail "done accepted a glob - that can delete an unread item"
fi

name=$(ls "$OWEDBOARD/owed/HOME" | head -1)
run_owed HOME done "$name" >/dev/null
out=$(run_owed HOME check)
[ -z "$out" ] && ok "clearing it makes it stop - a reminder that cannot be cleared is a note" \
              || fail "item survived done: $out"
rm -rf "$OWEDBOARD"

# WHICH BOARD does it write to? (2026-09-18) Every assertion above pins $LANES_BOARD, so none of
# them ever exercised the resolution order -- which is exactly why this shipped broken. The config
# was read BEFORE the tool looked at where it was running, so on a one-clone-per-lane machine every
# lane's copy wrote into whichever clone lanes.conf named. A /pd session raised a reminder and the
# file landed in the live modding session's working tree. A tool that WRITES must default to the
# clone it belongs to.
#
# Two clones, and a config deliberately naming the WRONG one, exactly like the real failure.
OWED_MINE=$(mktemp -d); mkdir -p "$OWED_MINE/tools" "$OWED_MINE/status"; (cd "$OWED_MINE" && git init -q . 2>/dev/null)
OWED_OTHER=$(mktemp -d); mkdir -p "$OWED_OTHER/status"; (cd "$OWED_OTHER" && git init -q . 2>/dev/null)
OWED_CONF=$(mktemp); printf 'board = %s\nrole  = DEV\n' "$OWED_OTHER" > "$OWED_CONF"
cp "$TOOLS/owed.sh" "$OWED_MINE/tools/owed.sh"

# Paths come back Git-Bash style ("/d/x") from a Windows-style argument ("D:/x"); same path.
owed_norm() { printf '%s' "$1" | sed -E 's#^([A-Za-z]):#/\L\1#' | sed 's#/*$##'; }
owed_same() { [ "$(owed_norm "$1")" = "$(owed_norm "$2")" ]; }

# 1. THE BUG: the clone's own copy, run from that clone, must ignore the config.
printf 'Why here: it is here\nDone when: it is done\n' |
  ( cd "$OWED_MINE" && LANES_CONFIG="$OWED_CONF" GATE_ROLE=DEV bash tools/owed.sh add HOME "board resolution" ) >/dev/null 2>&1
if [ -n "$(ls -A "$OWED_MINE/owed/HOME" 2>/dev/null)" ] && [ -z "$(ls -A "$OWED_OTHER/owed" 2>/dev/null)" ]; then
  ok "writes into the clone it belongs to, NOT the one the config names"
else
  fail "owed.sh wrote to the config's board instead of its own clone - the 2026-09-18 fault is back"
fi

# 2. The SessionStart hook's path: an installed copy, outside any clone, run from a non-board
#    directory, must still fall back to the config -- or session start silently stops working.
OWED_ELSEWHERE=$(mktemp -d); mkdir -p "$OWED_ELSEWHERE/tools"; cp "$TOOLS/owed.sh" "$OWED_ELSEWHERE/tools/owed.sh"
OWED_NEUTRAL=$(mktemp -d)
got=$( cd "$OWED_NEUTRAL" && LANES_CONFIG="$OWED_CONF" GATE_ROLE=DEV bash -c '
  eval "$(sed -n "/^is_board()/,/^}$/p" "$1")"
  eval "$(sed -n "/^find_board()/,/^}$/p" "$1")"
  BASH_SOURCE=("$1"); find_board' _ "$OWED_ELSEWHERE/tools/owed.sh" )
if owed_same "$got" "$OWED_OTHER"; then
  ok "an installed copy outside any clone still uses the config, so the hook keeps working"
else
  fail "the config fallback broke; the SessionStart hook would go silent (got '$got')"
fi

# 3. An explicit override still beats everything.
got=$( cd "$OWED_MINE" && LANES_BOARD="$OWED_OTHER" LANES_CONFIG="$OWED_CONF" bash -c '
  eval "$(sed -n "/^is_board()/,/^}$/p" "$1")"
  eval "$(sed -n "/^find_board()/,/^}$/p" "$1")"
  BASH_SOURCE=("$1"); find_board' _ "$OWED_MINE/tools/owed.sh" )
owed_same "$got" "$OWED_OTHER" && ok "\$LANES_BOARD still overrides everything" \
                               || fail "LANES_BOARD no longer wins (got '$got')"

rm -rf "$OWED_MINE" "$OWED_OTHER" "$OWED_ELSEWHERE" "$OWED_NEUTRAL"; rm -f "$OWED_CONF"

echo "machine names - never the computer's real name (0.24.0)"
if out=$(bash "$HERE/machine-label-fixture.sh" 2>&1); then
  ok "$(printf '%s\n' "$out" | tail -n 1)"
else
  printf '%s\n' "$out" | grep FAIL
  fail "machine-label-fixture.sh failed"
fi

echo "ideas.py - the ideas inbox (0.23.0)"
if out=$(bash "$HERE/ideas-fixture.sh" 2>&1); then
  ok "$(printf '%s\n' "$out" | tail -n 1)"
else
  printf '%s\n' "$out" | grep FAIL
  fail "ideas-fixture.sh failed"
fi

echo
if [ "$FAILED" -eq 0 ]; then
  echo "smoke-test: all assertions passed"
else
  echo "smoke-test: FAILURES above"
fi
exit "$FAILED"
