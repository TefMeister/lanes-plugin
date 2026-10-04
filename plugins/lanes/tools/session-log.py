#!/usr/bin/env python3
"""session-log - keep every session summary, dated, in its own folder per project.

    python session-log.py write <project> <slug>          the summary comes from stdin; saved as
                                                          <session_logs>/<project>/YYYY-MM-DD_HHMM_<slug>.md
    python session-log.py list <project> [--last N]       that project's logs, newest first (default 10)
    python session-log.py search <words> [--project P]    every log that mentions all the words, newest first

WHY (0.44.0)
  The write-up at the end of a session is the clearest account of what happened: what was changed, what the
  person saw, what is being waited on. It scrolled away with the terminal. A person asked for every one of them
  to be kept, "dated and time stamped, in their own folders for each different project", and for them to be
  the first place to look when a problem keeps coming back.

  Text, not screenshots: a few hundred bytes, searchable, and a later session can read it without image cost.

WHERE
  `session_logs = <folder>` in lanes.conf. When that folder is a git clone, every write is committed and pushed
  (only the new file is staged, then pull --rebase, then push), so the logs reach the other PC. Keep the repo
  PRIVATE: summaries talk about work in progress. Not set = the tool says so and does nothing.

WHEN STUCK
  Before trying a fix for the third time, run `search` with the symptom's words. Earlier sessions often met the
  same thing, and their summaries say what was tried and what the person saw.
"""
import datetime
import os
import re
import subprocess
import sys

KEY = "session_logs"
DEFAULT_LAST = 10                      # how many logs `list` prints when not told
SLUG_MAX = 48                          # characters kept from a slug
GIT_TIMEOUT_S = 60


def conf_path():
    p = os.environ.get("LANES_CONFIG")
    if p:
        return p
    return os.path.join(os.path.expanduser("~"), ".claude", "lanes.conf")


def read_conf():
    conf = {}
    try:
        with open(conf_path(), encoding="utf-8") as f:
            for line in f:
                m = re.match(r"^\s*([A-Za-z_]+)\s*=\s*(.*?)\s*(#.*)?$", line)
                if m and not line.lstrip().startswith("#"):
                    conf[m.group(1)] = m.group(2).strip()
    except OSError:
        pass
    return conf


def git(args, cwd):
    try:
        r = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=GIT_TIMEOUT_S,
                           encoding="utf-8", errors="replace")
        return r.returncode == 0, ((r.stdout or "") + (r.stderr or "")).strip()
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)


def clean(name):
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip("-.")
    return name[:SLUG_MAX] or "session"


def logs_root():
    root = read_conf().get(KEY, "")
    if not root:
        print("session-log: `session_logs = <folder>` is not set in lanes.conf, so nothing is kept.")
        return None
    return os.path.expanduser(root)


def write(project, slug, body):
    root = logs_root()
    if not root:
        return 1
    if not body.strip():
        print("session-log: nothing on stdin, nothing written.")
        return 1
    now = datetime.datetime.now()
    folder = os.path.join(root, clean(project))
    os.makedirs(folder, exist_ok=True)
    name = f"{now:%Y-%m-%d_%H%M}_{clean(slug)}.md"
    path = os.path.join(folder, name)
    n = 2
    while os.path.exists(path):                          # two in one minute: never overwrite
        path = os.path.join(folder, f"{now:%Y-%m-%d_%H%M}_{clean(slug)}-{n}.md")
        n += 1
    machine = read_conf().get("machine_name", "")
    head = f"<!-- {now:%Y-%m-%d %H:%M}{' on ' + machine if machine else ''} -->\n"
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(head + body.rstrip() + "\n")
    rel = os.path.relpath(path, root).replace(os.sep, "/")
    print(f"session-log: saved {rel}")
    if os.path.isdir(os.path.join(root, ".git")):
        steps = [["add", "--", rel], ["commit", "-q", "-m", f"session log: {rel}"],
                 ["pull", "-q", "--rebase"], ["push", "-q"]]
        for step in steps:
            ok, out = git(step, root)
            if not ok:
                print(f"session-log: saved on this PC, but `git {step[0]}` failed: {out[:200]}")
                return 1
        print("session-log: pushed")
    return 0


def all_logs(root, project=None):
    found = []
    for proj in sorted(os.listdir(root)):
        d = os.path.join(root, proj)
        if proj.startswith(".") or not os.path.isdir(d) or (project and proj != clean(project)):
            continue
        for fn in os.listdir(d):
            if fn.endswith(".md"):
                found.append((fn, proj, os.path.join(d, fn)))
    found.sort(reverse=True)                             # file names start with the date: newest first
    return found


def list_logs(project, last):
    root = logs_root()
    if not root or not os.path.isdir(root):
        return 1
    for fn, proj, _ in all_logs(root, project)[:last]:
        print(f"{proj}/{fn}")
    return 0


def search(words, project):
    root = logs_root()
    if not root or not os.path.isdir(root):
        return 1
    want = [w.lower() for w in words]
    hits = 0
    for fn, proj, path in all_logs(root, project):
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        low = text.lower()
        if all(w in low for w in want):
            hits += 1
            print(f"== {proj}/{fn}")
            for line in text.splitlines():
                if any(w in line.lower() for w in want):
                    print("   " + line.strip()[:200])
    if not hits:
        print("session-log: no log mentions all of: " + " ".join(words))
    return 0


def main(argv):
    if len(argv) >= 3 and argv[0] == "write":
        return write(argv[1], argv[2], sys.stdin.read())
    if len(argv) >= 2 and argv[0] == "list":
        last = DEFAULT_LAST
        if "--last" in argv:
            last = int(argv[argv.index("--last") + 1])
        return list_logs(argv[1], last)
    if len(argv) >= 2 and argv[0] == "search":
        project = None
        words = argv[1:]
        if "--project" in words:
            i = words.index("--project")
            project = words[i + 1]
            words = words[:i] + words[i + 2:]
        return search(words, project)
    print(__doc__.split("WHY")[0].strip())
    return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
