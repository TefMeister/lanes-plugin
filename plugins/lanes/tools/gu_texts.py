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
CATALOG PAGES (0.91.0, `catalog = <repo>/<file>`, repeatable): a page that should name every tool we made (the
toolkit's TOOLKIT.md). Flagged: a tool in that repo's tools/ folder, a public `ours =` repo, or an app any PC has
installed (installed.py's notes), that the page never names; and a tool it names whose repo had CATALOG_STALE_COMMITS
or more commits since the page last changed. The maintainer, 2026-10-27, after TOOLKIT.md missed five apps: "this should
have been covered by the /fullscan and /gu, can you make a fix for it so next time something like this is not forgotten".
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
CATALOG_STALE_COMMITS = 10   # a tool's repo moving this much after the catalog page last changed is worth a look
CATALOG_SKIP = {"README.md", "test", "tests", "__pycache__", "lib", "templates"}
ROW_STALE_COMMITS = 3        # commits of real work after a summary row's date before it counts as behind
SWEEP_REPOS = 4              # a commit subject seen in this many repos is an estate-wide sweep, not progress
NOT_WORK = ("external-research/**", "**/inbox/**", "inbox/**", "inspector/**", "**/inspector/**", "ideas/**",
            "README.md", "**/README.md",   # a front page changing is texts, not the project moving
            "**/data/**", "**/knowledge/**", "**/archive/**")   # reports filed and old files shelved, not the tool
# moving: every BeG0nE row read as weeks behind on 2026-10-28 because the rider files its reports there
VERSION_RE = re.compile(r"(?<![\w.])v?(\d+)\.(\d+)\.(\d+)(?![\w])|(?<![\w.])v(\d+)\.(\d+)(?![\w.])")
CURRENT_RE = re.compile(r"current|latest|newest|download|get it|released", re.I)
# A phrase in quotes is a page TALKING ABOUT the check (the plugin README does), not a status claim.
UNRELEASED_RE = re.compile(r"(?<![\"'“`])(?:nothing here is released|no releases yet|not released yet|nothing released)", re.I)
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


def squash(name):
    """'Hand Freeze', 'hand-freeze-vr' and 'HandFreeze' all read as 'handfreeze'"""
    s = re.sub(r"[^a-z0-9]", "", name.lower())
    return s[:-2] if s.endswith("vr") and len(s) > 4 else s


def catalog_items(clone, ours, apps, public):
    """{squashed name: [name, repo or None]} a catalog page should mention: every tool in its own repo's tools/ folder,
    every public repo of ours (`ours =`), and every app of ours any PC has installed (installed.py's notes). An app
    and its repo ('Hand Poser', hand-poser-vr) are one item, named as the app."""
    items = {}
    rc, listing = git(clone, "ls-tree", "--name-only", "HEAD", "tools/")
    for p in (listing.splitlines() if rc == 0 else []):
        name = os.path.basename(p)
        if name not in CATALOG_SKIP and not name.startswith((".", "_")):
            items[squash(os.path.splitext(name)[0])] = [name, None]
    own = os.path.basename(clone.rstrip("/\\")).lower()
    for path in ours:
        name = os.path.basename(path.rstrip("/\\"))
        if name.lower() in public and name.lower() != own:
            items.setdefault(squash(name), [name, None])[1] = name
    for app in apps:
        items.setdefault(squash(app), [app, None])[0] = app
    return items


def check_catalog(spec, clones, ours, apps, public):
    """flags for one `catalog = <repo>/<file>`: what it never mentions, and what it mentions while that tool's repo
    kept moving after the page last changed (2026-10-27: TOOLKIT.md had no word of Hand Poser, Window View, Grab Zones,
    VR Bench or Menu-o-matiC, and still called Hand Freeze 64-bit only and untried in a real game)"""
    repo, _, rel = spec.replace("\\", "/").partition("/")
    clone = clones.get(repo.lower())
    if not clone or not rel:
        return [f"{spec}: no local clone of {repo} to read it from"]
    ref, text = front_page(clone, rel)
    if text is None:
        return [f"{spec}: {rel} not found in {repo}"]
    said = squash(text)
    flags = []
    rc, ct = git(clone, "log", "-1", "--format=%ct", ref, "--", rel)
    for key, (item, item_repo) in sorted(catalog_items(clone, ours, apps, public).items()):
        if key not in said:
            flags.append(f"{rel} never mentions {item}")
            continue
        other = clones.get((item_repo or "").lower())
        if other and rc == 0 and ct:
            other_ref = front_page(other, "README.md")[0] or "HEAD"     # GitHub's copy when fetched (check_repo)
            n_rc, n = git(other, "rev-list", "--count", f"--since={ct}", other_ref)
            if n_rc == 0 and n.isdigit() and int(n) >= CATALOG_STALE_COMMITS:
                flags.append(f"{rel} mentions {item}, but {item_repo} had {n} commits since the page last changed")
    return flags


def row_date(mmdd, now):
    """a table's MM-DD as a date: this year, or last year when that would be in the future"""
    try:
        d = datetime.date(now.year, int(mmdd[:2]), int(mmdd[3:5]))
    except ValueError:
        return None
    return d if d <= now else d.replace(year=now.year - 1)


def work_since(clone, sub, since):
    """[(subject, date)] of commits on GitHub's copy after `since` (a date) that touch `sub` (or the whole repo), leaving
    out research notes, inboxes, Inspector notes and ideas, which move without the project moving"""
    ref = front_page(clone, "README.md")[0] or "HEAD"
    spec = ["--", sub or "."] + [f":(exclude,glob){p}" for p in NOT_WORK]
    rc, out = git(clone, "log", "--format=%s%x09%cs", f"--since={since.isoformat()}T23:59:59", ref, *spec)
    return [tuple(line.rsplit("\t", 1)) for line in out.splitlines() if "\t" in line] if rc == 0 else []


def summary_pages(pages, clones, releases, now, owner):
    """{repo: [flags]} for the pages that sum up every project (0.94.2): the profile README's table rows (each links to
    its repo, or a folder in it, and carries an MM-DD date) and INDEX.json's projects (latest_release, a dated stage).
    A row is behind when ROW_STALE_COMMITS or more commits of real work landed after its date, or when it names an
    older version than the newest release. A commit whose subject turns up in SWEEP_REPOS or more repos is an
    estate-wide sweep (a privacy clean-up, say), not progress, and does not count. The maintainer, 2026-10-28:
    "things are still being out of date and descriptions not updated throughout the github, sometimes only in some
    places and not others"."""
    entries = []        # (repo, sub, date, text, what)
    link = re.compile(r"\]\(https://github\.com/" + re.escape(owner) + r"/([\w.-]+)(?:/tree/[^/)]+/([^)#]+))?\)", re.I)
    for page in pages:
        if page.endswith(".json"):
            try:
                with open(page, encoding="utf-8") as f:
                    projects = json.load(f).get("projects") or []
            except (OSError, ValueError):
                continue
            for p in projects:
                stage = p.get("stage") or ""
                dates = sorted(re.findall(r"\d{4}-\d\d-\d\d", stage))
                when = datetime.date.fromisoformat(dates[-1]) if dates else None
                entries.append((p.get("repo", ""), "", when, stage + " " + str(p.get("latest_release") or ""),
                                "INDEX.json's stage"))
                rel = (releases.get(p.get("repo", "").lower()) or {}).get("tagName")
                said = p.get("latest_release")
                if rel and said and tag_version(said) and tag_version(said) < (tag_version(rel) or (0, 0, 0)):
                    entries.append((p["repo"], "", None, "", f"INDEX.json says latest_release {said}, GitHub's "
                                                              f"newest is {rel}"))
            continue
        try:
            with open(page, encoding="utf-8") as f:
                lines = f.read().splitlines()
        except OSError:
            continue
        for line in lines:
            m = link.search(line)
            if not line.startswith("| ") or not m:
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            mmdd = next((c for c in cells if re.fullmatch(r"\d\d-\d\d", c)), None)
            entries.append((m.group(1), (m.group(2) or "").strip("/"), row_date(mmdd, now) if mmdd else None, line,
                            f"the {os.path.basename(page)} row \"{cells[0].strip('*')[:40]}\""))
    found, subjects = [], {}
    for repo, sub, when, text, what in entries:
        clone = clones.get(repo.lower())
        commits = work_since(clone, sub, when) if clone and when else []
        for s, _ in commits:
            subjects.setdefault(s, set()).add(repo.lower())
        found.append((repo, sub, when, text, what, commits))
    out = {}
    for repo, sub, when, text, what, commits in found:
        if not text:                                   # a plain fact found above (INDEX.json's latest_release)
            out.setdefault(repo, []).append(what)
            continue
        work = [(s, d) for s, d in commits if len(subjects.get(s, ())) < SWEEP_REPOS]
        if len(work) >= ROW_STALE_COMMITS:
            out.setdefault(repo, []).append(f"{what}, dated {when}, is behind: {len(work)} commits of work since"
                                            + (f" in {sub}/" if sub else "") + f", newest {work[0][1]} \"{work[0][0][:70]}\"")
        rel = (releases.get(repo.lower()) or {}).get("tagName")
        latest = tag_version(rel)
        # INDEX.json's version is its latest_release, already compared above; said twice it read as two faults
        if latest and not sub and not what.startswith("INDEX.json") and latest not in versions(text) \
                and any(v < latest for v in versions(text)):
            out.setdefault(repo, []).append(f"{what} names an older version than the newest release {rel}")
    return out


def scan(roots, owner, now, catalogs=(), ours=(), apps=(), summaries=()):
    """{'owner', 'checked', 'without_clone', 'repos': [{'name', 'flags'}], 'error'}. `catalogs` are pages that should
    name every tool of ours (`catalog = <repo>/<file>`, 0.91.0); their findings come under that repo's name.
    `summaries` are the pages that sum up every project (the profile README and INDEX.json, 0.94.2)."""
    owner = owner or gh_login()
    if not owner:
        return {"owner": "", "checked": 0, "without_clone": 0, "repos": [], "error": "no account (texts_owner)"}
    try:
        repos = repo_list(owner)
    except Exception as e:
        return {"owner": owner, "checked": 0, "without_clone": 0, "repos": [], "error": str(e)}
    clones = clones_by_name(roots, owner)
    out, checked, missing = {}, 0, 0
    public = set()
    for repo in sorted(repos, key=lambda r: r["name"].lower()):
        if repo.get("visibility", "").upper() != "PUBLIC" or repo.get("isArchived"):
            continue
        public.add(repo["name"].lower())
        checked += 1
        clone = clones.get(repo["name"].lower())
        missing += clone is None
        flags = check_repo(repo, clone, now, owner)
        if flags:
            out[repo["name"]] = flags
    for spec in catalogs:
        flags = check_catalog(spec, clones, ours, apps, public)
        if flags:
            out.setdefault(spec.replace("\\", "/").split("/")[0], []).extend(flags)
    releases = {r["name"].lower(): newest_release(owner, r) for r in repos
                if r.get("visibility", "").upper() == "PUBLIC" and not r.get("isArchived")}
    for name, flags in summary_pages(summaries, clones, releases, now, owner).items():
        out.setdefault(name, []).extend(flags)
    return {"owner": owner, "checked": checked, "without_clone": missing,
            "repos": [{"name": n, "flags": f} for n, f in out.items()], "error": None}
