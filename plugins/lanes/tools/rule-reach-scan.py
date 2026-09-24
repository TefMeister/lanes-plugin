#!/usr/bin/env python3
"""rule-reach-scan - can a standing rule actually REACH the session that needs it?

WHY THIS EXISTS (2026-09-19)
  A rule can be written down perfectly and still never arrive. On this estate one did, twice.

  The user gave a design instruction at the start of one project - "mod the game as natively as
  possible" - and had to give it again fifteen days later, because in between not one session
  applied it. It had not been lost. It was filed, in the right repo, with the user's own words
  quoted and the reasoning intact. It still never reached anybody, for three dull reasons:

    1. REACH  - it lived only in a file the harness does not auto-load. The project's CLAUDE.md
                says to "skim as needed", and a rule that governs every design decision cannot
                depend on somebody deciding they need it.
    2. TITLE  - its heading was "Reach for the deep end". Nothing in those words is what a session
                would search for when the decision is live: not "native", not "C++", not "Lua",
                not "script". It was eventually found by grepping the BODY, by luck.
    3. SPLIT  - the same subject later got a second section elsewhere. Two copies of one rule are
                free to drift apart, and then neither is trustworthy.

  Every other check in this plugin looks at the RECORDS - tags, inboxes, board blocks. This one
  looks at whether the rules themselves are reachable, findable and single. It is deliberately
  mechanical: "is this rule reachable" should not be a judgement call made by the session that
  would suffer from getting it wrong.

  See docs/PROTOCOL.md section 8.

USAGE
  rule-reach-scan.py --always <file> [--rules <file>...] [--keywords <file>] [--json]

  --always    the file (or files) the harness auto-loads every session
  --rules     files holding standing rules that are NOT auto-loaded
  --keywords  optional newline-separated extra words that count as findable

EXIT
  0 = no faults, 1 = faults found, 2 = bad usage
"""
import argparse
import io
import json
import os
import re
import sys

# Headings on this estate carry emoji and dashes. A Windows console defaults to cp1252 and
# dies on them, which would make the checker unrunnable on the machine it is checking.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):  # pragma: no cover - older interpreters
    pass

# Words a heading can carry that make it findable when the decision is live. This is the
# vocabulary of the work, not of the prose - concrete nouns somebody would grep for.
DEFAULT_KEYWORDS = """
c++ cpp lua script native code engine plugin dll proxy hook patch memory
commit push repo git branch inbox lane claim board gate open status save
model opus fable sonnet haiku token
launch game headset vr flat stereo camera projection fov eye ipd render
test verify measure evidence tag confidence proof
screenshot capture log logging
machine pc dev home cross
release disclaimer credit attribution licence license removal
idea capture file folder path index
window windowed resolution fullscreen
numpad key keybind hotkey binding input controller hand animation bone mesh ik
reminder owed sync
subagent subagents agent agents helper reader fork parallel concurrent
tone voice reply report wording language jargon
mission goal aim workflow session mode
backup savegame
research sweep dossier notes ledger documentation
weapon blender model
profile readme activity frontpage
legal framerate performance
rule rules lesson preference instruction
observation observations report reported saw sighting judgement
ask asking request risk risky breaking safety
tool tools watch watchlist
""".split()

# A rule that claims to apply everywhere. These are the ones that MUST be reachable.
UNIVERSAL = re.compile(
    r"universal|every project|every game|every session|all games|every lane|"
    r"standing rule|from now on|always|never",
    re.I,
)


def sections(path):
    """Yield (line_no, heading, body) for every top-level '## ' section."""
    text = io.open(path, encoding="utf-8").read()
    lines = text.split("\n")
    head, buf, start = None, [], 0
    for n, line in enumerate(lines, 1):
        if line.startswith("## ") and not line.startswith("### "):
            if head is not None:
                yield start, head, "\n".join(buf)
            head, buf, start = line[3:].strip(), [], n
        elif head is not None:
            buf.append(line)
    if head is not None:
        yield start, head, "\n".join(buf)


def words(s):
    return set(re.findall(r"[a-z+]+", s.lower()))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--always", action="append", required=True,
                    help="a file the harness auto-loads every session")
    ap.add_argument("--rules", action="append", default=[],
                    help="a file of standing rules that is NOT auto-loaded")
    ap.add_argument("--keywords", help="file of extra findable words, one per line")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    keywords = set(DEFAULT_KEYWORDS)
    if args.keywords and os.path.exists(args.keywords):
        keywords |= set(io.open(args.keywords, encoding="utf-8").read().split())

    missing = [p for p in args.always + args.rules if not os.path.exists(p)]
    if missing:
        for p in missing:
            sys.stderr.write("rule-reach-scan: no such file: %s\n" % p)
        return 2

    always_text = "\n".join(io.open(p, encoding="utf-8").read() for p in args.always).lower()

    faults = {"unreachable": [], "unfindable": [], "split": []}
    seen = {}

    for path in args.always + args.rules:
        auto = path in args.always
        for n, head, body in sections(path):
            hw = words(head)
            findable = bool(hw & keywords)
            universal = bool(UNIVERSAL.search(head + "\n" + body[:800]))
            entry = {"file": os.path.basename(path), "line": n, "heading": head}

            # FAULT 2 - heading carries no word anybody would search for.
            if not findable:
                faults["unfindable"].append(dict(entry, auto=auto))

            # FAULT 1 - a universal rule with no route from an always-read file.
            # The test is deliberately weak on purpose: it asks only whether the
            # subject is MENTIONED in the always-read text at all. A rule that fails
            # even this has no route whatsoever.
            if not auto and universal:
                key = [w for w in hw if w in keywords]
                if not key or not any(k in always_text for k in key):
                    faults["unreachable"].append(entry)

            # FAULT 3 - the same subject headed in more than one file.
            subject = frozenset(w for w in hw if w in keywords)
            if len(subject) >= 2:
                seen.setdefault(subject, []).append(entry)

    for subject, entries in seen.items():
        if len({e["file"] for e in entries}) > 1:
            faults["split"].append({"subject": sorted(subject), "places": entries})

    total = sum(len(v) for v in faults.values())

    if args.json:
        print(json.dumps({"faults": faults, "total": total}, indent=2))
        return 1 if total else 0

    def show(title, why, items, fmt):
        print("=" * 76)
        print(title)
        print("  %s" % why)
        print("=" * 76)
        for it in items:
            print(fmt(it))
        print("  (%d)" % len(items))
        print()

    show("UNREACHABLE - a universal rule with no route from an always-read file",
         "Filed correctly and still never arrives. This is the fault that cost 15 days.",
         faults["unreachable"],
         lambda e: "  %-18s L%-5d %s" % (e["file"], e["line"], e["heading"][:70]))

    show("UNFINDABLE - a heading carrying no word a session would search for",
         'The "Reach for the deep end" fault: right rule, invisible title.',
         faults["unfindable"],
         lambda e: "  [%s] %-18s L%-5d %s" % ("auto" if e["auto"] else "skim",
                                              e["file"], e["line"], e["heading"][:62]))

    show("SPLIT - one subject stated in two files, free to drift apart",
         "Keep the full text in the always-read file and leave a pointer behind.",
         faults["split"],
         lambda s: "  %s\n%s" % (", ".join(s["subject"]),
                                 "\n".join("      %-18s L%-5d %s" % (e["file"], e["line"],
                                                                     e["heading"][:58])
                                           for e in s["places"])))

    print("%d fault(s)" % total)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
