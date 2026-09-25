---
description: (Ideas) Files every idea waiting in the ideas repo - lines typed into DUMP.md and open issues - word for word into the permanent record, sorted onto each project's page, then copies them to the project so its next session shows them as a numbered list. The session-start check runs this for you whenever something is waiting. Never launches anything; safe beside every other lane.
---

`/lanes:ideas` — **file the waiting ideas.** Ideas arrive whenever the person has them, often from a
phone: a line typed into `DUMP.md` on GitHub, or an issue. This command turns them into filed,
findable ideas, and puts each one in front of the project it is for. The work is clerical and needs
no stronger model than the one running.

**It runs by itself.** When ideas are waiting, the session-start check says so, and the session files
them **first**, before the rest of its work, unless the person has asked for something time-critical.
Say in one plain line that you are doing it. Nobody has to type this command.

Setup, once per machine: `ideas = /path/to/your-ideas-repo` in `~/.claude/lanes.conf`. No ideas repo
yet? Copy `${CLAUDE_PLUGIN_ROOT}/template-ideas/` into a new **private** repo.

## The rules that make it safe

- **The person's words are never edited.** Each idea is copied **verbatim** into a new file in the
  ideas repo's `inbox/`. That folder is append-only: nothing in it is ever changed, moved or deleted.
  It is the permanent record, and it is what makes a filing mistake free to fix.
- **A line leaves `DUMP.md` only after it is saved in `inbox/`** — `ideas.py clear` enforces this. It
  removes only the lines found in the inbox file you name, so an idea typed while you work survives.
- **Never settle or drop an idea yourself.** Filing places and describes ideas. Only the person decides
  which ones get built.
- **Say out loud when a feasibility verdict has not been checked** against the real project. An
  unchecked "looks doable" gets planned around.

## Steps

The tool is `python "${CLAUDE_PLUGIN_ROOT}/tools/ideas.py"` (or `py` / `python3`), below `ideas.py`.

1. **Pull the ideas repo, then read its `README.md`** before the first filing of the session. It holds
   the project names the person uses, the page headings and the tags. Those are theirs, not the plugin's.
2. **See what is waiting:** `ideas.py waiting` and `ideas.py issues`.
3. **Save the words.** Create `inbox/YYYY-MM-DD-<short-slug>.md` holding every waiting line exactly as
   typed, one per line, with no edits. Under them, add one line per idea saying which page and heading it
   went to. A new file every time; never add to an old one.
4. **File each idea** onto its project's page (`pages/<page>.md`, or `games/` in older repos), under the
   heading that matches **what the idea does**, not what it touches. A change to how something looks goes
   under visuals even when it is about a weapon. An unknown project name is not an error: start a new
   page for it and add a row to `repos.tsv` (`-` until the project has a repo and work on it has begun).
   A bare idea with no brackets still gets filed; ask which project only if it is genuinely unclear.
5. **Tag it**, on the line under its heading: whether it is wanted (`[raw]` for anything new) and whether
   it can be built (`[not judged]` unless you actually checked), plus a plain *What it'd take:* line when
   that helps. The tag line must start with a backtick and a square bracket: `` `[raw]` ``.
6. **Clear `DUMP.md`:** `ideas.py clear --from inbox/<the file from step 3>`. Check it reports nothing
   left that should have gone.
7. **Commit and push** the ideas repo: the inbox file, the pages, `repos.tsv` if changed, and `DUMP.md`.
   `git pull --rebase` first.
8. **Close each filed issue** with a comment naming where it went:
   `gh issue close <n> --repo <owner/repo> --comment "filed to pages/<page>.md, <heading>"`.
   Open means not filed yet; closed means filed.
9. **Send them to the projects:** `ideas.py sync --commit`. Each project that `repos.tsv` names gets the
   new ideas in its own `ideas/fresh/` folder.
10. **Reply in two or three plain lines per batch:** which project, which heading and why, and whether
    it looks possible. The detail is in the repo.

## When a session starts work on a project

`/pd`, `/lm` and any hands-on session open with that project's fresh ideas, before other work:

1. `ideas.py sync --commit <repo>`, then `ideas.py list <repo>`.
2. Check each against what is already built, and mark it ✅ already done or 🟡 partly done.
3. Print the numbered list first. The person answers with the numbers to keep.
4. Record the answer: `ideas.py pick <repo> "2,5"` (or `none`). Kept ideas move to `ideas/chosen/`;
   the rest are dropped from that project, and their words stay in the ideas repo's `inbox/`. Commit the
   project's `ideas/` folder and the ideas repo's `decisions.md` and page.
5. **Silence is not an answer.** If nobody replies, carry on with the session and drop nothing; the list
   comes back next time.
6. When a chosen idea has been built: `ideas.py done <repo> <file-stem>`.

`repos.tsv` decides where ideas go: one line per page, a tab, then the project repos it feeds. `*` means
every project with a board file, a clone in the root and no `PAUSED` line on its board. `-` means none
yet. `ideas_skip = repo-a repo-b` in `lanes.conf` keeps frozen projects out of `*`.
