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
    "vr": {"title": "For VR mods", "together": True,
           "note": "One keeps the headset picture down to the gameplay, the other reports when that "
                   "picture or the hands are not smooth, so its reports are about the mod and not about blur."},
}

# The extras. `link` is where to read more before switching it on: our GitHub, or the maker's.
FEATURES = {
    "theme": {"label": "The green look", "set": "everyday",
              "what": "puts the plugin's old-green-monitor look on this terminal; /lanes:theme restore undoes it",
              "link": GH + "commands/theme.md"},
    "talk_rule": {"label": "Check before agreeing", "set": "everyday",
                  "what": "Claude never says \"you are right\" before checking what you said",
                  "link": GH + "hooks/talk-rule"},
    "tools_rule": {"label": "Use the tools, grow the tools", "set": "everyday",
                   "what": "Claude drives menus and tests with the tools this PC has (routes, VR Bench, BeG0nE, the "
                           "live-game connectors) before doing it by hand, records what it learns, and adds a small "
                           "tool or improvement whenever it does the same thing by hand twice",
                   "link": PROTO_LINK + "33-use-every-tool-you-have-record-what-helps-grow-the-toolset-0850-2026-10-24"},
    "privacy_guard": {"label": "Privacy guard", "set": "everyday",
                      "what": "a git hook on this PC refuses any commit (and any gh issue, release or description) "
                              "that carries the login name, a home-folder path or the e-mail address; public repos "
                              "also never get machine names",
                      "link": PROTO_LINK + "34-the-privacy-guard-no-login-no-home-paths-no-e-mail-on-github-0860-2026-10-25"},
    "remote_control": {"label": "Remote Control in every session", "set": "everyday", "ask_on_update": True,
                       "what": "every Claude Code session on this PC starts with Remote Control on, so it can be "
                               "watched and typed into from the Claude phone app, claude.ai/code or a session on your "
                               "other PC; without it, /remote-control (or /rc) turns it on in one session",
                       "link": PROTO_LINK + "35-remote-control-in-every-session-0870-2026-10-26"},
    "keep_transcripts": {"label": "Keep full conversation logs", "set": "everyday",
                         "what": "copies each conversation out of Claude Code's 30-day clean-up, kept on this PC only",
                         "link": PROTO_LINK + "21-keep-conversations-short-an-earlier-summary-that-loses-nothing-0630-2026-10-13"},
    "gu_nudge": {"label": "Weekly tool reminder", "set": "tools",
                 "what": "one line at session start when the weekly tool check (/lanes:gu) is a week old",
                 "link": PROTO_LINK + "23-the-weekly-tool-check-lanesgu-0670-2026-10-14"},
    "update_safety": {"label": "Test builds before updates", "set": "tools",
                      "what": "in the weekly tool check, an update that could break what you build (a compiler, "
                              "Visual Studio, Python, Blender) is test-built first and put back if your work stops "
                              "building",
                      "link": PROTO_LINK + "31-test-build-before-keeping-an-update-0830-2026-10-23"},
    "begone_ride": {"label": "BeG0nE recorders", "set": "vr",
                    "what": "a quiet helper that starts with every session and turns each headset test of a mod wired "
                            "to it into a short report on jitter and hand faults",
                    "link": "https://github.com/TefMeister/BeG0nE"},
    "vr_effects_off": {"label": "Gameplay only in VR", "set": "vr",
                       "what": "sessions switch off every blur and screen effect a game paints over the picture, such "
                               "as motion blur, blood on the screen and the low-health tint",
                       "link": PROTO_LINK + "19-gameplay-only-every-blur-and-screen-effect-off-in-vr-0600-2026-10-12"},
}
ON_WORDS, OFF_WORDS = ("on", "yes", "true", "1"), ("off", "no", "false", "0")


def pairs(name):
    """The other extras of its set, when that set is one to take together."""
    s = FEATURES[name]["set"]
    return [n for n in FEATURES if n != name and FEATURES[n]["set"] == s] if SETS[s]["together"] else []


def describe(name):
    f = FEATURES[name]
    text = f["what"][0].upper() + f["what"][1:] + "."
    p = pairs(name)
    if p:
        text += " Goes well with: " + ", ".join(FEATURES[n]["label"] for n in p) + "."
    return text + " Read more: " + f["link"]


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
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"kind": k, "since": VERSION}, f)
    return k


def why(name):
    v = conf_value(name)
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
        rows = {n: dict(zip(("on", "why"), why(n)), label=FEATURES[n]["label"], what=FEATURES[n]["what"],
                        link=FEATURES[n]["link"], goes_well_with=pairs(n)) for n in FEATURES}
        if "--json" in a:
            print(json.dumps({"kind": kind(), "features": rows}, indent=1))
        else:
            for n, r in rows.items():
                print(f"{n:17} {'ON ' if r['on'] else 'off'}  {r['label']}  ({r['why']})  {r['link']}")
        return 0
    if cmd in ("on", "off") and len(a) > 1:
        for n in names(a[1]):
            set_conf(n, cmd, FEATURES[n]["label"])
        print(f"{a[1]}: {cmd} (in {conf_file()})")
        return 0
    if cmd == "is-on" and len(a) > 1:
        return 0 if is_on(names(a[1])[0]) else 1
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
    sys.exit(main(sys.argv))
