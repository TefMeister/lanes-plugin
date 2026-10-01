#!/usr/bin/env python3
"""inspector - look over code a session just wrote, write down what is messy, and hold the commit
until every finding has a verdict.

WHY THIS EXISTS (2026-09-26)
  code-shape-scan looks at the whole estate once a sweep. Mess is cheapest to fix in the minute it
  was written, by the session that wrote it, while it still knows why. The author's design, in
  three steps: Claude writes code; the Inspector writes what is messy into a SEPARATE file (so the
  findings survive a session that ends abruptly); Claude reads that file in the same session and
  decides, finding by finding, whether it is really mess or has to be that way to work. The
  verdict step is not skippable, not even when usage is low: then less gets done, never worse.
  See docs/PROTOCOL.md section 16 and docs/specs/inspector-idea.md.

THE NOTES FOLDER (2026-09-26, sorted into files at the user's request)
  <project>/dev-archive/inspector/ (or <project>/inspector/ with no dev-archive): this-session.md,
  waiting.md (left by an earlier session: answer first), decided.md, already-there.md, cleared.md.
  It travels with the project between PCs. See inspector_store.py. Each note has a Verdict line:
    waiting                     not answered yet
    fix now                     real; fix it in this session (only for kinds that cannot change behaviour)
    fix later: <board row>      real; the named board row carries it
    keep: <why it must stay>    not mess, or needed to work; raised again only if it gets clearly worse
  The Inspector writes only that folder. It never edits code.

WHEN IT ASKS (inspector_mode in lanes.conf)
  end  (default, "best of both"): notes are written silently after every edit, saves go through, and
       everything is answered once at the end of the session: a lane releasing its claim is held
       until the notes are answered and committed. A session that ends first leaves them in
       waiting.md, and the next session is told at start.
  each (the first design): asks after every edit and holds each commit until its notes are answered.

ONLY NEW OR WORSE
  A file the Inspector has never seen is compared with its last commit: anything already there is
  listed once under "Already there before the Inspector" and not raised. After that, a finding is
  raised when it is new, or when a decided one gets worse (a bigger number than when it was
  judged). One that disappears from the code moves to "Cleared".

SAFETY RULES (added 2026-09-26, before in-house testing)
  1. `fix now` only for LOOSE-NUMS, LOOSE-ADDRESS and DEAD-CODE, whose fix cannot change behaviour.
     On any other kind it counts as no verdict: structural fixes are `fix later`, done on their own.
  2. Emergency save: a commit whose message says `inspector: carry over` goes through with findings
     still waiting (the record must be staged with it). They greet the next session (`brief`).

USAGE
  inspector.py check FILE...        inspect files (the edit hook runs this); prints what is new
  inspector.py review REPO          inspect EVERY tracked source file, excusing nothing (a full review)
  inspector.py gate REPO [--all]    what a commit of the staged files would be refused for
  inspector.py status REPO          every finding still waiting, in one list
  inspector.py stats REPO           how the verdicts split, per kind (for in-house testing)
  inspector.py brief [--session ID] notes left unanswered by an earlier session (session start)
  inspector.py final ROOT PROJECT.. the end-of-session check (a lane's claim release runs it)
  inspector.py summary [--session ID] one line for the end of a session: found / fixed / kept / later /
                                    unanswered in this session (default: $CLAUDE_CODE_SESSION_ID)
  lanes.conf: `inspector = off` switches it off; `inspector_repos = a, b` limits it to those repos;
  `inspector_root = <folder>` is where the copy-paste check looks for sibling projects.
"""
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import inspector_checks as ic  # noqa: E402
from inspector_store import (BLOCKING_STATES, EXAMPLES_SHOWN, Record, record_dir,  # noqa: E402
                             verdict_state)
DUP_MAX_LINES = 20000   # a file longer than this is data, not a helper worth matching against
# Evidence folders keep a snapshot of the script a run used: copies by design, not copy-paste.
# (First Village review, 2026-09-26: 14 of 29 DUPLICATE findings pointed into recon/.)
DUP_SKIP_PARTS = {"recon"}
# A decided size finding is raised again only after a real step (replay of 40 Village commits, 2026-09-26).
SIZE_KINDS = {"OVER-SOFT", "OVER-HARD", "LONG-FUNCTION", "DUPLICATE"}
SIZE_GROWTH_PCT = 10
SIZE_GROWTH_MIN = 20
DEFAULT_HOME = os.path.join(os.path.expanduser("~"), ".claude", "lanes-inspector")


def home():
    """The Inspector's own folder on this PC (2026-09-26: the user chooses it when installing).
    Holds the backups of work kept back from GitHub (held/), the session lists and the copy-paste
    cache. `inspector_home` in lanes.conf; LANES_INSPECTOR_CACHE overrides it for tests."""
    return (os.environ.get("LANES_INSPECTOR_CACHE") or read_conf("inspector_home") or DEFAULT_HOME).rstrip("/\\")
# Safety rule 2: a commit whose message carries this phrase is the emergency save at session end.
# The code saves; the waiting findings carry over and greet the next session.
CARRY_RE = re.compile(r"inspector:\s*carry[- ]over", re.I)
def carry_log():
    return os.path.join(home(), "carried-over.log")

# Every project the Inspector has written notes for on this PC, so the session-start reminder finds
# them wherever they are cloned. One line per project: <when>\t<repo>\t<prefix>.
def projects_log():
    return os.path.join(home(), "projects.log")



def keep_notes_local(repo, notes_dir):
    """For public project repos (2026-09-26): notes can stay on this PC instead of being published. With
    `inspector_notes_local = on` its notes folder is listed in the clone's own .git/info/exclude, which is
    never committed or pushed, so the notes stay on this PC and git (and the upload hold) ignore them."""
    if (read_conf("inspector_notes_local") or "off").lower() not in ("on", "yes", "true", "1"):
        return
    rel = rel_to(repo, notes_dir) + "/"
    gitdir = (git(repo, "rev-parse", "--git-common-dir") or "").strip()
    if not gitdir:
        return
    path = os.path.join(gitdir if os.path.isabs(gitdir) else os.path.join(repo, gitdir), "info", "exclude")
    try:
        existing = open(path, encoding="utf-8").read() if os.path.isfile(path) else ""
        if "/" + rel not in existing.splitlines():
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8", newline="\n") as f:
                f.write(("" if existing.endswith("\n") or not existing else "\n")
                        + "# lanes Inspector notes, kept on this PC (inspector_notes_local = on)\n/" + rel + "\n")
    except OSError:
        pass


def remember_project(repo, prefix):
    line_key = f"\t{repo}\t{prefix}\n"
    try:
        os.makedirs(home(), exist_ok=True)
        try:
            with open(projects_log(), encoding="utf-8") as f:
                if any(l.endswith(line_key) for l in f):
                    return
        except OSError:
            pass
        with open(projects_log(), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d") + line_key)
    except OSError:
        pass

def read_conf(key):
    # A LANES_CONFIG that is set is the whole config: falling through to the real file would let a
    # test's scratch config inherit this machine's settings.
    paths = [os.environ["LANES_CONFIG"]] if os.environ.get("LANES_CONFIG") else \
        [os.path.expanduser("~/.claude/lanes.conf"), os.path.expanduser("~/.config/lanes/lanes.conf")]
    for path in paths:
        if not path or not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    m = re.match(r"^\s*" + re.escape(key) + r"\s*=\s*(.*?)\s*$", line)
                    if m:
                        return m.group(1).strip().strip('"')
        except OSError:
            continue
    return None


def enabled():
    """Optional (user-directed, 2026-09-26): the Inspector does nothing until `inspector = on` in lanes.conf."""
    return (read_conf("inspector") or "off").lower() in ("on", "yes", "true", "1")


def git(repo, *args):
    try:
        r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    except OSError:
        return None
    return r.stdout if r.returncode == 0 else None


def repo_of(path):
    d = path if os.path.isdir(path) else os.path.dirname(os.path.abspath(path))
    top = git(d, "rev-parse", "--show-toplevel")
    return os.path.normpath(top.strip()) if top else None


def project_prefix(repo, rel):
    """A repo holding one folder per project (`inspector_multi`, default `staging`) gets one record
    per top folder, so each project's findings stay with that project."""
    multi = [n.strip().lower() for n in (read_conf("inspector_multi") or "staging").split(",") if n.strip()]
    if os.path.basename(os.path.normpath(repo)).lower() in multi and "/" in rel:
        return rel.split("/", 1)[0] + "/"
    return ""


def project_name(repo, prefix=""):
    return prefix.rstrip("/") or os.path.basename(os.path.normpath(repo))


def repo_allowed(repo, prefix=""):
    """During in-house testing the Inspector can be limited to named projects (`inspector_repos`)."""
    names = [n.strip().lower() for n in (read_conf("inspector_repos") or "").split(",") if n.strip()]
    return not names or project_name(repo, prefix).lower() in names


def locate(path):
    """(repo, prefix) for a repo or a project folder inside one."""
    repo = repo_of(path)
    if not repo:
        return None, ""
    rel = os.path.relpath(os.path.abspath(path), repo).replace("\\", "/")
    return repo, ("" if rel in (".", "") else project_prefix(repo, rel + "/x"))


# ------------------------------------------------------------------ copy-paste index

def dup_index(repo):
    """{window hash: [qualified names]} across this repo and its sibling repos, cached by file mtime."""
    root = read_conf("inspector_root") or os.path.dirname(repo)
    os.makedirs(home(), exist_ok=True)
    cache_file = os.path.join(home(), "dup-" + re.sub(r"[^\w]", "_", root)[-80:] + ".json")
    try:
        with open(cache_file, encoding="utf-8") as f:
            cache = json.load(f)
    except (OSError, ValueError):
        cache = {}
    fresh, index = {}, {}
    for name in sorted(os.listdir(root)):
        r = os.path.join(root, name)
        if not os.path.exists(os.path.join(r, ".git")):
            continue
        listing = git(r, "ls-files") or ""
        patterns = ic.shape.ignore_patterns(r)
        for rel in listing.splitlines():
            if (not ic.is_source(rel) or ic.shape.skipped(rel, patterns) or ic.is_vendored(rel)
                    or DUP_SKIP_PARTS & {p.lower() for p in rel.split("/")[:-1]}):
                continue
            full = os.path.join(r, rel)
            try:
                st = os.stat(full)
            except OSError:
                continue
            qual = f"{name}/{rel}"
            stamp = f"{st.st_mtime_ns}:{st.st_size}"
            hit = cache.get(qual)
            if hit and hit[0] == stamp:
                hashes = hit[1]
            else:
                try:
                    with open(full, encoding="utf-8", errors="replace") as f:
                        text = f.read()
                except OSError:
                    continue
                lines = text.splitlines()
                hashes = [] if len(lines) > DUP_MAX_LINES or ic.generated(lines) else \
                    list(ic.windows(text, os.path.splitext(rel)[1].lower()))
            fresh[qual] = [stamp, hashes]
            for h in hashes:
                bucket = index.setdefault(h, [])
                if len(bucket) < 3:
                    bucket.append(qual)
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(fresh, f)
    except OSError:
        pass
    return index


# ------------------------------------------------------------------ checking

def findings_for(repo, rel, text, index):
    out = ic.inspect_text(rel, text)
    if index is not None and not ic.generated(text.splitlines()):
        me = f"{os.path.basename(repo)}/{rel}"
        out.extend(f._replace(path=rel) for f in ic.check_duplicates(me, text, index))
    return {Record.key(f.kind, f.path, f.detail): f for f in out}


def check_files(paths, with_dups=True, baseline=True, session=None):
    """Inspect files; update each project's record.
    Returns {(repo, prefix): (record, [raised items], [cleared])}.

    baseline=False is the full review: nothing is excused as "already there", every finding is raised."""
    by_unit, repos = {}, {}
    for p in paths:
        d = os.path.dirname(os.path.abspath(p))
        if d not in repos:
            repos[d] = repo_of(d)
        repo = repos[d]
        if not repo:
            continue
        rel = os.path.relpath(os.path.abspath(p), repo).replace("\\", "/")
        prefix = project_prefix(repo, rel)
        if (rel.startswith("..") or not repo_allowed(repo, prefix) or not ic.is_source(rel)
                or ic.shape.skipped(rel, ic.shape.ignore_patterns(repo))):
            continue
        by_unit.setdefault((repo, prefix), []).append(rel)
    results = {}
    for (repo, prefix), rels in by_unit.items():
        rec, raised, cleared = Record(repo, prefix), [], []
        if session:
            rec.current_session = session  # notes from any other session now count as carried over
        index = dup_index(repo) if with_dups else None
        for rel in rels:
            try:
                with open(os.path.join(repo, rel), encoding="utf-8", errors="replace") as f:
                    now = findings_for(repo, rel, f.read(), index)
            except OSError:
                continue
            base = {}
            if baseline and rel not in rec.seen:
                head = git(repo, "show", f"HEAD:{rel}")
                base = findings_for(repo, rel, head, index) if head is not None else {}
            now = {k: f for k, f in now.items() if not mirror_known(rec, repo, rel, f)}
            for k, f in now.items():
                item, old = rec.items.get(k), rec.old.get(k)
                if not baseline:
                    old = None
                if item:
                    state = verdict_state(item["verdict"], item["kind"])
                    if state in ("later", "keep"):
                        judged = item.setdefault("verdict_value", item["value"])
                        if worse(f.kind, judged, f.value):
                            item["note"] = (f"got worse since the verdict: was {judged}, now {f.value}; "
                                            f"the earlier verdict was \"{item['verdict']}\"")
                            item["verdict"] = "waiting"
                            item.pop("verdict_value", None)
                            raised.append(item)
                    item.update(value=f.value, what=f.what, examples=new_examples(f, base)[:EXAMPLES_SHOWN])
                elif old and not worse(f.kind, old["value"], f.value):
                    continue
                elif k in base and f.value <= base[k].value and rel not in rec.seen:
                    rec.old[k] = {"old": True, "kind": f.kind, "path": f.path, "detail": f.detail, "value": f.value}
                else:
                    note = f"got worse: was {old['value']} before the Inspector" if old else ""
                    ex = new_examples(f, base.get(k))
                    raised.append(rec.add(f._replace(examples=ex), note))
                    rec.old.pop(k, None)
            for k in [k for k, i in rec.items.items() if i["path"] == rel and k not in now]:
                i = rec.items.pop(k)
                cleared.append(i)
                rec.add_cleared(i)
            for k in [k for k, o in rec.old.items() if o["path"] == rel and k not in now]:
                rec.old.pop(k)
            rec.seen.add(rel)
        rec.save()
        keep_notes_local(repo, rec.path)
        remember_project(repo, prefix)
        if session:
            note_session_checks(session, len(rels))
        results[(repo, prefix)] = (rec, raised, cleared)
    return results


def worse(kind, judged, now):
    """Has a decided (or already-there) finding got worse enough to ask again?

    Size kinds grow a few lines with almost every change to a big file. Re-asking on each one made a
    replay of 40 real Village commits raise the same five findings 36 times (one function 14 times),
    which trains a session to type `keep:` without reading. So they come back only after a real step:
    at least SIZE_GROWTH_PCT percent AND SIZE_GROWTH_MIN lines past the value that was judged. Count
    kinds (a new bare number, a new F-key, a new probe line) are new mess each time and stay strict."""
    if kind in SIZE_KINDS:
        return now - judged >= SIZE_GROWTH_MIN and now >= judged * (1 + SIZE_GROWTH_PCT / 100.0)
    return now > judged


def mirror_known(rec, repo, rel, f):
    """Fault 7 (2026-09-26): A copied from B and B copied from A are one finding, not two."""
    if f.kind != "DUPLICATE":
        return False
    head = os.path.basename(os.path.normpath(repo)) + "/"
    if not f.detail.startswith(head):
        return False
    mirror = Record.key("DUPLICATE", f.detail[len(head):], head + rel)
    return mirror in rec.items or mirror in rec.old


def new_examples(f, base):
    """The example lines not already there in the baseline, so the note points at the new mess."""
    if base is None:
        return list(f.examples)
    if isinstance(base, dict):
        base = base.get(Record.key(f.kind, f.path, f.detail))
    if base is None:
        return list(f.examples)
    old = {e.split(": ", 1)[-1] for e in base.examples}
    fresh = [e for e in f.examples if e.split(": ", 1)[-1] not in old]
    return fresh or list(f.examples)


def blocking(rec, rels=None):
    """Findings that stop a commit of `rels` (all files when None)."""
    return [i for i in rec.items.values()
            if (rels is None or i["path"] in rels) and verdict_state(i["verdict"], i["kind"]) in BLOCKING_STATES]


def describe(item):
    tag = {"fixnow": "fix now, still there",
           "badfix": "fix now is not allowed for this kind: it could change behaviour, use fix later or keep",
           }.get(verdict_state(item["verdict"], item["kind"]), "waiting")
    return f"  {item['id']} {item['kind']} {item['path']}: {item['what']} [{tag}]"


def rel_to(repo, path):
    return os.path.relpath(path, repo).replace("\\", "/")


# ------------------------------------------------------------------ commands

def mode():
    """`each`: ask after every edit and hold each commit (the first design).
    `end` (default, the user's choice 2026-09-26, "best of both"): note silently after every edit, let
    saves through, and ask once at the end of the session - when a lane releases its claim, or on
    `inspector.py final`. A session that ends first leaves its notes in waiting.md for the next."""
    m = (read_conf("inspector_mode") or "end").strip().lower()
    return m if m in ("each", "end") else "end"


def cmd_check(paths, session=None):
    results = check_files(paths, session=session)
    if mode() == "end":
        return 0  # silent: the notes wait in this-session.md for the end of the session
    for (repo, prefix), (rec, raised, cleared) in results.items():
        rel_rec = rel_to(repo, rec.path)
        if raised:
            print(f"INSPECTOR: {len(raised)} new finding(s) in {project_name(repo, prefix)}, written to {rel_rec}/:")
            for i in raised:
                print(describe(i) + (f" ({i['note']})" if i.get("note") else ""))
        if cleared:
            print(f"INSPECTOR: {len(cleared)} finding(s) cleared from the code: "
                  + ", ".join(i["id"] for i in cleared))
        waiting = blocking(rec)
        if raised or (waiting and cleared):
            print(f"{len(waiting)} finding(s) in {rel_rec}/ are waiting for a verdict. Before this work is "
                  "committed, read each against the code: is it really mess, or does it have to be like that "
                  "to work? Write `fix now` (only for naming a number or address, or deleting commented-out "
                  "code), `fix later: <board row>` or `keep: <why>` on its Verdict line. The commit is refused "
                  "until they all have one. The verdict is never skipped, even when usage is low: do less, not "
                  "worse. Only if the session is ENDING: commit with `inspector: carry over` in the message.")
    return 0


def staged(repo, include_unstaged):
    names = git(repo, "diff", "--cached", "--name-only", "--diff-filter=ACMR") or ""
    if include_unstaged:
        names += git(repo, "diff", "--name-only", "--diff-filter=ACMR") or ""
    return sorted({n for n in names.splitlines() if n})


def record_dirty(repo, rec):
    """Does the notes folder hold changes that are not staged (or not committed, when final)?"""
    if not os.path.isdir(rec.path):
        return False
    out = git(repo, "status", "--porcelain", "--", rel_to(repo, rec.path))
    return bool(out) and any(l[1:2] != " " for l in out.splitlines())  # Y column: not staged, or untracked


def log_carry(repo, prefix, items):
    try:
        os.makedirs(home(), exist_ok=True)
        with open(carry_log(), "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')}\t{repo}\t{prefix}\t{','.join(i['id'] for i in items)}\n")
    except OSError:
        pass


def hold_message(rec, repo, stop, final=False):
    rel_rec = rel_to(repo, rec.path)
    when = "this session cannot close yet" if final else "this commit is held"
    lines = [f"INSPECTOR: {when}. {len(stop)} note(s) need an answer in {rel_rec}/:"]
    lines.extend(describe(i) for i in stop)
    lines.append("Read each against the code. Write `fix now` (only LOOSE-NUMS, LOOSE-ADDRESS, DEAD-CODE, and fix "
                 "it), `fix later: <board row>`, or `keep: <why it has to stay>` on its Verdict line, commit the "
                 "notes folder, then try again. Out of time? `inspector: carry over` in the commit message (or "
                 "the command) lets it through; the notes wait for the next session.")
    return "\n".join(lines)


def gate(repo, include_unstaged=False, carry=False):
    """(refusal message or None) for a commit. Inspects the staged source files first, so Bash edits
    are noted too. In `end` mode a commit is never held: the notes are only recorded."""
    by_prefix = {}
    for r in staged(repo, include_unstaged):
        if ic.is_source(r):
            prefix = project_prefix(repo, r)
            if repo_allowed(repo, prefix):
                by_prefix.setdefault(prefix, []).append(r)
    carried = []
    for prefix, rels in sorted(by_prefix.items()):
        results = check_files([os.path.join(repo, r) for r in rels])
        if mode() == "end":
            continue
        rec = results[(repo, prefix)][0] if (repo, prefix) in results else Record(repo, prefix)
        stop = blocking(rec, set(rels))
        if stop and not carry:
            return hold_message(rec, repo, stop)
        if record_dirty(repo, rec) and not include_unstaged:
            rel_rec = rel_to(repo, rec.path)
            return (f"INSPECTOR: {rel_rec}/ has changes that are not staged. The notes travel with the "
                    f"work: `git add {rel_rec}` and commit again.")
        if stop:
            carried.append((prefix, stop))
    for prefix, stop in carried:
        log_carry(repo, prefix, stop)  # safety rule 2: the emergency save goes through, notes carry over
    return None


def project_units(root, name):
    """(repo, prefix) pairs holding project `name` under a clone root: its own repo, and its folder in
    any repo that keeps one folder per project (staging)."""
    out = []
    own = os.path.join(root, name)
    if os.path.exists(os.path.join(own, ".git")):
        out.append((os.path.normpath(own), ""))
    for multi in (read_conf("inspector_multi") or "staging").split(","):
        m = os.path.join(root, multi.strip())
        if multi.strip() and os.path.isdir(os.path.join(m, name)) and os.path.exists(os.path.join(m, ".git")):
            out.append((os.path.normpath(m), name + "/"))
    return out


def final_gate(root, names, carry=False):
    """End of session (a lane releasing its claim, or `inspector.py final`): every note from this
    project must be answered and the notes folder committed. (refusal message or None)"""
    for name in names:
        for repo, prefix in project_units(root, name):
            if not repo_allowed(repo, prefix):
                continue
            rec = Record(repo, prefix)
            rec.save()  # file what was answered (to decided.md) before checking the folder is committed
            stop = blocking(rec)
            if stop and carry:
                log_carry(repo, prefix, stop)
                continue
            if stop:
                return hold_message(rec, repo, stop, final=True)
            if os.path.isdir(rec.path) and git(repo, "status", "--porcelain", "--", rel_to(repo, rec.path)):
                return (f"INSPECTOR: the notes in {project_name(repo, prefix)} ({rel_to(repo, rec.path)}/) are "
                        f"answered but not committed. Commit and push them, then close the session.")
    return None


def units_in(repo):
    """Every project in a repo that has a notes folder: the repo itself, or its per-project folders."""
    out = []
    if os.path.isdir(record_dir(repo)):
        out.append((repo, ""))
    if os.path.basename(os.path.normpath(repo)).lower() in [
            n.strip().lower() for n in (read_conf("inspector_multi") or "staging").split(",")]:
        for name in sorted(os.listdir(repo)):
            if os.path.isdir(record_dir(repo, name + "/")):
                out.append((repo, name + "/"))
    return out


def backup_held(repo, prefix):
    """While work is kept back from GitHub, keep a second copy of it in the Inspector's own folder:
    a git bundle of the commits not yet pushed (user-directed, 2026-09-26). Restore with `git fetch <bundle>`."""
    upstream = git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    span = f"{upstream.strip()}..HEAD" if upstream else "HEAD"
    if upstream and not (git(repo, "rev-list", "--count", span) or "0").strip().strip("0"):
        return None  # nothing unpushed
    folder = os.path.join(home(), "held", project_name(repo, prefix))
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError:
        return None
    path = os.path.join(folder, time.strftime("%Y-%m-%d_%H%M%S") + ".bundle")
    return path if git(repo, "bundle", "create", path, span) is not None else None


def push_gate(repo, carry=False, commits_first=False):
    """`inspector_mode = end`: saves stay on this PC until the notes are answered (user-directed, 2026-09-26).
    A `git push` is held while any note in this repo waits, or the notes folder is not committed.
    (refusal message or None)"""
    if mode() != "end":
        return None
    for r, prefix in units_in(repo):
        if not repo_allowed(r, prefix):
            continue
        rec = Record(r, prefix)
        rec.save()  # file what was answered before looking
        stop = blocking(rec)
        if stop and carry:
            log_carry(r, prefix, stop)
            continue
        if stop:
            kept = backup_held(r, prefix)
            where = f" A backup copy is in {kept}." if kept else ""
            return (hold_message(rec, r, stop, final=True).replace(
                "this session cannot close yet", "this upload to GitHub is held; the saves are safe on this PC")
                + where)
        status = (git(r, "status", "--porcelain", "--", rel_to(r, rec.path)) or "").splitlines()
        # `git commit ... && git push` in one command: staged notes are about to be committed.
        pending = [l for l in status if not (commits_first and l[1:2] == " ")]
        if pending:
            return (f"INSPECTOR: the notes in {project_name(r, prefix)} ({rel_to(r, rec.path)}/) are answered but "
                    f"not committed. Commit them, then push.")
    return None


def scan_roots():
    roots = [read_conf(k) for k in ("inspector_root", "root")]
    return [r for r in roots if r and os.path.isdir(r)]


def brief(session=None):
    """Session start: notes left unanswered by an earlier session. Only projects the Inspector may
    look at, found under the configured roots and in the carry-over log."""
    units = set()
    for root in scan_roots():
        for name in sorted(os.listdir(root)):
            for unit in project_units(root, name):
                units.add(unit)
    for log in (carry_log(), projects_log()):
        try:
            with open(log, encoding="utf-8") as f:
                for e in (l.rstrip("\n").split("\t") for l in f if l.strip()):
                    if len(e) >= 3 and os.path.isdir(e[1]):
                        units.add((os.path.normpath(e[1]), e[2]))
        except OSError:
            pass
    out = []
    for repo, prefix in sorted(units):
        if not repo_allowed(repo, prefix) or not os.path.isdir(record_dir(repo, prefix)):
            continue
        rec = Record(repo, prefix)
        waiting = [i for i in blocking(rec) if session is None or i.get("session", "") != session]
        if waiting:
            out.append(f"  {project_name(repo, prefix)}: {len(waiting)} note(s) in {rel_to(repo, rec.path)}/")
    if not out:
        return ""
    return ("INSPECTOR: an earlier session ended with notes unanswered, so they carried over. Answer them "
            "FIRST, before other work on that project:\n" + "\n".join(out))


def session_file(session):
    return os.path.join(home(), "sessions", re.sub(r"[^\w\-]", "_", session) + ".json")


def note_session_checks(session, n):
    """Count the source files looked over in a session, so a quiet session still shows the Inspector ran."""
    p = session_file(session)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        data["checked"] = int(data.get("checked", 0)) + int(n)
        data["last"] = time.strftime("%Y-%m-%d %H:%M")
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f)
    except OSError:
        pass


def known_projects():
    """(repo, prefix) for every project the Inspector has notes for on this PC."""
    out = []
    try:
        with open(projects_log(), encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) == 3 and os.path.isdir(parts[1]):
                    out.append((parts[1], parts[2]))
    except OSError:
        pass
    return list(dict.fromkeys(out))


def session_summary(session):
    """One line for the end of a session: how much the Inspector found in THIS session's code, and what
    became of it (2026-09-30, so the user can see whether it is an active part of the work)."""
    if not enabled():
        return "🔍 Inspector: off on this PC (`inspector = on` in lanes.conf switches it on)."
    if not session:
        return "🔍 Inspector: on, but this session's id is unknown, so nothing can be counted."
    counts, projects, checked = session_counts(session)
    if not counts["found"]:
        if not checked:
            return "🔍 Inspector: on, no code was written in this session."
        return f"🔍 Inspector: looked over {checked} file edit(s) this session and found nothing messy."
    where = f" in {', '.join(sorted(projects))}" if projects else ""
    return (f"🔍 Inspector this session{where}: {counts['found']} found · {counts['fixed']} fixed · "
            f"{counts['keep']} kept on purpose · {counts['later']} left for later · {counts['waiting']} unanswered "
            f"({checked} file edit(s) looked over).")


def session_counts(session):
    """(counts, projects, edits looked over) for one session, shared by the long line and the box cell."""
    counts = {"found": 0, "fixed": 0, "keep": 0, "later": 0, "waiting": 0}
    projects = set()
    tag = f"session:{session}"
    for repo, prefix in known_projects():
        rec = Record(repo, prefix)
        mine = [i for i in rec.items.values() if i.get("session") == session]
        gone = [c for c in rec.cleared if tag in c]
        if mine or gone:
            projects.add(project_name(repo, prefix))
        counts["found"] += len(mine) + len(gone)
        counts["fixed"] += len(gone)
        for i in mine:
            state = verdict_state(i["verdict"], i["kind"])
            if state in ("keep", "later"):
                counts[state] += 1
            else:
                counts["waiting"] += 1  # waiting, fix now not done yet, or an invalid fix now
    checked = 0
    try:
        with open(session_file(session), encoding="utf-8") as f:
            checked = int(json.load(f).get("checked", 0))
    except (OSError, ValueError):
        pass
    return counts, projects, checked


def session_cells(session):
    """The same count as session_summary, short enough for one cell of the close-out box
    (handover.py close, 0.40.0). Never raises: the box must print whatever state the Inspector is in."""
    if not enabled():
        return "off (`inspector = on` in lanes.conf switches it on)"
    if not session:
        return "on, but this session's id is unknown"
    counts, projects, checked = session_counts(session)
    if not counts["found"]:
        if not checked:
            return "on, no code was written"
        return f"looked over {checked} file edit{'' if checked == 1 else 's'}, nothing messy"
    text = (f"{counts['found']} found · {counts['fixed']} fixed · {counts['keep']} kept · "
            f"{counts['later']} for later · {counts['waiting']} unanswered")
    return text + (" ⚠️" if counts["waiting"] else "")


def stats(repo, prefix=""):
    """For in-house testing: how the verdicts split, per kind."""
    rec = Record(repo, prefix)
    table = {}
    for i in rec.items.values():
        row = table.setdefault(i["kind"], {})
        s = verdict_state(i["verdict"], i["kind"])
        row[s] = row.get(s, 0) + 1
    lines = [f"INSPECTOR stats for {project_name(repo, prefix)}: {len(rec.items)} findings, {len(rec.old)} "
             f"already there before, {len(rec.cleared)} cleared"]
    for kind in sorted(table):
        lines.append(f"  {kind:<14} " + "  ".join(f"{k} {v}" for k, v in sorted(table[kind].items())))
    return "\n".join(lines)


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[1], argv[2:]
    session = None
    if "--session" in rest:
        i = rest.index("--session")
        session, rest = rest[i + 1], rest[:i] + rest[i + 2:]
    if cmd == "check":
        return cmd_check(rest, session)
    if cmd == "brief":
        text = brief(session)
        if text:
            print(text)
        return 0
    if cmd == "summary":
        line = session_summary(session or os.environ.get("CLAUDE_CODE_SESSION_ID") or "")
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # a Windows console's code page has no emoji
        except (AttributeError, ValueError):
            pass
        print(line)
        return 0
    if cmd == "final" and len(rest) >= 2:
        msg = final_gate(os.path.abspath(rest[0]), rest[1:], carry="--carry" in rest)
        print(msg or "INSPECTOR: every note is answered and committed; the session may close.")
        return 1 if msg else 0
    if not rest:
        print(f"inspector: {cmd} needs a repo or project folder (try --help)", file=sys.stderr)
        return 2
    repo, prefix = locate(rest[0])
    if not repo:
        print(f"inspector: not inside a git repo: {rest[0]}", file=sys.stderr)
        return 2
    if cmd == "review":
        listing = (git(repo, "ls-files", "--", prefix or ".") or "").splitlines()
        results = check_files([os.path.join(repo, r) for r in listing], baseline=False, session=session)
        for (r, p), (rec, raised, cleared) in results.items():
            print(f"INSPECTOR review of {project_name(r, p)}: {len(raised)} finding(s) raised, written to {rec.path}")
        return 0
    if cmd == "gate":
        msg = gate(repo, "--all" in rest)
        print(msg or "INSPECTOR: nothing holds this commit.")
        return 1 if msg else 0
    if cmd == "status":
        rec = Record(repo, prefix)
        waiting = blocking(rec)
        print(f"INSPECTOR: {len(waiting)} waiting, {len(rec.items) - len(waiting)} decided, "
              f"{len(rec.old)} already there before, in {rec.path}")
        for i in waiting:
            print(describe(i))
        return 0
    if cmd == "stats":
        print(stats(repo, prefix))
        return 0
    print(f"inspector: unknown command {cmd!r} (try --help)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
