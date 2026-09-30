"""inspector_checks - the checks the Inspector runs over one source file.

Every check takes the file's repo-relative path and its text, and returns Findings. Nothing here
reads the record file or decides what is new; that is inspector.py's job. Keeping the checks pure
means a baseline (the file as it was at the last commit) and the file as it is now go through the
exact same code, so "new or worse" compares like with like.

The size, loose-number and Lua-locals rules are the ones tools/code-shape-scan.py already enforces
estate-wide (docs/PROTOCOL.md section 6); this module imports its constants rather than restating
them, so the two can never disagree about where the lines are.
"""
import hashlib
import importlib.util
import math
import os
import re
from collections import namedtuple

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("code_shape_scan", os.path.join(_HERE, "code-shape-scan.py"))
shape = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(shape)

# kind, the file, what makes this finding distinct inside the file, how bad it is (bigger is worse),
# a plain sentence, a suggested fix, and up to a few example lines.
Finding = namedtuple("Finding", "kind path detail value what fix examples")

EXAMPLES = 3
LONG_FUNCTION = 120     # lines in one function before it is reported
DEEP_NESTING = 6        # brace / indent levels inside one function before it is reported
COMMENTED_CODE_RUN = 6  # consecutive commented-out code lines before they count as dead code
DUP_WINDOW = 10         # meaningful lines that must match, in order, to count as a copy
DUP_MIN_CHARS = 4       # a line shorter than this (a brace, "end", "else") says nothing about a copy
ADDRESS_MIN_HEX = 6     # hex literals this long are addresses or offsets, not ordinary numbers
ADDRESS_FILE_RE = re.compile(r"addr|offset|pattern|signature|sig|settings|config|constants", re.I)
FKEY_RE = re.compile(r"\b(?:VK|DIK|KEY|SDLK|GLFW_KEY)_F([1-9]|1[0-9]|2[0-4])\b|[\"']F([1-9]|1[0-2])[\"']")
KEYWORD_NEAR_FKEY = re.compile(r"key|hotkey|bind|press|input", re.I)
# Fault 5 (Village review 2026-09-26): a bare `probe()` is often a safety read before a write, and
# "diag(1,-1)" is a matrix. Only names BUILT on the word count: probe_x, x_probe, diag_x, experiment*.
PROBE_RE = re.compile(r"\b(?:probe_\w+|\w+_probe\b|diag_\w+|\w+_diag\b|experiment\w*)", re.I)
# Fault 3: vendored SDKs and libraries are not ours to tidy. A path through one of these folders is
# skipped by every check and by the copy-paste index.
VENDOR_DIRS = {"reframework", "imgui", "minhook", "safetyhook", "glm", "nlohmann", "openvr", "openxr",
               "spdlog", "fmt", "d3dx12", "directxtk", "kiero", "detours", "sdk", "third_party"}
# Faults 6 and 8: tests hold expected values and long step-by-step mains by nature.
TEST_NAME_RE = re.compile(r"(^test_|_test\.|_tests\.|_check\.|_spec\.)", re.I)
TEST_DIRS = {"test", "tests", "spec", "specs"}
# Fault 2: all-bits patterns are "-1" or masks, not addresses.
MASK_RE = re.compile(r"^0x(?:[fF]+|7[fF]+|80+|10+)$")
# Fault 6: small whole numbers and a few universal constants are not hidden settings.
PLAIN_NUMS = {str(i) for i in range(0, 17)} | {"32", "64", "90", "100", "128", "180", "255", "256",
              "360", "1000", "1024", "0.25", "1.5", "3.0", "4.0", "10.0", "100.0", "180.0", "360.0"}
INDEX_RE = re.compile(r"\[[^\[\]]*\]")
# Maths, not settings (bench run 2026-09-26): pi and its multiples, clamps to +-1, and "unset" sentinels
# like -8, -9, -999 that only say "no value yet".
MATH_NUMS = {"3.14159265358979", "3.14159265", "3.14159", "3.1415926", "6.28318530717958", "6.28318",
             "6.2831853", "1.5707963", "1.57079632679", "57.2957795", "0.0174532925", "-1.0", "-1",
             "65504.0", "65504"}  # the largest half-float: a format fact
SENTINEL_RE = re.compile(r"^-(?:8|9|99|999|998|9999)(?:\.0*)?$")
# Fault 6: a line that DECLARES a setting (a global with an initializer, a settings-table row) is the
# fix, not the problem: `std::atomic<float> g_x{0.22f};  // what it is` or `{ "name", K_x, 0.1f },`.
SETTING_DECL_RE = re.compile(
    r"^(?:static\s+|inline\s+|const\s+|constexpr\s+)*(?:std::atomic<[^>]+>|float|double|int|unsigned|"
    r"bool|uint\d+_t|int\d+_t|size_t|auto|local)\s+[A-Za-z_]\w*(?:\[[^\]]*\])?\s*(?:\{|=)"
    r"|^\s*\{\s*\"[^\"]+\"\s*,"
    # Lua/Python names in capitals ARE the named settings: `M.PRIORITY_OFFSET = 0x1c`, `local A, B = 1, 2`.
    r"|^\s*(?:local\s+)?(?:\w+\.)?[A-Z][A-Z0-9_]*(?:\s*,\s*(?:\w+\.)?[A-Z][A-Z0-9_]*)*\s*=[^=]")
# Bench run 4 (2026-09-26): a descriptive name given a bare number, alone on its line, is the setting
# itself: `st.anchor_reach = 0.35` at the top of a block, `start_m = 0.02,` in a settings table.
# Only unindented lines or table fields, so a magic reset deep in logic (`s_hold = 45;`) still counts.
NAMED_LITERAL_RE = re.compile(
    r"^(?:local\s+)?[A-Za-z_][\w.]*\s*=\s*-?[\d.]+(?:e-?\d+)?[fFuUlL]*\s*[;,]?\s*(?:(?://|--|#).*)?$"
    r"|^\s+[A-Za-z_]\w*\s*=\s*-?[\d.]+(?:e-?\d+)?[fFuUlL]*\s*,\s*(?:(?://|--|#).*)?$"
    # replay 2026-09-26: several named fields on one line, `World = 0x80, UpdateFrame = 0xCC, ...`
    r"|^\s*\{?\s*(?:[A-Za-z_]\w*\s*=\s*-?(?:0x[\da-fA-F]+|[\d.]+)[fFuUlL]*\s*,\s*)+"
    r"[A-Za-z_]\w*\s*=\s*-?(?:0x[\da-fA-F]+|[\d.]+)[fFuUlL]*\s*,?\s*\}?\s*[,;]?\s*(?:(?://|--|#).*)?$")
# replay 2026-09-26: an RGB(A) colour, (30, 30, 30) or (200, 40, 40, 255), is not a setting to name.
COLOUR_RE = re.compile(r"\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*(?:,\s*\d{1,3}\s*)?\)")
# A file that is mostly assertions is a test, whatever it is called (e.g. plugin/tools/*_decompose.cpp).
ASSERT_RE = re.compile(r"\b(?:CHECK|ASSERT|EXPECT|REQUIRE)\w*\s*\(|\bassert\s*\(?")
ASSERTS_MAKE_A_TEST = 5
TEST_MAIN_RE = re.compile(r"^\s*int\s+main\s*\(|^if\s+__name__\s*==\s*[\"']__main__[\"']")
# Preprocessor lines (#pragma warning(disable : 4530), #include, #if) hold compiler facts, not settings.
PREPROCESSOR_RE = re.compile(r"^\s*#\s*(?:pragma|include|if|ifdef|ifndef|elif|else|endif|error|line)\b")
HEX_ADDR_RE = re.compile(r"(?<![\w.])0x[0-9a-fA-F]{%d,}\b" % ADDRESS_MIN_HEX)
CODEISH_RE = re.compile(r"[;{}]\s*$|^\s*(if|for|while|return|local|def|auto|int|float|void)\b|\w\s*=\s*\w|\w\(.*\)")
CONTAINER_RE = re.compile(r"\b(?:namespace|extern|class|struct|union|enum)\b[^;{}()]*$|^\s*$")
SIGNATURE_RE = re.compile(r"([~\w:]+)\s*\([^;{}]*\)[^;{}()]*$")
CONTROL_RE = re.compile(r"^(?:if|for|while|switch|catch|do|else|return|sizeof)$")
# A line that only DECLARES or IMPORTS a probe (a forward declaration, an extern, a Lua import line)
# is not where it is wired in; the call and the definition are. Bench run 2026-09-26.
PROBE_REFERENCE_RE = re.compile(
    r"^\s*(?:extern\b|(?:static\s+)?(?:void|bool|int|float)\s+\w+\s*\([^)]*\)\s*;\s*$|local\s+[\w\s,]+=\s*[\w.\s,]+$)")
PROBE_NAME_RE = re.compile(r"probe|diag|experiment|test", re.I)
# Bench judging 2026-09-27 (13 false alarms of 33 LOOSE-NUMS notes). Each rule below removes one shape:
EPSILON_MAX = 0.01          # 0.01 and smaller guard a comparison or a divide; they are not knobs
NEAR_ONE = 1e-3             # -0.999999 is "nearly opposite" in quaternion maths, i.e. -1
MATH_REL_TOL = 1e-6         # how close a literal must be to a pi multiple or a degree factor
MATH_FACTORS = (math.pi / 2, 180.0 / math.pi, math.pi / 180.0)
# Research scripts log, scan and dump by nature; their caps and offsets are not settings.
RESEARCH_NAME_RE = re.compile(r"recon|probe|dump|census|scan", re.I)
# `float quiet_deg = 0.05f` in a signature: the parameter name already names the number.
DEFAULT_PARAM_RE = re.compile(r"\b[A-Za-z_][\w:<>]*\s+[A-Za-z_]\w*\s*=\s*-?[\d.]+[fF]?(?=\s*[,)])")
# `len(parts) >= 20` stays reported: the 2026-09-26 replay judged it a bare limit, and two judgements
# disagreeing is a reason to stay noisy, not to go quiet.
# `shown >= 200`, `lines < 160`: a cap on how much a log prints.
LOG_CAP_RE = re.compile(r"\b(?:shown|printed|logged|lines|dumped)\s*[<>]=?\s*\d+")
# `{ path = "a.rtex", w = 1920, h = 1080 }`: named fields in a data row are named.
TABLE_FIELD_RE = re.compile(r"\b[A-Za-z_]\w*\s*=\s*-?(?:0x[\da-fA-F]+|[\d.]+)[fF]?(?=\s*[,}])")
# Probe plumbing is not wiring (bench judging 2026-09-27): where a probe is defined, where its switch is
# declared or read from the settings file, and a menu entry that only names it. The call is the finding.
PROBE_DEFINITION_RE = re.compile(
    r"^\s*(?:local\s+)?function\s+[\w.:]+\s*\(|^\s*(?:static\s+|inline\s+)*(?:void|bool|int|float)\s+\w+\s*\([^;]*\)\s*\{?\s*$")
PROBE_TABLE_REF_RE = re.compile(r"^\s*[\w.]+\s*=\s*[\w.]+\s*,?\s*(?:--.*|//.*)?$")
SETTINGS_READER_RE = re.compile(r"\bk\s*==\s*\"\w+\"")
C_FAMILY = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".inc", ".hlsl", ".fx", ".cs", ".js",
            ".ts", ".rs", ".go", ".java"}


def is_vendored(rel):
    return bool({p.lower() for p in rel.replace("\\", "/").split("/")[:-1]} & VENDOR_DIRS)


def is_test(rel, lines=None):
    parts = rel.replace("\\", "/").split("/")
    if {p.lower() for p in parts[:-1]} & TEST_DIRS or TEST_NAME_RE.search(parts[-1]):
        return True
    if lines is None:
        return False
    # By content only for a standalone check program: its own main() AND a run of assertions.
    # Working code that merely asserts its inputs is not a test (bench run 4 caught glass_look.cpp
    # and re8_scope_cam_clone.lua being exempted by a looser version of this rule).
    has_main = any(TEST_MAIN_RE.match(l) for l in lines)
    return has_main and sum(1 for l in lines if ASSERT_RE.search(l)) >= ASSERTS_MAKE_A_TEST


def verb(n, v):
    return v + "s" if n == 1 else v


def plural(n):
    return f"{n} line" if n == 1 else f"{n} lines"


def is_source(rel):
    ext = os.path.splitext(rel)[1].lower()
    return ext in shape.SOURCE_EXT


def comment_prefix(ext):
    return shape.COMMENT_PREFIX.get(ext, "//")


def generated(lines):
    return any(shape.GENERATED_RE.search(l) for l in lines[:shape.HEADER_LINES])


def code_lines(lines, ext):
    """Yield (line number, raw line, code with comments and strings removed), skipping block
    comments and Python docstrings the same way code-shape-scan does."""
    in_block = in_doc = False
    for n, raw in enumerate(lines, 1):
        s = raw.strip()
        if ext == ".py" and s.count('"""') % 2 == 1:
            in_doc = not in_doc
            continue
        if in_doc:
            continue
        text = raw
        if ext not in shape.COMMENT_PREFIX:
            if in_block:
                if "*/" not in text:
                    continue
                in_block, text = False, text.split("*/", 1)[1]
            # Fault 4 (2026-09-26): a /* ... */ on a code line was read as code.
            text = re.sub(r"/\*.*?\*/", " ", text)
            if "/*" in text:
                in_block, text = True, text.split("/*", 1)[0]
            if not text.strip():
                continue
        yield n, raw, shape.strip_comment(text, ext)


# ------------------------------------------------------------------ the checks, one per rule

def check_size(rel, lines, ext):
    n = len(lines)
    if n > shape.HARD_LINES:
        return [Finding("OVER-HARD", rel, "", n, f"{n} lines: past {shape.HARD_LINES}, splitting it is the job now.",
                        "Split it move-only on a branch, tagged pre-split-<date>, proven to change nothing (PROTOCOL section 6).", [])]
    if n > shape.SOFT_LINES:
        return [Finding("OVER-SOFT", rel, "", n, f"{n} lines: past {shape.SOFT_LINES}, split before adding more.",
                        "Move a self-contained part (probes, a subsystem) into its own file, move-only.", [])]
    return []


def check_lua_locals(rel, lines, ext):
    if ext != ".lua":
        return []
    count = 0
    for raw in lines:
        if raw.startswith("local "):
            count += 1 if raw.startswith("local function") else raw.split("=", 1)[0].count(",") + 1
    if count < shape.LUA_LOCALS_WARN:
        return []
    return [Finding("LUA-LOCALS", rel, "", count,
                    f"About {count} top-level locals; Lua refuses to load the file at 200.",
                    "Put new state in a table or a module instead of another top-level local.", [])]


def is_plain_number(m):
    """True for a literal that is maths or plumbing rather than a tunable setting."""
    # Hex digits include F: strip a type suffix only from decimal literals (0xFF must stay 0xFF;
    # found by the commit replay, 2026-09-26).
    core = m.rstrip("uUlL") if m.lstrip("-").lower().startswith("0x") else m.rstrip("fFuUlL")
    bare = core.lstrip("-")
    if m in shape.BENIGN_NUMS or bare in PLAIN_NUMS or core in MATH_NUMS or bare in MATH_NUMS:
        return True
    if SENTINEL_RE.match(core):
        return True
    try:
        v = int(bare, 16) if bare.lower().startswith("0x") else float(bare)
    except ValueError:
        return False
    if v != 0 and abs(v) <= EPSILON_MAX:
        return True  # an epsilon or tolerance guards a comparison; it is not a knob
    if abs(abs(v) - 1.0) <= NEAR_ONE:
        return True  # "nearly 1": a unit-length or opposite-direction test
    for k in MATH_FACTORS:
        q = abs(v) / k
        if v != 0 and round(q) >= 1 and abs(q - round(q)) <= MATH_REL_TOL * max(1.0, q):
            return True  # pi, two pi, half pi, degrees <-> radians

    if abs(v) >= 1e5 and "e" in bare.lower():
        return True  # 1e6f: a stand-in for "infinitely large"
    if float(v).is_integer() and str(int(abs(v))) in PLAIN_NUMS:
        return True  # 255.0 is 255
    if float(v).is_integer() and v > 0:
        iv = int(v)
        if iv & (iv - 1) == 0 or (iv + 1) & iv == 0:
            return True  # a power of two or an all-ones mask is a format fact, not a setting
    return False


def loose_number_lines(lines, ext):
    """The lines that carry a number written inline instead of as a named setting."""
    out = []
    for n, raw, code in code_lines(lines, ext):
        if (shape.DEFINITION_RE.match(raw) or SETTING_DECL_RE.match(raw) or NAMED_LITERAL_RE.match(raw)
                or PREPROCESSOR_RE.match(raw)):
            continue
        code = INDEX_RE.sub("[]", code)  # sizes and indices are not settings
        code = re.sub(r"(<<|>>)\s*\d+", r"\1 n", code)  # nor are bit-shift amounts
        code = COLOUR_RE.sub("(colour)", code)  # nor colours
        code = DEFAULT_PARAM_RE.sub("(param)", code)  # nor a parameter's default value
        code = LOG_CAP_RE.sub("(log cap)", code)  # nor how much a log prints
        if "{" in code:
            code = TABLE_FIELD_RE.sub("(field)", code)  # nor a named field in a data row
        hits = [m for m in shape.NUM_RE.findall(code)
                if not is_plain_number(m) and not HEX_ADDR_RE.fullmatch(m.lstrip("-"))]
        if hits:
            out.append((n, raw.strip()))
    return out


def check_loose_numbers(rel, lines, ext):
    if RESEARCH_NAME_RE.search(os.path.basename(rel)):
        return []  # a research script's caps and offsets are not settings
    found = loose_number_lines(lines, ext)
    if not found:
        return []
    return [Finding("LOOSE-NUMS", rel, "", len(found),
                    f"{plural(len(found))} {verb(len(found), 'use')} a number written straight into the code instead of a named setting.",
                    "Give each new number a name in the project's settings table, with a comment, and use the name.",
                    [f"{n}: {s[:90]}" for n, s in found])]


def check_addresses(rel, lines, ext):
    if ADDRESS_FILE_RE.search(os.path.basename(rel)):
        return []  # this IS the address table
    found = []
    for n, raw, code in code_lines(lines, ext):
        if shape.DEFINITION_RE.match(raw):
            continue
        if any(not MASK_RE.match(h) for h in HEX_ADDR_RE.findall(code)):
            found.append((n, raw.strip()))
    if not found:
        return []
    return [Finding("LOOSE-ADDRESS", rel, "", len(found),
                    f"{plural(len(found))} {verb(len(found), 'use')} a raw address or offset outside the address table.",
                    "Addresses belong to one build of the app: declare each once, named, in that build's address table.",
                    [f"{n}: {s[:90]}" for n, s in found])]


def check_fkeys(rel, lines, ext):
    found = []
    for n, raw, code in code_lines(lines, ext):
        m = FKEY_RE.search(raw)
        if m and (m.group(1) or KEYWORD_NEAR_FKEY.search(raw)):
            found.append((n, raw.strip()))
    if not found:
        return []
    return [Finding("F-KEY", rel, "", len(found),
                    f"{plural(len(found))} {verb(len(found), 'bind')} an F-key; games take the F-keys for themselves.",
                    "Use the numpad for mod hotkeys.", [f"{n}: {s[:90]}" for n, s in found])]


def check_probes(rel, lines, ext):
    if PROBE_NAME_RE.search(os.path.basename(rel)):
        return []  # a probe living in its own file is the rule being kept
    found, names = [], []
    for n, raw, code in code_lines(lines, ext):
        hits = PROBE_RE.findall(code)
        if not hits or PROBE_REFERENCE_RE.match(code.strip() if ext == ".lua" else code):
            continue
        if (PROBE_DEFINITION_RE.match(code) or PROBE_TABLE_REF_RE.match(code) or SETTING_DECL_RE.match(raw)
                or SETTINGS_READER_RE.search(raw)):
            continue  # plumbing: the probe is defined, switched or listed here, not run
        found.append((n, raw.strip()))
        names.extend(h for h in hits if h not in names)
    if not found:
        return []
    shown = ", ".join(names[:4]) + (" ..." if len(names) > 4 else "")
    return [Finding("PROBE-WIRED", rel, "", len(found),
                    f"{plural(len(found))} of probe or diagnostic code {verb(len(found), 'sit')} in the working file ({shown}).",
                    "Move each probe to its own file behind a named switch; once it has answered its question, archive it.",
                    [f"{n}: {s[:90]}" for n, s in found])]


def check_commented_code(rel, lines, ext):
    prefix = comment_prefix(ext)
    runs, run = [], []
    for n, raw in enumerate(lines, 1):
        s = raw.strip()
        body = s[len(prefix):].strip() if s.startswith(prefix) else None
        if body is not None and CODEISH_RE.search(body):
            run.append(n)
            continue
        if len(run) >= COMMENTED_CODE_RUN:
            runs.append(run)
        run = []
    if len(run) >= COMMENTED_CODE_RUN:
        runs.append(run)
    if not runs:
        return []
    total = sum(len(r) for r in runs)
    return [Finding("DEAD-CODE", rel, "", total,
                    f"{plural(total)} of commented-out code in {len(runs)} block(s).",
                    "Delete it; git keeps the history. If it is a switchable alternative, make it a named switch instead.",
                    [f"lines {r[0]}-{r[-1]}" for r in runs])]


def functions(lines, ext):
    """(name, first line, length, deepest nesting) for each function, by the file's own shape."""
    out = []
    if ext in C_FAMILY:
        # A stack of what each open brace belongs to. Namespaces, extern "C" and class bodies are
        # containers: a function can start inside one, and they do not count as nesting.
        stack, start, name, deepest, head = [], None, "", 0, ""
        for n, raw, code in code_lines(lines, ext):
            code = shape.STRING_RE.sub('""', code)
            if code.lstrip().startswith("#"):
                continue  # preprocessor lines, including macros full of braces
            for ch in code + " ":
                if ch == "{":
                    if start is None and CONTAINER_RE.search(head):
                        stack.append("container")
                    elif start is None and all(k == "container" for k in stack):
                        m = SIGNATURE_RE.search(head)
                        stack.append("func" if m and not CONTROL_RE.match(m.group(1)) else "block")
                        if stack[-1] == "func":
                            start, name, deepest = n, m.group(1), 1
                    else:
                        stack.append("block")
                        if start is not None:
                            deepest = max(deepest, sum(1 for k in stack if k != "container"))
                    head = ""
                elif ch == "}":
                    if stack and stack.pop() == "func":
                        out.append((name, start, n - start + 1, deepest))
                        start = None
                    head = ""
                elif ch == ";":
                    head = ""
                else:
                    head = (head + ch)[-300:]
    elif ext in (".py", ".lua"):
        opener = re.compile(r"^(\s*)(?:async\s+)?def\s+(\w+)" if ext == ".py"
                            else r"^(\s*)(?:local\s+)?function\s+([\w.:]+)")
        stack = []  # [indent, name, start, deepest]
        unit, brackets = indent_unit(lines), 0
        for n, raw, code in list(code_lines(lines, ext)) + [(len(lines) + 1, "<eof>", "<eof>")]:
            inside, brackets = brackets > 0, max(0, brackets + bracket_delta(code))
            if not raw.strip() or inside:
                continue  # a continuation line is aligned for reading, not nested
            indent = len(raw) - len(raw.lstrip())
            closes = ext == ".lua" and raw.strip() == "end"
            while stack and (indent < stack[-1][0] or (indent == stack[-1][0] and (ext == ".py" or closes))):
                ind, name, start, deepest = stack.pop()
                end = n if closes and indent == ind else n - 1
                out.append((name, start, end - start + 1, deepest))
                if closes and indent == ind:
                    break
            for item in stack:
                levels = (indent - item[0]) // unit
                item[3] = max(item[3], levels)
            m = opener.match(raw)
            if m and not (ext == ".lua" and lua_closes_on_line(code)):
                stack.append([len(m.group(1)), m.group(2), n, 0])
    return out


def lua_closes_on_line(code):
    """Fault 1 (2026-09-26): `local function f() return x end` opens and closes on one line."""
    code = shape.STRING_RE.sub('""', code)
    opens = len(re.findall(r"\bfunction\b|\bdo\b|\bif\b|\brepeat\b", code))
    closes = len(re.findall(r"\bend\b|\buntil\b", code))
    return closes >= opens


def indent_unit(lines):
    """The file's own indent step: the most common increase from one line to the next."""
    steps, prev = {}, 0
    for l in lines:
        if not l.strip():
            continue
        ind = len(l) - len(l.lstrip())
        if ind > prev:
            steps[ind - prev] = steps.get(ind - prev, 0) + 1
        prev = ind
    return max(steps, key=steps.get) if steps else 4


def bracket_delta(code):
    code = shape.STRING_RE.sub('""', code)
    return sum(code.count(c) for c in "([{") - sum(code.count(c) for c in ")]}")


def check_functions(rel, lines, ext):
    out = []
    for name, start, length, deepest in functions(lines, ext):
        if length > LONG_FUNCTION:
            out.append(Finding("LONG-FUNCTION", rel, name, length,
                               f"{name}() at line {start} is {length} lines long.",
                               "Pull its separate jobs out into named helpers so each can be read on one screen.", []))
        if deepest >= DEEP_NESTING:
            out.append(Finding("DEEP-NESTING", rel, name, deepest,
                               f"{name}() at line {start} nests {deepest} levels deep.",
                               "Return early, or move the inner loop or branch into a named helper.", []))
    return out


CHECKS = (check_size, check_lua_locals, check_loose_numbers, check_addresses, check_fkeys,
          check_probes, check_commented_code, check_functions)


TEST_EXEMPT = (check_loose_numbers, check_addresses, check_functions)


def inspect_text(rel, text):
    """Every finding for one file, except duplication, which needs the other files too."""
    ext = os.path.splitext(rel)[1].lower()
    lines = text.splitlines()
    if generated(lines) or is_vendored(rel):
        return []
    checks = CHECKS
    if is_test(rel, lines):  # fault 8: tests keep the size, copy, probe, F-key and dead-code checks
        checks = tuple(c for c in CHECKS if c not in TEST_EXEMPT)
    out = []
    for check in checks:
        out.extend(check(rel, lines, ext))
    return out


# ------------------------------------------------------------------ copy-paste across files

def _meaningful(text, ext):
    out = []
    for n, raw, code in code_lines(text.splitlines(), ext):
        norm = re.sub(r"\s+", " ", code).strip()
        if len(norm) >= DUP_MIN_CHARS:
            out.append((n, norm))
    return out


def windows(text, ext):
    """{hash of DUP_WINDOW consecutive meaningful lines: first line number}."""
    lines = _meaningful(text, ext)
    out = {}
    for i in range(len(lines) - DUP_WINDOW + 1):
        chunk = "\n".join(l for _, l in lines[i:i + DUP_WINDOW])
        out.setdefault(hashlib.sha1(chunk.encode("utf-8", "replace")).hexdigest()[:16], lines[i][0])
    return out


def check_duplicates(rel, text, index):
    """index: {window hash: ['repo/path', ...]} across the files. One finding per file copied from."""
    ext = os.path.splitext(rel)[1].lower()
    per_other = {}
    for h, line in windows(text, ext).items():
        other = next((o for o in index.get(h, ()) if o != rel), None)
        if other:
            per_other.setdefault(other, []).append(line)
    out = []
    for other, starts in sorted(per_other.items()):
        span = len(starts) + DUP_WINDOW - 1
        research = RESEARCH_NAME_RE.search(os.path.basename(rel)) and             RESEARCH_NAME_RE.search(os.path.basename(other))
        fix = ("Both are research scripts: once a script has answered its question, archive it (an archive/ "
               "folder with a README line) rather than sharing code between them." if research else
               "If it is a shared helper, keep one copy and use it from both places.")
        out.append(Finding("DUPLICATE", rel, other, span,
                           f"About {span} lines match {other}, starting at line {min(starts)}.",
                           fix,
                           [f"from line {min(starts)}"]))
    return out
