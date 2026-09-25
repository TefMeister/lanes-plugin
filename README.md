# lanes

![lanes plugin banner](assets/banner/banner.png)

**A Claude Code plugin for running several Claude sessions at once, across your projects, without
them undoing each other's work.**

## What it is

**The problem.** Two Claude sessions working on one set of files quietly overwrite each other.
Nothing crashes. The work just disappears.

**The fix.** Every session works in a **lane**, and each lane owns its own files. When one lane has
something for another, it leaves a new file in that lane's inbox instead of editing its files. New
files never clash, so git can always merge them.

**A shared board.** One list of every job, each tagged with what it needs. It answers the question
you have at the start of every session: *what can I actually do right now?*

## The lanes

| Command | What it does |
| --- | --- |
| `/lm` | **Live.** Claude runs the app itself: starts it, uses it, closes it, and tests its own changes. |
| `/pd` | **Parallel development.** Picks the next job that needs nothing running, so it can work beside anything else. |
| `/gr` | Web research for each project, kept in that project's notes. |
| `/sr` | Research across all projects, kept in one shared library. |
| `/gs` | Hygiene check: are notes tagged, and are hand-offs being picked up? |
| `/gates` | Shows the work board. |
| `/gate-watch` | Tells you when another session finishes something. |
| `/ideas` | Files the ideas you jotted down, onto the right project. |
| `/setup` | First-run setup: your name, this PC's name, and optional tools. |
| `/update` | Gets the newest version of the plugin, after asking you. |
| `/pt` | Tests the plugin itself. |
| `/ms` | **Manual session.** You do the hands-on work; Claude gives you the steps and writes the code. |

Type them as `/lanes:<name>`, for example `/lanes:pd`.

## How it works

- **One session per lane, one session per job.** A session claims its job, and the others skip it.
- **`/lm` and `/pd` never work on the same project at once.** While `/lm` holds a project, `/pd` is
  stopped from starting on it and picks another. Two sessions on one project was tried and worked
  once in fifty runs, so it was removed. Instead, `/lm` runs its own helper in the background for
  the no-app-needed work on that project.
- **The board says what each step needs:**

  | Tag | Needs |
  | --- | --- |
  | `[PD]` | nothing running |
  | `[USER]` | a person |
  | `[FLAT]` | the app running |
  | `[VR CLAUDE]` | special hardware plugged in, nobody needed |
  | `[VR USER]` | a person using the special hardware |

- **Every finding says how well it is known,** not just what it says.
- **Two PCs?** A job only one PC can do is queued for that PC, and greets it at its next session.
- **Nobody's name is written down.** You are "User" unless you choose a name. Each PC is PC1, PC2
  and so on unless you name it. Your real name, login and computer name are never written.
- **Ideas get filed for you.** Jot them into your ideas repo, even from a phone. The next session
  files them, and each project's next session lists them for you to pick from.

## Get started

```
/plugin marketplace add TefMeister/lanes-plugin
/plugin install lanes@lanes-plugin
```

Then run `/lanes:setup`. It asks what to call you and this PC, then offers the optional tools:
debuggers, Blender, build tools, VR. Say no once and it never asks again.

**Needs:** Claude Code, Git, Python 3.

**Check it first.** Don't take our word that it is safe. [`AUDIT.md`](AUDIT.md) is a request you
paste into your own Claude Code, which then reviews every file before you install.

## Early version

In daily use since 2026-09-09, on two PCs. It was built for turning flat games into VR, so many
examples and optional tools lean that way. The lanes themselves work for any project. Expect changes: `/lanes:update` tells you
what is new and never installs without asking. The full manual is in
[`plugins/lanes/README.md`](plugins/lanes/README.md).

| Plugin | What it does | State |
| --- | --- | --- |
| [`lanes`](plugins/lanes/) | Several Claude Code sessions at once, without them treading on each other. | `0.25.0`, early public release |

## Modding games?

The author's games in progress, and the research behind them, are listed on the author's
[GitHub profile](https://github.com/TefMeister).

## Licence

MIT, see [LICENSE](LICENSE).

*Made for Claude Code; not made by, or affiliated with, Anthropic.*
