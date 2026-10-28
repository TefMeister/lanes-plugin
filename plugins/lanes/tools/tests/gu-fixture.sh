#!/usr/bin/env bash
# gu-fixture.sh - tools/gu.py (0.67.0): twins that match and differ, a watched tool with an un-noted release, one of
# our clones behind GitHub, lessons from KNOWN.md since the last run, and the weekly nudge. No network.
# Exit 0 = all passed.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TOOL="$HERE/../gu.py"
OD="$HERE/../od.py"
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
check "asks before installing by default" 'printf "%s" "$out" | grep -q "Ask before installing: yes"'
printf 'gu_ask = no   # my own PCs\n' >> "$T/lanes.conf"
out2="$(LANES_GU_FAKE_RELEASES="$T/rel.json" "$PY" "$TOOL" scan)"
check "gu_ask = no: updates without asking" 'printf "%s" "$out2" | grep -q "Ask before installing: no"'
"$PY" "$TOOL" seen "Some Tool" v2 >/dev/null
out="$(LANES_GU_FAKE_RELEASES="$T/rel.json" "$PY" "$TOOL" scan)"
check "once noted, the release is no longer new" 'printf "%s" "$out" | grep -q "Some Tool: v2, already noted"'

# twins in git: the copy was committed later, but the master's file date is newer (a fresh clone) -> the copy wins
mkdir -p "$T/ga" "$T/gb"
for r in ga gb; do git -C "$T/$r" init -q; done
printf 'v1\n' > "$T/ga/h.py"; (cd "$T/ga" && git add h.py && GIT_COMMITTER_DATE="2026-10-01T00:00:00" git -c user.name=t -c user.email=t@t commit -q -m a --date "2026-10-01T00:00:00")
printf 'v2\n' > "$T/gb/h.py"; (cd "$T/gb" && git add h.py && GIT_COMMITTER_DATE="2026-10-10T00:00:00" git -c user.name=t -c user.email=t@t commit -q -m b --date "2026-10-10T00:00:00")
touch "$T/ga/h.py"
printf 'twin = %s | %s\n' "$T/ga" "$T/gb" > "$T/git.conf"
out="$(LANES_CONFIG="$T/git.conf" "$PY" "$TOOL" scan)"
check "twins in git: the last commit decides, not the file date" 'printf "%s" "$out" | grep -q "changed last: the second copy"'

check "nudge: silent within the week" '[ -z "$(LANES_GU_TODAY=2026-10-11 "$PY" "$TOOL" nudge)" ]'
check "nudge: one line after a week" 'LANES_GU_TODAY=2026-10-12 "$PY" "$TOOL" nudge | grep -q "7 days ago"'
rm -f "$LANES_STATE_DIR/gu.json"
check "nudge: never run but set up = one line" '"$PY" "$TOOL" nudge | grep -q "never run"'
check "nudge: never run and nothing set up = silent" '[ -z "$(LANES_CONFIG="$T/none.conf" "$PY" "$TOOL" nudge)" ]'

# 5. texts on GitHub (0.69.0; /od section 3 since 0.94.0): a stale description, a front page pointing at an old version and saying nothing is
# released, a status part left behind by later work; and a repo whose texts are current, which must stay quiet
mkdir -p "$T/texts"
gc() { GIT_COMMITTER_DATE="$2" git -C "$T/texts/$1" -c user.name=t -c user.email=t@t commit -q "${@:3}" --date "$2"; }
git init -q -b main "$T/texts/scope"
git -C "$T/texts/scope" remote add origin https://github.com/me/scope.git
printf '# Scope\n\n## Status\n\nFinished. Download v1.0.2 from Releases.\nNothing here is released.\nUnreal Engine 5.1.1 inside.\n' > "$T/texts/scope/README.md"
git -C "$T/texts/scope" add README.md
gc scope "2026-08-01T00:00:00" -m readme
for i in $(seq 1 16); do gc scope "2026-09-10T00:00:00" --allow-empty -m "work $i"; done
git init -q -b main "$T/texts/fresh"
git -C "$T/texts/fresh" remote add origin ssh://github.com/me/fresh.git
printf '# Fresh\n\nThe current version is v2.0.0. Download it from Releases.\nThe check flags "nothing released" beside a release.\n' > "$T/texts/fresh/README.md"
git -C "$T/texts/fresh" add README.md
gc fresh "2026-10-14T00:00:00" -m readme
cat > "$T/repos.json" <<EOF
[{"name": "scope", "description": "A scope. Finished: v1.0.2 released.", "visibility": "PUBLIC", "isArchived": false, "latestRelease": {"tagName": "v1.1.5"}},
 {"name": "fresh", "description": "Fresh, v2.0.0. Engine 5.1.", "visibility": "PUBLIC", "isArchived": false, "latestRelease": {"tagName": "v2.0.0"}},
 {"name": "pre", "description": "Early build v0.1.7-alpha out.", "visibility": "PUBLIC", "isArchived": false, "latestRelease": null, "releases": [{"tagName": "v0.1.8-alpha"}]},
 {"name": "hidden", "description": "Private until work starts", "visibility": "PRIVATE", "isArchived": false, "latestRelease": null},
 {"name": "noclone", "description": "Private until work starts", "visibility": "PUBLIC", "isArchived": false, "latestRelease": null}]
EOF
printf 'texts = %s/texts\ntexts_owner = me\n' "$T" > "$T/texts.conf"
out="$(LANES_CONFIG="$T/texts.conf" LANES_GU_FAKE_REPOS="$T/repos.json" LANES_GU_TODAY=2026-10-15 "$PY" "$OD" scan)"
check "texts: public repos counted, one without a clone" 'printf "%s" "$out" | grep -q "4 public repos of me checked, 2 without a local clone"'
check "texts: old version in the description" 'printf "%s" "$out" | grep -q "scope: description names an older version than the newest release v1.1.5"'
check "texts: front page download line points at the old version" 'printf "%s" "$out" | grep -q "scope: README.md line 5 points at an older version than v1.1.5"'
check "texts: nothing-released beside a release" 'printf "%s" "$out" | grep -q "scope: README.md says nothing is released"'
check "texts: status part left behind by later work" 'printf "%s" "$out" | grep -q "scope: README.md has a status part unchanged for 75 days, 16 commits since"'
check "texts: an engine version is not a mod version" '! printf "%s" "$out" | grep -q "line 7"'
check "texts: public repo calling itself private" 'printf "%s" "$out" | grep -q "noclone: description says it is private"'
check "texts: current texts and private repos stay quiet" '! printf "%s" "$out" | grep -q "fresh:\|hidden:"'
check "texts: a pre-release counts when there is no full release" 'printf "%s" "$out" | grep -q "pre: description names an older version than the newest release v0.1.8-alpha"'
check "texts: not set up says so" 'printf "%s" "$(LANES_CONFIG="$T/none.conf" "$PY" "$OD" scan)" | grep -q "not set up (texts"'

# 6. Lanes and the skills page keep up (0.93.0; /od section 4 since 0.94.0): a public tool of ours Lanes does not offer (and a private one, an
# offered one and a skipped one that stay quiet); a connector and a plugin the skills page never names, a page gone stale
mkdir -p "$T/six/kit" "$T/six/clones/newtool" "$T/six/clones/secret" "$T/six/clones/window-view-vr" "$T/six/clones/oldtool"
git init -q -b main "$T/six/kit"
printf '# Skills\n\nx64dbg MCP and the Superpowers plugin.\n' > "$T/six/kit/SKILLS.md"
git -C "$T/six/kit" add SKILLS.md
GIT_COMMITTER_DATE="2026-08-01T00:00:00" git -C "$T/six/kit" -c user.name=t -c user.email=t@t commit -q -m s --date "2026-08-01T00:00:00"
cat > "$T/six/repos.json" <<EOF
[{"name": "newtool", "visibility": "PUBLIC", "isArchived": false}, {"name": "secret", "visibility": "PRIVATE", "isArchived": false},
 {"name": "window-view-vr", "visibility": "PUBLIC", "isArchived": false}, {"name": "oldtool", "visibility": "PUBLIC", "isArchived": false}]
EOF
printf '{"mcpServers": {"x64dbg": {}, "fancy-mcp": {}, "hush": {}}}' > "$T/six/claude.json"
printf '{"plugins": {"superpowers@x": [], "shiny@y": []}}' > "$T/six/plugins.json"
{ printf 'texts = %s/six\ntexts_owner = me\nskills = kit/SKILLS.md\nskills_skip = hush\nlanes_skip = oldtool\n' "$T"
  for n in newtool secret window-view-vr oldtool; do printf 'ours = %s/six/clones/%s\n' "$T" "$n"; done; } > "$T/six.conf"
out="$(LANES_CONFIG="$T/six.conf" LANES_GU_FAKE_REPOS="$T/six/repos.json" LANES_CLAUDE_JSON="$T/six/claude.json" \
       LANES_CLAUDE_PLUGINS="$T/six/plugins.json" LANES_GU_TODAY=2026-10-27 "$PY" "$OD" scan | sed -n '/^4\./,$p')"
check "coverage: a public tool Lanes does not offer" 'printf "%s" "$out" | grep -q "newtool: a public tool of ours that Lanes does not offer"'
check "coverage: private, offered and skipped tools stay quiet" '! printf "%s" "$out" | grep -q "secret:\|window-view-vr:\|oldtool:"'
check "coverage: a connector the skills page never names" 'printf "%s" "$out" | grep -q "MCP server .fancy-mcp. is in use"'
check "coverage: a plugin the skills page never names" 'printf "%s" "$out" | grep -q "plugin .shiny. is in use"'
check "coverage: named and skipped connectors stay quiet" '! printf "%s" "$out" | grep -q "x64dbg\|superpowers\|hush"'
check "coverage: a stale skills page" 'printf "%s" "$out" | grep -q "unchanged for 87 days"'
check "coverage: skills page not set up says so" 'LANES_CONFIG="$T/none.conf" "$PY" "$OD" scan | grep -q "skills page: not set up"'
# the skills page as GitHub shows it (0.94.1): GitHub's copy names fancy-mcp and is new, this clone was never pulled
git -C "$T/six/kit" checkout -q -b newer
printf '# Skills\n\nx64dbg MCP, fancy-mcp and the Superpowers plugin.\n' > "$T/six/kit/SKILLS.md"
GIT_COMMITTER_DATE="2026-10-27T00:00:00" git -C "$T/six/kit" -c user.name=t -c user.email=t@t commit -qam newer --date "2026-10-27T00:00:00"
git -C "$T/six/kit" update-ref refs/remotes/origin/main newer; git -C "$T/six/kit" checkout -q main; git -C "$T/six/kit" branch -qD newer
out="$(LANES_CONFIG="$T/six.conf" LANES_GU_FAKE_REPOS="$T/six/repos.json" LANES_CLAUDE_JSON="$T/six/claude.json" \
       LANES_CLAUDE_PLUGINS="$T/six/plugins.json" LANES_GU_TODAY=2026-10-27 "$PY" "$OD" scan | sed -n '/^4\./,$p')"
check "coverage: the skills page is read as GitHub shows it, not as an unpulled clone" \
  '! printf "%s" "$out" | grep -q "fancy-mcp\|unchanged for" && grep -q "x64dbg MCP and" "$T/six/kit/SKILLS.md"'
check "gu: the GitHub sections now point at /od" '"$PY" "$TOOL" scan | grep -q "5. GitHub pages, downloads and the skills page: /lanes:od"'

# /od sections 1 and 2 (0.94.0): an app whose program changed after its download (a notes-only change does not count),
# an app with no download, a library with and without the one-zip link, one in od_skip
mk() { git init -q -b main "$T/od/$1"; for f in "${@:2}"; do mkdir -p "$(dirname "$T/od/$1/$f")"; echo x > "$T/od/$1/$f"; done
       git -C "$T/od/$1" add -A; git -C "$T/od/$1" -c user.name=t -c user.email=t@t commit -q -m first; }
cm() { mkdir -p "$(dirname "$T/od/$1/$2")"; echo "$3" >> "$T/od/$1/$2"; git -C "$T/od/$1" add -A; git -C "$T/od/$1" -c user.name=t -c user.email=t@t commit -q -m "$4"; }
mkdir -p "$T/od"
mk behind build.bat app/a.cs README.md; git -C "$T/od/behind" tag v1
cm behind README.md "notes" "only notes"; cm behind app/a.cs "code" "the program moved"
mk notesonly build.bat app/a.cs; git -C "$T/od/notesonly" tag v2; cm notesonly docs/x.md "doc" "a doc"
mk distonly build.bat app/a.cs dist/a.exe; git -C "$T/od/distonly" tag v3; git -C "$T/od/distonly" rm -q dist/a.exe
git -C "$T/od/distonly" -c user.name=t -c user.email=t@t commit -q -m "built copy out of the repo"
mk nodl install.ps1 app/a.cs
mk lib README.md data/a.txt
mk libok README.md; printf 'get [it](https://github.com/me/libok/archive/refs/heads/main.zip)\n' > "$T/od/libok/README.md"
git -C "$T/od/libok" -c user.name=t -c user.email=t@t commit -qam link
mk skipped install.ps1
printf '[%s]' "$(for n in behind notesonly distonly nodl lib libok skipped; do r=""; [ $n = behind ] && r=',"latestRelease":{"tagName":"v1"}'
  [ $n = notesonly ] && r=',"latestRelease":{"tagName":"v2"}'; [ $n = distonly ] && r=',"latestRelease":{"tagName":"v3"}'; printf '{"name":"%s","visibility":"PUBLIC","isArchived":false%s},' $n "$r"; done | sed 's/,$//')" > "$T/od/repos.json"
{ printf 'texts_owner = me\nod_skip = skipped\n'; for n in behind notesonly distonly nodl lib libok skipped; do printf 'ours = %s/od/%s\n' "$T" $n; done; } > "$T/od.conf"
out="$(LANES_CONFIG="$T/od.conf" LANES_GU_FAKE_REPOS="$T/od/repos.json" "$PY" "$OD" scan | sed -n '1,/^3\./p')"
check "od: a program changed after its download" 'printf "%s" "$out" | grep -q "behind: 1 change(s) to the program since its newest download v1, newest: \"the program moved\""'
check "od: a notes-only change keeps the download current" '[ "$(git -C "$T/od/notesonly" rev-list --count v2..HEAD)" = 1 ] && ! printf "%s" "$out" | grep -q "notesonly:"'
check "od: taking built copies out of the repo is not a new program" '! printf "%s" "$out" | grep -q "distonly:"'
check "od: an app with no download" 'printf "%s" "$out" | grep -q "nodl: an app or add-on with no download yet"'
check "od: a library without the one-zip link" 'printf "%s" "$out" | grep -q "lib: a library with no one-zip download link"'
check "od: a library with the link, and od_skip, stay quiet" '! printf "%s" "$out" | grep -q "libok:\|skipped:"'

# the pages that sum up every project (0.94.2): a profile row behind its repo's work, and one whose repo only filed
# reports since; INDEX.json naming an older release than GitHub's newest
sp() { mkdir -p "$(dirname "$T/sp/$1/$2")"; echo "$3" >> "$T/sp/$1/$2"; git -C "$T/sp/$1" add -A
  GIT_COMMITTER_DATE="2026-10-${4}T12:00:00+0000" git -C "$T/sp/$1" -c user.name=t -c user.email=t@t commit -q -m "$2 $4"; }
for r in proj filed; do git init -q "$T/sp/$r"; sp $r README.md "# $r" 01; done
for d in 10 11 12; do sp proj src/a.txt $d $d; sp filed data/r.txt $d $d; sp filed knowledge/k.md $d $d; done
mkdir -p "$T/sp/profile"
printf '| Name | Where it stands | Updated |\n| --- | --- | --- |\n| **Proj** | [proj](https://github.com/me/proj) one thing | 10-01 |\n| **Filed** | [filed](https://github.com/me/filed) reports | 10-01 |\n' > "$T/sp/profile/README.md"
printf '{"projects": [{"repo": "proj", "stage": "worked on 2026-10-12", "latest_release": "v1.0.0"}]}' > "$T/sp/profile/INDEX.json"
out="$(cd "$HERE/.." && "$PY" -c "
import datetime, gu_texts as g
r = g.summary_pages(['$T/sp/profile/README.md', '$T/sp/profile/INDEX.json'], {'proj': '$T/sp/proj', 'filed': '$T/sp/filed'},
                    {'proj': {'tagName': 'v1.1.0'}}, datetime.date(2026, 10, 28), 'me')
for k, v in r.items():
    for f in v: print(k + ': ' + f)
")"
check "summary: a row behind three commits of work" 'printf "%s" "$out" | grep -q "proj: the README.md row \"Proj\", dated 2026-10-01, is behind: 3 commits"'
check "summary: reports filed since are not work" '! printf "%s" "$out" | grep -q "^filed:"'
check "summary: INDEX.json naming an older release" 'printf "%s" "$out" | grep -q "INDEX.json says latest_release v1.0.0, GitHub.s newest is v1.1.0"'
check "summary: a stage dated after the work is not behind" '! printf "%s" "$out" | grep -q "INDEX.json.s stage"'

echo "gu-fixture: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
