---
description: (Update) Checks GitHub for a newer version of the lanes plugin, says in plain words what changed, and updates it - only after the user says yes. The same check runs by itself at session start.
---

1. **Check** (fetches now, ignoring the usual few-hour wait):

   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/tools/update-check.py" --json --force
   ```

   Use `py` or `python3` if `python` is not the working one.

   ⚠️ **Read `installed` out of the JSON; do not assume it describes this machine without looking.**
   For a marketplace registered as a local directory, `${CLAUDE_PLUGIN_ROOT}` points at that repo
   clone rather than at the installed copy — so this check used to report the REPO's version as
   installed, find no marketplace at all, and answer "up to date" about a machine it had never
   looked at. Since 0.12.1 it locates the real installed copy itself and sets `ran_from_repo` when
   it had to; `installed_root` then says which copy the answer is about.

2. **Up to date** (`newer` is false): say so in one line, with the version. Go to step 6.

3. **Newer version available:** tell the user in two or three plain sentences:
   - that a new version is out, and which one they have;
   - **what it means for them**, drawn from `changes` (each entry is one plain line per version
     they are missing). List **each version in between with one plain line** on what it adds or changes
     for them (0.66.0: people asked to always see what an update brings). No jargon, one line each;
   - that updating downloads it from GitHub and **takes effect after they restart Claude Code**.

   Then **ask** whether you may update it now. Print this question **word for word, on a line of its
   own, with its bell icon** - a fixed icon, like the reply headings, so it can be spotted without
   reading the rest (2026-09-21):

   🔔 **New plugin update available! Would you like to install it now?**

   and offer the two answers (AskUserQuestion: "Update now" / "Not now").

4. **"Update now"**: run **every** command in `update_commands`, in the order given, and show what
   each printed. There may be two or three: when the marketplace is a local directory whose clone is
   behind, the first is a `git pull` of that clone.

   ⚠️ **Then check the version, do not take the installer's word for it.** Re-run the check with
   `--json --force` and confirm `installed` is the new number. `claude plugin update` installs from
   the marketplace clone's WORKING TREE, so against a stale clone it prints
   *"already at the latest version"* and names the OLD one — success and failure look identical.
   That is what the `git pull` in the command list prevents; verifying is what catches it if
   anything else goes wrong.

   On success, say plainly that it is updated and that they need to restart Claude Code for it to
   take effect. Then, if the plugin's look is on this PC and there is no desktop shortcut yet
   (`python "${CLAUDE_PLUGIN_ROOT}/tools/shortcut.py" status` says "no shortcut yet"), offer one in one plain
   sentence - a shortcut named **Lanes** on the Desktop that opens Claude Code exactly as this terminal looks -
   with AskUserQuestion ("Make the shortcut" / "No thanks"): yes runs `shortcut.py create`, no runs
   `shortcut.py decline` so it is not asked again (0.53.0). If a command fails, show its error in plain words and give them the commands to run
   themselves with `! `. Do not retry in a loop.

5. **"Not now"**:

   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/tools/update-check.py" --dismiss
   ```

   Tell them it will be offered again tomorrow, or any time they type `/lanes:update`.

6. **Hand Freeze, every run** (0.64.0), whichever way steps 2-5 went (an up-to-date plugin does not stop this step):
   `python "${CLAUDE_PLUGIN_ROOT}/tools/hand-freeze.py" status --json`.
   - `installed` false: say nothing (`/lanes:setup` offers it; do not nag).
   - `newer` true: say in one plain line that a newer Hand Freeze is out, and ask (AskUserQuestion: "Update Hand
     Freeze" / "Not now"). Yes runs `hand-freeze.py install`; it refuses while the app is open, so if it says so,
     ask them to close the Hand Freeze window and try once more.
   - Otherwise, or if `error` is set: say nothing.

7. **The OpenXR Simulator, every run** (0.73.0), after step 6:
   `python "${CLAUDE_PLUGIN_ROOT}/tools/openxr-sim.py" status --json`.
   - `installed` false and `declined` false: offer it in one plain sentence - a pretend headset that shows a VR game's
     two eyes in a window on the desktop, so VR work can be checked with no headset plugged in, by elliotttate - and
     ask (AskUserQuestion: "Download it" / "Download the fork for 32-bit games too" / "No thanks"). The first runs
     `openxr-sim.py install`, the second `openxr-sim.py install --fork`, the third `openxr-sim.py decline` so it is
     not offered again. Say that it is NOT switched on by downloading it.
   - `newer` true: one plain line that a newer simulator is out, and ask ("Update it" / "Not now"); yes runs
     `openxr-sim.py install` (add `--fork` when `source` is `fork`). It refuses while a game has it loaded.
   - Otherwise, or if `error` is set: say nothing.

Never update without a yes in this session. A yes from an earlier session does not count.
