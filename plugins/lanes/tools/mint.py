#!/usr/bin/env python3
"""mint.py - keep the untouched app in mint condition, and do all modding in a private copy.

    mint.py guide       <project>                     how to get a truly clean install (printed steps)
    mint.py fingerprint <project>                     record every file of the clean install (read-only)
    mint.py check       <project> [--copy]            compare the clean install (or the copy) with that record
    mint.py copy        <project> --to DIR [--yes] [--steam-appid N]
                                                      make the private working copy, verified file by file
    mint.py status      <project>                     what is set up, and whether the clean install still matches
    mint.py scripts     <project> [--repo DIR]        find the project's OWN scripts that still name the clean
                                                      install (a deploy/install step would write into it)

WHY (0.27.0)
  A bug followed a game through three "clean" reinstalls: every file that was not the game's own was
  moved out, the store verified the rest, and the bug stayed. Only deleting the whole game folder and
  installing it again removed it - something left over from months of modding had survived every
  partial clean, and nobody could say which file. The person's answer: "keep the vanilla game in mint
  condition", and do the modding in a separate copy. Then the clean install is a fixed reference that
  nothing ever writes into, a fingerprint says in seconds whether it is still clean, and a test copy
  can be thrown away and remade from it whenever a result stops making sense.

SCRIPTS STILL POINTING AT THE CLEAN INSTALL (0.27.1)
  The same day the copy was made, four of the project's own tools (a build script's --deploy, an asset
  installer, a game driver, an old snapshot tool) were found still naming the real game folder. mint.py
  and builds.py refuse to write there, but a project's own scripts know nothing of that. `scripts` reads
  the project repo for any script that names the clean install, in any spelling (backslashes, C:/..., /c/...),
  and says where to point it instead. `check` runs it too, so every session start sees it.

WHAT IT NEVER DOES
  - It never writes into the clean install. Every command only reads it.
  - It never uploads or commits anything. Fingerprints stay on this PC (`mint_home`).
  - It refuses to make the copy inside a git repo, inside a cloud-synced folder, or inside the clean
    install, because the copy is the game's own files and must never leave this PC. Sharing them is
    illegal; the copy carries a notice saying so.

WHERE THINGS ARE (lanes.conf, all per PC)
  mint_home = <local folder for fingerprints>          (default ~/.claude/lanes/mint)
  mint_vanilla.<project> = <the clean install>         nothing of ours ever goes in here
  mint_copy.<project> = <the private working copy>     builds.py uses this as the app folder
  mint_normal.<project> = <pattern>                    repeatable: files the app rewrites itself when it
                                                       runs (settings, logs), reported but not a fault
"""
import argparse
import datetime
import fnmatch
import hashlib
import os
import re
import shutil
import subprocess
import sys

# ---- settings (named numbers and words, one place) ----------------------------------------------
HASH_CHUNK = 1 << 20                  # bytes read per step while hashing (large game archives)
LIST_MAX = 40                         # files listed per section before "... and N more"
FP_PREFIX = "fingerprint-"
FP_SUFFIX = ".sha256"
NOTICE_FILE = "NOT-FOR-SHARING.txt"
SCRIPT_EXTS = (".sh", ".bash", ".py", ".ps1", ".psm1", ".bat", ".cmd", ".lua", ".js", ".cmake")   # files that can
                                      # run a deploy/install step (logs and notes only record paths, so they are skipped)
SCRIPT_OK_MARK = "mint-ok"            # a line (or the line above it) carrying this is a deliberate read-only use
SCRIPT_SKIP_DIRS = (".git", "node_modules", "build", "__pycache__")
SCRIPT_MAX_BYTES = 2 << 20            # skip anything bigger (generated dumps, not scripts)
SYNC_WORDS = ("onedrive", "dropbox", "google drive", "googledrive", "icloud")   # folder names that sync

NOTICE = """\
PRIVATE COPY - FOR MODDING ON THIS PC ONLY

This folder is a copy of a game you own, made only so you can mod and test it
on this computer without touching the real installation.

Sharing these files is illegal. The game's files belong to its publisher, and
giving them to anyone else - uploading them, putting them in a git repository
or a cloud-synced folder, sending them, or packing them into a mod - is
copyright infringement.

- Keep this copy on this PC. Do not move it into a synced or shared folder.
- Share only the files you made yourself.
- Delete the copy when you no longer need it.
"""

GUIDE = """\
A TRULY CLEAN INSTALL - why the usual ways are not enough

  "Verify files" only repairs the game's own files; it leaves every extra file where it is.
  Moving "everything that is not the game's" out by hand can miss a file, and you cannot
  tell which. Only an uninstall AND deleting what is left of the folder is certain.

STEAM (other stores work the same way: uninstall, delete the leftover folder, install)
  1. Save anything of yours from the game folder first (mod files, settings you want).
     The session can move all of it to a safe folder for you.
  2. Saves: most games keep them outside the game folder or in Steam Cloud. If yours are
     inside the game folder, copy them out too.
  3. Steam library -> right-click the game -> Manage -> Uninstall.
  4. Open the folder the game was in (steamapps/common/<game>). If it is still there, it
     holds only what Steam did not install - delete it.
  5. Install the game again from Steam.
  6. Start it once with nothing added, reach the main menu, and close it.
  7. Tell the session. It fingerprints the clean install, so "is it still clean?" becomes a
     check that takes seconds.

  From then on nothing of yours goes into that folder. Modding happens in a private copy
  (mint.py copy), which stays on this PC and is never shared.
"""


# ---- config -------------------------------------------------------------------------------------
def conf_candidates():
    if os.environ.get("LANES_CONFIG"):
        return [os.environ["LANES_CONFIG"]]
    return [os.path.expanduser("~/.claude/lanes.conf"), os.path.expanduser("~/.config/lanes/lanes.conf")]


def conf_all(key):
    pat = re.compile(r"^\s*" + re.escape(key) + r"\s*=\s*(.*?)\s*$")
    out = []
    for path in conf_candidates():
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.lstrip().startswith("#"):
                    continue
                m = pat.match(line.rstrip("\r\n"))
                if m:
                    out.append(m.group(1).strip().strip('"').strip("'"))
        if out:
            break
    return out


def conf_get(key):
    vals = conf_all(key)
    return vals[0] if vals else ""


def mint_home():
    return os.environ.get("LANES_MINT_HOME", "") or conf_get("mint_home") or \
        os.path.expanduser("~/.claude/lanes/mint")


def vanilla_of(project, required=True):
    v = conf_get(f"mint_vanilla.{project}")
    if required and not v:
        sys.exit(f"mint.py: no clean install set for {project}. Add `mint_vanilla.{project} = <game folder>` "
                 "to lanes.conf (after a clean reinstall - `mint.py guide` says how).")
    if required and not os.path.isdir(v):
        sys.exit(f"mint.py: the clean install folder is not there: {v!r}")
    return v


def norm(p):
    return os.path.normcase(os.path.abspath(p)).rstrip("\\/")


def inside(child, parent):
    c, p = norm(child), norm(parent)
    return c == p or c.startswith(p + os.sep)


# ---- files --------------------------------------------------------------------------------------
def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(HASH_CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def tree(folder, skip=()):
    """rel path (forward slashes) -> sha256, for every file under folder."""
    out = {}
    for base, dirs, files in os.walk(folder):
        dirs.sort()
        for name in sorted(files):
            full = os.path.join(base, name)
            rel = os.path.relpath(full, folder).replace("\\", "/")
            if rel in skip:
                continue
            out[rel] = sha(full)
    return out


def write_manifest(path, state):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for rel in sorted(state):
            f.write(f"{state[rel]}  {rel}\n")


def read_manifest(path):
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if "  " in line:
                digest, rel = line.split("  ", 1)
                out[rel] = digest
    return out


def fingerprints(project):
    d = os.path.join(mint_home(), project)
    if not os.path.isdir(d):
        return []
    return sorted(os.path.join(d, n) for n in os.listdir(d) if n.startswith(FP_PREFIX) and n.endswith(FP_SUFFIX))


def latest_fingerprint(project):
    fps = fingerprints(project)
    if not fps:
        sys.exit(f"mint.py: {project} has no fingerprint yet - run `mint.py fingerprint {project}` on the "
                 "clean install first.")
    return fps[-1]


def compare(record, now, normal):
    added = sorted(set(now) - set(record))
    removed = sorted(set(record) - set(now))
    changed = sorted(r for r in set(now) & set(record) if now[r] != record[r])
    is_normal = lambda r: any(fnmatch.fnmatch(r, p) or fnmatch.fnmatch(os.path.basename(r), p) for p in normal)
    faults = [("added", r) for r in added] + [("removed", r) for r in removed] + \
             [("changed", r) for r in changed if not is_normal(r)]
    normals = [r for r in changed if is_normal(r)]
    return faults, normals


def show(items, label):
    print(f"  {label}: {len(items)}")
    for it in items[:LIST_MAX]:
        print(f"    {it}")
    if len(items) > LIST_MAX:
        print(f"    ... and {len(items) - LIST_MAX} more")


# ---- guards for the copy ------------------------------------------------------------------------
def in_git_repo(path):
    probe = path
    while not os.path.isdir(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            return False
        probe = parent
    r = subprocess.run(["git", "-C", probe, "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == "true"


def synced(path):
    parts = norm(path).lower().replace("\\", "/").split("/")
    return next((w for w in SYNC_WORDS for part in parts if part.startswith(w)), "")


def copy_refusal(vanilla, dest):
    if inside(dest, vanilla):
        return "the copy cannot go inside the clean install - that would change the clean install"
    if inside(vanilla, dest):
        return "the copy cannot be a folder that contains the clean install"
    if in_git_repo(dest):
        return ("that folder is inside a git repository - the copy is the game's own files and must never "
                "be committed or pushed. Pick a plain folder outside every repo")
    w = synced(dest)
    if w:
        return (f"that folder looks cloud-synced ({w}) - the copy must stay on this PC only. "
                "Pick a plain local folder")
    if os.path.isdir(dest) and os.listdir(dest):
        return "that folder is not empty - pick a new or empty folder, so nothing old mixes into the copy"
    return ""


# ---- commands -----------------------------------------------------------------------------------
def cmd_guide(a):
    print(GUIDE)
    v = conf_get(f"mint_vanilla.{a.project}")
    print(f"  clean install for {a.project}: {v or '(not set yet)'}")


def cmd_fingerprint(a):
    v = vanilla_of(a.project)
    state = tree(v)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S")
    path = os.path.join(mint_home(), a.project, f"{FP_PREFIX}{stamp}{FP_SUFFIX}")
    write_manifest(path, state)
    print(f"fingerprinted the clean install of {a.project}: {len(state)} files")
    print(f"  kept on this PC only: {path}")


def cmd_check(a):
    folder = conf_get(f"mint_copy.{a.project}") if a.copy else vanilla_of(a.project)
    if a.copy and not folder:
        sys.exit(f"mint.py: no copy set for {a.project} (mint_copy.{a.project} in lanes.conf).")
    fp = latest_fingerprint(a.project)
    record = read_manifest(fp)
    now = tree(folder, skip=(NOTICE_FILE,) if a.copy else ())
    faults, normals = compare(record, now, conf_all(f"mint_normal.{a.project}"))
    what = "the copy" if a.copy else "the clean install"
    print(f"{what} of {a.project} against {os.path.basename(fp)}")
    if normals:
        show(normals, "changed by the app itself (normal)")
    scripts_bad = 0 if a.copy else report_scripts(a.project, default_repo(a.project))
    if not faults:
        print(f"  {what} matches the fingerprint" + (" - still mint" if not a.copy else ""))
        return scripts_bad
    if a.copy:
        show([f"{k}: {r}" for k, r in faults], "differs from the clean install (your changes)")
        return 0
    show([f"{k}: {r}" for k, r in faults], "NOT MINT any more")
    print("  something wrote into the clean install. Find out what before trusting any test against it.")
    return 1


def path_spellings(folder):
    """Every way a script may write this folder: backslashes (single or doubled), C:/x, /c/x (lower-cased)."""
    f = os.path.abspath(folder).rstrip("\\/")
    fwd = f.replace("\\", "/")
    out = {f.lower(), fwd.lower(), f.replace("\\", "\\\\").lower()}
    m = re.match(r"^([A-Za-z]):/(.*)$", fwd)
    if m:
        out.add(f"/{m.group(1).lower()}/{m.group(2)}".lower())
    return sorted(out, key=len, reverse=True)


def scan_scripts(project, repo):
    """(file, line number, line) for every script line that names the clean install."""
    v = conf_get(f"mint_vanilla.{project}")
    if not v or not repo or not os.path.isdir(repo):
        return []
    spell = path_spellings(v)
    hits = []
    for base, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SCRIPT_SKIP_DIRS]
        for n in files:
            if not n.lower().endswith(SCRIPT_EXTS):
                continue
            path = os.path.join(base, n)
            try:
                if os.path.getsize(path) > SCRIPT_MAX_BYTES:
                    continue
                with open(path, encoding="utf-8", errors="replace") as f:
                    prev = ""
                    for i, line in enumerate(f, 1):
                        low = line.lower()
                        if any(sp in low for sp in spell) and SCRIPT_OK_MARK not in low and SCRIPT_OK_MARK not in prev:
                            hits.append((os.path.relpath(path, repo), i, line.strip()[:140]))
                        prev = low
            except OSError:
                continue
    return hits


def default_repo(project):
    root = conf_get("root")
    return os.path.join(root, project) if root else ""


def report_scripts(project, repo):
    if not repo or not os.path.isdir(repo):
        return 0      # no repo known on this PC (no `root` in lanes.conf): nothing to read, nothing to say
    hits = scan_scripts(project, repo)
    if not hits:
        print(f"  no script in {repo} names the clean install")
        return 0
    c = conf_get(f"mint_copy.{project}")
    print(f"  {len(hits)} script line(s) in {repo} still name the CLEAN INSTALL - a deploy or install step there")
    print(f"  would write into it. Point them at the private copy{(' (' + c + ')') if c else ''}:")
    by_file = {}
    for rel, i, line in hits:
        by_file.setdefault(rel, []).append((i, line))
    for rel, lines in list(by_file.items())[:LIST_MAX]:
        i, line = lines[0]
        more = f"  (+{len(lines) - 1} more lines)" if len(lines) > 1 else ""
        print(f"    {rel}:{i}: {line}{more}")
    if len(by_file) > LIST_MAX:
        print(f"    ... and {len(by_file) - LIST_MAX} more files")
    print(f"  A deliberate read-only use (reading the game's archives, say) can carry a `{SCRIPT_OK_MARK}` comment on")
    print("  that line or the line above; it is then not listed.")
    return 1


def cmd_scripts(a):
    vanilla_of(a.project)
    return report_scripts(a.project, a.repo or default_repo(a.project))


def cmd_copy(a):
    v = vanilla_of(a.project)
    dest = os.path.abspath(a.to)
    why = copy_refusal(v, dest)
    if why:
        sys.exit(f"mint.py: refused - {why}.")
    print(NOTICE)
    print(f"copy {v}\n  to {dest}")
    if not a.yes:
        print("  dry run - add --yes to make the copy")
        return 0
    fp = latest_fingerprint(a.project)
    record = read_manifest(fp)
    faults, _ = compare(record, tree(v), conf_all(f"mint_normal.{a.project}"))
    if faults:
        show([f"{k}: {r}" for k, r in faults], "the clean install is NOT mint")
        sys.exit("mint.py: refused - copying a clean install that is no longer clean copies the problem too.")
    source = tree(v)
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    shutil.copytree(v, dest, dirs_exist_ok=True)
    copied = tree(dest)
    if copied != source:
        bad = sorted(set(source) ^ set(copied)) + sorted(r for r in source if copied.get(r) not in (None, source[r]))
        show(bad, "the copy does not match")
        sys.exit("mint.py: the copy is not identical - do not use it; delete it and try again.")
    with open(os.path.join(dest, NOTICE_FILE), "w", encoding="utf-8", newline="\n") as f:
        f.write(NOTICE)
    if a.steam_appid:
        with open(os.path.join(dest, "steam_appid.txt"), "w", encoding="utf-8", newline="") as f:
            f.write(str(a.steam_appid))
    print(f"  done: {len(copied)} files, every one identical to the clean install; {NOTICE_FILE} written")
    print("  add to lanes.conf on this PC (builds.py then works in the copy):")
    print(f"    mint_copy.{a.project} = {dest}")
    return 0


def cmd_status(a):
    v = conf_get(f"mint_vanilla.{a.project}")
    c = conf_get(f"mint_copy.{a.project}")
    fps = fingerprints(a.project)
    print(f"{a.project}")
    print(f"  clean install : {v or '(not set)'}")
    print(f"  private copy  : {c or '(not set)'}")
    print(f"  fingerprints  : {len(fps)}" + (f", latest {os.path.basename(fps[-1])}" if fps else ""))
    if v and fps and os.path.isdir(v):
        return cmd_check(argparse.Namespace(project=a.project, copy=False))
    return 0


def cmd_where(a):
    """Which folder a live session runs the app from (0.42.0). The private copy, whenever one exists,
    unless the project is marked `work_in_original.<project> = <why>` (reverse-engineering stage,
    before hands-on fine tuning). Prints one line a session can act on; exit 0 = a folder was named."""
    v = conf_get(f"mint_vanilla.{a.project}")
    c = conf_get(f"mint_copy.{a.project}")
    why = conf_get(f"work_in_original.{a.project}")
    if why:
        print(f"ORIGINAL  {v or '(original folder not set in lanes.conf)'}")
        print(f"  why: work_in_original.{a.project} = {why}")
        print("  (reverse-engineering stage: work in the game's own folder until hands-on fine tuning;"
              " remove that line to move to the copy)")
        return 0
    if c and os.path.isdir(c):
        print(f"COPY      {c}")
        print("  run, deploy and launch from this folder; start its own exe, never through the store"
              " (the store starts the original)")
        return 0
    if c:
        print(f"MISSING   {c}")
        print("  a copy is set in lanes.conf but the folder is not there; say so before launching")
        return 1
    print(f"NO-COPY   {v or '(no folder set)'}")
    print("  no private copy is set for this project; the original folder is the only one")
    return 0


def main():
    p = argparse.ArgumentParser(description="keep the clean install mint; mod in a private copy")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("guide", "fingerprint", "status", "where"):
        sub.add_parser(name).add_argument("project")
    c = sub.add_parser("check")
    c.add_argument("project")
    c.add_argument("--copy", action="store_true", help="check the private copy instead")
    c = sub.add_parser("scripts")
    c.add_argument("project")
    c.add_argument("--repo", default="", help="the project repo (default: <root>/<project> from lanes.conf)")
    c = sub.add_parser("copy")
    c.add_argument("project")
    c.add_argument("--to", required=True)
    c.add_argument("--yes", action="store_true")
    c.add_argument("--steam-appid", type=int, default=0,
                   help="write steam_appid.txt so the copy starts itself instead of Steam starting the real one")
    a = p.parse_args()
    return {"guide": cmd_guide, "fingerprint": cmd_fingerprint, "check": cmd_check,
            "copy": cmd_copy, "status": cmd_status, "scripts": cmd_scripts,
            "where": cmd_where}[a.cmd](a) or 0


if __name__ == "__main__":
    sys.exit(main())
