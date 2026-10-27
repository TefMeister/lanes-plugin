"""vb_learn - the learning hour: the stage machine that runs VR Bench's stages on one game, in order.

Each stage ends PASS (seen to work, with the picture that shows it), CHECK (did something, not sure it is right) or
UNKNOWN (could not try), and is recorded in the run's run.json the moment it ends. The run stops at the time limit,
at a refusal (pre-flight found something missing) or at an error; whatever happens, the claim on the game and the
layer are released and the debrief is written (`finally`).

Every outside action goes through `tools` (vb_tools.Tools on a real PC, a fake in the tests), so the machine can be
tested with no game, no simulator and no headset.
"""
import os
from collections import namedtuple

STAGES = ["preflight", "launch", "menus", "flat", "vr_head", "vr_hands", "vr_body", "vr_buttons", "report"]
ALWAYS = ("preflight", "report")
NEEDS_SCREEN_LINE = "this game needs the screen for the flat stages until plan 2 (keys still go in through the front)"

Verdict = namedtuple("Verdict", "name result how picture")


class Refused(Exception):
    """pre-flight found something missing; the text says what, in plain words"""


class Learn:
    def __init__(self, game, minutes, stages, tier, run, tools, exe=None):
        self.game, self.minutes, self.tier, self.run, self.tools, self.exe = game, minutes, tier, run, tools, exe
        wanted = set(stages) if stages else set(STAGES)
        self.stages = [s for s in STAGES if s in wanted or s in ALWAYS]
        self.known_added = []
        self.verdicts = []
        self.notes = []

    # ---- helpers the stages use ----
    def known_add(self, section, text):
        self.tools.known_add(section, text)
        self.known_added.append(f"{section}: {text}")

    def verdict(self, name, result, how, picture=None):
        return Verdict(name, result, how, picture)

    # ---- the machine ----
    def run_all(self):
        import vb_stages_flat as F
        import vb_stages_body as B
        import vb_stages_vr as V
        funcs = {"preflight": preflight, "launch": F.launch, "menus": F.menus, "flat": F.flat,
                 "vr_head": V.vr_head, "vr_hands": V.vr_hands, "vr_body": B.vr_body, "vr_buttons": V.vr_buttons, "report": report}
        started = self.tools.now()
        reason = None
        try:
            for name in self.stages:
                if name == "report":
                    break
                if self.tools.now() - started > self.minutes * 60:
                    reason = "time"
                    break
                v = funcs[name](self)
                self.verdicts.append(v)
                self.run.stage(v.name, v.result, v.how, v.picture)
            if reason is None and "report" in self.stages:
                v = report(self)
                self.verdicts.append(v)
                self.run.stage(v.name, v.result, v.how, v.picture)
            reason = reason or "done"
        except Refused as e:
            reason = str(e)
        except Exception as e:   # anything at all: the finally below must still release the game
            reason = f"error: {type(e).__name__}: {e}"
        finally:
            for undo in (self.tools.layer_stop, lambda: self.tools.claim(False)):
                try:
                    undo()
                except Exception as e:
                    self.notes.append(f"could not undo: {e}")
            if reason != "done":
                write_debrief(self, reason)
            self.run.finish(reason)
        return {"reason": reason, "stages": [v._asdict() for v in self.verdicts], "folder": self.run.folder}


# ---- the two stages that always run -------------------------------------------------------------------------------
def preflight(L):
    t = L.tools
    if not t.sim_installed():
        raise Refused("simulator not on this PC: install it with `openxr-sim.py install --fork`")
    try:
        L.exe = L.exe or t.resolve_exe(L.game)
    except LookupError as e:
        raise Refused(f"game program not found: {e}")
    try:
        known = t.known()
    except OSError as e:
        raise Refused(f"KNOWN.md could not be read or made: {e}")
    t.claim(True)
    t.profile()
    t.layer_start(L.exe)
    L.notes.append(NEEDS_SCREEN_LINE)
    if not _has_music_line(known):
        return L.verdict("preflight", "CHECK", "ready; the game's music switch is not known yet (KNOWN.md Controls)")
    return L.verdict("preflight", "PASS", "ready: simulator, game, KNOWN.md, claim and layer")


def _has_music_line(known):
    in_controls = False
    for line in known.splitlines():
        if line.startswith("## "):
            in_controls = line.strip() == "## Controls"
        elif in_controls and "music" in line.lower():
            return True
    return False


def report(L):
    path = write_debrief(L, "done")
    for log in L.tools.logs():
        L.run.copy_log(log)
    return L.verdict("report", "PASS", "debrief written", os.path.basename(path))


def write_debrief(L, reason):
    rows = [f"# VR Bench: {L.game}", "", f"Ended: {reason}. Tier: {L.tier}.", ""]
    for i, v in enumerate(L.verdicts, 1):
        rows.append(f"{i}. {v.name}: {v.result}. {v.how}" + (f" (picture: {v.picture})" if v.picture else ""))
    if L.known_added:
        rows += ["", "Added to KNOWN.md:", ""] + [f"- {k}" for k in L.known_added]
    if L.notes:
        rows += ["", "Worth knowing:", ""] + [f"- {n}" for n in L.notes]
    path = os.path.join(L.run.folder, "debrief.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(rows) + "\n")
    return path
