#!/usr/bin/env python3
"""builds.py - keep every build: one numbered, full copy per change, shared through GitHub.

    builds.py init    <project> --app DIR --ours NAME [--ours NAME ...] [--series 0.1.0]
                      [--skip NAME ...] [--local-only PATH ...]
    builds.py snap    <project> "<title>" --note "<what changed and why>" [--result "<what was seen>"]
                      [--source DIR] [--no-push]
    builds.py result  <project> <N> "<what was seen>"      fill in a result later
    builds.py list    <project>
    builds.py which   <project>                            which build the app folder holds right now
    builds.py restore <project> <N> [--yes]                put build N back into the app folder

WHY (0.26.0)
  The person asked for it twice: "keep each version saved ... so we can roll back steps", then "a new
  folder for every smallest change made ... with a new mod version number", and last "it also has to
  be pushed on github, so the mod version is always in sync between the dev and home pc". Bisecting a
  regression needs the exact earlier files, and a build that only lives on one PC cannot be tested on
  the other. So every change that goes into the app folder becomes a new numbered folder, never an
  overwrite, and that folder is committed to a private git repo both PCs clone.

WHAT A BUILD IS
  <builds repo>/<project>/v<series>-bNNN - <title>/  holding a full copy of everything of OURS in the
  app folder (the `ours` list in PROJECT.conf - never the app's own files), plus MANIFEST.sha256 and
  CHANGES.md (what changed since the previous build, the note, the result). INDEX.md lists them all.
  Git stores a file that did not change as the same object, so a full copy per build costs only the
  files that actually changed.

TWO KINDS OF FILE NEVER GO TO GITHUB, and both are still listed with their hash in MANIFEST.sha256:
  - `local_only` paths: anything built from the app's own data (an edited game file, a repacked
    texture). Publishing those is publishing the game. They stay in the build folder on this PC; a
    per-build .gitignore keeps them out, and `restore` on the other PC names exactly which are missing.
  - files over BIG_FILE_MB: sent as a release asset on the builds repo instead (GitHub refuses files
    over 100 MB in the tree). A small `<file>.release.txt` stub stays in the folder; `restore` fetches it.

WHERE THINGS ARE
  lanes.conf  builds = <clone of your private builds repo>      ($LANES_BUILDS)
              builds_app.<project> = <app folder on THIS PC>    (overrides PROJECT.conf `app`)
              mint_copy.<project> = <private copy>             (mint.py; wins over both, and restore
                                                               refuses to write into mint_vanilla)
  <builds>/<project>/PROJECT.conf  - series, app, ours, skip, local_only (one value per line, repeatable)

NUMBERS STAY IN STEP BETWEEN PCs: `snap` pulls before it numbers and pushes straight after. If the other
PC pushed the same number in between, the push is refused, the tool pulls again and renumbers its own
build to the next free number, so two PCs can never share a number.

Nothing is ever deleted by this tool, except that `restore` removes the `ours` items from the app folder
before copying the chosen build in - and it first saves the app folder as a build if it does not match one.
"""
import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time

# ---- settings (named numbers, one place) --------------------------------------------------------
BIG_FILE_MB = 95                       # above this a file goes up as a release asset, not into git
DEFAULT_SERIES = "0.1.0"
TITLE_MAX = 70                         # characters of the title kept in a folder name
CHANGES_LIST_MAX = 200                 # files listed per section in CHANGES.md
PUSH_TRIES = 3
META = ("MANIFEST.sha256", "CHANGES.md", ".gitignore")
RELEASE_STUB = ".release.txt"
NOT_TESTED = "(not tested yet)"


# ---- config -------------------------------------------------------------------------------------
def conf_candidates():
    if os.environ.get("LANES_CONFIG"):
        return [os.environ["LANES_CONFIG"]]
    return [os.path.expanduser("~/.claude/lanes.conf"), os.path.expanduser("~/.config/lanes/lanes.conf")]


def conf_get(key):
    pat = re.compile(r"^\s*" + re.escape(key) + r"\s*=\s*(.*?)\s*$")
    for path in conf_candidates():
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = pat.match(line.rstrip("\r\n"))
                if m and not line.lstrip().startswith("#"):
                    return m.group(1).strip().strip('"').strip("'")
    return ""


def builds_root():
    root = os.environ.get("LANES_BUILDS", "") or conf_get("builds")
    if not root or not os.path.isdir(root):
        sys.exit("builds.py: no builds repo. Clone your private builds repo and set `builds = <path>` in "
                 "~/.claude/lanes.conf.")
    return root


def read_project(root, project):
    path = os.path.join(root, project, "PROJECT.conf")
    if not os.path.isfile(path):
        sys.exit(f"builds.py: {project} has no PROJECT.conf yet - run `builds.py init {project} ...` first.")
    conf = {"series": DEFAULT_SERIES, "app": "", "ours": [], "skip": [], "local_only": []}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = (s.strip() for s in line.partition("="))
            if isinstance(conf.get(key), list):
                conf[key].append(val)
            elif key in conf:
                conf[key] = val
    # A private copy (mint.py, 0.27.0) IS the app folder: the clean install is never written into.
    conf["app"] = conf_get(f"mint_copy.{project}") or conf_get(f"builds_app.{project}") or conf["app"]
    conf["vanilla"] = conf_get(f"mint_vanilla.{project}")
    return conf


# ---- git ----------------------------------------------------------------------------------------
def git(root, *args, check=True):
    r = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f"builds.py: git {' '.join(args)} failed:\n{r.stderr.strip()}")
    return r


def pull(root):
    if os.environ.pop("LANES_BUILDS_TEST_SKIP_FIRST_PULL", ""):   # tests only: act as if the other PC
        return                                                    # pushed between our pull and our push
    if has_upstream(root):
        git(root, "pull", "--rebase", "--quiet")


def has_upstream(root):
    """False for a brand-new repo whose first push has not happened yet: nothing to pull."""
    return git(root, "rev-parse", "--abbrev-ref", "@{u}", check=False).returncode == 0


def push_now(root):
    args = ["push", "--quiet"] if has_upstream(root) else ["push", "--quiet", "-u", "origin", "HEAD"]
    return git(root, *args, check=False).returncode == 0


def has_remote(root):
    return bool(git(root, "remote", check=False).stdout.strip())


def remote_slug(root):
    url = git(root, "remote", "get-url", "origin", check=False).stdout.strip()
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
    return m.group(1) if m else ""


# ---- files --------------------------------------------------------------------------------------
def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_local_only(rel, conf):
    return any(rel == p.rstrip("/") or rel.startswith(p.rstrip("/") + "/") for p in conf["local_only"])


def files_of_ours(folder, conf):
    """rel path -> abs path for every file of ours under folder (an app folder or a build folder)."""
    out = {}
    for item in conf["ours"]:
        p = os.path.join(folder, item)
        if os.path.isfile(p):
            out[item.replace("\\", "/")] = p
        elif os.path.isdir(p):
            for r, _, names in os.walk(p):
                for n in names:
                    if n in conf["skip"]:
                        continue
                    full = os.path.join(r, n)
                    out[os.path.relpath(full, folder).replace("\\", "/")] = full
    return out


def read_manifest(build_dir):
    out = {}
    try:
        with open(os.path.join(build_dir, "MANIFEST.sha256"), encoding="utf-8") as f:
            for line in f:
                h, _, p = line.rstrip("\n").partition("  ")
                if p:
                    out[p] = h
    except OSError:
        pass
    return out


# ---- builds -------------------------------------------------------------------------------------
def version_re(series):
    return re.compile(r"^v" + re.escape(series) + r"-b(\d{3,}) - ")


def builds(root, project, conf):
    pdir = os.path.join(root, project)
    vre = version_re(conf["series"])
    out = [(int(m.group(1)), n) for n in os.listdir(pdir) if (m := vre.match(n))]
    return sorted(out)


def safe_title(t):
    return re.sub(r"[^\w .,+()-]", "", t).strip()[:TITLE_MAX].strip()


def write_ignore_and_stubs(root, project, build_dir, conf, tag_hint):
    """Keep local-only files out of git; send big files to a release asset and leave a stub."""
    ignore, big = [], []
    for rel in read_manifest(build_dir):
        full = os.path.join(build_dir, rel)
        if is_local_only(rel, conf):
            ignore.append(rel)
        elif os.path.isfile(full) and os.path.getsize(full) > BIG_FILE_MB * 1024 * 1024:
            ignore.append(rel)
            big.append(rel)
    with open(os.path.join(build_dir, ".gitignore"), "w", encoding="utf-8", newline="\n") as f:
        f.write("# Kept on this PC only (built from the app's own data), or sent as a release asset (too big).\n")
        f.writelines("/" + re.sub(r"([\[\]*?!#])", r"\\\1", rel) + "\n" for rel in ignore)
    slug = remote_slug(root)
    for rel in big:
        stub = os.path.join(build_dir, rel + RELEASE_STUB)
        if os.path.isfile(stub):
            continue
        digest = sha(os.path.join(build_dir, rel))
        tag = f"{project}-{digest[:12]}"
        where = "(no GitHub remote - kept on this PC only)"
        if slug:
            exists = subprocess.run(["gh", "release", "view", tag, "--repo", slug], capture_output=True).returncode == 0
            if not exists:
                r = subprocess.run(["gh", "release", "create", tag, os.path.join(build_dir, rel), "--repo", slug,
                                    "--title", f"{project} {os.path.basename(rel)} {digest[:12]}",
                                    "--notes", f"Large file of {tag_hint}; see its folder in the builds repo."],
                                   capture_output=True, text=True)
                if r.returncode:
                    print(f"  WARNING: could not upload {rel} as a release asset: {r.stderr.strip()}")
                    continue
            where = f"release {tag} on {slug}"
        with open(stub, "w", encoding="utf-8", newline="\n") as f:
            f.write(f"{digest}  {rel}\n{where}\n")
    return ignore


def write_index_row(root, project, conf, name, when, note, result):
    index = os.path.join(root, project, "INDEX.md")
    if not os.path.isfile(index):
        with open(index, "w", encoding="utf-8", newline="\n") as f:
            f.write(f"# {project} build versions\n\nOne folder per change, oldest first. Each holds a full copy of "
                    "everything of ours that was in the app folder, plus CHANGES.md.\n\n"
                    "| Build | When | What changed | Result |\n| --- | --- | --- | --- |\n")
    cell = lambda s: s.replace("|", "/").replace("\n", " ")
    with open(index, "a", encoding="utf-8", newline="\n") as f:
        f.write(f"| {name} | {when} | {cell(note)} | {cell(result or NOT_TESTED)} |\n")


def commit_and_push(root, project, message):
    git(root, "add", "--", project)
    if not git(root, "status", "--porcelain", "--", project, check=False).stdout.strip():
        return "nothing to commit"
    git(root, "commit", "--quiet", "-m", message)
    if not has_remote(root):
        return "committed (no remote)"
    for _ in range(PUSH_TRIES):
        if push_now(root):
            return "pushed"
        pull(root)
    return "NOT PUSHED - run `git push` in the builds repo"


def move_to_free_number(root, project, conf, name):
    """The build folder is not committed. If its number is taken now, rename it to the next free one."""
    vre = version_re(conf["series"])
    num = int(vre.match(name).group(1))
    taken = [(b, n) for b, n in builds(root, project, conf) if n != name]
    if not any(b == num for b, _ in taken):
        return name
    new_num = max(b for b, _ in taken) + 1
    new_name = vre.sub(f"v{conf['series']}-b{new_num:03d} - ", name)
    pdir = os.path.join(root, project)
    os.rename(os.path.join(pdir, name), os.path.join(pdir, new_name))
    changes = os.path.join(pdir, new_name, "CHANGES.md")
    with open(changes, encoding="utf-8") as f:
        text = f.read()
    with open(changes, "w", encoding="utf-8", newline="\n") as f:
        f.write(text.replace(name, new_name, 1))
    print(f"  the other PC had already used b{num:03d}; this build is now {new_name}")
    return new_name


def save_build(root, project, conf, name, when, note, result, push=True):
    """Add the index row, commit, push. If the push is refused because the other PC saved first, undo
    our commit (keeping the files), take theirs, move ours to a free number, and try again - so the
    shared INDEX.md never has to be merged by hand and no two builds ever share a number."""
    index_rel = f"{project}/INDEX.md"
    for _ in range(PUSH_TRIES):
        write_index_row(root, project, conf, name, when, note, result)
        if not push:
            return name, "not committed (--no-push)"
        git(root, "add", "--", project)
        git(root, "commit", "--quiet", "-m", f"{project}: {name}")
        if not has_remote(root):
            return name, "committed (no remote)"
        if push_now(root):
            return name, "pushed"
        git(root, "reset", "--quiet", "--mixed", "HEAD~1")
        if git(root, "ls-files", "--", index_rel, check=False).stdout.strip():
            git(root, "checkout", "--", index_rel)
        else:
            os.remove(os.path.join(root, index_rel))
        pull(root)
        name = move_to_free_number(root, project, conf, name)
    return name, "NOT PUSHED - run `git push` in the builds repo"


def snapshot(root, project, conf, title, note, result, source):
    if not conf["ours"]:
        sys.exit("builds.py: PROJECT.conf lists nothing under `ours`.")
    src = source or conf["app"]
    if not src or not os.path.isdir(src):
        sys.exit(f"builds.py: app folder not found: {src!r}. Set `builds_app.{project} = <path>` in lanes.conf.")
    pull(root)
    existing = builds(root, project, conf)
    num = existing[-1][0] + 1 if existing else 1
    name = f"v{conf['series']}-b{num:03d} - {safe_title(title)}"
    dest = os.path.join(root, project, name)
    os.makedirs(dest)
    now = {}
    for rel, full in files_of_ours(src, conf).items():
        target = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(full, target)
        now[rel] = sha(target)
    with open(os.path.join(dest, "MANIFEST.sha256"), "w", encoding="utf-8", newline="\n") as f:
        f.writelines(f"{now[p]}  {p}\n" for p in sorted(now))
    prev_name = existing[-1][1] if existing else ""
    prev = read_manifest(os.path.join(root, project, prev_name)) if prev_name else {}
    added = sorted(set(now) - set(prev))
    removed = sorted(set(prev) - set(now))
    changed = sorted(p for p in set(now) & set(prev) if now[p] != prev[p])
    when = time.strftime("%Y-%m-%d %H:%M")
    ignored = write_ignore_and_stubs(root, project, dest, conf, name)
    lines = [f"# {name}", "", f"- **When:** {when}",
             f"- **Copied from:** {'the app folder' if not source else 'a folder given with --source'}",
             f"- **Previous build:** {prev_name or '(first)'}",
             f"- **What changed and why:** {note}", f"- **Result:** {result or NOT_TESTED}",
             f"- **Not on GitHub:** {len(ignored)} file(s), listed in .gitignore (local-only or release asset)", "",
             f"## Files compared with the previous build ({len(now)} files in this build)", ""]
    for label, items in (("Added", added), ("Removed", removed), ("Changed", changed)):
        lines.append(f"**{label}:** {len(items)}")
        lines.extend(f"- `{p}`" for p in items[:CHANGES_LIST_MAX])
        lines.append("")
    with open(os.path.join(dest, "CHANGES.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    print(f"saved {name}: {len(now)} files (+{len(added)} -{len(removed)} ~{len(changed)} vs previous)")
    return name, when


def cmd_snap(a):
    root = builds_root()
    conf = read_project(root, a.project)
    name, when = snapshot(root, a.project, conf, a.title, a.note, a.result, a.source)
    name, state = save_build(root, a.project, conf, name, when, a.note, a.result, push=not a.no_push)
    print(f"github: {state}  ({name})")


def cmd_result(a):
    root = builds_root()
    conf = read_project(root, a.project)
    pull(root)
    match = [n for b, n in builds(root, a.project, conf) if b == a.number]
    if not match:
        sys.exit(f"builds.py: no build b{a.number:03d} in {a.project}")
    name = match[0]
    path = os.path.join(root, a.project, name, "CHANGES.md")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    text = re.sub(r"^- \*\*Result:\*\* .*$", lambda _: f"- **Result:** {a.text}", text, count=1, flags=re.M)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    index = os.path.join(root, a.project, "INDEX.md")
    with open(index, encoding="utf-8") as f:
        rows = f.read().splitlines()
    cell = a.text.replace("|", "/")
    rows = [re.sub(r"\| [^|]* \|$", lambda _: f"| {cell} |", r) if r.startswith(f"| {name} |") else r for r in rows]
    with open(index, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(rows) + "\n")
    print(f"result recorded for {name}")
    print(f"github: {commit_and_push(root, a.project, f'{a.project}: result for {name}')}")


def cmd_list(a):
    root = builds_root()
    conf = read_project(root, a.project)
    for _, n in builds(root, a.project, conf):
        print(n)


def app_state(conf):
    return {rel: sha(full) for rel, full in files_of_ours(conf["app"], conf).items()}


def closest(root, project, conf, state):
    best = None
    for num, name in reversed(builds(root, project, conf)):
        man = read_manifest(os.path.join(root, project, name))
        diff = sorted(p for p in set(man) | set(state) if man.get(p) != state.get(p))
        if best is None or len(diff) < len(best[2]):
            best = (num, name, diff)
        if not diff:
            break
    return best


def cmd_which(a):
    root = builds_root()
    conf = read_project(root, a.project)
    pull(root)
    state = app_state(conf)
    all_builds = builds(root, a.project, conf)
    best = closest(root, a.project, conf, state)
    if not best:
        print("no builds saved yet")
        return
    num, name, diff = best
    latest = all_builds[-1][1]
    if not diff:
        print(f"the app folder holds {name}")
    else:
        print(f"the app folder matches NO saved build; nearest is {name}, {len(diff)} file(s) differ:")
        for p in diff[:20]:
            print(f"  {p}")
        print("  -> save it with `builds.py snap` before testing, so the result belongs to a number")
    if name != latest:
        print(f"the newest build is {latest} - `builds.py restore {a.project} {all_builds[-1][0]}` brings it here")


def cmd_restore(a):
    root = builds_root()
    conf = read_project(root, a.project)
    pull(root)
    match = [n for b, n in builds(root, a.project, conf) if b == a.number]
    if not match:
        sys.exit(f"builds.py: no build b{a.number:03d} in {a.project}")
    name = match[0]
    bdir = os.path.join(root, a.project, name)
    man = read_manifest(bdir)
    slug = remote_slug(root)
    missing = []
    for rel, digest in man.items():
        full = os.path.join(bdir, rel)
        if os.path.isfile(full):
            continue
        stub = full + RELEASE_STUB
        if os.path.isfile(stub) and slug and a.yes:
            tag = f"{a.project}-{digest[:12]}"
            subprocess.run(["gh", "release", "download", tag, "--repo", slug, "--dir", os.path.dirname(full),
                            "--pattern", os.path.basename(rel)], capture_output=True)
            if os.path.isfile(full):
                continue
        missing.append(rel + ("  (release asset)" if os.path.isfile(stub) else "  (kept on the other PC only)"))
    if conf["vanilla"] and os.path.normcase(os.path.abspath(conf["app"])) ==             os.path.normcase(os.path.abspath(conf["vanilla"])):
        sys.exit(f"builds.py: refused - {conf['app']!r} is the clean install (mint_vanilla.{a.project}), and nothing "
                 f"is ever written into it. Restore into the private copy: set mint_copy.{a.project} in lanes.conf.")
    state = app_state(conf)
    best = closest(root, a.project, conf, state)
    unsaved = bool(state) and (best is None or best[2])
    print(f"restore {name} into {conf['app']}")
    print(f"  {len(man)} files; the app folder now {'matches ' + best[1] if best and not best[2] else 'matches no saved build'}")
    if missing:
        print(f"  {len(missing)} file(s) are not on this PC yet:")
        for m in missing[:30]:
            print(f"    {m}")
    if not a.yes:
        print("  dry run - add --yes to do it" + (" (the current app folder is saved as a build first)" if unsaved else ""))
        return
    if missing and not a.force_missing:
        sys.exit("  stopped: files missing. Copy them into the build folder, or add --force-missing to restore without them.")
    if unsaved:
        note = "Automatic: the app folder matched no saved build, so it was kept before a restore."
        saved, when = snapshot(root, a.project, conf, f"before restoring b{a.number:03d}", note, "", None)
        print(f"  github: {save_build(root, a.project, conf, saved, when, note, '')[1]}")
    for item in conf["ours"]:
        p = os.path.join(conf["app"], item)
        if os.path.isdir(p):
            shutil.rmtree(p)
        elif os.path.isfile(p):
            os.remove(p)
    for rel in man:
        full = os.path.join(bdir, rel)
        if os.path.isfile(full):
            target = os.path.join(conf["app"], rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(full, target)
    print(f"  done: the app folder holds {name}")


def cmd_init(a):
    root = builds_root()
    pdir = os.path.join(root, a.project)
    os.makedirs(pdir, exist_ok=True)
    path = os.path.join(pdir, "PROJECT.conf")
    if os.path.isfile(path) and not a.force:
        sys.exit(f"builds.py: {path} exists (add --force to rewrite it)")
    lines = [f"# builds.py settings for {a.project}. One value per line; repeat a key to list several.",
             "# `app` is this project's app folder; a PC whose folder differs sets builds_app.<project> in lanes.conf.",
             f"series = {a.series}", f"app = {a.app}"]
    lines += [f"ours = {x}" for x in a.ours] + [f"skip = {x}" for x in a.skip or []]
    lines += ["# Built from the app's own data: kept on the PC, never pushed."]
    lines += [f"local_only = {x}" for x in a.local_only or []]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    conf = read_project(root, a.project)
    adopted = 0
    for _, name in builds(root, a.project, conf):   # builds made by hand before this tool: same format
        write_ignore_and_stubs(root, a.project, os.path.join(pdir, name), conf, name)
        adopted += 1
    print(f"wrote {path}; {adopted} existing build(s) adopted")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("project")
    p.add_argument("--app", required=True)
    p.add_argument("--ours", action="append", required=True)
    p.add_argument("--skip", action="append")
    p.add_argument("--local-only", action="append")
    p.add_argument("--series", default=DEFAULT_SERIES)
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_init)
    p = sub.add_parser("snap")
    p.add_argument("project")
    p.add_argument("title")
    p.add_argument("--note", required=True)
    p.add_argument("--result", default="")
    p.add_argument("--source")
    p.add_argument("--no-push", action="store_true")
    p.set_defaults(fn=cmd_snap)
    p = sub.add_parser("result")
    p.add_argument("project")
    p.add_argument("number", type=int)
    p.add_argument("text")
    p.set_defaults(fn=cmd_result)
    for name, fn in (("list", cmd_list), ("which", cmd_which)):
        p = sub.add_parser(name)
        p.add_argument("project")
        p.set_defaults(fn=fn)
    p = sub.add_parser("restore")
    p.add_argument("project")
    p.add_argument("number", type=int)
    p.add_argument("--yes", action="store_true")
    p.add_argument("--force-missing", action="store_true")
    p.set_defaults(fn=cmd_restore)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
