#!/usr/bin/env python3
"""gu_texts.py - /lanes:gu section 5: texts on GitHub that have fallen behind the work (0.69.0, 2026-10-15).

Asked for by the maintainer after finding a repo whose description still named v1.0.2, and whose front page sent
people to an older download, while v1.1.5 was the newest release: "can github update /gu also do that, go over the
whole github and bring all the texts and descriptions up to date". This module FINDS the likely stale texts; the
session reads the project's own notes and rewrites them (a tool cannot know what a project's status should say).

What it flags, for every public, non-archived repo of the account (`texts_owner =`, else the gh login):
  - the repo DESCRIPTION names a version older than the newest release;
  - the description or front page says nothing is released, or that the repo is private, while it is public and
    has a release;
  - a front-page line about the current version or the download (README.md, mod/README.md) names an older version
    and not the newest;
  - a front page with a Status part that has not changed in STATUS_STALE_DAYS while STATUS_STALE_COMMITS or more
    commits landed in the repo since.
Front pages are read from local clones (`texts = <folder of clones>`, repeatable), matched by their GitHub address;
a repo with no clone there gets the description checks only. Never edits anything.
Tests: LANES_GU_FAKE_REPOS (a JSON list shaped like `gh repo list --json name,description,visibility,isArchived,
latestRelease`), LANES_GU_NO_NET=1 (no fetch, no gh), LANES_GU_TODAY.
"""
import datetime
import json
import os
import re
import subprocess

GIT_TIMEOUT_S = 30
GH_TIMEOUT_S = 60
REPO_LIMIT = 1000
STATUS_STALE_DAYS = 21       # a status line untouched this long ...
STATUS_STALE_COMMITS = 15    # ... while this much work landed is worth a look
FRONT_PAGES = ("README.md", "mod/README.md")
VERSION_RE = re.compile(r"(?<![\w.])v?(\d+)\.(\d+)\.(\d+)(?![\w])|(?<![\w.])v(\d+)\.(\d+)(?![\w.])")
CURRENT_RE = re.compile(r"current|latest|newest|download|get it|released", re.I)
UNRELEASED_RE = re.compile(r"nothing here is released|no releases yet|not released yet|nothing released", re.I)
PRIVATE_RE = re.compile(r"private until|\*\*private[,.]", re.I)
STATUS_RE = re.compile(r"^#+\s*status\b|\bstatus:", re.I | re.M)


def versions(text):
    out = []
    for m in VERSION_RE.finditer(text or ""):
        g = m.groups()
        out.append(tuple(int(x) for x in (g[:3] if g[0] is not None else (g[3], g[4], 0))))
    return out


def tag_version(tag):
    v = versions(tag or "") or versions("v" + (tag or "").lstrip("vV"))
    return v[0] if v else None


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=GIT_TIMEOUT_S,
                       encoding="utf-8", errors="replace")
    return r.returncode, r.stdout.strip()


def repo_list(owner):
    fake = os.environ.get("LANES_GU_FAKE_REPOS")
    if fake:
        with open(fake, encoding="utf-8") as f:
            return json.load(f)
    if os.environ.get("LANES_GU_NO_NET"):
        return []
    r = subprocess.run(["gh", "repo", "list", owner, "-L", str(REPO_LIMIT), "--json",
                        "name,description,visibility,isArchived,latestRelease"],
                       capture_output=True, text=True, timeout=GH_TIMEOUT_S, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "gh repo list failed")
    return json.loads(r.stdout)


def newest_release(owner, repo):
    """The latest full release, else the newest pre-release (gh's latestRelease skips pre-releases; three projects
    here only ever had those, and one front page went stale behind them)."""
    if repo.get("latestRelease"):
        return repo["latestRelease"]
    if "releases" in repo or os.environ.get("LANES_GU_FAKE_REPOS") or os.environ.get("LANES_GU_NO_NET"):
        return (repo.get("releases") or [{}])[0]
    r = subprocess.run(["gh", "release", "list", "-R", f"{owner}/{repo['name']}", "-L", "1", "--json", "tagName"],
                       capture_output=True, text=True, timeout=GH_TIMEOUT_S, encoding="utf-8")
    try:
        return (json.loads(r.stdout) or [{}])[0] if r.returncode == 0 else {}
    except ValueError:
        return {}


def gh_login():
    if os.environ.get("LANES_GU_NO_NET"):
        return ""
    r = subprocess.run(["gh", "api", "user", "-q", ".login"], capture_output=True, text=True, timeout=GH_TIMEOUT_S)
    return r.stdout.strip() if r.returncode == 0 else ""


def clones_by_name(roots, owner):
    """{repo name: clone path} for clones under the `texts` folders whose origin is github.com/<owner>/<name>."""
    out = {}
    pat = re.compile(r"github\.com[:/]" + re.escape(owner) + r"/([^/]+?)(?:\.git)?/?$", re.I)
    for root in roots:
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            path = os.path.join(root, name)
            if not os.path.isdir(os.path.join(path, ".git")):
                continue
            rc, url = git(path, "remote", "get-url", "origin")
            m = pat.search(url) if rc == 0 else None
            if m:
                out.setdefault(m.group(1).lower(), path)
    return out


def front_page(clone, rel):
    """The file as GitHub shows it: origin's branch after a fetch, else this clone's HEAD."""
    for ref in ("origin/HEAD", "origin/main", "HEAD"):
        rc, text = git(clone, "show", f"{ref}:{rel}")
        if rc == 0:
            return ref, text
    return None, None


def status_staleness(clone, ref, rel, now):
    rc, ct = git(clone, "log", "-1", "--format=%ct", ref, "--", rel)
    if rc != 0 or not ct:
        return None
    rc, since = git(clone, "rev-list", "--count", f"--since={ct}", ref)
    days = (now - datetime.date.fromtimestamp(int(ct))).days
    commits = max(int(since) - 1, 0) if rc == 0 and since.isdigit() else 0
    if days >= STATUS_STALE_DAYS and commits >= STATUS_STALE_COMMITS:
        return days, commits
    return None


def check_repo(repo, clone, now, owner=""):
    flags = []
    rel = newest_release(owner, repo) or {}
    latest = tag_version(rel.get("tagName"))
    desc = repo.get("description") or ""
    if latest and any(v < latest for v in versions(desc)) and latest not in versions(desc):
        flags.append(f"description names an older version than the newest release {rel.get('tagName')}")
    if rel and UNRELEASED_RE.search(desc):
        flags.append("description says nothing is released, but there is a release")
    if PRIVATE_RE.search(desc):
        flags.append("description says it is private, but the repo is public")
    if not clone:
        return flags
    if not os.environ.get("LANES_GU_NO_NET"):
        git(clone, "fetch", "-q", "origin")
    for page in FRONT_PAGES:
        ref, text = front_page(clone, page)
        if text is None:
            continue
        if rel and UNRELEASED_RE.search(text):
            flags.append(f"{page} says nothing is released, but there is a release")
        if PRIVATE_RE.search(text):
            flags.append(f"{page} says it is private, but the repo is public")
        if latest:
            for n, line in enumerate(text.splitlines(), 1):
                vs = versions(line)
                if vs and CURRENT_RE.search(line) and latest not in vs and any(v < latest for v in vs):
                    flags.append(f"{page} line {n} points at an older version than {rel.get('tagName')}")
        if STATUS_RE.search(text):
            stale = status_staleness(clone, ref, page, now)
            if stale:
                flags.append(f"{page} has a status part unchanged for {stale[0]} days, {stale[1]} commits since")
    return flags


def scan(roots, owner, now):
    """{'owner', 'checked', 'without_clone', 'repos': [{'name', 'flags'}], 'error'}"""
    owner = owner or gh_login()
    if not owner:
        return {"owner": "", "checked": 0, "without_clone": 0, "repos": [], "error": "no account (texts_owner)"}
    try:
        repos = repo_list(owner)
    except Exception as e:
        return {"owner": owner, "checked": 0, "without_clone": 0, "repos": [], "error": str(e)}
    clones = clones_by_name(roots, owner)
    out, checked, missing = [], 0, 0
    for repo in sorted(repos, key=lambda r: r["name"].lower()):
        if repo.get("visibility", "").upper() != "PUBLIC" or repo.get("isArchived"):
            continue
        checked += 1
        clone = clones.get(repo["name"].lower())
        missing += clone is None
        flags = check_repo(repo, clone, now, owner)
        if flags:
            out.append({"name": repo["name"], "flags": flags})
    return {"owner": owner, "checked": checked, "without_clone": missing, "repos": out, "error": None}
