"""NEXUS visual theme: palette, fonts, text helpers."""
import os
from PIL import ImageFont

W, H = 1920, 1080
FPS = 30
FONT_DIR = "/home/user/assets/fonts"

_CACHE = {}


def _load(name, size):
    key = (name, size)
    if key not in _CACHE:
        _CACHE[key] = ImageFont.truetype(os.path.join(FONT_DIR, name), size)
    return _CACHE[key]


def _var(name, size, axes):
    f = _load(name, size)
    try:
        f.set_variation_by_axes(axes)
    except Exception:
        pass
    return f


def FDISP(s):   # display / titles  (Orbitron, heavy)
    return _var("Orbitron.ttf", s, [800])


def FDISPR(s):  # display regular
    return _var("Orbitron.ttf", s, [480])


def FUI(s):     # tech UI labels (Chakra Petch)
    return _load("Chakra-Bold.ttf", s)


def FMONO(s):   # telemetry / logs (Share Tech Mono)
    return _load("ShareTechMono.ttf", s)


def FNUM(s):    # big numbers (Rajdhani)
    return _load("Rajdhani-Bold.ttf", s)


# ---------------------------------------------------------------- palette
BG        = (5, 8, 14)
BG2       = (9, 14, 24)
PANEL     = (10, 16, 27)
PANEL2    = (13, 21, 34)
LINE_DIM  = (26, 44, 66)
LINE_MID  = (40, 66, 96)

WHITE     = (232, 244, 255)
GREY      = (128, 152, 178)
GREY_D    = (74, 94, 116)

RED       = (255, 54, 72)      # ULTRON / red team
RED_HOT   = (255, 140, 120)
RED_DEEP  = (150, 12, 30)
AMBER     = (255, 176, 40)
ORANGE    = (255, 120, 30)
CYAN      = (0, 226, 255)      # PROTON / blue team
CYAN_D    = (0, 120, 150)
BLUE      = (60, 130, 255)
GREEN     = (56, 255, 148)
GREEN_D   = (18, 120, 70)
PURPLE    = (170, 110, 255)
YELLOW    = (255, 226, 90)

TEAM_RED = RED
TEAM_BLU = CYAN


def mix(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(round(a + (b - a) * t)) for a, b in zip(c1, c2))


def scale(c, k):
    return tuple(max(0, min(255, int(round(v * k)))) for v in c)


def with_alpha(c, a):
    return (int(c[0] * a), int(c[1] * a), int(c[2] * a))


# ---------------------------------------------------------------- text
def tw(draw, s, font):
    """text width"""
    b = draw.textbbox((0, 0), s, font=font)
    return b[2] - b[0], b[3] - b[1]


def text(draw, xy, s, font, fill, tracking=0, anchor=None, glow_draw=None,
         glow_a=0.35):
    """Draw text, optional tracking (letter-spacing) and additive glow pass."""
    x, y = xy
    if tracking:
        if anchor:
            w, h = tracked_size(draw, s, font, tracking)
            if "m" in anchor or "a" in anchor:
                x -= w / 2 if "m" in anchor else w
            if "d" in anchor:
                y -= h / 2
            if "b" in anchor:
                y -= h
        cx = x
        for ch in s:
            draw.text((cx, y), ch, font=font, fill=fill)
            cx += draw.textlength(ch, font=font) + tracking
        return
    if glow_draw is not None:
        gx, gy = xy
        if anchor:
            b = draw.textbbox((0, 0), s, font=font)
            w, h = b[2] - b[0], b[3] - b[1]
            gx = x - (w / 2 if "m" in anchor else w if "r" in anchor or "a" in anchor else 0)
        glow_draw.text((gx + 1, gy + 1), s, font=font, fill=with_alpha(fill, glow_a))
        glow_draw.text((gx - 1, gy - 1), s, font=font, fill=with_alpha(fill, glow_a * 0.6))
    draw.text(xy, s, font=font, fill=fill, anchor=anchor)


def tracked_size(draw, s, font, tracking=0):
    w = sum(draw.textlength(c, font=font) + tracking for c in s) - tracking
    b = draw.textbbox((0, 0), s, font=font)
    return w, b[3] - b[1]


def clip(s, n):
    return s if len(s) <= n else s[: max(1, n - 1)] + "…"
