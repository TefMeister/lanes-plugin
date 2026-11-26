"""hidden_test.py - the flags hidden.py gives a child, and window-scan.py's verdicts (0.125.1). No window is opened."""
import importlib.util
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
import hidden  # noqa: E402

spec = importlib.util.spec_from_file_location("window_scan", os.path.join(TOOLS, "window-scan.py"))
ws = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ws)
failed = 0
n = 0


def check(what, cond):
    global failed, n
    n += 1
    if not cond:
        failed += 1
        print("FAIL", what)


if os.name == "nt":
    real = hidden.has_console
    hidden.has_console = lambda: False
    check("no console: the child gets a hidden one", hidden.flags({})["creationflags"] & hidden.NO_WINDOW)
    f = hidden.flags({"creationflags": hidden.DETACHED | hidden.NEW_GROUP})["creationflags"]
    check("DETACHED is swapped for a hidden console", not f & hidden.DETACHED and f & hidden.NO_WINDOW and f & hidden.NEW_GROUP)
    check("a console asked for on purpose is left alone",
          hidden.flags({"creationflags": hidden.NEW_CONSOLE})["creationflags"] == hidden.NEW_CONSOLE)
    check("visible=True is left alone and never reaches subprocess", hidden.flags({"visible": True}) == {})
    hidden.has_console = lambda: True
    check("with a console the child shares it, as before", "creationflags" not in hidden.flags({}))
    f = hidden.flags({"creationflags": hidden.DETACHED})["creationflags"]
    check("DETACHED is swapped even with a console", f == hidden.NO_WINDOW)
    hidden.has_console = real
    check("this test (a console program) has a console", hidden.has_console())
check("python_exe is never pythonw when python.exe is there",
      os.path.basename(hidden.python_exe()).lower() != "pythonw.exe" or not os.path.isfile(
          os.path.join(os.path.dirname(sys.executable), "python.exe")))

with tempfile.TemporaryDirectory() as d:
    def scan(src, name="tool.py"):
        p = os.path.join(d, name)
        open(p, "w", encoding="utf-8").write(src)
        return ws.scan_file(p)
    check("subprocess.run is caught", scan("import subprocess\nsubprocess.run(['git'])\n"))
    check("a multi-line Popen is caught", scan("import subprocess\nsubprocess.Popen(\n  ['x'],\n  cwd='.')\n"))
    check("an alias is caught", scan("import subprocess as sp\nsp.check_output(['x'])\n"))
    check("from subprocess import run is caught", scan("from subprocess import run\nrun(['x'])\n"))
    check("os.system is caught", scan("import os\nos.system('x')\n"))
    check("hidden.run passes", not scan("import hidden\nhidden.run(['git'])\n"))
    check("subprocess.DEVNULL alone passes", not scan("import subprocess\nx = subprocess.DEVNULL\n"))
    check("a marked line passes", not scan("import os\nos.startfile(x)  # window-ok: the game\n"))
check("the plugin itself is clean", not ws.scan(os.path.dirname(TOOLS)))
print("hidden_test: %d of %d checks pass" % (n - failed, n))
sys.exit(1 if failed else 0)
