"""Hook shim: run tools/compact.py <mode> (pre | post | end) with this hook's stdin.

The early summary (0.63.0, PROTOCOL section 21). Silent on any failure: a hook here must never block
a summary or the end of a session. LANES_COMPACT=0 turns all three off.
"""
import os
import sys

if os.environ.get("LANES_COMPACT", "1") == "0" or len(sys.argv) < 2:
    sys.exit(0)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
try:
    import compact
    sys.exit(compact.main([sys.argv[1]]))
except Exception:  # noqa: BLE001
    sys.exit(0)
