"""estate.py - set up a fresh GitHub account the way Lanes works best (0.78.0, 2026-10-18, user-directed: "add it",
after asking whether Lanes offers to set up a dedicated GitHub account with all the systems we have going on, "the
folders, guards and countless other mechanics that make it all work").

The person makes the GitHub account and signs `gh` in to it themselves (docs/NEW-ACCOUNT.md walks them through it).
This tool then builds everything else, and never deletes, overwrites or makes anything public on its own.

    python estate.py check                       what is set up on this PC and on GitHub, and what is missing
    python estate.py plan  --root <folder>       what `make` would do, doing nothing
    python estate.py make  --root <folder>       make the private base repos, clone them, make the lane roots,
                                                 and write their places into lanes.conf
         [--skip ideas,staging,builds,logs]      leave some of the base repos out
         [--name board=my-board]                 a different name for one (repeatable)
    python estate.py project <name> [--public]   a new project repo with its lane folders, cloned into every lane
                                                 root, plus its page on the board (private unless --public)

The base repos (all PRIVATE):
    board         the shared work board: status/<project>.md, machine-assignments.tsv, owed/ reminders
    ideas         where ideas are written down as they come and filed later (/lanes:ideas)
    staging       unfinished work and hand-offs between PCs, one folder per project
    builds        every installed change as its own numbered version (tools/builds.py)
    session-logs  every session's write-up, one folder per project (tools/session-log.py)

Run `make` again on a second PC with the same names: whatever is already on GitHub is cloned, nothing is made twice.
LANES_GH points at a different gh (tests); LANES_CONFIG at a different lanes.conf.
"""
import os
import re
import shutil
import subprocess
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
GH = os.environ.get("LANES_GH") or "gh"
GH_TIMEOUT_S = 120        # one gh call; creating and pushing a small repo takes a few seconds
GIT_TIMEOUT_S = 120
SYNC_TIMEOUT_S = 600      # root-sync.sh copying every repo into four lane roots
LANE_SUFFIXES = ("-pd", "-gr", "-sr", "-gs")   # the lane roots root-sync.sh finds by itself
NAME_OK = re.compile(r"^[A-Za-z0-9._-]{1,100}$")

# key: (default repo name, lanes.conf key or None, what it is)
BASE = {
    "board": ("board", "board", "the shared work board"),
    "ideas": ("ideas", "ideas", "ideas, written down as they come"),
    "staging": ("staging", None, "unfinished work and hand-offs between PCs"),
    "builds": ("builds", "builds", "every installed change as a numbered version"),
    "logs": ("session-logs", "session_logs", "every session's write-up"),
}


# ---------- lanes.conf ----------

def conf_file():
    if os.environ.get("LANES_CONFIG"):
        return os.environ["LANES_CONFIG"]
    for c in (os.path.expanduser("~/.claude/lanes.conf"), os.path.expanduser("~/.config/lanes/lanes.conf")):
        if os.path.exists(c):
            return c
    return os.path.expanduser("~/.claude/lanes.conf")


def conf_get(key):
    try:
        for line in open(conf_file(), encoding="utf-8"):
            k, sep, v = line.partition("=")
            if sep and k.strip() == key:
                return v.split(" #")[0].strip().strip('"')
    except OSError:
        pass
    return None


def conf_set(key, value, note):
    """Add `key = value`. Never changes a key that already holds something else; returns what happened."""
    have = conf_get(key)
    if have and same_path(have, value):
        return "already set"
    if have:
        return f"NOT changed: lanes.conf already says {key} = {have}"
    p = conf_file()
    try:
        text = open(p, encoding="utf-8").read()
    except OSError:
        text = ""
    if text and not text.endswith("\n"):
        text += "\n"
    text += f"{key} = {value}   # {note} (estate.py)\n"
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return "written"


def same_path(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


# ---------- gh and git ----------

def run(args, cwd=None, timeout=GIT_TIMEOUT_S):
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, "", str(e)


def gh(*args):
    return run([GH, *args], timeout=GH_TIMEOUT_S)


def gh_login():
    """The signed-in GitHub account's name, or None."""
    rc, _, _ = gh("auth", "status")
    if rc != 0:
        return None
    rc, out, _ = gh("api", "user", "--jq", ".login")
    return out.splitlines()[0].strip() if rc == 0 and out else None


def on_github(owner, name):
    return gh("repo", "view", f"{owner}/{name}", "--json", "name")[0] == 0


def is_clone(path):
    return os.path.isdir(os.path.join(path, ".git"))


def commit_identity(owner):
    """-c options for a commit when git has no name/e-mail set, so the first commit never stops a beginner.
    Uses the display name and GitHub's private no-reply address, never anything personal."""
    if run(["git", "config", "user.email"])[1]:
        return []
    name = conf_get("display_name") or "User"
    rc, uid, _ = gh("api", "user", "--jq", ".id")
    email = f"{uid}+{owner}@users.noreply.github.com" if rc == 0 and uid.isdigit() else f"{owner}@users.noreply.github.com"
    return ["-c", f"user.name={name}", "-c", f"user.email={email}"]


def first_push(folder, name, owner, public, message):
    """git init + first commit in `folder`, then make the GitHub repo from it and push. Returns (ok, detail)."""
    ident = commit_identity(owner)
    for args in (["git", "init", "-q", "-b", "main"], ["git", "add", "-A"],
                 ["git", *ident, "commit", "-q", "-m", message]):
        rc, _, err = run(args, cwd=folder)
        if rc != 0:
            return False, f"{' '.join(args[:2])} failed: {err[:200]}"
    vis = "--public" if public else "--private"
    rc, _, err = gh("repo", "create", name, vis, "--source", folder, "--remote", "origin", "--push")
    if rc != 0:
        return False, f"GitHub would not make it: {err[:300]}"
    return True, "made on GitHub (" + ("PUBLIC" if public else "private") + ") and pushed"


# ---------- what goes in each new repo ----------

def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def fill_base(key, folder):
    if key == "board":
        shutil.copytree(os.path.join(PLUGIN, "template-board"), folder, dirs_exist_ok=True)
        ex = os.path.join(folder, "status", "example-project.md")
        if os.path.exists(ex):
            os.remove(ex)
        write(os.path.join(folder, "status", ".gitkeep"), "")
        write(os.path.join(folder, "owed", "README.md"), OWED_README)
    elif key == "ideas":
        shutil.copytree(os.path.join(PLUGIN, "template-ideas"), folder, dirs_exist_ok=True)
    else:
        write(os.path.join(folder, "README.md"), BASE_READMES[key])


OWED_README = """# Reminders for one PC

A job that only one PC can do (an install, a test that needs hardware only it has) is queued here for that PC,
one file per job in `owed/<PC>/`, by `tools/owed.sh add`. That PC is told about it at its next session start, and
the file goes when the job is done. Nothing else lives here.
"""

BASE_READMES = {
    "staging": """# Staging

Unfinished work and hand-offs between your PCs, one folder per project (`<project>/`). Anything here is not
proven yet: when it works, it moves into the project's own repo. Keep this repo private.
""",
    "builds": """# Builds

Every change installed into an app is saved here as its own numbered version, so any PC can go back to any
build. `tools/builds.py init <project>` sets a project up the first time it needs it (PROTOCOL section 14).
Keep this repo private.
""",
    "logs": """# Session logs

Every session's write-up, one folder per project, one dated file per summary (`tools/session-log.py`). When a
problem keeps coming back, sessions search these first. Keep this repo private.
""",
}

PROJECT_FILES = {
    "README.md": """# {name}

| Folder | What it holds | Who edits it |
| --- | --- | --- |
| `dev-archive/` | the working source and its full history: code, test logs, evidence | the working sessions (/pd, /lm, /ms) |
| `notes/` | readable progress notes, newest first | the working sessions |
| `engine-research/` | `ENGINE-DOSSIER.md`: what is known about how the app works, and the dead ends | the working sessions |
| `external-research/` | what other people have published about it, with sources | only /gr |

Every folder that another lane may add to has an `inbox/`: drop a new file there, never edit someone else's.
The project's open work is on the board, in `status/{name}.md`.
""",
    "dev-archive/README.md": """# Dev archive

The live source of {name} and everything that led to it: code, builds' notes, logs, screenshots of results.
Probes and tests that were disproved move to `archive/`, with one line here saying why.
""",
    "notes/README.md": """# Notes

Readable progress notes for {name}, one dated entry per notable success or failure, newest first.
""",
    "engine-research/ENGINE-DOSSIER.md": """# {name}: engine dossier

Every claim carries a tag saying how well it is known: [verified-live YYYY-MM-DD, n=K], [measured YYYY-MM-DD],
[verified-numerically YYYY-MM-DD, n=K], [compile-verified YYYY-MM-DD], [inferred-static], [reported],
[hypothesis], [disproved YYYY-MM-DD]. Untagged means [hypothesis].

## 1. What it is
(engine, version, store, how it is launched)

## 2. How it is built
(renderer, main modules, how the camera and input work)

## 3. Where things are
(addresses, files, functions, with the build they were found in)

## 4. Settings and switches
(window size, music volume, blur and screen effects, where each lives)

## 5. Dead ends
(what was tried and did not work, and why; research reads this first)
""",
    "engine-research/inbox/README.md": """# Inbox

Other lanes drop findings for this folder here, as NEW files named `YYYY-MM-DD-<lane>-<slug>.md`. Never edit
or delete a file in here; the owner folds each one into the dossier at session start and deletes only the files
it read.
""",
    "external-research/INDEX.md": """# {name}: what others have published

One line per lead: what it is, where it is (a link), when it was checked, and its status
(`new` / `tried, worked` / `tried, did not work` / `not for us`). Only /gr edits this file.
""",
    "external-research/inbox/README.md": """# Inbox

Working sessions drop their verdicts on a lead here ("tried it, it worked"), as NEW files named
`YYYY-MM-DD-<lane>-<slug>.md`. Never edit or delete a file in here; /gr folds them into INDEX.md.
""",
}

BOARD_PAGE = """## {name}

OPEN ({today}):
  [PD]        read what is already known about {name} and write the first page of its dossier

- **{today} - project started.** Its repo has the lane folders; the dossier is empty.
"""


# ---------- commands ----------

def base_names(argv):
    names = {k: v[0] for k, v in BASE.items()}
    skip = set()
    i = 0
    while i < len(argv):
        if argv[i] == "--skip" and i + 1 < len(argv):
            skip |= {s.strip() for s in argv[i + 1].split(",") if s.strip()}
            i += 2
        elif argv[i] == "--name" and i + 1 < len(argv):
            k, _, v = argv[i + 1].partition("=")
            if k not in BASE or not NAME_OK.match(v):
                raise SystemExit(f"--name wants <one of {', '.join(BASE)}>=<repo name>, not {argv[i + 1]}")
            names[k] = v
            i += 2
        else:
            i += 1
    bad = skip - set(BASE)
    if bad:
        raise SystemExit(f"--skip knows {', '.join(BASE)}, not {', '.join(sorted(bad))}")
    if "board" in skip:
        raise SystemExit("the board cannot be skipped: every lane reads it")
    return {k: n for k, n in names.items() if k not in skip}


def arg_value(argv, flag):
    if flag in argv:
        i = argv.index(flag)
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def lane_roots(root):
    """`lane_roots` from lanes.conf when set (comma-separated, as root-sync.sh reads it), else <root>-pd, -gr ..."""
    listed = [p.strip() for p in (conf_get("lane_roots") or "").split(",") if p.strip()]
    return listed or [root.rstrip("/\\") + s for s in LANE_SUFFIXES]


def sync_lane_roots(root):
    for lr in lane_roots(root):
        os.makedirs(lr, exist_ok=True)
    bash = shutil.which("bash")
    if not bash:
        return "the lane roots were made, but bash was not found to copy the repos into them: run tools/root-sync.sh --fix"
    rc, out, err = run([bash, os.path.join(HERE, "root-sync.sh"), "--fix", root], timeout=SYNC_TIMEOUT_S)
    return "every lane root holds every repo" if rc == 0 else f"copying into the lane roots failed: {(err or out)[:300]}"


def cmd_check():
    login = gh_login()
    print("GitHub:", f"signed in as {login}" if login else "NOT signed in (docs/NEW-ACCOUNT.md, steps 2 and 3)")
    root = conf_get("root")
    print("clone root:", root or "not set (make --root <folder> sets it)")
    for key, (default, ck, what) in BASE.items():
        place = conf_get(ck) if ck else (os.path.join(root, default) if root else None)
        here = bool(place) and is_clone(place)
        online = on_github(login, os.path.basename(place) if place else default) if login else None
        state = "cloned here" if here else "not on this PC"
        state += "" if online is None else (", on GitHub" if online else ", not on GitHub")
        print(f"  {key:<8} {what}: {state}")
    if root:
        missing = [lr for lr in lane_roots(root) if not os.path.isdir(lr)]
        print("lane roots:", "all there" if not missing else "missing " + ", ".join(missing))
    return 0 if login else 1


def cmd_make(argv, dry):
    root = arg_value(argv, "--root") or conf_get("root")
    if not root:
        print("say where the clones should live: --root <folder>")
        return 2
    root = os.path.abspath(root)
    names = base_names(argv)
    owner = gh_login()
    if not owner:
        print("GitHub is not signed in on this PC. Do steps 2 and 3 of docs/NEW-ACCOUNT.md first, then run this again.")
        return 1
    if not dry:
        os.makedirs(root, exist_ok=True)
    print(("PLAN (nothing is done): " if dry else "") + f"repos for {owner}, clones in {root}")
    failed = False
    for key, name in names.items():
        default, ck, what = BASE[key]
        folder = os.path.join(root, name)
        if is_clone(folder):
            act = "already cloned here, left alone"
        elif os.path.exists(folder) and os.listdir(folder):
            act = "STOPPED: that folder exists and is not a clone; move it or pick another --name"
            failed = True
        elif on_github(owner, name):
            act = "on GitHub already: clone it"
            if not dry:
                rc, _, err = gh("repo", "clone", f"{owner}/{name}", folder)
                act = "cloned from GitHub" if rc == 0 else f"clone failed: {err[:200]}"
                failed |= rc != 0
        else:
            act = "make it (private) from the plugin's template, push it, keep the clone"
            if not dry:
                fill_base(key, folder)
                ok, act = first_push(folder, name, owner, False, f"{name}: start, from the lanes plugin")
                failed |= not ok
        line = f"  {name:<14} {what}: {act}"
        if ck and not dry and is_clone(folder):
            line += f"; lanes.conf {ck}: {conf_set(ck, folder, what)}"
        print(line)
    if dry:
        print("  lane roots: " + ", ".join(lane_roots(root)) + " (made, and given a copy of every repo)")
        print("  lanes.conf: root and the places above")
        return 0
    print("  lanes.conf root:", conf_set("root", root, "the folder holding every clone"))
    print("  lane roots:", sync_lane_roots(root))
    return 1 if failed else 0


def cmd_project(argv):
    if not argv or argv[0].startswith("-") or not NAME_OK.match(argv[0]):
        print("usage: estate.py project <name> [--public]   (letters, digits and . _ - only)")
        return 2
    name, public = argv[0], "--public" in argv
    root, board = conf_get("root"), conf_get("board")
    if not (root and board and is_clone(board)):
        print("run `estate.py make --root <folder>` first: the project needs the clone root and the board")
        return 1
    owner = gh_login()
    if not owner:
        print("GitHub is not signed in on this PC (docs/NEW-ACCOUNT.md, steps 2 and 3)")
        return 1
    folder = os.path.join(root, name)
    if is_clone(folder):
        print(f"{name}: already cloned here, left alone")
    elif os.path.exists(folder):
        print(f"{name}: STOPPED, {folder} exists and is not a clone")
        return 1
    elif on_github(owner, name):
        rc, _, err = gh("repo", "clone", f"{owner}/{name}", folder)
        print(f"{name}: on GitHub already, " + ("cloned" if rc == 0 else f"clone failed: {err[:200]}"))
        if rc != 0:
            return 1
    else:
        for rel, text in PROJECT_FILES.items():
            write(os.path.join(folder, rel), text.format(name=name))
        ok, detail = first_push(folder, name, owner, public, f"{name}: start, with the lane folders")
        print(f"{name}: {detail}")
        if not ok:
            return 1
    page = os.path.join(board, "status", f"{name}.md")
    if os.path.exists(page):
        print(f"board page status/{name}.md: already there, left alone")
    else:
        write(page, BOARD_PAGE.format(name=name, today=date.today().isoformat()))
        ident = commit_identity(owner)
        steps = (("add", ["git", "add", "--", f"status/{name}.md"]),
                 ("commit", ["git", *ident, "commit", "-q", "-m", f"{name}: board page", "--", f"status/{name}.md"]),
                 ("pull", ["git", "pull", "-q", "--rebase"]), ("push", ["git", "push", "-q"]))
        for label, args in steps:
            rc, _, err = run(args, cwd=board)
            if rc != 0:
                print(f"board page written, but git {label} failed: {err[:200]}")
                return 1
        print(f"board page status/{name}.md: written and pushed")
    print("lane roots:", sync_lane_roots(root))
    return 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "check":
        return cmd_check()
    if cmd in ("plan", "make"):
        return cmd_make(rest, cmd == "plan")
    if cmd == "project":
        return cmd_project(rest)
    print(__doc__)
    return 2


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):   # a character the console cannot show prints as ? (0.94.2)
        try:
            _stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))
