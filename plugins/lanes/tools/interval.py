#!/usr/bin/env python3
"""interval.py -- how often a regular job comes round: a number of days, or once a month.

One rule for every reminder of the full scan (0.125.2): the Keeper's regular job, Gold Digger's session-start line
and the tool check's line all ask this module, so they never disagree. Asked for by Tefa, 2026-11-28: "a fullscan -
we'll do this once a month now, please remind me every beginning of the month. this is taking a long time, too long to
do every week".

    lanes.conf:  fullscan_every = month      due from the 1st of each month in which it has not run yet
                 fullscan_every = 7          due 7 days after the last run (the default)

A job's own interval (the Keeper's jobs.tsv) takes the same two spellings: a whole number of days, or `month`.
"""
import datetime
import os

DEFAULT_DAYS = 7
MONTH = "month"
CONF_KEY = "fullscan_every"


def parse(value, default=DEFAULT_DAYS):
    """'month' / 'monthly' -> MONTH; a whole number of days -> that int; anything else -> default."""
    v = (value or "").strip().lower()
    if v in ("month", "monthly"):
        return MONTH
    return int(v) if v.isdigit() and int(v) > 0 else default


def _conf_files():
    if os.environ.get("LANES_CONFIG"):
        return [os.environ["LANES_CONFIG"]]
    home = os.path.expanduser("~")
    return [os.path.join(home, ".claude", "lanes.conf"), os.path.join(home, ".config", "lanes", "lanes.conf")]


def fullscan_every():
    """The full scan's interval from lanes.conf (`fullscan_every =`), else every 7 days."""
    for path in _conf_files():
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.lstrip().startswith("#"):
                        continue
                    k, sep, v = line.partition("=")
                    if sep and k.strip() == CONF_KEY:
                        return parse(v.split(" #")[0].strip().strip('"'))
        except OSError:
            pass
    return DEFAULT_DAYS


def late_by(start, every, today):
    """Days the job is late (0 = due today), or None when it is not due yet.

    start is the day it was last done (or first seen, for a job never done). Monthly: due from the 1st of every
    month after the month of `start`, late counted from that 1st."""
    if every == MONTH:
        if (today.year, today.month) <= (start.year, start.month):
            return None
        return (today - today.replace(day=1)).days
    late = (today - start).days - every
    return late if late >= 0 else None


def words(every):
    """'once a month' or 'every 7 days', for the reminder lines."""
    return "once a month" if every == MONTH else "every %d days" % every


def habit(every):
    """'monthly' or 'weekly' or 'every N days', for a line naming the check."""
    if every == MONTH:
        return "monthly"
    return "weekly" if every == 7 else "every-%d-days" % every


if __name__ == "__main__":
    e = fullscan_every()
    print("full scan: %s (lanes.conf `%s =`)" % (words(e), CONF_KEY))
    t = datetime.date.today()
    print("example: last run %s -> late by %s" % (t.replace(day=1), late_by(t.replace(day=1), e, t)))
