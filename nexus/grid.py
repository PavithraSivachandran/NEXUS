"""NEXUS digital-twin grid model: topology, power flow, cascade, agents, metrics."""
import math
import random

from fx import (Arc, Burst, Projectile, Ripple, Shockwave, jagged, neon_circle,
                neon_line, neon_lines, neon_poly, hexpts, disc, scale, tri)
from theme import *

BLAST_K = 0.945

# node states
NOM, STRESS, CRIT, FAIL, ISO = 0, 1, 2, 3, 4

# ------------------------------------------------------------------ topology
# kind: source | substation | line | control | data | load
NODES = [
    dict(id="GEN1", label="GEN-01",  sub="GENERATOR",     kind="source",     x=0.075, y=0.50, cap=800, demand=0,   crit=0, wt=0,  bu=0),
    dict(id="SUBA", label="SUB-A",   sub="SUBSTATION",    kind="substation", x=0.305, y=0.225, cap=520, demand=8,   crit=0, wt=5,  bu=0),
    dict(id="SUBB", label="SUB-B",   sub="SUBSTATION",    kind="substation", x=0.305, y=0.780, cap=520, demand=8,   crit=0, wt=5,  bu=0),
    dict(id="CTRL", label="SCADA",   sub="CONTROL CTR",   kind="control",    x=0.290, y=0.505, cap=1,   demand=8,   crit=1, wt=8,  bu=45),
    dict(id="TELE", label="TELEMETRY", sub="DATA BUS",    kind="data",       x=0.075, y=0.855, cap=1,   demand=4,   crit=0, wt=6,  bu=0),
    dict(id="LN1",  label="LINE-1",  sub="TRANSMISSION",  kind="line",       x=0.560, y=0.140, cap=1,   demand=0,   crit=0, wt=10, bu=0),
    dict(id="LN2",  label="LINE-2",  sub="TRANSMISSION",  kind="line",       x=0.560, y=0.860, cap=1,   demand=0,   crit=0, wt=10, bu=0),
    dict(id="CITY", label="CITY LOAD", sub="DISTRICT 7",  kind="load",       x=0.555, y=0.330, cap=1,   demand=320, crit=0, wt=20, bu=0),
    dict(id="PUMP", label="WATER PUMP", sub="CRITICAL",   kind="load",       x=0.800, y=0.180, cap=1,   demand=90,  crit=1, wt=18, bu=0),
    dict(id="HOSP", label="HOSPITAL", sub="CRITICAL",     kind="load",       x=0.950, y=0.430, cap=1,   demand=60,  crit=1, wt=26, bu=240),
    dict(id="RAIL", label="RAIL SIGNAL", sub="CRITICAL",  kind="load",       x=0.790, y=0.800, cap=1,   demand=70,  crit=1, wt=14, bu=0),
]

EDGES = [
    dict(id="e1", a="GEN1", b="SUBA", kind="power", cap=520),
    dict(id="e2", a="GEN1", b="SUBB", kind="power", cap=520),
    dict(id="e3", a="SUBA", b="LN1",  kind="power", cap=700),
    dict(id="e4", a="SUBA", b="LN2",  kind="power", cap=300),
    dict(id="e5", a="SUBB", b="LN2",  kind="power", cap=300),
    dict(id="e6", a="LN1",  b="PUMP", kind="power", cap=200),
    dict(id="e7", a="LN1",  b="CITY", kind="power", cap=460),
    dict(id="e8", a="LN2",  b="CITY", kind="power", cap=300, open=True),
    dict(id="e9", a="LN2",  b="RAIL", kind="power", cap=160),
    dict(id="e10", a="PUMP", b="HOSP", kind="power", cap=90),
    dict(id="e16", a="SUBB", b="LN1", kind="power", cap=420, open=True),
    dict(id="e12", a="CTRL", b="SUBA", kind="control", cap=1),
    dict(id="e13", a="CTRL", b="SUBB", kind="control", cap=1),
    dict(id="e14", a="TELE", b="CTRL", kind="data", cap=1),
    dict(id="e15", a="TELE", b="SUBB", kind="data", cap=1),
]

STATE_COL = {
    NOM: CYAN, STRESS: AMBER, CRIT: ORANGE, FAIL: RED, ISO: BLUE,
}


class Node:
    def __init__(self, spec, rect, sc=1.0, idx=0):
        self.__dict__.update(spec)
        self.idx = idx
        self.phase = (idx * 1.73) % 6.28
        self.rect = rect
        self.sc = sc
        self.state = NOM
        self.powered = True
        self.load = 0.45
        self.target_load = 0.45
        self.backup = float(spec["bu"])
        self.backup_max = float(spec["bu"])
        self.compromised = 0.0      # 0..1 red control
        self.shielded = 0.0         # 0..1 blue protection
        self.pulse = 0.0
        self.hit_flash = 0.0
        self.heal_flash = 0.0
        self.dead_since = None
        self.t_degraded = 0.0
        self.r = 34 * sc
        self.xy = (rect[0] + spec["x"] * (rect[2] - rect[0]),
                   rect[1] + spec["y"] * (rect[3] - rect[1]))
        self.isolated = False
        self.spoofed = False
        self.degraded = False

    @property
    def xy_(self):
        return self.xy

    def impact(self):
        """0..1 fraction of service lost"""
        if self.state == FAIL:
            return 1.0
        if self.state == CRIT:
            return 0.85
        if self.state == STRESS:
            return 0.55 if not self.powered else 0.30
        return 0.0


class Edge:
    def __init__(self, spec, nodes, sc=1.0):
        self.__dict__.update(spec)
        self.sc = sc
        self.open = bool(spec.get("open", False))
        self.state = 0          # 0 ok, 1 overload, 2 severed, 3 rerouted/closed
        self.flow = 0.0
        self.flow_disp = 0.0
        self.overload_t = 0.0
        self.sever_t = 0.0
        self.flash = 0.0


class Battle:
    """one wargame battle on the twin"""

    def __init__(self, rect, seed=1, sc=1.0, mini=False):
        self.rect = rect
        self.sc = sc
        self.mini = mini
        self.rng = random.Random(seed)
        self.nodes = {s["id"]: Node(s, rect, sc, i) for i, s in enumerate(NODES)}
        self.edges = [Edge(e, self.nodes, sc) for e in EDGES]
        self.t = 0.0
        self.fx = []            # generic fx objects (burst/shock/arc/ripple)
        self.shots = []         # projectiles with on_hit callbacks
        self.log = []           # (t, text, kind)
        self.shake = 0.0
        self.flash = 0.0
        self.flash_col = WHITE
        self.detected = None
        self.detection_t = None
        self.threat_t0 = None
        self.outcome = None
        self.pending = []       # (t_fire, callable)
        # metrics
        self.blast = 0.0
        self.cascade_p = 0.0
        self.risk = 0.0
        self.crit_assets = 0
        self.unserved = 0.0
        self.total_demand = sum(n.demand for n in self.nodes.values())
        self.predicted_path = []
        self.recompute()

    def set_rect(self, rect):
        self.rect = rect
        for s, n in zip(NODES, self.nodes.values()):
            n.xy = (rect[0] + s["x"] * (rect[2] - rect[0]),
                    rect[1] + s["y"] * (rect[3] - rect[1]))

    # -------------------------------------------------- geometry helpers
    def n(self, nid):
        return self.nodes[nid]

    def xy(self, nid):
        return self.nodes[nid].xy

    def edge(self, a, b):
        for e in self.edges:
            if (e.a == a and e.b == b) or (e.a == b and e.b == a):
                return e
        return None

    def offscreen_origin(self, side="left"):
        x0, y0, x1, y1 = self.rect
        cy = (y0 + y1) / 2
        if side == "left":
            return (x0 - 190 * self.sc, cy - 120 * self.sc)
        if side == "right":
            return (x1 + 190 * self.sc, cy + 120 * self.sc)
        return (x0 - 190 * self.sc, cy)

    # -------------------------------------------------- fx
    def add(self, obj):
        self.fx.append(obj)

    def burst(self, xy, color, n=26, **kw):
        self.fx.append(Burst(xy, color, n=n, seed=self.rng.randrange(1 << 30), **kw))

    def shock(self, xy, color, rmax=320, life=0.85, w=4):
        self.fx.append(Shockwave(xy, color, rmax * self.sc, life, w))

    def arc(self, p0, p1, color, life=0.3, amp=26, segs=14, w=2, branches=3):
        self.fx.append(Arc(p0, p1, color, life, amp * self.sc, segs,
                           seed=self.rng.randrange(1 << 30), w=w, branches=branches))

    def ping(self, xy, color, rmax=260, life=1.2, w=2):
        self.fx.append(Ripple(xy, color, rmax * self.sc, life, w))

    def shake_it(self, amt):
        self.shake = max(self.shake, amt)

    def flash_it(self, amt, col=WHITE):
        self.flash = max(self.flash, amt)
        self.flash_col = col

    def launch(self, path, color, speed=900.0, on_hit=None, size=5.0, head=WHITE,
               trail=16, delay=0.0, wobble=0.0):
        p = Projectile(path, color, speed * self.sc, t0=self.t + delay, trail=trail,
                       size=size * self.sc, head=head, wobble=wobble * self.sc,
                       seed=self.rng.randrange(1 << 30))
        self.shots.append((p, on_hit))
        return p

    def after(self, delay, fn):
        self.pending.append((self.t + delay, fn))

    def say(self, text, kind="info"):
        self.log.append((self.t, text, kind))
        if len(self.log) > 40:
            self.log.pop(0)

    # -------------------------------------------------- actions
    def sever(self, eid, spark=True):
        e = [x for x in self.edges if x.id == eid][0]
        if e.state == 2:
            return
        e.state = 2
        e.sever_t = self.t
        e.flash = 1.0
        if spark:
            a, b = self.xy(e.a), self.xy(e.b)
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            self.arc(a, mid, ORANGE, life=0.45, amp=34 * self.sc, segs=16, w=3, branches=4)
            self.arc(mid, b, ORANGE, life=0.45, amp=34 * self.sc, segs=16, w=3, branches=4)
            self.burst(mid, ORANGE, n=40, speed=(120 * self.sc, 520 * self.sc), size=2.6 * self.sc)
            self.burst(mid, WHITE, n=14, speed=(60 * self.sc, 300 * self.sc), size=1.8 * self.sc)
            self.shock(mid, ORANGE, rmax=170, life=0.75, w=3)
            self.shake_it(9.0)
            self.flash_it(0.16, (255, 190, 150))
        self.recompute()

    def restore(self, eid, col=GREEN):
        e = [x for x in self.edges if x.id == eid][0]
        e.state = 3 if col == GREEN else 0
        e.sever_t = self.t
        self.recompute()

    def isolate(self, nid):
        nd = self.nodes[nid]
        nd.isolated = True
        for e in self.edges:
            if nid in (e.a, e.b) and e.kind == "power" and e.state != 2:
                a, b = self.xy(e.a), self.xy(e.b)
                m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                self.burst(m, CYAN, n=18, speed=(80 * self.sc, 300 * self.sc), size=2.0 * self.sc)
        self.recompute()

    def deisolate(self, nid):
        self.nodes[nid].isolated = False
        self.recompute()

    def heal_all(self, col=GREEN):
        for nd in self.nodes.values():
            if nd.state != NOM:
                nd.heal_flash = 1.0
            nd.state = NOM
            nd.compromised = 0.0
            nd.spoofed = False
            nd.backup = nd.backup_max
        for e in self.edges:
            if e.state == 2:
                e.state = 0
        self.recompute()

    def compromise(self, nid, amt=1.0, col=RED):
        nd = self.nodes[nid]
        nd.compromised = min(1.0, nd.compromised + amt)
        nd.hit_flash = 1.0
        self.burst(nd.xy, col, n=30, speed=(100 * self.sc, 430 * self.sc), size=2.4 * self.sc)
        self.shock(nd.xy, col, rmax=140, life=0.7, w=3)
        self.shake_it(5.0)
        self.recompute()

    def shield(self, nid):
        nd = self.nodes[nid]
        nd.shielded = 1.0
        self.ping(nd.xy, CYAN, rmax=110, life=0.9, w=2)

    # -------------------------------------------------- physics
    def _adj(self):
        """power adjacency of healthy, closed, non-isolated nodes"""
        nodes = self.nodes
        adj = {k: [] for k in nodes}
        for e in self.edges:
            if e.kind != "power" or e.state == 2:
                continue
            if e.open and e.state != 3:
                continue
            a, b = e.a, e.b
            if nodes[a].isolated or nodes[b].isolated:
                continue
            if nodes[a].state == FAIL or nodes[b].state == FAIL:
                continue
            adj[a].append((b, e))
            adj[b].append((a, e))
        return adj

    def _component(self, adj, start, blocked):
        seen = {start}
        stack = [start]
        while stack:
            u = stack.pop()
            for v, e in adj[u]:
                if v not in seen and e is not blocked:
                    seen.add(v)
                    stack.append(v)
        return seen

    def recompute(self):
        """supply propagation + DC-ish flow sharing + state transitions + metrics"""
        nodes = self.nodes
        adj = self._adj()
        srcs = [k for k, n in nodes.items() if n.kind == "source" and not n.isolated
                and n.state != FAIL]

        # ---------- supply
        supplied = set()
        for s in srcs:
            supplied |= self._component(adj, s, None)
        for k, n in nodes.items():
            n.powered = True if n.kind == "source" else (k in supplied)
        # control / data nodes are energised from any adjacent energised asset
        for _ in range(3):
            for e in self.edges:
                if e.kind == "power" or e.state == 2:
                    continue
                if nodes[e.a].isolated or nodes[e.b].isolated:
                    continue
                if nodes[e.a].state == FAIL or nodes[e.b].state == FAIL:
                    continue
                if nodes[e.a].powered != nodes[e.b].powered:
                    nodes[e.a].powered = True
                    nodes[e.b].powered = True

        # ---------- flows: for each in-service edge, load = demand of the
        # component left without a source / number of feeders across that cut
        for e in self.edges:
            e.load = 0.0
        for e in self.edges:
            if e.kind != "power" or e.state == 2:
                continue
            if e.open and e.state != 3:
                continue
            ca = self._component(adj, e.a, e)
            a_has_src = any(x in ca for x in srcs)
            if a_has_src:
                comp = self._component(adj, e.b, e)
                b_has_src = any(x in comp for x in srcs)
                if b_has_src:
                    continue          # meshed loop: no single-cut flow
            else:
                comp = ca
            dem = sum(nodes[v].demand for v in comp)
            # feeders crossing the cut
            feeders = 0
            for o in self.edges:
                if o.kind != "power" or o.state == 2:
                    continue
                if o.open and o.state != 3:
                    continue
                x = (o.a in comp) != (o.b in comp)
                if x:
                    feeders += 1
            feeders = max(1, feeders)
            e.load = (dem / feeders) / max(1.0, e.cap)

        # ---------- edge state
        for e in self.edges:
            if e.kind == "power" and e.state in (0, 1):
                if e.load > 1.02:
                    e.state = 1
                elif e.state == 1 and e.load < 0.94:
                    e.state = 0

        # ---------- node state
        for k, n in nodes.items():
            feed = [e for e in self.edges if e.kind == "power" and (e.a == k or e.b == k)
                    and e.state != 2 and not (e.open and e.state != 3)]
            worst = max([e.load for e in feed], default=0.0)
            if n.kind == "source":
                n.target_load = min(1.0, sum(e.load for e in feed) * e.cap / 800.0
                                    if False else 0.35 + worst * 0.4)
                n.state = NOM
                continue
            if n.isolated:
                n.state = ISO
                n.target_load = 0.0
                continue
            n.target_load = min(1.3, 0.30 + worst * 0.75)
            if not n.powered:
                if n.backup_max > 0 and n.backup > 0:
                    n.state = CRIT if n.crit else STRESS
                else:
                    n.state = FAIL
                n.target_load = 0.0
            elif worst > 1.05:
                n.state = CRIT
            elif worst > 0.95 or n.compromised > 0.5:
                n.state = STRESS
            else:
                n.state = NOM
            if (n.spoofed or n.degraded) and n.state == NOM:
                n.state = STRESS

        # ---------- metrics
        wt = {k: n.wt for k, n in nodes.items()}
        tot_w = max(1.0, sum(wt.values()))
        affected, risk1, risk2 = set(), set(), set()
        for k, n in nodes.items():
            if n.state in (STRESS, CRIT, FAIL, ISO):
                affected.add(k)
        for e in self.edges:
            if e.kind == "power" and e.state == 1:
                risk1.add(e.a)
                risk1.add(e.b)
        for k in list(affected):
            for v, e in adj[k]:
                risk1.add(v)
        for k in list(risk1):
            for v, e in adj[k]:
                risk2.add(v)
        w_aff = sum(wt[k] * (1.0 if nodes[k].state == FAIL else
                             0.8 if nodes[k].state == CRIT else
                             0.5 if nodes[k].state == STRESS else 0.25)
                    for k in affected)
        w_r1 = 0.35 * sum(wt[k] for k in risk1 if k not in affected)
        w_r2 = 0.15 * sum(wt[k] for k in risk2 if k not in affected and k not in risk1)
        raw = (w_aff + w_r1 + w_r2) / tot_w
        self.blast = min(1.0, raw * BLAST_K)

        overloads = sum(1 for e in self.edges if e.kind == "power" and e.state == 1)
        pending_crit = sum(1 for n in nodes.values()
                           if n.crit and n.state in (STRESS, CRIT, FAIL))
        foothold = any(n.compromised > 0.5 and not n.isolated for n in nodes.values())
        self.crit_assets = pending_crit
        active = min(1.0, self.blast / 0.05)
        self.cascade_p = min(0.97, active * (0.13 + 0.25 * min(2, overloads)
                                             + 0.12 * pending_crit + 0.35 * self.blast
                                             + (0.13 if foothold else 0.0)))
        self.risk = min(10.0, 4.4 * self.blast + 6.85 * self.cascade_p)

    # -------------------------------------------------- step
    def step(self, dt):
        self.t += dt
        # pending callbacks
        if self.pending:
            rest = []
            for tt, fn in self.pending:
                if self.t >= tt:
                    fn()
                else:
                    rest.append((tt, fn))
            self.pending = rest
        # projectiles
        keep = []
        for p, on_hit in self.shots:
            arrived = p.step(self.t, dt)
            if arrived:
                if on_hit:
                    on_hit(p)
            else:
                keep.append((p, on_hit))
        self.shots = keep
        # fx
        keepf = []
        for f in self.fx:
            f.step(dt)
            if f.alive:
                keepf.append(f)
        self.fx = keepf
        # node dynamics
        for n in self.nodes.values():
            n.load += (n.target_load - n.load) * min(1.0, dt * 3.0)
            n.hit_flash = max(0.0, n.hit_flash - dt * 3.2)
            n.heal_flash = max(0.0, n.heal_flash - dt * 2.2)
            n.pulse += dt
            if n.state in (CRIT, FAIL) and n.backup_max > 0:
                n.backup = max(0.0, n.backup - dt)
                if n.backup <= 0 and n.state == CRIT:
                    n.state = FAIL
                    self.say(f"{n.label}: BACKUP DEPLETED — LOAD SHED", "bad")
        for e in self.edges:
            e.flow_disp += (e.load - e.flow_disp) * min(1.0, dt * 3.0)
            e.flash = max(0.0, e.flash - dt * 2.0)
        self.shake = max(0.0, self.shake - dt * 26.0)
        self.flash = max(0.0, self.flash - dt * 2.6)
        self.recompute()

    # -------------------------------------------------- draw field
    def draw_edges(self, cv, t, show_flow=True):
        for e in self.edges:
            a, b = self.xy(e.a), self.xy(e.b)
            if e.kind == "power":
                if e.state == 2:
                    # severed: broken dashed stub
                    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
                    dx, dy = b[0] - a[0], b[1] - a[1]
                    L = math.hypot(dx, dy) or 1
                    ux, uy = dx / L, dy / L
                    gap = 34 * self.sc
                    p0 = (mx - ux * gap, my - uy * gap)
                    p1 = (mx + ux * gap, my + uy * gap)
                    neon_line(cv, a, p0, scale(GREY_D, 0.55), w=1, glow=0)
                    neon_line(cv, p1, b, scale(GREY_D, 0.55), w=1, glow=0)
                    # dangling spark
                    if self.rng.random() < 0.30:
                        self.arc(p0, (p0[0] + self.rng.uniform(-16, 16) * self.sc,
                                      p0[1] + self.rng.uniform(-16, 16) * self.sc),
                                 AMBER, life=0.12, amp=10 * self.sc, segs=5, w=1, branches=1)
                    continue
                if e.state == 1:
                    col = ORANGE
                    w = 3 * self.sc
                elif e.state == 3:
                    col = GREEN
                    w = 3 * self.sc
                else:
                    col = mix(CYAN_D, CYAN, min(1.0, e.flow_disp * 1.4))
                    w = 2 * self.sc
                neon_line(cv, a, b, col, w=w, glow=13 * self.sc, ga=0.75)
                if show_flow and e.state != 2:
                    self._flow_dots(cv, a, b, col, e, t)
            else:
                dash = 9 * self.sc
                dx, dy = b[0] - a[0], b[1] - a[1]
                L = math.hypot(dx, dy) or 1
                ux, uy = dx / L, dy / L
                col = mix(LINE_MID, PURPLE if e.kind == "data" else BLUE, 0.75)
                if e.state == 2:
                    col = scale(RED, 0.4)
                elif e.state == 4:
                    col = scale(AMBER, 0.85)
                n = int(L / (dash * 2))
                off = (t * 26 * self.sc) % (dash * 2)
                for i in range(n):
                    s = i * dash * 2 + off
                    if s + dash > L:
                        break
                    p0 = (a[0] + ux * s, a[1] + uy * s)
                    p1 = (a[0] + ux * (s + dash), a[1] + uy * (s + dash))
                    cv.d.line([p0, p1], fill=col, width=max(1, int(1.4 * self.sc)))

    def _flow_dots(self, cv, a, b, col, e, t):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1
        ux, uy = dx / L, dy / L
        speed = (46 + 130 * min(1.4, e.flow_disp)) * self.sc
        spacing = 92 * self.sc if not self.mini else 70 * self.sc
        k = max(1, int(L / spacing))
        base = (t * speed) % spacing
        bright = scale(mix(col, WHITE, 0.55), 0.95)
        for i in range(k):
            s = base + i * spacing
            if s > L:
                continue
            p = (a[0] + ux * s, a[1] + uy * s)
            rr = (2.2 + 1.6 * min(1.3, e.flow_disp)) * self.sc
            cv.g.ellipse([p[0] - rr * 3, p[1] - rr * 3, p[0] + rr * 3, p[1] + rr * 3],
                         fill=scale(bright, 0.13))
            cv.d.ellipse([p[0] - rr, p[1] - rr, p[0] + rr, p[1] + rr], fill=bright)

    def draw_nodes(self, cv, t, labels=True):
        for nid, n in self.nodes.items():
            col = STATE_COL[n.state]
            if n.state == NOM:
                col = mix(CYAN, GREEN, 0.25)
            x, y = n.xy
            r = n.r
            beat = 0.5 + 0.5 * math.sin(t * (2.2 if n.state == NOM else 6.5) + n.phase)
            # body
            pts = hexpts(x, y, r, rot=math.pi / 6)
            cv.d.polygon(pts, fill=mix(PANEL2, col, 0.10 + 0.18 * beat * (n.state != NOM)))
            if n.state == FAIL:
                flick = 0.55 + 0.45 * (1 if self.rng.random() < 0.82 else 0.2)
                neon_poly(cv, pts, scale(RED, flick), w=max(1, int(2.6 * self.sc)),
                          glow=22 * self.sc, ga=0.95)
            elif n.state == ISO:
                neon_poly(cv, pts, BLUE, w=max(1, int(2.4 * self.sc)), glow=18 * self.sc, ga=0.8)
            else:
                neon_poly(cv, pts, col, w=max(1, int(2.2 * self.sc)),
                          glow=(10 + 12 * beat) * self.sc if n.state != NOM else 9 * self.sc,
                          ga=0.75)
            # inner gauge (load)
            lw = r * 1.25
            lh = max(2, int(4 * self.sc))
            bx, by = x - lw / 2, y + r * 0.52
            cv.d.rectangle([bx, by, bx + lw, by + lh], fill=scale(LINE_MID, 0.5))
            lfrac = min(1.0, n.load)
            lcol = GREEN if lfrac < 0.75 else (AMBER if lfrac < 0.98 else RED)
            cv.g.rectangle([bx, by, bx + lw * lfrac, by + lh], fill=scale(lcol, 0.5))
            cv.d.rectangle([bx, by, bx + lw * lfrac, by + lh], fill=lcol)
            # core glow
            core = mix(col, WHITE, 0.35 + 0.3 * beat)
            rr = r * (0.20 + 0.05 * beat)
            cv.g.ellipse([x - rr * 3, y - rr * 3, x + rr * 3, y + rr * 3], fill=scale(col, 0.16 * (0.5 + beat)))
            cv.d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=core)
            # compromised marker (red chevrons)
            if n.compromised > 0.02:
                for i in range(3):
                    ang = t * 2.0 + i * math.tau / 3
                    px = x + math.cos(ang) * r * 1.5
                    py = y + math.sin(ang) * r * 1.5
                    neon_poly(cv, tri(px, py, 5 * self.sc, ang + math.pi / 2), scale(RED, n.compromised),
                              w=1, glow=10, ga=0.9)
            # shield ring
            if n.shielded > 0.02:
                a = n.shielded
                neon_circle(cv, (x, y), r * 1.42, scale(CYAN, a), w=max(1, int(1.8 * self.sc)),
                            glow=12, ga=0.7)
                for i in range(6):
                    ang = -t * 0.9 + i * math.tau / 6
                    px = x + math.cos(ang) * r * 1.42
                    py = y + math.sin(ang) * r * 1.42
                    cv.d.ellipse([px - 2 * self.sc, py - 2 * self.sc, px + 2 * self.sc, py + 2 * self.sc],
                                 fill=scale(CYAN, a))
            # isolated containment
            if n.isolated:
                rr2 = r * 1.62
                for i in range(3):
                    k = (t * 0.5 + i / 3) % 1.0
                    neon_circle(cv, (x, y), rr2 * (0.7 + 0.3 * k), scale(BLUE, 0.5 * (1 - k)),
                                w=max(1, int(1.6 * self.sc)), glow=8, ga=0.5)
            # hit flash
            if n.hit_flash > 0.01:
                cv.g.ellipse([x - r * 2.4, y - r * 2.4, x + r * 2.4, y + r * 2.4],
                             fill=scale(RED, 0.30 * n.hit_flash))
            if n.heal_flash > 0.01:
                cv.g.ellipse([x - r * 2.6, y - r * 2.6, x + r * 2.6, y + r * 2.6],
                             fill=scale(GREEN, 0.26 * n.heal_flash))
            if labels:
                fsz = max(9, int(15 * self.sc))
                text(cv.d, (x, y + r * 0.52 + 12 * self.sc), n.label, FUI(fsz),
                     WHITE, anchor="ma", glow_draw=cv.g, glow_a=0.25)
                text(cv.d, (x, y + r * 0.52 + 12 * self.sc + fsz * 0.95), n.sub, FMONO(max(7, int(10 * self.sc))),
                     scale(col, 0.85), anchor="ma")
                if n.crit:
                    text(cv.d, (x - r * 1.15, y - r * 0.95), "★", FUI(max(9, int(13 * self.sc))),
                         AMBER, anchor="ma", glow_draw=cv.g, glow_a=0.4)

    def draw_fx(self, cv):
        for f in self.fx:
            f.draw(cv)
        for p, _ in self.shots:
            p.draw(cv)


# ------------------------------------------------------------------ agent swarms
class Swarm:
    """team drones hovering around an anchor point"""

    def __init__(self, anchor, n=3, sc=1.0, seed=3, spread=(70.0, 130.0), side="red"):
        self.anchor = anchor
        self.side = side  # 'red' | 'blue'
        self.sc = sc
        self.spread = spread
        self.rng = random.Random(seed)
        self.drones = []
        for i in range(n):
            self.drones.append(dict(
                ang=self.rng.uniform(0, math.tau),
                rx=self.rng.uniform(0.45, 1.0) * spread[0] * sc,
                ry=self.rng.uniform(0.45, 1.0) * spread[1] * sc,
                spd=self.rng.uniform(0.35, 0.75) * (1 if i % 2 else -1),
                bob=self.rng.uniform(0, math.tau),
                dash=None, dash_t=0.0, hold=0.0,
            ))
        self.col = RED if side == "red" else CYAN

    def step(self, dt):
        for d in self.drones:
            d["ang"] += d["spd"] * dt
            d["bob"] += dt * 3.0
            if d["dash"] is not None:
                d["dash_t"] += dt
                if d["dash_t"] > d["dash"][2] + d["hold"]:
                    d["dash"] = None

    def pos(self, i, t):
        d = self.drones[i]
        ax, ay = self.anchor
        px = ax + math.cos(d["ang"]) * d["rx"]
        py = ay + math.sin(d["ang"]) * d["ry"] + math.sin(d["bob"]) * 8 * self.sc
        if d["dash"] is not None:
            p0, p1, dur = d["dash"]
            u = min(1.0, d["dash_t"] / dur)
            e = u * u * (3 - 2 * u)
            px = p0[0] + (p1[0] - p0[0]) * e
            py = p0[1] + (p1[1] - p0[1]) * e
            if d["dash_t"] > dur:
                k = (d["dash_t"] - dur) / max(0.001, d["hold"])
                px = px + math.sin(k * 12) * 3 * self.sc
        return (px, py)

    def dash_to(self, i, xy, dur=0.5, hold=0.0):
        p0 = self.pos(i, 0)
        self.drones[i]["dash"] = (p0, xy, dur)
        self.drones[i]["dash_t"] = 0.0
        self.drones[i]["hold"] = hold

    def draw(self, cv, t, alert=0.0, active=1.0):
        for i, d in enumerate(self.drones):
            x, y = self.pos(i, t)
            s = self.sc
            col = scale(self.col, 0.35 + 0.65 * active)
            if alert:
                col = mix(col, WHITE, 0.4 * alert * (0.5 + 0.5 * math.sin(t * 14 + i)))
            if self.side == "red":
                pts = tri(x, y, 11 * s, t * 1.6 + i)
                neon_poly(cv, pts, col, w=2, glow=16 * s, ga=0.85, fill=scale(RED_DEEP, 0.65))
                cv.d.ellipse([x - 2.5 * s, y - 2.5 * s, x + 2.5 * s, y + 2.5 * s], fill=WHITE)
                for k in range(4):
                    a = t * 1.6 + i + k * 0.35
                    px = x - math.cos(a) * (12 + k * 7) * s
                    py = y - math.sin(a) * (12 + k * 7) * s
                    cv.g.ellipse([px - 3 * s, py - 3 * s, px + 3 * s, py + 3 * s],
                                 fill=scale(col, 0.16 * (1 - k / 4)))
            else:
                neon_circle(cv, (x, y), 10 * s, col, w=2, glow=16 * s, ga=0.85,
                            fill=scale((0, 40, 60), 0.8))
                pts = []
                for k in range(6):
                    a = math.pi / 180 * (60 * k - 30) + t * 0.8 + i
                    pts.append((x + 12 * s * math.cos(a), y + 12 * s * math.sin(a)))
                neon_poly(cv, pts, scale(col, 0.8), w=1, glow=10, ga=0.6)
                cv.d.ellipse([x - 2.5 * s, y - 2.5 * s, x + 2.5 * s, y + 2.5 * s], fill=WHITE)
