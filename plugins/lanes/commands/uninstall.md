---
description: (Uninstall) Takes Lanes off this PC in one go - the look, the Desktop shortcut, the background helpers, its own settings and state, and finally the plugin itself - after showing what it will do and getting a yes. Never touches the person's own work or the tools setup installed.
---

1. **Show the plan first** (it changes nothing):

   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/tools/uninstall.py" plan
   ```

   Tell the person in plain words what is on this PC and what will go, one short line per item, and say clearly what
   STAYS: every repo, board, note, build, recording and game folder, and the tools setup installed (those are listed
   with how to remove them by hand, if they want).

2. **Ask once** (AskUserQuestion): *"Take Lanes off this PC now?"* Options: **"Yes, take it all off"**,
   **"Yes, but keep my settings"** (name, PC name, folders, for a reinstall later) and **"No, leave it"**.

3. **On a yes, run it** (add `--keep-settings` for the second choice):

   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/tools/uninstall.py" do
   ```

   It stops BeG0nE's rider and the OBS auto-recorder, removes the Desktop shortcut, puts the terminal look back,
   deletes Lanes' own state, puts `lanes.conf` aside as `lanes.conf.uninstalled-<date>` (never deleted), and LAST
   removes the plugin from Claude Code (`claude plugin uninstall lanes@lanes-plugin`) and its source. Last on purpose:
   while the plugin is installed, its session-start hooks would put the look straight back.

4. **Report** each line it printed, in plain words, and any `FAILED` line with what to do about it. End with: restart
   Claude Code to finish, since this window keeps Lanes loaded until then.

Never run step 3 without the yes in step 2. Nothing here touches a repo or a game folder.
