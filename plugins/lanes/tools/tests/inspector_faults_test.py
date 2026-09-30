"""inspector_faults_test.py - one check per fault found in the first RE Village review (2026-09-26).

Each case is a small made-up file, never game code. Every fault gets a "no longer raised" check AND
a "still raised when it should be" check, so a fix cannot pass by switching a check off.
    python tools/tests/inspector_faults_test.py      (exit 0 = all passed)
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ["LANES_CONFIG"] = os.path.join(tempfile.mkdtemp(), "lanes.conf")
open(os.environ["LANES_CONFIG"], "w").close()
os.environ["LANES_INSPECTOR_CACHE"] = tempfile.mkdtemp()
import inspector as I  # noqa: E402
import inspector_checks as ic  # noqa: E402

N = FAILED = 0


def check(ok, text):
    global N, FAILED
    N += 1
    if not ok:
        FAILED += 1
    print(("  ok    " if ok else "  FAIL  ") + text)


def kinds(rel, text):
    return [f.kind for f in ic.inspect_text(rel, text)]


filler = "\n".join(f"x{i} = x{i - 1} + 1" for i in range(1, 200))

print("fault 1: one-line Lua functions")
lua = "local function go_of(c) return c ~= nil and safe(function() return c end) or nil end\n" + filler + "\n"
check("LONG-FUNCTION" not in kinds("s/a.lua", lua), "a one-line function is not read as 200 lines long")
long_lua = "local function big()\n" + "\n".join(f"    y{i} = {i}" for i in range(150)) + "\nend\n"
check("LONG-FUNCTION" in kinds("s/b.lua", long_lua), "a real 150-line Lua function is still raised")

print("fault 2: masks are not addresses")
check("LOOSE-ADDRESS" not in kinds("s/c.cpp", "void f() { write(OFF, 0xFFFFFFFF); }\n"), "0xFFFFFFFF is not an address")
check("LOOSE-ADDRESS" in kinds("s/c.cpp", "void f() { call(0x14A2B3C40); }\n"), "a real address is still raised")

print("fault 3: vendored SDK code")
bad = "void f() { if (GetAsyncKeyState(VK_F9)) { call(0x14A2B3C40); } }\n" * 3
check(kinds("plugin/include/reframework/API.hpp", bad) == [], "a file in a vendored SDK folder is skipped")
check(kinds("plugin/src/mine.cpp", bad) != [], "the same code in our own folder is still inspected")

print("fault 4: /* */ comments on a code line")
check("PROBE-WIRED" not in kinds("s/d.h", "float roll;   /* rotation against diag_base(1,-1) */\n"),
      "a word inside /* */ is not code")
check("LOOSE-NUMS" not in kinds("s/d.cpp", "void f() { g(a); /* 3.75 metres */ }\n"), "a number inside /* */ is not code")
check("LOOSE-NUMS" in kinds("s/d.cpp", "void f() { g(a * 3.75f); /* note */ }\n"), "a number before the comment still counts")

print("fault 5: probe as a word")
check("PROBE-WIRED" not in kinds("s/e.lua", "local function probe()\n  return true\nend\nif not probe() then return end\n"),
      "a bare probe() safety read is not research code")
check("PROBE-WIRED" in kinds("s/e.lua", "local function f()\n  probe_sky_layers()\nend\n"),
      "a named research probe is still raised")

print("fault 6: settings, sizes and indices are not loose numbers")
decl = "std::atomic<float> g_tm_m{0.22f};           // LinearSectionBegin\n"
check("LOOSE-NUMS" not in kinds("s/f.cpp", decl), "a declared setting with a comment is the fix, not the problem")
check("LOOSE-NUMS" not in kinds("s/f.cpp", '    { "glass_aspect", bootv::K_glass_aspect,  0.1f   },\n'),
      "a settings-table row is not a loose number")
check("LOOSE-NUMS" not in kinds("s/f.cpp", "void f() { float m[16]; v = m[12] * r.x[3]; }\n"),
      "array sizes and indices are not settings")
check("LOOSE-NUMS" in kinds("s/f.cpp", "void f() { if ((tick++ % 72) == 0) log(); }\n"),
      "a log cadence written inline is still raised")

print("fault 7: a copy between two files is ONE finding")
tmp = tempfile.mkdtemp()
repo = os.path.join(tmp, "proj")
os.makedirs(os.path.join(repo, "src"))
body = "\n".join(f"float helper_{i}(float a) {{ return a * k_scale + offset_{i}; }}" for i in range(14)) + "\n"
for name in ("one.cpp", "two.cpp"):
    with open(os.path.join(repo, "src", name), "w", newline="\n") as fh:
        fh.write(body)
for cmd in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"], ["add", "-A"],
            ["commit", "-qm", "init"]):
    subprocess.run(["git", "-C", repo] + cmd, check=True, capture_output=True)
I.check_files([os.path.join(repo, "src", n) for n in ("one.cpp", "two.cpp")], baseline=False)
dups = [i for i in I.Record(repo).items.values() if i["kind"] == "DUPLICATE"]
check(len(dups) == 1, f"two copied files give one DUPLICATE, not two (got {len(dups)})")

print("fault 8: tests have their own rules")
test_main = "int main() {\n" + "\n".join(f"    expect(f({i}.5f) == {i * 3}.25f);" for i in range(160)) + "\n}\n"
k = kinds("plugin/tools/geom_test.cpp", test_main)
check("LONG-FUNCTION" not in k and "LOOSE-NUMS" not in k, "a long test main full of expected values is left alone")
k = kinds("plugin/tools/geom_test.cpp", test_main + "void t() { if (GetAsyncKeyState(VK_F9)) {} }\n")
check("F-KEY" in k, "a test still gets the F-key check")
check("LONG-FUNCTION" in kinds("plugin/src/geom.cpp", test_main), "the same long function outside tests is raised")

print("bench weak spot 1: maths is not a setting")
for line, why in (("    return acosf(d) * (180.0f / 3.14159265358979f);\n", "pi"),
                  ("    if (w < 1e-4f) return false;\n", "an epsilon"),
                  ("    v = clamp(-1.0f, 1.0f, dot(a, b));\n", "a clamp to +-1"),
                  ("    if (v > -8.0f) g_mode.store(v > 0.5f ? 1 : 0);\n", "an 'unset' sentinel"),
                  ("    b = dec((v >> 22) & 0x3FF) / 1024.0f;\n", "a mask and a power of two")):
    check("LOOSE-NUMS" not in kinds("s/g.cpp", "void f() {\n" + line + "}\n"), f"{why} is not reported")
for line, why in (("    if (WaitForSingleObject(ev, 2000) != 0) return;\n", "a 2000 ms timeout"),
                  ("    if ((tm_tick++ % 30) == 0) log();\n", "a log cadence"),
                  ("    if (d->Width == 1280) return d->Height >= 700;\n", "a resolution check"),
                  ("    if (nx < -2.0f || nx > 2.5f) return false;\n", "a range limit")):
    check("LOOSE-NUMS" in kinds("s/g.cpp", "void f() {\n" + line + "}\n"), f"{why} is still reported")

check("LOOSE-NUMS" not in kinds("s/g.lua", "M.PRIORITY_OFFSET = 0x1c   -- the priority dword\n"),
      "a module constant in capitals is a named setting")
check("LOOSE-NUMS" not in kinds("s/g.lua", "local GO_UPDATE, GO_DRAW = 0x12, 0x13\n"),
      "several capital names declared together are named settings")
check("LOOSE-NUMS" in kinds("s/g.lua", "local function f()\n  st.lens_radius = 0.039\nend\n"),
      "a lower-case assignment of a bare number is still reported")

print("bench run 4: the last noise in the number notes")
for text, why in (("st.anchor_reach = 0.35\n", "a name given its number at the top of a block"),
                  ("local RAY = {\n    start_m   = 0.02,    -- just ahead of the muzzle\n}\n", "a settings-table field"),
                  ("void f() { r = g / 255.0f; }\n", "255.0 (a whole plain number written as a float)"),
                  ("void f() { s = (d > 1e-6f) ? a / d : 1e6f; }\n", "a 1e6 stand-in for infinity"),
                  ("void f() { if (fabs(a - b) <= 0.001) ok(); }\n", "a 0.001 tolerance")):
    check("LOOSE-NUMS" not in kinds("s/j" + (".lua" if "--" in text or text.startswith("st.") else ".cpp"), text),
          f"{why} is not reported")
check("LOOSE-NUMS" in kinds("s/j.cpp", "void f() {\n    if (jump) {\n        s_hold = 45;\n    }\n}\n"),
      "a magic reset inside logic (s_hold = 45;) is still reported")
check("LOOSE-NUMS" in kinds("s/j.cpp", "void f() { if (now - last < 500) return; }\n"),
      "a 500 ms interval is still reported")
checks_tool = "int main() {\n" + "\n".join(f"    CHECK(f({i}.5) < 0.{i + 1}5, \"step\");" for i in range(8)) + "\n}\n"
check("LOOSE-NUMS" not in kinds("plugin/tools/crop_centre_decompose.cpp", checks_tool),
      "a file full of CHECK(...) is a test even when its name does not say so")
check("LOOSE-NUMS" in kinds("plugin/src/crop.cpp", "void f() { x = y * 0.37f; CHECK(x); }\n"),
      "one CHECK in working code does not make it a test")
asserting = "void apply() {\n" + "\n".join(f"    assert(p{i} != nullptr); use(p{i});" for i in range(130)) + "\n}\n"
check("LONG-FUNCTION" in kinds("plugin/src/glass_look.cpp", asserting),
      "working code full of assert() but with no main() is NOT a test (regression caught on the bench)")
check("LOOSE-NUMS" not in kinds("s/k.cpp", "#pragma warning(disable : 4530)\nvoid f() {}\n"),
      "a compiler #pragma is not a setting")
check("LOOSE-NUMS" not in kinds("s/k.cpp", "void f() { if (e == 31) return 65504.0f; }\n"),
      "the largest half-float is a format fact")

print("replay of 40 real commits: colours, named-field lines, and asking again")
check("LOOSE-NUMS" not in kinds("s/m.py", "def f():\n    img = new('RGB', (w, h), (30, 30, 30))\n"),
      "an RGB colour is not a setting")
check("LOOSE-NUMS" not in kinds("s/m.lua", "local OFF = {\n    World = 0x80, UpdateFrame = 0xCC, DirtySelf = 0xD1,\n}\n"),
      "several named fields on one line are named")
check("LOOSE-NUMS" in kinds("s/m.py", "def f():\n    if len(parts) >= 20:\n        pass\n"),
      "a bare limit next to them is still reported")
check("LOOSE-NUMS" not in kinds("s/m.cpp", "void f() { b = ((v >> 8) & 0xFF) / 255.0f; }\n"),
      "0xFF keeps its F digits (a hex literal is not a float with an f suffix)")
check(ic.is_plain_number("0xFF") and not ic.is_plain_number("0xCD"), "0xFF is a mask; 0xCD is a value")
check("LOOSE-NUMS" not in kinds("s/m.lua", "local F = {\n  World = 0x80, UpdateFrame = 0xCC, DirtySelf = 0xD1 }\n"),
      "a line of named fields that closes its table is still named")
check(not I.worse("LONG-FUNCTION", 301, 303), "a kept long function growing 2 lines is NOT raised again")
check(not I.worse("LONG-FUNCTION", 293, 310), "17 lines of growth is not yet a real step")
check(I.worse("LONG-FUNCTION", 293, 342), "49 lines (+17%) is raised again")
check(not I.worse("OVER-SOFT", 918, 963), "a big file growing 5% is not raised again")
check(I.worse("LOOSE-NUMS", 3, 4), "a NEW bare number after a keep is still raised (count kinds stay strict)")
check(I.worse("F-KEY", 1, 2), "a new F-key after a keep is still raised")

print("bench weak spot 2: a probe is reported where it is wired, not where it is declared")
check("PROBE-WIRED" not in kinds("s/h.cpp", "void spread_probe();\nextern std::atomic<int> g_hold_diag;\n"),
      "a forward declaration and an extern are not wiring")
check("PROBE-WIRED" not in kinds("s/h.lua", "local bind_glass, rx_probe = _probes.bind_glass, _probes.rx_probe\n"),
      "a Lua import line is not wiring")
calls = kinds("s/h.cpp", "void tick() {\n    if (g_req.exchange(false)) spread_probe();\n}\n")
check("PROBE-WIRED" in calls, "a probe CALLED in the working path is still reported")
f = [x for x in ic.inspect_text("s/h.cpp", "void t() { spread_probe(); diag_dump(); }\n") if x.kind == "PROBE-WIRED"]
check(bool(f) and "spread_probe" in f[0].what and "diag_dump" in f[0].what, "the finding names the probes it saw")

print("bench judging 2026-09-27: the shapes of the 13 false alarms")
check("LOOSE-NUMS" not in kinds("s/n.h", "void f() { while (d > 3.14159265f) d -= 6.28318531f; }\n"),
      "pi and two pi written to eight places are maths")
check("LOOSE-NUMS" not in kinds("s/n.cpp", "float f(float r) { return r * 57.29577951308232f; }\n"),
      "radians to degrees is maths")
check("LOOSE-NUMS" not in kinds("s/n.h", "int f(float z) { if (z >= -0.01f) return 0; return 1; }\n"),
      "a 0.01 guard is an epsilon")
check("LOOSE-NUMS" in kinds("s/n.h", "int f(float z) { if (z >= -0.02f) return 0; return 1; }\n"),
      "0.02 is still reported (the epsilon line stays at 0.01)")
check("LOOSE-NUMS" not in kinds("s/n.lua", "local function f(d)\n  if d < -0.999999 then return 1 end\nend\n"),
      "nearly -1 is a direction test")
check("LOOSE-NUMS" not in kinds("s/n.h", "inline float g(const A& a, float quiet_deg = 0.05f) { return a.x; }\n"),
      "a parameter's default value is named by the parameter")
check("LOOSE-NUMS" in kinds("s/n.h", "inline float g(const A& a) { return a.x * 0.05f; }\n"),
      "the same number inside the body is still reported")
check("LOOSE-NUMS" not in kinds("s/n.lua", "local function f()\n  if shown > 120 then L('capped') end\nend\n"),
      "a cap on how much a log prints is not a setting")
check("LOOSE-NUMS" not in kinds("s/n.lua", "local T = {\n  { path = 'a.rtex', w = 1920, h = 1080 },\n}\n"),
      "named fields in a data row are named")
check("LOOSE-NUMS" not in kinds("s/re8_scope_m3_recon.lua", "local function f()\n  for off = 0, 0x3fc, 4 do x(off * 48) end\nend\n"),
      "a recon script's scan ranges are not settings")
check("LOOSE-NUMS" in kinds("s/re8_scope_pose.lua", "local function f()\n  st.off_f = 1.0 * g(0.715)\nend\n"),
      "a working script's tuned offsets are still reported")
check("PROBE-WIRED" not in kinds("s/p.lua", "local function probe_sky_layers()\n  return 1\nend\n"),
      "where a probe is defined is not where it is wired")
check("PROBE-WIRED" not in kinds("s/p.lua", "local M = {\n    probe_rtex = rx_probe,\n}\n"),
      "a menu entry that only names a probe is not wiring")
check("PROBE-WIRED" not in kinds("s/p.cpp", "void load() {\n    if (k == \"hold_diag\") g_hold_diag.store(1);\n}\n"),
      "the settings reader that switches a probe is not wiring")
check("PROBE-WIRED" in kinds("s/p.lua", "local function attach()\n  dump_type_api('x')\n  probe_sky_layers()\nend\n"),
      "a probe run on every attach is still reported")
copy = "\n".join(f"line_{i} = call_{i}(x)" for i in range(12))
d = ic.check_duplicates("r/re8_a_recon2.lua", copy, {h: ["r/re8_a_recon3.lua"] for h in ic.windows(copy, ".lua")})
check(bool(d) and "archive" in d[0].fix, "copies between research scripts suggest archiving, not sharing")
d = ic.check_duplicates("r/steer.lua", copy, {h: ["r/pose.lua"] for h in ic.windows(copy, ".lua")})
check(bool(d) and "shared helper" in d[0].fix, "copies between working scripts still suggest one shared helper")

print(f"inspector-faults-test: {N} checks, {FAILED} failed")
sys.exit(1 if FAILED else 0)
