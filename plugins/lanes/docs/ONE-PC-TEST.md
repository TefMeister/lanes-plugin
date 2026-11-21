# The one-PC test (0.120.0)

Run once after setting up one PC (`ONE-PC.md`), and after a Lanes update that touches the Keeper, the claims or the
clash guard. Each step says what proves it. A step that fails goes on the fault list with what was seen.

Before: `keeper = on`, `keeper_mode = this_pc` in `lanes.conf`; a small test project of your own on GitHub.

| # | Step | Passes when |
| --- | --- | --- |
| O1 | In a `/pd` window: commit a one-line change in the test project, then `python tools/parcel.py send <project> --note "one-PC test"` | The command returns at once; within two minutes `parcel.py light` says everything is on GitHub, and GitHub shows the commit |
| O2 | The same window: `git push` was never typed | `parcel.py status` shows a receipt for that hand-over, made on this PC |
| O3 | The hand-over with a note | A Keeper window opens by itself, starts its round, writes the front-page line, and closes when nothing waits |
| O4 | `python tools/keeper.py ask "one-PC test job"` | A Keeper window opens (or the open one gets the job); the job is listed in its round; `keeper.py close` closes it politely |
| O5 | A weekly job due (or `keeper.py due` showing one) | Every new window prints it at the top with the exact thing to type, until `keeper.py done <job>` |
| O6 | A `/pd` window claims a game, then a `/lm` window is started on the same game | The `/lm` window is refused by the claim, and says who holds it |
| O7 | Two windows try a clashing job at once (two `/gu`, or a `/gu` while `/fullscan` runs) | The second waits or is refused by the clash guard; nothing is done twice |
| O8 | The first reply of a `/pd`, a `/lm` and a `/lanes:keeper` window | Each says its role in one line (`🧰 Developer`, `🧰 Tester`, `🧰 Keeper`) |
| O9 | A session start | No line about another PC (no "Keeper PC off", no "the other PC is behind", no other PC's save state) |
| O10 | `python tools/machine-name.py retire <a PC that left>` (when there was one) | Its files are under `retired/`, its name is gone from `machines.txt`, and the next session start prints nothing about it |
