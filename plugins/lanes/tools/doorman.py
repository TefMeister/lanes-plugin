#!/usr/bin/env python3
"""doorman.py - open, list and politely close Claude sessions, on the other PC or on this one (0.108.0, 2026-11-11).

Asked for by the maintainer: "i need you to be able to open and close sessions" on the other PC, so the PC that
does the building is always linked to the PC that keeps GitHub (the Keeper, tools/keeper.py). A remote-desktop
program only gives a picture and a mouse; this is the proper door. With the Keeper on the SAME PC (`keeper_mode =
this_pc`) the same verbs are used with --local, and nothing listens on any network. On or off: `keeper`.

ON THE PC THAT IS REACHED (the Keeper), once:
    python doorman.py install          start the doorman at every logon (a Startup shortcut, no admin), start it now,
                                       and print the ONE firewall command that needs an administrator window
    python doorman.py serve            run the doorman in this window (what the Startup shortcut runs, hidden)
    python doorman.py uninstall        take the Startup shortcut away and stop the doorman

FROM THE OTHER PC (the Developer PC):
    python doorman.py status           is the doorman there, which PC is it, how many Claude sessions are open
    python doorman.py list             the open Claude sessions: process number, when started, the name it was given
    python doorman.py open [name]      open a Claude window from the terminal shortcut, named <name> (default from conf)
    python doorman.py close <pid>      type /exit into that session and wait until it is gone; NEVER kills
    python doorman.py ensure           status; when no session is open there, open one. One line. For session start.
    python doorman.py receive          have the other PC take the waiting parcels NOW (it also looks by itself)
  Add --local to list / open / close to act on THIS PC without the network (how the tool is tested).

SETTINGS (~/.claude/lanes.conf; nothing secret, nothing goes to GitHub):
    doorman_port     = 47600                     both PCs
    doorman_bind     = <this PC's private-link address>          server; default: the first 100.x address found
    doorman_allow    = <address>[, <address>]    server: the ONLY callers answered (the other PC's private-link address)
    doorman_shortcut = <path to the terminal .lnk>               server; default: Lanes.lnk on the Desktop
    doorman_name     = Keeper link               server: the name new windows get
    doorman_peer     = <address>                 client: where the other PC's doorman is
    parcel_watch     = 60                        server: look for parcels every so many seconds and take them
                                                 (tools/parcel.py receive: check, upload, receipt). 0 or absent = off.
                                                 A plain program does this; no Claude session is needed or used.

SAFETY
  - It answers only the addresses in doorman_allow, and listens only on the private link (the link itself proves who
    the caller is, so there is no password to leak). The firewall rule narrows it once more.
  - Five fixed verbs. It cannot run a command it is handed: `open` starts the one configured shortcut, `close`
    types the fixed text /exit into a process that must be claude.exe, `receive` runs the one program parcel.py
    (beside this file) with the one word receive.
  - `close` is polite: Claude Code runs its own end steps on /exit. A session that does not leave is reported, not
    killed. Ask it to save first (a message), close it when it is idle.
"""
import ctypes
import ctypes.wintypes as W
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOME = os.path.expanduser("~")
CONF = os.environ.get("LANES_CONFIG") or os.path.join(HOME, ".claude", "lanes.conf")
STATE_DIR = os.environ.get("LANES_STATE_DIR") or os.path.join(HOME, ".claude", "lanes")
STATE = os.path.join(STATE_DIR, "doorman-state.json")
LOG = os.path.join(STATE_DIR, "doorman.log")
FIREWALL_RULE = "Lanes doorman - private link only"
SESSION_EXE = "claude.exe"
TERMINAL_PROGRAMS = {"windowsterminal.exe", "openconsole.exe", "conhost.exe", "cmd.exe", "powershell.exe",
                     "pwsh.exe", "wt.exe"}
ANCESTORS_LOOKED_AT = 6
DEFAULT_PORT = 47600
DEFAULT_NAME = "Keeper link"
PRIVATE_LINK_PREFIX = "100."            # the private link's addresses (100.64.0.0/10)
PRIVATE_LINK_RANGE = "100.64.0.0/10"
EXIT_TEXT = "/exit"
OPEN_WAIT_S = 30.0                      # how long a new session may take to appear
RECEIVE_WAIT_S = 900.0                  # a big parcel's upload may take this long
CLOSE_WAIT_S = 60.0                     # how long /exit (with its end steps) may take
SETTLE_S = 5.0                          # a new session's short-lived helpers are gone by then
TYPE_PAUSE_S = 0.4                      # between the text and Enter, so it is not taken for a paste
HTTP_TIMEOUT_S = 8.0
STARTUP_LNK = "Lanes doorman.lnk"
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008


# ----- settings, log, state -----
def conf():
    out = {}
    try:
        with open(CONF, encoding="utf-8") as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                if "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip()
    except OSError:
        pass
    return out


def expand(p):
    return os.path.normpath(os.path.expandvars(os.path.expanduser(p)))


def log(msg):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


def read_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"opened": {}}


def write_state(st):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=1)
    os.replace(tmp, STATE)


def port():
    try:
        return int(conf().get("doorman_port", DEFAULT_PORT))
    except ValueError:
        return DEFAULT_PORT


# ----- sessions on this PC -----
class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("th32ProcessID", W.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", W.DWORD), ("cntThreads", W.DWORD),
                ("th32ParentProcessID", W.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", W.DWORD),
                ("szExeFile", W.WCHAR * 260)]


def processes():
    """every process on the PC: {pid: (parent pid, program name in small letters)}"""
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateToolhelp32Snapshot.restype = W.HANDLE
    snap = k.CreateToolhelp32Snapshot(0x2, 0)                             # TH32CS_SNAPPROCESS
    out, e = {}, PROCESSENTRY32W()
    e.dwSize = ctypes.sizeof(e)
    ok = k.Process32FirstW(W.HANDLE(snap), ctypes.byref(e))
    while ok:
        out[e.th32ProcessID] = (e.th32ParentProcessID, e.szExeFile.lower())
        ok = k.Process32NextW(W.HANDLE(snap), ctypes.byref(e))
    k.CloseHandle(W.HANDLE(snap))
    return out


def session_pids():
    """Claude Code sessions that sit in a terminal window. The Claude DESKTOP APP is also called claude.exe and runs
    eight or so helpers of that name (found 2026-11-11: 10 "sessions" listed with 2 windows open); those are not
    sessions and must never be typed into. A session is a claude.exe whose nearest ancestor that is a terminal
    program or another claude.exe is a TERMINAL program."""
    procs = processes()
    found = []
    for pid, (parent, name) in procs.items():
        if name != SESSION_EXE:
            continue
        seen = 0
        while parent in procs and seen < ANCESTORS_LOOKED_AT:
            up_parent, up_name = procs[parent]
            if up_name == SESSION_EXE:
                break                                                     # a helper of the app, or of a session
            if up_name in TERMINAL_PROGRAMS:
                found.append(pid)
                break
            parent, seen = up_parent, seen + 1
    return sorted(found)


def started_at(pid):
    """when a process started, as 'YYYY-MM-DD HH:MM', or '' when it cannot be read"""
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x1000, False, pid)                # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    made, a, b, c = W.FILETIME(), W.FILETIME(), W.FILETIME(), W.FILETIME()
    ok = k.GetProcessTimes(h, ctypes.byref(made), ctypes.byref(a), ctypes.byref(b), ctypes.byref(c))
    k.CloseHandle(h)
    if not ok:
        return ""
    ticks = (made.dwHighDateTime << 32) | made.dwLowDateTime          # 100 ns steps since 1601
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ticks / 1e7 - 11644473600))


def list_sessions():
    st = read_state()
    live = session_pids()
    opened = {k: v for k, v in st.get("opened", {}).items() if int(k) in live}
    if opened != st.get("opened"):
        st["opened"] = opened
        write_state(st)
    return [{"pid": p, "started": started_at(p), "name": opened.get(str(p), {}).get("name", ""),
             "by_doorman": str(p) in opened} for p in live]


# ----- open -----
def read_shortcut(path):
    """target, arguments and start folder of a .lnk (Windows Script Host, the way Windows itself reads it)"""
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:DOORMAN_LNK);"
          "@{target=$s.TargetPath;args=$s.Arguments;dir=$s.WorkingDirectory}|ConvertTo-Json -Compress")
    env = dict(os.environ, DOORMAN_LNK=path)
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, env=env,
                         creationflags=CREATE_NO_WINDOW).stdout.strip()
    return json.loads(out) if out else {}


def clean_name(name):
    return re.sub(r"[^A-Za-z0-9 _-]", "", name or "").strip()[:40]


def open_session(name=""):
    c = conf()
    lnk = expand(c.get("doorman_shortcut", os.path.join(HOME, "Desktop", "Lanes.lnk")))
    if not os.path.isfile(lnk):
        return {"ok": False, "error": "no terminal shortcut at the configured place (doorman_shortcut in lanes.conf)"}
    name = clean_name(name) or clean_name(c.get("doorman_name", DEFAULT_NAME))
    before = set(session_pids())
    sc = read_shortcut(lnk)
    target, args = sc.get("target", ""), (sc.get("args", "") or "").strip()
    named = False
    taken = {v.get("name") for k, v in read_state().get("opened", {}).items() if int(k) in before}
    base, n = name, 1
    while name in taken:                                  # two windows never share a name
        n += 1
        name = "%s %d" % (base, n)
    m = re.search(r"(^|\s)claude(\s.*)?$", args)
    if target.lower().endswith("wt.exe") and m and name:
        # the same terminal profile and folder as the icon; only Claude's own part gets the name: any name the icon
        # carries (--remote-control "<name>") is replaced by this window's own
        head = args[:m.start()].strip()
        tail = re.sub(r'\s--remote-control(\s+("[^"]*"|[^-\s]\S*))?', "", m.group(2) or "")
        cmd = '"%s" %s claude%s --remote-control "%s"' % (target, head, tail, name)
        subprocess.Popen(cmd, cwd=sc.get("dir") or None, creationflags=DETACHED_PROCESS)
        named = True
    else:
        os.startfile(lnk)                                 # an icon of another shape: start it exactly as it is
    deadline = time.time() + OPEN_WAIT_S
    while time.time() < deadline:
        new = sorted(set(session_pids()) - before)
        if new:
            # a starting session shows short-lived helper processes too: wait, then take the one that stayed,
            # the earliest started when more than one did
            time.sleep(SETTLE_S)
            stayed = sorted(set(session_pids()) - before, key=lambda p: (started_at(p), p))
            if not stayed:
                continue
            pid = stayed[0]
            st = read_state()
            st.setdefault("opened", {})[str(pid)] = {"name": name if named else "", "at": time.strftime("%Y-%m-%d %H:%M")}
            write_state(st)
            log("opened pid %d name %r" % (pid, name if named else ""))
            return {"ok": True, "pid": pid, "name": name if named else "", "named": named}
        time.sleep(0.5)
    log("open: no new session appeared")
    return {"ok": False, "error": "the shortcut was started but no new Claude session appeared in %d s" % OPEN_WAIT_S}


# ----- close: type /exit into the session's own console -----
class KEY_EVENT_RECORD(ctypes.Structure):
    _fields_ = [("bKeyDown", W.BOOL), ("wRepeatCount", W.WORD), ("wVirtualKeyCode", W.WORD),
                ("wVirtualScanCode", W.WORD), ("UnicodeChar", W.WCHAR), ("dwControlKeyState", W.DWORD)]


class INPUT_RECORD(ctypes.Structure):
    _fields_ = [("EventType", W.WORD), ("Event", KEY_EVENT_RECORD)]


def type_into(pid, text, enter=True):
    """type text (then Enter) into the console a process sits in. Run in a process of its own: it leaves its console."""
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateFileW.restype = W.HANDLE
    k.FreeConsole()
    if not k.AttachConsole(pid):
        return "could not reach that session's console (error %d)" % ctypes.get_last_error()
    h = k.CreateFileW("CONIN$", 0xC0000000, 3, None, 3, 0, None)        # read+write, shared, open existing
    if h in (None, W.HANDLE(-1).value):
        return "could not open that console's input (error %d)" % ctypes.get_last_error()

    def send(chars, vk=0):
        recs = (INPUT_RECORD * (2 * len(chars)))()
        for i, ch in enumerate(chars):
            for j, down in enumerate((True, False)):
                r = recs[2 * i + j]
                r.EventType = 1                                           # KEY_EVENT
                r.Event.bKeyDown, r.Event.wRepeatCount = down, 1
                r.Event.wVirtualKeyCode, r.Event.UnicodeChar = vk, ch
        done = W.DWORD()
        return bool(k.WriteConsoleInputW(h, recs, len(recs), ctypes.byref(done))) and done.value == len(recs)

    ok = send(text)
    if ok and enter:
        time.sleep(TYPE_PAUSE_S)
        ok = send("\r", vk=0x0D)
    k.CloseHandle(h)
    k.FreeConsole()
    return "" if ok else "the keys were not taken"


def close_session(pid):
    if pid == os.getpid() or pid not in session_pids():
        return {"ok": False, "error": "process %d is not an open Claude session on this PC" % pid}
    p = subprocess.run([sys.executable, os.path.abspath(__file__), "_type", str(pid)], capture_output=True, text=True,
                       creationflags=CREATE_NO_WINDOW)
    problem = (p.stdout + p.stderr).strip()
    if p.returncode != 0:
        log("close %d: %s" % (pid, problem))
        return {"ok": False, "error": problem or "could not type into that session"}
    deadline = time.time() + CLOSE_WAIT_S
    while time.time() < deadline:
        if pid not in session_pids():
            log("closed pid %d" % pid)
            return {"ok": True, "pid": pid, "closed": True}
        time.sleep(0.5)
    log("close %d: still running" % pid)
    return {"ok": False, "pid": pid, "closed": False,
            "error": "/exit was typed but the session is still there after %d s (busy, or waiting for an answer); not killed" % CLOSE_WAIT_S}


# ----- parcels: the Keeper takes what the Developer PC handed over -----
PARCEL_LOCK = threading.Lock()


def parcels_waiting():
    """how many parcels sit in the outbox without a final answer"""
    t = conf().get("transfer", "")
    box = os.path.join(expand(t), "parcels") if t else ""
    if not box or not os.path.isdir(os.path.join(box, "outbox")):
        return 0
    n = 0
    for name in os.listdir(os.path.join(box, "outbox")):
        if name.endswith(".json"):
            try:
                with open(os.path.join(box, "receipts", name), encoding="utf-8") as f:
                    if json.load(f).get("status") == "refused":
                        continue                                          # answered; the sender sends a new one
            except (OSError, ValueError):
                pass
            n += 1
    return n


def receive_parcels():
    """run parcel.py receive (one at a time) and hand back what it printed"""
    tool = os.path.join(os.path.dirname(os.path.abspath(__file__)), "parcel.py")
    if not os.path.isfile(tool):
        return {"ok": False, "error": "parcel.py is not beside the doorman"}
    with PARCEL_LOCK:
        py = os.path.join(os.path.dirname(sys.executable), "python.exe")
        p = subprocess.run([py if os.path.isfile(py) else sys.executable, tool, "receive"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=RECEIVE_WAIT_S,
                           creationflags=CREATE_NO_WINDOW)
    lines = [l for l in (p.stdout + p.stderr).splitlines() if l.strip()]
    for l in lines:
        log(l)
    return {"ok": p.returncode == 0, "lines": lines[-20:], "waiting": parcels_waiting()}


def watch_parcels():
    try:
        every = float(conf().get("parcel_watch", 0) or 0)
    except ValueError:
        every = 0
    if every <= 0:
        return
    log("watching for parcels every %d s" % every)
    while True:
        time.sleep(every)
        try:
            if parcels_waiting():
                receive_parcels()
        except Exception as e:                                             # the watcher must outlive one bad parcel
            log("parcel watcher: %r" % (e,))


# ----- the doorman itself -----
def machine():
    c = conf()
    return {"machine": c.get("machine_name", ""), "role": c.get("role", "")}


def own_private_address():
    c = conf().get("doorman_bind", "")
    if c:
        return c
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            if info[4][0].startswith(PRIVATE_LINK_PREFIX):
                return info[4][0]
    except OSError:
        pass
    return ""


class Door(BaseHTTPRequestHandler):
    server_version = "doorman"

    def log_message(self, *a):
        pass

    def answer(self, code, body):
        data = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def allowed(self):
        allow = [a.strip() for a in conf().get("doorman_allow", "").split(",") if a.strip()]
        who = self.client_address[0]
        if who in allow:
            return True
        log("REFUSED a caller that is not on the list: " + who)
        self.answer(403, {"ok": False, "error": "not on the doorman's list"})
        return False

    def do_GET(self):
        if not self.allowed():
            return
        if self.path == "/status":
            self.answer(200, dict(machine(), ok=True, sessions=len(session_pids()),
                                  parcels_waiting=parcels_waiting()))
        elif self.path == "/list":
            self.answer(200, {"ok": True, "sessions": list_sessions()})
        else:
            self.answer(404, {"ok": False, "error": "unknown"})

    def do_POST(self):
        if not self.allowed():
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except ValueError:
            body = {}
        if self.path == "/open":
            self.answer(200, open_session(str(body.get("name", ""))))
        elif self.path == "/receive":
            self.answer(200, receive_parcels())
        elif self.path == "/close":
            try:
                self.answer(200, close_session(int(body.get("pid"))))
            except (TypeError, ValueError):
                self.answer(400, {"ok": False, "error": "close needs a process number"})
        else:
            self.answer(404, {"ok": False, "error": "unknown"})


def serve():
    addr = own_private_address()
    if not addr:
        print("doorman: this PC has no private-link address (100.x); set doorman_bind in lanes.conf")
        return 1
    if not conf().get("doorman_allow"):
        print("doorman: doorman_allow is not set in lanes.conf; it would answer nobody")
        return 1
    try:
        srv = ThreadingHTTPServer((addr, port()), Door)
    except OSError as e:
        print("doorman: could not listen (%s); is one already running?" % e)
        return 1
    log("listening on the private link, port %d" % port())
    threading.Thread(target=watch_parcels, daemon=True).start()
    print("doorman: listening on the private link, port %d" % port())
    srv.serve_forever()


# ----- install on the PC that is reached -----
def startup_lnk():
    return os.path.join(os.environ.get("APPDATA", HOME), "Microsoft", "Windows", "Start Menu", "Programs", "Startup",
                        STARTUP_LNK)


def pythonw():
    cand = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return cand if os.path.isfile(cand) else sys.executable


def install():
    lnk, me = startup_lnk(), os.path.abspath(__file__)
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:DOORMAN_LNK);$s.TargetPath=$env:DOORMAN_PY;"
          "$s.Arguments='\"'+$env:DOORMAN_ME+'\" serve';$s.WindowStyle=7;$s.Description='Lanes doorman';$s.Save()")
    env = dict(os.environ, DOORMAN_LNK=lnk, DOORMAN_PY=pythonw(), DOORMAN_ME=me)
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], env=env, creationflags=CREATE_NO_WINDOW)
    if not os.path.isfile(lnk):
        print("doorman: could not make the Startup shortcut")
        return 1
    subprocess.Popen([pythonw(), me, "serve"], creationflags=DETACHED_PROCESS)
    print("doorman: starts at every logon from now on, and is started now.")
    have = subprocess.run(["netsh", "advfirewall", "firewall", "show", "rule", "name=" + FIREWALL_RULE],
                          capture_output=True, creationflags=CREATE_NO_WINDOW).returncode == 0
    if have:
        print("The firewall rule is in already; nothing else to do.")
        return 0
    print("ONE step needs an administrator window (it lets the other PC through the firewall, private link only):")
    print('  netsh advfirewall firewall add rule name="%s" dir=in action=allow '
          'protocol=TCP localport=%d remoteip=%s' % (FIREWALL_RULE, port(), PRIVATE_LINK_RANGE))
    return 0


def uninstall():
    try:
        os.remove(startup_lnk())
    except OSError:
        pass
    # only python programs are looked at, so the search never matches (and stops) the program doing the searching
    ps = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and "
          "$_.CommandLine -like '*doorman.py*serve*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], creationflags=CREATE_NO_WINDOW)
    print("doorman: Startup shortcut removed and the doorman stopped. The firewall rule stays until removed by hand.")
    return 0


# ----- the caller's side -----
def call(path, body=None):
    peer = conf().get("doorman_peer", "")
    if not peer:
        return {"ok": False, "error": "doorman_peer is not set in lanes.conf (the other PC's private-link address)"}
    url = "http://%s:%d%s" % (peer, port(), path)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    wait = HTTP_TIMEOUT_S + {"/open": OPEN_WAIT_S + SETTLE_S, "/close": CLOSE_WAIT_S,
                             "/receive": RECEIVE_WAIT_S}.get(path, 0)
    try:
        with urllib.request.urlopen(req, timeout=wait) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except ValueError:
            return {"ok": False, "error": "the doorman answered %d" % e.code}
    except (urllib.error.URLError, OSError, ValueError) as e:
        return {"ok": False, "unreachable": True, "error": "the other PC's doorman did not answer (%s)" %
                getattr(e, "reason", e)}


def show_list(r):
    if not r.get("ok"):
        print("doorman: " + r.get("error", "failed"))
        return 1
    if not r["sessions"]:
        print("no Claude session is open there")
    for s in r["sessions"]:
        print("  pid %-6d started %s  %s" % (s["pid"], s["started"] or "?", s["name"] or "(opened by hand)"))
    return 0


def main(argv):
    local = "--local" in argv
    argv = [a for a in argv if a != "--local"]
    verb = argv[0] if argv else ""
    if verb == "_type":                                   # the helper close_session starts; not for people
        problem = type_into(int(argv[1]), EXIT_TEXT)
        if problem:
            print(problem)
        return 1 if problem else 0
    if verb == "serve":
        return serve() or 0
    if verb == "install":
        return install()
    if verb == "uninstall":
        return uninstall()
    if verb == "status":
        r = call("/status")
        if not r.get("ok"):
            print("doorman: " + r.get("error", "failed"))
            return 1
        print("doorman: %s (%s) is there, %d Claude session(s) open" % (r.get("machine"), r.get("role"), r["sessions"]))
        return 0
    if verb == "list":
        return show_list({"ok": True, "sessions": list_sessions()} if local else call("/list"))
    if verb == "open":
        name = " ".join(argv[1:])
        r = open_session(name) if local else call("/open", {"name": name})
        print("doorman: opened a session, pid %d%s" % (r["pid"], ", named '%s'" % r["name"] if r.get("name") else "")
              if r.get("ok") else "doorman: " + r.get("error", "failed"))
        return 0 if r.get("ok") else 1
    if verb == "close" and len(argv) > 1 and argv[1].isdigit():
        r = close_session(int(argv[1])) if local else call("/close", {"pid": int(argv[1])})
        print("doorman: session %s closed" % argv[1] if r.get("ok") else "doorman: " + r.get("error", "failed"))
        return 0 if r.get("ok") else 1
    if verb == "receive":
        r = call("/receive", {})
        print("\n".join(r.get("lines") or [r.get("error", "nothing came back")]))
        return 0 if r.get("ok") else 1
    if verb == "ensure":
        r = call("/status")
        if not r.get("ok"):
            print("LINK: the other PC is not reachable (%s). Carry on; hand-overs wait." % r.get("error", "?"))
            return 1
        if r["sessions"]:
            print("LINK: %s is there with %d session(s) open." % (r.get("machine"), r["sessions"]))
            return 0
        o = call("/open", {"name": ""})
        print("LINK: %s had no session open; opened one (pid %s)." % (r.get("machine"), o.get("pid")) if o.get("ok")
              else "LINK: %s is there but a session could not be opened (%s)." % (r.get("machine"), o.get("error")))
        return 0 if o.get("ok") else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
