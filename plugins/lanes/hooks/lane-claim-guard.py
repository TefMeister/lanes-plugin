"""lane-claim-guard.py -- block a /pd or /lm prompt that names a job another
same-lane session has claimed LIVE.

Wired as a UserPromptSubmit hook (see hooks/hooks.json).

WHY A HOOK AND NOT JUST A RULE IN THE COMMAND FILE
  The collision this exists to stop was a session that READ the rule, looked at
  the evidence, and judged wrong: it saw a commit from twenty-seven minutes
  earlier, decided that session had finished, and undid its fix. Git was clean;
  the loss was semantic. A rule the model applies is behavioural. A hook is the
  same check for every session, and it runs before the model sees the prompt.
  The command files still carry the rule -- this is the floor under them.

WHAT IT DOES
  Prompt starts with "/pd" or "/lm" -> resolve the named job(s) against
  status/*.md on origin/main of the board repo, run `lane-claim.sh check`, and if
  any FRESH (or malformed) claim exists, exit 2 with the reason. The prompt is
  blocked and the reason is shown.

  "force" anywhere in the arguments -> let it through; the command file makes the
  session say so out loud. Anything else -> exit 0, silent.

  Fetch failure, no board, unknown names -> exit 0, silent. THIS HOOK MUST NEVER
  FAIL CLOSED: a broken guard that blocks every /pd is worse than no guard.

Scope: reads origin/main only and never touches a working tree, so it is safe to
run from any lane's clone root on any machine.
"""
import json
import os
import re
import subprocess
import sys

CONF_KEY = "board"


def read_conf(key):
    """Read `key = value` from the same config file the shell tools use."""
    candidates = [os.environ.get("LANES_CONFIG"),
                  os.path.expanduser("~/.claude/lanes.conf"),
                  os.path.expanduser("~/.config/lanes/lanes.conf")]
    pat = re.compile(r"^\s*" + re.escape(key) + r"\s*=\s*(.*?)\s*$")
    for path in candidates:
        if not path or not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    m = pat.match(line.rstrip("\r\n"))
                    if m:
                        return m.group(1).strip().strip('"')
        except Exception:
            continue
    return None


def find_board():
    # LANE_CLAIM_REPO is the test override; it points at a throwaway clone.
    for value in (os.environ.get("LANE_CLAIM_REPO"),
                  os.environ.get("LANES_BOARD"),
                  read_conf(CONF_KEY)):
        if value and os.path.isdir(os.path.join(value, "status")):
            return value
    return None


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo] + list(args),
                       capture_output=True, text=True, timeout=15)
    return r.returncode, r.stdout


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def resolve(tokens, prefixes):
    """Exact match first; otherwise every prefix containing all the tokens."""
    hits = [t for t in tokens if t in prefixes]
    if hits:
        return hits
    want = [norm(t) for t in tokens if norm(t)]
    if not want:
        return []
    fuzzy = [p for p in prefixes if all(w in norm(p) for w in want)]
    return fuzzy if len(fuzzy) == 1 else []


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    prompt = (data.get("prompt") or "").strip()
    m = re.match(r"^/(pd|lm)\b(.*)$", prompt, re.S)
    if not m:
        return 0
    lane, rest = "/" + m.group(1), m.group(2).strip()
    # Keep the user's OWN tokens for the remedy text (fault 8): the suggested command
    # used to be rebuilt as lane + " force " + jobs, which silently dropped every other
    # token -- skip: lists, "i launch", anything -- and told the user to type something
    # they had not asked for. Only the job names go through name resolution.
    own_tokens = rest.split()
    tokens = [t for t in own_tokens if not t.startswith("skip:")]
    if any(t.lower() == "force" for t in tokens):
        return 0
    tokens = [t for t in tokens if t.lower() != "force"]
    if not tokens:
        return 0

    board = find_board()
    if not board:
        return 0
    try:
        git(board, "fetch", "-q", "origin")
        rc, out = git(board, "ls-tree", "--name-only", "origin/main", "status/")
        if rc != 0:
            return 0
        names = [os.path.basename(p)[:-3] for p in out.split()
                 if p.endswith(".md") and not p.endswith("_headlines-archive.md")]
        jobs = resolve(tokens, names)
        if not jobs:
            return 0
        # The claim script ships beside this hook, in the plugin's tools/ folder.
        # Fall back to the board's own copy only if this file was lifted out alone.
        here = os.path.dirname(os.path.abspath(__file__))
        tool = os.path.join(here, "..", "tools", "lane-claim.sh")
        if not os.path.isfile(tool):
            tool = os.path.join(board, "tools", "lane-claim.sh")
        if not os.path.isfile(tool):
            return 0
        r = subprocess.run(["bash", tool, "check", "--no-fetch", "--repo", board] + jobs,
                           capture_output=True, text=True, timeout=15)
    except Exception:
        return 0
    if r.returncode != 1:
        return 0
    blocked = [l for l in r.stdout.splitlines() if " FRESH " in l or " MALFORMED " in l]
    if not blocked:
        return 0
    sys.stderr.write(
        "BLOCKED by lane-claim-guard: the same lane is already live on this job.\n"
        + "\n".join("  " + l.strip() for l in blocked)
        + "\n\nWait for that session to finish (it releases the claim in its write-up), or if it "
          "is really dead, type exactly:  " + lane + " force " + " ".join(own_tokens)
        + "\nA claim older than 12h is treated as stale and does not block.\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
