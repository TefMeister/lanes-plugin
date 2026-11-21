#!/usr/bin/env bash
# estate-fixture.sh - tools/estate.py (0.78.0) against a stand-in gh whose "GitHub" is a folder of bare repos.
# make builds the private base repos and the lane roots and writes lanes.conf; a second PC clones instead of making;
# project makes the lane folders and the board page; nothing existing is overwritten. Exit 0 = all passed.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PY=""
for cand in python3 python py; do command -v "$cand" >/dev/null 2>&1 && "$cand" -c "" >/dev/null 2>&1 && { PY="$cand"; break; }; done
[ -n "$PY" ] || { echo "estate-fixture: no working Python"; exit 1; }
pass=0; fail=0
check() { if [ "$1" = "$2" ]; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $3 (got $1, wanted $2)"; fi; }
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
W() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi; }
ES="$HERE/../estate.py"
mkdir -p "$T/github"
export GIT_CONFIG_GLOBAL="$T/gitconfig" GIT_CONFIG_NOSYSTEM=1
git config --global init.defaultBranch main

# the stand-in gh: signed in as "someone"; repos live as bare repos in $T/github/<name>.git
cat > "$T/gh.py" <<'EOF'
import os, subprocess, sys
T = os.path.dirname(os.path.abspath(__file__))
G = os.path.join(T, "github")
a = sys.argv[1:]
log = open(os.path.join(T, "calls"), "a"); log.write(" ".join(a) + "\n"); log.close()
if a[:2] == ["auth", "status"]:
    sys.exit(0 if not os.path.exists(os.path.join(T, "signed-out")) else 1)
if a[:2] == ["api", "user"]:
    print("4242" if a[-1] == ".id" else "someone"); sys.exit(0)
if a[:2] == ["repo", "view"]:
    sys.exit(0 if os.path.isdir(os.path.join(G, a[2].split("/")[1] + ".git")) else 1)
if a[:2] == ["repo", "create"]:
    lim = os.path.join(T, "limit")
    if os.path.exists(lim) and int(open(lim).read().strip() or 0) > 0:
        n = int(open(lim).read().strip())
        open(lim, "w").write(str(n - 1))
        sys.stderr.write("GraphQL: You have created too many repositories, too quickly. Please try again later. (createRepository)")
        sys.exit(1)
    name, src = a[2], a[a.index("--source") + 1]
    bare = os.path.join(G, name + ".git")
    subprocess.run(["git", "init", "-q", "--bare", bare], check=True)
    open(os.path.join(G, name + ".visibility"), "w").write("public" if "--public" in a else "private")
    subprocess.run(["git", "-C", src, "remote", "add", "origin", bare], check=True)
    sys.exit(subprocess.run(["git", "-C", src, "push", "-q", "-u", "origin", "main"]).returncode)
if a[:2] == ["repo", "clone"]:
    sys.exit(subprocess.run(["git", "clone", "-q", os.path.join(G, a[2].split("/")[1] + ".git"), a[3]]).returncode)
sys.exit(1)
EOF
printf '@echo off\r\n"%s" "%s" %%*\r\n' "$(W "$(command -v "$PY")")" "$(W "$T/gh.py")" > "$T/gh.cmd"
printf '#!/usr/bin/env bash\nexec "%s" "%s" "$@"\n' "$(command -v "$PY")" "$T/gh.py" > "$T/gh"; chmod +x "$T/gh"
if [ "${OS:-}" = "Windows_NT" ]; then export LANES_GH="$(W "$T/gh.cmd")"; else export LANES_GH="$T/gh"; fi

# PC one
export LANES_CONFIG="$(W "$T/pc1.conf")"
touch "$T/signed-out"
"$PY" "$ES" make --root "$(W "$T/pc1/clones")" >/dev/null; check $? 1 "make stops when GitHub is not signed in"
[ -e "$T/pc1/clones" ]; check $? 1 "nothing was made while signed out"
rm "$T/signed-out"
"$PY" "$ES" plan --root "$(W "$T/pc1/clones")" >/dev/null; check $? 0 "plan works"
[ -e "$T/pc1/clones" ]; check $? 1 "plan makes nothing"
"$PY" "$ES" make --root "$(W "$T/pc1/clones")" --skip builds --name ideas=my-ideas >/dev/null; check $? 0 "make works"
for r in board my-ideas staging session-logs; do
  [ -d "$T/github/$r.git" ]; check $? 0 "$r is on GitHub"
  check "$(cat "$T/github/$r.visibility")" private "$r is private"
done
[ -d "$T/github/builds.git" ]; check $? 1 "a skipped repo is not made"
[ -f "$T/pc1/clones/board/machine-assignments.tsv" ]; check $? 0 "the board comes from the template"
[ -f "$T/pc1/clones/board/status/example-project.md" ]; check $? 1 "without the example project"
[ -f "$T/pc1/clones/my-ideas/DUMP.md" ]; check $? 0 "the ideas repo comes from its template"
[ -d "$T/pc1/clones-pd/board/.git" ]; check $? 0 "the lane roots got a copy of every repo"
[ -d "$T/pc1/clones-gs/staging/.git" ]; check $? 0 "every lane root"
grep -q "^board = " "$T/pc1.conf"; check $? 0 "lanes.conf has the board"
grep -q "^ideas = .*my-ideas" "$T/pc1.conf"; check $? 0 "and the renamed ideas repo"
grep -q "^root = " "$T/pc1.conf"; check $? 0 "and the clone root"
grep -q "^builds = " "$T/pc1.conf"; check $? 1 "and not the skipped one"
before=$(wc -l < "$T/calls")
"$PY" "$ES" make --root "$(W "$T/pc1/clones")" --skip builds --name ideas=my-ideas >/dev/null; check $? 0 "a second make is harmless"
check "$(tail -n +"$((before+1))" "$T/calls" | grep -c 'repo create')" 0 "and makes nothing twice"
check "$(grep -c '^board = ' "$T/pc1.conf")" 1 "lanes.conf is not written twice"

"$PY" "$ES" project my-game >/dev/null; check $? 0 "project works"
check "$(cat "$T/github/my-game.visibility")" private "a project is private by default"
for f in README.md dev-archive/README.md notes/README.md engine-research/ENGINE-DOSSIER.md \
         engine-research/inbox/README.md external-research/INDEX.md external-research/inbox/README.md; do
  [ -f "$T/pc1/clones/my-game/$f" ]; check $? 0 "the project has $f"
done
git --git-dir="$T/github/board.git" show main:status/my-game.md 2>/dev/null | grep -q "^OPEN ("; check $? 0 "its board page is pushed"
[ -d "$T/pc1/clones-sr/my-game/.git" ]; check $? 0 "the project reached the lane roots"
"$PY" "$ES" project shown --public >/dev/null; check $? 0 "a public project when asked"
check "$(cat "$T/github/shown.visibility")" public "is public"
echo "my own notes" > "$T/pc1/clones/board/status/my-game.md"
"$PY" "$ES" project my-game >/dev/null; check $? 0 "an existing project is left alone"
check "$(cat "$T/pc1/clones/board/status/my-game.md")" "my own notes" "its board page is not overwritten"

# GitHub's "too many repositories, too quickly" (Workshop PC 2026-11-21): waited out by itself; a project it kept
# refusing is made by the next run instead of being "left alone" for ever
export LANES_ESTATE_WAITS="0,0"
echo 2 > "$T/limit"
out=$("$PY" "$ES" project waited 2>&1); check $? 0 "a project GitHub refused twice is made on the third try by itself"
printf '%s' "$out" | grep -q "too many repos too quickly"; check $? 0 "and it says plainly why it waits"
[ -d "$T/github/waited.git" ]; check $? 0 "the waited-for project is on GitHub"
echo 99 > "$T/limit"
out=$("$PY" "$ES" project refused 2>&1); check $? 1 "a project GitHub keeps refusing stops"
printf '%s' "$out" | grep -q "run the same command again later"; check $? 0 "and says what to do next"
[ -d "$T/github/refused.git" ]; check $? 1 "it is not on GitHub"
[ -d "$T/pc1/clones/refused/.git" ]; check $? 0 "its local copy is kept"
rm -f "$T/limit"
out=$("$PY" "$ES" project refused 2>&1); check $? 0 "the next run makes the refused project"
printf '%s' "$out" | grep -q "left alone"; check $? 1 "instead of leaving the copy alone"
[ -d "$T/github/refused.git" ]; check $? 0 "it is on GitHub now"
git --git-dir="$T/github/refused.git" log -1 --format=%s main 2>/dev/null | grep -q "lane folders"; check $? 0 "with its first commit"
git --git-dir="$T/github/board.git" show main:status/refused.md 2>/dev/null | grep -q "^OPEN ("; check $? 0 "and its board page"
[ -d "$T/pc1/clones-sr/refused/.git" ]; check $? 0 "and it reached the lane roots"
printf '%s' "$out" | grep -q "but builds"; check $? 0 "the lane-root line says builds stays in one place"
export LANES_CONFIG="$(W "$T/pc3.conf")"
echo 99 > "$T/limit"
"$PY" "$ES" make --root "$(W "$T/pc3/clones")" --skip ideas,staging,builds,logs --name board=board3 >/dev/null 2>&1; check $? 1 "a base repo GitHub refuses stops make"
rm -f "$T/limit"
"$PY" "$ES" make --root "$(W "$T/pc3/clones")" --skip ideas,staging,builds,logs --name board=board3 >/dev/null 2>&1; check $? 0 "the next make finishes it"
[ -d "$T/github/board3.git" ]; check $? 0 "the refused base repo is on GitHub now"
unset LANES_ESTATE_WAITS

# PC two, same account: everything is cloned, nothing made
export LANES_CONFIG="$(W "$T/pc2.conf")"
echo "board = /somewhere/else" > "$T/pc2.conf"
before=$(wc -l < "$T/calls")
out=$("$PY" "$ES" make --root "$(W "$T/pc2/clones")" --skip builds --name ideas=my-ideas); check $? 0 "the second PC's make works"
check "$(tail -n +"$((before+1))" "$T/calls" | grep -c 'repo create')" 0 "the second PC makes no repo"
[ -d "$T/pc2/clones/board/status" ]; check $? 0 "it clones the board"
printf '%s' "$out" | grep -q "NOT changed"; check $? 0 "it says when lanes.conf already points elsewhere"
check "$(grep '^board' "$T/pc2.conf")" "board = /somewhere/else" "and leaves that setting alone"
mkdir -p "$T/pc2/clones/other"; echo x > "$T/pc2/clones/other/file"
"$PY" "$ES" make --root "$(W "$T/pc2/clones")" --name staging=other >/dev/null; check $? 1 "a folder that is not a clone stops it"
check "$(cat "$T/pc2/clones/other/file")" x "and is not touched"

[ "$fail" -eq 0 ] || exit 1
echo "estate: $pass checks passed"
