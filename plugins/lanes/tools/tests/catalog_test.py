"""catalog_test.py - /lanes:gu's catalog check (0.91.0): a page that should name every tool of ours says when one is
missing or has moved on, with made-up repos in a temporary folder, nothing real. Exit 0 = pass."""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

fails = 0


def check(ok, what):
    global fails
    print(("  ok    " if ok else "FAIL: ") + what)
    fails += not ok


def git(d, *args, when=None):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    if when:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = when
    subprocess.run(["git", "-C", d, *args], check=True, capture_output=True, env=env)


def repo(root, name, files, when="2026-01-01T12:00:00"):
    d = os.path.join(root, name)
    os.makedirs(d)
    git(d, "init", "-q")
    for rel, text in files.items():
        os.makedirs(os.path.dirname(os.path.join(d, rel)) or d, exist_ok=True)
        open(os.path.join(d, rel), "w", encoding="utf-8").write(text)
    git(d, "add", "-A")
    git(d, "commit", "-q", "-m", "first", when=when)
    return d


def main():
    os.environ["LANES_GU_NO_NET"] = "1"
    import gu_texts as gt
    t = tempfile.mkdtemp()
    try:
        kit = repo(t, "kit", {"TOOLKIT.md": "# Tools\n\n### Hand Freeze\n### `pe-inspect.ps1`\n",
                              "tools/pe-inspect.ps1": "x", "tools/send-key.ps1": "x", "tools/README.md": "x"})
        freeze = repo(t, "hand-freeze-vr", {"README.md": "v1"})
        for i in range(gt.CATALOG_STALE_COMMITS):
            open(os.path.join(freeze, "README.md"), "a").write(f"\n{i}")
            git(freeze, "commit", "-qam", f"c{i}", when=f"2026-02-{i + 1:02d}T12:00:00")
        repo(t, "hand-poser-vr", {"README.md": "x"})
        repo(t, "secret-tool", {"README.md": "x"})
        clones = {n: os.path.join(t, n) for n in ("kit", "hand-freeze-vr", "hand-poser-vr", "secret-tool")}
        ours = [os.path.join(t, n) for n in ("kit", "hand-freeze-vr", "hand-poser-vr", "secret-tool")]
        public = {"kit", "hand-freeze-vr", "hand-poser-vr"}
        flags = gt.check_catalog("kit/TOOLKIT.md", clones, ours, ["Hand Poser", "Grab Zones"], public)
        text = "\n".join(flags)
        check("never mentions send-key.ps1" in text, "a tool in tools/ the page never names is flagged")
        check("pe-inspect" not in text, "a tool it names is not")
        check("never mentions Hand Poser" in text and "hand-poser-vr" not in text,
              "an app and its repo are one item, named as the app")
        check("never mentions Grab Zones" in text, "an app installed on a PC, with no repo of its own, is flagged")
        check("secret-tool" not in text, "a private repo is never asked for on the page")
        check("README" not in text, "the tools folder's README is not a tool")
        check(any("hand-freeze-vr had" in f and "commits since" in f for f in flags),
              "a named tool whose repo moved on since the page changed is flagged")
        check(gt.check_catalog("nowhere/TOOLKIT.md", clones, ours, [], public) == [
              "nowhere/TOOLKIT.md: no local clone of nowhere to read it from"], "a page with no clone says so")
    finally:
        shutil.rmtree(t, ignore_errors=True)
    print(f"catalog: {'FAIL' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
