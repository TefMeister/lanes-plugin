"""Write the four info panels and the version number onto layout.png, producing banner.png.

    python make_banner.py

Run it on EVERY version bump, after editing notes.txt. The version comes from
plugins/lanes/.claude-plugin/plugin.json and must match the `version:` line in notes.txt.
banner.png carries both the version and a hash of notes.txt, so the lanes smoke test fails
when the banner is stale. Needs Pillow.

notes.txt format
    version: 1.2.3
    [top-left] PANEL TITLE      starts a panel (top-left, top-right, bottom-left, bottom-right)
    # HEADING                   a small heading inside the panel
    left | right                a two-column row (used for the command list)
    .. text                     a continuation line: indented, no bullet
    anything else               a bulleted line
"""
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from PIL.PngImagePlugin import PngInfo

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
PLUGIN_JSON = REPO / "plugins" / "lanes" / ".claude-plugin" / "plugin.json"
BASE = HERE / "layout.png"
NOTES = HERE / "notes.txt"
OUT = HERE / "banner.png"

# ---- settings -------------------------------------------------------------
FONT_CANDIDATES = ["bahnschrift.ttf", "C:/Windows/Fonts/bahnschrift.ttf", "DejaVuSans.ttf"]

# Four panels, mirrored left/right, matching the artwork in base.png.
#
# 2026-09-18: the boxes were widened from 332 to 536 and pulled 34 px in from the edges,
# to sit exactly on the panel frames in the new base art (the author's banner, made with GPT).
# They are deliberately a few pixels LARGER than the frames painted in that art, because
# the generator fills each box opaquely: any overhang covers the underlying frame instead
# of leaving a stray stroke poking out. Measured off the art, not guessed - the frames run
# x 36..564 / 1417..1946 and y 40..376 / 396..720.
# ⚠️ Top and bottom heights DIFFER in that art, so the two rows have their own constants;
# a single symmetric margin cannot express it and used to force the bottom row 33 px down,
# into the audit strip.
IMAGE_W, IMAGE_H = 1983, 793
PANEL_MARGIN_X = 34            # from the left and right edges
PANEL_WIDTH = 536
PANEL_TOP_Y = 36               # top row: y 36..380
PANEL_TOP_HEIGHT = 344
PANEL_BOTTOM_Y = 392           # bottom row: y 392..724
PANEL_BOTTOM_HEIGHT = 332
_L, _R = PANEL_MARGIN_X, IMAGE_W - PANEL_MARGIN_X - PANEL_WIDTH
_T, _B = PANEL_TOP_Y, PANEL_BOTTOM_Y
PANELS = {
    "top-left": (_L, _T, _L + PANEL_WIDTH, _T + PANEL_TOP_HEIGHT),
    "top-right": (_R, _T, _R + PANEL_WIDTH, _T + PANEL_TOP_HEIGHT),
    "bottom-left": (_L, _B, _L + PANEL_WIDTH, _B + PANEL_BOTTOM_HEIGHT),
    "bottom-right": (_R, _B, _R + PANEL_WIDTH, _B + PANEL_BOTTOM_HEIGHT),
}

PANEL_FILL = (1, 9, 3, 255)
FRAME = (16, 150, 60)
FRAME_WIDTH = 2
CUT = 10                       # size of the cut corners
GLOW_RADIUS = 3

HEADER_HEIGHT = 30
HEADER_FILL = (16, 150, 60)
HEADER_TEXT = (0, 12, 4)
HEADER_SIZE = 18

PAD = 12
HEADING_SIZE = 14
HEADING_COLOUR = (60, 205, 95)
ITEM_SIZE_MAX = 19
ITEM_SIZE_MIN = 12
ITEM_COLOUR = (205, 240, 205)
CMD_COLOUR = (95, 235, 125)
DIM_COLOUR = (110, 170, 120)
LINE_GAP = 5
SECTION_GAP = 9
BULLET = "› "
CONTINUATION_INDENT = 16
COLUMN_GAP = 10

VERSION_CENTRE = (991, 561)    # centred under PLUGIN, measured off the 2026-09-18 base art
VERSION_SIZE = 22
VERSION_COLOUR = (34, 177, 76)
VERSION_LETTER_GAP = 1

# Permanent, on every version: not in notes.txt, so a release edit cannot drop it.
# 2026-09-18, the author's call: the old wording ran nearly the full width of the gap between the two
# bottom panels and read as a paragraph. It said the same thing three times over. One short
# line that lands the single point -- you can check this yourself before installing it --
# beats a long one nobody finishes.
AUDIT_TEXT = "AUDIT IT YOURSELF FIRST  ·  your own Claude Code can check every file  ·  AUDIT.md"
AUDIT_CENTRE = (991, 707)      # measured off the 2026-09-18 base art
AUDIT_SIZE = 19
# 2026-09-18, the author's call: it used to be the same soft green as everything else on that row and
# sank into the backdrop. Yellow is already the artwork's accent -- the road markings down
# the wordmark, the PLUGIN letters, the two rules beside them -- so the line now borrows it
# and belongs to the picture instead of sitting on top of it.
# ⚠️ The two values are SAMPLED, not picked by eye: (248, 230, 48) is the artwork's own
# yellow, the most common tone across its 31,197 yellow pixels, and the wordmark's mean is
# (236, 224, 47). The text is that colour taken down to about 80%, which is dark enough to
# read as a caption rather than compete with the wordmark; the glow behind it is the full
# brightness version, faint and wide, which is what makes the line impossible to miss on a
# near-black background where a dark colour alone would do the opposite.
AUDIT_COLOUR = (198, 184, 38)
AUDIT_GLOW_COLOUR = (248, 230, 48)
AUDIT_GLOW_ALPHA = 105         # faint: a lit sign, not a highlighter
AUDIT_GLOW_RADIUS = 6          # wider than the panels' GLOW_RADIUS, so it reads as a halo
AUDIT_MAX_WIDTH = 1240         # stays clear of the two bottom panels
# ---------------------------------------------------------------------------

_fonts = {}


def font(size, bold=False, light=False):
    key = (size, bold, light)
    if key in _fonts:
        return _fonts[key]
    for name in FONT_CANDIDATES:
        try:
            f = ImageFont.truetype(name, size)
        except OSError:
            continue
        for wanted, flag in (("Bold", bold), ("Light", light)):
            if flag:
                try:
                    f.set_variation_by_name(wanted)
                except Exception:
                    pass
        _fonts[key] = f
        return f
    sys.exit("make_banner: no usable font found (tried %s)" % FONT_CANDIDATES)


def read_notes():
    text = NOTES.read_text(encoding="utf-8").replace("\r", "")
    version, panels, current = None, {}, None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.lower().startswith("version:"):
            version = line.split(":", 1)[1].strip()
        elif line.startswith("[") and "]" in line and "-" in line[1:line.index("]")]:
            where, title = line[1:].split("]", 1)
            if where not in PANELS:
                sys.exit("make_banner: unknown panel [%s] (use %s)" % (where, ", ".join(PANELS)))
            current = panels.setdefault(where, {"title": title.strip(), "rows": []})
        elif current is None:
            sys.exit("make_banner: '%s' comes before any [panel] line" % line)
        elif line.startswith("#"):
            current["rows"].append(("heading", line.lstrip("#").strip().upper()))
        elif line.startswith(".."):
            current["rows"].append(("more", line[2:].strip()))
        elif "|" in line:
            left, right = (part.strip() for part in line.split("|", 1))
            current["rows"].append(("pair", (left, right)))
        else:
            current["rows"].append(("item", line))
    return version, panels, hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def gap_before(kind, index):
    return SECTION_GAP if kind == "heading" and index > 0 else 0


def row_height(kind, size):
    return (HEADING_SIZE if kind == "heading" else size) + LINE_GAP


def content_height(panel, size):
    return sum(gap_before(k, i) + row_height(k, size) for i, (k, _) in enumerate(panel["rows"])) - LINE_GAP


def fits(panel, box, size):
    x0, y0, x1, y1 = box
    inner_w = x1 - x0 - 2 * PAD
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    f = font(size)
    col = pair_column(panel, size)
    h = 0
    for index, (kind, value) in enumerate(panel["rows"]):
        if kind == "item":
            w = probe.textlength(BULLET + value, font=f)
        elif kind == "more":
            w = CONTINUATION_INDENT + probe.textlength(value, font=f)
        elif kind == "pair":
            w = col + probe.textlength(value[1], font=f)
        else:
            w = probe.textlength(value, font=font(HEADING_SIZE, bold=True))
        if w > inner_w:
            return False
        h += gap_before(kind, index) + row_height(kind, size)
    return h <= (y1 - y0) - HEADER_HEIGHT - 2 * PAD


def pair_column(panel, size):
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    lefts = [v[0] for k, v in panel["rows"] if k == "pair"]
    return max((probe.textlength(l, font=font(size, bold=True)) for l in lefts), default=0) + COLUMN_GAP


def glow_text(canvas, pos, text, fnt, colour, glow=True):
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text(pos, text, font=fnt, fill=colour + (255,))
    if glow:
        canvas.alpha_composite(layer.filter(ImageFilter.GaussianBlur(GLOW_RADIUS)))
    canvas.alpha_composite(layer)


def cut_polygon(box):
    x0, y0, x1, y1 = box
    return [(x0 + CUT, y0), (x1 - CUT, y0), (x1, y0 + CUT), (x1, y1 - CUT),
            (x1 - CUT, y1), (x0 + CUT, y1), (x0, y1 - CUT), (x0, y0 + CUT)]


def shared_size(panels):
    """One text size for all panels: the largest that fits every one of them."""
    for size in range(ITEM_SIZE_MAX, ITEM_SIZE_MIN - 1, -1):
        if all(fits(panels[where], box, size) for where, box in PANELS.items()):
            return size
    tight = [panels[w]["title"] for w, b in PANELS.items() if not fits(panels[w], b, ITEM_SIZE_MIN)]
    sys.exit("make_banner: %s does not fit even at %dpx - shorten notes.txt" % (", ".join(tight), ITEM_SIZE_MIN))


def draw_panel(canvas, box, panel, size):
    x0, y0, x1, y1 = box
    poly = cut_polygon(box)

    body = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(body)
    d.polygon(poly, fill=PANEL_FILL)
    # header bar: green with a cut on its lower-right corner
    d.polygon([(x0 + CUT, y0), (x1 - CUT, y0), (x1, y0 + CUT), (x1, y0 + HEADER_HEIGHT - 6),
               (x1 - 6, y0 + HEADER_HEIGHT), (x0, y0 + HEADER_HEIGHT), (x0, y0 + CUT)], fill=HEADER_FILL + (255,))
    canvas.alpha_composite(body)

    frame = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(frame).line(poly + [poly[0]], fill=FRAME + (255,), width=FRAME_WIDTH)
    canvas.alpha_composite(frame.filter(ImageFilter.GaussianBlur(3)))
    canvas.alpha_composite(frame)

    head_font = font(HEADER_SIZE, bold=True)
    glow_text(canvas, (x0 + PAD, y0 + (HEADER_HEIGHT - HEADER_SIZE) // 2 - 1), panel["title"], head_font,
              HEADER_TEXT, glow=False)

    col = pair_column(panel, size)
    body_top, body_h = y0 + HEADER_HEIGHT, (y1 - y0) - HEADER_HEIGHT
    x, y = x0 + PAD, body_top + max(PAD, (body_h - content_height(panel, size)) // 2)
    for index, (kind, value) in enumerate(panel["rows"]):
        y += gap_before(kind, index)
        if kind == "heading":
            glow_text(canvas, (x, y), value, font(HEADING_SIZE, bold=True), HEADING_COLOUR)
        elif kind == "item":
            glow_text(canvas, (x, y), BULLET + value, font(size), ITEM_COLOUR)
        elif kind == "more":
            glow_text(canvas, (x + CONTINUATION_INDENT, y), value, font(size), DIM_COLOUR)
        else:
            glow_text(canvas, (x, y), value[0], font(size, bold=True), CMD_COLOUR)
            glow_text(canvas, (x + col, y), value[1], font(size), ITEM_COLOUR)
        y += row_height(kind, size)


def draw_version(canvas, version):
    text = "version  " + version
    f = font(VERSION_SIZE, light=True)
    probe = ImageDraw.Draw(canvas)
    widths = [probe.textlength(ch, font=f) for ch in text]
    total = sum(widths) + VERSION_LETTER_GAP * (len(text) - 1)
    x = VERSION_CENTRE[0] - total / 2
    y = VERSION_CENTRE[1] - VERSION_SIZE // 2 - 2
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for ch, w in zip(text, widths):
        d.text((x, y), ch, font=f, fill=VERSION_COLOUR + (255,))
        x += w + VERSION_LETTER_GAP
    canvas.alpha_composite(layer.filter(ImageFilter.GaussianBlur(GLOW_RADIUS)))
    canvas.alpha_composite(layer)


def draw_audit(canvas):
    """The audit line: dark yellow text over its own faint, brighter halo.

    Unlike glow_text(), the halo is drawn in a DIFFERENT colour from the text — blurring the
    dark yellow would only have produced a dark smudge, which is the problem this is fixing.
    """
    f = font(AUDIT_SIZE)
    if ImageDraw.Draw(Image.new("RGB", (1, 1))).textlength(AUDIT_TEXT, font=f) > AUDIT_MAX_WIDTH:
        sys.exit("make_banner: the audit line is too wide")

    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).text(AUDIT_CENTRE, AUDIT_TEXT, font=f,
                              fill=AUDIT_GLOW_COLOUR + (AUDIT_GLOW_ALPHA,), anchor="mm")
    canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(AUDIT_GLOW_RADIUS)))

    text = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(text).text(AUDIT_CENTRE, AUDIT_TEXT, font=f,
                              fill=AUDIT_COLOUR + (255,), anchor="mm")
    canvas.alpha_composite(text)


def main():
    plugin_version = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))["version"]
    version, panels, digest = read_notes()
    if version != plugin_version:
        sys.exit("make_banner: notes.txt says %s but plugin.json says %s - update notes.txt first"
                 % (version, plugin_version))
    missing = [p for p in PANELS if p not in panels]
    if missing:
        sys.exit("make_banner: notes.txt has no [%s] panel" % "], [".join(missing))
    canvas = Image.open(BASE).convert("RGBA")
    size = shared_size(panels)
    for where, box in PANELS.items():
        draw_panel(canvas, box, panels[where], size)
    draw_version(canvas, version)
    draw_audit(canvas)
    info = PngInfo()
    info.add_text("lanes-version", version)
    info.add_text("lanes-notes-sha256", digest)
    info.add_text("lanes-audit-line", AUDIT_TEXT)
    canvas.convert("RGB").save(OUT, pnginfo=info, optimize=True)
    print("wrote %s for v%s" % (OUT, version))


if __name__ == "__main__":
    main()
