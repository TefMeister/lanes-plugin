#!/usr/bin/env python3
"""ideas.py - the ideas inbox: catch every idea, file it, and put it in front of the project it is for.

    ideas.py check                          session-start check: prints a notice ONLY when ideas wait
    ideas.py waiting                        print the unfiled lines in DUMP.md, verbatim
    ideas.py issues                         print the open issues on the ideas repo (the second channel)
    ideas.py clear --from inbox/<file>.md   remove from DUMP.md exactly the lines that file holds
    ideas.py sync  [--commit] [repo ...]    copy undecided ideas into <repo>/ideas/fresh/
    ideas.py list  <repo>                   numbered list of a project's fresh ideas
    ideas.py pick  <repo> <n,n,...|none>    keep those numbers, drop the rest, log the decision
    ideas.py done  <repo> <file-stem>       move a chosen idea to ideas/done/ once it is built

HOW IT FITS TOGETHER (0.23.0)
  The person writes ideas as they come - a line in DUMP.md typed on a phone, or an issue - in the form
  `[project; part] the idea`. Filing them needs judgement (which page, which heading, how feasible), so
  a SESSION files them, by the /lanes:ideas command. This tool does every part that needs no judgement:
  it notices that something is waiting (the session-start hook runs `check`), prints it word for word,
  clears DUMP.md safely once the words are saved, and later copies filed ideas into each project's own
  repo so the next session on that project opens with them as a numbered list.

THE SAFETY RULE IN `clear`
  A line leaves DUMP.md only if the same line is already in an inbox/ file. So clearing can never lose an
  idea: either it was copied verbatim first, or it stays where it is. A line typed on the phone WHILE a
  session is filing is not in that inbox file, so it survives the clear - the same reason inboxes are
  drained by explicit list and never by pattern (PROTOCOL.md section 2).

WHERE THINGS ARE (lanes.conf, then environment, then flags)
  ideas       = the ideas repo clone            ($LANES_IDEAS, --ideas)
  root        = the folder holding your clones  ($LANES_ROOT,  --root)
  board       = the board repo                  ($LANES_BOARD)       - used to expand `*` in repos.tsv
  ideas_skip  = projects never offered ideas, space-separated (frozen or archived repos)
  display_name= who "chosen by" names           (see display-name.py)

  The ideas repo holds: DUMP.md, inbox/ (verbatim, never edited), pages/ (or games/) with one
  <page>.md per project, decisions.md, and repos.tsv saying which project repo each page feeds.
  template-ideas/ in the plugin is a ready-made one.

Read-only except: `clear` edits DUMP.md, `sync` writes <repo>/ideas/, `pick`/`done` write ideas/ and
decisions.md. Only `sync --commit` commits. Every other write is left for the session to commit.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# ---- settings (named numbers, one place) --------------------------------------------------------
MARKER = "<!-- write below this line -->"   # DUMP.md: everything below this is waiting to be filed
TAG_LOOKAHEAD_LINES = 4                     # an idea's tag line sits within this many lines of its heading
MAX_ISSUES = 50                             # open issues read per check
TAG_PREVIEW_CHARS = 150                     # how much of a tag line `list` prints
IDEAS_DIR, FRESH, CHOSEN, DONE, DECIDED = "ideas", "fresh", "chosen", "done", "decided.md"
PAGE_DIR_NAMES = ("pages", "games")         # the first that exists in the ideas repo is used
SHARED_PAGE_NOTE = "  (every-project reminder, not new)"
PAUSED_RE = re.compile(r"^[ \t]*\u23f8\ufe0f?[ \t]*\*\*PAUSED", re.M)  # a line starting "⏸️ **PAUSED"
TODAY = datetime.date.today().isoformat()

README = """# Ideas for this project

Filled automatically from the ideas repo by the lanes plugin (`tools/ideas.py sync`). At the start of
every session on this project the session shows `fresh/` as a numbered list; the answer is the numbers
to keep.

| Folder | Holds |
| --- | --- |
| `fresh/` | ideas nobody has decided on yet |
| `chosen/` | ideas that were picked; they become board rows when work on them starts |
| `done/` | chosen ideas that have been built |
| `decided.md` | one line per decision, so a dropped idea is never offered again |

A dropped idea is deleted here but never lost: the original words stay in the ideas repo's `inbox/`.
"""


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


def setting(flag_value, env, key):
    return flag_value or os.environ.get(env, "") or conf_get(key)


def display_name():
    return conf_get("display_name") or "User"


# ---- small helpers ------------------------------------------------------------------------------
def slug(text):
    text = re.sub(r"[`*~_]", "", text).lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:70].rstrip("-")


def read(p):
    return p.read_text(encoding="utf-8")


def write(p, text):
    p.write_text(text, encoding="utf-8", newline="\n")


def pages_dir(ideas):
    override = conf_get("ideas_pages")
    if override:
        return ideas / override
    for name in PAGE_DIR_NAMES:
        if (ideas / name).is_dir():
            return ideas / name
    return ideas / PAGE_DIR_NAMES[0]


def web_url(ideas):
    """https URL of the ideas repo if it is on GitHub, else ''."""
    try:
        url = subprocess.run(["git", "-C", str(ideas), "remote", "get-url", "origin"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
    return f"https://github.com/{m.group(1)}" if m else ""


def gh_repo(ideas):
    u = web_url(ideas)
    return u.split("github.com/", 1)[1] if u else ""


# ---- DUMP.md ------------------------------------------------------------------------------------
def dump_split(dump_text):
    """(head, waiting_lines). head ends with the marker line. With no marker, the whole file is
    'waiting' only for bracket lines - a false alarm is recoverable, a missed idea is not."""
    lines = dump_text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == MARKER:
            return lines[:i + 1], lines[i + 1:]
    return None, [l for l in lines if re.match(r"^\s*\[[^\]]+\]", l)]


def is_idea_line(line):
    s = line.strip()
    return bool(s) and not s.startswith("<!--")


def waiting_lines(ideas):
    dump = ideas / "DUMP.md"
    if not dump.is_file():
        return []
    return [l for l in dump_split(read(dump))[1] if is_idea_line(l)]


def open_issues(ideas):
    repo = gh_repo(ideas)
    if not repo:
        return []
    try:
        out = subprocess.run(["gh", "issue", "list", "--repo", repo, "--state", "open", "--limit",
                              str(MAX_ISSUES), "--json", "number,title"],
                             capture_output=True, text=True, timeout=20)
        return json.loads(out.stdout) if out.returncode == 0 and out.stdout.strip() else []
    except (OSError, subprocess.SubprocessError, ValueError):
        return []


def cmd_check(a, ctx):
    """Silent unless something waits. Never fails: a hook that errors gets switched off."""
    ideas = ctx["ideas"]
    if not ideas or not (ideas / ".git").exists():
        return
    subprocess.run(["git", "-C", str(ideas), "pull", "--ff-only", "--quiet"],
                   capture_output=True, timeout=30)
    n_dump, n_iss = len(waiting_lines(ideas)), (0 if a.no_issues else len(open_issues(ideas)))
    if not n_dump and not n_iss:
        return
    parts = ([f"{n_dump} line(s) in DUMP.md"] if n_dump else []) + ([f"{n_iss} open issue(s)"] if n_iss else [])
    print(f"UNFILED IDEAS WAITING in the ideas repo: {', '.join(parts)}.")
    print("""These are the person's own words, and filing them is what stops an idea being lost.
FILE THEM FIRST, before the rest of this session's work, by following /lanes:ideas - unless the
person has asked for something time-critical, in which case do that first and file straight after.
Say in one plain line at the start that you are filing them. Filing is clerical work: it needs no
stronger model than the one running. Never settle or drop an idea yourself - only the person does.""")


def cmd_waiting(a, ctx):
    lines = waiting_lines(ctx["ideas"])
    if not lines:
        print("DUMP.md: nothing waiting.")
        return
    print(f"DUMP.md: {len(lines)} line(s) waiting, verbatim:")
    for line in lines:
        print(line)


def cmd_issues(a, ctx):
    iss = open_issues(ctx["ideas"])
    if not iss:
        print("no open issues (or no GitHub access from here).")
    for i in iss:
        print(f"#{i['number']}\t{i['title']}")


def cmd_clear(a, ctx):
    ideas = ctx["ideas"]
    src = Path(a.src)
    if not src.is_absolute():
        src = ideas / src
    if not src.is_file() or src.parent.name != "inbox":
        sys.exit(f"ideas.py: --from must be a file in the ideas repo's inbox/ folder, got {src}")
    saved = {l.strip() for l in read(src).splitlines() if l.strip()}
    dump = ideas / "DUMP.md"
    head, rest = dump_split(read(dump))
    if head is None:
        sys.exit("ideas.py: DUMP.md has no '" + MARKER + "' line; clear it by hand, carefully")
    kept, cleared = [], 0
    for line in rest:
        if is_idea_line(line) and line.strip() in saved:
            cleared += 1
        else:
            kept.append(line)
    while kept and not kept[-1].strip():
        kept.pop()
    write(dump, "\n".join(head + [""] + kept).rstrip("\n") + "\n")
    left = [l for l in kept if is_idea_line(l)]
    print(f"DUMP.md: cleared {cleared} line(s) saved in {src.name}; {len(left)} still waiting.")
    for line in left:
        print(f"  still waiting: {line}")


# ---- pages and repos.tsv ------------------------------------------------------------------------
def read_map(ideas):
    out, f = {}, ideas / "repos.tsv"
    if not f.is_file():
        return out
    for line in read(f).splitlines():
        if line.strip() and not line.startswith("#") and "\t" in line:
            page, repos = line.split("\t", 1)
            out[page.strip()] = [] if repos.strip() == "-" else repos.split()
    return out


def parse_page(path):
    """The ideas on one page, in page order: a '### ' heading followed within a few lines by a
    tag line starting with '`['. A heading with no tag line is a sub-heading, not an idea."""
    lines = read(path).splitlines()
    ideas = []
    for i, line in enumerate(lines):
        if not line.startswith("### "):
            continue
        tags = next((l for l in lines[i + 1:i + 1 + TAG_LOOKAHEAD_LINES] if l.startswith("`[")), None)
        if tags is None:
            continue
        end = next((j for j in range(i + 1, len(lines)) if lines[j].startswith(("### ", "## "))), len(lines))
        ideas.append({"title": re.sub(r"~~", "", line[4:]).strip(), "tags": tags,
                      "body": "\n".join(lines[i + 1:end]).strip(),
                      "decided": bool(re.match(r"`\[(settled|killed)\]`", tags))})
    return ideas


def is_paused(board, repo):
    f = board / "status" / f"{repo}.md" if board else None
    return bool(f and f.is_file() and PAUSED_RE.search(read(f)))


def every_active_project(ctx):
    """`*` in repos.tsv: every project with a board file, a clone in the root, and no pause line."""
    board, root = ctx["board"], ctx["root"]
    if not board or not (board / "status").is_dir():
        return []
    skip = set(conf_get("ideas_skip").split())
    repos = sorted(p.stem for p in (board / "status").glob("*.md"))
    return [r for r in repos if r not in skip and (root / r).is_dir() and not is_paused(board, r)]


# ---- the project side ---------------------------------------------------------------------------
def decided_ids(d):
    f = d / DECIDED
    return set(re.findall(r"`([^`]+)`", read(f))) if f.is_file() else set()


def known_ids(d):
    ids = decided_ids(d)
    for sub in (FRESH, CHOSEN, DONE):
        if (d / sub).is_dir():
            ids |= {p.stem for p in (d / sub).glob("*.md")}
    return ids


def fresh_list(d):
    files = list((d / FRESH).glob("*.md")) if (d / FRESH).is_dir() else []

    def order(p):
        m = re.search(r"^Order: (\d+)", read(p), re.M)
        return (int(m.group(1)) if m else 10 ** 9, p.stem)
    return sorted(files, key=order)


def git_commit(repo_path, msg):
    g = ["git", "-C", str(repo_path)]
    subprocess.run(g + ["add", "--", IDEAS_DIR], check=True)
    if subprocess.run(g + ["diff", "--cached", "--quiet"]).returncode == 0:
        return
    subprocess.run(g + ["commit", "-q", "-m", f"{msg}\n\nLane: ideas"], check=True)
    ok = subprocess.run(g + ["pull", "-q", "--rebase"]).returncode == 0 and \
        subprocess.run(g + ["push", "-q"]).returncode == 0
    print(f"  {'pushed' if ok else 'PUSH FAILED'} {repo_path.name}")


def cmd_sync(a, ctx):
    ideas, root = ctx["ideas"], ctx["root"]
    pdir, url = pages_dir(ideas), web_url(ideas)
    wanted, changed, everyone = set(a.repos), {}, None
    for page_no, (page, targets) in enumerate(read_map(ideas).items()):
        pf = pdir / f"{page}.md"
        if not targets or not pf.is_file():
            continue
        shared = targets == ["*"]
        if shared:
            everyone = everyone if everyone is not None else every_active_project(ctx)
            targets = everyone
        for n, idea in enumerate(parse_page(pf)):
            if idea["decided"]:
                continue
            stem = f"{page}--{slug(idea['title'])}"
            for repo in targets:
                if (wanted and repo not in wanted) or not (root / repo).is_dir():
                    continue
                d = root / repo / IDEAS_DIR
                if stem in known_ids(d):
                    continue
                (d / FRESH).mkdir(parents=True, exist_ok=True)
                if not (d / "README.md").is_file():
                    write(d / "README.md", README)
                where = f"`{pf.parent.name}/{page}.md`" + (f" (<{url}/blob/main/{pf.parent.name}/{page}.md>)" if url else "")
                write(d / FRESH / f"{stem}.md",
                      f"# {idea['title']}\n\nOrder: {page_no * 1000 + n}\n"
                      f"From: the ideas repo, {where}, copied {TODAY}\n"
                      + (f"Shared: yes\n" if shared else "") + f"\n{idea['body']}\n")
                changed.setdefault(repo, []).append(idea["title"])
    for repo, titles in changed.items():
        print(f"{repo}: {len(titles)} new idea(s) -> ideas/fresh/")
        if a.commit:
            git_commit(root / repo, f"ideas: {len(titles)} fresh from the ideas repo")
    if not changed:
        print("ideas.py sync: nothing new")


def cmd_list(a, ctx):
    d = ctx["root"] / a.repo / IDEAS_DIR
    files = fresh_list(d)
    if not files:
        print(f"{a.repo}: no fresh ideas waiting.")
        return
    # 2026-09-26 (user feedback): ideas for EVERY project are not new ideas and must not be presented as if they were. They are
    # reminders: each project answers them once, for itself, and every other project keeps its own copy until its own
    # session answers. (pick already works that way; the wording did not say so.)
    shared = sum(1 for p in files if re.search(r"^Shared: yes", read(p), re.M))
    own = len(files) - shared
    parts = ([f"{own} new for this project"] if own else []) + \
        ([f"{shared} every-project reminder(s) not yet answered HERE (other projects keep theirs until they answer)"] if shared else [])
    print(f"{a.repo}: {'; '.join(parts)}. Answer with the numbers to keep; the rest are dropped for {a.repo} only.")
    for i, p in enumerate(files, 1):
        text = read(p)
        title = text.splitlines()[0].lstrip("# ").strip()
        tags = next((l for l in text.splitlines() if l.startswith("`[")), "")
        note = SHARED_PAGE_NOTE if re.search(r"^Shared: yes", text, re.M) else ""
        print(f"  {i:>2}. {title}{note}\n      {tags[:TAG_PREVIEW_CHARS]}")


def cmd_pick(a, ctx):
    d = ctx["root"] / a.repo / IDEAS_DIR
    files = fresh_list(d)
    raw = a.numbers.strip().lower()
    keep = set() if raw == "none" else {int(x) for x in re.split(r"[ ,]+", raw) if x}
    bad = sorted(n for n in keep if not 1 <= n <= len(files))
    if bad:
        sys.exit(f"ideas.py: no idea numbered {bad}; there are {len(files)}")
    (d / CHOSEN).mkdir(parents=True, exist_ok=True)
    who, log, mlog = display_name(), [], []
    for i, p in enumerate(files, 1):
        title = read(p).splitlines()[0].lstrip("# ").strip()
        if i in keep:
            write(p, read(p) + f"\nChosen by {who}: {TODAY}\n")
            p.rename(d / CHOSEN / p.name)
            verdict = "chosen"
        else:
            p.unlink()
            verdict = "dropped"
        log.append(f"- {TODAY} {verdict} `{p.stem}` - {title}")
        mlog.append((p.stem, title, verdict))
        print(f"  {i:>2}. {verdict.upper():8} {title}")
    with open(d / DECIDED, "a", encoding="utf-8", newline="\n") as f:
        if f.tell() == 0:
            f.write("# Decisions on this project's ideas\n\nOne line per idea, so nothing is offered twice.\n\n")
        f.write("\n".join(log) + "\n")
    record_decisions(ctx, a.repo, mlog, who)


def record_decisions(ctx, repo, mlog, who):
    ideas = ctx["ideas"]
    mapping, pdir = read_map(ideas), pages_dir(ideas)
    lines = [f"\n## {TODAY} - picks for `{repo}` (numbered list at session start)\n"]
    for stem, title, verdict in mlog:
        page = stem.split("--", 1)[0]
        lines.append(f"- **{verdict}** for `{repo}`: *{title}* (`{pdir.name}/{page}.md`)")
        if mapping.get(page) == [repo]:       # an idea for this project alone: its tag follows the pick
            set_tag(pdir / f"{page}.md", title, "settled" if verdict == "chosen" else "killed",
                    f"{'picked' if verdict == 'chosen' else 'not picked'} by {who} {TODAY}")
    with open(ideas / "decisions.md", "a", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print(f"ideas repo: decisions.md updated; commit and push {ideas}")


def set_tag(page_file, title, new, note):
    lines = read(page_file).splitlines()
    for i, line in enumerate(lines):
        if line.startswith("### ") and re.sub(r"~~", "", line[4:]).strip() == title:
            for j in range(i + 1, min(i + 1 + TAG_LOOKAHEAD_LINES, len(lines))):
                if lines[j].startswith("`["):
                    lines[j] = re.sub(r"^`\[[a-z]+\]`", f"`[{new}]` - *{note}*", lines[j], count=1)
                    write(page_file, "\n".join(lines) + "\n")
                    return


def cmd_done(a, ctx):
    d = ctx["root"] / a.repo / IDEAS_DIR
    src = d / CHOSEN / f"{a.stem}.md"
    if not src.is_file():
        sys.exit(f"ideas.py: {src} not found")
    (d / DONE).mkdir(parents=True, exist_ok=True)
    write(src, read(src) + f"Built: {TODAY}\n")
    src.rename(d / DONE / src.name)
    with open(d / DECIDED, "a", encoding="utf-8", newline="\n") as f:
        f.write(f"- {TODAY} done `{a.stem}`\n")
    print(f"moved to ideas/done/: {a.stem}")


# ---- main ---------------------------------------------------------------------------------------
def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ideas", help="the ideas repo clone (default: lanes.conf `ideas`)")
    ap.add_argument("--root", help="the folder holding the project clones (default: lanes.conf `root`)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("check"); s.add_argument("--no-issues", action="store_true")
    sub.add_parser("waiting")
    sub.add_parser("issues")
    s = sub.add_parser("clear"); s.add_argument("--from", dest="src", required=True)
    s = sub.add_parser("sync"); s.add_argument("--commit", action="store_true"); s.add_argument("repos", nargs="*")
    s = sub.add_parser("list"); s.add_argument("repo")
    s = sub.add_parser("pick"); s.add_argument("repo"); s.add_argument("numbers")
    s = sub.add_parser("done"); s.add_argument("repo"); s.add_argument("stem")
    a = ap.parse_args()

    ideas = setting(a.ideas, "LANES_IDEAS", "ideas")
    root = setting(a.root, "LANES_ROOT", "root")
    board = os.environ.get("LANES_BOARD", "") or conf_get("board")
    ctx = {"ideas": Path(ideas) if ideas else None, "root": Path(root) if root else Path.cwd(),
           "board": Path(board) if board else None}

    if a.cmd == "check":
        try:
            cmd_check(a, ctx)
        except Exception:        # a session-start check must never be the reason a session errors
            pass
        return
    if not ctx["ideas"] or not ctx["ideas"].is_dir():
        sys.exit("ideas.py: no ideas repo configured. Add `ideas = /path/to/your-ideas-repo` to "
                 "~/.claude/lanes.conf (template-ideas/ in the plugin is a ready-made one).")
    {"waiting": cmd_waiting, "issues": cmd_issues, "clear": cmd_clear, "sync": cmd_sync,
     "list": cmd_list, "pick": cmd_pick, "done": cmd_done}[a.cmd](a, ctx)


if __name__ == "__main__":
    main()
