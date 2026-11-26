"""window-scan.py - the release check that keeps black console windows out of Lanes (0.125.1).

Every program Lanes starts must go through tools/hidden.py (see why there). This scan reads every shipped Python file
of the plugin and fails on a process start that does not:
    subprocess.run / Popen / call / check_call / check_output / getoutput / getstatusoutput,
    os.system / os.popen / os.startfile / os.spawn* / os.exec*
A start that must stay as it is carries `# window-ok: <why>` on its line (for example a window meant to be seen).
Tests (tests/ folders, test_*.py, *_test.py) are not shipped to the background and are not scanned.

    python window-scan.py [plugin folder]        exit 0 clean, 1 with the list of places
"""
import ast
import os
import sys

SUB_CALLS = {"run", "Popen", "call", "check_call", "check_output", "getoutput", "getstatusoutput"}
OS_CALLS = {"system", "popen", "startfile"}
OS_PREFIXES = ("spawn", "exec")
MARK = "# window-ok:"
SKIP_DIRS = {".git", "__pycache__", "tests", "node_modules"}


def skipped_file(name):
    return name == "hidden.py" or name.startswith("test_") or name.endswith("_test.py")


def scan_file(path):
    try:
        src = open(path, encoding="utf-8").read()
        tree = ast.parse(src)
    except (OSError, SyntaxError, ValueError) as e:
        return [(0, "could not read: %s" % e)]
    lines = src.splitlines()
    aliases = {"subprocess": "subprocess", "os": "os"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                if n.name in ("subprocess", "os") and n.asname:
                    aliases[n.asname] = n.name
        elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            for n in node.names:
                if n.name in SUB_CALLS:
                    return [(node.lineno, "imports %s from subprocess: use hidden.%s" % (n.name, n.name))]
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)):
            continue
        mod = aliases.get(node.func.value.id)
        attr = node.func.attr
        bad = (mod == "subprocess" and attr in SUB_CALLS) or \
              (mod == "os" and (attr in OS_CALLS or attr.startswith(OS_PREFIXES)))
        if not bad:
            continue
        span = lines[node.lineno - 1:(node.end_lineno or node.lineno)]
        if any(MARK in l for l in span):
            continue
        found.append((node.lineno, "%s.%s outside hidden.py" % (mod, attr)))
    return found


def scan(root):
    out = []
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for f in fn:
            if f.endswith(".py") and not skipped_file(f):
                p = os.path.join(dp, f)
                for line, why in scan_file(p):
                    out.append("%s:%d  %s" % (os.path.relpath(p, root).replace("\\", "/"), line, why))
    return out


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bad = scan(root)
    if bad:
        print("window-scan: %d process start(s) that could open a black window (use hidden.py, or mark the line "
              "'%s <why>'):" % (len(bad), MARK))
        for b in bad:
            print("  " + b)
        sys.exit(1)
    print("window-scan: every process start goes through hidden.py")
