"""NEXUS HUD widgets: panels, meters, charts, team plates, telemetry."""
import math

from PIL import Image, ImageDraw

from fx import hexpts, neon_circle, neon_line, neon_poly, round_rect, scale, tri
from theme import *

# ------------------------------------------------------------------ background
_BG = None


def background():
    global _BG
    if _BG is not None:
        return _BG
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img, "RGBA")
    # radial glow
    grad = Image.new("RGB", (W, H), (0, 0, 0))
    gd = ImageDraw.Draw(grad)
    steps = 60
    for i in range(steps, 0, -1):
        k = i / steps
        r = (W * 0.72) * k
        cx, cy = W / 2, H * 0.52
        col = scale((10, 22, 40), (1 - k) ** 2 * 1.5)
        gd.ellipse([cx - r, cy - r * 0.78, cx + r, cy + r * 0.78], fill=col)
    img = Image.blend(img, grad, 0.9)
    d = ImageDraw.Draw(img, "RGBA")
    # grid
    for x in range(0, W, 44):
        d.line([(x, 0), (x, H)], fill=(16, 30, 48, 60))
    for y in range(0, H, 44):
        d.line([(0, y), (W, y)], fill=(16, 30, 48, 60))
    for x in range(0, W, 220):
        d.line([(x, 0), (x, H)], fill=(22, 44, 70, 90))
    for y in range(0, H, 220):
        d.line([(0, y), (W, y)], fill=(22, 44, 70, 90))
    # faint hex pattern
    for gy in range(-1, 12):
        for gx in range(-1, 20):
            cx = gx * 118 + (59 if gy % 2 else 0)
            cy = gy * 102
            pts = hexpts(cx, cy, 66, math.pi / 6)
            d.polygon(pts, outline=(20, 40, 64, 46))
    # corner vignette glows
    for (cx, cy, col) in ((0, 0, (0, 40, 70)), (W, H, (60, 0, 20)), (W, 0, (0, 40, 70))):
        for i in range(8, 0, -1):
            r = 260 * i / 8
            d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col + (4,))
    _BG = img
    return img


# ------------------------------------------------------------------ panels
def panel(cv, box, title=None, accent=CYAN, fill=PANEL, edge=LINE_MID, radius=10,
          head=True, tag=None, glow=0.5, alpha=232):
    x0, y0, x1, y1 = box
    d, g = cv.d, cv.g
    d.rounded_rectangle(box, radius=radius, fill=fill + (alpha,),
                        outline=edge + (200,), width=1)
    # top accent line
    if glow:
        g.rectangle([x0 + radius, y0, x1 - radius, y0 + 2], fill=scale(accent, 0.55 * glow))
    # corner ticks
    L = 14
    for (px, py, sx, sy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        d.line([(px + sx * 1, py + sy * L), (px + sx * 1, py + sy * 1), (px + sx * L, py + sy * 1)],
               fill=scale(accent, 0.9) + (230,), width=2)
        g.line([(px + sx * 1, py + sy * L), (px + sx * 1, py + sy * 1), (px + sx * L, py + sy * 1)],
               fill=scale(accent, 0.25), width=6)
    if title and head:
        text(d, (x0 + 14, y0 + 9), title, FUI(15), scale(accent, 0.95), tracking=2.2,
             glow_draw=g, glow_a=0.35)
        if tag:
            tw_, _ = tracked_size(d, tag, FUI(13), 1.6)
            tx = x1 - 14 - tw_
            d.rounded_rectangle([tx - 8, y0 + 8, x1 - 8, y0 + 28], radius=4,
                                fill=scale(accent, 0.16) + (255,))
            text(d, (tx, y0 + 10), tag, FUI(13), accent, tracking=1.6)
    return box


def hline(cv, x0, x1, y, col=LINE_MID, a=1.0):
    cv.d.line([(x0, y), (x1, y)], fill=col + (int(210 * a),), width=1)


# ------------------------------------------------------------------ meters
def bar(cv, box, frac, col, bg=LINE_DIM, segs=0, h=None, glow=True):
    x0, y0, x1, y2 = box
    frac = max(0.0, min(1.0, frac))
    d, g = cv.d, cv.g
    d.rounded_rectangle(box, radius=max(2, (y2 - y0) // 2), fill=bg + (255,))
    w = (x1 - x0) * frac
    if w > 2:
        d.rounded_rectangle([x0, y0, x0 + w, y2], radius=max(2, (y2 - y0) // 2), fill=col)
        if glow:
            g.rounded_rectangle([x0, y0 - 1, x0 + w, y2 + 1], radius=max(2, (y2 - y0) // 2),
                                fill=scale(col, 0.22))
    if segs:
        for i in range(1, segs):
            x = x0 + (x1 - x0) * i / segs
            d.line([(x, y0), (x, y2)], fill=BG + (180,), width=1)


def meter(cv, box, frac, col, label, value, sub=None, vfont=22, danger=False):
    x0, y0, x1, y1 = box
    d, g = cv.d, cv.g
    text(d, (x0, y0), label, FUI(13), GREY, tracking=1.8, glow_draw=g, glow_a=0.2)
    tw_, _ = tracked_size(d, value, FNUM(vfont), 0)
    text(d, (x1, y0 - 6), value, FNUM(vfont), col, anchor="ra", glow_draw=g, glow_a=0.5)
    bar(cv, [x0, y1 - 8, x1, y1], frac, col, segs=20)
    if sub:
        text(d, (x0, y1 + 4), sub, FMONO(11), scale(col, 0.65))


def stat(cv, xy, label, value, col=WHITE, vs=30, ls=12, anchor="la", unit=None):
    x, y = xy
    d, g = cv.d, cv.g
    text(d, (x, y), label, FUI(ls), scale(col, 0.72), tracking=2.0, anchor=anchor)
    text(d, (x, y + ls + 2), value, FNUM(vs), col, anchor=anchor, glow_draw=g, glow_a=0.45)
    if unit:
        text(d, (x + (0 if anchor == "la" else 0), y + ls + 2 + vs * 0.95), unit,
             FMONO(11), scale(col, 0.6), anchor=anchor)


# ------------------------------------------------------------------ team plate
def team_plate(cv, box, name, tagline, col, score=0, active=1.0, side="left",
               glyph="tri", seed=0, t=0.0, wins=0):
    x0, y0, x1, y1 = box
    d, g = cv.d, cv.g
    a = 0.35 + 0.65 * active
    d.rounded_rectangle(box, radius=8, fill=mix(PANEL, col, 0.06) + (235,),
                        outline=scale(col, 0.35 * a) + (255,), width=1)
    g.rounded_rectangle([x0, y0, x1, y1], radius=8, outline=scale(col, 0.06 * a))
    cy = (y0 + y1) / 2
    cx = x0 + 40 if side == "left" else x1 - 40
    if glyph == "tri":
        pts = tri(cx, cy, 15, t * 1.4)
        neon_poly(cv, pts, scale(col, a), w=2, glow=18, ga=0.8, fill=scale(col, 0.12) + (0,))
    else:
        neon_circle(cv, (cx, cy), 13, scale(col, a), w=2, glow=18, ga=0.8,
                    fill=scale(col, 0.12) + (0,))
        for k in range(6):
            ang = t * 0.9 + k * math.tau / 6
            px = cx + 16 * math.cos(ang)
            py = cy + 16 * math.sin(ang)
            d.ellipse([px - 1.6, py - 1.6, px + 1.6, py + 1.6], fill=scale(col, a))
    tx = x0 + 70 if side == "left" else x0 + 18
    anch = "la" if side == "left" else "la"
    text(d, (tx, y0 + 12), name, FDISP(20), scale(col, a), tracking=2.0,
         glow_draw=g, glow_a=0.5 * a)
    text(d, (tx, y0 + 40), tagline, FMONO(11), scale(col, 0.55 * a))
    sx = x1 - 16 if side == "left" else x1 - 16
    text(d, (sx, y0 + 14), str(score).zfill(3), FNUM(30), scale(col, a), anchor="ra",
         glow_draw=g, glow_a=0.5 * a)
    text(d, (sx, y0 + 46), "SCORE", FUI(11), scale(col, 0.5 * a), anchor="ra", tracking=2)


# ------------------------------------------------------------------ log
def log_panel(cv, box, entries, t, title="EVENT STREAM", accent=GREEN, maxrows=14,
              tref=0.0, row_h=17):
    x0, y0, x1, y1 = box
    panel(cv, box, title=title, accent=accent, glow=0.6)
    d, g = cv.d, cv.g
    rows = [e for e in entries][-maxrows:]
    y = y0 + 38
    icon_col = {"bad": RED, "good": GREEN, "warn": AMBER, "red": RED, "blue": CYAN,
                "info": GREY}
    for (lt, msg, kind) in rows:
        col = icon_col.get(kind, GREY)
        age = max(0.0, tref - lt)
        a = max(0.25, 1.0 - age * 0.02)
        text(d, (x0 + 12, y), f"{lt:06.2f}", FMONO(11), scale(col, 0.45 * a))
        d.ellipse([x0 + 66, y + 5, x0 + 71, y + 10], fill=scale(col, a))
        text(d, (x0 + 80, y), msg[:44], FMONO(12), scale(col, 0.92 * a),
             glow_draw=g if age < 0.6 else None, glow_a=0.3)
        y += row_h
        if y > y1 - 14:
            break


# ------------------------------------------------------------------ charts
def chart(cv, box, series, title, accent=CYAN, ymax=None, ymin=0.0, xlabel="BATTLES",
          ylabel=None, dots=True, gridn=4, cur=None, target=None, invert=False,
          label_fmt="{:.0f}"):
    """series: list of (x, y) or list of y"""
    x0, y0, x1, y1 = box
    d, g = cv.d, cv.g
    panel(cv, box, title=title, accent=accent, glow=0.5)
    px0, py0, px1, py1 = x0 + 46, y0 + 40, x1 - 14, y1 - 26
    if not series:
        return
    ys = [s[1] if isinstance(s, (tuple, list)) else s for s in series]
    ymax = ymax if ymax is not None else max(ys) * 1.15 + 1e-6
    ymin = ymin
    n = max(2, len(ys))

    def P(i, v):
        ux = i / (n - 1)
        uy = (v - ymin) / max(1e-6, (ymax - ymin))
        return (px0 + (px1 - px0) * ux, py1 - (py1 - py0) * max(0.0, min(1.0, uy)))

    for i in range(gridn + 1):
        yy = py1 - (py1 - py0) * i / gridn
        d.line([(px0, yy), (px1, yy)], fill=LINE_DIM + (170,), width=1)
        v = ymin + (ymax - ymin) * i / gridn
        text(d, (px0 - 8, yy - 6), label_fmt.format(v), FMONO(10), GREY_D, anchor="ra")
    for i in range(5):
        xx = px0 + (px1 - px0) * i / 4
        d.line([(xx, py0), (xx, py1)], fill=LINE_DIM + (90,), width=1)
    if target is not None:
        yy = py1 - (py1 - py0) * ((target - ymin) / max(1e-6, (ymax - ymin)))
        for i in range(0, int(px1 - px0), 12):
            d.line([(px0 + i, yy), (px0 + i + 6, yy)], fill=scale(GREEN, 0.45) + (200,), width=1)
        text(d, (px1, yy - 14), "TARGET", FMONO(9), scale(GREEN, 0.6), anchor="ra")
    pts = [P(i, v) for i, v in enumerate(ys)]
    for i in range(1, len(pts)):
        g.line([pts[i - 1], pts[i]], fill=scale(accent, 0.10), width=10)
        g.line([pts[i - 1], pts[i]], fill=scale(accent, 0.22), width=5)
        d.line([pts[i - 1], pts[i]], fill=accent, width=2)
    if dots and len(pts) > 1:
        lx, ly = pts[-1]
        d.ellipse([lx - 3, ly - 3, lx + 3, ly + 3], fill=WHITE)
        g.ellipse([lx - 9, ly - 9, lx + 9, ly + 9], fill=scale(accent, 0.28))
    text(d, (px0, py1 + 8), xlabel, FMONO(10), GREY_D)
    if ylabel:
        text(d, (px1, py1 + 8), ylabel, FMONO(10), GREY_D, anchor="ra")
    if cur is not None:
        text(d, (px1, py0 - 2), cur, FNUM(20), accent, anchor="ra", glow_draw=g, glow_a=0.4)


def bars_compare(cv, box, items, title, unit="", ymax=None):
    """items: [(label, before, after, col_before, col_after, invert?)]
    each row is normalised to its own before-value so the delta reads clearly."""
    x0, y0, x1, y1 = box
    d, g = cv.d, cv.g
    panel(cv, box, title=title, accent=GREEN, glow=0.5)
    n = len(items)
    top = y0 + 42
    h = (y1 - top - 16) / n
    for i, it in enumerate(items):
        lab, b, a, cb, ca = it[0], it[1], it[2], it[3], it[4]
        better_down = it[5] if len(it) > 5 else True
        cy = top + h * i + h / 2
        text(d, (x0 + 14, cy - 24), lab, FUI(14), GREY, tracking=1.2)
        bw = x1 - x0 - 250
        bh = 11
        mx = max(b, a, 1e-6)
        # before
        by = cy - 6
        d.rounded_rectangle([x0 + 14, by, x0 + 14 + bw, by + bh], radius=5, fill=LINE_DIM + (200,))
        w = bw * (b / mx)
        d.rounded_rectangle([x0 + 14, by, x0 + 14 + w, by + bh], radius=5, fill=scale(cb, 0.9))
        g.rounded_rectangle([x0 + 14, by - 1, x0 + 14 + w, by + bh + 1], radius=5, fill=scale(cb, 0.20))
        text(d, (x0 + 14 + bw + 56, by - 4), f"{b:g}{unit}", FNUM(17), scale(cb, 0.95), anchor="ra")
        text(d, (x0 + 18 + bw + 56, by - 3), "BEFORE", FUI(9), scale(cb, 0.55), anchor="ra", tracking=1.4)
        # after
        by2 = by + bh + 6
        d.rounded_rectangle([x0 + 14, by2, x0 + 14 + bw, by2 + bh], radius=5, fill=LINE_DIM + (200,))
        w2 = bw * (a / mx)
        d.rounded_rectangle([x0 + 14, by2, x0 + 14 + w2, by2 + bh], radius=5, fill=ca)
        g.rounded_rectangle([x0 + 14, by2 - 1, x0 + 14 + w2, by2 + bh + 1], radius=5, fill=scale(ca, 0.24))
        text(d, (x0 + 14 + bw + 56, by2 - 4), f"{a:g}{unit}", FNUM(17), ca, anchor="ra",
             glow_draw=g, glow_a=0.4)
        text(d, (x0 + 18 + bw + 56, by2 - 3), "AFTER", FUI(9), scale(ca, 0.6), anchor="ra", tracking=1.4)
        # delta
        pct = (abs(a - b) / max(1e-6, b)) * 100
        sign = "-" if (a < b) == better_down else "+"
        dx0 = x0 + 14 + bw + 74
        text(d, (dx0, cy - 6), f"{sign}{pct:.0f}%", FDISP(19), GREEN if sign == "-" else RED,
             glow_draw=g, glow_a=0.35)


# ------------------------------------------------------------------ misc
def chip(cv, xy, label, col, size=12, pad=8, active=1.0, glow=0.5):
    d, g = cv.d, cv.g
    f = FUI(size)
    w = d.textlength(label, font=f) + pad * 2
    x, y = xy
    a = 0.35 + 0.65 * active
    d.rounded_rectangle([x, y, x + w, y + size + 12], radius=4, fill=scale(col, 0.13 * a) + (255,),
                        outline=scale(col, 0.55 * a) + (255,))
    if glow:
        g.rounded_rectangle([x, y, x + w, y + size + 12], radius=4, outline=scale(col, 0.10 * a))
    text(d, (x + pad, y + 5), label, f, scale(col, a))
    return w


def scanlines_box(cv, box, col, a=0.05, step=4):
    x0, y0, x1, y1 = box
    y = y0
    while y < y1:
        cv.d.line([(x0, y), (x1, y)], fill=col + (int(255 * a),))
        y += step


def danger_stripes(cv, box, col=RED, a=0.5, w=10, off=0):
    x0, y0, x1, y1 = box
    x = x0 - (x1 - x0)
    while x < x1:
        pts = [(x, y1), (x + w, y1), (x + w + (y1 - y0), y0), (x + (y1 - y0), y0)]
        cv.d.polygon(pts, fill=col + (int(255 * a * 0.16),))
        x += w * 2
