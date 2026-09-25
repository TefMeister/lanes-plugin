"""Rebuild layout.png (the backdrop make_banner.py writes onto) from source-gpt.png.

    python make_layout.py

You only need this when the ARTWORK changes. A normal version bump does not touch it —
edit notes.txt and run make_banner.py instead.

2026-09-18: the artwork was replaced. The author had a fully composed banner made with GPT —
better proportioned than the old one, with the panels inset from the edges and a screen
bezel around everything — and asked for it to become the banner. It could not simply be
dropped in as banner.png: the version number and the "What's new" panel go stale on every
release, and the smoke test (rightly) fails a banner that does not match plugin.json.

So the artwork becomes the BACKDROP instead, and the generator keeps writing the parts
that change. That way the picture is theirs and the words stay true.

⚠️ It also quietly fixed a real defect. The artwork's install lines read
`TeMeister/claude-plugins` and `lanes@teMeister-plugins` — the "f" is missing from the
account name in both, so anyone typing what they saw would get "repository not found".
Because make_banner.py draws those lines from notes.txt, regenerating them corrects the
spelling by construction rather than by anyone noticing.

Two strips have to be cleared, because the generator draws over them and any leftover
would show through the new text.
"""
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
SRC = HERE / "source-gpt.png"
OUT = HERE / "layout.png"

image = Image.open(SRC).convert("RGB")
pixels = np.asarray(image).astype(np.uint8).copy()


def mirror_fill(x0, y0, x1, y1):
    """Average the band above (flipped) with the band below.

    Cheap and seamless — but ONLY when both neighbouring bands are empty backdrop. If
    either holds artwork this stamps a ghost of it, which is exactly what happened when
    it was first tried under the version line: the PLUGIN wordmark sits directly above
    and appeared upside down beneath the version.
    """
    height = y1 - y0
    above = pixels[y0 - height:y0, x0:x1].astype(float)
    below = pixels[y1:y1 + height, x0:x1].astype(float)
    pixels[y0:y1, x0:x1] = ((above[::-1] + below) / 2.0).astype(np.uint8)


def copy_band(x0, y0, x1, y1, src_y):
    """Copy a clean band of the same width from another height.

    The backdrop texture is horizontal scanlines, so any empty band reads correctly
    somewhere else. This is the one to use where mirror_fill would ghost.
    """
    height = y1 - y0
    pixels[y0:y1, x0:x1] = pixels[src_y:src_y + height, x0:x1]


# "version 0.11.2" as the artwork drew it, at (991, 561), plus the short yellow rule
# under it. make_banner.py redraws the version at VERSION_CENTRE.
copy_band(855, 536, 1135, 596, src_y=612)

# The audit strip along the bottom, rows 702..712. make_banner.py redraws it at AUDIT_CENTRE.
#
# ⚠️ This used mirror_fill and looked fine until the text was recoloured yellow, at which point
# a green rule was clearly running straight THROUGH the letters. It was a ghost, from the same
# mistake as the version strip: the band above holds the artwork's decorative rule at rows
# 679..682, and flipping it landed that rule at 709..712 — dead centre of the text. It hid inside
# a green line drawn in the same green, and only showed up once the colour changed.
# **A patch that hides in one colour scheme is not a patch.** Measured instead: rows 606..663 and
# 713..783 are the only bands of 24+ rows with no content across this width, so the fill comes
# from 630.
copy_band(520, 694, 1470, 720, src_y=630)

Image.fromarray(pixels).save(OUT)
print("wrote %s from %s" % (OUT.name, SRC.name))
