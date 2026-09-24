# The lanes banner

| File | What it is |
| --- | --- |
| `banner.png` | **The banner.** Shown at the top of this repo and of the plugin's README. Generated; never edit it by hand. |
| `notes.txt` | Everything written on the banner: the `version:` line and the four panels (top-left **What's new**, top-right **The lanes**, bottom-left **Get started**, bottom-right **How it works**). The format is at the top of `make_banner.py`. Edit this on every release. |
| `make_banner.py` | Writes `notes.txt` and the plugin version onto `layout.png`, producing `banner.png`. |
| `layout.png` | **The backdrop** the generator draws onto: the artwork with the version line and audit strip cleared. Made by `make_layout.py`. |
| `make_layout.py` | Rebuilds `layout.png` from `source-gpt.png`. Only needed when the artwork itself changes — a version bump does not touch it. |
| `source-gpt.png` | **The current artwork** (2026-09-18): a fully composed banner the author had made with GPT, kept exactly as delivered. |
| `check_banner.py` | Used by the smoke test: fails when `banner.png` or `notes.txt` does not match `plugin.json`. |
| `base.png`, `layout_base.py`, `clean_base.py` | **The previous artwork's pipeline** (2026-09-17), kept so it can be gone back to. Nothing in the current build reads them. |
| `source-original.png` | The 2026-09-17 artwork (made with ChatGPT and hand-edited), kept so `base.png` can be rebuilt. |

## Why the artwork is a backdrop and not simply the banner

The picture the author commissioned was already complete — panels, text, version number, everything. It
could not be dropped in as `banner.png` all the same, because two things on a banner go stale on
every release: the version number and the **What's new** panel. A finished image freezes both, and
the smoke test rightly fails a banner that does not match `plugin.json`.

So the artwork becomes the backdrop, and the generator keeps writing the parts that change. The
picture is theirs; the words stay true.

⚠️ **That also repaired a real defect in the artwork, by construction.** Its install lines read
`TeMeister/claude-plugins` and `lanes@teMeister-plugins` — the account name is missing its "f" in
both, so anyone typing what they saw would get "repository not found". Because those lines are drawn
from `notes.txt`, regenerating them corrects the spelling without anyone having to catch it. Worth
remembering the next time a finished image is offered as a banner: **artwork can carry text, and
text can be wrong.**

## On every version bump

1. Edit `notes.txt`: set `version:` to the new version, rewrite **What's new** with only the most
   important points, and add any new command to **The lanes**. Short lines; the script refuses
   text that does not fit, and the test fails if a command in `plugins/lanes/commands/` is not listed.
2. Run `python assets/banner/make_banner.py` (needs Pillow).
3. Commit `notes.txt` and `banner.png` with the version bump.

The smoke test fails if step 1 or 2 was skipped, the same way it fails when `CHANGELOG.md` is behind.
The version number under the logo is always read from `plugin.json`.
