"""inspector_store - where the Inspector keeps its notes, one folder per project.

The user's idea (2026-09-26): notes sorted into clear places - old ones, new ones, the ones from the
session in progress - instead of one long file. Each project gets an `inspector/` folder (inside
`dev-archive/` when the project has one), committed with the work so it travels between PCs:

    inspector/
      README.md          what this folder is, and how to answer a note
      this-session.md    noted during the session in progress, not answered yet
      waiting.md         left unanswered by an earlier session that ended first: answer these FIRST
      decided.md         answered (`fix later` / `keep`), with the reasons: what stops repeat questions
      already-there.md   what was in the code before the Inspector first looked at each file
      cleared.md         notes that left the code, newest first
      .state.json        bookkeeping for the tool (files seen, next id, current session); not for reading

A note is answered by replacing `waiting` on its Verdict line, in whichever file it sits; the next
save moves it to decided.md. The Inspector writes only this folder. It never edits code.
"""
import json
import os
import re
import time

FOLDER = "inspector"
EXAMPLES_SHOWN = 3
CLEARED_KEPT = 200
META_RE = re.compile(r"<!-- inspector (\{.*\}) -->$")
VERDICT_RE = re.compile(r"^- \*\*Verdict:\*\*\s*(.*)$")
# Safety rule 1: `fix now` only for kinds whose fix cannot change behaviour - giving a number or an
# address a name, deleting commented-out code. Splitting, moving, re-binding keys and de-duplicating
# are structural: they go to `fix later` and are done carefully on their own, move-only and tested.
FIX_NOW_OK = {"LOOSE-NUMS", "LOOSE-ADDRESS", "DEAD-CODE"}
BLOCKING_STATES = ("waiting", "fixnow", "badfix")
META_KEYS = ("id", "kind", "path", "detail", "value", "seen", "what", "fix", "examples", "note", "session",
             "verdict_value")

README = """# Inspector notes

Written by the lanes Inspector after code edits. **It never edits code; it only writes this
folder.** Each file holds one kind of note:

| File | What is in it |
| --- | --- |
| `this-session.md` | noted during the session in progress, not answered yet |
| `waiting.md` | left unanswered by an earlier session that ended first: **answer these first** |
| `decided.md` | answered, with the reason; a note here is only raised again if it gets clearly worse |
| `already-there.md` | what was in the code before the Inspector first looked at each file |
| `cleared.md` | notes that have left the code, newest first |

**To answer a note**, replace `waiting` on its Verdict line with one of:

- `fix now`: real; fix it before the session ends. **Only for LOOSE-NUMS, LOOSE-ADDRESS and DEAD-CODE**,
  whose fix cannot change behaviour. Anything structural (splitting, moving, re-binding a key,
  de-duplicating) is `fix later`, done on its own and tested.
- `fix later: <the board row that carries it>`
- `keep: <why it has to stay this way to work>`

Also check by eye, since no script can: a log limit that also switches off the behaviour it logs, and a
helper that exists in near-identical form in another game's code.

**Emergency save:** a session that has to end with notes unanswered commits with `inspector: carry over`
in the message; the notes wait in `waiting.md` and the next session is told about them first.
"""

FILES = {
    "this-session.md": ("Noted this session", "Noted during the session in progress, not answered yet."),
    "waiting.md": ("Waiting from an earlier session",
                   "Left unanswered when an earlier session ended. **Answer these before other work.**"),
    "decided.md": ("Decided", "Answered, with the reason. Raised again only if it gets clearly worse."),
}


def verdict_state(text, kind=None):
    t = (text or "").strip().strip("_*`").strip()
    low = t.lower()
    if low.startswith("fix now"):
        return "fixnow" if kind is None or kind in FIX_NOW_OK else "badfix"
    if low.startswith("fix later:") and len(t.split(":", 1)[1].strip()) >= 3:
        return "later"
    if low.startswith("keep:") and len(t.split(":", 1)[1].strip()) >= 10:
        return "keep"
    return "waiting"


def record_dir(repo, prefix=""):
    base = os.path.join(repo, prefix) if prefix else repo
    sub = os.path.join(base, "dev-archive")
    return os.path.join(sub if os.path.isdir(sub) else base, FOLDER)


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


class Record:
    """All of one project's notes. `path` is the folder."""

    def __init__(self, repo, prefix=""):
        self.repo, self.prefix = repo, prefix
        self.path = record_dir(repo, prefix)
        self.items, self.old, self.cleared = {}, {}, []
        self.seen, self.next_id, self.current_session = set(), 1, ""
        self.originals = {}
        state = _read(os.path.join(self.path, ".state.json"))
        if state:
            try:
                st = json.loads(state)
                self.seen = set(st.get("seen", []))
                self.next_id = int(st.get("next_id", 1))
                self.current_session = st.get("current_session", "")
            except ValueError:
                pass
        for name in list(FILES) + ["already-there.md", "cleared.md", "README.md", ".state.json"]:
            text = _read(os.path.join(self.path, name))
            self.originals[name] = text
            if text and name.endswith(".md") and name != "README.md":
                self._parse(name, text)

    @staticmethod
    def key(kind, path, detail):
        return f"{kind}|{path}|{detail}"

    def _parse(self, name, text):
        block = []
        for line in text.splitlines():
            if name == "cleared.md":
                if line.startswith("- "):
                    self.cleared.append(line)
                continue
            m = META_RE.search(line)
            if not m:
                block.append(line)
                continue
            try:
                meta = json.loads(m.group(1))
            except ValueError:
                block = []
                continue
            k = self.key(meta["kind"], meta["path"], meta.get("detail", ""))
            if meta.get("old"):
                self.old[k] = meta
            else:
                verdict = next((VERDICT_RE.match(l).group(1) for l in block if VERDICT_RE.match(l)), "waiting")
                meta["verdict"] = verdict.strip() or "waiting"
                self.items[k] = meta
                self.next_id = max(self.next_id, int(meta["id"].split("-")[1]) + 1)
            block = []

    def add(self, f, note="", session=None):
        k = self.key(f.kind, f.path, f.detail)
        self.items[k] = {"id": f"I-{self.next_id:04d}", "kind": f.kind, "path": f.path, "detail": f.detail,
                         "value": f.value, "verdict": "waiting", "seen": time.strftime("%Y-%m-%d"),
                         "what": f.what, "fix": f.fix, "examples": list(f.examples)[:EXAMPLES_SHOWN],
                         "note": note, "session": session if session is not None else self.current_session}
        self.next_id += 1
        return self.items[k]

    def add_cleared(self, item):
        tag = f" <!-- session:{item['session']} -->" if item.get("session") else ""
        self.cleared.insert(0, f"- {time.strftime('%Y-%m-%d')} {item['id']} {item['kind']} {item['path']}: "
                               f"gone from the code{tag}")

    def place(self, item):
        """Which file a note belongs in."""
        if verdict_state(item["verdict"], item["kind"]) not in BLOCKING_STATES:
            return "decided.md"
        return "this-session.md" if item.get("session", "") == self.current_session else "waiting.md"

    def _render_items(self, name):
        title, intro = FILES[name]
        out = [f"# {title}\n", intro + "\n"]
        items = sorted((i for i in self.items.values() if self.place(i) == name), key=lambda x: x["id"])
        if not items:
            out.append("_none_\n")
        for i in items:
            out.append(f"### {i['id']} · {i['kind']} · {i['path']}")
            out.append(f"- **What:** {i['what']}")
            if i.get("note"):
                out.append(f"- **Note:** {i['note']}")
            if i.get("examples"):
                out.append("- **Where:** " + " · ".join(f"`{e}`" for e in i["examples"]))
            out.append(f"- **Suggested fix:** {i['fix']}")
            out.append(f"- **Seen:** {i['seen']}")
            out.append(f"- **Verdict:** {i['verdict']}")
            meta = {k: i[k] for k in META_KEYS if k in i}
            out.append(f"<!-- inspector {json.dumps(meta, ensure_ascii=False)} -->\n")
        return "\n".join(out).rstrip() + "\n"

    def render(self):
        files = {name: self._render_items(name) for name in FILES}
        old = ["# Already there before the Inspector\n",
               "Found in the last commit the first time the Inspector looked at each file. Not raised unless "
               "it gets clearly worse.\n"]
        for k in sorted(self.old):
            o = self.old[k]
            label = f"{o['kind']} {o['path']}" + (f" ({o['detail']})" if o.get("detail") else "")
            old.append(f"- `{label}`: {o['value']} <!-- inspector {json.dumps(o, ensure_ascii=False)} -->")
        files["already-there.md"] = "\n".join(old).rstrip() + "\n"
        files["cleared.md"] = "\n".join(["# Cleared\n", "Notes that have left the code, newest first.\n"]
                                        + (self.cleared[:CLEARED_KEPT] or ["_none yet_"])) + "\n"
        files["README.md"] = README
        files[".state.json"] = json.dumps({"seen": sorted(self.seen), "next_id": self.next_id,
                                           "current_session": self.current_session}, indent=1) + "\n"
        return files

    def save(self):
        changed = False
        for name, text in self.render().items():
            if text == self.originals.get(name):
                continue
            os.makedirs(self.path, exist_ok=True)
            with open(os.path.join(self.path, name), "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            self.originals[name] = text
            changed = True
        return changed
