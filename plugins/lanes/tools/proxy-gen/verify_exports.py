#!/usr/bin/env python3
"""
verify_exports.py - check that a built proxy exports exactly what the original does.

    python verify_exports.py <built proxy dll> <original dll>

Compares (ordinal, name) pairs, including ordinal-only exports, and confirms both
files are the same architecture. Exit code 0 = identical, 1 = mismatch.
"""
import sys

import pefile


def export_set(path):
    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories(
        directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]])
    symbols = pe.DIRECTORY_ENTRY_EXPORT.symbols if hasattr(pe, "DIRECTORY_ENTRY_EXPORT") else []
    pairs = {(s.ordinal, s.name.decode() if s.name else None)
             for s in symbols if s.address or s.forwarder}
    return pe.FILE_HEADER.Machine, pairs


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    proxy_path, original_path = sys.argv[1], sys.argv[2]
    proxy_machine, proxy = export_set(proxy_path)
    orig_machine, orig = export_set(original_path)
    ok = True
    if proxy_machine != orig_machine:
        print(f"MISMATCH machine: proxy 0x{proxy_machine:X}, original 0x{orig_machine:X}")
        ok = False
    for ordinal, name in sorted(orig - proxy, key=lambda p: p[0]):
        print(f"MISSING in proxy: #{ordinal} {name}")
        ok = False
    for ordinal, name in sorted(proxy - orig, key=lambda p: p[0]):
        print(f"EXTRA in proxy:   #{ordinal} {name}")
        ok = False
    named = sum(1 for _, n in orig if n)
    verdict = "MATCH" if ok else "MISMATCH"
    print(f"{verdict}: proxy {len(proxy)} exports, original {len(orig)} "
          f"({named} named, {len(orig) - named} ordinal-only)  [{proxy_path}]")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
