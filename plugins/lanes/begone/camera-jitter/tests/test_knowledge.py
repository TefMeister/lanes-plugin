"""Self-test for the knowledge base: made-up sessions with known faults, checked that
  - two sessions that behave the same collapse into ONE pattern (no copies),
  - labels stick to the pattern and survive a rebuild,
  - the report names the measure that separates jittery from smooth (camera writes per picture),
  - a session with no head movement is skipped, not stored as a pattern.

    python tests/test_knowledge.py      exit code 0 = all good
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import jitter_log_check  # noqa: E402
import knowledge  # noqa: E402


def main():
    tmp = tempfile.mkdtemp(prefix="begone-know-")
    knowledge.DATA = os.path.join(tmp, "data")
    knowledge.KNOW = os.path.join(tmp, "knowledge")
    knowledge.BASE = os.path.join(knowledge.KNOW, "patterns.json")
    knowledge.FINDINGS = os.path.join(knowledge.KNOW, "FINDINGS.md")
    failed = 0

    def check(name, ok):
        nonlocal failed
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name}")

    sessions = [("village", "run1_stepped", "stepped"), ("village", "run2_stepped", "stepped"),
                ("village", "run3_smooth", "smooth"), ("hardreset", "run4_smooth", "smooth"),
                ("hardreset", "run5_stale", "stale"), ("hardreset", "run6_still", "still")]
    try:
        for game, run, case in sessions:
            log = os.path.join(tmp, run + ".jl")
            with open(log, "w", encoding="utf-8") as f:
                f.write(jitter_log_check._synth(case))
            out = os.path.join(knowledge.DATA, game, run)
            jitter_log_check.check(log, out)
            fid, status = knowledge.ingest(out)
            print(f"      {run}: pattern {fid} {status}")
        base = knowledge._load()
        p_of = lambda run: base["sessions"][run]["pattern"]
        check("same behaviour -> one pattern", p_of("run1_stepped") == p_of("run2_stepped")
              and base["patterns"][p_of("run1_stepped")]["count"] == 2)
        check("different behaviour -> different patterns", len({p_of("run1_stepped"), p_of("run3_smooth"), p_of("run5_stale")}) == 3)
        check("no head movement -> no pattern", p_of("run6_still") is None)
        knowledge.label("run1_stepped", "jittery", "felt stepped on a slow turn")
        knowledge.label("run3_smooth", "smooth")
        knowledge.label("run4_smooth", "smooth")
        knowledge.label("run5_stale", "jittery")
        base = knowledge._load()
        check("label sticks to the pattern", base["patterns"][p_of("run1_stepped")]["labels"].get("jittery") == 1)
        text = open(knowledge.FINDINGS, encoding="utf-8").read()
        check("report names the separating measure", "**camera writes per picture**" in text or
              "**pose reads identical to the one before**" in text)
        check("report has a per-game section", "## village" in text and "## hardreset" in text)
        knowledge.rebuild()
        base = knowledge._load()
        check("labels survive a rebuild", base["sessions"]["run1_stepped"].get("label") == "jittery"
              and len(base["patterns"]) == 3)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"{8 - failed}/8 checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
