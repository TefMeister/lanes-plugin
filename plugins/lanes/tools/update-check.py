#!/usr/bin/env python3
"""update-check - is a newer version of this plugin published than the one installed here?

WHY THIS EXISTS (2026-09-17)
  A new version only reaches a machine when someone runs `claude plugin update`, and nothing
  told anyone a new one existed: the only reminders were notes on a board. Now the session tells
  the user, lists what changed, and updates on their say-so.

HOW IT KNOWS (no extra credentials, works for a private repo)
  Claude Code keeps a git clone of every marketplace (known_marketplaces.json -> installLocation).
  This runs `git fetch` in that clone - using whatever git sign-in the machine already has - and
  reads the plugin's version from the fetched default branch. It never changes the clone's files,
  never installs anything, and is silent on any failure (offline, no git, no clone).

  The fetch runs at most once every CHECK_EVERY_H hours; between fetches the last result is reused.

USAGE
  python update-check.py            one plain line when a newer version exists; nothing otherwise
  python update-check.py --json     {"installed", "latest", "newer", "marketplace", "changes": [...], ...}
  python update-check.py --force    ignore the fetch throttle and the "not now" answer
  python update-check.py --dismiss  the user said "not now": stay quiet about THIS version for SNOOZE_H hours

  Test overrides: LANES_STATE_DIR, LANES_PLUGIN_ROOT (the installed copy), LANES_UPDATE_MARKETPLACE_DIR
  (a clone to fetch in), LANES_UPDATE_MARKETPLACE (its name).
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys

PLUGIN_NAME = "lanes"
CHECK_EVERY_H = 6          # fetch from GitHub at most this often
SNOOZE_H = 24              # after "not now", stay quiet about that version this long
# The update question, word for word, on its own line with its own icon (2026-09-21).
ASK_LINE = "\U0001f514 **New plugin update available! Would you like to install it now?**"
GIT_TIMEOUT_S = 15
MAX_CHANGES_SHOWN = 8
CHANGELOG_LINE_RE = re.compile(r"^- \*\*(\d+\.\d+(?:\.\d+|\.x)?)\*\*\s*(?:\([^)]*\))?\s*[:—-]*\s*(.*)$")

HOME = os.path.expanduser("~")
STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(HOME, ".claude", "lanes")
STATE_FILE = os.path.join(STATE_DIR, "update-state.json")
PLUGIN_ROOT = os.environ.get("LANES_PLUGIN_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_REL = f"plugins/{PLUGIN_NAME}/.claude-plugin/plugin.json"
CHANGELOG_REL = f"plugins/{PLUGIN_NAME}/CHANGELOG.md"  # read from GitHub, because Claude Code's clone is shallow


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def vtuple(v):
    try:
        return tuple(int(x) for x in v.split("."))
    except (AttributeError, ValueError):
        return ()


def git(repo, *args):
    try:
        r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                           timeout=GIT_TIMEOUT_S, encoding="utf-8", errors="replace")
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def version_at(root):
    try:
        with open(os.path.join(root, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
            return json.load(f).get("version")
    except (OSError, ValueError):
        return None


def in_cache(root):
    """Is this root an INSTALLED copy (…/plugins/cache/<marketplace>/<plugin>/<version>)?"""
    parts = os.path.normpath(os.path.abspath(root)).split(os.sep)
    return "cache" in parts and len(parts) > parts.index("cache") + 1


def newest_installed():
    """(root, version) of the newest installed copy, searching the plugin cache directly.

    ⚠️ THIS EXISTS BECAUSE THE SCRIPT CANNOT TRUST ITS OWN LOCATION (2026-09-18). PLUGIN_ROOT
    defaults to wherever this file happens to live, so running the copy inside a REPO CLONE made
    installed_version() report the repo's version and marketplace() find no marketplace at all.
    The result was `newer: false` -- a confident "you are up to date" about a machine it had not
    looked at. `/lanes:update`'s own step 1 pointed at a repo clone, so that is what it did every
    time it was run. Same shape as fault 11: the failure is indistinguishable from success.
    """
    base = os.path.join(HOME, ".claude", "plugins", "cache")
    best = (None, None)
    try:
        markets = os.listdir(base)
    except OSError:
        return best
    for market in markets:
        plugin_dir = os.path.join(base, market, PLUGIN_NAME)
        if not os.path.isdir(plugin_dir):
            continue
        for entry in os.listdir(plugin_dir):
            root = os.path.join(plugin_dir, entry)
            version = version_at(root)
            if version and (best[1] is None or vtuple(version) > vtuple(best[1])):
                best = (root, version)
    return best


def resolve_root():
    """(root, version, ran_from_repo). Prefer the real installed copy over this file's location."""
    if in_cache(PLUGIN_ROOT) or os.environ.get("LANES_PLUGIN_ROOT"):
        return PLUGIN_ROOT, version_at(PLUGIN_ROOT), False
    root, version = newest_installed()
    if root:
        return root, version, True
    # Nothing installed anywhere: fall back, but say the version came from a repo.
    return PLUGIN_ROOT, version_at(PLUGIN_ROOT), True


def marketplace(root):
    """(name, clone dir). Installed copies live at plugins/cache/<marketplace>/<plugin>/<version>."""
    name = os.environ.get("LANES_UPDATE_MARKETPLACE")
    if not name:
        parts = os.path.normpath(os.path.abspath(root)).split(os.sep)
        if "cache" in parts and len(parts) > parts.index("cache") + 1:
            name = parts[parts.index("cache") + 1]
    clone = os.environ.get("LANES_UPDATE_MARKETPLACE_DIR")
    source = os.environ.get("LANES_UPDATE_MARKETPLACE_SOURCE")
    if not clone and name:
        try:
            with open(os.path.join(HOME, ".claude", "plugins", "known_marketplaces.json"), encoding="utf-8") as f:
                entry = json.load(f).get(name) or {}
            clone = entry.get("installLocation")
            source = (entry.get("source") or {}).get("source")
        except (OSError, ValueError):
            clone = None
    return name, clone, source


def commits_behind(clone):
    """How far the clone's CHECKED-OUT tree is behind its origin, or None if unknown.

    ⚠️ THE SECOND HALF OF THE SAME TRAP (2026-09-18). fetch_latest() reads origin/main, so it sees
    a new release the moment it is pushed. But `claude plugin update` installs from the clone's
    WORKING TREE. For a marketplace registered as a local directory those two differ whenever the
    release was pushed from a different clone of the repo -- and the installer then answers
    "already at the latest version", naming the OLD one, right after the checker promised a new one.
    Observed 2026-09-18: 0.12.0 was pushed from one clone root while the marketplace pointed at
    another, and the update reported success twice without installing anything.
    """
    if not clone or not os.path.isdir(os.path.join(clone, ".git")):
        return None
    for cand in ("origin/HEAD", "origin/main", "origin/master"):
        if git(clone, "rev-parse", "--verify", "--quiet", cand):
            out = git(clone, "rev-list", "--count", f"HEAD..{cand}")
            try:
                return int((out or "").strip())
            except ValueError:
                return None
    return None


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except OSError:
        pass


def hours_since(iso):
    try:
        return (now() - datetime.datetime.fromisoformat(iso)).total_seconds() / 3600
    except (TypeError, ValueError):
        return float("inf")


def fetch_latest(clone):
    """(latest version, [(version, summary)] newest first) from the clone's fetched default branch."""
    if not clone or not os.path.isdir(clone):
        return None, []
    git(clone, "fetch", "--quiet", "origin")
    ref = None
    for cand in ("origin/HEAD", "origin/main", "origin/master"):
        if git(clone, "rev-parse", "--verify", "--quiet", cand):
            ref = cand
            break
    if not ref:
        return None, []
    manifest = git(clone, "show", f"{ref}:{MANIFEST_REL}")
    try:
        latest = json.loads(manifest).get("version") if manifest else None
    except ValueError:
        latest = None
    changes = []
    for line in (git(clone, "show", f"{ref}:{CHANGELOG_REL}") or "").splitlines():
        m = CHANGELOG_LINE_RE.match(line.strip())
        if m:
            changes.append((m.group(1), m.group(2).strip()))
    return latest, changes


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # the bell icon in ASK_LINE is not in cp1252
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dismiss", action="store_true")
    args = ap.parse_args()

    root, installed, ran_from_repo = resolve_root()
    name, clone, source = marketplace(root)
    state = load_state()

    if args.force or hours_since(state.get("last_check")) >= CHECK_EVERY_H:
        latest, changes = fetch_latest(clone)
        if latest:
            state.update(last_check=now().isoformat(), latest=latest, changes=changes)
            save_state(state)
    latest = state.get("latest")
    changes = [tuple(c) for c in state.get("changes", [])]
    newer = bool(installed and latest and vtuple(latest) > vtuple(installed))

    if args.dismiss:
        if latest:
            state.update(dismissed_version=latest, dismissed_at=now().isoformat())
            save_state(state)
        return 0

    snoozed = (not args.force and state.get("dismissed_version") == latest
               and hours_since(state.get("dismissed_at")) < SNOOZE_H)
    missed = [c for c in changes if vtuple(c[0].replace(".x", ".0")) > vtuple(installed or "0")]

    # A marketplace registered as a local DIRECTORY installs from that clone's working tree, not
    # from origin. If the tree is behind, `claude plugin update` cheerfully reports the old version
    # as "the latest". Pulling it first is the whole fix, so it belongs in the command list rather
    # than in a note nobody reads.
    behind = commits_behind(clone) if source == "directory" else None
    update_cmds = []
    if name:
        if behind:
            update_cmds.append(f'git -C "{clone}" pull --ff-only')
        update_cmds += [f"claude plugin marketplace update {name}",
                        f"claude plugin update {PLUGIN_NAME}@{name}"]

    if args.json:
        print(json.dumps({"plugin": PLUGIN_NAME, "installed": installed, "latest": latest, "newer": newer,
                          "snoozed": snoozed, "marketplace": name, "changes": missed,
                          "update_commands": update_cmds,
                          "installed_root": root, "ran_from_repo": ran_from_repo,
                          "marketplace_source": source, "marketplace_behind": behind}, indent=2))
        return 0
    if newer and not snoozed:
        shown = "; ".join(f"{v}: {s.rstrip('.')}" for v, s in missed[:MAX_CHANGES_SHOWN])
        more = f" (+{len(missed) - MAX_CHANGES_SHOWN} more)" if len(missed) > MAX_CHANGES_SHOWN else ""
        print(f"A NEW VERSION of the {PLUGIN_NAME} plugin is available: {latest} (this machine has {installed}). "
              f"What changed: {shown}{more}. "
              f"Tell the user in one or two plain sentences (what it means for them, not the version list), and "
              f"ASK whether you may update it now: end that with this question, exactly, on a line of its own with its bell icon and nothing else on the line: " + ASK_LINE + f" Only if they say yes, run: {' && '.join(update_cmds)} - then tell "
              f"them the new version takes effect after they restart Claude Code. If they say not now, run: "
              f"python \"${{CLAUDE_PLUGIN_ROOT}}/tools/update-check.py\" --dismiss  (quiet for {SNOOZE_H} h).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
