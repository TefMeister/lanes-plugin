#!/usr/bin/env python3
"""gd_dump.py - read a Windows crash dump (minidump, .dmp) the way a person reads it: what went wrong, in which
module and where, and what had already been unloaded (0.112.0, 2026-11-12; Gold Digger's helper).

    python gd_dump.py <file.dmp>        the crash record in plain lines

Why: Gold Digger's digest printed a dump's raw memory strings; on 2026-11-07 eleven Silent Hill 2 dumps had to be read
by hand to find that they were the same crash. Now each dump is a few lines (the exception, the module and offset it
happened at, the Steam modules already unloaded), so identical crashes fold together like repeated log lines.

The format (Microsoft's MINIDUMP_* structures, all little-endian): a header ("MDMP", the stream count and where the
stream directory is), then streams. Used here: 4 = the loaded modules, 6 = the exception, 14 = the unloaded modules.
Reads only what it needs, never the whole file into memory (dumps reach hundreds of MB).
"""
import os
import struct
import sys

MAGIC = b"MDMP"
MODULE_LIST, EXCEPTION, UNLOADED = 4, 6, 14
MODULE_SIZE = 108                     # MINIDUMP_MODULE
MAX_MODULES = 5000
STEAM_MODULES = ("steam_api64.dll", "steam_api.dll", "steamclient64.dll", "steamclient.dll",
                 "gameoverlayrenderer64.dll", "gameoverlayrenderer.dll", "tier0_s64.dll", "vstdlib_s64.dll")

CODES = {
    0xC0000005: "access violation (a read or write of memory it may not touch)",
    0xC0000409: "stack buffer overrun / fail-fast (the program stopped itself on purpose)",
    0xC00000FD: "stack overflow",
    0xC0000374: "heap corruption",
    0xC000001D: "illegal instruction",
    0xC0000094: "integer divide by zero",
    0xC0000096: "privileged instruction",
    0xC0000420: "assertion failure",
    0x80000003: "breakpoint (a debug stop, or a deliberate crash)",
    0xE06D7363: "C++ exception that nobody caught",
    0xC06D007E: "a DLL could not be found (delay load)",
    0xC0000602: "fail-fast exception",
}
AV_KIND = {0: "reading", 1: "writing", 8: "running code at"}


class Dump:
    def __init__(self, path):
        self.f = open(path, "rb")
        head = self.f.read(32)
        if len(head) < 32 or head[:4] != MAGIC:
            raise ValueError("not a minidump")
        self.count, self.dir_rva = struct.unpack_from("<II", head, 8)
        self.streams = {}
        self.f.seek(self.dir_rva)
        for _ in range(min(self.count, 4096)):
            raw = self.f.read(12)
            if len(raw) < 12:
                break
            kind, size, rva = struct.unpack("<III", raw)
            self.streams.setdefault(kind, (size, rva))

    def close(self):
        self.f.close()

    def read(self, rva, size):
        self.f.seek(rva)
        return self.f.read(size)

    def string(self, rva):
        raw = self.read(rva, 4)
        if len(raw) < 4:
            return "?"
        n = struct.unpack("<I", raw)[0]
        return self.read(rva + 4, min(n, 2048)).decode("utf-16-le", "replace")

    def modules(self):
        """[(base, size, name)] of the loaded modules"""
        if MODULE_LIST not in self.streams:
            return []
        _, rva = self.streams[MODULE_LIST]
        n = struct.unpack("<I", self.read(rva, 4))[0]
        out = []
        for i in range(min(n, MAX_MODULES)):
            raw = self.read(rva + 4 + i * MODULE_SIZE, MODULE_SIZE)
            if len(raw) < 24:
                break
            base, size, _cs, _ts, name_rva = struct.unpack_from("<QIIII", raw, 0)
            out.append((base, size, self.string(name_rva)))
        return out

    def unloaded(self):
        if UNLOADED not in self.streams:
            return []
        _, rva = self.streams[UNLOADED]
        hsize, esize, n = struct.unpack("<III", self.read(rva, 12))
        out = []
        for i in range(min(n, MAX_MODULES)):
            raw = self.read(rva + hsize + i * esize, 24)
            if len(raw) < 24:
                break
            base, size, _cs, _ts, name_rva = struct.unpack("<QIIII", raw)
            out.append((base, size, self.string(name_rva)))
        return out

    def exception(self):
        """(thread, code, address, [parameters]) or None"""
        if EXCEPTION not in self.streams:
            return None
        _, rva = self.streams[EXCEPTION]
        raw = self.read(rva, 8 + 152)
        if len(raw) < 8 + 32:
            return None
        thread = struct.unpack_from("<I", raw, 0)[0]
        code, _flags, _rec, addr, nparams = struct.unpack_from("<IIQQI", raw, 8)
        params = list(struct.unpack_from("<%dQ" % min(nparams, 15), raw, 8 + 32)) if nparams else []
        return thread, code, addr, params


def base_name(path):
    return path.replace("\\", "/").rsplit("/", 1)[-1]


def where(addr, mods):
    for base, size, name in mods:
        if base <= addr < base + size:
            return base_name(name), addr - base
    return None, None


def summary(path):
    """plain lines saying what the dump records; the first line is the one a crash is known by"""
    try:
        d = Dump(path)
    except (OSError, ValueError, struct.error) as e:
        return ["not a readable crash dump (%s)" % e]
    try:
        mods, gone = d.modules(), d.unloaded()
        exc = d.exception()
        lines = []
        if not exc:
            lines.append("crash dump with no exception record (taken by hand, or a hang)")
        else:
            _thread, code, addr, params = exc
            mod, off = where(addr, mods)
            if mod is None:
                gmod, goff = where(addr, gone)
                at = ("in %s+0x%X, a module ALREADY UNLOADED" % (base_name(gmod), goff)) if gmod else \
                     "at 0x%X, in no loaded module" % addr
            else:
                at = "in %s+0x%X" % (mod, off)
            lines.append("crash 0x%08X %s %s" % (code, CODES.get(code, "(an exception code not in the list)"), at))
            if code == 0xC0000005 and len(params) >= 2:
                lines.append("  it was %s address 0x%X%s" % (AV_KIND.get(params[0], "touching"), params[1],
                                                           " (a null pointer)" if params[1] < 0x10000 else ""))
        names = {base_name(n).lower() for _, _, n in mods}
        gone_steam = sorted({base_name(n) for _, _, n in gone if base_name(n).lower() in STEAM_MODULES
                             and base_name(n).lower() not in names})
        if gone_steam:
            lines.append("  Steam was already unloaded: " + ", ".join(gone_steam))
        elif any(n in names for n in STEAM_MODULES):
            lines.append("  Steam was still loaded")
        lines.append("  %d modules loaded, %d unloaded" % (len(mods), len(gone)))
        return lines
    finally:
        d.close()


def is_dump(path):
    if path.lower().endswith((".dmp", ".mdmp")):
        return True
    try:
        with open(path, "rb") as f:
            return f.read(4) == MAGIC
    except OSError:
        return False


if __name__ == "__main__":
    if len(sys.argv) != 2 or not os.path.isfile(sys.argv[1]):
        print(__doc__.split("\n\n")[1])
        sys.exit(2)
    print("\n".join(summary(sys.argv[1])))
