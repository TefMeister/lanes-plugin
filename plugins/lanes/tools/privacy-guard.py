#!/usr/bin/env python3
"""privacy-guard.py - refuses a commit that would put this PC's login, a home-folder path, the person's e-mail address
or a never-publish word on GitHub (0.86.0, 2026-10-25).

The maintainer, after finding the home PC's login and a home-folder path in published notes: "please see to it
that these are never added and if possible, make an iron rule in Lanes and in general to not add any of the actual
home pc username or file paths anywhere. only name Tefa is fine". The naming rule had said so since 0.40, and the
release scan (scrub-scan.py) checked the plugin itself, but nothing checked an ordinary commit: 27 repos had collected
the login in notes and old scripts, one by one, written by sessions that could see the rule. A rule a model applies
is behavioural; a git hook is not.

    python privacy-guard.py install       every git repository on this PC checks each commit (machine-wide hooks)
    python privacy-guard.py uninstall     puts the machine-wide hook setting back as it was
    python privacy-guard.py status        installed or not, and what is checked
    python privacy-guard.py staged        (pre-commit) check what is about to be committed; exit 1 = refused
    python privacy-guard.py message FILE  (commit-msg) check the commit message; exit 1 = refused
    python privacy-guard.py push NAME URL  (pre-push, 0.86.1) no personal e-mail on the pushed commits, none of the
                                          words in their messages; also stops old history coming back after a clean-up;
                                          (0.95.0) and the lines every pushed commit adds, as the commit check would
    python privacy-guard.py text [--public] < file   check any text (tests, and the gh-command hook)
    python privacy-guard.py audit [--quick]    (0.95.0) what GitHub already holds: every branch of every clone, and
                                          commits carrying your own e-mail (--quick: authors of the last 2 weeks)
    python privacy-guard.py private-words [add [WORD]]   the PC's own refuse-everywhere list (0.95.0)
    python privacy-guard.py drop-old-tags [--yes]   (0.95.0) old tags from before a history clean-up, still carrying
                                          the old details on this PC, swapped for GitHub's cleaned ones

WHAT IS REFUSED
  Everywhere, private repos too:
  - this PC's login name (unless it is the display name the person chose, lanes.conf display_name);
  - a home-folder path naming anyone but the display name or a placeholder: C:\\Users\\<user>, C:/Users/<user>,
    /c/Users/<user>, /home/<user>, /Users/<user> -- write ~ instead, or look the folder up when the code runs;
  - the e-mail address in this PC's git settings (git config user.email), unless it is a noreply address;
  - every word in ~/.claude/lanes/private-words.txt (0.95.0): the person's real e-mail address, the other PC's
    login, anything else that must never leave the PC. Needed because the usual, safe set-up has git's e-mail set to
    the GitHub noreply address, so the guard never learned the real one: on the dev PC it let it through. That
    list never leaves the PC either; `private-words` shows how many words it holds, `private-words add` adds one.
  In PUBLIC repos (or when the visibility cannot be found) also:
  - every word in ~/.claude/lanes/never-publish.txt (machine names and the like; that list never leaves the PC).
  Private repos may keep machine names: some tools file their records by computer name.
  Only ADDED lines are checked, so an old line elsewhere in a file never blocks an unrelated commit.
  A line holding "privacy-guard:allow" or "scrub-scan:allow" is skipped (deliberate test fixtures).

HOW IT HOOKS IN
  `install` makes ~/.claude/lanes/githooks/ and points git's machine-wide core.hooksPath at it. Every hook there
  first runs this check (pre-commit, commit-msg), then hands over to whatever machine-wide hook folder was set
  before (remembered in .previous, e.g. a push guard), else to the repository's own hook. A repository with its own
  core.hooksPath setting skips machine-wide hooks; `status` lists the ones it can see in the Lanes roots.
"""
import getpass
import json
import os
import re
import subprocess
import sys

HOME = os.path.expanduser("~")
STATE = os.environ.get("LANES_STATE_DIR") or os.path.join(HOME, ".claude", "lanes")
HOOKDIR = os.path.join(STATE, "githooks")
NEVER = os.path.join(STATE, "never-publish.txt")
PRIVATE = os.path.join(STATE, "private-words.txt")
AUDIT_SEEN = os.path.join(STATE, "privacy-audit-told.txt")   # commit ids the session-start audit already reported
CONF = os.environ.get("LANES_CONFIG") or os.path.join(HOME, ".claude", "lanes.conf")
HOOK_NAMES = ("pre-commit", "commit-msg", "prepare-commit-msg", "post-commit", "post-checkout", "post-merge",
              "post-rewrite", "pre-rebase", "pre-push", "reference-transaction")
ALLOW_MARKS = ("privacy-guard:allow", "scrub-scan:allow")
PLACEHOLDERS = {"user", "username", "you", "yourname", "your-name", "name", "someone", "example", "me", "x", "xx",
                "test", "runner", "ci", "home", "root", "admin", "public", "default", "all users", "default user",
                "%username%", "$user", "$username", "${user}", "${username}", "$env:username", "..."}
# 0.95.0: any letter case (Windows writes c:\users\<user> in many logs), WSL's /mnt/c/Users/, and the old
# Documents and Settings folder; all three let a home path through before
HOME_PATH = re.compile(r"(?:\b[A-Za-z]:(?:\\\\|\\|/)+(?:users|documents and settings)(?:\\\\|\\|/)+"
                       r"|(?<![\w.])/[a-z]/users/|(?<![\w.])/mnt/[a-z]/users/|(?<![\w.])/home/"
                       r"|(?<![\w.~])/Users/)([^\\/\s\"'`<>*|:;,)\]]+)", re.I)
MAX_SHOWN = 12


def conf_value(key):
    try:
        for line in open(CONF, encoding="utf-8"):
            k, _, v = line.partition("=")
            if k.strip() == key:
                return v.split("#")[0].strip()
    except OSError:
        pass
    return ""


def git(*args, cwd=None):
    r = subprocess.run(["git"] + list(args), capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=cwd)
    return r.stdout if r.returncode == 0 else ""


def words(public):
    """(word, why) pairs to refuse, lower-case."""
    display = conf_value("display_name").lower()
    out = []
    for login in {os.environ.get("USERNAME", ""), os.environ.get("USER", ""), safe_getuser()}:
        login = login.strip().lower()
        if len(login) >= 3 and login != display and login not in PLACEHOLDERS:
            out.append((login, "this PC's login name"))
    for email in set(git("config", "--get-all", "user.email").lower().split()
                     + git("config", "--global", "--get-all", "user.email").lower().split()):
        if email and "noreply" not in email:
            out.append((email, "the e-mail address in git's settings"))
    out += [(w.lower(), "a private word (private-words.txt)") for w in list_file(PRIVATE)]
    if public:
        out += [(w.lower(), "a never-publish word") for w in list_file(NEVER)]
    return out


def list_file(path):
    """The words in one of the PC's own lists: one per line, # starts a comment."""
    try:
        with open(path, encoding="utf-8") as f:
            return [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
    except OSError:
        return []


def safe_getuser():
    try:
        return getpass.getuser()
    except Exception:
        return ""


def has_word(low, w):
    """w appears in low as a word of its own, not inside a longer one (0.95.0): a machine called BOX is in
    "the home PC (BOX)", not in a renderer called "D3D9DrvBOX" in a credit."""
    if w not in low:
        return False
    return re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", low) is not None


def check_line(line, ws, display):
    """Reasons this one line may not be published."""
    if any(m in line for m in ALLOW_MARKS):
        return []
    low = line.lower()
    why = [w_why for w, w_why in ws if has_word(low, w)]
    for m in HOME_PATH.finditer(line):
        name = m.group(1).strip().lower()
        if name and name != display and name not in PLACEHOLDERS and not name.startswith(("<", "$", "%", "{")):
            why.append("a home-folder path (%s...)" % m.group(0)[:12].replace("\\\\", "\\"))
    return sorted(set(why))


def visibility(cwd=None):
    """public / private / unknown, cached per repository in its own git settings."""
    v = git("config", "--local", "lanes.visibility", cwd=cwd).strip()
    if v in ("public", "private"):
        return v
    url = git("remote", "get-url", "origin", cwd=cwd).strip()
    m = re.search(r"github\.com[:/]+([^/]+/[^/]+?)(?:\.git)?/?$", url)
    if not m:
        return "private" if not url else "unknown"   # no remote at all: nothing is published from here
    try:
        r = subprocess.run(["gh", "repo", "view", m.group(1), "--json", "visibility", "-q", ".visibility"],
                           capture_output=True, text=True, timeout=20)
        v = r.stdout.strip().lower()
    except Exception:
        v = ""
    if v in ("public", "private"):
        git("config", "--local", "lanes.visibility", v, cwd=cwd)
        return v
    return "unknown"


def report(findings, what):
    if not findings:
        return 0
    sys.stderr.write("\nPRIVACY GUARD (lanes): this %s would put something personal on GitHub.\n" % what)
    for where, why in findings[:MAX_SHOWN]:
        sys.stderr.write("  %s: %s\n" % (where, ", ".join(why)))
    if len(findings) > MAX_SHOWN:
        sys.stderr.write("  ... and %d more\n" % (len(findings) - MAX_SHOWN))
    sys.stderr.write("Fix: write ~ for the home folder (or look it up when the code runs: os.path.expanduser('~'),\n"
                     "$HOME, %USERPROFILE%), name people only by the display name, and leave machine names out.\n"
                     "Then stage the fix and commit again. Never skip this check (no --no-verify).\n\n")
    return 1


def cmd_staged():
    public = visibility() != "private"
    ws, display = words(public), conf_value("display_name").lower()
    findings = []
    for name in git("diff", "--cached", "--name-only", "--diff-filter=AR", "-z").split("\0"):
        if name:
            why = check_line(name, ws, display)
            if why:
                findings.append((name + " (the file's name)", why))
    cur, line_no = "", 0
    for line in git("diff", "--cached", "-U0", "--no-color", "--no-ext-diff").splitlines():
        if line.startswith("+++ "):
            cur = line[6:] if line.startswith("+++ b/") else line[4:]
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            line_no = int(m.group(1)) if m else 0
        elif line.startswith("+"):
            why = check_line(line[1:], ws, display)
            if why:
                findings.append(("%s:%d" % (cur, line_no), why))
            line_no += 1
    return report(findings, "commit")


def cmd_message(path):
    public = visibility() != "private"
    ws, display = words(public), conf_value("display_name").lower()
    findings = []
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return 0
    for i, line in enumerate(text.splitlines(), 1):
        if line.startswith("#"):
            continue
        why = check_line(line, ws, display)
        if why:
            findings.append(("commit message line %d" % i, why))
    return report(findings, "commit message")


def cmd_text(public):
    ws, display = words(public), conf_value("display_name").lower()
    findings = []
    for i, line in enumerate(sys.stdin.read().splitlines(), 1):
        why = check_line(line, ws, display)
        if why:
            findings.append(("line %d" % i, why))
    return report(findings, "text")


ZERO = "0" * 40
NOREPLY = ("users.noreply.github.com", "noreply@github.com", "noreply@anthropic.com")


def mask(email):
    """An e-mail address as the refusal prints it: enough to recognise, not the address itself (the refusal lands in
    terminals and session write-ups)."""
    name, _, domain = email.partition("@")
    return "%s...@%s" % (name[:2], domain) if domain else email[:2] + "..."


def pushed_content(rng, ws, display):
    """(0.95.0) The lines each pushed commit ADDS, and the names of files it adds. The pre-commit check sees only
    ordinary commits: a rebase, cherry-pick or merge, a commit made with --no-verify or before the guard was put
    on, all reach the push unchecked. Every commit is read, not only the end result, because a line added in one
    commit and taken out in the next still goes to GitHub in the history."""
    findings, commit, cur, line_no = [], "", "", 0
    out = git("log", "-p", "-U0", "--no-color", "--no-ext-diff", "--no-renames", "--format=%x01%H", *rng)
    for line in out.splitlines():
        if line.startswith("\x01"):
            commit = line[1:10]
        elif line.startswith("+++ "):
            cur = line[6:] if line.startswith("+++ b/") else line[4:]
            why = check_line(cur, ws, display) if cur != "/dev/null" else []
            if why:
                findings.append(("commit %s, %s (the file's name)" % (commit, cur), why))
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            line_no = int(m.group(1)) if m else 0
        elif line.startswith("+"):
            why = check_line(line[1:], ws, display)
            if why:
                findings.append(("commit %s, %s:%d" % (commit, cur, line_no), why))
            line_no += 1
    return findings


def cmd_push(remote_url):
    """(pre-push, 0.86.1) Commits about to reach GitHub: no personal e-mail as author or committer, no login or
    never-publish word in a message. Old commits from before a history clean-up all carry the old e-mail, so this is
    also what stops an old copy from pushing the old history back."""
    if "github.com" not in (remote_url or ""):
        return 0
    public = visibility() != "private"
    ws, display = words(public), conf_value("display_name").lower()
    findings, seen = [], set()
    for line in sys.stdin.read().splitlines():
        parts = line.split()
        if len(parts) != 4 or parts[1] == ZERO:
            continue
        local, remote = parts[1], parts[3]
        known = remote != ZERO and subprocess.run(["git", "cat-file", "-e", remote + "^{commit}"],
                                                  capture_output=True).returncode == 0
        rng = ["%s..%s" % (remote, local)] if known else [local, "--not", "--remotes"]
        log = git("log", "--format=%H%x00%ae%x00%ce%x00%B%x1e", *rng)
        for rec in log.split("\x1e"):
            f = rec.strip("\n").split("\x00")
            if len(f) < 4 or f[0] in seen:
                continue
            seen.add(f[0])
            why = ["the e-mail address %s as author or committer" % mask(e) for e in sorted({f[1], f[2]})
                   if e and not e.lower().endswith(NOREPLY)]
            for ml in f[3].splitlines():
                why += check_line(ml, ws, display)
            if why:
                findings.append(("commit " + f[0][:9], sorted(set(why))))
        findings += pushed_content(rng, ws, display)
    if findings:
        sys.stderr.write("\nPRIVACY GUARD (lanes): this push would put something personal on GitHub.\n")
        for where, why in findings[:MAX_SHOWN]:
            sys.stderr.write("  %s: %s\n" % (where, ", ".join(why)))
        if len(findings) > MAX_SHOWN:
            sys.stderr.write("  ... and %d more commits\n" % (len(findings) - MAX_SHOWN))
        sys.stderr.write("If this repository's history was cleaned, this copy still holds the old commits: move it onto\n"
                         "the clean history with  git fetch  then  git reset --keep origin/<branch>  (your own edits stay as\n"
                         "they are), and commit again. If it is your own new commit: set git's e-mail to your GitHub\n"
                         "no-reply address (git config --global user.email <id>+<name>@users.noreply.github.com),\n"
                         "then  git commit --amend --reset-author --no-edit. Never skip this check (no --no-verify).\n\n")
        return 1
    return 0


AUDIT_RECENT_DAYS = 14
SHOW_CHUNK = 300   # commit ids per git show call
GITHUB_WEB = "noreply@github.com"   # the committer of an edit made on github.com


def clone_roots():
    """Every Lanes clone root on this PC (the same ones the handover light reads). Falls back to `root` when this
    copy runs from the hooks folder, where the handover tool is not beside it."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        import handover
        return handover.roots_from(handover.read_conf())
    except Exception:
        r = conf_value("root")
        return [r] if r and os.path.isdir(r) else []


def clones(first_root_only=False):
    seen, out = set(), []
    for root in clone_roots()[:1 if first_root_only else None]:
        try:
            names = sorted(os.listdir(root))
        except OSError:
            continue
        for n in names:
            p = os.path.join(root, n)
            if os.path.exists(os.path.join(p, ".git")) and os.path.normcase(p) not in seen:
                seen.add(os.path.normcase(p))
                out.append(p)
    return out


def one_per_repo(paths):
    """The first clone of each GitHub repo (the live root comes first): every lane root holds a copy of the same
    repos, and what GitHub holds is read once, not once per copy."""
    seen, out = set(), []
    for p in paths:
        url = git("remote", "get-url", "origin", cwd=p).strip().lower().rstrip("/")
        url = url[:-4] if url.endswith(".git") else url
        if url and url not in seen:
            seen.add(url)
            out.append(p)
    return out


def personal_emails():
    """The addresses that are the person's own: git's settings plus any e-mail in private-words.txt."""
    out = {e for e in git("config", "--global", "--get-all", "user.email").lower().split() if "noreply" not in e}
    out |= {w.lower() for w in list_file(PRIVATE) if "@" in w}
    return out


def audit_authors(repo, refs_args, mails, since=None, skip=()):
    """Commits with one of the person's own addresses as author or committer, among refs_args, leaving out the
    commit ids in skip. Returns (count, newest date, made on github.com?, their ids)."""
    args = ["log", "--format=%H%x00%ae%x00%ce%x00%cs"] + (["--since=%s" % since] if since else []) + refs_args
    n, newest, web, ids = 0, "", False, []
    for line in git(*args, cwd=repo).splitlines():
        f = line.split("\x00")
        if len(f) == 4 and f[0] not in skip and (f[1].lower() in mails or f[2].lower() in mails):
            n += 1
            newest = max(newest, f[3])
            web = web or f[2].lower() == GITHUB_WEB
            ids.append(f[0])
    return n, newest, web, ids


def remote_refs(repo):
    return [r for r in git("for-each-ref", "--format=%(refname)", "refs/remotes/origin", cwd=repo).split()
            if not r.endswith("/HEAD")]


def grep_hits(repo, ref, ws, display):
    """(where, why) for every line on one remote branch that a commit would be refused for."""
    out = []
    for line in git("grep", "-I", "-n", "-i", "-E", audit_prefilter(ws), ref, "--", cwd=repo).splitlines():
        parts = line.split(":", 3)   # ref is origin/<branch>, so: origin/<branch> : path : line : text
        if len(parts) < 4:
            continue
        why = check_line(parts[3], ws, display)
        if why:
            out.append(("%s:%s" % (parts[1], parts[2]), why))
    return out


def cmd_audit(quick):
    """What GitHub holds, checked the way a new commit is (0.95.0). The commit and push checks only see what is
    added from now on; this looks at what is already there, as of the last fetch. A full audit found, on the
    maintainer's account, four side branches of a private repo still holding a home login and the old contact
    e-mail after two clean-ups, and one commit on the public profile repo made on github.com with the real e-mail
    (GitHub's own setting, not anything on the PC). --quick (session start) reads only the authors of the last
    two weeks of commits: fast, no file contents."""
    mails = personal_emails()
    display = conf_value("display_name").lower()
    problems, olds, kept, all_clones = [], [], [], clones(first_root_only=quick)   # quick: the live root holds them all
    seen, told = set(list_file(AUDIT_SEEN)), []   # quick: each commit is told once; the full audit always lists it
    for repo in one_per_repo(all_clones):
        name = os.path.basename(repo)
        remotes = remote_refs(repo)
        if not remotes:
            continue
        public = visibility(repo) != "private"
        if mails:
            n, newest, web, ids = audit_authors(repo, remotes, mails, ("%d.days" % AUDIT_RECENT_DAYS) if quick else None,
                                                seen if quick else ())
            told += ids if quick and public else []
            web_note = " (made on github.com: switch on GitHub's 'Keep my email addresses private')" if web else ""
            if n and public:
                problems.append("%s: %d commit(s) on GitHub carry your own e-mail address, newest %s%s" % (
                    name, n, newest, web_note))
            elif n and not quick:
                # private repos kept their history when the public ones were cleaned (the maintainer's decision)
                kept.append("%s (private): %d older commit(s) carry your e-mail, newest %s%s" % (name, n, newest, web_note))
        if quick:
            continue
        ws = words(public)
        for ref in remotes:
            short = ref[len("refs/remotes/"):]
            hits = grep_hits(repo, short, ws, display)
            for where, why in hits[:3]:
                problems.append("%s %s %s: %s" % (name, short, where, ", ".join(why)))
            if len(hits) > 3:
                problems.append("%s %s: ... and %d more line(s)" % (name, short, len(hits) - 3))
    if mails and not quick:
        by_repo = {}
        for repo in all_clones:
            tags, branches = old_refs(repo, mails)
            if tags or branches:
                e = by_repo.setdefault(os.path.basename(repo), [0, 0, 0])
                e[0] += 1
                e[1] += len(tags)
                e[2] += len(branches)
        for name, (copies, tags, branches) in sorted(by_repo.items()):
            olds.append("%s: old copies from before the history clean-up in %d clone(s) on this PC (%d tag(s), %d"
                        " branch(es)); nothing to save in them. Tags: privacy-guard.py drop-old-tags puts GitHub's"
                        " cleaned ones in their place%s" % (name, copies, tags, branches,
                                                            "; branches: delete them by hand" if branches else ""))
    if told:
        os.makedirs(STATE, exist_ok=True)
        with open(AUDIT_SEEN, "a", encoding="utf-8", newline="\n") as f:
            f.write("".join(i + "\n" for i in told))
    if not quick:
        for k in kept:
            print("  kept on purpose: " + k)
    if not problems and not olds:
        if not quick:
            print("privacy audit: nothing personal found in what GitHub holds (%d clones%s)." % (
                len(all_clones), "" if mails else "; no personal e-mail known yet: add it with private-words add"))
        return 0
    print("PRIVACY AUDIT (lanes): %s" % ("tell the person in plain words, without repeating the details:"
                                         if quick else "what GitHub holds, as of the last fetch:"))
    for p in problems + olds:
        print("  " + p)
    return 1 if problems else 0


def old_refs(repo, mails):
    """(tags, branches) on this clone only whose commits carry the person's e-mail and that GitHub does not hold as
    they are: copies from before a history clean-up, which rewrote every commit id. A tag of the same name on GitHub
    points at the cleaned commit; a branch is old when GitHub holds every one of its changes (git cherry)."""
    remotes = remote_refs(repo)
    if not remotes:
        return [], []
    tags, branches = [], []
    reach = set(git("rev-list", *remotes, cwd=repo).split())
    targets = {}
    for line in git("for-each-ref", "--format=%(refname:short) %(objectname) %(*objectname)", "refs/tags",
                    cwd=repo).splitlines():
        f = line.split()
        if len(f) >= 2 and f[-1] not in reach:
            targets[f[0]] = f[-1]          # the commit a tag points at (peeled when it is an annotated tag)
    if targets:
        bad, commits = set(), sorted(set(targets.values()))
        for i in range(0, len(commits), SHOW_CHUNK):     # a Windows command line holds about 32,000 characters
            for line in git("show", "-s", "--format=%H%x00%ae%x00%ce", *commits[i:i + SHOW_CHUNK],
                            cwd=repo).splitlines():
                f = line.split("\x00")
                if len(f) == 3 and (f[1].lower() in mails or f[2].lower() in mails):
                    bad.add(f[0])
        tags = sorted(t for t, c in targets.items() if c in bad)
    for ref in git("for-each-ref", "--format=%(refname)", "refs/heads", cwd=repo).split():
        if audit_authors(repo, [ref, "--not"] + remotes, mails)[0]:
            b = ref[len("refs/heads/"):]
            up = "refs/remotes/origin/" + b if "refs/remotes/origin/" + b in remotes else "HEAD"
            if not any(l.startswith("+") for l in git("cherry", up, b, cwd=repo).splitlines()):
                branches.append(b)
    return tags, branches


def cmd_drop_old_tags(apply):
    """Replace the tags that are old copies (see old_refs) with GitHub's cleaned tags of the same name. A tag GitHub
    does not have at all is left alone and named, since it may be the only copy of something."""
    mails = personal_emails()
    if not mails:
        print("no personal e-mail known: add it first with private-words add")
        return 2
    total = 0
    for repo in clones():
        tags, _ = old_refs(repo, mails)
        if not tags:
            continue
        on_github = {l.split("refs/tags/")[1].replace("^{}", "") for l in
                     git("ls-remote", "--tags", "origin", cwd=repo).splitlines() if "refs/tags/" in l}
        swap = [t for t in tags if t in on_github]
        keep = [t for t in tags if t not in on_github]
        where = "%s (%s)" % (os.path.basename(repo), os.path.basename(os.path.dirname(repo)))
        if swap and apply:
            git("tag", "-d", *swap, cwd=repo)
            git("fetch", "-q", "origin", *["refs/tags/%s:refs/tags/%s" % (t, t) for t in swap], cwd=repo)
        total += len(swap)
        print("  %s: %d tag(s) %s%s" % (where, len(swap), "replaced" if apply else "to replace",
                                         ("; left alone, not on GitHub: " + ", ".join(keep)) if keep else ""))
    print("%d old tag(s) %s." % (total, "replaced with GitHub's cleaned ones" if apply else
                                 "would be replaced; run again with --yes"))
    return 0


def audit_prefilter(ws):
    """One loose pattern for git grep; every hit is then judged by check_line, the same test a commit gets."""
    parts = [r"users[\\/]", r"/home/", r"documents and settings"] + [re.escape(w) for w, _ in ws]
    return "|".join(parts)


def cmd_private_words(argv):
    """private-words: how many words the PC's own private list holds. private-words add [WORD]: add one (from
    stdin when no word is given, so it stays out of the shell history). The list itself is never printed."""
    if argv[:1] == ["add"]:
        w = (argv[1] if len(argv) > 1 else sys.stdin.read()).strip()
        if not w or "\n" in w:
            print("give one word or address")
            return 2
        if w.lower() in (x.lower() for x in list_file(PRIVATE)):
            print("already on the private list")
            return 0
        os.makedirs(STATE, exist_ok=True)
        with open(PRIVATE, "a", encoding="utf-8", newline="\n") as f:
            f.write(w + "\n")
        print("added; the private list now holds %d word(s)" % len(list_file(PRIVATE)))
        return 0
    n = len(list_file(PRIVATE))
    print("private list: %d word(s)%s" % (n, "" if n else " - add your real e-mail address: private-words add"))
    return 0


HOOK = """#!/bin/sh
# Lanes privacy guard (tools/privacy-guard.py install): checks a commit, then hands over to the hook that was here
# before (a machine-wide one remembered in .previous, else the repository's own).
name=$(basename "$0")
case "$name" in
  pre-commit) @@PY@@ "@@TOOL@@" staged || exit 1 ;;
  commit-msg) @@PY@@ "@@TOOL@@" message "$1" || exit 1 ;;
  pre-push)
    # the pushed refs arrive on stdin once: keep a copy for the hook that runs after this one
    tmp=$(mktemp 2>/dev/null || echo "${TMPDIR:-/tmp}/lanes-pre-push.$$")
    cat > "$tmp"
    @@PY@@ "@@TOOL@@" push "$2" < "$tmp" || { rm -f "$tmp"; exit 1; }
    exec 3< "$tmp"; rm -f "$tmp"; exec 0<&3 ;;
esac
prev=$(cat "$(dirname "$0")/.previous" 2>/dev/null)
if [ -n "$prev" ] && [ -x "$prev/$name" ]; then exec "$prev/$name" "$@"; fi
gd=$(git rev-parse --git-dir 2>/dev/null)
if [ -z "$prev" ] && [ -n "$gd" ] && [ -x "$gd/hooks/$name" ]; then exec "$gd/hooks/$name" "$@"; fi
exit 0
"""


def cmd_install():
    os.makedirs(HOOKDIR, exist_ok=True)
    py = sys.executable.replace("\\", "/")
    # the hooks copy this file next to them, so a plugin update that moves the plugin folder never breaks commits
    here = os.path.join(HOOKDIR, "privacy-guard.py")
    if os.path.abspath(here) != os.path.abspath(__file__):
        with open(__file__, encoding="utf-8") as src, open(here, "w", encoding="utf-8", newline="\n") as dst:
            dst.write(src.read())
    tool = here.replace("\\", "/")
    for n in HOOK_NAMES:
        p = os.path.join(HOOKDIR, n)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(HOOK.replace("@@PY@@", '"%s"' % py).replace("@@TOOL@@", tool))
        os.chmod(p, 0o755)
    cur = git("config", "--global", "--get", "core.hooksPath").strip()
    mine = HOOKDIR.replace("\\", "/")
    if cur and os.path.normcase(os.path.abspath(os.path.expanduser(cur))) != os.path.normcase(os.path.abspath(HOOKDIR)):
        with open(os.path.join(HOOKDIR, ".previous"), "w", encoding="utf-8", newline="\n") as f:
            f.write(cur.replace("\\", "/"))
    subprocess.run(["git", "config", "--global", "core.hooksPath", mine])
    print("privacy guard installed: every commit on this PC is checked.%s"
          % (" (It hands over to the hooks that were set before: %s)" % cur if cur and cur != mine else ""))
    return 0


def cmd_uninstall():
    prev = ""
    try:
        prev = open(os.path.join(HOOKDIR, ".previous"), encoding="utf-8").read().strip()
    except OSError:
        pass
    if prev:
        subprocess.run(["git", "config", "--global", "core.hooksPath", prev])
    else:
        subprocess.run(["git", "config", "--global", "--unset", "core.hooksPath"])
    print("privacy guard removed; machine-wide hooks are %s again" % (prev or "unset"))
    return 0


def installed():
    cur = git("config", "--global", "--get", "core.hooksPath").strip()
    return bool(cur) and os.path.normcase(os.path.abspath(os.path.expanduser(cur))) == os.path.normcase(
        os.path.abspath(HOOKDIR)) and os.path.isfile(os.path.join(HOOKDIR, "pre-commit"))


def cmd_status(as_json):
    st = {"installed": installed(), "hooks": HOOKDIR, "never_publish_words": len(words(True)) - len(words(False)),
          "checks": ["login", "home-folder paths", "git e-mail", "private words", "never-publish words (public repos)"]}
    if as_json:
        print(json.dumps(st))
    else:
        print("privacy guard: %s" % ("ON, every commit on this PC is checked" if st["installed"] else "NOT installed"))
    return 0 if st["installed"] else 1


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    c = argv[0]
    if c == "staged":
        return cmd_staged()
    if c == "message" and len(argv) > 1:
        return cmd_message(argv[1])
    if c == "push":
        return cmd_push(argv[2] if len(argv) > 2 else (argv[1] if len(argv) > 1 else ""))
    if c == "text":
        return cmd_text("--public" in argv)
    if c == "install":
        return cmd_install()
    if c == "uninstall":
        return cmd_uninstall()
    if c == "status":
        return cmd_status("--json" in argv)
    if c == "audit":
        return cmd_audit("--quick" in argv)
    if c == "private-words":
        return cmd_private_words(argv[1:])
    if c == "drop-old-tags":
        return cmd_drop_old_tags("--yes" in argv)
    print(__doc__)
    return 2


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):   # a character the console cannot show prints as ? (0.94.2)
        try:
            _stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))
