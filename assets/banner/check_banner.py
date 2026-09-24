"""Is banner.png up to date? Prints "ok", or what is stale. Standard library only.

    python check_banner.py <plugin version>
"""
import hashlib
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def png_text(path):
    raw = path.read_bytes()
    text, i = {}, 8
    while i < len(raw):
        length, kind = struct.unpack(">I4s", raw[i:i + 8])
        body = raw[i + 8:i + 8 + length]
        i += 12 + length
        if kind == b"tEXt":
            key, value = body.split(b"\x00", 1)
            text[key.decode()] = value.decode("latin-1")
    return text


def main():
    want = sys.argv[1]
    notes = (HERE / "notes.txt").read_text(encoding="utf-8").replace("\r", "")
    noted = next((l.split(":", 1)[1].strip() for l in notes.splitlines()
                  if l.lower().startswith("version:")), None)
    text = png_text(HERE / "banner.png")
    problems = []
    if noted != want:
        problems.append("notes.txt says %s" % noted)
    if text.get("lanes-version") != want:
        problems.append("banner.png says %s" % text.get("lanes-version"))
    commands = sorted(c.stem for c in (HERE.parent.parent / "plugins" / "lanes" / "commands").glob("*.md"))
    listed = {l.split("|", 1)[0].strip().lstrip("/") for l in notes.splitlines() if "|" in l}
    unlisted = [c for c in commands if c not in listed]
    if unlisted:
        problems.append("THE LANES panel is missing /%s" % ", /".join(unlisted))
    if "audit" not in text.get("lanes-audit-line", "").lower():
        problems.append("banner.png has lost the permanent audit-it-yourself line")
    if not (HERE.parent.parent / "AUDIT.md").is_file():
        problems.append("AUDIT.md is missing")
    if text.get("lanes-notes-sha256") != hashlib.sha256(notes.strip().encode("utf-8")).hexdigest():
        problems.append("banner.png was not rebuilt after notes.txt changed")
    print("; ".join(problems) or "ok")


if __name__ == "__main__":
    main()
