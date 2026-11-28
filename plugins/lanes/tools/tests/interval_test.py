"""interval_test.py - how often a regular job comes round: days, or once a month (0.125.2, 2026-11-28).

Pure date sums, plus lanes.conf read through LANES_CONFIG in a temp folder. Nothing else is touched. Exit 0 = pass."""
import datetime
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import interval  # noqa: E402

D = datetime.date
fails = 0


def check(ok, what):
    global fails
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        fails += 1


M = interval.MONTH
check(interval.parse("month") == M and interval.parse("Monthly") == M, "'month' and 'monthly' read as once a month")
check(interval.parse("30") == 30 and interval.parse("") == 7 and interval.parse("soon") == 7, "days, else 7")
check(interval.late_by(D(2026, 11, 28), M, D(2026, 11, 30)) is None, "monthly: same month, not due")
check(interval.late_by(D(2026, 11, 28), M, D(2026, 12, 1)) == 0, "monthly: due on the 1st of the next month")
check(interval.late_by(D(2026, 11, 28), M, D(2026, 12, 5)) == 4, "monthly: 4 days late on the 5th")
check(interval.late_by(D(2026, 12, 3), M, D(2026, 12, 31)) is None, "monthly: a late run on the 3rd holds to the month end")
check(interval.late_by(D(2026, 12, 15), M, D(2027, 1, 1)) == 0, "monthly: across the year end")
check(interval.late_by(D(2026, 11, 21), 7, D(2026, 11, 27)) is None, "7 days: day 6 not due")
check(interval.late_by(D(2026, 11, 21), 7, D(2026, 11, 28)) == 0, "7 days: due on day 7")
check(interval.words(M) == "once a month" and interval.words(7) == "every 7 days", "the words")

T = tempfile.mkdtemp(prefix="interval-")
conf = os.path.join(T, "lanes.conf")
os.environ["LANES_CONFIG"] = conf
check(interval.fullscan_every() == 7, "no lanes.conf: every 7 days")
with open(conf, "w", encoding="utf-8") as f:
    f.write("# fullscan_every = 3\nfullscan_every = month   # Tefa 2026-11-28\n")
check(interval.fullscan_every() == M, "fullscan_every = month (a note after it, a commented line before it)")
with open(conf, "w", encoding="utf-8") as f:
    f.write("fullscan_every = 14\n")
check(interval.fullscan_every() == 14, "fullscan_every = 14")

print("interval_test: %s" % ("all passed" if not fails else "%d FAILED" % fails))
sys.exit(1 if fails else 0)
