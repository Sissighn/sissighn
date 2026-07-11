"""
Text -> SVG path conversion.

Why paths instead of <text font-family="...">: GitHub serves README images
through its camo proxy, which will not load webfonts. Any font-family we name
would silently fall back to the visitor's default serif. Converting glyphs to
vector paths means the lettering renders identically for everyone, with no
font installed on their side.
"""

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont


class Face:
    def __init__(self, path, wght=None):
        font = TTFont(path)
        if wght is not None and "fvar" in font:
            font = instantiateVariableFont(font, {"wght": wght})
        self.font = font
        self.upm = font["head"].unitsPerEm
        self.glyphset = font.getGlyphSet()
        self.cmap = font.getBestCmap()
        self.hmtx = font["hmtx"]
        try:
            self.kern = font["kern"].kernTables[0].kernTable
        except Exception:
            self.kern = {}

    def _glyph_name(self, ch):
        return self.cmap.get(ord(ch))

    def width(self, text, size, tracking=0.0):
        """Advance width of `text` at font-size `size` (px)."""
        scale = size / self.upm
        total = 0.0
        prev = None
        for ch in text:
            gn = self._glyph_name(ch)
            if gn is None:
                total += size * 0.3
                prev = None
                continue
            total += self.hmtx[gn][0] * scale
            if prev is not None:
                total += self.kern.get((prev, gn), 0) * scale
            total += tracking
            prev = gn
        return total

    def path(self, text, size, x=0.0, y=0.0, tracking=0.0, anchor="start"):
        """Return an SVG path `d` string for `text`, baseline at (x, y)."""
        scale = size / self.upm
        if anchor == "middle":
            x -= self.width(text, size, tracking) / 2
        elif anchor == "end":
            x -= self.width(text, size, tracking)

        d = []
        pen_x = x
        prev = None
        for ch in text:
            gn = self._glyph_name(ch)
            if gn is None:
                pen_x += size * 0.3
                prev = None
                continue
            if prev is not None:
                pen_x += self.kern.get((prev, gn), 0) * scale

            pen = SVGPathPen(self.glyphset)
            self.glyphset[gn].draw(pen)
            seg = pen.getCommands()
            if seg:
                # y flips: font coords go up, SVG goes down
                d.append(
                    f'<g transform="translate({pen_x:.2f} {y:.2f}) '
                    f'scale({scale:.5f} {-scale:.5f})"><path d="{seg}"/></g>'
                )
            pen_x += self.hmtx[gn][0] * scale + tracking
            prev = gn
        return "".join(d)


def text_path(face, text, size, x, y, fill, tracking=0.0, anchor="start", opacity=None, extra=""):
    """Full <g> element with fill, ready to drop into an SVG."""
    inner = face.path(text, size, x, y, tracking, anchor)
    op = f' opacity="{opacity}"' if opacity is not None else ""
    return f'<g fill="{fill}"{op}{extra}>{inner}</g>'
