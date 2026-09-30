#!/usr/bin/env bash
# inspector-fixture.sh - asserts the Inspector keeps its promises: it raises new mess and only new
# mess, it holds a commit until every finding has a verdict, it never edits code, and it fails OPEN
# on anything it cannot work out. Builds throwaway repos in a temp folder; never reads the real
# lanes.conf (LANES_CONFIG) or the real copy-paste cache (LANES_INSPECTOR_CACHE).
#   bash tools/tests/inspector-fixture.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PLUGIN="$(cd "$HERE/../.." && pwd)"
HOOK="$PLUGIN/hooks/inspector-hook.py"
TOOL="$PLUGIN/tools/inspector.py"
PY=""
for cand in python3 python py; do
  command -v "$cand" >/dev/null 2>&1 || continue
  "$cand" -c "" >/dev/null 2>&1 || continue
  PY="$cand"; break
done
[ -n "$PY" ] || { echo "inspector-fixture: no working python"; exit 2; }

T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
FAILED=0; N=0
ok()   { N=$((N+1)); printf '  ok    %s\n' "$1"; }
fail() { N=$((N+1)); FAILED=$((FAILED+1)); printf '  FAIL  %s\n' "$1"; }

# Most checks below are for `each` mode (ask after every edit); the `end` mode has its own section.
# The Inspector is optional: it does nothing until `inspector = on`, so every config here switches it on
# (unless the argument itself sets `inspector = ...`).
setconf() {
  { case "${1:-}" in "inspector = "*) ;; *) echo "inspector = on" ;; esac
    echo "inspector_mode = ${MODE:-each}"; [ $# -gt 0 ] && echo "$1"; } > "$LANES_CONFIG"
}
export LANES_CONFIG="$T/lanes.conf"; setconf
export LANES_INSPECTOR_CACHE="$T/cache"
# Paths handed to Python must be native on Windows; git bash gives /c/... otherwise.
native() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi; }

G="$T/root/game"; O="$T/root/othergame"
mkdir -p "$G/dev-archive/src" "$O/src"
for r in "$G" "$O"; do
  git -C "$r" init -q; git -C "$r" config user.email t@t; git -C "$r" config user.name t
  git -C "$r" config core.autocrlf false
done
GN="$(native "$G")"; SRC="$G/dev-archive/src/mod.cpp"; SRCN="$(native "$SRC")"
RECD="$G/dev-archive/inspector"
# All the notes in one file to grep (a pipe into grep -q breaks under pipefail).
recf() { cat "$RECD"/*.md > "$T/rec.txt" 2>/dev/null; printf '%s' "$T/rec.txt"; }

cat > "$SRC" <<'EOF'
static const float kScale = 1.5f;
int old_mess(int x) { return x * 37; }
// int a = old_mess(1);
// int b = old_mess(2);
// if (a > b) { a = b; }
// for (int i = 0; i < a; ++i) { b += i; }
// b = old_mess(b);
// return b;
EOF
# A helper the other game already has, to be copied in later.
cat > "$O/src/helper.cpp" <<'EOF'
float blend_towards(float current, float target, float rate) {
    float delta = target - current;
    if (delta > rate) delta = rate;
    if (delta < -rate) delta = -rate;
    float next_value = current + delta;
    if (next_value > target && delta > 0) next_value = target;
    if (next_value < target && delta < 0) next_value = target;
    float clamped_value = next_value;
    float result_value = clamped_value;
    float returned_value = result_value;
    return returned_value;
}
EOF
git -C "$G" add -A; git -C "$G" commit -qm init
git -C "$O" add -A; git -C "$O" commit -qm init

post() { printf '{"hook_event_name":"PostToolUse","tool_name":"Edit","tool_input":{"file_path":"%s"}}' "$1" \
         | "$PY" "$HOOK" 2>&1; }
commit_hook() { OUT=$(printf '{"hook_event_name":"PreToolUse","tool_name":"%s","cwd":"%s","tool_input":{"command":"%s"}}' \
                "$1" "$2" "$3" | "$PY" "$HOOK" 2>&1); RC=$?; }
verdict() { "$PY" - "$RECD" "$1" "$2" <<'EOF'
import sys, re, os
folder, fid, text = sys.argv[1:]
for name in os.listdir(folder):
    path = os.path.join(folder, name)
    if not name.endswith(".md"):
        continue
    s = open(path, encoding="utf-8").read()
    if "### %s " % fid not in s:
        continue
    s = re.sub(r"(### %s .*?- \*\*Verdict:\*\*) [^\n]*" % re.escape(fid), lambda m: m.group(1) + " " + text, s, flags=re.S)
    open(path, "w", encoding="utf-8", newline="\n").write(s)
EOF
}

echo "raising new mess, and only new mess"
cat >> "$SRC" <<'EOF'
void tick() {
    if (GetAsyncKeyState(VK_F10)) { apply(2.75f); }
}
EOF
BEFORE=$(cat "$SRC")
out=$(post "$SRCN")
case "$out" in *'"additionalContext"'*INSPECTOR*F-KEY*) ok "an F-key hotkey in new code is raised to the session" ;;
                *) fail "the edit hook did not raise the F-key ($out)" ;; esac
case "$out" in *LOOSE-NUMS*) ok "a new bare number is raised" ;; *) fail "the new bare number was not raised" ;; esac
[ -f "$RECD/this-session.md" ] && ok "findings are written to dev-archive/inspector/this-session.md" || fail "no notes folder in dev-archive/"
[ "$(cat "$SRC")" = "$BEFORE" ] && ok "the code file is untouched" || fail "the Inspector changed the code"
grep -q "DEAD-CODE dev-archive/src/mod.cpp\`: 6" "$RECD/already-there.md" && ! grep -q "^### I-.* DEAD-CODE" "$(recf)" \
  && ok "mess already in the last commit is listed as already there, not raised" \
  || fail "the baseline from the last commit is missing"
grep -q '2.75f' "$(recf)" && ! grep -q 'Where:.*x \* 37' "$(recf)" && ok "the finding points at the NEW line, not the old one" \
  || fail "the finding's example is not the new line"

echo "holding the commit"
git -C "$G" add dev-archive/src/mod.cpp
commit_hook Bash "$(native "$T")" "cd \\\"$GN\\\" && git commit -m wip"
[ "$RC" = "2" ] && ok "a commit is held while findings wait (repo found through cd)" || fail "commit not held (rc=$RC $OUT)"
case "$OUT" in *"held"*I-000*) ok "and it names the findings" ;; *) fail "the hold does not name the findings" ;; esac

verdict I-0001 "keep: short"; verdict I-0002 "keep: short"
commit_hook PowerShell "$(native "$T")" "git -C \\\"$GN\\\" commit -m wip"
[ "$RC" = "2" ] && ok "a keep with no real reason still counts as waiting (repo found through git -C)" \
                || fail "a reasonless keep let the commit through"

IDS=$(grep -o '^### I-[0-9]*' "$(recf)" | cut -c5-)
for id in $IDS; do verdict "$id" "fix now"; done
commit_hook Bash "$GN" "git commit -m wip"
[ "$RC" = "2" ] && case "$OUT" in *"still there"*) true ;; *) false ;; esac && ok "fix now blocks while the mess is still there" \
                || fail "fix now let the mess through (rc=$RC)"

for id in $IDS; do verdict "$id" "keep: the debug build binds F10 on purpose; this game leaves it free"; done
commit_hook Bash "$GN" "git commit -m wip"
[ "$RC" = "2" ] && case "$OUT" in *"git add"*) true ;; *) false ;; esac && ok "the record must be committed with the work" \
                || fail "an unstaged record was let through (rc=$RC $OUT)"
git -C "$G" add dev-archive/inspector
commit_hook Bash "$GN" "git commit -m wip"
[ "$RC" = "0" ] && ok "with every verdict in and the record staged, the commit passes" || fail "a clean commit was held ($OUT)"
git -C "$G" commit -qm wip

echo "remembering verdicts"
out=$(post "$SRCN")
case "$out" in *INSPECTOR*) fail "a decided finding was raised again ($out)" ;; *) ok "a decided finding is not raised again" ;; esac
printf 'void t2() { if (GetAsyncKeyState(VK_F11)) {} }\n' >> "$SRC"
out=$(post "$SRCN")
case "$out" in *"got worse"*) ok "a kept finding that gets worse is raised again" ;; *) fail "worse was not raised ($out)" ;; esac
grep -q 'the earlier verdict was' "$(recf)" && ok "and the earlier verdict is kept in its note" || fail "the earlier verdict was lost"

echo "clearing, shell edits, copies"
"$PY" - "$SRC" <<'EOF'
import sys; p = sys.argv[1]; s = open(p).read()
open(p, "w", newline="\n").write("\n".join(l for l in s.splitlines() if "VK_F" not in l) + "\n")
EOF
post "$SRCN" >/dev/null
grep -q 'F-KEY dev-archive/src/mod.cpp: gone from the code' "$RECD/cleared.md" && ok "a finding that leaves the code moves to Cleared" \
  || fail "the removed F-key was not cleared"
cp "$O/src/helper.cpp" "$G/dev-archive/src/helper.cpp"   # a shell copy: no edit hook runs
git -C "$G" add dev-archive/src/helper.cpp dev-archive/src/mod.cpp
commit_hook Bash "$GN" "git commit -am copy"
case "$OUT" in *DUPLICATE*othergame/src/helper.cpp*) ok "code added through the shell is inspected at the commit, copies included" ;;
               *) fail "the shell-added copy was not caught ($OUT)" ;; esac

echo "staying out of the way"
commit_hook Bash "$GN" "git status && git log --oneline -3"
[ "$RC" = "0" ] && ok "ordinary git commands pass" || fail "a non-commit command was held"
printf 'generated file, do not edit\nint x = 12345;\n' > "$G/dev-archive/src/gen.cpp"
out=$(post "$(native "$G/dev-archive/src/gen.cpp")")
[ -z "$out" ] && ok "generated files are left alone" || fail "a generated file was inspected ($out)"
OUT=$(printf 'not json' | "$PY" "$HOOK" 2>&1); RC=$?
[ "$RC" = "0" ] && ok "broken input fails OPEN" || fail "broken input blocked (rc=$RC)"
setconf "inspector = off"
commit_hook Bash "$GN" "git commit -m wip"
[ "$RC" = "0" ] && ok "inspector = off in lanes.conf switches it off" || fail "the off switch did not work"
setconf
"$PY" "$TOOL" status "$GN" | grep -q "waiting" && ok "status lists what is waiting" || fail "status printed nothing useful"

echo "the two safety rules (2026-09-26)"
DUP=$(grep -o '^### I-[0-9]* · DUPLICATE' "$(recf)" | head -1 | cut -c5-10)
verdict "$DUP" "fix now"
git -C "$G" add dev-archive/inspector
commit_hook Bash "$GN" "git commit -m wip"
[ "$RC" = "2" ] && case "$OUT" in *"not allowed"*) true ;; *) false ;; esac \
  && ok "fix now is refused for a structural kind (copy-paste), which could change behaviour" \
  || fail "fix now on a DUPLICATE was accepted (rc=$RC $OUT)"
commit_hook Bash "$GN" "git commit -m \\\"end of session. inspector: carry over\\\""
[ "$RC" = "0" ] && ok "the emergency save goes through with findings still waiting" || fail "carry over was held ($OUT)"
git -C "$G" commit -qm "end of session. inspector: carry over"
out=$("$PY" "$TOOL" brief)
case "$out" in *carried*game*) ok "and the next session is told about them first" ;; *) fail "brief said nothing ($out)" ;; esac
verdict "$DUP" "keep: the two games genuinely share this helper on purpose"
git -C "$G" add dev-archive/inspector; git -C "$G" commit -qm verdicts
out=$("$PY" "$TOOL" brief)
[ -z "$out" ] && ok "once judged, the carry-over reminder goes away" || fail "brief kept nagging ($out)"
setconf "inspector_repos = someothergame"
printf 'void t3() { if (GetAsyncKeyState(VK_F9)) {} }\n' >> "$SRC"
out=$(post "$SRCN")
[ -z "$out" ] && ok "inspector_repos limits it to the named projects" || fail "it ran outside inspector_repos ($out)"
setconf "inspector_repos = game"
out=$(post "$SRCN")
case "$out" in *F-KEY*) ok "and runs on a named one" ;; *) fail "it did not run on a named repo ($out)" ;; esac
setconf
"$PY" "$TOOL" stats "$GN" | grep -q "DUPLICATE .*keep 1" && ok "stats counts verdicts per kind" || fail "stats is wrong"

echo "a repo that holds one folder per project (staging)"
S="$T/root/staging"; mkdir -p "$S/alpha" "$S/beta"
git -C "$S" init -q; git -C "$S" config user.email t@t; git -C "$S" config user.name t
printf 'int a = 1;\n' > "$S/alpha/a.cpp"; printf 'int b = 1;\n' > "$S/beta/b.cpp"
git -C "$S" add -A; git -C "$S" commit -qm init
printf 'void ta() { if (GetAsyncKeyState(VK_F5)) {} }\n' >> "$S/alpha/a.cpp"
out=$(post "$(native "$S/alpha/a.cpp")")
[ -d "$S/alpha/inspector" ] && [ ! -d "$S/inspector" ] && ok "each project folder gets its own record" \
  || fail "the staging record landed in the wrong place ($out)"
setconf "inspector_repos = alpha"
printf 'void tb() { if (GetAsyncKeyState(VK_F6)) {} }\n' >> "$S/beta/b.cpp"
out=$(post "$(native "$S/beta/b.cpp")")
[ -z "$out" ] && [ ! -d "$S/beta/inspector" ] && ok "inspector_repos names project folders inside staging" \
  || fail "a project outside inspector_repos was inspected ($out)"
setconf

echo "best of both: note silently, answer once at the end of the session (inspector_mode = end)"
MODE=end; setconf
E="$T/root/endgame"; ED="$E/dev-archive/inspector"; mkdir -p "$E/dev-archive/src"
git -C "$E" init -q; git -C "$E" config user.email t@t; git -C "$E" config user.name t
printf 'int a = 1;\n' > "$E/dev-archive/src/e.cpp"; git -C "$E" add -A; git -C "$E" commit -qm init
EN="$(native "$E")"; RN="$(native "$T/root")"
post_s() { printf '{"hook_event_name":"PostToolUse","tool_name":"Edit","session_id":"%s","tool_input":{"file_path":"%s"}}' \
           "$1" "$2" | "$PY" "$HOOK" 2>&1; }
printf 'void te() { if (GetAsyncKeyState(VK_F7)) {} }\n' >> "$E/dev-archive/src/e.cpp"
out=$(post_s s1 "$(native "$E/dev-archive/src/e.cpp")")
[ -z "$out" ] && grep -q "F-KEY" "$ED/this-session.md" && ok "an edit is noted silently, in this-session.md" \
  || fail "end mode spoke up or wrote nothing ($out)"
git -C "$E" add dev-archive/src/e.cpp
commit_hook Bash "$EN" "git commit -m mid-session"
[ "$RC" = "0" ] && ok "a save in the middle of the session goes through" || fail "end mode held a mid-session save ($OUT)"
git -C "$E" commit -qm mid-session
RELEASE="bash claude-memory/tools/lane-claim.sh release /pd endgame"
commit_hook Bash "$RN" "$RELEASE"
[ "$RC" = "2" ] && case "$OUT" in *"cannot close"*F-KEY*) true ;; *) false ;; esac \
  && ok "closing the lane session is held until the notes are answered" || fail "the session closed unanswered (rc=$RC $OUT)"
RECD="$ED"; verdict I-0001 "keep: F7 is free in this game and matches the other mods' debug key"
commit_hook Bash "$RN" "$RELEASE"
[ "$RC" = "2" ] && case "$OUT" in *"not committed"*) true ;; *) false ;; esac \
  && ok "answered but uncommitted notes still hold it" || fail "uncommitted notes let the session close (rc=$RC $OUT)"
git -C "$E" add dev-archive/inspector; git -C "$E" commit -qm notes
commit_hook Bash "$RN" "$RELEASE"
[ "$RC" = "0" ] && ok "answered and committed: the session closes" || fail "a clean close was held ($OUT)"
grep -q "I-0001" "$ED/decided.md" && ok "the answered note moved to decided.md" || fail "decided.md does not hold it"
printf 'void tf() { if (GetAsyncKeyState(VK_F4)) {} }\n' >> "$E/dev-archive/src/e.cpp"
post_s s1 "$(native "$E/dev-archive/src/e.cpp")" >/dev/null
out=$("$PY" "$TOOL" brief --session s2)
case "$out" in *endgame*) ok "a session that ended with a note unanswered: the next session is told first" ;;
               *) fail "the next session was not told ($out)" ;; esac
printf 'void tg() { x = y * 3.75f; }\n' >> "$E/dev-archive/src/e.cpp"
post_s s2 "$(native "$E/dev-archive/src/e.cpp")" >/dev/null
grep -q "F-KEY" "$ED/waiting.md" && grep -q "LOOSE-NUMS" "$ED/this-session.md" \
  && ok "the old session's note sits in waiting.md, the new session's in this-session.md" \
  || fail "notes were not sorted by session"
commit_hook Bash "$RN" "$RELEASE   # inspector: carry over"
[ "$RC" = "0" ] && ok "out of time: carry over lets the session close anyway" || fail "carry over was held ($OUT)"

echo "saves stay on this PC until the notes are answered (upload held, 2026-09-26)"
git -C "$E" add -A; git -C "$E" commit -qm "work with notes waiting"
commit_hook Bash "$EN" "git push"
[ "$RC" = "2" ] && case "$OUT" in *"upload to GitHub is held"*) true ;; *) false ;; esac \
  && ok "an upload is held while notes wait; saving itself was never blocked" || fail "the push went through (rc=$RC $OUT)"
ls "$LANES_INSPECTOR_CACHE/held/endgame/"*.bundle >/dev/null 2>&1 \
  && ok "a backup copy of the held work is in the Inspector's own folder" || fail "no backup bundle was made"
B=$(ls "$LANES_INSPECTOR_CACHE/held/endgame/"*.bundle | head -1)
git -C "$E" bundle verify "$B" >/dev/null 2>&1 && ok "and git can read it back" || fail "the backup bundle is not valid"
commit_hook Bash "$EN" "git push   # inspector: carry over"
[ "$RC" = "0" ] && ok "carry over lets an upload through in an emergency" || fail "carry over did not free the push ($OUT)"
RECD="$ED"
for id in $(grep -o '^### I-[0-9]*' "$ED/waiting.md" "$ED/this-session.md" | sed 's/.*### //'); do
  verdict "$id" "fix later: row endgame-tidy on the board"
done
commit_hook Bash "$EN" "git push"
[ "$RC" = "2" ] && case "$OUT" in *"not committed"*) true ;; *) false ;; esac \
  && ok "answered but uncommitted notes still hold the upload" || fail "uncommitted notes let the push through (rc=$RC $OUT)"
git -C "$E" add dev-archive/inspector
commit_hook Bash "$EN" "git commit -m notes && git push"
[ "$RC" = "0" ] && ok "answered, staged and committed in the same command: the upload goes" || fail "commit-then-push was held ($OUT)"
setconf "inspector = off"
commit_hook Bash "$EN" "git push"
[ "$RC" = "0" ] && ok "with the Inspector not switched on, nothing is held" || fail "an optional Inspector held a push"
rm -f "$LANES_CONFIG"
out=$(post_s s3 "$(native "$E/dev-archive/src/e.cpp")")
[ -z "$out" ] && ok "with no setting at all, the Inspector stays off (installing it is optional)" || fail "it ran unasked ($out)"
MODE=each; setconf

echo "notes stay on this PC while the Inspector is in-house (public repos, 2026-09-26)"
P="$T/root/publicgame"; mkdir -p "$P/dev-archive/src"
git -C "$P" init -q; git -C "$P" config user.email t@t; git -C "$P" config user.name t
printf 'int a = 1;\n' > "$P/dev-archive/src/p.cpp"; git -C "$P" add -A; git -C "$P" commit -qm init
MODE=end; setconf "inspector_notes_local = on"
printf 'void tp() { if (GetAsyncKeyState(VK_F3)) {} }\n' >> "$P/dev-archive/src/p.cpp"
post_s s9 "$(native "$P/dev-archive/src/p.cpp")" >/dev/null
[ -d "$P/dev-archive/inspector" ] && ! git -C "$P" status --porcelain | grep -q inspector \
  && ok "the notes folder is written but git does not see it" || fail "the notes folder would be committed"
grep -q "^/dev-archive/inspector/$" "$P/.git/info/exclude" && ok "it is listed in the clone's own exclude file, never pushed" \
  || fail "the exclude line is missing"
git -C "$P" add -A; git -C "$P" commit -qm work
commit_hook Bash "$(native "$P")" "git push"
[ "$RC" = "2" ] && case "$OUT" in *"upload to GitHub is held"*) true ;; *) false ;; esac \
  && ok "unanswered local notes still hold the upload" || fail "local notes did not hold the push ($OUT)"
MODE=each; setconf

echo "the eight faults from the first Village review"
if out=$("$PY" "$HERE/inspector_faults_test.py" 2>&1); then ok "$(printf '%s\n' \"$out\" | tail -n 1)"
else printf '%s\n' \"$out\" | grep FAIL; fail "inspector_faults_test.py failed"; fi

echo "inspector-fixture: $N checks, $FAILED failed"
[ "$FAILED" -eq 0 ]
