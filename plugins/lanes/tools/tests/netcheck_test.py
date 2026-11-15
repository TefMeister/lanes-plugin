"""netcheck_test.py - the network check reads only, says what is unsafe in plain words, and from the second check on
says what changed; expected programs are never flagged (0.116.0, 2026-11-15).

Pretend readings (NETCHECK_TEST_GATHER) in a temp folder: nothing on this PC is read or changed. Exit 0 = pass."""
import copy
import json
import os
import subprocess
import sys
import tempfile

T = tempfile.mkdtemp(prefix="netcheck-")
HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(HERE), "netcheck.py")
fails = 0


def check(ok, what):
    global fails
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        fails += 1


SAFE = {
    "processes": ["System", "svchost", "steam", "NodeHelperClient", "NodeHelperService", "rustdesk"],
    "firewall": [{"name": "Domain", "on": True}, {"name": "Private", "on": True}, {"name": "Public", "on": True}],
    "defender": {"realtime": True, "antivirus": True, "age_days": 0, "mode": "Normal"},
    "antivirus": [{"name": "Windows Defender", "on": True, "out_of_date": False}],
    "networks": [{"category": "Public", "adapter": "Ethernet"}],
    "listening": [{"port": 445, "all": True, "program": "System"}, {"port": 27036, "all": True, "program": "steam"},
                  {"port": 9000, "all": True, "program": "NodeHelperService"}],
    "talking_out": [{"program": "steam", "connections": 3}, {"program": "NodeHelperClient", "connections": 1}],
    "inbound_rules": [{"id": "r1", "name": "Steam", "program": "steam.exe", "profile": "Any"}],
    "remote_desktop": False, "remote_assistance": False, "smb1": False,
    "startup": ["Steam"], "last_update": "2099-01-01", "dns": ["192.168.1.1"], "hosts": [],
}
conf = os.path.join(T, "lanes.conf")
with open(conf, "w", encoding="utf-8") as f:
    f.write("netcheck_known = NodeHelper\n")
env = dict(os.environ, LANES_CONFIG=conf, LANES_STATE_DIR=os.path.join(T, "state"))


def run(reading, *args):
    path = os.path.join(T, "reading.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(reading, f)
    r = subprocess.run([sys.executable, TOOL, "scan"] + list(args), env=dict(env, NETCHECK_TEST_GATHER=path),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout + r.stderr


rc, out = run(SAFE)
check(rc == 0 and "nothing to look at" in out, "a safe PC: nothing to look at (exit 0)")
check("first check on this PC" in out, "the first check says it is the starting list")
check("Firewall is on" in out and "antivirus on and up to date" in out, "it says what is fine, too")
check("expected and left alone" in out and "NodeHelperClient" in out, "expected programs are named as expected")
check(os.path.isfile(os.path.join(T, "state", "netcheck", "last.json")), "the reading is kept in this PC's Lanes folder")

rc, out = run(SAFE)
check(rc == 0 and "first check" not in out, "the second check compares, and nothing changed")

bad = copy.deepcopy(SAFE)
bad["firewall"][2]["on"] = False
bad["defender"]["age_days"] = 30
bad["remote_desktop"] = True
bad["smb1"] = True
bad["last_update"] = "2001-01-01"
rc, out = run(bad, "--no-save")
check(rc == 1 and "OFF for Public" in out, "the firewall off for a kind of network is worth a look (exit 1)")
check("30 days old" in out, "old virus definitions are named")
check("Remote Desktop is ON" in out, "Remote Desktop switched on is named")
check("SMB1" in out, "the old SMB1 file sharing is named")
check("no Windows update installed" in out, "no Windows update for a long time is named")

new = copy.deepcopy(SAFE)
new["processes"] += ["anydesk", "NodeHelperUpdater"]
new["listening"].append({"port": 4444, "all": True, "program": "strange"})
new["listening"].append({"port": 9001, "all": True, "program": "NodeHelperUpdater"})
new["inbound_rules"].append({"id": "r2", "name": "", "program": "strange.exe", "profile": "Public"})
new["startup"].append("StrangeUpdater")
new["talking_out"].append({"program": "strange", "connections": 2})
new["dns"] = ["10.9.9.9"]
new["hosts"] = ["1.2.3.4 example.invalid"]
rc, out = run(new, "--no-save")
check(rc == 1 and "NEW since the last check" in out and "strange" in out, "a program newly open to the network is named")
check("NEW openings in the firewall (1): strange.exe" in out, "a new opening in the firewall is named")
check("NEW at Windows start: StrangeUpdater" in out, "a program that newly starts with Windows is named")
check("not before: AnyDesk" in out, "a remote-access program that was not running before is named")
check("name server changed" in out, "a changed name server is named")
check("hosts file changed" in out and "example.invalid" not in out, "a changed hosts file is named, its lines are not")
check("NodeHelperUpdater" not in out.split("expected and left alone")[0], "an expected program is never flagged as new")
check("stop" not in out.lower().replace("windows start", ""), "it never suggests stopping a program")

rc, out = run(SAFE, "--json")
data = json.loads(out)
check(all(len(f) == 2 for f in data["findings"]), "--json gives the findings for other tools")
r = subprocess.run([sys.executable, TOOL, "show"], env=env, capture_output=True, text=True, encoding="utf-8")
check(r.returncode == 0 and "Network check" in r.stdout, "show prints the last report")

print()
print("netcheck_test.py: %s" % ("all passed" if not fails else "%d FAILED" % fails))
sys.exit(1 if fails else 0)
