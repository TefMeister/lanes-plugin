# A new GitHub account, set up the Lanes way


This guide takes you from no GitHub account to the whole working setup Lanes is built around: the shared work
board, the ideas repo, the hand-over repo, the build archive, the session logs, one copy of everything for each
kind of session, and a repo for each project with its folders and inboxes already in place.

You do steps 1 to 3 yourself (they need your own hands: a sign-up and a browser sign-in). Claude does the rest,
with `tools/estate.py`, and shows you what it will make before it makes anything.


What it never does


- It never deletes, empties or overwrites anything. A repo or folder that is already there is left alone.
- It never makes anything public. Every repo is private unless you ask for one to be public, and then you are
  asked again before it happens.
- It never touches a game or app folder.


STEP 1 - Make the GitHub account


1.1  Open https://github.com/signup and follow the steps.

1.2  Pick a user name you are happy for others to see. It is on every public page you ever make, so it does not
     have to be your real name.

1.3  Confirm the e-mail GitHub sends you.

1.4  Turn on two-factor sign-in: https://github.com/settings/security (GitHub asks for it anyway, sooner or later).

1.5  Optional, recommended: https://github.com/settings/emails, tick "Keep my email addresses private". Your
     commits then carry a GitHub no-reply address instead of your e-mail.


STEP 2 - Install Git and GitHub's command line tool


2.1  The easiest way: type `/lanes:setup` in Claude Code and say yes when it offers Git and the GitHub CLI.

2.2  Or do it yourself. On Windows, in a terminal:

    winget install --id Git.Git -e
    winget install --id GitHub.cli -e

     Or download them from https://git-scm.com/downloads and https://cli.github.com

2.3  Close the terminal and Claude Code and open them again, so they find the new tools.


STEP 3 - Sign the GitHub tool in to your account


3.1  In Claude Code, type this (the `!` runs it right in the session):

    ! gh auth login

3.2  Answer: `GitHub.com`, then `HTTPS`, then `Yes` (use it for Git too), then `Login with a web browser`.

3.3  It shows a code of eight letters. Press Enter, a browser opens, paste the code, approve.

3.4  Check it worked:

    ! gh auth status

     It should say "Logged in to github.com account <your name>".

- Already signed in to a different account? `gh auth login` adds the new one, and `gh auth switch` swaps
  between them. Check with `gh auth status` that the new one is the active one before step 5.


STEP 4 - Pick the folder for your copies


4.1  Pick a drive with room and a folder for the working copies of every repo, for example `D:\lanes\clones`.

4.2  Lanes makes four more beside it (`clones-pd`, `clones-gr`, `clones-sr`, `clones-gs`): each kind of
     session works in its own copy, so two sessions running at once can never trip over each other's files.
     They share their storage, so they cost very little space.


STEP 5 - Let Claude build the rest


5.1  Tell Claude: "set up my new GitHub account the Lanes way, clones in D:\lanes\clones" (your folder from
     step 4). `/lanes:setup` offers this too, once.

5.2  Claude first shows you the plan (`estate.py plan`), which does nothing: every repo it would make, and
     where. Say yes, or ask for different names.

5.3  Then it builds it (`estate.py make`). You get these private repos:

| Repo | What it is for |
| --- | --- |
| `board` | the shared work board: one page per project saying what is left and what each step needs, plus reminders for jobs only one PC can do |
| `ideas` | ideas written down as they come (from your phone too) and sorted later, so none is lost |
| `staging` | unfinished work and hand-offs between your PCs |
| `builds` | every change you install, saved as its own numbered version, so you can always go back |
| `session-logs` | every session's write-up, so a problem that comes back can be looked up |

5.4  It copies each one into all five folders, and writes where they are into Lanes' settings file
     (`~/.claude/lanes.conf`), so every session finds them by itself.

- Leave one out: "skip the builds repo" (`--skip builds`). Rename one: "call the board my-board"
  (`--name board=my-board`). The board cannot be left out: every session reads it.


STEP 6 - Start your first project


6.1  Tell Claude: "start a project called my-game" (`estate.py project my-game`).

6.2  You get a private repo `my-game` with these folders, each with a short note inside saying what goes there:

| Folder | What it holds |
| --- | --- |
| `dev-archive/` | the working code and its whole history |
| `notes/` | readable progress notes, newest first |
| `engine-research/` | what is known about how the game or app works, and what was tried and failed |
| `external-research/` | what other people have published about it, gathered by `/gr` |

6.3  The research folders have an `inbox/`: other kinds of session drop findings there as new files instead of
     editing someone else's notes. That is what lets several sessions run at once safely.

6.4  The project also gets its page on the board, with its first step, and a copy in every session folder.

6.5  Want the project public (for a mod others can follow)? Say so. Claude asks you once more before it happens.


STEP 7 - A second PC


7.1  On the second PC, do steps 2 and 3, signing in to the same account.

7.2  Tell Claude the same thing as in step 5, with that PC's folder. Everything already on GitHub is copied down;
     nothing is made twice.


STEP 8 - Optional extras


8.1  `/lanes:setup` offers the rest one at a time, each only once: a name for sessions to call you, a name for
     this PC, the code checker, a synced folder for files that must never go on GitHub, and starring the
     people whose work yours uses.

8.2  A public front page: on GitHub, a public repo named exactly like your account shows its README on your
     profile. Make it only if you want one, then set `frontpage = <its README>` in `lanes.conf`.


UNDO


- Lanes never deletes repos. To remove one, open it on GitHub, Settings, scroll to the bottom, "Delete this
  repository".
- The settings it wrote are plain lines at the end of `~/.claude/lanes.conf`, each marked `(estate.py)`; delete
  a line to forget it.
