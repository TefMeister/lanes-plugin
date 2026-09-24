# Spec: keep every build (opt-in), delete only when the user says the project is done

**Asked for by the user, 2026-09-22, twice in one evening.** First: *"from now on, can you keep the
each version saved on the pc at least and if possible, on github too, so we can roll back steps if
needed"*. Then, on hearing the first hand-made version of it: *"make that a choosable option for the
plugin as well and then only when the user says so by the end of the project, these can be deleted
so you know exactly what can be deleted once the time comes."*

**Why it exists:** on 2026-09-22 a mod picture turned upside down some time after a known-good
run. Bisecting it needed the exact earlier binaries. The plugin DLLs survived only because the
install helper happened to keep `.pre-*` copies; the framework build from the good run was gone
(two later builds had overwritten it), so the comparison had to be rebuilt from a patch, which is
not the same binary. Status: NOT BUILT. Hand-made version in use meanwhile (see below).

## What it does

1. **`keep_builds = yes|no` in `lanes.conf`** (default `no`; the setup walk-through offers it).
2. When on, **every time a session installs a built binary into a game folder**, it first copies
   the binary into the archive:
   `<archive root>/<project>/YYYY-MM-DD_HHMM_<sha256 first 8>_<kind>-<short-name>/<file>` plus a
   `MANIFEST.txt`: file name, full sha256, build time, source repo + commit, one plain line of
   what changed, and a `worn:` line the session fills in later (`not yet` / `worn YYYY-MM-DD:
   <one-line verdict>`).
3. **Archive root** is a `lanes.conf` key (`builds_root`), one folder per project. The same
   binary (same hash) is never stored twice.
4. **GitHub, where size allows:** small binaries (under ~1 MB, e.g. a REFramework plugin) are
   committed to the user's private `builds` repo under the same folder name; large ones (a
   whole framework fork, 22 MB) are attached as a release asset on that repo, one release per
   build, never committed to the tree. A `keep_builds_github = yes|no` key gates this.
5. **Nothing is ever deleted by the plugin.** A `/lanes:builds` command lists the archive per
   project (date, hash, note, worn verdict, size) and marks which builds are *safe to delete*
   by the plugin's own reckoning (superseded, never worn, or older than the last released
   build). Deletion happens only when the **user says the project is finished**, and then only
   through that command, which prints the list and asks once. The point of the list is that the
   user can see exactly what would go before saying yes.
6. The install helpers the plugin generates (`UPDATE-*.bat` and their kin) call the archive step
   themselves, so it cannot be forgotten by a session.

## Not in scope

- Archiving game files (never; only binaries the mod built).
- Automatic pruning of any kind.

## Hand-made version already in use (home PC, 2026-09-22)

A per-project `builds/<project>/` folder on the author's home PC holds 15 builds with manifests, seeded by
a one-off script; new builds are added by hand until this spec is built. The rule itself is
kept in the author's own notes.
