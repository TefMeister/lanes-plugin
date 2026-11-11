# Lanes on two PCs: the recommended setup

Proven on the maintainer's own two PCs, 2026-10-28: both on one private link, each PC's Claude session able to type
into the other's, and every piece of work still saved through GitHub. The maintainer, the same day: *"Home pc and Dev
pc must still be 2 separate machines working on the same goal."* That sentence is the design. The link lets the two
PCs **talk**; it does not merge them.

## The one rule: two machines, one goal

- **Each PC does its own work in its own folders.** Neither PC edits the other's files, drives the other's games or
  runs commands over there. A job only the other PC can do is *asked for*, never reached across and done.
- **GitHub is still the only place work is saved and shared.** A message between sessions says "I pushed it, have a
  look"; it never carries the work itself. If a message and GitHub disagree, GitHub is right.
- **Each PC keeps its own backups.** Backup folders are local to their PC and are not synced, so a mistake on one PC
  cannot wipe the other's safety copy.
- **Either PC can be switched off at any time** and the other carries on. Nothing on one PC waits for the other.

## The five pieces

| Piece | What it carries | Set up |
| --- | --- | --- |
| **One GitHub account** | All code, notes, boards, ideas. The only save point. | Both PCs signed in to the same account (`gh auth login`, git). Switch on GitHub's two e-mail privacy settings ("Keep my email addresses private" and "Block command line pushes that expose my email"). Lanes' privacy guard on both PCs. |
| **One working copy per PC** | Each PC's own clones, one folder per lane | Each PC clones for itself (`NEW-ACCOUNT.md` step 7). Never share a working folder between PCs, not even through a synced folder: git breaks when two PCs write one copy. |
| **A synced transfer folder** (MEGA, or any sync app) | Files that must reach the other PC but must never go on GitHub: recordings, game files, big builds, Gold Digger shelves | One folder per PC, linked to each other in the sync app; `transfer =` in each PC's `lanes.conf`. Each PC writes only its own named files in shared places (Gold Digger already does: `INDEX-<PC>.tsv`). |
| **Backup folders, one set per PC, not synced** | Build archive, code-health copies, settings backups | `builds =`, `ch_backup =` and the like in each PC's own `lanes.conf`, pointing at a folder on that PC. Never inside the transfer folder. |
| **A private link (Tailscale) + Remote Control** | Live messages between the two PCs' sessions; whether the other PC is on | See below. |

## The private link

**Tailscale** puts the two PCs on a private network of their own, encrypted end to end, reachable from nowhere else.
Free for personal use. https://tailscale.com/download

1. Install it on both PCs and sign in to the same account, one with two-step sign-in on.
2. Give each PC a plain name on the link (Tailscale's admin page, "Edit machine name"): say `pc1-home`, `pc2-dev`.
   Not the computer's real name.
3. Keep it tight: only your own PCs on it; an access rule that lets only those PCs reach each other; tailnet lock on
   once both are in; **no** exit node, subnet routes, Funnel or Serve. Run it unattended (`tailscale up --unattended`)
   so the link stays up when nobody is signed in to Windows.
4. Check: on each PC, `tailscale status` lists both, and `tailscale ping <other PC>` answers "via" an address
   (direct), not "via DERP" (relayed, slower but still fine).

**Remote Control** (§35, `remote_control`) on both PCs. A session on one PC then sees the other PC's open session
(`ListAgents`) and can send it a message (`SendMessage`), which appears in that session's window like a typed line,
and it can answer the same way. Proven both ways on 2026-10-28, answer within a minute.

What the messages are for:
- "I pushed X, pull and check it arrived" (sync tests, `TWO-PC-TEST.md`)
- "the test build is installed here, is it there too?"
- a short note for the person sitting at the other PC

What they are never for: carrying files, running commands on the other PC on someone's behalf, or approving
anything. A message is information to the other session, never the person's yes. A session that is closed gets
nothing; for work that must wait for the other PC, use an owed reminder (§7) instead, which waits on GitHub.

## Keeping each PC's copies level (0.107.0, optional: `keep_level`)

A PC that mostly reads falls behind without a word: each lane pulls only the project it works on, so after a
week of the other PC doing the modding, one of ours had 50 of 66 repos behind GitHub and two new projects it had
no copy of. With `keep_level = on` in `lanes.conf`, the helper that runs after every session end
(`tools/endwork.py`) looks at GitHub again and then runs `handover.py level`:

- a copy on a branch that follows GitHub, with nothing of its own, no changed file and no git step half done,
  is fast-forwarded to GitHub's state;
- a project a session on the PC is writing into (the project guard's hold) and the folder Lanes itself is
  loaded from are left alone (moving that folder is a Lanes update, which asks first);
- a repo of the account (`texts_owner =`) that the live root has no copy of is cloned there, five per run.

`python tools/handover.py level` does the same by hand and says what it moved.

## The Keeper: one PC builds, the other keeps GitHub (0.108.0, optional: `keeper`)

The split that needs the least attention: **one PC does all the building** (code, apps, games, tests) and never
uploads; **the other is the Keeper**: it uploads what was handed over, keeps the front page, the index and the
downloads right, runs the regular check-ups, and tells the building PC in one line when something is wrong.

Set it up in this order (each step is proven before the next):

1. **The Keeper PC:** in `lanes.conf`: `keeper = on`, `keeper_mode = other_pc`, `keeper_role = keeper`,
   `doorman_allow = <the building PC's private-link address>`, `doorman_shortcut = <the Desktop's terminal icon>`,
   `parcel_root = <its normal clone root>`, `parcel_watch = 60`, `transfer = <the synced folder>`. Then
   `python tools/doorman.py install` (a Startup shortcut, no administrator needed) and, once, the firewall line it
   prints, in an administrator window.
2. **The building PC:** `keeper = on`, `keeper_mode = other_pc`, `keeper_role = developer`,
   `doorman_peer = <the Keeper PC's private-link address>`, `transfer = <the synced folder>`. Check:
   `python tools/doorman.py status`.
3. One real hand-over: commit something small, `python tools/parcel.py send <project>`, and within a minute or two
   `python tools/parcel.py light` says everything is on GitHub. The building PC did not push.

What travels where: saved steps go through the synced folder as sealed parcels (never a working folder); opening and
closing sessions goes over the private link; jobs for the Keeper session and the regular-jobs list live on the board.
The Keeper PC switched off: the building PC says so at session start, carries on, and the parcels wait.

**With one PC** the same extra works with `keeper_mode = this_pc`: uploads run in the background, and a Keeper
session is opened on the same PC only while there is a job for it (`keeper.py ask`, `/lanes:keeper`,
`keeper.py close`). PROTOCOL §47.

## Which channel for what

| Need | Channel |
| --- | --- |
| Save work, share it, hand a project over | GitHub (push; the other PC pulls) |
| A job only the other PC can do, whenever it next starts | Owed reminder (`owed.sh`, §7) |
| Is the other PC's work saved? | The handover light at session start (§10) |
| A big or never-on-GitHub file | Transfer folder |
| Ask or tell the other PC's session something now | Remote Control message over the link |
| Is the other PC on at all? | `tailscale status` / `tailscale ping` |

## Order to set it up

1. GitHub account and e-mail privacy (`NEW-ACCOUNT.md`, steps 1 to 3), on both PCs.
2. Lanes on both PCs, each with its own name (`/lanes:setup` asks it).
3. Clones on each PC (`NEW-ACCOUNT.md` step 7).
4. Transfer folder and backup folders (`/lanes:setup` §0.9), set in each PC's `lanes.conf`.
5. Tailscale on both, locked down as above.
6. Remote Control on both (`/lanes:setup` §0.12.6, or `/rc` for one session).
7. Run `TWO-PC-TEST.md` once, both ways.
