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
   take effect. Then, if the plugin's look is on this PC, there is no desktop shortcut yet
   (`python "${CLAUDE_PLUGIN_ROOT}/tools/shortcut.py" status` says "no shortcut yet") and
   `python "${CLAUDE_PLUGIN_ROOT}/tools/offers.py" should shortcut` says `offer`, offer one in one plain
   sentence - a shortcut named **Lanes** on the Desktop that opens Claude Code exactly as this terminal looks -
   with AskUserQuestion ("Make the shortcut" / "No thanks"): yes runs `shortcut.py create`, no runs
   `shortcut.py decline` so it is not asked again (0.53.0); either way run `offers.py made shortcut <yes|no>`. If a command fails, show its error in plain words and give them the commands to run
   themselves with `! `. Do not retry in a loop.

5. **"Not now"**:

   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/tools/update-check.py" --dismiss
   ```

   Tell them this version will not be offered again (every offer is made once, 0.75.0); the next version is offered
   when it comes out, and `/lanes:update` installs this one any time they ask.

6. **Hand Freeze, every run** (0.64.0), whichever way steps 2-5 went (an up-to-date plugin does not stop this step):
   `python "${CLAUDE_PLUGIN_ROOT}/tools/hand-freeze.py" status --json`.
   - `installed` false: say nothing (`/lanes:setup` offers it; do not nag).
   - `newer` true: say in one plain line that a newer Hand Freeze is out, and ask (AskUserQuestion: "Update Hand
     Freeze" / "Not now"). Yes runs `hand-freeze.py install`; it refuses while the app is open, so if it says so,
     ask them to close the Hand Freeze window and try once more.
   - Otherwise, or if `error` is set: say nothing.

7. **The OpenXR Simulator, every run** (0.73.0), after step 6:
   `python "${CLAUDE_PLUGIN_ROOT}/tools/openxr-sim.py" status --json`.
   - `installed` false, `declined` false and `offers.py should openxr-sim` says `offer`: offer it in one plain sentence - a pretend headset that shows a VR game's
     two eyes in a window on the desktop, so VR work can be checked with no headset plugged in, by elliotttate - and
     ask with the three choices of `/lanes:setup` §3.6 (0.74.0), plus "No thanks":
     "OpenXR Simulator (webhead2oo9's build) + VR Bench" (Recommended) runs `openxr-sim.py install --fork --bench`;
     "OpenXR Simulator (webhead2oo9's build) only" runs `openxr-sim.py install --fork`;
     "OpenXR Simulator (elliotttate's original)" runs `openxr-sim.py install`;
     "No thanks" runs `openxr-sim.py decline` so it is not offered again. Either way run
     `offers.py made openxr-sim <answer>`. With VR Bench chosen, ask setup's headset
     question once if lanes.conf has no `bench_headset` yet. Say that nothing is switched on by downloading.
   - `newer` true: one plain line that a newer simulator is out, and ask ("Update it" / "Not now"); yes runs
     `openxr-sim.py install` (add `--fork` when `source` is `fork`). It refuses while a game has it loaded.
   - Otherwise, or if `error` is set: say nothing.

8. **VR Bench, every run** (0.74.0), after step 7:
   `python "${CLAUDE_PLUGIN_ROOT}/tools/vrbench/vrbench.py" status --json`.
   - `installed` false: say nothing (step 7 and `/lanes:setup` offer it; do not nag).
   - `newer` true: one plain line that a newer VR Bench is out, and ask ("Update VR Bench" / "Not now"); yes runs
     `vrbench.py install`. It refuses while a run is on; if it says so, leave it for the next update.
   - Otherwise, or if `error` is set: say nothing.

9. **Thanks on GitHub, once** (0.75.0), after step 8, whichever way steps 2-5 went: only if
   `python "${CLAUDE_PLUGIN_ROOT}/tools/offers.py" should thanks` says `offer`. This is the one-time offer for
   everyone who had Lanes before it could do this. Ask it exactly as `/lanes:setup` §0.12 does (one question,
   "Yes" / "No thanks", then `offers.py made thanks <answer>` and `thanks.py on` or `thanks.py off`).

10. **Recording beside BeG0nE, once** (0.76.0), after step 9: as `/lanes:setup` §0.13 says (the same checks, the
    same one question, then `offers.py made begone-record <answer>`).

11. **The superpowers skills, once** (0.77.0), after step 10: as `/lanes:setup` §0.14 says (already installed is
    recorded as `had-it` without a word; otherwise one question, then `offers.py made superpowers <answer>`).

12. **A whole GitHub setup, once** (0.78.0), after step 11: only if `lanes.conf` has no `board =` yet; then as
    `/lanes:setup` §0.6.5 says. With a board already set, record `offers.py made estate had-board` without a word.

13. **Unlock everything before modding, once** (0.81.0), after step 12: as `/lanes:setup` §0.12.5 says (one
    question, then `unlock.py on` or `off` and `offers.py made unlock-all <answer>`).

**Every offer on this page is made once** (0.75.0): an add-on offer is never repeated once `offers.py made` holds
it, and "Not now" to an update quiets that version for good. Updates of things already installed (steps 6-8,
`newer` true) are not offers of something new and are asked when a newer version appears.

Never update without a yes in this session. A yes from an earlier session does not count.
