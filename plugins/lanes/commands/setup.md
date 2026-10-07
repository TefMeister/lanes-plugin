---
description: (Setup) First-run walk-through - first asks what name sessions should call you in notes and on GitHub (default "User") and what to call this PC (default PC1, PC2 ...), then the optional tools the lanes use - Git, Python, build tools, debuggers and decompilers with their MCP servers, Blender + Blender MCP, gamepad and VR runtimes. For each missing tool it offers to install it for you, or gives you the official link to do it yourself, or skips it. Safe to re-run any time; it only ever adds what you say yes to.
---

`/lanes:setup` walks the user through **optional** tools, one group at a time. The catalog, with
official links, install commands and checks, is **`${CLAUDE_PLUGIN_ROOT}/docs/TOOLS.md`**. Read it
first, in full, every run. Never install from memory.

## 0. Ground rules

- **Nothing is installed without a yes for that tool.** A yes for one group is not a yes for the next.
- **Official sources only**, exactly as the catalog lists them.
- **Say what each tool is for in one plain sentence** before asking about it. Many users are not
  programmers, and "pefile" means nothing to them. Say what the tool lets a session do.
- **Say it before it happens** when a step needs administrator rights (Windows will ask for
  approval), a large download, a restart of Claude Code, or a browser sign-in.
- **Anything that needs the user's own hands** stays theirs, handed over as one plain block.
  That covers a browser sign-in, a store purchase, a Windows approval, and clicking inside Blender.
  For commands the user can type, suggest the `! <command>` form so the output lands in the session.
- **Never touch a game folder.** Per-game frameworks (catalog section 7) are listed for reference
  only; a game's own session installs them.

## 0.5 What should sessions call you? (asked first, every first run)

Every session follows one naming rule, set by a session-start hook: in anything saved or published
(notes, boards, commit messages, READMEs, issues) the person at this machine is **"User"**, and
their real name, login, e-mail, machine names and home-folder paths are never written. Setup is
where they can choose a different name for sessions to use.

Check what is set now: `python "${CLAUDE_PLUGIN_ROOT}/tools/display-name.py"`. If it already
prints a name other than `User`, say so in one line and move on (do not ask again). Otherwise ask
**one question** (AskUserQuestion), in plain words, for example: *"In notes and on GitHub, sessions
will call you 'User'. Would you like them to use a name or handle of your choosing instead? It will
appear wherever your work is described, including public READMEs."* Options: **"Keep 'User'"** and
**"Choose a name"** (they type it through "Other").

- Save a chosen name with `python "${CLAUDE_PLUGIN_ROOT}/tools/display-name.py" set "<name>"`. It
  refuses anything but letters, digits, spaces and `. _ -`; if refused, say why and ask again.
- ⚠️ **Never suggest their real name, login or account name** as the display name, even if you can
  see it. The whole point is that they choose what is published.
- The rule applies from the next session start; for the rest of this session, follow it already.

## 0.6 What should this PC be called? (asked second, every first run)

Claims and reminders say which PC wrote them, because two sessions on one PC share one keyboard.
They never use the computer's real name; they use a plain name for the PC.

Check what is set now: `python "${CLAUDE_PLUGIN_ROOT}/tools/machine-name.py" suggest`. If
`machine_name` is already in `lanes.conf`, say the name in one line and move on. Otherwise ask **one
question** (AskUserQuestion), for example: *"What should this PC be called in your notes? If you
don't mind, it will just be PC2."* Use the suggested name in the question. Options: **"Use <PCn>"**
and **"Choose a name"** (they type it through "Other").

- Save it with `python "${CLAUDE_PLUGIN_ROOT}/tools/machine-name.py" set "<name>"`, the suggested one
  too. It adds the name to the board's `machines.txt` so no other PC takes it. It refuses spaces, a
  name another PC already has, and the computer's real name; if refused, say why and ask again.
- ⚠️ **Never suggest the computer's real name.**
- Nobody set one? The first claim or reminder takes the next free PC number by itself.

## 0.7 Keep every build? (0.26.0, only if they mod or build something that gets installed)

Ask **one question**: *"Should every change you install be saved as its own numbered version, and sent
to a private GitHub repo so your other PCs can use the same one?"* Options: **"Yes"** and **"Not now"**.
On yes: make a private repo (`gh repo create <name> --private`), clone it, and add
`builds = <that clone>` to `lanes.conf`. Each project is set up the first time it needs it, with
`tools/builds.py init` (see `docs/PROTOCOL.md` §14). On another PC: clone the same repo and set the
same key; if the app sits in a different folder there, also set `builds_app.<project> = <folder>`.

## 0.8 Switch on the Inspector? (0.37.0, only if they have Claude write code)

Ask **one question**: *"Should the Inspector look over every piece of code I write, and note anything
messy for us to decide on before it is uploaded?"* Options: **"Yes"** and **"Not now"**. **No answer means
off.** On yes, ask where its folder should live, offering a default (beside their other backups if you can
find them, otherwise `~/.claude/lanes-inspector`); create it and write `inspector = on` and
`inspector_home = <folder>` to `lanes.conf`. Say in one line that `inspector = off` switches it off again at
any time. What it does: `docs/PROTOCOL.md` §16.

## 0.9 A synced transfer folder for files that must not go on GitHub? (0.47.0, only if they use two or more PCs)

Some files a project needs on both PCs must never be uploaded to GitHub: the app's own files, extracted
assets, recordings, and builds too big for a repo. Say this in plain words, then suggest a **MEGA** account
(**https://mega.io**, free tier available) as the most seamless way to carry them: its desktop app keeps one
folder in step on every PC, so a session only has to save a file there and it turns up on the other PC by itself.
Any other sync service with a desktop app works the same way; MEGA is a suggestion, not a requirement.

⚠️ **Say this plainly, every time it is offered:** the folder is for moving files between **your own** PCs only.
Sharing game files (or any copyrighted files) with other people is illegal, and the folder must never be used for that.

Ask **one question**: *"Would you like steps to set up a synced folder that I will save these files into?"*
Options: **"Yes, give me the steps"** and **"Not now"**. On yes:

1. You create the folder (ask where; a roomy drive is best) with two folders inside: **`Videos`** (recordings) and
   **`Game Files`** (app files, extracted assets, big builds; one folder per project inside it).
2. **User:** install the MEGA desktop app from **https://mega.io/desktop** and sign in (their own hands: an account
   and a password are theirs alone; never ask for or type a password).
3. **User:** in the MEGA app, Settings → **Sync** → **Add sync**: the local folder from step 1, and a new MEGA folder
   with the same name. On the other PC, link that PC's folder to the **same** MEGA folder.
4. You write `transfer = <folder>` to `lanes.conf`, drop a small test file in each subfolder, and check that the
   app picked them up (its log, or the user's word that they show on the MEGA website). Delete the test files after.

From then on, sessions save anything that must travel between PCs but must not be committed into that folder,
sorted into the right subfolder, and say in their write-up what they put there.

## 1. Scan

```bash
python "${CLAUDE_PLUGIN_ROOT}/tools/setup-scan.py"
```

(Use `py` or `python3` if `python` is not the working one; the scan itself explains nothing, so
read `docs/TOOLS.md` alongside it.) Show the user the result as a short grouped list: present / missing.
If the saved state (`setup-scan.py --state`) shows earlier choices, say what they chose last time.
Do not ask again about a tool they skipped unless they ask.

## 2. One group at a time

Go through the groups in the catalog's order: **core → building → reverse engineering → driving
apps → 3D → VR**. For each group with anything missing, ask **one question** (AskUserQuestion,
multi-select). List each missing tool as an option labelled with what it is for, then add these
choices:

- **"Install the ticked ones for me"**: you run the catalog's command for each, one at a time,
  showing the command first.
- **"Give me the links, I'll do it"**: print each tool's official link and its steps as one plain
  numbered block, then wait for "done".
- **"Skip this group"**.

Present tools are not asked about. A group with nothing missing is one line: "Core: all present."

**After each install, run that tool's check** from the catalog, and say plainly whether it passed.
A failed install is reported with its error. Do not quietly move on, and do not retry blindly.
Offer the manual link instead.

## 3. Blender + Blender MCP: check the live link before walking anyone through it

**Check first, then offer.** The scan's Blender MCP line carries a `detail` saying whether the link
actually answers — it asks the add-on inside Blender for the scene, rather than trusting that a
registered server and an add-on file mean a working link:

- **"link live: Blender is open and answering"** — it is done. Say so in one line and **do not print
  any of the steps below.** Someone who set this up months ago must not be walked through it again.
- **"installed, but not answering"** — the files are in place and only the two in-Blender clicks are
  left (steps 5–6). Print those two, nothing else. Blender may simply be closed, which is not a fault.
- **Line absent entirely** — nothing is set up; use the full sequence.

Blender MCP is the one setup with steps that only the user can do inside another app, so it gets its
own guided sequence. Use the catalog's numbered steps:

1. Blender from **https://www.blender.org/download/**, or you install it through winget.
2. uv, if it is missing (the MCP server runs through `uvx`).
3. You run `claude mcp add --scope user blender -- uvx mcp-for-blender`.
4. You run `uvx mcp-for-blender install-addon`.
5. **User:** open Blender → Edit → Preferences → Add-ons → enable **"Interface: MCP for Blender"**.
6. **User:** in the 3D viewport press **N** → **MCP for Blender** tab → **Start MCP Server**.
7. **User:** restart Claude Code; the next session shows `blender` in `claude mcp list`.

Print steps 5–7 as one block for the user, then wait. Afterwards, **re-run the scan and read the
`detail` again**: it is what tells you the clicks landed, and it works in the session that made the
change, without waiting for a restart.

## 4. MCP servers need a restart

`claude mcp add` takes effect at the **next** session. When any MCP server was added (x64dbg,
Ghidrust, Blender), end with one line saying so. Do not try to call the new tools in this session.
Checking a server is a different thing from calling it: `claude mcp list` reports whether each one
**starts**, and the Blender probe above reports whether the link **answers**. Use those to confirm
the setup worked; only the tools themselves have to wait.

## 5. Save the state

```bash
python "${CLAUDE_PLUGIN_ROOT}/tools/setup-scan.py" --mark-done --choices '{"<tool id>": "installed-by-claude|user|skip", ...}'
```

Do this even if the user skipped everything, because that is what stops the first-run offer from
repeating every session. Then report:
1. **What is now present**: the scan's final count.
2. **What they chose to do themselves**: the links again, briefly.
3. **Whether Claude Code needs a restart.**

Re-running `/lanes:setup` later is always safe: it only asks about what is still missing. To change
the display name later: `display-name.py set "<name>"`, or `display-name.py clear` to go back to "User".
To rename this PC: `machine-name.py set "<name>"`.
