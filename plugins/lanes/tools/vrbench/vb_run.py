"""vb_run - one run's folder: what was sent, what was seen, and each stage's verdict.

    RUNS_DIR/<game>/<YYYY-MM-DD>_<HH-MM-SS>/
        run.json        game, started, finished, reason, tier, stages[{name, verdict, how, picture, at}]
        input.jsonl     every input file sent, one JSON line each, with the time
        screens/        pictures taken through the simulator
        game-log/       the game's and the layer's logs, copied in at the end
"""
import json
import os
import shutil
import time

import vb_settings as S
import vb_sim


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


class Run:
    def __init__(self, folder):
        self.folder = folder
        self._json = os.path.join(folder, "run.json")

    @classmethod
    def new(cls, game, tier=None):
        base = os.path.join(S.RUNS_DIR, game, time.strftime("%Y-%m-%d_%H-%M-%S"))
        folder, n = base, 1
        while os.path.exists(folder):   # two runs in one second
            n += 1
            folder = f"{base}_{n}"
        os.makedirs(os.path.join(folder, "screens"))
        run = cls(folder)
        run._save({"game": game, "started": _now(), "finished": None, "reason": None, "tier": tier, "stages": []})
        return run

    def _load(self):
        with open(self._json, encoding="utf-8") as f:
            return json.load(f)

    def _save(self, rec):
        tmp = self._json + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=1)
        os.replace(tmp, self._json)

    def shot(self, name):
        """a picture through the simulator into screens/<name>.png; the path, or None when none came"""
        path = os.path.join(self.folder, "screens", name + ".png")
        return path if vb_sim.screenshot(path) else None

    def input_sent(self, inp):
        with open(os.path.join(self.folder, "input.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"at": _now(), "input": inp.as_dict()}) + "\n")

    def stage(self, name, verdict, how, picture=None):
        rec = self._load()
        rec["stages"].append({"name": name, "verdict": verdict, "how": how, "picture": picture, "at": _now()})
        self._save(rec)

    def copy_log(self, path):
        if not os.path.isfile(path):
            return None
        dest_dir = os.path.join(self.folder, "game-log")
        os.makedirs(dest_dir, exist_ok=True)
        return shutil.copy2(path, os.path.join(dest_dir, os.path.basename(path)))

    def finish(self, reason):
        rec = self._load()
        rec["finished"] = _now()
        rec["reason"] = reason
        self._save(rec)
