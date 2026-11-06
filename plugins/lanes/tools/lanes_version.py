"""lanes_version.py - which Lanes this PC runs, and a warning when another PC runs a different one (2026-11-05).

Asked for by the maintainer: "so both PCs are always on the same version without a doubt". On 2026-11-04 the home PC
still ran 0.95.0 while the dev PC ran 0.99.1, and nothing said so. Each PC's handover report on the board now carries
`lanes = <version>`; the session-start line and the close-out box compare it with this PC's own.

    python lanes_version.py          this PC's Lanes version
"""
import json
import os

PLUGIN_JSON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".claude-plugin", "plugin.json")


def mine():
    """This copy's version from its plugin.json, or "" when it cannot be read."""
    try:
        with open(PLUGIN_JSON, encoding="utf-8") as f:
            return str(json.load(f).get("version", "")).strip()
    except (OSError, ValueError, AttributeError):
        return ""


def vtuple(v):
    try:
        return tuple(int(x) for x in v.split("."))
    except (AttributeError, ValueError):
        return ()


def mismatch(machine, theirs, own=None):
    """One plain warning when another PC runs a different Lanes, else "". A report with no version was written by a
    Lanes older than this check (before 0.100.0), which is itself a different version."""
    own = mine() if own is None else own
    if not own:
        return ""
    if not theirs:
        return ("%s runs a Lanes older than 0.100.0 (its report has no version); this PC runs %s: update %s"
                % (machine, own, machine))
    if theirs == own:
        return ""
    newer = machine if vtuple(theirs) > vtuple(own) else "this PC"
    behind = "this PC" if newer == machine else machine
    return "%s runs Lanes %s, this PC runs %s: %s is behind, update it" % (machine, theirs, own, behind) \
        if vtuple(theirs) and vtuple(own) else "%s runs Lanes %s, this PC runs %s" % (machine, theirs, own)


def branch():
    """The branch name when this copy is loaded straight from a git clone on a branch other than main (a test copy,
    e.g. lanes-next), else "". A copy installed from the marketplace is not a clone and says nothing."""
    import subprocess
    root = os.path.dirname(os.path.dirname(PLUGIN_JSON))
    try:
        r = subprocess.run(["git", "-C", root, "rev-parse", "--abbrev-ref", "HEAD"],
                           capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    b = r.stdout.strip() if r.returncode == 0 else ""
    return "" if b in ("", "main", "master", "HEAD") else b


def line():
    """The session's first line, e.g. "🏷️ Lanes 0.100.0 (test branch lanes-next)" (2026-11-05, asked for by the
    maintainer: "in the beginning of the session show which Lanes version the session is running")."""
    v = mine() or "unknown"
    b = branch()
    return "🏷️ Lanes %s%s" % (v, " (test branch %s)" % b if b else "")


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["line"]:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
        print(line())
    else:
        print(mine() or "unknown")
