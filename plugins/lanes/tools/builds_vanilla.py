"""builds_vanilla.py - the app's ORIGINAL files, saved before anything of ours changes them (0.46.0).

Used by builds.py (`vanilla`, `vanilla-restore`, and inside `snap`, `restore` and `check`); not run on its own.

WHY
  The person asked, 2026-10-06: "add a folder that saves all the vanilla files before you change anything within
  them ... so reverting back to a working game is always doable, even late into modding". Builds keep every
  version of OUR files, but a file of the app's own that a mod overwrites (a config, a data file, a stock DLL) was
  kept nowhere: once changed, the only way back was a full reinstall.

WHERE
  <builds>/<project>/_vanilla/<path in the app folder>   the untouched copy, on THIS PC only
  <builds>/<project>/_vanilla/MANIFEST.sha256           its hash; this list IS pushed, the files never are
  The folder's .gitignore keeps every original file out of git: they are the app's own files, and publishing
  them is publishing the app. The hash list tells the other PC what to save on its side (`vanilla --fill`).

RULES
  - The FIRST copy wins. An original is never overwritten by a later save.
  - A file that already matches one of OUR saved builds is refused: it is not the original any more.
  - Nothing here is ever deleted by the tool.
"""
import hashlib
import os
import shutil

VANILLA_DIR = "_vanilla"
MANIFEST = "MANIFEST.sha256"
IGNORE = "*\n!.gitignore\n!MANIFEST.sha256\n!README.md\n"
README = """# Original app files (kept by builds.py)

Each file here is the app's own, untouched copy of a file a mod changed, saved BEFORE the change.
`builds.py vanilla-restore <project> --yes` takes everything of ours out of the app folder and puts these back:
a working, unmodded app, at any point in the project.

The files stay on the PC that saved them and are never uploaded (they belong to the app's makers).
Only MANIFEST.sha256 is shared, so the other PC knows what to save on its side: `builds.py vanilla <project> --fill`.
"""


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def vdir(root, project):
    return os.path.join(root, project, VANILLA_DIR)


def read(root, project):
    """rel path -> hash of every original saved on ANY PC (the shared list)."""
    out = {}
    try:
        with open(os.path.join(vdir(root, project), MANIFEST), encoding="utf-8") as f:
            for line in f:
                h, _, p = line.rstrip("\n").partition("  ")
                if p:
                    out[p] = h
    except OSError:
        pass
    return out


def _write(root, project, entries):
    d = vdir(root, project)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, ".gitignore"), "w", encoding="utf-8", newline="\n") as f:
        f.write(IGNORE)
    if not os.path.isfile(os.path.join(d, "README.md")):
        with open(os.path.join(d, "README.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(README)
    with open(os.path.join(d, MANIFEST), "w", encoding="utf-8", newline="\n") as f:
        f.writelines(f"{entries[p]}  {p}\n" for p in sorted(entries))


def _files(app, paths):
    """App-relative path -> absolute path for every file named, folders walked."""
    out = {}
    for p in paths:
        full = p if os.path.isabs(p) else os.path.join(app, p)
        full = os.path.normpath(full)
        if os.path.isdir(full):
            for r, _, names in os.walk(full):
                for n in names:
                    f = os.path.join(r, n)
                    out[os.path.relpath(f, app).replace("\\", "/")] = f
        else:
            out[os.path.relpath(full, app).replace("\\", "/")] = full
    return out


def save(root, project, app, paths, ours_hashes, fill=False):
    """Save originals. ours_hashes: rel -> set of hashes that file had in any saved build (so not original).
    Returns (lines to print, True if the shared list changed)."""
    entries = read(root, project)
    d = vdir(root, project)
    lines, changed = [], False
    todo = _files(app, paths)
    if fill:
        todo.update({rel: os.path.join(app, rel) for rel in entries if not os.path.isfile(os.path.join(d, rel))})
    for rel, full in sorted(todo.items()):
        copy = os.path.join(d, rel)
        if rel.startswith(".."):
            lines.append(f"  refused  {rel}: not inside the app folder")
            continue
        if not os.path.isfile(full):
            lines.append(f"  missing  {rel}: not in the app folder")
            continue
        now = sha(full)
        if rel in entries:
            if os.path.isfile(copy):
                lines.append(f"  kept     {rel}: the original is already saved (the first copy wins)")
            elif now == entries[rel]:
                os.makedirs(os.path.dirname(copy), exist_ok=True)
                shutil.copy2(full, copy)
                lines.append(f"  saved    {rel}: this PC's copy of the original (hash matches the shared list)")
            else:
                lines.append(f"  CHANGED  {rel}: the original was saved on the other PC, but this PC's file is "
                             "already different. Repair or reinstall the app to get the original back, then --fill.")
            continue
        if now in ours_hashes.get(rel, ()):
            lines.append(f"  refused  {rel}: it matches one of our saved builds, so it is not the original any more")
            continue
        os.makedirs(os.path.dirname(copy), exist_ok=True)
        shutil.copy2(full, copy)
        entries[rel] = now
        changed = True
        lines.append(f"  saved    {rel}")
    if changed or not os.path.isfile(os.path.join(d, MANIFEST)):
        _write(root, project, entries)
    return lines, changed


def put_back(root, project, app, only_missing=False):
    """Copy the saved originals into the app folder. only_missing: just those the app folder lacks (after a
    restore took out a folder of ours that held one). Returns (put back, no copy on this PC)."""
    entries = read(root, project)
    d = vdir(root, project)
    done, lacking = [], []
    for rel, digest in sorted(entries.items()):
        target = os.path.join(app, rel)
        if only_missing and os.path.isfile(target):
            continue
        copy = os.path.join(d, rel)
        if not os.path.isfile(copy) or sha(copy) != digest:
            if not (os.path.isfile(target) and sha(target) == digest):   # already the original: nothing to do
                lacking.append(rel)
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(copy, target)
        done.append(rel)
    return done, lacking


def check_lines(root, project, app):
    """Session-start lines (no paths): originals listed on the shared list but not saved on this PC."""
    entries = read(root, project)
    d = vdir(root, project)
    can, cannot = 0, 0
    for rel, digest in entries.items():
        if os.path.isfile(os.path.join(d, rel)):
            continue
        target = os.path.join(app, rel)
        if os.path.isfile(target) and sha(target) == digest:
            can += 1
        else:
            cannot += 1
    out = []
    if can:
        out.append(f"- {project}: {can} original app file(s) are saved on the other PC but not on this one; while "
                   f"this PC still has them untouched, `builds.py vanilla {project} --fill` saves them here too.")
    if cannot:
        out.append(f"- {project}: {cannot} original app file(s) have no saved copy on this PC and this PC's copy is "
                   "already changed; a repair or reinstall of the app gets them back, then `vanilla --fill`.")
    return out
