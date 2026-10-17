"""offers.py - every offer Lanes makes is made ONCE, on the first setup or on the first update that brings it (0.75.0,
2026-10-17, user-directed: "any offer has to be one time only on both install and also future updates on lanes
plugin").

    python offers.py should <name>            exit 0 and print "offer" when <name> has never been offered on this PC;
                                              exit 3 and say when it was, and the answer, when it has
    python offers.py made <name> <answer>     record that <name> was offered and what the person said (yes / no / ...)
    python offers.py list [--json]            every offer this plugin knows, and whether this PC has had it

Whatever the answer was, a recorded offer is never made again by setup or update. The person can still ask for the
thing by name any time (the command that offers it says how). The record lives in ~/.claude/lanes/offers.json
(LANES_STATE_DIR moves it, for tests).
"""
import json
import os
import sys
from datetime import datetime

HOME = os.path.expanduser("~")
STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(HOME, ".claude", "lanes")
STATE = os.path.join(STATE_DIR, "offers.json")

# name: (version that brought it, what it is, in plain words)
KNOWN = {
    "thanks": ("0.75.0", "star and follow, on GitHub, the people whose tools and findings your work uses"),
    "shortcut": ("0.53.0", "a desktop shortcut named Lanes that opens Claude Code in the plugin's look"),
    "openxr-sim": ("0.73.0", "the OpenXR Simulator, a pretend headset (with VR Bench since 0.74.0)"),
    "begone-record": ("0.76.0", "record the game window by itself whenever BeG0nE logs a headset session, so every "
                      "jitter can be seen frame by frame"),
    "superpowers": ("0.77.0", "the superpowers skills plugin (obra): ways of working Claude follows, such as planning before "
                    "building, debugging step by step and checking work before calling it done"),
}


def load():
    try:
        with open(STATE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save(d):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(d, f, indent=1, sort_keys=True)
    os.replace(tmp, STATE)


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    d = load()
    if cmd == "should" and len(rest) == 1:
        rec = d.get(rest[0])
        if rec:
            print(f"already offered on {rec.get('at', '?')[:10]} (answer: {rec.get('answer', '?')}); not offered again")
            return 3
        print("offer")
        return 0
    if cmd == "made" and len(rest) == 2:
        d[rest[0]] = {"answer": rest[1], "at": datetime.now().isoformat(timespec="seconds")}
        save(d)
        print(f"noted: {rest[0]} was offered (answer: {rest[1]}); it will not be offered again")
        return 0
    if cmd == "list":
        rows = [{"name": n, "since": v, "what": w, "offered": n in d,
                 "answer": d.get(n, {}).get("answer"), "at": d.get(n, {}).get("at")}
                for n, (v, w) in KNOWN.items()]
        rows += [{"name": n, "since": None, "what": None, "offered": True, "answer": r.get("answer"), "at": r.get("at")}
                 for n, r in d.items() if n not in KNOWN]
        if "--json" in rest:
            print(json.dumps(rows, indent=1))
        else:
            for r in rows:
                state = f"offered {str(r['at'])[:10]}, answer {r['answer']}" if r["offered"] else "not offered yet"
                print(f"{r['name']:<12} {state}" + (f"  - {r['what']}" if r["what"] else ""))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
