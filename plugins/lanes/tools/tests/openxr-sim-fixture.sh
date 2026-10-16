#!/usr/bin/env bash
# openxr-sim-fixture.sh - tools/openxr-sim.py (0.73.0) against a scratch "GitHub": a release zip with one top folder
# and its SHA-256 file. Not on the PC -> installs into the default folder, unpacked flat, release noted; finds it again
# through lanes.conf when it lives elsewhere; a wrong checksum installs nothing; decline is remembered.
# Exit 0 = all passed.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TOOL="$HERE/../openxr-sim.py"
PY=""
for cand in python3 python py; do command -v "$cand" >/dev/null 2>&1 && "$cand" -c "" >/dev/null 2>&1 && { PY="$cand"; break; }; done
[ -n "$PY" ] || { echo "openxr-sim-fixture: no working Python"; exit 1; }
pass=0; fail=0
check() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; fi; }

T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
# a release zip with one top folder holding both runtimes, plus its checksum, plus a fake GitHub answer
"$PY" - "$T" <<'EOF'
import hashlib, json, os, sys, zipfile
t = sys.argv[1]
z = os.path.join(t, "sim.zip")
with zipfile.ZipFile(z, "w") as f:
    for n in ("OpenXR-Simulator/openxr_simulator.dll", "OpenXR-Simulator/openxr_simulator.json",
              "OpenXR-Simulator/openxr_simulator-32.dll", "OpenXR-Simulator/mcp-server/helper.py"):
        f.writestr(n, "x" + n)
h = hashlib.sha256(open(z, "rb").read()).hexdigest()
open(z + ".sha256", "w").write(h + "  sim.zip\n")
open(os.path.join(t, "bad.sha256"), "w").write("0" * 64 + "  sim.zip\n")
def rel(tag, sha):
    return {"tag_name": tag, "assets": [{"name": "sim.zip", "browser_download_url": z},
                                        {"name": "sim.zip.sha256", "browser_download_url": sha}]}
json.dump({"original": rel("v9.0", z + ".sha256"), "fork": rel("v9.1", z + ".sha256")}, open(os.path.join(t, "rel.json"), "w"))
json.dump({"original": rel("v9.0", os.path.join(t, "bad.sha256")), "fork": rel("v9.1", os.path.join(t, "bad.sha256"))},
          open(os.path.join(t, "bad.json"), "w"))
EOF
export LANES_OPENXRSIM_NOREG=1 LANES_STATE_DIR="$T/state" LANES_CONFIG="$T/none.conf"
run() { LANES_OPENXRSIM_DIR="$T/default" LANES_OPENXRSIM_RELEASE="$T/${REL:-rel.json}" "$PY" "$TOOL" "$@"; }

out="$(run status --json)"
check "nothing there: not installed, newest release read" '[[ "$out" == *"\"installed\": false"* && "$out" == *"v9.0"* ]]'
REL=bad.json run install >"$T/o" 2>&1
check "a wrong checksum installs nothing" '[ ! -e "$T/default/openxr_simulator.dll" ] && grep -q "does not match" "$T/o"'
out="$(run install)"
check "install unpacks flat into the default folder" '[ -f "$T/default/openxr_simulator.dll" ] && [ -f "$T/default/mcp-server/helper.py" ]'
check "install notes the source and release" 'grep -q "original v9.0" "$T/default/lanes-release.txt"'
check "install says it is not switched on" '[[ "$out" == *"NOT switched on"* ]]'
out="$(run status --json)"
check "status: installed, both runtimes, up to date" '[[ "$out" == *"\"installed\": true"* && "$out" == *"\"has_32bit\": true"* && "$out" == *"\"newer\": false"* ]]'
mkdir -p "$T/elsewhere"; cp "$T/default/openxr_simulator.dll" "$T/elsewhere/"; rm -rf "$T/default"
ELSE="$T/elsewhere"; command -v cygpath >/dev/null 2>&1 && ELSE="$(cygpath -m "$ELSE")"   # a path Windows Python can read
printf 'openxr_sim = %s\n' "$ELSE" > "$T/c.conf"
out="$(LANES_CONFIG="$T/c.conf" run status)"
check "a copy named in lanes.conf is found, release unknown" '[[ "$out" == *"release unknown"* ]]'
out="$(LANES_CONFIG="$T/c.conf" run install --fork)"
check "install --fork updates the copy where it is" 'grep -q "fork v9.1" "$T/elsewhere/lanes-release.txt" && [ ! -e "$T/default" ]'
run decline >/dev/null
out="$(run status --json)"
check "decline is remembered" '[[ "$out" == *"\"declined\": true"* ]]'
echo "openxr-sim-fixture: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
