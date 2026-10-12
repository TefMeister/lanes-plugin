"""begone_common.py - what every BeG0nE tool in Lanes shares: where things live, and which tools there are.

THREE PLACES (Lanes 0.62.0)
  code        this folder, inside the plugin. Updates with the plugin; never holds anything of the person's.
  home        where the filed reports and the knowledge live: `begone = <folder>` in lanes.conf (a clone of the
              BeG0nE repo, so the reports reach GitHub and the other PC), else ~/Documents/BeG0nE recordings.
              Each tool has its own folder there: <home>/<tool folder>/data/ and, for the jitter tool, knowledge/.
  logs        the raw recordings a mod writes while a headset session runs: %LOCALAPPDATA%\\BeG0nE\\<log dir>\\.
              Filed ones move to done\\ and stay on the PC that made them; they are never uploaded.

THE TOOLS are the folders here with a tool.json. A new tool is a new folder with a tool.json; the rider, the
reader and the raw-number lock pick it up without any other change.
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "BeG0nE")
DEFAULT_HOME = os.path.join(os.path.expanduser("~"), "Documents", "BeG0nE recordings")


def conf_path():
    return os.environ.get("LANES_CONFIG") or os.path.join(os.path.expanduser("~"), ".claude", "lanes.conf")


def read_conf():
    conf = {}
    try:
        with open(conf_path(), encoding="utf-8") as f:
            for line in f:
                if line.lstrip().startswith("#"):
                    continue
                m = re.match(r"^\s*([A-Za-z_]+)\s*=\s*(.*?)\s*(#.*)?$", line)
                if m:
                    conf[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    except OSError:
        pass
    return conf


def home():
    """The person's BeG0nE home. An explicitly set folder that does not exist is NOT replaced by the default:
    reports written somewhere unexpected are reports nobody finds."""
    h = os.environ.get("LANES_BEGONE")
    if h is None:
        h = read_conf().get("begone", "")
    return h if h else DEFAULT_HOME


def tools():
    """Every tool: its tool.json plus 'dir' (the code folder). Sorted by folder name."""
    out = []
    for name in sorted(os.listdir(HERE)):
        p = os.path.join(HERE, name, "tool.json")
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    t = json.load(f)
            except (OSError, ValueError):
                continue
            t["dir"] = os.path.join(HERE, name)
            t.setdefault("folder", name)
            out.append(t)
    return out


def tool(key):
    """Find a tool by folder name or by any word of its name ('ghost', 'jitter', 'occlusion')."""
    key = key.lower()
    for t in tools():
        if key == t["folder"] or key in t["name"].lower() or key in t.get("short", "").lower():
            return t
    return None


def tool_home(t, root=None):
    return os.path.join(root or home(), t["folder"])


def data_dir(t, root=None):
    return os.path.join(tool_home(t, root), "data")


def index_path(t, root=None):
    return os.path.join(data_dir(t, root), "INDEX.csv")


def log_dir(t):
    return os.path.join(LOCAL, t["log_dir"]) if t.get("log_dir") else None
