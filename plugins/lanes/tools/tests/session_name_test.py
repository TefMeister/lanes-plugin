"""session_name_test.py - the desk window naming (hooks/session-name.py, 0.105.1).

Tefa's shape: one window for the PC link, one for dev work. Closing the link window must not leave the next window
numbered after a gap or a duplicate; a new window takes the plain name back when no open window holds it.
Run: python session_name_test.py   (exit 0 = all passed)
"""
import importlib.util
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "..", "..", "hooks", "session-name.py")

tmp = tempfile.mkdtemp(prefix="lanes-session-name-")
os.environ["LANES_STATE_DIR"] = tmp
spec = importlib.util.spec_from_file_location("session_name", HOOK)
sn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sn)

N = "Dev PC desk"
fails = 0


def check(what, got, want):
    global fails
    ok = got == want
    fails += 0 if ok else 1
    print("%s  %s%s" % ("ok  " if ok else "FAIL", what, "" if ok else "  (got %r, want %r)" % (got, want)))


def reset(given=None):
    path = sn.names_file()
    if os.path.exists(path):
        os.remove(path)
    if given is not None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in given.items()}, f)


reset()
check("first window alone takes the plain name", sn.pick_title(N, 100, [100]), N)
check("second window takes 2", sn.pick_title(N, 200, [100, 200]), N + " 2")
# the link window (100) closes; a new one (300) opens while 200 is still open
check("after the first closes, a new window takes the plain name back", sn.pick_title(N, 300, [200, 300]), N)
check("and a fourth takes 3, not a second 2", sn.pick_title(N, 400, [200, 300, 400]), N + " 3")

reset()
# windows opened before the names file existed are counted by start order
check("old windows without a record: start order", sn.pick_title(N, 500, [100, 200, 500]), N + " 3")
reset()
check("a lone window with no record counts as the plain name (known limit: seed desk-names.json once)",
      sn.pick_title(N, 600, [200, 600]), N + " 2")
reset({200: N + " 2"})
check("a recorded '2' with the plain name free: the new window takes the plain name",
      sn.pick_title(N, 700, [200, 700]), N)

ctx = sn.desk_context(N, N + " 2")
check("context says any desk window may get the messages", "ANY desk window" in ctx, True)
check("context names the window", ('"%s 2"' % N) in ctx, True)
check("plain-name context has no 'already holds' line", "already holds" in sn.desk_context(N, N), False)

sys.exit(1 if fails else 0)
