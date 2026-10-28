"""lanes_common.py - small helpers every Lanes tool shares, kept in ONE place so they cannot drift apart (0.94.2).

Polish day, 2026-10-28 (the maintainer: "Lanes has gotten pretty damn massive now ... can we spend most of the day now
looking at Lanes itself, finding faults in the plugin itself ... just polish what is already here"). Five tools each had
their own copy of the settings reader, and they disagreed (first line or last line wins, where a note after a value
starts, which files are read); 25 tools could crash on a character the Windows console cannot show.

    utf8_console()        call first in main(): print any character instead of crashing on it
"""
import sys


def utf8_console():
    """A name, a log line or a commit subject can hold any character; a Windows console or pipe defaults to cp1252
    and crashed /od on a non-breaking hyphen in a profile row (2026-10-28). Replace what cannot be shown instead."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
