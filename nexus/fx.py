"""NEXUS render FX: additive neon canvas, bloom, particles, sparks, arcs."""
import math
import random

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter
from scipy.ndimage import gaussian_filter

from theme import W, H, scale, mix

# ============================================================ canvas
class Canvas:
    """base (opaque) + glow (additive light) layers."""

    def __init__(self, size=(W, H), bg=(5, 8, 14)):
        self.size = size
        self.base = Image.new("RGB", size, bg)
        self.glow = Image.new("RGB", size, (0, 0, 0))
        self.d = ImageDraw.Draw(self.base, "RGBA")
        self.g = ImageDraw.Draw(self.glow)

    def finish(self):
        return ImageChops.add(self.base, self.glow)


# ============================================================ shapes
def neon_line(cv, p0, p1, color, w=2, glow=12, ga=0.55, glow_draw=None):
    g = glow_draw or cv.g
    if glow > 0:
        for ww, aa in ((glow, 0.10 * ga), (glow * 0.55, 0.22 * ga), (glow * 0.28, 0.45 * ga)):
            g.line([p0, p1], fill=scale(color, aa), width=max(1, int(ww)))
    cv.d.line([p0, p1], fill=color, width=max(1, int(w)))


def neon_lines(cv, pts, color, w=2, glow=12, ga=0.55):
    if glow > 0:
        for ww, aa in ((glow, 0.10 * ga), (glow * 0.55, 0.22 * ga), (glow * 0.28, 0.45 * ga)):
            cv.g.line(pts, fill=scale(color, aa), width=max(1, int(ww)))
    cv.d.line(pts, fill=color, width=max(1, int(w)), joint="curve")


def neon_poly(cv, pts, color, w=2, glow=12, ga=0.6, fill=None):
    if glow > 0:
        for ww, aa in ((glow, 0.10 * ga), (glow * 0.5, 0.24 * ga), (glow * 0.25, 0.5 * ga)):
            cv.g.polygon(pts, outline=scale(color, aa), width=max(1, int(ww)))
    cv.d.polygon(pts, outline=color, fill=fill, width=max(1, int(w)))


def neon_circle(cv, cxy, r, color, w=2, glow=14, ga=0.6, fill=None, width_seq=None):
    x, y, r = cxy[0], cxy[1], r
    box = [x - r, y - r, x + r, y + r]
    if glow > 0:
        for ww, aa in ((glow, 0.09 * ga), (glow * 0.5, 0.2 * ga), (glow * 0.25, 0.45 * ga)):
            rr = r + ww * 0.35
            cv.g.ellipse([x - rr, y - rr, x + rr, y + rr], outline=scale(color, aa),
                         width=max(1, int(ww)))
    if fill is not None:
        cv.d.ellipse(box, fill=fill)
    cv.d.ellipse(box, outline=color, width=max(1, int(w)))


def disc(cv, cxy, r, color, glow=0.0, layers=6):
    """soft additive blob"""
    g = cv.g
    for i in range(layers, 0, -1):
        k = i / layers
        rr = r * (0.35 + 1.65 * k)
        a = (1 - k) ** 2 * 0.55
        g.ellipse([cxy[0] - rr, cxy[1] - rr, cxy[0] + rr, cxy[1] + rr],
                  fill=scale(color, a))
    if glow > 0:
        pass
    cv.d.ellipse([cxy[0] - r * 0.5, cxy[1] - r * 0.5, cxy[0] + r * 0.5, cxy[1] + r * 0.5],
                 fill=color)


def hexpts(cx, cy, r, rot=0.0, squash=1.0):
    pts = []
    for i in range(6):
        a = math.pi / 180 * (60 * i - 30) + rot
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a) * squash))
    return pts


def rr(box, radius):
    x0, y0, x1, y1 = box
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def round_rect(draw, box, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def jagged(p0, p1, amp, segs, rng, decay=True):
    """lightning-ish polyline between two points"""
    x0, y0 = p0
    x1, y1 = p1
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / L, dx / L
    pts = [(x0, y0)]
    for i in range(1, segs):
        t = i / segs
        f = amp * (1 - abs(t - 0.5) * 2 * 0.55) if decay else amp
        o = rng.uniform(-f, f)
        pts.append((x0 + dx * t + nx * o, y0 + dy * t + ny * o))
    pts.append((x1, y1))
    return pts


def tri(cx, cy, r, ang):
    pts = []
    for k in (-90, 30, 150):
        a = math.radians(k) + ang
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


# ============================================================ post
_BLOOM_CACHE = {}


def _down(img, f=2):
    return img.resize((W // f, H // f), Image.BILINEAR)


def bloom(img, thr=0.50, strength=1.05):
    small = np.asarray(img.resize((W // 2, H // 2), Image.BILINEAR), dtype=np.float32) * (1 / 255.0)
    b = np.clip(small - thr, 0, None)
    b1 = gaussian_filter(b, sigma=(0.9, 0.9, 0), mode="constant")
    b2 = gaussian_filter(b, sigma=(2.9, 2.9, 0), mode="constant")
    s4 = np.asarray(img.resize((W // 6, H // 6), Image.BILINEAR), dtype=np.float32) * (1 / 255.0)
    b3 = gaussian_filter(np.clip(s4 - thr, 0, None), sigma=(2.4, 2.4, 0), mode="constant")
    bl = cv2.resize(b1 * (0.50 * strength) + b2 * (0.80 * strength), (W, H),
                    interpolation=cv2.INTER_LINEAR)
    bl += cv2.resize(b3 * (1.00 * strength), (W, H), interpolation=cv2.INTER_LINEAR)
    return np.clip(np.asarray(img, dtype=np.float32) * (1 / 255.0) + bl, 0, 1)


_NOISE = None


def _noise():
    global _NOISE
    if _NOISE is None:
        _NOISE = np.random.default_rng(1234).standard_normal((2200, 2200), dtype=np.float32)
    return _NOISE


_VIG = None
_SCAN = None


def _masks():
    global _VIG, _SCAN
    if _VIG is None:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        cx, cy = W / 2, H / 2
        d = np.sqrt(((xx - cx) / (W * 0.62)) ** 2 + ((yy - cy) / (H * 0.60)) ** 2)
        _VIG = np.clip(1.0 - 0.72 * np.clip(d - 0.55, 0, None) ** 1.5, 0.35, 1.0)[..., None]
        _SCAN = (0.955 + 0.045 * np.sin(np.arange(H) * math.pi / 2.0))[:, None, None].astype(np.float32)
    return _VIG, _SCAN


def post(img_arr, grain=0.012, vignette=1.0, aberration=0.0, rng=None, flash=0.0,
         flash_color=(255, 255, 255)):
    """float32 [0,1] array -> uint8 with grain / vignette / scanlines / chromatic split"""
    vig, scan = _masks()
    a = img_arr
    if aberration > 0.2:
        k = int(round(aberration))
        a = a.copy()
        a[:-k if k > 0 else None, :, 0] = a[k:, :, 0]
        a[k:, :, 2] = a[:-k, :, 2]
    a *= (1.0 - (1.0 - vig) * vignette)
    a *= scan
    if flash > 0:
        a += flash * (np.array(flash_color, dtype=np.float32) * (1 / 255.0))
    if grain > 0:
        n = _noise()
        dy = int(rng.random() * (n.shape[0] - H)) if rng is not None else 0
        dx = int(rng.random() * (n.shape[1] - W)) if rng is not None else 0
        a += (n[dy:dy + H, dx:dx + W, None] * grain)
    return np.clip(a * 255.0, 0, 255).astype(np.uint8)


# ============================================================ particles / fx objects
class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "age", "color", "size", "drag", "grav")

    def __init__(self, x, y, vx, vy, life, color, size=2.0, drag=0.90, grav=0.0):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life, self.age = life, 0.0
        self.color, self.size, self.drag, self.grav = color, size, drag, grav

    def step(self, dt):
        self.age += dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += self.grav * dt
        k = self.drag ** (dt * 60)
        self.vx *= k
        self.vy *= k

    @property
    def alive(self):
        return self.age < self.life

    def draw(self, cv):
        t = 1 - self.age / self.life
        a = t ** 1.4
        s = max(0.7, self.size * (0.35 + 0.65 * t))
        cv.g.ellipse([self.x - s * 2.2, self.y - s * 2.2, self.x + s * 2.2, self.y + s * 2.2],
                     fill=scale(self.color, 0.22 * a))
        cv.d.ellipse([self.x - s, self.y - s, self.x + s, self.y + s],
                     fill=scale(self.color, a))


class Burst:
    """radial particle explosion + flash ring"""

    def __init__(self, xy, color, n=26, speed=(90, 420), life=(0.35, 0.95), size=2.4,
                 grav=0.0, drag=0.90, seed=0):
        self.xy = xy
        self.color = color
        rng = random.Random(seed)
        self.ps = []
        self.life = max(life)
        self.age = 0.0
        self.core = 1.0
        for _ in range(n):
            a = rng.uniform(0, math.tau)
            sp = rng.uniform(*speed)
            self.ps.append(Particle(xy[0], xy[1], math.cos(a) * sp, math.sin(a) * sp,
                                    rng.uniform(*life), color, rng.uniform(size * 0.5, size * 1.5),
                                    drag, grav))

    def step(self, dt):
        self.age += dt
        for p in self.ps:
            p.step(dt)

    @property
    def alive(self):
        return self.age < self.life

    def draw(self, cv):
        t = self.age / self.life
        if t < 0.35:
            r = 8 + 90 * (t / 0.35)
            a = (1 - t / 0.35) ** 2
            cv.g.ellipse([self.xy[0] - r, self.xy[1] - r, self.xy[0] + r, self.xy[1] + r],
                         outline=scale(self.color, 0.8 * a), width=3)
        for p in self.ps:
            if p.alive:
                p.draw(cv)


class Shockwave:
    def __init__(self, xy, color, rmax=320, life=0.85, w=4, seed=0):
        self.xy, self.color = xy, color
        self.rmax, self.life, self.w = rmax, life, w
        self.age = 0.0

    def step(self, dt):
        self.age += dt

    @property
    def alive(self):
        return self.age < self.life

    def draw(self, cv):
        t = self.age / self.life
        r = self.rmax * (1 - (1 - t) ** 2.4)
        a = (1 - t) ** 1.6
        x, y = self.xy
        for k, aa in ((3.0, 0.10), (1.8, 0.22), (1.0, 0.75)):
            rr = r * (1 + 0.02 * k)
            cv.g.ellipse([x - rr, y - rr, x + rr, y + rr], outline=scale(self.color, aa * a),
                         width=max(1, int(self.w * (1 - t * 0.6))))
        # leading edge
        cv.d.ellipse([x - r, y - r, x + r, y + r], outline=scale(self.color, a), width=2)


class Arc:
    """flickering electric arc between two points"""

    def __init__(self, p0, p1, color, life=0.30, amp=26, segs=14, seed=0, w=2, branches=3):
        self.p0, self.p1, self.color = p0, p1, color
        self.life, self.amp, self.segs = life, amp, segs
        self.age = 0.0
        self.rng = random.Random(seed)
        self.w = w
        self.branches = branches

    def step(self, dt):
        self.age += dt

    @property
    def alive(self):
        return self.age < self.life

    def draw(self, cv):
        t = self.age / self.life
        a = (1 - t) ** 1.2 if t > 0.35 else (0.65 + 0.35 * self.rng.random())
        amp = self.amp * (0.35 + 0.65 * (1 - t))
        pts = jagged(self.p0, self.p1, amp, self.segs, self.rng)
        neon_lines(cv, pts, scale(self.color, a), w=self.w, glow=16, ga=0.8)
        for _ in range(self.branches):
            i = self.rng.randrange(1, len(pts) - 1)
            q = pts[i]
            end = (q[0] + self.rng.uniform(-46, 46), q[1] + self.rng.uniform(-46, 46))
            neon_lines(cv, jagged(q, end, amp * 0.5, 5, self.rng), scale(self.color, a * 0.55),
                       w=1, glow=8, ga=0.6)


class Projectile:
    """comet packet travelling a polyline path"""

    def __init__(self, path, color, speed=900.0, t0=0.0, trail=16, size=5.0,
                 head=(255, 255, 255), wobble=0.0, seed=0, dash=False):
        self.path = path
        self.color = color
        self.speed = speed
        self.t0 = t0
        self.trail = trail
        self.size = size
        self.head = head
        self.wobble = wobble
        self.rng = random.Random(seed)
        self.dash = dash
        segs = []
        for i in range(len(path) - 1):
            segs.append(math.dist(path[i], path[i + 1]))
        self.seg_lens = segs
        self.total = max(1e-6, sum(segs))
        self.dur = self.total / speed
        self.done = False
        self.pos = path[0]
        self.hist = []

    def step(self, t, dt):
        u = (t - self.t0) / self.dur
        if u < 0:
            self.pos = self.path[0]
            return False
        if u >= 1.0:
            self.done = True
            self.pos = self.path[-1]
            return True
        d = u * self.total
        for i, L in enumerate(self.seg_lens):
            if d <= L or i == len(self.seg_lens) - 1:
                k = 0 if L == 0 else min(1.0, d / L)
                a, b = self.path[i], self.path[i + 1]
                self.pos = (a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k)
                break
            d -= L
        if self.wobble:
            self.pos = (self.pos[0] + self.rng.uniform(-self.wobble, self.wobble),
                        self.pos[1] + self.rng.uniform(-self.wobble, self.wobble))
        self.hist.append(self.pos)
        if len(self.hist) > self.trail:
            self.hist.pop(0)
        return False

    def draw(self, cv):
        if len(self.hist) > 1:
            n = len(self.hist)
            for i in range(1, n):
                a = (i / n) ** 2.2
                p0, p1 = self.hist[i - 1], self.hist[i]
                wseg = max(1, int(self.size * 1.5 * (i / n)))
                cv.g.line([p0, p1], fill=scale(self.color, 0.16 * a), width=wseg * 4)
                cv.g.line([p0, p1], fill=scale(self.color, 0.45 * a), width=wseg * 2)
                cv.d.line([p0, p1], fill=scale(self.color, 0.35 + 0.6 * a), width=wseg)
        x, y = self.pos
        # hot core
        for rr, aa in ((self.size * 5.0, 0.10), (self.size * 3.0, 0.22), (self.size * 1.9, 0.5)):
            cv.g.ellipse([x - rr, y - rr, x + rr, y + rr], fill=scale(self.color, aa))
        cv.d.ellipse([x - self.size, y - self.size, x + self.size, y + self.size], fill=self.head)


class Ripple:
    """soft expanding ring (detection ping)"""

    def __init__(self, xy, color, rmax=260, life=1.2, w=2):
        self.xy, self.color, self.rmax, self.life, self.w = xy, color, rmax, life, w
        self.age = 0.0

    def step(self, dt):
        self.age += dt

    @property
    def alive(self):
        return self.age < self.life

    def draw(self, cv):
        t = self.age / self.life
        r = self.rmax * (0.15 + 0.85 * t)
        a = (1 - t) ** 1.8
        x, y = self.xy
        cv.g.ellipse([x - r, y - r, x + r, y + r], outline=scale(self.color, 0.30 * a), width=self.w * 4)
        cv.d.ellipse([x - r, y - r, x + r, y + r], outline=scale(self.color, 0.9 * a), width=self.w)
