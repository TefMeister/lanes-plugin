"""vb_tools - the real PC behind the learning hour: Menu-o-matiC, the simulator, the layer, KNOWN.md and the claim.

vb_learn and the stages only ever call these methods, so the tests swap in a fake. Where a game's facts live:
  routes and KNOWN.md   <routes>/<game>/ from `routes =` in lanes.conf (the game's project name without "-vr";
                        `vrbench_routes.<project> = <folder name>` when it differs)
  the game's window     the "window" of its launch route, else `vrbench_window.<project> =`
  the game's log        `vrbench_log.<project> = <file>` (our mods log what the layer sent them)
"""
import glob
import json
import socket
import os
import subprocess
import sys
import time

import vb_input
import vb_layer
import vb_profile
import vb_settings as S
import vb_sim

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
MOM = os.path.join(TOOLS, "menu-o-matic", "menu_o_matic.py")
MOVE = os.path.join(TOOLS, "menu-o-matic", "move_o_matic.py")
CLAIM = os.path.join(TOOLS, "lane-claim.sh")
OPENXR_SIM = os.path.join(TOOLS, "openxr-sim.py")
LANE = "/vb"
FLAT_SCALE = "0.5"            # flat pictures at half size: a quarter of the cost to look at
MOM_TIMEOUT_S = 900
SKIN = dict(r_min=90, rg_gap=10, gb_gap=5, stride=2, min_pixels=40)   # the hand colour test of 2026-10-16


class Tools:
    def __init__(self, project, run):
        self.project, self.run = project, run
        name = S.conf_get(f"vrbench_routes.{project}") or (project[:-3] if project.endswith("-vr") else project)
        self.routes_dir = os.path.join(S.conf_get("routes") or "", name)
        self._window = S.conf_get(f"vrbench_window.{project}") or None

    # ---- time ----
    def now(self):
        return time.time()

    def sleep(self, s):
        time.sleep(s)

    # ---- pre-flight ----
    def sim_installed(self):
        try:
            r = subprocess.run([sys.executable, OPENXR_SIM, "status", "--json"], capture_output=True, text=True,
                               timeout=MOM_TIMEOUT_S, env=dict(os.environ, LANES_OPENXRSIM_OFFLINE="1"))
            return bool(json.loads(r.stdout).get("installed"))
        except Exception:
            return False

    def resolve_exe(self, game):
        return vb_layer.resolve_exe(game)

    def known(self):
        if not S.conf_get("routes"):
            raise OSError("no `routes =` folder in lanes.conf")
        r = subprocess.run([sys.executable, MOM, "known", self.routes_dir], capture_output=True, text=True)
        if r.returncode:
            raise OSError((r.stderr or r.stdout).strip()[:200])
        path = os.path.join(self.routes_dir, "KNOWN.md")
        with open(path, encoding="utf-8") as f:
            return f.read()

    def known_add(self, section, text):
        subprocess.run([sys.executable, MOM, "known", self.routes_dir, "--add", section, text], capture_output=True)

    def claim(self, take):
        """take or release VR Bench's own claim; inside a live /lm session on this PC that already holds the game, the
        run works under that claim and touches nothing (2026-10-17: taking a second claim failed, and was not needed)"""
        if take:
            held = subprocess.run(["bash", CLAIM, "check", self.project], capture_output=True, text=True).stdout
            self._under_lm = "FRESH" in held and "/lm" in held and socket.gethostname().lower() in held.lower()
        if getattr(self, "_under_lm", False):
            return
        r = subprocess.run(["bash", CLAIM, "take" if take else "release", LANE, self.project],
                           capture_output=True, text=True)
        if take and r.returncode:
            import vb_learn
            raise vb_learn.Refused(f"could not claim {self.project}: {(r.stdout + r.stderr).strip()[:200]}")

    def profile(self):
        conf = {k: S.conf_get(k) for k in ("bench_headset", "bench_tier")}
        vb_profile.write(vb_profile.collect(conf, vb_profile.Probes()))

    def layer_start(self, exe):
        self._layer_was_on = os.path.exists(S.ENABLED_FILE)
        vb_layer.start(exe)

    def layer_stop(self):
        """only a layer this run switched on goes off again: one already on was left on by its owner (2026-10-17:
        learn used to switch it off at its end, and the next hand-made test had to switch it on again)"""
        if not getattr(self, "_layer_was_on", False):
            vb_layer.stop()

    def logs(self):
        return [p for p in (S.conf_get(f"vrbench_log.{self.project}"), S.LAYER_LOG) if p and os.path.isfile(p)]

    # ---- Menu-o-matiC ----
    def find_route(self, start, end):
        for path in sorted(glob.glob(os.path.join(self.routes_dir, "*.json"))):
            try:
                with open(path, encoding="utf-8") as f:
                    route = json.load(f)
            except (OSError, ValueError):
                continue
            named = os.path.splitext(os.path.basename(path))[0] == f"{start}_to_{end}"
            if named or (route.get("from"), route.get("to")) == (start, end):
                self._window = self._window or route.get("window")
                return path
        return None

    def mom(self, args, script=MOM):
        r = subprocess.run([sys.executable, script, *args], capture_output=True, text=True, timeout=MOM_TIMEOUT_S)
        events = []
        for line in r.stdout.splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                pass
        return {"code": r.returncode, "events": events}

    def window(self):
        if not self._window:
            self.find_route("launch", "gameplay")
        if not self._window:
            raise LookupError(f"no window title known: set vrbench_window.{self.project} in lanes.conf")
        return self._window

    def _screen(self, name):
        return os.path.join(self.run.folder, "screens", name + ".png")

    def flat_shot(self, name):
        out = self._screen(name)
        return out if self.mom(["look", self.window(), out, "--scale", FLAT_SCALE])["code"] == 0 else None

    def turn(self, px, name):
        out = self._screen(name)
        return out if self.mom(["turn", self.window(), f"{px},0", "--look", out], MOVE)["code"] == 0 else None

    def probe(self, key, seconds):
        res = self.mom(["probe", self.window(), key, "--seconds", str(seconds)])
        return any(e.get("region_changed") for e in res["events"] if e.get("event") == "probe")

    def picture_diff(self, a, b):
        sys.path.insert(0, os.path.dirname(MOM))
        import mom_route
        from PIL import Image
        return mom_route.distance(mom_route.signature(Image.open(a)), mom_route.signature(Image.open(b)))

    # ---- the simulator and the layer ----
    def head(self, x, y, z, yaw, pitch, roll):
        vb_sim.head(x, y, z, yaw, pitch, roll)

    def sweep(self, on, yaw_amp=0.0, hz=0.0):
        vb_sim.sweep(on, yaw_amp, hz)

    def sim_shot(self, name):
        return self.run.shot(name)

    def send(self, inp):
        vb_input.write(inp)
        self.run.input_sent(inp)

    def hand_centroid(self, png):
        """the middle of the hand-coloured pixels in the LEFT eye (skin: red > green > blue); None when too few"""
        from PIL import Image
        im = Image.open(png).convert("RGB")
        w, h = im.size
        px = im.load()
        sx = sy = n = 0
        for y in range(0, h, SKIN["stride"]):
            for x in range(0, w // 2, SKIN["stride"]):
                r, g, b = px[x, y]
                if r > SKIN["r_min"] and r > g + SKIN["rg_gap"] and g > b + SKIN["gb_gap"]:
                    sx += x
                    sy += y
                    n += 1
        return (sx / n, sy / n) if n >= SKIN["min_pixels"] else None

    def game_log_tail(self, n):
        path = S.conf_get(f"vrbench_log.{self.project}")
        if not path or not os.path.isfile(path):
            return []
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.readlines()[-n:]
