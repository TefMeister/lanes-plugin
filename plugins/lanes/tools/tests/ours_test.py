"""ours_test.py - our own apps and libraries as optional downloads (0.93.0), with a made-up release in a temporary
folder: nothing is fetched from the internet and nothing is installed. Exit 0 = pass."""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

fails = 0


def check(ok, what):
    global fails
    print(("  ok    " if ok else "FAIL: ") + what)
    fails += not ok


def main():
    t = tempfile.mkdtemp()
    try:
        os.environ["LANES_OURS_DIR"] = os.path.join(t, "ours")
        os.environ["LANES_OURS_APPS"] = os.path.join(t, "Programs")
        os.environ["LANES_CONFIG"] = os.path.join(t, "lanes.conf")
        os.environ["LANES_STATE_DIR"] = os.path.join(t, "state")
        open(os.environ["LANES_CONFIG"], "w").write("ours_window_view = on\n")
        z = os.path.join(t, "WindowView-v1.2.zip")
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("WindowView/install.ps1", "# stand-in")
            f.writestr("WindowView/WindowView.exe", "not really a program")
        good = hashlib.sha256(open(z, "rb").read()).hexdigest()
        sums = os.path.join(t, "SHA256SUMS.txt")
        fake = os.path.join(t, "fake.json")

        def release(tag, digest):
            open(sums, "w").write(f"{digest} *WindowView-v1.2.zip\n")
            json.dump({"TefMeister/window-view-vr": {"tag_name": tag, "assets": [
                {"name": "WindowView-v1.2.zip", "browser_download_url": "file:" + z},
                {"name": "SHA256SUMS.txt", "browser_download_url": "file:" + sums}]}}, open(fake, "w"))
        os.environ["LANES_OURS_FAKE"] = fake
        import ours
        import features

        release("v1.2", "0" * 64)
        try:
            ours.get("window_view")
            check(False, "an app that does not match its checksum is refused")
        except RuntimeError as e:
            check("does not match" in str(e) and not ours.got("window_view"),
                  "an app that does not match its checksum is refused, and nothing is noted as got")
        release("v1.2", good)
        lines = ours.get("window_view")
        check(ours.got("window_view") == "v1.2" and os.path.isfile(
            os.path.join(t, "Programs", "WindowView", "WindowView.exe")), f"a checked app is installed ({lines[0]})")
        check("LANES_OUTSIDE_DIR" not in os.environ, "the temporary download folder is not left behind as a setting")
        check(ours.newer() == [], "nothing newer when the newest is got")
        release("v1.3", good)
        check(any("v1.2 -> v1.3" in n for n in ours.newer()), "a newer release is named")
        none = ours.get("hand_poser")
        check("no release to download yet" in none[0] and not ours.got("hand_poser"),
              "an app with no release says so and installs nothing")
        check(ours.is_on("window_view") and not ours.is_on("hand_poser"), "each one is its own extra, by lanes.conf")
        f = features.FEATURES.get("ours_cross_engine_library", {})
        check(f.get("link", "").endswith("TefMeister/flat-to-vr-cross-engine-research") and f.get("ask_on_update")
              and f.get("set") == "ours", "its extra links to our GitHub, sits in our set and is asked before it is on")
        check(not any(n in ours.TOOLS for n in ("game_bridge", "out_of_focus", "hand_freeze", "vr_bench")),
              "private apps and the ones with their own installers are not listed twice")
        check(not features.lint(), "the extras list stays complete: " + "; ".join(features.lint()))
    finally:
        shutil.rmtree(t, ignore_errors=True)
    print(f"ours: {'FAIL' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
