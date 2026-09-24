#!/usr/bin/env bash
# Self-test for proxy-gen. Never touches an app: it loads proxies into a small test exe.
#
#   bash run_tests.sh                 fake-dll tests only (64- and 32-bit)
#   bash run_tests.sh LIST_FILE       ...plus every built proxy named in LIST_FILE
#
# LIST_FILE lines: <kind> <arch> <short> <full path to a built proxy dll>
#   kind: dxgi | d3d9 | d3d11 | fake | early     arch: x64 | x86
# Each listed proxy must have been generated with the default log name (<short>_proxy_log.txt)
# or with --log-name matching what the list expects; the test reads build/<arch>/<short>_proxy_log.txt.
#
# 1. The fake dll proves the stubs keep integer, float, fastcall and stack arguments intact,
#    on the first (logging) call and on later (plain-jump) calls.
# 2. An export called BEFORE DllMain has run must not crash (the 2026-09-17 app-compat-shim case).
#
# Needs: python with pefile, and llvm-mingw clang (x86_64-w64-mingw32-clang and
# i686-w64-mingw32-clang) on PATH, or LLVM_MINGW_BIN pointing at its bin folder.
# Exit: 0 pass, 1 fail, 77 skipped (a prerequisite is missing - says which).
set -u
cd "$(dirname "$0")"
LIST="${1:-}"

BIN="${LLVM_MINGW_BIN:-}"
cc_for() {
  local name="$1"
  if [ -n "$BIN" ] && [ -x "$BIN/$name.exe" ]; then echo "$BIN/$name.exe"; return; fi
  command -v "$name" 2>/dev/null
}
declare -A CC=([x64]="$(cc_for x86_64-w64-mingw32-clang)" [x86]="$(cc_for i686-w64-mingw32-clang)")
PYTHON=""
for cand in python3 python py; do
  command -v "$cand" >/dev/null 2>&1 && "$cand" -c "import pefile" >/dev/null 2>&1 && { PYTHON="$cand"; break; }
done
[ -n "$PYTHON" ] || { echo "proxy-gen tests SKIPPED: no python with pefile (pip install pefile)"; exit 77; }
for ARCH in x64 x86; do
  [ -n "${CC[$ARCH]}" ] || { echo "proxy-gen tests SKIPPED: no llvm-mingw clang for $ARCH (set LLVM_MINGW_BIN)"; exit 77; }
done
winpath() { command -v cygpath >/dev/null 2>&1 && cygpath -w "$1" || echo "$1"; }

FAILED=0
TESTS=""
for ARCH in x64 x86; do
  OUT="build/$ARCH"
  mkdir -p "$OUT/real" "$OUT/proxy"
  "${CC[$ARCH]}" -O2 -Wall -o "$OUT/proxy_test.exe" proxy_test.c -ldxguid || exit 1
  "${CC[$ARCH]}" -shared -O2 -Wall -o "$OUT/real/fake.dll" fake_real.c fake_real.def -Wl,--kill-at || exit 1
  "$PYTHON" ../gen_proxy.py --dll fake --short fake --arch "$ARCH" --out "$OUT/proxy" \
      --source "$OUT/real/fake.dll" --real-path "$(winpath "$PWD/$OUT/real/fake.dll")" > /dev/null || exit 1
  "${CC[$ARCH]}" -shared -O2 -Wall -o "$OUT/proxy/fake.dll" "$OUT/proxy/fake_proxy.c" "$OUT/proxy/fake.def" || exit 1
  "$PYTHON" ../verify_exports.py "$OUT/proxy/fake.dll" "$OUT/real/fake.dll" || FAILED=1
  TESTS+="fake $ARCH fake $(winpath "$PWD/$OUT/proxy/fake.dll")"$'\n'
  [ "$ARCH" = x64 ] && TESTS+="early $ARCH fake $(winpath "$PWD/$OUT/proxy/fake.dll")"$'\n'
done
[ -n "$LIST" ] && TESTS+="$(grep -v '^\s*#' "$LIST")"$'\n'

while read -r KIND ARCH SHORT DLL; do
  [ -z "${KIND:-}" ] && continue
  LOG="build/$ARCH/${SHORT}_proxy_log.txt"
  rm -f "$LOG"
  echo "=================== $SHORT ($KIND, $ARCH)"
  "build/$ARCH/proxy_test.exe" "$KIND" "$DLL" || FAILED=1
  # The early case logs one expected FATAL (the real dll cannot load inside the loader, error 1168)
  # plus the early-call line; every other case must log no warning at all.
  BAD="WARNING\|FATAL\|ERROR"
  EXTRA="attached, PID"
  if [ "$KIND" = early ]; then BAD="WARNING\|ERROR"; EXTRA="early call to export"; fi
  if [ -f "$LOG" ]; then
    grep -q "attached, PID" "$LOG" && grep -q "real dll:" "$LOG" && grep -q "first call:" "$LOG" \
      && grep -q "$EXTRA" "$LOG" && grep -q "detached" "$LOG" && ! grep -q "$BAD" "$LOG" \
      && echo "LOG CHECK: PASS" || { echo "LOG CHECK: FAIL"; cat "$LOG"; FAILED=1; }
  else
    echo "LOG CHECK: FAIL (no log file at $LOG)"; FAILED=1
  fi
done <<< "$TESTS"

echo
[ $FAILED = 0 ] && echo "ALL TESTS PASSED" || echo "SOME TESTS FAILED"
exit $FAILED
