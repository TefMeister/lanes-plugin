---
description: (Setup) First-run walk-through - first asks what name sessions should call you in notes and on GitHub (default "User") and what to call this PC (default PC1, PC2 ...), then the optional tools the lanes use - Git, Python, build tools, debuggers and decompilers with their MCP servers, Blender + Blender MCP, gamepad and VR runtimes, and our Hand Freeze app. For each missing tool it offers to install it for you, or gives you the official link to do it yourself, or skips it. Safe to re-run any time; it only ever adds what you say yes to.
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
- **Every offer is made once** (0.75.0, the maintainer: "any offer has to be one time only"). Before an offer
  that `tools/offers.py list` names (thanks, shortcut, openxr-sim, begone-record, superpowers, estate), run `offers.py should <name>`; exit 3 means it
  was made already on this PC, so skip it without a word. After asking, whatever the answer, run
  `offers.py made <name> <yes|no>`. The person can still ask for any of them by name later.
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

## 0.6.5 A whole GitHub setup in one go? (0.78.0, only if no board is set yet, offered once)

Only if `lanes.conf` has no `board =` yet and `python "${CLAUDE_PLUGIN_ROOT}/tools/offers.py" should estate` says
`offer`. Say in plain words: Lanes works best with a few private repos (the work board, ideas, hand-overs between
PCs, saved builds, session write-ups), a copy of each for every kind of session, and a repo per project with its
folders and inboxes ready; Claude can build all of it on a GitHub account, new or one they already have, and shows
the plan before making anything. Ask **one question**: *"Set up your GitHub the Lanes way, with the work board,
the ideas repo and the rest, all private?"* Options: **"Yes"** and **"Not now"**. Either way run
`offers.py made estate <yes|no>`.
- **Yes:** follow `${CLAUDE_PLUGIN_ROOT}/docs/NEW-ACCOUNT.md`. Steps 1 to 3 are the person's own hands (making
  the account, installing Git and gh, `! gh auth login`): hand them over as one plain block, skipping what
  `python "${CLAUDE_PLUGIN_ROOT}/tools/estate.py" check` shows is done. Ask for the folder (step 4), run
  `estate.py plan --root <folder>`, show it in plain words, and on a yes run `estate.py make --root <folder>`
  (with `--skip`/`--name` if they asked). Name each repo before it is made; all are private. A first project:
  `estate.py project <name>`, private unless they say public (the guard asks again).
- **Not now:** say they can ask for it any time ("set up my GitHub the Lanes way").
After a yes, 0.7 below is already done when `builds =` is set: skip it.

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

## 0.10 Videos: DaVinci Resolve and FFmpeg (0.48.0, only if they record or share their work)

If the person records test runs or makes progress videos, offer the catalog's section 8 group: **DaVinci Resolve**
(free) as the editor they cut videos in, and **FFmpeg** with it, which is what Claude uses on the recordings (cutting,
joining, still frames, converting files the free Resolve will not open). Say plainly that Resolve runs without FFmpeg,
but the free version cannot open some recordings, so the two are best installed together. Resolve is downloaded by
the person (a short sign-up form on Blackmagic's site); FFmpeg Claude can install with winget.

## 0.11 Keep conversations short? (0.63.0, everyone)

Say in plain words: a long conversation costs more with every message and gets vaguer; Claude Code summarises it
by itself when it is nearly full, and Lanes can make that happen earlier while saving everything first. Ask **one
question**: *"Should conversations be summarised earlier, at about 40% full, with everything important saved
first?"* Options: **"Yes"** and **"Not now"**. On yes run `python tools/compact.py on` and say it applies from the
next restart of Claude Code. If it answers that this Claude Code does not have the setting, say the close-out box
will tell them when it is safe to type `/clear` instead. What it does: `docs/PROTOCOL.md` §21.

## 0.12 Thank the people your work uses? (0.75.0, everyone with a GitHub account, offered once)

Only if `python "${CLAUDE_PLUGIN_ROOT}/tools/offers.py" should thanks` says `offer`. Say in plain words: much of
what sessions use comes from other people's free tools, mods and findings on GitHub; a star and a follow is how
GitHub says thank you. Ask **one question** (AskUserQuestion): *"Should sessions star and follow, on your GitHub
account, the people whose tools, mods or findings your work uses, even one useful fact?"* Options: **"Yes"** and
**"No thanks"**. Then run `offers.py made thanks yes` or `offers.py made thanks no`.
- **Yes:** run `python "${CLAUDE_PLUGIN_ROOT}/tools/thanks.py" on`, then `thanks.py status`. If it says GitHub
  has not given permission to follow people, hand over the one line it prints (`! gh auth refresh -h github.com
  -s user:follow`, a browser sign-in) and run `thanks.py credits` once it is done; otherwise run `thanks.py credits`
  now. It stars the projects Lanes is built on and follows their owners. Say it is undone any time with
  `thanks.py off` (nothing starred is taken back).
- **No thanks:** run `thanks.py off`. Nothing is starred or followed, and it is not asked again.
No GitHub account or no `gh`: skip it and record `offers.py made thanks no-github`. What sessions do with it:
`docs/PROTOCOL.md` section 25.

## 0.13 Record the game while BeG0nE logs? (0.76.0, VR modders, offered once)

Only if `python "${CLAUDE_PLUGIN_ROOT}/tools/offers.py" should begone-record` says `offer`, and only for someone
who makes VR mods (BeG0nE is on: `begone =` in lanes.conf). Say in plain words: whenever the jitter checker logs a
headset session, the game's own window (and the pretend headset's view) can be recorded at the same time, so
every jittery second it finds can also be looked at picture by picture; only the game's windows are recorded,
never the screen, and the files stay on this PC (the recordings folder). It needs OBS, FFmpeg and Python's
`obsws-python` (and Pillow + numpy for the held/jumped count); offer whichever is missing first. Ask **one
question**: *"Record the game by itself whenever the jitter checker is logging, so each jitter can be seen frame by
frame?"* ("Yes" / "No thanks"). Yes writes `begone_record = yes` to lanes.conf; no writes `begone_record = no`.
Either way run `offers.py made begone-record <answer>`. What it does: `docs/PROTOCOL.md` section 26.

## 0.14 The superpowers skills (0.77.0, everyone, offered once)

Only if `python "${CLAUDE_PLUGIN_ROOT}/tools/offers.py" should superpowers` says `offer`, and only if
`claude plugin list` does not already show `superpowers@` (already there: run `offers.py made superpowers
had-it` and say nothing). The maintainer asked for it to be offered on every install (2026-10-17). Say in plain
words: superpowers (by obra, from Anthropic's official plugin list) is a set of working habits Claude follows on
its own: think a job through before building it, hunt a bug down step by step instead of guessing, and check the
work before calling it done. Ask **one question**: *"Add the superpowers skills, so Claude plans, debugs and checks
its work more carefully?"* ("Yes" / "No thanks"). Yes runs `claude plugin install
superpowers@claude-plugins-official` (it needs a restart of Claude Code to take effect; say so). Either way run
`offers.py made superpowers <answer>`.

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
apps → 3D → VR → recording and editing videos**. For each group with anything missing, ask **one question** (AskUserQuestion,
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

## 3.5 Hand Freeze (0.64.0, in the VR group, only if they have a VR headset)

Our own small desktop app (catalog section 6): it holds both VR controllers still in any OpenXR game, so hand and
weapon poses can be tuned with the mouse while the controllers lie on the desk. It is offered with the VR group like
any other tool. "Install it for me" runs `python "${CLAUDE_PLUGIN_ROOT}/tools/hand-freeze.py" install`: it downloads
the newest release from GitHub, puts a **Hand Freeze** icon on the Desktop, and needs no administrator rights. Say in
one line that it must be switched **ON before a game starts**, and that it works with OpenXR games only.
"Give me the links" gives https://github.com/TefMeister/hand-freeze-vr/releases (download the zip, unzip, right-click
`install.ps1` → Run with PowerShell).

## 3.6 The pretend headset and VR Bench (0.74.0, in the VR group)

When the VR group reaches the **OpenXR Simulator** or **VR Bench** row and either is missing, and
`offers.py should openxr-sim` says `offer`, offer them together as ONE question (AskUserQuestion), worded for someone who has never heard of either:

1. **OpenXR Simulator (webhead2oo9's build) + VR Bench** *(Recommended)*: a pretend headset that shows a VR game's two
   eyes in a desktop window and also runs 32-bit games, plus VR Bench, our robot player that learns a game's menus
   and controls by itself, and, with a real headset, marks the spot you point at when you hold both grips and the
   left trigger. Runs `python "${CLAUDE_PLUGIN_ROOT}/tools/openxr-sim.py" install --fork --bench`.
2. **OpenXR Simulator (webhead2oo9's build) only**: the pretend headset, 64-bit and 32-bit games.
   Runs `openxr-sim.py install --fork`.
3. **OpenXR Simulator (elliotttate's original)**: the pretend headset, 64-bit games only. Runs `openxr-sim.py install`.

"No thanks" runs `openxr-sim.py decline`. Whatever was chosen, then run `offers.py made openxr-sim <answer>`. When the simulator is already there and only VR Bench is missing, ask
just "Add VR Bench?" and run `python "${CLAUDE_PLUGIN_ROOT}/tools/vrbench/vrbench.py" install`. Say in one line that
nothing is switched on by installing: the simulator is pointed at per game, and VR Bench is switched on per run.

Then, when VR Bench was chosen, ask once: **"Can a real VR headset be used on this PC?"** ("Yes" / "No, the
simulator only") and write `bench_headset = real` or `bench_headset = none` to lanes.conf. Nothing on the PC can
tell this reliably, so it is asked, never guessed. Then run `vrbench.py profile` and say its tier in one line.
Recording the headset's own view (elliotttate's OpenXR OBS Mirror) comes with the next version; say so in one line.

Credits to say when offering: the simulator is elliotttate's, the 32-bit build webhead2oo9's.

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
