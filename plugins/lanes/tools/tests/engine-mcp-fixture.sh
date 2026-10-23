#!/usr/bin/env bash
# engine-mcp-fixture.sh - tools/engine-mcp.py (0.82.0) in a scratch folder, offline: the game-side half puts exactly
# the listed files in and takes exactly those out again, refuses a game without REFramework's C# support, and
# status reports what is there. Exit 0 = all passed.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PY=""
for cand in python3 python py; do command -v "$cand" >/dev/null 2>&1 && "$cand" -c "" >/dev/null 2>&1 && { PY="$cand"; break; }; done
[ -n "$PY" ] || { echo "engine-mcp-fixture: no working Python"; exit 1; }
pass=0; fail=0
check() { if [ "$1" = "$2" ]; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $3 (got $1, wanted $2)"; fi; }
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
export LANES_ENGINEMCP_HOME="$T/apps" LANES_UEVR_APPDATA="$T/appdata" LANES_CLAUDE_JSON="$T/claude.json"
export LANES_STATE_DIR="$T/state" LANES_ENGINEMCP_OFFLINE=1
EM="$HERE/../engine-mcp.py"

# stand-in installs of both servers
mkdir -p "$T/apps/re-engine-mcp/reframework/plugins/source/WebAPI" "$T/apps/re-engine-mcp/mcp-server/bin/Release/net10.0"
echo "// plugin" > "$T/apps/re-engine-mcp/reframework/plugins/source/TestWebAPI.cs"
echo "<html>" > "$T/apps/re-engine-mcp/reframework/plugins/source/WebAPI/index.html"
touch "$T/apps/re-engine-mcp/mcp-server/bin/Release/net10.0/McpServer.dll"
mkdir -p "$T/apps/uevr-mcp/bin"; touch "$T/apps/uevr-mcp/bin/UevrMcpServer.exe" "$T/apps/uevr-mcp/bin/uevr_mcp.dll"
echo '{"mcpServers": {"uevr": {"command": "x"}}}' > "$T/claude.json"

# an RE Engine game: REFramework without C# support is refused
G="$T/game"; mkdir -p "$G/reframework/plugins/source"; echo "ours" > "$G/reframework/plugins/source/keep.cs"
"$PY" "$EM" game re "$G" >/dev/null; check $? 1 "a game without csharp-api is refused"
touch "$G/reframework/plugins/REFramework.NET.dll"
"$PY" "$EM" game re "$G" >/dev/null; check $? 0 "the plugin goes in"
[ -f "$G/reframework/plugins/source/WebAPI/index.html" ]; check $? 0 "the WebAPI folder is copied"
"$PY" "$EM" game re "$G" --remove >/dev/null; check $? 0 "remove runs"
[ -e "$G/reframework/plugins/source/TestWebAPI.cs" ]; check $? 1 "the plugin file is gone"
[ -d "$G/reframework/plugins/source/WebAPI" ]; check $? 1 "the folder it made is gone"
[ -f "$G/reframework/plugins/source/keep.cs" ]; check $? 0 "a file that was not ours stays"

# an Unreal game: the plugin goes into UEVR's profile, dumper mode only on request
"$PY" "$EM" game uevr "$T/MyGame-Win64-Shipping.exe" --dumper >/dev/null; check $? 0 "uevr plugin goes in"
P="$T/appdata/UnrealVRMod/MyGame-Win64-Shipping"
[ -f "$P/plugins/uevr_mcp.dll" ] && [ -f "$P/dumper_mode" ]; check $? 0 "dll and dumper_mode are written"
out=$("$PY" "$EM" status); check $? 0 "status runs"
case "$out" in *"dumper mode ON"*) check 0 0 "";; *) check 1 0 "status names dumper mode";; esac
case "$out" in *"RE Engine MCP: installed"*"Not registered"*) check 0 0 "";; *) check 1 0 "status says re is not registered";; esac
"$PY" "$EM" game uevr "$T/MyGame-Win64-Shipping.exe" --remove >/dev/null
[ -e "$P/plugins/uevr_mcp.dll" ] || [ -e "$P/dumper_mode" ]; check $? 1 "remove takes both out"
"$PY" "$EM" game uevr "$T/bad;name.exe" >/dev/null; check $? 1 "an odd program name is refused"

echo "engine-mcp-fixture: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
