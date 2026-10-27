"""outside_test.py - other people's tools as optional downloads (0.92.0), with a made-up release in a temporary folder:
nothing is fetched from the internet and nothing is installed. Exit 0 = pass."""
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
        os.environ["LANES_OUTSIDE_DIR"] = os.path.join(t, "tools")
        os.environ["LANES_CONFIG"] = os.path.join(t, "lanes.conf")
        os.environ["LANES_STATE_DIR"] = os.path.join(t, "state")
        open(os.environ["LANES_CONFIG"], "w").write("outside_uevr_renderdoc = on\n")
        z = os.path.join(t, "Thing-v2.zip")
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("inside.txt", "hello")
        good = hashlib.sha256(open(z, "rb").read()).hexdigest()
        sums = os.path.join(t, "SHA256SUMS.txt")
        fake = os.path.join(t, "fake.json")

        def release(tag, digest):
            open(sums, "w").write(f"{digest} *Thing-v2.zip\n")
            json.dump({"elliotttate/UEVR-RenderDoc-Capture": {"tag_name": tag, "assets": [
                {"name": "Thing-v2.zip", "browser_download_url": "file:" + z},
                {"name": "SHA256SUMS.txt", "browser_download_url": "file:" + sums}]}}, open(fake, "w"))
        os.environ["LANES_OUTSIDE_FAKE"] = fake
        import outside
        import features

        release("v2", "0" * 64)
        try:
            outside.get("uevr_renderdoc")
            check(False, "a download that does not match its checksum is refused")
        except RuntimeError as e:
            check("does not match" in str(e) and not outside.got("uevr_renderdoc"),
                  "a download that does not match its checksum is refused, and nothing is noted as got")
        release("v2", good)
        lines = outside.get("uevr_renderdoc")
        check(outside.got("uevr_renderdoc") == "v2" and os.path.isfile(
            os.path.join(t, "tools", "uevr_renderdoc", "v2", "inside.txt")), f"a checked zip is unpacked ({lines[0]})")
        check(outside.newer() == [], "nothing newer when the newest is got")
        release("v3", good)
        check(any("v2 -> v3" in n for n in outside.newer()), "a newer release is named")
        check(outside.is_on("uevr_renderdoc") and not outside.is_on("xrfps"),
              "each tool is its own extra, on or off by lanes.conf")
        f = features.FEATURES.get("outside_obs_mirror", {})
        check(f.get("link", "").endswith("elliotttate/OpenXR-Layer-OBSMirror") and f.get("ask_on_update"),
              "its extra links to the maker's GitHub and is asked before it is on")
        check(not features.lint(), "the extras list stays complete: " + "; ".join(features.lint()))
        link = outside.get("uevr_6dof_window")
        check("github.com/elliotttate/UEVR-6DOF-Window" in link[0], "a link-only tool prints its link")
    finally:
        shutil.rmtree(t, ignore_errors=True)
    print(f"outside: {'FAIL' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
