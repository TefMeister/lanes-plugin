#!/usr/bin/env bash
# privacy-fixture.sh - tools/privacy-guard.py (0.95.0) against every gap the 2026-10-28 test day found: home paths in
# lower case, under WSL's /mnt and under Documents and Settings; the person's real e-mail when git's own is the noreply
# address (the private list); a word inside a longer word; a line added by a commit the pre-commit check never saw,
# refused at push; and the audit naming a personal e-mail in what a remote already holds. All names are made up.
# Exit 0 = all passed.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PG="$HERE/../privacy-guard.py"
PY=""
for cand in python3 python py; do command -v "$cand" >/dev/null 2>&1 && "$cand" -c "" >/dev/null 2>&1 && { PY="$cand"; break; }; done
[ -n "$PY" ] || { echo "privacy-fixture: no working Python"; exit 1; }
pass=0; fail=0
check() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; fi; }

T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
T="$(cygpath -m "$T" 2>/dev/null || printf '%s' "$T")"
export GIT_CONFIG_GLOBAL="$T/gitconfig" GIT_CONFIG_NOSYSTEM=1     # never this PC's real git settings
git config --global user.email "1+someone@users.noreply.github.com"; git config --global user.name someone
git config --global init.defaultBranch main
printf 'display_name = Someone\nroot = %s/root\n' "$T" > "$T/lanes.conf"
env_run() { USERNAME=someone LANES_CONFIG="$T/lanes.conf" LANES_STATE_DIR="$T/state" "$PY" "$PG" "$@"; }
refused() { printf '%s\n' "$1" | env_run text ${2:-} >/dev/null 2>&1; [ $? -eq 1 ]; }

check "a lower-case home path is refused" 'refused "c:\\users\\GEORGEX\\notes"'   # privacy-guard:allow
check "a WSL home path is refused" 'refused "/mnt/c/Users/hankx/notes"'            # privacy-guard:allow
check "a Documents and Settings path is refused" 'refused "C:\\Documents and Settings\\erinx\\x"'   # privacy-guard:allow
check "the display name, ~ and placeholders still pass" '! refused "C:\\Users\\Someone\\x ~/y C:/Users/Public/z %USERPROFILE%"'

check "a real e-mail passes while nothing knows it" '! refused "write to fake.person@example.org"'
mkdir -p "$T/state"
printf 'fake.person@example.org' | env_run private-words add >/dev/null
check "the private list refuses it everywhere, private repos too" 'refused "write to fake.person@example.org"'
check "private-words never prints the word itself" '! env_run private-words | grep -q fake.person'
printf 'BOXNAME\n' > "$T/state/never-publish.txt"
check "a never-publish word is refused in public text" 'refused "built on BOXNAME today" --public'
check "but not inside a longer word" '! refused "the D3D9DrvBOXNAME renderer" --public'

# push: a line that never passed the commit check (a commit made with --no-verify) is refused at push
git init -q --bare "$T/remote.git"
git clone -q "$T/remote.git" "$T/root/r" 2>/dev/null
cd "$T/root/r"
git config lanes.visibility private
git config core.hooksPath "$T/nohooks"
echo ok > a.txt; git add a.txt; git commit -q -m one; git push -q origin HEAD:main 2>/dev/null
echo "see C:/Users/hiddenx/secret" > b.txt; git add b.txt; git commit -q -m two   # privacy-guard:allow
L="$(git rev-parse HEAD)"; R="$(git rev-parse origin/main)"
out="$(printf 'refs/heads/main %s refs/heads/main %s\n' "$L" "$R" | env_run push origin https://github.com/x/y.git 2>&1)"
check "a home path in a pushed commit is refused at push" 'printf "%s" "$out" | grep -q "b.txt:1"'
echo "fine now" > b.txt; git commit -q -am three
L="$(git rev-parse HEAD)"
out="$(printf 'refs/heads/main %s refs/heads/main %s\n' "$L" "$R" | env_run push origin https://github.com/x/y.git 2>&1)"
check "and still refused when a later commit takes it out (history keeps it)" 'printf "%s" "$out" | grep -q "b.txt:1"'

# audit: a commit the remote holds with the person's own e-mail as author is named, masked
git reset -q --hard "$R"
echo mail > c.txt; git add c.txt; git -c user.email=fake.person@example.org commit -q -m four
git push -q origin HEAD:main 2>/dev/null; git fetch -q
out="$(env_run audit 2>&1)"
check "the audit names a pushed commit carrying the person's e-mail" 'printf "%s" "$out" | grep -q "r (private): 1 older commit"'
check "and never prints the address" '! printf "%s" "$out" | grep -q "fake.person@"'
cd "$HERE"

echo "privacy-fixture: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
