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
    def __init__(self, path, wght=None, **axes):
        """Extra keyword args pin variable-font axes, e.g. opsz=72 for Ballet."""
        font = TTFont(path)
        if wght is not None:
            axes["wght"] = wght
        if axes and "fvar" in font:
            present = {a.axisTag for a in font["fvar"].axes}
            wanted = {k: v for k, v in axes.items() if k in present}
            if wanted:
                font = instantiateVariableFont(font, wanted)
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

    def ink_bounds(self, text, size, tracking=0.0):
        """Visual extents (x_min, y_min, x_max, y_max) of the drawn outlines,
        relative to a baseline origin at (0, 0), y growing downwards.

        Script faces like Pinyon have swashes that reach well past the
        advance width, so laying glyphs out by `width()` alone makes them
        collide with whatever sits next to them.
        """
        from fontTools.pens.boundsPen import BoundsPen

        scale = size / self.upm
        pen_x = 0.0
        prev = None
        xs_min = ys_min = xs_max = ys_max = None
        for ch in text:
            gn = self._glyph_name(ch)
            if gn is None:
                pen_x += size * 0.3
                prev = None
                continue
            if prev is not None:
                pen_x += self.kern.get((prev, gn), 0) * scale
            bp = BoundsPen(self.glyphset)
            self.glyphset[gn].draw(bp)
            if bp.bounds:
                x0, y0, x1, y1 = bp.bounds
                b = (pen_x + x0 * scale, -y1 * scale, pen_x + x1 * scale, -y0 * scale)
                if xs_min is None:
                    xs_min, ys_min, xs_max, ys_max = b
                else:
                    xs_min, ys_min = min(xs_min, b[0]), min(ys_min, b[1])
                    xs_max, ys_max = max(xs_max, b[2]), max(ys_max, b[3])
            pen_x += self.hmtx[gn][0] * scale + tracking
            prev = gn
        if xs_min is None:
            return (0.0, 0.0, 0.0, 0.0)
        return (xs_min, ys_min, xs_max, ys_max)

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
