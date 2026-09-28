#!/usr/bin/env bash
# release.sh - publish a lanes version ONLY if every check passes. The one way to release.
#
#   bash plugins/lanes/tools/release.sh X.Y.Z "one-line release notes"     check, then publish
#   bash plugins/lanes/tools/release.sh X.Y.Z --check                       check only, publish nothing
#
# Why this exists (2026-09-28): 0.31.1 was published with a person's name in it. The privacy scan DID catch it,
# but the release ran in the same command line as the checks, behind a pipe that hid their failure. A check that
# does not stop the release is decoration. Here every check runs on its own, its exit code is read, and nothing
# is tagged or published unless all of them passed.
#
# What it checks, in order (it stops at the first failure and says which):
#   1. the version is X.Y.Z in all four places: plugin.json, marketplace.json, the newest CHANGELOG line,
#      and the front page (the installer reads marketplace.json; RELEASE-CHECKLIST B8)
#   2. everything is committed (nothing unsaved could slip past the checks)
#   3. the tag vX.Y.Z does not exist yet
#   4. the privacy scan finds nothing that identifies a person
#   5. the smoke test and the hooks test pass
# Then it pushes, tags vX.Y.Z, pushes the tag, and creates the GitHub Release marked Latest.
set -uo pipefail

VERSION="${1:-}"
NOTES="${2:-}"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "usage: release.sh X.Y.Z \"notes\" | --check"; exit 2; }
[ -n "$NOTES" ] || { echo "give one line of release notes, or --check"; exit 2; }

HERE="$(cd "$(dirname "$0")" && pwd)"
PLUGIN="$(cd "$HERE/.." && pwd)"
ROOT="$(cd "$PLUGIN/../.." && pwd)"
cd "$ROOT" || exit 2
REL="${PLUGIN#$ROOT/}"   # the plugin folder relative to the repo, so Windows Python can open it
PY=""
for cand in python3 python py; do
  command -v "$cand" >/dev/null 2>&1 && "$cand" -c "" >/dev/null 2>&1 && { PY="$cand"; break; }
done
[ -n "$PY" ] || { echo "STOP: no python found"; exit 1; }

stop() { echo; echo "STOP: $*"; echo "Nothing was tagged or published."; exit 1; }
ok() { echo "  ok    $*"; }

echo "Checking lanes $VERSION before any release"

# 1. the version in all four places
pv=$("$PY" -c "import json; print(json.load(open('$REL/.claude-plugin/plugin.json'))['version'])")
mv=$("$PY" -c "import json; print([p['version'] for p in json.load(open('.claude-plugin/marketplace.json'))['plugins'] if p['name']=='lanes'][0])")
cv=$(grep -m1 -oE '^- \*\*[0-9]+\.[0-9]+\.[0-9]+\*\*' "$REL/CHANGELOG.md" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
grep -q "\`$VERSION\`" README.md && rv="$VERSION" || rv="(not found)"
[ "$pv" = "$VERSION" ] || stop "plugin.json says $pv, not $VERSION"
[ "$mv" = "$VERSION" ] || stop "marketplace.json says $mv, not $VERSION (this is the one the installer reads)"
[ "$cv" = "$VERSION" ] || stop "the newest CHANGELOG line is $cv, not $VERSION"
[ "$rv" = "$VERSION" ] || stop "the front page does not name $VERSION"
ok "version $VERSION in plugin.json, marketplace.json, CHANGELOG and the front page"

# 2. everything committed
[ -z "$(git status --porcelain)" ] || { git status --short | head; stop "there are unsaved changes; commit them first so the checks see what is published"; }
ok "everything is committed"

# 3. the tag is new
git fetch -q --tags origin 2>/dev/null
git rev-parse -q --verify "refs/tags/v$VERSION" >/dev/null && stop "the tag v$VERSION already exists"
ok "tag v$VERSION is new"

# 4. privacy
if ! out=$("$PY" "$REL/tools/scrub-scan.py" . 2>&1); then
  printf '%s\n' "$out" | head -20
  stop "the privacy scan found something that identifies a person"
fi
ok "privacy scan clean"

# 5. tests
if ! out=$(bash "$HERE/tests/smoke-test.sh" 2>&1); then
  printf '%s\n' "$out" | grep -E "FAIL" | head -20
  stop "the smoke test failed"
fi
ok "smoke test passed"
if ! out=$(bash "$HERE/tests/hooks-test.sh" 2>&1); then
  printf '%s\n' "$out" | grep -E "FAIL" | head -20
  stop "the hooks test failed"
fi
ok "hooks test passed"

if [ "$NOTES" = "--check" ]; then
  echo; echo "All checks passed. --check: nothing was published."
  exit 0
fi

echo "All checks passed. Publishing lanes $VERSION"
git pull -q --rebase || stop "could not bring the branch up to date"
git push -q || stop "push failed"
git tag "v$VERSION" && git push -q origin "v$VERSION" || stop "could not push the tag"
gh release create "v$VERSION" --verify-tag --latest --title "$VERSION" --notes "$NOTES" || stop "the tag is pushed but the GitHub Release failed; run: gh release create v$VERSION --verify-tag --latest"
echo "Published lanes $VERSION"
