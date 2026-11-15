#!/usr/bin/env python3
"""netcheck.py - is this PC still safe on the network, and what changed since last week (0.116.0, 2026-11-15, extra
`netcheck`).

Asked for by the maintainer, 2026-11-15: "is there a way to add some sort of a network security check to the weekly
fullscan". It READS ONLY: no setting is changed, no program is stopped or removed, nothing is sent anywhere. What it
finds is said in plain words; the person decides what, if anything, to do.

    python netcheck.py scan [--json] [--no-save]
                                   read this PC (netcheck_gather.ps1, no administrator rights needed), compare with
                                   the last check, print the findings, keep today's reading in this PC's Lanes folder
                                   (never GitHub: it names programs and network settings).
                                   Exit 0 = nothing to look at, 1 = something worth a look, 2 = could not run
    python netcheck.py show        print the last report again

WHAT IT LOOKS AT
  every week    Windows Firewall on for every kind of network; an antivirus switched on and up to date; Remote Desktop,
                Remote Assistance and the old SMB1 file sharing (off is safer); Windows updates installed lately;
                whether each network is set as Public (safer) or Private (trusted)
  what changed  a program that newly accepts connections from the network; a new opening in the firewall; a program
                that newly starts with Windows; a remote-access program that was not running before; a program that
                newly talks to the internet; the PC's name server; the hosts file
  The first check on a PC is the starting list: from the second one on it says what changed.

EXPECTED PROGRAMS. `netcheck_known = <program>, <program>` in lanes.conf names programs that are there on purpose
(a compute node, a remote-access tool the person uses): they are listed as expected and never flagged as new. Never
suggest stopping or removing them.
Tests feed a pretend reading with NETCHECK_TEST_GATHER=<file.json>.
"""
import json
import os
import subprocess
import sys
import time

HOME = os.path.expanduser("~")
HERE = os.path.dirname(os.path.abspath(__file__))
CONF = os.environ.get("LANES_CONFIG") or os.path.join(HOME, ".claude", "lanes.conf")
STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(HOME, ".claude", "lanes")
OUT_DIR = os.path.join(STATE_DIR, "netcheck")
GATHER = os.path.join(HERE, "netcheck_gather.ps1")

# ---- settings (named numbers, one place) --------------------------------------------------------
GATHER_TIMEOUT_S = 180
SIGNATURE_MAX_DAYS = 7            # virus definitions older than this are out of date
UPDATE_MAX_DAYS = 45              # no Windows update installed for this long
LISTED_MAX = 8                    # names listed per finding; the rest are counted
REMOTE_TOOLS = {                  # process name (lower case) -> plain name
    "rustdesk": "RustDesk", "teamviewer": "TeamViewer", "teamviewer_service": "TeamViewer", "anydesk": "AnyDesk",
    "tailscaled": "Tailscale", "tailscale-ipn": "Tailscale", "parsecd": "Parsec", "sunshine": "Sunshine",
    "remoting_host": "Chrome Remote Desktop", "splashtopstreamer": "Splashtop", "srservice": "Splashtop",
    "tvnserver": "TightVNC", "winvnc": "VNC", "vncserver": "VNC", "screenconnect.clientservice": "ScreenConnect",
    "ultraviewer_service": "UltraViewer", "supremo": "Supremo", "aa_v3": "Ammyy Admin", "rutserv": "Remote Utilities",
    "meshagent": "MeshCentral", "zerotier-one_x64": "ZeroTier", "hamachi-2": "Hamachi",
}
WARN, NOTE, OK = "warn", "note", "ok"


def conf():
    out = {}
    try:
        with open(CONF, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                if "=" in line:
                    k, v = line.split("=", 1)
                    out.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except OSError:
        pass
    return out


def known_programs(c):
    return {x.strip().lower() for x in c.get("netcheck_known", "").split(",") if x.strip()}


def is_known(name, known):
    """a program named in netcheck_known, or one whose name starts with such a name (AethirChecker covers
    AethirCheckerClient and AethirCheckerService)"""
    low = (name or "").lower()
    return bool(low) and any(low.startswith(k) for k in known)


def gather():
    test = os.environ.get("NETCHECK_TEST_GATHER")
    if test:
        with open(test, encoding="utf-8-sig") as f:
            return json.load(f)
    if os.name != "nt":
        return None
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", GATHER],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=GATHER_TIMEOUT_S,
                           creationflags=flags)
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = r.stdout.strip()
    start = text.find("{")
    try:
        return json.loads(text[start:]) if start >= 0 else None
    except ValueError:
        return None


def listed(names):
    names = sorted(set(n for n in names if n))
    more = len(names) - LISTED_MAX
    return ", ".join(names[:LISTED_MAX]) + (" and %d more" % more if more > 0 else "")


def as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def remote_running(d):
    return {REMOTE_TOOLS[p.lower()] for p in as_list(d.get("processes")) if p and p.lower() in REMOTE_TOOLS}


def network_listeners(d, known):
    return {x.get("program", "") for x in as_list(d.get("listening")) if x.get("all") and x.get("program")
            and not is_known(x.get("program", ""), known)}


def rule_label(r):
    return r.get("name") or r.get("program") or r.get("id", "?")


def findings(d, last, known):
    out = []
    fw = as_list(d.get("firewall"))
    off = [f["name"] for f in fw if not f.get("on")]
    if off:
        out.append((WARN, "Windows Firewall is OFF for %s networks: switch it back on (Windows Security, Firewall)."
                    % " and ".join(off)))
    elif fw:
        out.append((OK, "Windows Firewall is on for every kind of network."))
    av = [a for a in as_list(d.get("antivirus")) if a.get("on")]
    defender = d.get("defender") or {}
    if not av and not defender.get("realtime"):
        out.append((WARN, "no antivirus is switched on."))
    else:
        names = listed(a.get("name", "") for a in av) or "Windows Defender"
        stale = [a.get("name", "") for a in av if a.get("out_of_date")]
        age = defender.get("age_days")
        if stale:
            out.append((WARN, "the antivirus says it is out of date: %s." % listed(stale)))
        elif defender.get("realtime") and isinstance(age, int) and age > SIGNATURE_MAX_DAYS:
            out.append((WARN, "Windows Defender's virus definitions are %d days old (Windows Update brings new ones)."
                        % age))
        else:
            out.append((OK, "antivirus on and up to date (%s)." % names))
    if d.get("remote_desktop"):
        out.append((WARN, "Remote Desktop is ON: this PC accepts remote logins. Off is safer unless you use it."))
    if d.get("remote_assistance"):
        out.append((NOTE, "Windows Remote Assistance invitations are allowed. Off is safer if you never use it "
                          "(System, Remote settings)."))
    if d.get("smb1"):
        out.append((WARN, "the old SMB1 file sharing is installed: old and unsafe, nothing modern needs it."))
    upd = d.get("last_update")
    if upd:
        try:
            days = int((time.time() - time.mktime(time.strptime(upd, "%Y-%m-%d"))) / 86400)
        except ValueError:
            days = 0
        if days > UPDATE_MAX_DAYS:
            out.append((WARN, "no Windows update installed for %d days." % days))
        else:
            out.append((OK, "Windows updates installed lately (the newest %d days ago)." % days))
    nets = as_list(d.get("networks"))
    if nets:
        out.append((NOTE, "networks: " + "; ".join("%s set as %s" % (n.get("adapter", "?"), n.get("category", "?"))
                                                   for n in nets) + " (Public is the safer setting)."))
    remote = remote_running(d)
    knownnames = sorted(p for p in as_list(d.get("processes")) if is_known(p, known))
    if not last:
        out.append((NOTE, "first check on this PC: today's reading is the starting list; from next week on this says "
                          "what changed."))
        if remote:
            out.append((NOTE, "remote-access programs running: %s." % listed(remote)))
        listen = network_listeners(d, known)
        if listen:
            out.append((NOTE, "programs that accept connections from the network: %s." % listed(listen)))
    else:
        new = network_listeners(d, known) - network_listeners(last, known)
        if new:
            out.append((WARN, "NEW since the last check: accepts connections from the network: %s." % listed(new)))
        old_rules = {r.get("id") for r in as_list(last.get("inbound_rules"))}
        new_rules = [r for r in as_list(d.get("inbound_rules")) if r.get("id") not in old_rules
                     and not is_known(r.get("program", ""), known)]
        if new_rules:
            out.append((WARN, "NEW openings in the firewall (%d): %s. Fine when you just installed that program."
                        % (len(new_rules), listed(rule_label(r) for r in new_rules))))
        new_start = set(as_list(d.get("startup"))) - set(as_list(last.get("startup")))
        if new_start:
            out.append((WARN, "NEW at Windows start: %s." % listed(new_start)))
        new_remote = {t for t in remote - remote_running(last) if not is_known(t, known)}
        if new_remote:
            out.append((WARN, "a remote-access program is running that was not before: %s." % listed(new_remote)))
        talk_old = {t.get("program") for t in as_list(last.get("talking_out"))}
        talk_new = {t.get("program") for t in as_list(d.get("talking_out"))} - talk_old - {""}
        talk_new = {t for t in talk_new if not is_known(t, known)}
        if talk_new:
            out.append((NOTE, "talking to the internet now, not at the last check: %s (usually just a program you "
                              "opened)." % listed(talk_new)))
        if sorted(as_list(d.get("dns"))) != sorted(as_list(last.get("dns"))) and last.get("dns") is not None:
            out.append((WARN, "the PC's name server changed since the last check (a new router does that; so does "
                              "unwanted software)."))
        if as_list(d.get("hosts")) != as_list(last.get("hosts")) and last.get("hosts") is not None:
            out.append((WARN, "the hosts file changed since the last check (%d line(s) in use now)."
                        % len(as_list(d.get("hosts")))))
    if knownnames:
        out.append((OK, "expected and left alone (netcheck_known): %s." % listed(knownnames)))
    return out


ICON = {WARN: "⚠️", NOTE: "ℹ️", OK: "✅"}


def write(d, found):
    os.makedirs(OUT_DIR, exist_ok=True)
    md = os.path.join(OUT_DIR, time.strftime("%Y-%m-%d") + ".md")
    lines = ["# Network check, %s" % time.strftime("%Y-%m-%d %H:%M"), "", "Read only: nothing was changed.", ""]
    lines += ["- %s %s" % (ICON[lv], text) for lv, text in found]
    lines += ["", "## The reading", "", "```json", json.dumps(d, indent=1), "```"]
    with open(md, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(OUT_DIR, "last.json"), "w", encoding="utf-8") as f:
        json.dump({"when": time.strftime("%Y-%m-%d %H:%M"), "reading": d, "report": md}, f)
    return md


def read_last():
    try:
        with open(os.path.join(OUT_DIR, "last.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def main(argv):
    verb = argv[0] if argv else ""
    if verb == "show":
        last = read_last()
        if not last or not os.path.isfile(last.get("report", "")):
            print("netcheck: no check has run on this PC yet")
            return 1
        print(open(last["report"], encoding="utf-8").read())
        return 0
    if verb != "scan":
        print(__doc__)
        return 2
    d = gather()
    if not d:
        print("NETWORK CHECK: could not read this PC (Windows only; PowerShell did not answer). Nothing was changed.")
        return 2
    last = read_last()
    found = findings(d, last.get("reading"), known_programs(conf()))
    md = write(d, found) if "--no-save" not in argv else ""
    if "--json" in argv:
        print(json.dumps({"findings": found, "report": md}, indent=1))
    else:
        worth = sum(1 for lv, _ in found if lv == WARN)
        print("NETWORK CHECK (read only, nothing changed): %s" % ("%d thing(s) worth a look" % worth if worth
                                                                else "nothing to look at"))
        for lv, text in sorted(found, key=lambda f: (WARN, NOTE, OK).index(f[0])):
            print("  %s %s" % (ICON[lv], text))
        if md:
            print("report: %s" % md)
    return 1 if any(lv == WARN for lv, _ in found) else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
