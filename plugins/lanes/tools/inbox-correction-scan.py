#!/usr/bin/env python3
"""inbox-correction-scan - is the thing a correction says is WRONG still there?

WHY THIS EXISTS (2026-09-19)
  A correction filed as an inbox drop is a *request*. The only thing that fulfils it is somebody
  draining the inbox, and on this estate one correction went four rounds of that and lost.

  A research pass established that a dossier sentence was false. It filed a drop saying so. Two
  later hygiene sweeps re-flagged it. Fifteen days after the first flag the sentence was still
  there, still false, and still being used as the evidence for a live design decision.

  Nobody was careless. Three things made it almost inevitable:

    1. A CORRECTION LOOKS EXACTLY LIKE A CONTRIBUTION. Whoever drains an inbox reads a folder of
       files and folds them in. Nothing distinguishes "here is something new" from "a sentence
       currently in your dossier is false". One bundle was half-drained for exactly this reason:
       its tag half was applied and its date half was not.
    2. VOLUME HIDES IT. That repo held five undrained drops and the estate held thirty. A live
       falsehood was reported at the same volume as a research note.
    3. AGE IS THE WRONG ALARM. "This drop is N days old" says nothing about whether the owner has
       been here, and nothing at all about whether the claim is still wrong.

  So this tool does not ask whether a drop is pending. **It asks whether the falsehood is still
  live** - it reads the target file and looks for the exact string the correction says must go.
  That turns a nudge into a fact, and a fact is escalatable.

THE CONVENTION IT READS
  A correction drop may carry one or more machine-readable lines:

      Still-wrong: <path/to/target.md> :: <exact string that must no longer appear>

  The path is relative to the repo root. The string is matched literally. Write the string the way
  the target file actually has it, and keep it short enough to be unambiguous.

  ⚠️ A drop with a `Supersedes:` line pointing at a document but NO `Still-wrong:` line is reported
  as UNVERIFIABLE - not an error, a nudge to the author. A correction that states what is wrong,
  verbatim, is worth more than one that only states what is right, because only the first can be
  checked by anything but a human re-reading the whole document.

USAGE
  inbox-correction-scan.py <repo-root> [<repo-root> ...] [--json]

EXIT
  0 = no live falsehoods, 1 = at least one live falsehood, 2 = bad usage
"""
import io
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):  # pragma: no cover
    pass

STILL_WRONG = re.compile(r"^Still-wrong:\s*(.+?)\s*::\s*(.+?)\s*$", re.M)
SUPERSEDES = re.compile(r"^Supersedes:\s*(.+?)\s*$", re.M)


def inbox_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        if os.path.basename(dirpath) != "inbox":
            continue
        for name in sorted(filenames):
            if name.endswith(".md") and name != "README.md":
                yield os.path.join(dirpath, name)


def scan(root):
    live, unverifiable, clean = [], [], []
    for path in inbox_files(root):
        try:
            text = io.open(path, encoding="utf-8").read()
        except OSError:
            continue

        claims = STILL_WRONG.findall(text)
        rel_drop = os.path.relpath(path, root).replace("\\", "/")

        if not claims:
            if SUPERSEDES.search(text):
                # A correction that cannot be checked mechanically.
                target = SUPERSEDES.search(text).group(1)
                # A drop superseding another INBOX file is fine - draining both together
                # resolves it, and check 2 of the sweep already pairs them.
                if ".md" in target and "inbox/" in target:
                    continue
                unverifiable.append({"drop": rel_drop, "supersedes": target[:120]})
            continue

        for target, needle in claims:
            tpath = os.path.join(root, target.replace("/", os.sep))
            entry = {"drop": rel_drop, "target": target, "needle": needle}
            if not os.path.exists(tpath):
                entry["state"] = "TARGET MISSING"
                live.append(entry)
                continue
            body = io.open(tpath, encoding="utf-8").read()
            if needle in body:
                entry["state"] = "STILL PRESENT"
                live.append(entry)
            else:
                entry["state"] = "gone"
                clean.append(entry)
    return live, unverifiable, clean


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    as_json = "--json" in sys.argv[1:]
    if not args:
        sys.stderr.write(__doc__.split("USAGE")[1].strip() + "\n")
        return 2

    all_live, all_unver, all_clean = [], [], []
    for root in args:
        if not os.path.isdir(root):
            sys.stderr.write("inbox-correction-scan: not a directory: %s\n" % root)
            return 2
        live, unver, clean = scan(root)
        name = os.path.basename(os.path.abspath(root))
        for e in live + unver + clean:
            e["repo"] = name
        all_live += live
        all_unver += unver
        all_clean += clean

    if as_json:
        print(json.dumps({"live": all_live, "unverifiable": all_unver,
                          "resolved": all_clean}, indent=2))
        return 1 if all_live else 0

    print("=" * 76)
    print("LIVE FALSEHOODS - a correction names this string and the target still has it")
    print("  This is a FACT, not a nudge. Someone is reading something untrue right now.")
    print("=" * 76)
    for e in all_live:
        print("  %s" % e["state"])
        print("    target : %s/%s" % (e["repo"], e["target"]))
        print("    string : %s" % e["needle"][:88])
        print("    said by: %s" % e["drop"])
    print("  (%d)\n" % len(all_live))

    print("=" * 76)
    print("UNVERIFIABLE - corrects a document but does not say what must no longer appear")
    print("  Not an error. Add a 'Still-wrong: <file> :: <string>' line and it becomes checkable.")
    print("=" * 76)
    for e in all_unver:
        print("  %-52s -> %s" % (e["repo"] + "/" + e["drop"], e["supersedes"][:70]))
    print("  (%d)\n" % len(all_unver))

    print("resolved (string is gone, drop can be drained): %d" % len(all_clean))
    return 1 if all_live else 0


if __name__ == "__main__":
    sys.exit(main())
