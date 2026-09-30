#!/usr/bin/env python3
"""inspector_summary_test - the end-of-session line counts exactly what happened in THIS session.

Builds a throwaway project, has "session S1" write messy code, answers one note `keep:`, fixes another by
removing it from the code, and checks `session_summary` reports found / fixed / kept / unanswered to the
number, that another session sees none of it, and that a switched-off Inspector says so. Needs git.
"""
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

FAILED, N = 0, 0


def check(ok, what):
    global FAILED, N
    N += 1
    if not ok:
        FAILED += 1
    print(("  ok    " if ok else "  FAIL  ") + what)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    tmp = tempfile.mkdtemp()
    conf = os.path.join(tmp, "lanes.conf")
    os.environ["LANES_CONFIG"] = conf
    os.environ["LANES_INSPECTOR_CACHE"] = os.path.join(tmp, "cache")
    with open(conf, "w") as f:
        f.write("inspector = on\ninspector_mode = end\n")
    import inspector
    from inspector_store import Record

    repo = os.path.join(tmp, "root", "game")
    os.makedirs(os.path.join(repo, "src"))
    for args in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"],
                 ["config", "core.autocrlf", "false"], ["commit", "-q", "--allow-empty", "-m", "start"]):
        subprocess.run(["git", "-C", repo] + args, check=True)

    src = os.path.join(repo, "src", "mod.cpp")
    body = ["int hotkey() { return VK_F5; }",
            "// int a = 1;", "// int b = 2;", "// if (a > b) { a = b; }",
            "// for (int i = 0; i < a; ++i) { b += i; }", "// b = a + b;", "// return b;",
            "int main() { return hotkey(); }"]
    with open(src, "w", newline="\n") as f:
        f.write("\n".join(body) + "\n")
    inspector.check_files([src], session="S1")

    rec = Record(repo)
    kinds = sorted(i["kind"] for i in rec.items.values())
    check(len(kinds) >= 2, f"messy code raised at least two notes ({', '.join(kinds)})")

    # answer the F-key note `keep:`, leave the rest unanswered
    for i in rec.items.values():
        if i["kind"] == "F-KEY":
            i["verdict"] = "keep: the tester's own debug key, never shipped"
    rec.save()

    line = inspector.session_summary("S1")
    found = len(kinds)
    check(f"{found} found" in line and "0 fixed" in line and "1 kept on purpose" in line
          and f"{found - 1} unanswered" in line, f"before any fix: {line}")

    # fix the commented-out code by deleting it
    with open(src, "w", newline="\n") as f:
        f.write("\n".join([body[0], body[-1]]) + "\n")
    inspector.check_files([src], session="S1")
    line = inspector.session_summary("S1")
    check(f"{found} found" in line and "1 fixed" in line and "1 kept on purpose" in line,
          f"after deleting the dead code: {line}")
    check(re.search(r"\(\d+ file edit\(s\) looked over\)", line) is not None, "the edits looked over are counted")

    other = inspector.session_summary("S2")
    check("no code was written" in other, f"another session sees none of it: {other}")

    with open(conf, "w") as f:
        f.write("inspector = off\n")
    off = inspector.session_summary("S1")
    check("off on this PC" in off, f"switched off, it says so: {off}")

    print(f"inspector-summary-test: {N} checks, {FAILED} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
