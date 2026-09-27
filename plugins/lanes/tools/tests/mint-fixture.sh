#!/usr/bin/env bash
# mint-fixture.sh - asserts mint.py never writes into the clean install, catches a file that appears
# in it, refuses to put the private copy anywhere it could be shared, makes a verified copy carrying the
# notice, and that builds.py works in the copy and refuses to restore into the clean install.
# Everything lives in a temp folder; the real lanes.conf is never read (LANES_CONFIG points at a scratch file).
#   bash tools/tests/mint-fixture.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TOOLS="$(cd "$HERE/.." && pwd)"
PY=""
for cand in python3 python py; do
  command -v "$cand" >/dev/null 2>&1 || continue
  "$cand" -c "" >/dev/null 2>&1 || continue
  PY="$cand"; break
done
[ -n "$PY" ] || { echo "mint-fixture: no working python"; exit 2; }

T="$(mktemp -d)"; T="$(cygpath -m "$T" 2>/dev/null || echo "$T")"; trap 'rm -rf "$T"' EXIT
FAILED=0; N=0
ok()   { N=$((N+1)); printf '  ok    %s\n' "$1"; }
fail() { N=$((N+1)); printf '  FAIL  %s\n' "$1"; FAILED=1; }
has()  { case "$2" in *"$1"*) ok "$3" ;; *) fail "$3 (expected: $1)" ;; esac; }
treesum() { (cd "$1" && find . -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -c1-64); }

export GIT_AUTHOR_NAME=fixture GIT_AUTHOR_EMAIL=fixture@example.invalid
export GIT_COMMITTER_NAME=fixture GIT_COMMITTER_EMAIL=fixture@example.invalid
V="$T/store/game"; mkdir -p "$V/data"
echo exe > "$V/game.exe"; echo pak > "$V/data/content.pak"; echo "opt=1" > "$V/settings.ini"
cat > "$T/lanes.conf" <<EOF
mint_home = $T/minthome
mint_vanilla.proj = $V
mint_normal.proj = settings.ini
EOF
export LANES_CONFIG="$T/lanes.conf"
mint() { "$PY" "$TOOLS/mint.py" "$@" 2>&1; }
before=$(treesum "$V")

echo "guide + fingerprint + check"
has "Uninstall" "$(mint guide proj)" "the guide gives the uninstall step"
has "3 files" "$(mint fingerprint proj)" "fingerprint records every file"
out=$(mint check proj); rc=$?
has "still mint" "$out" "a clean install checks as mint"; [ $rc -eq 0 ] && ok "exit 0 when mint" || fail "exit 0 when mint"
echo "opt=2" > "$V/settings.ini"
out=$(mint check proj); rc=$?
has "changed by the app itself" "$out" "a rewritten settings file is reported as normal"
[ $rc -eq 0 ] && ok "a normal change is not a fault" || fail "a normal change is not a fault"
echo "opt=1" > "$V/settings.ini"
echo leftover > "$V/data/leftover.lua"
out=$(mint check proj); rc=$?
has "added: data/leftover.lua" "$out" "a file that appeared in the clean install is named"
[ $rc -eq 1 ] && ok "exit 1 when not mint" || fail "exit 1 when not mint"
out=$(mint copy proj --to "$T/copyA" --yes)
has "NOT mint" "$out" "copying an unclean install is refused"
[ -d "$T/copyA" ] && fail "nothing copied when refused" || ok "nothing copied when refused"
rm "$V/data/leftover.lua"

echo "the copy may only go where it cannot be shared"
has "inside the clean install" "$(mint copy proj --to "$V/sub" --yes)" "refused inside the clean install"
git init -q "$T/repo"
has "git repository" "$(mint copy proj --to "$T/repo/gamecopy" --yes)" "refused inside a git repo"
has "cloud-synced" "$(mint copy proj --to "$T/OneDrive/gamecopy" --yes)" "refused inside a synced folder"
mkdir -p "$T/full"; echo x > "$T/full/old.txt"
has "not empty" "$(mint copy proj --to "$T/full" --yes)" "refused into a folder that is not empty"
out=$(mint copy proj --to "$T/copy")
has "Sharing these files is illegal" "$out" "the dry run shows the legal notice"
[ -d "$T/copy" ] && fail "a dry run copies nothing" || ok "a dry run copies nothing"

echo "the copy"
out=$(mint copy proj --to "$T/copy" --yes --steam-appid 12345)
has "every one identical" "$out" "the copy is verified file by file"
[ -f "$T/copy/NOT-FOR-SHARING.txt" ] && ok "the copy carries the notice" || fail "the copy carries the notice"
grep -q "illegal" "$T/copy/NOT-FOR-SHARING.txt" && ok "the notice says sharing is illegal" || fail "the notice says sharing is illegal"
[ "$(cat "$T/copy/steam_appid.txt" 2>/dev/null)" = "12345" ] && ok "steam_appid.txt written on request" || fail "steam_appid.txt written on request"
printf 'mint_copy.proj = %s\n' "$T/copy" >> "$T/lanes.conf"
echo mod > "$T/copy/mod.dll"
out=$(mint check proj --copy)
has "added: mod.dll" "$out" "check --copy lists our changes in the copy"

echo "builds.py works in the copy and never writes into the clean install"
git init -q --bare -b main "$T/remote.git"; git clone -q "$T/remote.git" "$T/builds" 2>/dev/null
git -C "$T/builds" commit -q --allow-empty -m start && git -C "$T/builds" push -q -u origin main 2>/dev/null
export LANES_BUILDS="$T/builds"
"$PY" "$TOOLS/builds.py" init proj --app "$V" --ours mod.dll >/dev/null 2>&1
out=$("$PY" "$TOOLS/builds.py" snap proj "first" --note "n" 2>&1)
[ -f "$T/builds/proj/v0.1.0-b001 - first/mod.dll" ] && ok "snap reads the copy, not PROJECT.conf's app" || fail "snap reads the copy ($out)"
grep -v '^mint_copy' "$T/lanes.conf" > "$T/l2" && mv "$T/l2" "$T/lanes.conf"
out=$("$PY" "$TOOLS/builds.py" restore proj 1 --yes 2>&1)
has "refused" "$out" "restore into the clean install is refused"

after=$(treesum "$V")
[ "$before" = "$after" ] && ok "the clean install is byte-for-byte what it was before every command" \
  || fail "the clean install changed"

echo
[ "$FAILED" -eq 0 ] && echo "mint-fixture: $N checks, 0 failed" || { echo "mint-fixture: FAILURES above"; exit 1; }
