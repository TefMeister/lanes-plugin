#!/usr/bin/env python3
"""od.py - /lanes:od, Out of Date: is everything we published on GitHub as new as the work behind it? (0.94.0, 2026-10-27)

Asked for by the maintainer: "a slash command now actually, that scans if something is out of date across our github
... it must run before /gu ... and then add this function to the /fullscan as well so our github will always be shiny
and has the latest stuff". It came out of one afternoon: Hand Freeze's download was still v3.2 while v4 had been
worn in a game, three apps had no download at all, and the skills page was 67 days old. Looks only; the session fixes.

  1. DOWNLOADS BEHIND THE WORK: one of our public tools (`ours =`) whose program changed after its newest release.
     Notes, docs, tests and ideas do not count, only what goes into the download.
  2. TOOLS WITH NO DOWNLOAD: an app or add-on of ours (it has install.ps1, build.bat or a dist/*.zip) with no release
     at all; a library with no one-zip download link on its front page (archive/refs/heads/main.zip).
  3. TEXTS ON GITHUB: descriptions and front pages behind the work, and catalog pages missing a tool (gu_texts.py,
     /gu section 5 until 0.94.0).
  4. LANES AND THE SKILLS PAGE: a public tool of ours Lanes does not offer, a connector the skills page never names
     (/gu section 6 until 0.94.0).

    python od.py scan [--json]

Settings in lanes.conf: ours, texts, texts_owner, catalog, skills, skills_skip, lanes_skip, od_skip (a repo whose
downloads /od leaves alone). Never commits, never publishes. Tests: the gu.py variables plus LANES_GU_FAKE_REPOS
(entries may carry "latestRelease" or "releases").
"""
import json
import os
import subprocess
import sys

import gu
import gu_texts

GIT_TIMEOUT_S = 60
# what is not part of a download: a change here alone does not make the download out of date
# (dist and build hold built copies: taking them out of the repo is not a new program, Grip Zones 2026-10-27)
NOT_SHIPPED = ("*.md", "docs", "ideas", "inspector", "test", "tests", "examples", "archive", "LICENSE", ".gitignore",
               "dist", "build")
APP_MARKS = ("install.ps1", "build.bat")
ZIP_LINK = "archive/refs/heads/main.zip"


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=GIT_TIMEOUT_S)
    return r.returncode, r.stdout.strip()


def newest(clone):
    """GitHub's newest state of a clone (fetched first): its upstream branch, else HEAD. A clone that was not pulled
    must not make a page look older than it is (seen on the first real run, 2026-10-27)."""
    if not os.environ.get("LANES_GU_NO_NET"):
        git(clone, "fetch", "-q", "--tags", "origin")
    return "@{upstream}" if git(clone, "rev-parse", "-q", "--verify", "@{upstream}")[0] == 0 else "HEAD"


def is_app(clone, head):
    """an app or add-on: something built and installed, so it needs a release to download"""
    _, tracked = git(clone, "ls-tree", "-r", "--name-only", head)
    files = tracked.splitlines()
    return any(m in files for m in APP_MARKS) or any(f.startswith("dist/") and f.endswith(".zip") for f in files)


def code_changes_since(clone, tag, head):
    """(count, newest subject) of commits after `tag` that touch what the download is made from; None when the tag is
    not in the clone"""
    if git(clone, "rev-parse", "-q", "--verify", f"refs/tags/{tag}")[0] != 0:
        return None
    spec = ["--", "."] + [f":(exclude){p}" for p in NOT_SHIPPED]
    _, log = git(clone, "log", "--format=%s", f"{tag}..{head}", *spec)
    lines = [x for x in log.splitlines() if x.strip()]
    return len(lines), (lines[0] if lines else "")


def downloads(owner):
    """sections 1 and 2: [{'name', 'flag'}], error"""
    skip = {s.lower() for s in gu.conf_values("od_skip")}
    clones = {os.path.basename(c.rstrip("/\\")).lower(): c for c in gu.conf_values("ours")}
    try:
        repos = {r["name"].lower(): r for r in gu_texts.repo_list(owner)
                 if str(r.get("visibility", "")).upper() == "PUBLIC" and not r.get("isArchived")}
    except Exception as e:
        return [], [], f"could not ask GitHub for the repo list ({e})"
    behind, missing = [], []
    for key, clone in sorted(clones.items()):
        if key not in repos or key in skip or not os.path.isdir(os.path.join(clone, ".git")):
            continue
        name = repos[key]["name"]
        tag = (gu_texts.newest_release(owner, repos[key]) or {}).get("tagName", "")
        head = newest(clone)
        if tag:
            got = code_changes_since(clone, tag, head)
            if got is None:
                behind.append({"name": name, "flag": f"its newest download {tag} is not in the clone (pull its tags)"})
            elif got[0]:
                behind.append({"name": name, "flag": f"{got[0]} change(s) to the program since its newest download "
                                                     f"{tag}, newest: \"{got[1][:90]}\""})
        elif is_app(clone, head):
            missing.append({"name": name, "flag": "an app or add-on with no download yet: build it, test it, "
                                                  "publish a release with SHA256SUMS.txt"})
        else:
            _, page = git(clone, "show", f"{head}:README.md")
            if ZIP_LINK not in page:
                missing.append({"name": name, "flag": "a library with no one-zip download link on its front page "
                                                      f"(https://github.com/{owner}/{name}/{ZIP_LINK})"})
    return behind, missing, ""


def scan(as_json):
    owner = (gu.conf_values("texts_owner") or [""])[-1]
    behind, missing, err = downloads(owner) if owner else ([], [], "not set up (texts_owner = <account>)")
    report = {"behind": behind, "missing": missing, "error": err, "texts": gu.texts_report(),
              "coverage": gu.coverage_report()}
    if as_json:
        print(json.dumps(report, indent=1))
        return 0
    print("1. Downloads behind the work")
    if err:
        print(f"   could not check: {err}")
    for b in behind:
        print(f"   {b['name']}: {b['flag']}")
    if not behind and not err:
        print("   every download is as new as its program")
    print("2. Tools with no download")
    for m in missing:
        print(f"   {m['name']}: {m['flag']}")
    if not missing and not err:
        print("   none")
    print("3. Texts on GitHub")
    t = report["texts"]
    if t is None:
        print("   not set up (texts = <folder of clones>)")
    elif t["error"]:
        print(f"   could not check: {t['error']}")
    else:
        print(f"   {t['checked']} public repos of {t['owner']} checked"
              + (f", {t['without_clone']} without a local clone (description only)" if t["without_clone"] else ""))
        for r in t["repos"]:
            for f in r["flags"]:
                print(f"   {r['name']}: {f}")
        if not t["repos"]:
            print("   nothing found by the checks; still read each description once against the project's notes")
    print("4. Lanes and the skills page keep up")
    c = report["coverage"]
    if c["error"]:
        print(f"   could not check: {c['error']}")
    for n in c["not_offered"]:
        print(f"   {n}: a public tool of ours that Lanes does not offer yet: add it to tools/ours.py "
              f"(or lanes_skip = {n})")
    if c["skills"] is None:
        print("   skills page: not set up (skills = <repo>/<file>)")
    else:
        for f in c["skills"]["flags"]:
            print(f"   {c['skills']['page']}: {f}")
    if not c["not_offered"] and not c["error"] and (c["skills"] is None or not c["skills"]["flags"]):
        print("   nothing missing")
    return 0


def main(argv):
    if argv and argv[0] == "scan":
        return scan("--json" in argv)
    print(__doc__)
    return 0 if not argv or argv[0] in ("-h", "--help") else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
