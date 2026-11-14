# What must not run at the same time

The clash guard (`tools/clash.py`, extra `clash_guard`) keeps these apart. "On the same PC" is checked with a
small file on this PC; "on either PC" is also held on GitHub, so the other PC sees it. A lock left by a run that
was cut off runs out after 12 hours. Written by `tools/clash.py doc`; edit the table there, not here.

- **the full scan** (`fullscan`): never two at once on either PC; not beside Gold Digger, game research (/gr), the cross-project research sweep (/sr), Out of Date (/od), the weekly tool check (/gu), code health (/ch), the GitHub sweep (/gs) on either PC; its own parts may run inside it. Why: two would double the research, rewrite the same notes and pages against each other, dig the same shelves twice and could publish one download twice.
- **Gold Digger** (`gd`): never two at once on either PC; not beside the full scan on either PC. Why: two would read the same shelves and hand the same facts to the notes twice.
- **game research (/gr)** (`gr`): never two at once on either PC (on one project); not beside the full scan on either PC. Why: two on one project would rewrite the same research notes against each other.
- **the cross-project research sweep (/sr)** (`sr`): never two at once on either PC; not beside the full scan on either PC. Why: both would rewrite the one shared library.
- **Out of Date (/od)** (`od`): never two at once on either PC; not beside the full scan, the weekly tool check (/gu), a Lanes release on either PC. Why: it rewrites front pages and descriptions and publishes downloads; two at once could publish twice.
- **the weekly tool check (/gu)** (`gu`): never two at once on either PC; not beside the full scan, Out of Date (/od), code health (/ch) on either PC; not beside a Lanes update, Lanes setup on the same PC. Why: it puts tool copies back in step and installs updates; beside another it could undo the other's work.
- **code health (/ch)** (`ch`): never two at once on either PC; not beside the full scan, the weekly tool check (/gu), a Lanes release on either PC. Why: it tidies our tools' code; a release or a second tidy at the same time would ship or tidy half of it.
- **the GitHub sweep (/gs)** (`gs`): never two at once on either PC; not beside the full scan on either PC. Why: two would file the same notes into the inboxes twice.
- **filing ideas** (`ideas`): never two at once on either PC. Why: two would file the same ideas twice and clear the phone page under each other.
- **a save (/sp)** (`save`): never two at once on the same PC. Why: two saves at once in one clone root sweep each other's unsaved files into their commits.
- **a Lanes release** (`release`): never two at once on either PC; not beside Out of Date (/od), code health (/ch) on either PC. Why: two releases at once would number and publish over each other.
- **a Lanes update** (`update`): never two at once on the same PC; not beside the weekly tool check (/gu), Lanes setup, taking Lanes off on the same PC. Why: two installs of the plugin on one PC at once leave it half one version, half the other.
- **Lanes setup** (`setup`): never two at once on the same PC; not beside the weekly tool check (/gu), a Lanes update, taking Lanes off on the same PC. Why: it writes this PC's settings and installs programs; two at once write over each other.
- **taking Lanes off** (`uninstall`): never two at once on the same PC; not beside a Lanes update, Lanes setup, the terminal look on the same PC. Why: it removes what the others are writing.
- **the terminal look** (`theme`): never two at once on the same PC; not beside taking Lanes off on the same PC. Why: both write the terminal's one settings file.
- **Menu-o-matiC / Move-o-matiC** (`menu`): never two at once on the same PC; not beside VR Bench, a game session (/lm, /ms, VR Bench's start, or a project's launcher) on the same PC. Why: it presses keys into the window in front; beside VR Bench or another session's game it presses into that game.
- **VR Bench** (`bench`): never two at once on the same PC; not beside Menu-o-matiC / Move-o-matiC, a game session (/lm, /ms, VR Bench's start, or a project's launcher) on the same PC. Why: there is one pretend headset and one set of pretend hands on a PC, and it presses keys into the window in front; beside another session's game it would press into that game.
- **a recording asked for by hand** (`obs_clip`): never two at once on the same PC; not beside the automatic BeG0nE recording on the same PC. Why: OBS records one thing at a time; a second start would take over the first one's recording. Guarded by: obs-rec.py start refuses while OBS is already recording.
- **the automatic BeG0nE recording** (`begone_record`): never two at once on the same PC; not beside a recording asked for by hand on the same PC. Why: OBS records one thing at a time. Guarded by: the BeG0nE helper never starts one while OBS is recording.
- **the BeG0nE helper (and the collector in it)** (`rider`): never two at once on the same PC. Why: two would file every report and every game run twice. Guarded by: rider.py start: one helper per PC (a running one is kept, or restarted when its code is older).
- **a game session (/lm, /ms, VR Bench's start, or a project's launcher)** (`live`): never two at once on the same PC; not beside Menu-o-matiC / Move-o-matiC, VR Bench on the same PC. Why: a PC runs one game at a time: two game sessions would fight over the screen, the keys, the headset and the frame-time numbers (Tefa, 2026-11-06: several /pd at once, only one live game).
- **/pd, /lm or /ms on one project** (`lane`): never two at once on either PC (on one project). Why: two sessions changing one game's mod at once undo each other's work. Guarded by: the live claim on the board (lane-claim.sh, the /pd lock and their hooks).

Every other command, hook, tool and extra of the plugin (112 of them) has a row saying why it needs no guard;
`clash.py audit` refuses a new one without a row.
