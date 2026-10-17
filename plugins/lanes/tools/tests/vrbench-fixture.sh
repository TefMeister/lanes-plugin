#!/usr/bin/env bash
# vrbench-fixture.sh - VR Bench's installer (tools/vrbench/vb_install.py, 0.74.0) against a scratch "GitHub": a release
# zip with the two layer DLLs, their manifests and an install.ps1. Not installed -> status says so with the newest tag;
# install puts the layer in place, notes the release, and this PC's board note names VR Bench; a run that is on
# refuses an install; openxr-sim.py install --fork --bench installs both.
# Exit 0 = all passed.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
VRB="$HERE/../vrbench/vrbench.py"
SIM="$HERE/../openxr-sim.py"
PY=""
for cand in python3 python py; do command -v "$cand" >/dev/null 2>&1 && "$cand" -c "" >/dev/null 2>&1 && { PY="$cand"; break; }; done
[ -n "$PY" ] || { echo "vrbench-fixture: no working Python"; exit 1; }
pass=0; fail=0
check() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; fi; }

T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
W="$T"; command -v cygpath >/dev/null 2>&1 && W="$(cygpath -m "$T")"   # paths Windows Python can read
"$PY" - "$W" <<'EOF'
import json, os, sys, zipfile
t = sys.argv[1]
z = os.path.join(t, "vr-bench-v9.0.zip")
with zipfile.ZipFile(z, "w") as f:
    for n in ("vrbench_layer.dll", "vrbench_layer32.dll", "vrbench_layer.json", "vrbench_layer32.json", "install.ps1"):
        f.writestr(n, "x" + n)
json.dump({"tag_name": "v9.0", "assets": [{"name": "vr-bench-v9.0.zip", "browser_download_url": z}]},
          open(os.path.join(t, "bench.json"), "w"))
s = os.path.join(t, "sim.zip")
with zipfile.ZipFile(s, "w") as f:
    for n in ("openxr_simulator.dll", "openxr_simulator-32.dll", "openxr_simulator.json"):
        f.writestr(n, "x" + n)
rel = {"tag_name": "v8.0", "assets": [{"name": "sim.zip", "browser_download_url": s}]}
json.dump({"original": rel, "fork": rel}, open(os.path.join(t, "sim.json"), "w"))
EOF
mkdir -p "$T/board/status"
printf 'machine_name = PCA\n' > "$T/pc.conf"
export LANES_VRBENCH_LAYER_DIR="$W/app" LANES_VRBENCH_RELEASE="$W/bench.json" LANES_VRBENCH_DIR="$W/state" \
       LANES_VRBENCH_FAKEREG="$W/reg.json" LANES_BOARD="$W/board" LANES_CONFIG="$W/pc.conf" \
       LANES_OPENXRSIM_NOREG=1 LANES_OPENXRSIM_DIR="$W/sim" LANES_OPENXRSIM_RELEASE="$W/sim.json" LANES_STATE_DIR="$W/lstate"
echo '{}' > "$T/reg.json"

out="$("$PY" "$VRB" status --json)"
check "not installed: status says so, with the newest release" '[[ "$out" == *"\"installed\": false"* && "$out" == *"v9.0"* ]]'
out="$("$PY" "$VRB" install 2>&1)"
check "install puts the 32-bit layer in place" '[ -f "$T/app/vrbench_layer32.dll" ]'
check "install notes the release" 'grep -q "v9.0" "$T/app/lanes-release.txt"'
check "this PC's board note names VR Bench" 'grep -q "VR Bench" "$T/board/installed/PCA.json"'
check "install says nothing is switched on" '[[ "$out" == *"switched on"* ]]'
out="$("$PY" "$VRB" status --json)"
check "status: installed, up to date" '[[ "$out" == *"\"installed\": true"* && "$out" == *"\"newer\": false"* ]]'
echo "{\"C:/x/vrbench_layer32.json\": 0}" > "$T/reg.json"
echo "changed" > "$T/app/vrbench_layer32.dll"
out="$("$PY" "$VRB" install 2>&1)"
check "a run that is on refuses an install, nothing replaced" '[[ "$out" == *"stop it first"* ]] && grep -q changed "$T/app/vrbench_layer32.dll"'
echo '{}' > "$T/reg.json"
rm -rf "$T/app"
out="$("$PY" "$SIM" install --fork --bench 2>&1)"
check "openxr-sim.py install --fork --bench installs both" '[ -f "$T/sim/lanes-release.txt" ] && [ -f "$T/app/lanes-release.txt" ]'
out="$("$PY" "$SIM" status --json)"
check "openxr-sim.py status carries VR Bench's status" '[[ "$out" == *"\"bench\": {"* ]]'
echo "vrbench-fixture: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
