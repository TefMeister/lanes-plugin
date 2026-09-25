"""Build base.png: the banner artwork with the hand-edited patches repaired and the
two text panels emptied, ready for make_banner.py to write the notes and version into.

Run once, or again only if the artwork itself changes:
    python clean_base.py [original.png]

Needs Pillow and numpy.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

HERE = Path(__file__).resolve().parent
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "source-original.png"
OUT = HERE / "base.png"

# ---- settings -------------------------------------------------------------
# Rectangles are (left, top, right, bottom) in pixels of the 1983x793 artwork.
TOP_LEFT_PATCHES = [(4, 50, 334, 137), (4, 128, 196, 321), (184, 257, 240, 291)]
TOP_RIGHT_INTERIOR = (1707, 58, 1960, 196)      # inside the version panel's frame
BOTTOM_LEFT_INTERIOR = (0, 566, 195, 733)       # inside the bar-chart frame
STAR_BOX = (1690, 490, 1983, 736)               # the Claude star and its black patch

# Clean background to borrow scanline texture from (below the PLUGIN line).
TEXTURE_DONOR = (1240, 588, 1600, 690)
BACKGROUND_CAP = np.array([10, 34, 12], np.float32)   # never drag a bright line into a fill
ANCHOR_REACH = 40                                     # px either side sampled per row
TEXTURE_STRENGTH = 0.9

CHART_BARS = [  # (left, right, top) - all bars end at CHART_BASELINE
    (25, 48, 588), (72, 95, 624), (116, 139, 632), (161, 185, 600)]
CHART_BASELINE = 718
CHART_COLOURS = [(10, 118, 36), (7, 86, 26), (7, 92, 28), (9, 108, 32)]
CHART_SEGMENT = 26            # px between the faint breaks in each bar

STAR_FILL = (6, 81, 17)
STAR_RIM_MID = (20, 140, 40)
STAR_RIM_HIGH = (90, 225, 110)
STAR_GLOW = (10, 120, 30)
SUPERSAMPLE = 4
# ---------------------------------------------------------------------------


def rect_mask(shape, rects):
    m = np.zeros(shape, bool)
    for x0, y0, x1, y1 in rects:
        m[y0:y1, x0:x1] = True
    return m


def dilate(mask, size):
    img = Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(size))
    return np.array(img) > 0


def texture(img, shape):
    """High-frequency scanline detail from a clean patch, tiled over the whole image."""
    x0, y0, x1, y1 = TEXTURE_DONOR
    patch = img[y0:y1, x0:x1]
    smooth = np.array(Image.fromarray(patch.astype(np.uint8)).filter(ImageFilter.GaussianBlur(12))).astype(np.float32)
    detail = patch - smooth
    reps = (shape[0] // detail.shape[0] + 1, shape[1] // detail.shape[1] + 1, 1)
    return np.tile(detail, reps)[:shape[0], :shape[1]]


def fill(img, hole, detail):
    """Repaint masked pixels: per-row background level from clean neighbours, plus borrowed texture."""
    out = img.copy()
    H, W, _ = img.shape
    for y in np.nonzero(hole.any(axis=1))[0]:
        row_hole = hole[y]
        xs = np.nonzero(row_hole)[0]
        runs = np.split(xs, np.nonzero(np.diff(xs) > 1)[0] + 1)
        for run in runs:
            a, z = run[0], run[-1]
            left = img[y, max(a - ANCHOR_REACH, 0):a][~row_hole[max(a - ANCHOR_REACH, 0):a]]
            right = img[y, z + 1:min(z + 1 + ANCHOR_REACH, W)][~row_hole[z + 1:min(z + 1 + ANCHOR_REACH, W)]]
            lv = np.minimum(np.median(left, axis=0), BACKGROUND_CAP) if len(left) else None
            rv = np.minimum(np.median(right, axis=0), BACKGROUND_CAP) if len(right) else None
            lv = rv if lv is None else lv
            rv = lv if rv is None else rv
            if lv is None:
                lv = rv = BACKGROUND_CAP * 0.5
            t = np.linspace(0, 1, len(run))[:, None]
            out[y, run] = lv * (1 - t) + rv * t + detail[y, run] * TEXTURE_STRENGTH
    return np.clip(out, 0, 255)


def draw_chart(img):
    for (x0, x1, top), colour in zip(CHART_BARS, CHART_COLOURS):
        c = np.array(colour, np.float32)
        img[top:CHART_BASELINE, x0:x1] = c
        img[top:top + 2, x0:x1] = np.minimum(c * 1.6, 255)          # lit top edge
        img[top:CHART_BASELINE, x0:x0 + 1] = c * 0.6                 # soft sides
        img[top:CHART_BASELINE, x1 - 1:x1] = c * 0.6
        for y in range(CHART_BASELINE - CHART_SEGMENT, top + 4, -CHART_SEGMENT):
            img[y:y + 1, x0:x1] = c * 0.55


def star_mask(img):
    x0, y0, x1, y1 = STAR_BOX
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    box = rect_mask(r.shape, [STAR_BOX])
    green = (g > 55) & (r < 40) & (b < 45) & (g > r + 40)
    orange = (r > g + 20) & (r > 60)
    star = box & (green | orange)
    closed = Image.fromarray((star * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    star = np.array(closed) > 127
    black = box & (img.sum(axis=2) < 6)
    return star, black


def draw_star(img, star):
    x0, y0, x1, y1 = STAR_BOX
    S = SUPERSAMPLE
    m = Image.fromarray((star * 255).astype(np.uint8)).crop(STAR_BOX)
    big = m.resize((m.width * S, m.height * S), Image.BICUBIC).filter(ImageFilter.GaussianBlur(3))
    big = Image.fromarray((np.array(big) > 127).astype(np.uint8) * 255)

    def down(im):
        return np.array(im.resize((x1 - x0, y1 - y0), Image.LANCZOS)).astype(np.float32)[..., None] / 255

    shape = down(big)
    in1 = down(big.filter(ImageFilter.MinFilter(2 * S + 1)))
    in3 = down(big.filter(ImageFilter.MinFilter(6 * S + 1)))
    glow = np.array(Image.fromarray((shape[..., 0] * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(6))).astype(np.float32)[..., None] / 255
    region = img[y0:y1, x0:x1]
    region = region + np.array(STAR_GLOW, np.float32) * glow * (1 - shape) * 0.55
    colour = (np.array(STAR_RIM_HIGH, np.float32) * (shape - in1)
              + np.array(STAR_RIM_MID, np.float32) * (in1 - in3)
              + np.array(STAR_FILL, np.float32) * in3)
    img[y0:y1, x0:x1] = region * (1 - shape) + colour


def main():
    img = np.array(Image.open(SRC).convert("RGB")).astype(np.float32)
    detail = texture(img, img.shape[:2])
    star, black = star_mask(img)

    hole = rect_mask(img.shape[:2], TOP_LEFT_PATCHES + [TOP_RIGHT_INTERIOR, BOTTOM_LEFT_INTERIOR])
    hole |= dilate(star | black, 7) & rect_mask(img.shape[:2], [STAR_BOX])

    img = fill(img, hole, detail)
    draw_chart(img)
    draw_star(img, star)
    Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(OUT, optimize=True)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
