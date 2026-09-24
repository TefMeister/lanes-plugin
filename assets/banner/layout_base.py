"""Build layout.png from base.png: move the LANES / PLUGIN logo down, and put the
Claude Code title with the star above it (the author's layout of 2026-09-17, made symmetrical).

    python layout_base.py

Run once after clean_base.py, or again only if the artwork changes. Needs Pillow and numpy.
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from clean_base import fill, star_mask, texture

HERE = Path(__file__).resolve().parent
BASE = HERE / "base.png"
SOURCE = HERE / "source-original.png"
OUT = HERE / "layout.png"

# ---- settings -------------------------------------------------------------
CENTRE_X = 991                            # the image's (and the logo's) centre line
LOGO_BOX = (372, 180, 1612, 596)          # LANES + PLUGIN and their glow, in base.png
LOGO_SHIFT = 51                           # px down (the author's spacing of 2026-09-17)
LOGO_ALPHA_FROM = 22                      # brightness where the moved logo starts to show
LOGO_ALPHA_SPAN = 70                      # ...and is fully opaque

TITLE_TEXT = "CLAUDE CODE"
TITLE_PREFIX = "for"
TITLE_SIZE = 46
PREFIX_SIZE = 24
TITLE_COLOUR = (40, 200, 90)
PREFIX_COLOUR = (30, 150, 70)
TITLE_LETTER_GAP = 5
TITLE_BASELINE_Y = 147                    # vertical centre of the title row
TITLE_NUDGE_X = -10                       # the author's optical centring of the star + text group
STAR_HEIGHT = 104
STAR_GAP = 14                             # between the star and the text
STAR_ONLY = (1700, 496, 1945, 734)        # the star itself, clear of the frame lines
FONT_CANDIDATES = ["bahnschrift.ttf", "C:/Windows/Fonts/bahnschrift.ttf", "DejaVuSans.ttf"]

STAR_FILL = (6, 81, 17)
STAR_RIM = (80, 220, 105)
GLOW_RADIUS = 4
# ---------------------------------------------------------------------------


def font(size, light=True):
    for name in FONT_CANDIDATES:
        try:
            f = ImageFont.truetype(name, size)
        except OSError:
            continue
        if light:
            try:
                f.set_variation_by_name("Light")
            except Exception:
                pass
        return f
    raise SystemExit("layout_base: no usable font found")


def move_logo(img):
    x0, y0, x1, y1 = LOGO_BOX
    logo = img[y0:y1, x0:x1].copy()
    hole = np.zeros(img.shape[:2], bool)
    hole[y0:y1, x0:x1] = True
    cleared = fill(img, hole, texture(img, img.shape[:2]))
    lum = logo.max(axis=2)
    alpha = np.clip((lum - LOGO_ALPHA_FROM) / LOGO_ALPHA_SPAN, 0, 1)[..., None]
    ty0, ty1 = y0 + LOGO_SHIFT, y1 + LOGO_SHIFT
    under = cleared[ty0:ty1, x0:x1]
    cleared[ty0:ty1, x0:x1] = np.maximum(under, logo * alpha + under * (1 - alpha))
    return cleared


def star_image(height):
    source = np.array(Image.open(SOURCE).convert("RGB")).astype(np.float32)
    star, _ = star_mask(source)
    keep = np.zeros_like(star)
    x0, y0, x1, y1 = STAR_ONLY
    keep[y0:y1, x0:x1] = True
    star &= keep
    # drop specks: open the mask (shrink, then grow back)
    opened = Image.fromarray((star * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(5)).filter(ImageFilter.MaxFilter(5))
    star &= np.array(opened) > 0
    ys, xs = np.nonzero(star)
    crop = Image.fromarray((star[ys.min():ys.max() + 1, xs.min():xs.max() + 1] * 255).astype(np.uint8))
    width = round(crop.width * height / crop.height)
    big = crop.resize((width * 4, height * 4), Image.BICUBIC).filter(ImageFilter.GaussianBlur(3))
    big = Image.fromarray((np.array(big) > 127).astype(np.uint8) * 255)
    shape = big.resize((width, height), Image.LANCZOS)
    inner = big.filter(ImageFilter.MinFilter(9)).resize((width, height), Image.LANCZOS)
    s = np.array(shape).astype(np.float32)[..., None] / 255
    i = np.array(inner).astype(np.float32)[..., None] / 255
    rgb = np.array(STAR_RIM, np.float32) * (s - i) + np.array(STAR_FILL, np.float32) * i
    rgba = np.concatenate([rgb / np.maximum(s, 1e-6), s * 255], axis=2)
    return Image.fromarray(np.clip(rgba, 0, 255).astype(np.uint8), "RGBA")


def spaced_width(draw, text, f, gap):
    return sum(draw.textlength(ch, font=f) for ch in text) + gap * (len(text) - 1)


def draw_spaced(draw, x, y, text, f, gap, colour):
    for ch in text:
        draw.text((x, y), ch, font=f, fill=colour + (255,), anchor="lm")
        x += draw.textlength(ch, font=f) + gap
    return x


def draw_title(canvas):
    star = star_image(STAR_HEIGHT)
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    title_f, prefix_f = font(TITLE_SIZE), font(PREFIX_SIZE)
    prefix_w = spaced_width(d, TITLE_PREFIX, prefix_f, 2) + 14
    title_w = spaced_width(d, TITLE_TEXT, title_f, TITLE_LETTER_GAP)
    total = star.width + STAR_GAP + prefix_w + title_w
    x = CENTRE_X - total / 2 + TITLE_NUDGE_X
    layer.alpha_composite(star, (round(x), TITLE_BASELINE_Y - star.height // 2))
    x += star.width + STAR_GAP
    x = draw_spaced(d, x, TITLE_BASELINE_Y + 4, TITLE_PREFIX, prefix_f, 2, PREFIX_COLOUR) + 12
    draw_spaced(d, x, TITLE_BASELINE_Y, TITLE_TEXT, title_f, TITLE_LETTER_GAP, TITLE_COLOUR)
    canvas.alpha_composite(layer.filter(ImageFilter.GaussianBlur(GLOW_RADIUS)))
    canvas.alpha_composite(layer)


def main():
    img = np.array(Image.open(BASE).convert("RGB")).astype(np.float32)
    img = move_logo(img)
    canvas = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGBA")
    draw_title(canvas)
    canvas.convert("RGB").save(OUT, optimize=True)
    print("wrote %s" % OUT)


if __name__ == "__main__":
    main()
