"""switch_off_guard_test.py - every spelling of a bare switch-off is refused (hooks/switch-off-guard.py, 0.118.2).

The fault (Developer PC, 2026-11-11 23:29, 11-19 01:19 and 22:27): sessions switched the PC off through the Bash tool
with Git Bash's doubled slash, `shutdown //s //t 90`, chained after other commands, and the guard let it through, so
the sessions' end steps never ran. Also covered: flags written together, a flag in a variable, a script file that
switches off, and the things that must still pass (a search, a message, `shutdown /a`, the guarded switch-off).
Run: python switch_off_guard_test.py   (exit 0 = all passed)
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "..", "..", "hooks", "switch-off-guard.py")
T = tempfile.mkdtemp(prefix="lanes-switch-off-guard-")
with open(os.path.join(T, "lanes.conf"), "w", encoding="utf-8") as f:
    f.write("shutdown_guard = on\n")
ENV = dict(os.environ, LANES_CONFIG=os.path.join(T, "lanes.conf"), LANES_STATE_DIR=os.path.join(T, "state"))
fails = 0


def hook(cmd, tool="Bash", cwd=T):
    payload = {"tool_name": tool, "tool_input": {"command": cmd}, "cwd": cwd}
    r = subprocess.run([sys.executable, HOOK], input=json.dumps(payload).encode(), capture_output=True, env=ENV)
    return r.returncode, r.stderr.decode(errors="replace")


def check(what, ok):
    global fails
    fails += 0 if ok else 1
    print(("ok    " if ok else "FAIL  ") + what)


REFUSED = [
    ("the 2026-11-19 22:27 command, word for word",
     'python "$HOME/x/handover.py" close 2>&1 | head -1; cd ~/m && git status --short | wc -l && git fetch -q && '
     'git rev-list --count origin/main..HEAD; shutdown //s //t 90 //c "Saved and checked. Shutting down in 90 '
     'seconds." && echo "shutdown set: 90 s"'),
    ("the 2026-11-19 01:19 command", 'python "$T" add a/b --why "x" 2>&1 | tail -2; shutdown //s //t 120 //c '
                                    '"Switching off as Tefa asked: everything is saved." && echo "shutdown in 120 s"'),
    ("the 2026-11-11 command", 'shutdown //s //t 90 //c "Switching off as Tefa asked." && echo "off in 90 s"'),
    ("a doubled-slash restart", "shutdown //r //t 0"),
    ("flags written together", "shutdown /s/t 90"),
    ("a flag in a PowerShell variable", "$a='/s'; shutdown $a /t 90"),
    ("a flag in a cmd variable", "shutdown %FLAG% /t 90"),
    ("a flag from a command", "shutdown $(echo /s) /t 0"),
    ("still: a plain /s", "shutdown /s /t 0"),
    ("still: a dash flag", "shutdown.exe -s -f -t 90"),
    ("still: Start-Process with a list", "Start-Process -FilePath shutdown.exe -ArgumentList @('/s','/t','90')"),
    ("still: cmd /c", 'cmd /c "shutdown /s /t 90"'),
    ("still: Stop-Computer", "Stop-Computer -Force"),
]
for what, cmd in REFUSED:
    rc, err = hook(cmd)
    check("refused: " + what, rc == 2 and "switch_off.py" in err)

PASSED = [
    ("stopping a countdown", "shutdown /a"), ("stopping it, Git Bash spelling", "shutdown //a"),
    ("the guarded switch-off", 'python "$P/tools/switch_off.py" now --wait'),
    ("a search", "grep -n shutdown $FILE"),   # (a search for the whole phrase `shutdown /s` is refused, as before)
    ("a message", "echo shutdown done"), ("a commit message", "git commit -m shutdown-guard"),
    ("a log search", "git log --grep shutdown"), ("a file named so", "cat /tmp/shutdown.log"),
]
for what, cmd in PASSED:
    check("passes: " + what, hook(cmd)[0] == 0)

with open(os.path.join(T, "off.ps1"), "w", encoding="utf-8") as f:
    f.write("Write-Host bye\nshutdown /s /t 0\n")
with open(os.path.join(T, "off.py"), "w", encoding="utf-8") as f:
    f.write("import subprocess\nsubprocess.run(['shutdown', '//s', '//t', '0'])\n")
with open(os.path.join(T, "fine.py"), "w", encoding="utf-8") as f:
    f.write("print('the shutdown guard is on')\n")
rc, err = hook("powershell -File off.ps1", "PowerShell")
check("refused: a PowerShell script that switches off", rc == 2 and "off.ps1" in err)
check("refused: a Python script that switches off", hook("python off.py")[0] == 2)
check("refused: a script named by its full path", hook('& "%s"' % os.path.join(T, "off.ps1"), "PowerShell")[0] == 2)
check("passes: a script that only names a switch-off in words", hook("python fine.py")[0] == 0)
check("passes: Lanes' own guarded switch-off", hook("python %s now --wait" % os.path.join(
    HERE, "..", "switch_off.py"))[0] == 0)
check("passes: a script that is not there", hook("python missing.py")[0] == 0)
check("only shell commands are looked at", hook("shutdown //s", tool="Read")[0] == 0)
with open(os.path.join(T, "lanes.conf"), "w", encoding="utf-8") as f:
    f.write("shutdown_guard = off\n")
check("switched off, it lets everything through", hook("shutdown //s //t 0")[0] == 0)
check("bad input passes (never fails closed)",
      subprocess.run([sys.executable, HOOK], input=b"not json", capture_output=True, env=ENV).returncode == 0)
sys.exit(1 if fails else 0)
