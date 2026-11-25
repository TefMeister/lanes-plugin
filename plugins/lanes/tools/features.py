#!/usr/bin/env python3
"""features.py - the Lanes extras: each one on or off per PC, chosen at a new install's setup (0.82.0; links, sets
and update safety 0.84.0, 2026-10-23).

Asked for by the maintainer, twice on 2026-10-23: "see if there are any features of Lanes plugin that are not
optional right now, but can be made optional at the first install. no need to make them optional for people updating
the plugin", then "please make this and every future Lanes feature optional, so it is as modular as it can be, but do
suggest some features to be installed together, as they complement each other. also for the description, please add a
clickable link to either our Github or someone elses, should the user wish to read up more about it, before
installing."

    python features.py status [--json]       each extra: on or off, why, and where to read more
    python features.py on <name>|all         switch one on (written to lanes.conf)
    python features.py off <name>|all        switch one off
    python features.py is-on <name>          exit 0 = on, 1 = off (what hooks and commands ask)
    python features.py pending               the extras a new install has not answered yet (exit 1 = none)
    python features.py recommended [--json]  setup's recommended set: every extra but the few marked not recommended
    python features.py ask [--json] [--all]  setup's questions: the unanswered extras grouped in their sets
    python features.py doc [--check]         write docs/EXTRAS.md from this list (--check: exit 1 if it is stale)
    python features.py lint                  every extra has a name, a description, a link and a set (exit 1 if not)

ADDING A FEATURE (every new Lanes feature, from 0.84.0): give it an entry in FEATURES below (label, what, link, set),
gate it with `is-on <name>`, run `doc`, and end its CHANGELOG line with "On or off: `<name>`." release.sh refuses a
CHANGELOG line with no "On or off:" at all; a fix that adds nothing to switch says "On or off: nothing new."

HOW A NEW INSTALL IS TOLD FROM AN UPDATE
  The first time anything asks, this PC is sorted once and for all into features-state.json:
  - "update": lanes.conf, or anything else of Lanes in the state folder, was already there (older than five
    minutes, because the other session-start hooks run at the same moment and may have just made theirs). Every extra
    stays on, as it was; nobody is asked.
  - "new": nothing of Lanes was on this PC. Every extra is off until /lanes:setup asks; the answer is written to
    lanes.conf. Skipping setup leaves them off; `on <name>` switches one on any time.
  An explicit `<name> = on|off` in lanes.conf always wins, on either kind of PC.
  An extra marked "ask_on_update" (one that changes how every session starts, such as remote_control) is off on
  both kinds of PC until asked: setup asks a new install, and /lanes:update asks once on a PC that had Lanes.
Tests set LANES_STATE_DIR and LANES_CONFIG.
"""
import json
import os
import re
import sys
import time

HOME = os.path.expanduser("~")
STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(HOME, ".claude", "lanes")
STATE_FILE = os.path.join(STATE_DIR, "features-state.json")
PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROTOCOL = os.path.join(PLUGIN, "docs", "PROTOCOL.md")
EXTRAS_DOC = os.path.join(PLUGIN, "docs", "EXTRAS.md")
VERSION = "0.84.0"
FRESH_WINDOW_S = 300
MAX_OPTIONS = 4                      # one setup question holds at most four choices
GH = "https://github.com/TefMeister/lanes-plugin/blob/main/plugins/lanes/"
PROTO_LINK = GH + "docs/PROTOCOL.md#"

# The sets: extras that belong together. "together" = suggested as a pair (each makes the other more useful).
SETS = {
    "everyday": {"title": "Everyday helpers", "together": False,
                 "note": "Small things for every session. Each one works on its own."},
    "tools": {"title": "Keeping your tools up to date", "together": True,
              "note": "The reminder brings the weekly tool check round, and the test builds make sure "
                      "an update it installs does not break what you build."},
    "checkup": {"title": "The weekly check-up", "together": True,
                "note": "Every game run's logs are kept on shelves, and the weekly check-up reads them together "
                        "with the research, tool and tidiness checks."},
    "vr": {"title": "For VR mods", "together": True,
           "note": "One keeps the headset picture down to the gameplay, the other reports when that "
                   "picture or the hands are not smooth, so its reports are about the mod and not about blur."},
    "recording": {"title": "Filming the VR tests", "together": True,
                  "note": "One films the game during every VR test so each fault can be seen picture by "
                          "picture, the other takes those videos off the PC again once nothing needs them."},
    "ours": {"title": "Our own apps and libraries", "together": False,
             "note": "The other things we built for flat-to-VR work, each from its page on TefMeister's GitHub. "
                     "Each one is useful on its own."},
    "outside": {"title": "Other people's tools", "together": False,
                "note": "Downloads from other makers that help flat-to-VR work, each from its maker's GitHub. "
                        "Each one is useful on its own."},
}

# The extras. `link` is where to read more before switching it on: our GitHub, or the maker's.
FEATURES = {
    "theme": {"label": "The green look", "set": "everyday",
              "what": "gives this terminal window the plugin's old green-monitor look; it can be taken off again any "
                      "time",
              "link": GH + "commands/theme.md"},
    "version_line": {"label": "Lanes version first", "set": "everyday",
                     "what": "every session opens with one line naming the Lanes version it runs, so an old copy is "
                             "seen at a glance",
                     "link": GH + "hooks/version-line"},
    "talk_rule": {"label": "Check before agreeing", "set": "everyday",
                  "what": "Claude never says \"you are right\" before checking what you said",
                  "link": GH + "hooks/talk-rule"},
    "straight_talk": {"label": "Straight talk", "set": "everyday", "recommended": False,
                      "what": "Claude talks like a friend: warm but honest and direct, and when you miss something "
                              "obvious it says so with a light ribbing instead of \"easy to miss\"",
                      "link": GH + "hooks/straight-talk"},
    "reply_check": {"label": "Reply check", "set": "everyday",
                    "what": "when Claude forgets one of the lines it promised to put in a reply (for example the "
                            "green tick that says you may close the game), it is made to add it straight away",
                    "link": GH + "hooks/reply-check.py"},
    "git_queue": {"label": "Saving in turn", "set": "everyday",
                  "what": "when several Claude windows work at once, they save to GitHub one after another, so one "
                          "never saves into another's half-done work",
                  "link": GH + "hooks/git-queue.py"},
    "project_guard": {"label": "One window per game", "set": "everyday",
                      "what": "only one Claude window at a time changes a game's files; a second one is stopped with "
                              "one line until the first is done, and saying \"take over <game>\" hands it over",
                      "link": GH + "hooks/project-guard.py"},
    "rest_reminder": {"label": "Rest reminder", "set": "everyday", "recommended": False,
                      "what": "once a session, past the rest time you set (midnight unless you change it), Claude "
                              "says so in one line at the top of its reply",
                      "link": GH + "hooks/rest-reminder.py"},
    "tools_rule": {"label": "Use the tools, grow the tools", "set": "everyday",
                   "what": "Claude uses the helper programs this PC has (menu routes, the pretend headset, the VR "
                           "fault reports, the live game connectors) before doing a job by hand, writes down what it "
                           "learns, and turns a job done by hand twice into a small tool",
                   "link": PROTO_LINK + "33-use-every-tool-you-have-record-what-helps-grow-the-toolset-0850-2026-10-24"},
    "privacy_guard": {"label": "Privacy guard", "set": "everyday",
                      "what": "nothing you save to GitHub can carry your Windows login name, your home folder's "
                              "location or your e-mail address; anything that would is stopped before it leaves "
                              "the PC",
                      "link": PROTO_LINK + "34-the-privacy-guard-no-login-no-home-paths-no-e-mail-on-github-0860-2026-10-25"},
    "games_check": {"label": "Games check at session start", "set": "everyday",
                    "what": "each session starts by checking your project games: one a store has updated (a mod may "
                            "need a fix), one removed or moved, a new project with no game found yet",
                    "link": GH + "tools/games.py"},
    "remote_control": {"label": "Remote Control in every session", "set": "everyday", "ask_on_update": True,
                       "recommended": False,
                       "what": "every Claude session on this PC can be watched and typed into from the Claude phone "
                               "app or claude.ai, or from a session on your other PC; it needs a claude.ai account",
                       "one_pc": "every Claude session on this PC can be watched and typed into from the Claude "
                                 "phone app or claude.ai; it needs a claude.ai account",
                       "link": PROTO_LINK + "35-remote-control-in-every-session-0870-2026-10-26"},
    "taskbar_flash": {"label": "Blink when Claude is done", "set": "everyday",
                      "what": "the terminal's button on the taskbar blinks when Claude finishes or waits for an "
                              "answer, so a window hidden behind a game is not missed",
                      "link": GH + "tools/taskbar_flash.py"},
    "keep_transcripts": {"label": "Keep full conversation logs", "set": "everyday", "recommended": False,
                         "what": "keeps a copy of every conversation on this PC after Claude Code's own 30-day "
                                 "clean-up (about 1 GB a month of disk)",
                         "link": PROTO_LINK + "21-keep-conversations-short-an-earlier-summary-that-loses-nothing-0630-2026-10-13"},
    "gu_nudge": {"label": "Weekly tool reminder", "set": "tools",
                 "what": "one line at the start of a session when the weekly check for newer versions of your tools "
                         "is due",
                 "link": PROTO_LINK + "23-the-weekly-tool-check-lanesgu-0670-2026-10-14"},
    "auto_update": {"label": "Lanes updates itself", "set": "tools", "ask_on_update": True,
                    "what": "a new Lanes version installs by itself in the background, never while a game or a test "
                            "is running, and the next session says what it added; a failed update leaves the old "
                            "version working",
                    "link": GH + "tools/auto_update.py"},
    "fresh_nudge": {"label": "Fresh-session nudge", "set": "tools", "ask_on_update": True,
                    "what": "when a job is finished and saved and the conversation has grown long, one line suggests "
                            "starting a fresh one, because every step of a long one costs more; never in the middle "
                            "of a job",
                    "link": GH + "tools/handon.py"},
    "hand_on": {"label": "Session hand-on", "set": "tools", "ask_on_update": True, "recommended": False,
                "what": "on your yes to a next job, Claude writes the job down for a new window, opens it, and closes "
                        "the old window once everything is saved",
                "link": GH + "commands/next.md"},
    "update_hold": {"label": "Hold Lanes updates during a test", "set": "tools",
                    "what": "while you test something, Lanes can be told not to update itself until the test is over "
                            "(or 12 hours pass), so nothing changes under the test",
                    "link": PROTO_LINK + "43-hold-lanes-updates-while-a-test-runs-lanes-next-2026-11-01"},
    "update_safety": {"label": "Test builds before updates", "set": "tools",
                      "what": "an update that could break what you build (a compiler, Visual Studio, Python, "
                              "Blender) is tried on a test build first and undone if your work stops building",
                      "link": PROTO_LINK + "31-test-build-before-keeping-an-update-0830-2026-10-23"},
    "gold_digger": {"label": "Keep every run's logs", "set": "checkup",
                    "what": "after every game run its logs and fault reports are kept on labelled shelves (camera, "
                            "guns, jitter, menus and so on) in your transfer folder, never deleted, and read once a "
                            "week for anything new",
                    "one_pc": "after every game run its logs and fault reports are kept on labelled shelves (camera, "
                              "guns, jitter, menus and so on) in a folder on this PC, never deleted, and read once a "
                              "week for anything new",
                    "link": GH + "commands/gd.md"},
    "fullscan": {"label": "Weekly check-up reminder", "set": "checkup",
                 "what": "one line at the start of a session when the weekly check-up (the logs, research, tool "
                         "versions, tidiness, then save) is due",
                 "link": GH + "commands/fullscan.md"},
    # lanes-next 2026-11-05: the clash guard took over "fullscan_guard" (the full scan's lock was its first piece).
    "clash_guard": {"label": "No clashes", "set": "everyday",
                    "what": "things that must not run at the same time (two weekly check-ups, two Lanes installs, two "
                            "recordings, a second game beside a running one) are kept apart on both your PCs: the "
                            "second is stopped with one line saying what is running where",
                    "one_pc": "things that must not run at the same time (two weekly check-ups, two Lanes installs, "
                              "two recordings, a second game beside a running one) are kept apart: the second is "
                              "stopped with one line saying what is running",
                    "link": GH + "docs/CLASHES.md"},
    "keep_level": {"label": "Copies kept level with GitHub", "set": "everyday", "ask_on_update": True,
                   "what": "after each session, every copy on this PC that is only behind GitHub is brought up to "
                           "date, and a project your other PC started is copied here; a copy with unsaved work is "
                           "never touched",
                   "one_pc": "after each session, every copy on this PC that is only behind GitHub is brought up to "
                             "date, so no window works from old notes; a copy with unsaved work is never touched",
                   "link": GH + "docs/TWO-PCS.md"},
    "keeper": {"label": "Saving to GitHub in the background", "set": "everyday", "ask_on_update": True,
               "what": "the windows that build never upload: they save their work and hand it over, and a keeper "
                       "on your second PC uploads it and keeps your GitHub pages up to date",
               "one_pc": "the windows that build never upload: they save their work and hand it over, and it is "
                         "uploaded in the background, with your GitHub pages kept up to date",
               "link": GH + "docs/ONE-PC.md"},
    # 2026-11-25 (Tefa: "you really need to learn how to work on the background so i can use the pc at the same time"):
    "backstage": {"label": "Games run behind your windows", "set": "everyday", "ask_on_update": True,
                  "what": "when Claude starts or drives a game, its window is kept behind yours (or off the "
                          "screen, if you prefer: backstage_place = off_screen) and your typing stays in your own "
                          "window, so you can use the PC at the same time; Claude presses a "
                          "pretend game pad instead of your keyboard and mouse, and a short log says if a window "
                          "still showed for a moment",
                  "link": PROTO_LINK + "51-backstage-games-run-off-the-screen-01250-2026-11-25"},
    "shutdown_guard": {"label": "Switch off only when everything is saved", "set": "everyday",
                       "what": "when you ask Claude to switch the PC off after its work, it waits until no game runs, "
                               "no other window is busy and everything is on GitHub, then switches off by itself; it "
                               "never forces",
                       "link": GH + "tools/switch_off.py"},
    "scan_priority": {"label": "The weekly check-up goes first", "set": "checkup",
                      "what": "while the weekly check-up runs, the other Claude windows on this PC finish their step, "
                              "save and wait, and carry on when it is done",
                      "link": PROTO_LINK + "48-the-full-scan-goes-first-01100-2026-11-11"},
    "netcheck": {"label": "Network safety check", "set": "checkup",
                 "what": "once a week, without changing anything, checks this PC's firewall, antivirus, remote "
                         "logins and Windows updates, and says what changed since last week",
                 "link": GH + "tools/netcheck.py"},
    "spacecheck": {"label": "Forgotten space finder", "set": "checkup",
                   "what": "once a week, lists what takes space on your drives in three groups (safe to clear, "
                           "probably safe, yours to decide); it never deletes anything",
                   "link": GH + "tools/spacecheck.py"},
    "quiet_installs": {"label": "Installs with no Yes click", "set": "tools", "ask_on_update": True,
                       "what": "one Windows Yes click, once, lets Lanes install and update programs from Windows' own "
                               "catalogue without asking again, so nothing ever sits waiting for a click while you "
                               "are away; it can do nothing else",
                       "link": PROTO_LINK + "49-installs-with-no-yes-click-01100-2026-11-11"},
    "collector": {"label": "Every game run noted", "set": "checkup",
                  "what": "every time one of your project games runs, its load, temperature, hangs, logs and crashes "
                          "are noted quietly and kept with the other run logs",
                  "link": PROTO_LINK + "44-the-always-on-collector-lanes-next-2026-11-04"},
    "code_health": {"label": "Code health", "set": "checkup",
                    "what": "once a week, your own helper programs are read through again and tidied only where it "
                            "cannot change how they work, after a working copy is saved",
                    "link": GH + "commands/ch.md"},
    "out_of_date": {"label": "Out of Date", "set": "checkup",
                    "what": "once a week, checks that everything you published on GitHub is as new as the work "
                            "behind it, and brings it level",
                    "link": GH + "commands/od.md"},
    "begone_ride": {"label": "VR fault reports", "set": "vr",
                    "what": "a quiet helper turns each headset test of a mod into a short report on stepped "
                            "movement and hands that do not follow the controllers",
                    "link": "https://github.com/TefMeister/BeG0nE"},
    # 0.101.0 (2026-11-05): the rider only ever FILED reports; a session had to save them, and a session that ended
    # first left them on the PC only (eight Village reports on 2026-11-05). Pushes to GitHub, so asked once.
    "begone_autosave": {"label": "VR fault reports save themselves", "set": "vr", "ask_on_update": True,
                        "what": "each VR fault report is saved to GitHub by itself, so one is never left only on "
                                "this PC",
                        "link": "https://github.com/TefMeister/BeG0nE"},
    "vr_effects_off": {"label": "Gameplay only in VR", "set": "vr",
                       "what": "sessions switch off every blur and screen effect a game paints over the picture, such "
                               "as motion blur, blood on the screen and the low-health tint",
                       "link": PROTO_LINK + "19-gameplay-only-every-blur-and-screen-effect-off-in-vr-0600-2026-10-12"},
    # Both off until asked: one films, the other deletes (0.90.0; begone_record was a setup-only offer since 0.80.0)
    "begone_record": {"label": "Film every VR test", "set": "recording", "ask_on_update": True,
                      "what": "OBS films the game's own window (never the whole screen) during every VR test, so each "
                              "fault in the report can be looked at picture by picture",
                      "link": PROTO_LINK + "26-the-recording-and-the-jitter-log-side-by-side-0760-2026-10-17"},
    "begone_video_tidy": {"label": "Test videos clean up after themselves", "set": "recording",
                          "ask_on_update": True,
                          "what": "the videos of VR tests are taken off the PC once nothing needs them (the game was "
                                  "tested again on a later day, or two weeks passed); the cut pictures and the "
                                  "reports stay",
                          "link": PROTO_LINK + "38-beg0ne-videos-clean-up-after-themselves-0900-2026-10-27"},
}
# Other people's tools (0.92.0): one extra each, described and linked from tools/outside.py's own list, so the two
# never disagree. Off until asked on every PC: each one downloads something.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import outside  # noqa: E402
import ours  # noqa: E402
# Our own apps and libraries (0.93.0), the same way: described and linked from tools/ours.py's list.
for _name, _t in ours.TOOLS.items():
    FEATURES[ours.feature_name(_name)] = {"label": _t["label"], "set": "ours", "ask_on_update": True,
                                          "what": _t["what"], "link": ours.GH + _t["repo"]}
for _name, _t in outside.TOOLS.items():
    FEATURES[outside.feature_name(_name)] = {"label": f"{_t['label']} (by {_t['maker']})", "set": "outside",
                                             "ask_on_update": True, "what": _t["what"], "link": outside.GH + _t["repo"]}
ON_WORDS, OFF_WORDS = ("on", "yes", "true", "1"), ("off", "no", "false", "0")
# Extras that setup used to offer a second time as their own one-time offer (offers.py): answering the extra counts as
# that offer made, so it is never asked twice (Workshop PC 2026-11-21: the 22 own and outside tools, and the BeG0nE
# recording, were asked in the extras and again in setup's later steps).
OFFER_OF_SET = {"ours": "our-tools", "outside": "outside-tools"}
OFFER_OF_FEATURE = {"begone_record": "begone-record", "begone_video_tidy": "video-tidy",
                    "remote_control": "remote-control"}


def note_offers(changed, value):
    """Record, in offers.py's list, the offers these extras stand for, unless they were made already."""
    import offers
    from datetime import datetime
    d = offers.load()
    new = False
    for n in changed:
        o = OFFER_OF_FEATURE.get(n) or OFFER_OF_SET.get(FEATURES[n]["set"])
        if o and o not in d:
            d[o] = {"answer": f"answered with the extras ({n} {value})",
                    "at": datetime.now().isoformat(timespec="seconds")}
            new = True
    if new:
        offers.save(d)


def pairs(name):
    """The other extras of its set, when that set is one to take together."""
    s = FEATURES[name]["set"]
    return [n for n in FEATURES if n != name and FEATURES[n]["set"] == s] if SETS[s]["together"] else []


def one_pc():
    return conf_value("pcs") == "1"


def what_of(name):
    """The description for this PC: the one-PC wording when lanes.conf says pcs = 1 and the extra has one."""
    f = FEATURES[name]
    return f["one_pc"] if one_pc() and f.get("one_pc") else f["what"]


def recommended_names():
    """setup's recommended set (0.121.0): every extra, except those marked "recommended": False (a personal choice,
    something that needs an account, or one that uses a lot of disk); Tefa, 2026-11-21: "keep the list"."""
    return [n for n, f in FEATURES.items() if f.get("recommended", True)]


# Words a newcomer cannot know, kept out of what setup shows for the built-in extras (0.121.0; the Workshop PC's
# newcomer met /lanes:gu, pd_parallel, hold.py, BeG0nE, claim and fast-forward in them). `lint` refuses them.
JARGON = ("/lanes:", "pd_parallel", "hold.py", "BeG0nE", "claim", "fast-forward", ".py", "lanes.conf", "/pd",
          "/lm", "Gold Digger", "Inspector", "rider", "MCP")


def describe(name):
    what = what_of(name)
    text = what[0].upper() + what[1:] + "."
    p = pairs(name)
    if p:
        text += " Goes well with: " + ", ".join(FEATURES[n]["label"] for n in p) + "."
    return text + " Read more: " + FEATURES[name]["link"]


def conf_file():
    if os.environ.get("LANES_CONFIG"):
        return os.environ["LANES_CONFIG"]
    for c in (os.path.join(HOME, ".claude", "lanes.conf"), os.path.join(HOME, ".config", "lanes", "lanes.conf")):
        if os.path.exists(c):
            return c
    return os.path.join(HOME, ".claude", "lanes.conf")


def conf_value(key):
    try:
        for line in open(conf_file(), encoding="utf-8"):
            k, _, v = line.partition("=")
            if k.strip() == key:
                return v.split("#")[0].strip().strip('"').lower()
    except OSError:
        pass
    return None


def set_conf(key, value, note):
    p = conf_file()
    try:
        lines = open(p, encoding="utf-8").read().splitlines()
    except OSError:
        lines = []
    out, done = [], False
    for line in lines:
        if line.partition("=")[0].strip() == key:
            if not done:                 # a second line for the same key (an older setup wrote one by hand) is dropped
                out.append(f"{key} = {value}")
            done = True
        else:
            out.append(line)
    if not done:
        out.append(f"{key} = {value}   # {note} (features.py)")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")


def kind():
    """'new' or 'update', decided the first time and kept."""
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)["kind"]
    except (OSError, ValueError, KeyError):
        pass
    # Session-start hooks run side by side, so another hook may have written its first file a moment ago: only
    # files older than that count as Lanes having been here before.
    cutoff = time.time() - FRESH_WINDOW_S
    old = [conf_file()] + ([os.path.join(STATE_DIR, n) for n in os.listdir(STATE_DIR)
                            if n != os.path.basename(STATE_FILE)] if os.path.isdir(STATE_DIR) else [])
    had_lanes = any(os.path.exists(p) and os.path.getmtime(p) < cutoff for p in old)
    k = "update" if had_lanes else "new"
    # 0.120.0: just uninstalled (the settings put aside, none in their place): the window that ran the uninstall still
    # has Lanes loaded until restart, and must not write Lanes' state folder back (the Workshop PC's test found it did)
    cf = conf_file()
    folder = os.path.dirname(cf) or "."
    if not os.path.exists(cf) and os.path.isdir(folder) and any(
            n.startswith(os.path.basename(cf) + ".uninstalled-") for n in os.listdir(folder)):
        return k
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"kind": k, "since": VERSION}, f)
    return k


RENAMED = {"clash_guard": "fullscan_guard"}   # a PC that switched the old name off keeps it off


def why(name):
    v = conf_value(name)
    if v is None and name in RENAMED:
        v = conf_value(RENAMED[name])
    if v in ON_WORDS:
        return True, "switched on"
    if v in OFF_WORDS:
        return False, "switched off"
    if FEATURES[name].get("ask_on_update"):
        return False, "not chosen yet (asked once)"
    if kind() == "update":
        return True, "on, as before"
    return False, "not chosen yet (setup asks)"


def is_on(name):
    return why(name)[0]


def pending():
    if kind() != "new":
        return []
    return [n for n in FEATURES if conf_value(n) not in ON_WORDS + OFF_WORDS]


def questions(only=None):
    """Setup's questions: one per set (split at four choices), in the order of SETS."""
    want = pending() if only is None else only
    out = []
    for key, s in SETS.items():
        members = [n for n in FEATURES if FEATURES[n]["set"] == key and n in want]
        for i in range(0, len(members), MAX_OPTIONS):
            chunk = members[i:i + MAX_OPTIONS]
            out.append({"set": key, "title": s["title"], "together": s["together"], "note": s["note"],
                        "options": [{"name": n, "label": FEATURES[n]["label"], "description": describe(n),
                                     "recommended": FEATURES[n].get("recommended", True),
                                     "link": FEATURES[n]["link"], "goes_well_with": pairs(n)} for n in chunk]})
    return out


def github_slug(heading):
    """The anchor GitHub gives a Markdown heading."""
    s = heading.strip().lstrip("#").strip().lower()
    s = re.sub(r"[^\w\- ]", "", s)
    return s.replace(" ", "-")


def doc_text():
    lines = ["# Lanes extras", "",
             "Every extra below is optional: each PC switches it on or off (`features.py on|off <name>`). A new",
             "install chooses at `/lanes:setup`; a PC that had Lanes before keeps what it had. Sets marked **best",
             "together** are suggested as a pair. Written by `tools/features.py doc`; edit the list there, not here.", ""]
    for key, s in SETS.items():
        lines += [f"## {s['title']}" + (" (best together)" if s["together"] else ""), "", s["note"], ""]
        for n, f in FEATURES.items():
            if f["set"] != key:
                continue
            p = pairs(n)
            lines.append(f"- **{f['label']}** (`{n}`): {f['what']}. [Read more]({f['link']})"
                         + (f". Goes well with: {', '.join(FEATURES[x]['label'] for x in p)}." if p else ""))
        lines.append("")
    return "\n".join(lines)


def lint():
    problems = []
    anchors = set()
    try:
        anchors = {github_slug(l) for l in open(PROTOCOL, encoding="utf-8") if l.startswith("## ")}
    except OSError:
        problems.append("docs/PROTOCOL.md not found")
    for n, f in FEATURES.items():
        for field in ("label", "what", "link", "set"):
            if not f.get(field):
                problems.append(f"{n}: no {field}")
        if f.get("set") not in SETS:
            problems.append(f"{n}: unknown set '{f.get('set')}'")
        if f.get("set") not in ("ours", "outside"):     # those two carry their makers' own product names
            shown = " ".join([f.get("label", ""), f.get("what", ""), f.get("one_pc", "")])
            problems += [f"{n}: the words shown at setup use \"{w}\", which a newcomer cannot know"
                         for w in JARGON if w in shown]
    for key, s in SETS.items():
        problems += [f"set '{key}': its words use \"{w}\", which a newcomer cannot know"
                     for w in JARGON if w in s["title"] + " " + s["note"]]
    # 2026-11-25: these link checks sat inside the loop over the SETS, so only the last extra's link was ever checked
    for n, f in FEATURES.items():
        link = str(f.get("link", ""))
        if not link.startswith("https://"):
            problems.append(f"{n}: the link is not a web address")
        if link.startswith(PROTO_LINK) and link[len(PROTO_LINK):] not in anchors:
            problems.append(f"{n}: PROTOCOL.md has no heading for #{link[len(PROTO_LINK):]}")
        elif link.startswith(GH) and "#" not in link and not os.path.exists(os.path.join(PLUGIN, link[len(GH):])):
            problems.append(f"{n}: the linked file {link[len(GH):]} is not in the plugin")
    for s in SETS:
        if not any(f["set"] == s for f in FEATURES.values()):
            problems.append(f"set '{s}' has no extras")
    # every extra says whether it clashes with anything (tools/clash.py, lanes-next 2026-11-05)
    try:
        import clash
        problems += [f"{n}: no row in tools/clash.py (say which job it is, or why it needs none)"
                     for n in FEATURES if clash.row_of("feature:" + n) is None]
    except Exception as e:
        problems.append(f"tools/clash.py would not load: {e}")
    return problems


def names(arg):
    if arg == "all":
        return list(FEATURES)
    if arg in FEATURES:
        return [arg]
    raise SystemExit(f"Unknown extra '{arg}'. Known: {', '.join(FEATURES)}")


def main(argv):
    a = argv[1:]
    cmd = a[0] if a else "status"
    if cmd == "status":
        rows = {n: dict(zip(("on", "why"), why(n)), label=FEATURES[n]["label"], what=what_of(n),
                        link=FEATURES[n]["link"], goes_well_with=pairs(n)) for n in FEATURES}
        if "--json" in a:
            print(json.dumps({"kind": kind(), "features": rows}, indent=1))
        else:
            for n, r in rows.items():
                print(f"{n:17} {'ON ' if r['on'] else 'off'}  {r['label']}  ({r['why']})  {r['link']}")
        return 0
    if cmd in ("on", "off") and len(a) > 1:
        changed = names(a[1])
        for n in changed:
            set_conf(n, cmd, FEATURES[n]["label"])
        note_offers(changed, cmd)
        print(f"{a[1]}: {cmd} (in {conf_file()})")
        return 0
    if cmd == "is-on" and len(a) > 1:
        return 0 if is_on(names(a[1])[0]) else 1
    if cmd == "recommended":
        r = recommended_names()
        print(json.dumps(r) if "--json" in a else "\n".join(r))
        return 0
    if cmd == "pending":
        p = pending()
        print("\n".join(p) if p else "none")
        return 0 if p else 1
    if cmd == "ask":
        q = questions(list(FEATURES) if "--all" in a else None)
        if "--json" in a:
            print(json.dumps(q, indent=1))
        else:
            for g in q:
                print(f"{g['title']}{' (best together)' if g['together'] else ''}: {g['note']}")
                for o in g["options"]:
                    print(f"  - {o['label']} ({o['name']}): {o['description']}")
        return 0 if q else 1
    if cmd == "doc":
        text = doc_text()
        try:
            same = open(EXTRAS_DOC, encoding="utf-8").read() == text
        except OSError:
            same = False
        if "--check" in a:
            print("docs/EXTRAS.md is up to date" if same else "docs/EXTRAS.md is stale: run features.py doc")
            return 0 if same else 1
        with open(EXTRAS_DOC, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print("wrote docs/EXTRAS.md")
        return 0
    if cmd == "lint":
        p = lint()
        print("\n".join(p) if p else f"all {len(FEATURES)} extras have a name, a description, a link and a set")
        return 1 if p else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):   # a character the console cannot show prints as ? (0.94.2)
        try:
            _stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv))
