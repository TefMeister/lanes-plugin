#!/usr/bin/env python3
"""code-shape-scan - flag source files that have grown too big, and numbers left loose in the code.

WHY THIS EXISTS (2026-09-17)
  The board checks look at the RECORDS (tags, inboxes, OPEN blocks). Nothing looked at the CODE's
  shape, and three hand-written files on one estate had quietly reached 5,600-6,800 lines. One of
  them was a Lua script sitting at exactly 200 top-level locals - the language's hard limit - so
  the next session to add one `local` would have broken the mod at load time with no warning.
  Sessions add a dated block per pass and nothing ever takes the superseded ones out; a scan is
  the only thing that notices the total. See docs/PROTOCOL.md section 6.

WHAT IT REPORTS (read-only; always exits 0 unless the arguments are wrong)
  OVER-HARD  a hand-written file past HARD_LINES: split it before adding anything else
  OVER-SOFT  past SOFT_LINES: the next session that edits it should split first
  LUA-LOCALS a Lua file close to Lua's 200-locals-per-function limit at top level
  LOOSE-NUMS a file with many numeric literals written inline instead of as named settings

USAGE
  python3 code-shape-scan.py [ROOT ...]          scan every git repo under each ROOT (default: .)
  python3 code-shape-scan.py --soft 800 --hard 1500 --nums 40 ROOT

  Only tracked files are scanned. A repo can exclude paths with a `.code-shape-ignore` file at its
  root (one fnmatch pattern per line, # for comments). Files that say they are generated in their
  first lines are skipped - fix the generator, not its output.
"""
import argparse
import fnmatch
import os
import re
import subprocess
import sys

SOFT_LINES = 800      # past this, split before the next feature goes in
HARD_LINES = 1500     # past this, splitting is the job
LOOSE_NUMS = 40       # inline numeric literals per file before it is reported
LUA_LOCALS_WARN = 150  # Lua allows 200 locals per function; the main chunk counts as one
HEADER_LINES = 15     # how far down a "generated" marker may sit
EXAMPLES = 3          # example lines shown per LOOSE-NUMS file
LOOSE_NUMS_SHOWN = 10  # worst LOOSE-NUMS files listed unless --all

SOURCE_EXT = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".inc", ".lua", ".py", ".ps1",
              ".sh", ".hlsl", ".fx", ".cs", ".js", ".ts", ".rs", ".go", ".java"}
SKIP_DIR_PARTS = {"third_party", "thirdparty", "vendor", "external", "extern", "deps",
                  "node_modules", "archive", "snapshots", "restore_points", "history", "sdk",
                  "build", "dist", "out", ".git"}
GENERATED_RE = re.compile(r"generated|do not edit|auto-?generated", re.I)
# Numbers that are almost never a hidden setting.
BENIGN_NUMS = {"0", "1", "2", "-1", "0.0", "1.0", "0.5", "2.0", "0f", "1f", "0.0f", "1.0f", "0.5f",
               "0x0", "0x1", "0u", "1u"}
NUM_RE = re.compile(r"(?<![\w.])-?(?:0x[0-9a-fA-F]+|\d+\.\d*(?:[eE][-+]?\d+)?f?|\.\d+f?|\d+(?:[eE][-+]?\d+)?[uUlLf]*)(?![\w.])")
# A line that NAMES a number is the fix, not the problem.
DEFINITION_RE = re.compile(
    r"^\s*(#\s*define\b|(static\s+)?(inline\s+)?(const|constexpr)\b|enum\b|"
    r"local\s+[A-Z][A-Z0-9_]*\s*=|[A-Z][A-Z0-9_]*\s*[:=]|\.set\s|readonly\s)")
COMMENT_PREFIX = {".lua": "--", ".py": "#", ".sh": "#", ".ps1": "#"}
STRING_RE = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')


def git_repos(root):
    root = os.path.abspath(root)
    if os.path.exists(os.path.join(root, ".git")):  # a worktree has a .git FILE
        yield root
        return
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if os.path.exists(os.path.join(path, ".git")):
            yield path


def tracked_files(repo):
    try:
        out = subprocess.run(["git", "-C", repo, "ls-files"], capture_output=True, text=True,
                             check=True, encoding="utf-8", errors="replace").stdout
    except (OSError, subprocess.CalledProcessError):
        return []
    return [line for line in out.splitlines() if line]


def ignore_patterns(repo):
    path = os.path.join(repo, ".code-shape-ignore")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8", errors="replace") as f:
        return [l.strip() for l in f if l.strip() and not l.lstrip().startswith("#")]


def skipped(rel, patterns):
    parts = {p.lower() for p in rel.replace("\\", "/").split("/")[:-1]}
    if parts & SKIP_DIR_PARTS:
        return True
    return any(fnmatch.fnmatch(rel, p) for p in patterns)


def strip_comment(line, ext):
    prefix = COMMENT_PREFIX.get(ext, "//")
    line = STRING_RE.sub('""', line)
    cut = line.find(prefix)
    return line if cut < 0 else line[:cut]


def scan_file(path, ext):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    if any(GENERATED_RE.search(l) for l in lines[:HEADER_LINES]):
        return None
    loose, examples, lua_locals, in_block, in_doc = 0, [], 0, False, False
    for n, raw in enumerate(lines, 1):
        s = raw.strip()
        if ext == ".py" and s.count('"""') % 2 == 1:  # docstring boundaries
            in_doc = not in_doc
            continue
        if in_doc:
            continue
        if ext not in COMMENT_PREFIX:  # C-family block comments
            if in_block:
                if "*/" in s:
                    in_block = False
                continue
            if s.startswith("/*") and "*/" not in s:
                in_block = True
                continue
        if ext == ".lua" and raw.startswith("local "):
            names = raw.split("=", 1)[0]  # only the names being declared, not commas in the value
            lua_locals += 1 if raw.startswith("local function") else names.count(",") + 1
        if DEFINITION_RE.match(raw):
            continue
        code = strip_comment(raw, ext)
        hits = [m for m in NUM_RE.findall(code) if m not in BENIGN_NUMS]
        if hits:
            loose += len(hits)
            if len(examples) < EXAMPLES:
                examples.append(f"{n}: {s[:90]}")
    return len(lines), loose, examples, lua_locals


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("roots", nargs="*", default=["."])
    ap.add_argument("--soft", type=int, default=SOFT_LINES)
    ap.add_argument("--hard", type=int, default=HARD_LINES)
    ap.add_argument("--nums", type=int, default=LOOSE_NUMS)
    ap.add_argument("--all", action="store_true", help="list every LOOSE-NUMS file, not just the worst")
    args = ap.parse_args()

    rows = []
    for root in args.roots:
        if not os.path.isdir(root):
            print(f"code-shape-scan: not a directory: {root}", file=sys.stderr)
            return 2
        for repo in git_repos(root):
            patterns = ignore_patterns(repo)
            for rel in tracked_files(repo):
                ext = os.path.splitext(rel)[1].lower()
                if ext not in SOURCE_EXT or skipped(rel, patterns):
                    continue
                res = scan_file(os.path.join(repo, rel), ext)
                if not res:
                    continue
                lines, loose, examples, lua_locals = res
                name = f"{os.path.basename(repo)}/{rel}"
                if lines > args.hard:
                    rows.append(("OVER-HARD", lines, name, []))
                elif lines > args.soft:
                    rows.append(("OVER-SOFT", lines, name, []))
                if lua_locals >= LUA_LOCALS_WARN:
                    rows.append(("LUA-LOCALS", lua_locals, name, ["estimated top-level locals (luac -l -l gives the exact count); Lua stops loading at 200"]))
                if loose >= args.nums:
                    rows.append(("LOOSE-NUMS", loose, name, examples))

    order = {"LUA-LOCALS": 0, "OVER-HARD": 1, "OVER-SOFT": 2, "LOOSE-NUMS": 3}
    rows.sort(key=lambda r: (order[r[0]], -r[1]))
    counts = {k: sum(1 for r in rows if r[0] == k) for k in order}
    print(f"code-shape-scan: {counts['LUA-LOCALS']} near the Lua locals limit, {counts['OVER-HARD']} over "
          f"{args.hard} lines, {counts['OVER-SOFT']} over {args.soft}, {counts['LOOSE-NUMS']} with "
          f">= {args.nums} loose numbers")
    shown_nums = 0
    for kind, value, name, notes in rows:
        if kind == "LOOSE-NUMS":
            shown_nums += 1
            if shown_nums > LOOSE_NUMS_SHOWN and not args.all:
                continue
        print(f"  {kind:<10} {value:>6}  {name}")
        for note in notes:
            print(f"               {note}")
    if shown_nums > LOOSE_NUMS_SHOWN and not args.all:
        print(f"  ... and {shown_nums - LOOSE_NUMS_SHOWN} more LOOSE-NUMS files (--all lists them)")
    if not rows:
        print("  clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
