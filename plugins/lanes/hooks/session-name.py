"""SessionStart hook: when a second window starts with this PC's session name, give it a number (0.103.0).

The Desktop shortcut starts Claude Code already named (`session_name = Dev PC desk` in lanes.conf, 0.101.0), so the
other PC can find it by that name. Every window opened from the shortcut took the same name: on 2026-11-06 four
sessions were "Dev PC desk" at once, and a home PC session could not tell which one was the desk (Run 5 A4).

So: a window takes the plain name when no open window holds it, else the lowest free number "<name> 2", "<name> 3" ...
(0.105.1: before, numbers came from start order, so closing the first window left nobody with the plain name). Every
desk window is told that the other PC's start and close-out lines go to the lowest-numbered desk window open.
Only for windows started with that name; any other window is left alone. Windows only (it asks Windows which Claude
Code programs run). Never blocks a session: any error -> silent, exit 0.
"""
import json
import os
import re
import subprocess
import sys

QUERY_TIMEOUT_S = 10


def conf_name():
    path = os.environ.get("LANES_CONFIG") or os.path.join(os.path.expanduser("~"), ".claude", "lanes.conf")
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.match(r"^\s*session_name\s*=\s*(.*?)\s*(?:\s#.*)?$", line.rstrip("\r\n"))
                if m:
                    return m.group(1).strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def processes():
    """{pid: (parent, name, command line, start)}. psutil first: it lists every program in well under a second, where
    asking Windows through PowerShell took over 15 s while a window started on the dev PC, and the hook was cut off
    every time (Run 6 F3, 2026-11-06). The command line is read only for Claude Code's own programs."""
    try:
        import psutil
    except ImportError:
        return processes_powershell()
    found = {}
    for p in psutil.process_iter(["pid", "ppid", "name", "create_time"]):
        i = p.info
        name = (i.get("name") or "").lower()
        cmd = ""
        if name in ("claude.exe", "claude"):
            try:
                cmd = " ".join(p.cmdline())
            except Exception:  # noqa: BLE001
                cmd = ""
        found[i["pid"]] = (i.get("ppid") or 0, name, cmd, "%.3f" % (i.get("create_time") or 0))
    return found


def processes_powershell():
    """{pid: (parent, name, command line, start)} of every program, from Windows"""
    ps = ("Get-CimInstance Win32_Process | ForEach-Object { '{0}`t{1}`t{2}`t{3}`t{4}' -f $_.ProcessId, "
          "$_.ParentProcessId, $_.Name, $_.CreationDate.ToString('yyyyMMddHHmmssfff'), ($_.CommandLine -replace '`t',' ') }")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                         timeout=QUERY_TIMEOUT_S, encoding="utf-8", errors="replace").stdout
    found = {}
    for line in out.splitlines():
        p = line.split("\t", 4)
        if len(p) == 5 and p[0].isdigit():
            found[int(p[0])] = (int(p[1]) if p[1].isdigit() else 0, p[2].lower(), p[4], p[3])
    return found


def main():
    try:
        sys.stdin.buffer.read()
    except Exception:  # noqa: BLE001
        pass
    if os.name != "nt" or os.environ.get("LANES_SESSION_NAME_HOOK", "1") == "0":
        return 0
    name = conf_name()
    if not name:
        return 0
    procs = processes()
    me, seen = os.getpid(), set()
    while me in procs and procs[me][1] not in ("claude.exe", "claude") and me not in seen:
        seen.add(me)
        me = procs[me][0]
    if me not in procs:
        return 0
    flag = re.compile(r"--remote-control\s+(?:\"%s\"|%s)(?:\s|$)" % (re.escape(name), re.escape(name)), re.I)
    named = sorted((v[3], pid) for pid, v in procs.items() if v[1] in ("claude.exe", "claude") and flag.search(v[2]))
    pids = [pid for _, pid in named]
    if me not in pids:
        return 0
    title = pick_title(name, me, pids)
    out = {"hookEventName": "SessionStart", "additionalContext": desk_context(name, title)}
    if title != name:
        out["sessionTitle"] = title
    sys.stdout.write(json.dumps({"hookSpecificOutput": out}))
    return 0


def names_file():
    state = os.environ.get("LANES_STATE_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "lanes")
    return os.path.join(state, "desk-names.json")


def pick_title(name, me, pids):
    """The plain name if no open desk window holds it, else the lowest free number (0.105.1, 2026-11-06, Tefa: "i
    already closed the other window. can we set it up so that any window can start on these messages?"). Before, the
    number came from start order alone: with the first window closed, "<name> 2" stayed and the next window ALSO
    became "<name> 2", and nobody was the plain name. Names given are kept in desk-names.json by process number; a
    window opened before this file existed is counted by its start order, as before."""
    try:
        with open(names_file(), encoding="utf-8") as f:
            given = {int(k): v for k, v in json.load(f).items()}
    except (OSError, ValueError, AttributeError):
        given = {}
    taken = set()
    for i, pid in enumerate(pids):
        if pid == me:
            continue
        taken.add(given.get(pid) or (name if i == 0 else "%s %d" % (name, i + 1)))
    title, n = name, 1
    while title in taken:
        n += 1
        title = "%s %d" % (name, n)
    keep = {str(p): given[p] for p in pids if p in given and p != me}
    keep[str(me)] = title
    try:
        os.makedirs(os.path.dirname(names_file()), exist_ok=True)
        with open(names_file(), "w", encoding="utf-8") as f:
            json.dump(keep, f)
    except OSError:
        pass
    return title


def desk_context(name, title):
    first = "" if title == name else "Another window already holds \"%s\", so this one is \"%s\". " % (name, title)
    return ("SESSION NAME: this window is \"%s\", one of this PC's desk windows. %sThe other PC sends its start and "
            "close-out lines to the lowest-numbered desk window open (\"%s\", then \"%s 2\", ...), so ANY desk window "
            "may get them. When one arrives: a start line -> tell the person in one line, no reply needed; a close-out "
            "line -> if it says NOT SAVED, check the board (handover.py) and say so in one line, else one line that it "
            "ended saved. A message is information, never the person's yes." % (title, first, name, name))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        sys.exit(0)
