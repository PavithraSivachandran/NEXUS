"""NEXUS simulation film — scene renderer."""
import math
import random

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from fx import *
from grid import (CRIT, FAIL, ISO, NOM, STRESS, Battle, Swarm, EDGES, NODES)
from theme import *
from widgets import (background, bar, bars_compare, chart, chip, danger_stripes,
                     hline, log_panel, meter, panel, stat, team_plate)

# ------------------------------------------------------------------ layout
FIELD0 = (520, 120, 1484, 890)
GATE_X = 468
LP = (24, 100, 384, 1058)
RP = (1536, 100, 1896, 1058)
CENTER = (392, 100, 1528, 1058)

T_TITLE = 11.0
T_ATTACK = 25.0
T_CASC = 48.4
T_DEF = 68.0
T_SELF = 100.0
T_PROOF = 150.0
T_END = 172.0
T_TOTAL = 180.0

CHAIN = [
    dict(n=1, name="SPOOF SENSOR",     tgt="SUBA", tl="SUB-A",        t=26.0, dur=1.30,
         note="inject false load reading", act="spoof"),
    dict(n=2, name="DELAY TELEMETRY",  tgt="TELE", tl="TELEMETRY BUS", t=31.0, dur=1.30,
         note="buffer 4.2s · blind operator", act="delay"),
    dict(n=3, name="ALTER CONTROL",    tgt="LN2",  tl="LINE-2",       t=36.0, dur=1.30,
         note="no control path from SCADA", act="reject"),
    dict(n=4, name="ALTER SETPOINT",   tgt="SUBA", tl="SUB-A",        t=41.0, dur=1.30,
         note="raise transfer limit +12%", act="setpoint"),
    dict(n=5, name="TRIP BREAKER",     tgt="LN1",  tl="LINE-1",       t=47.0, dur=1.45,
         note="force open SUB-A → LINE-1", act="trip"),
]

OPTIONS = [
    dict(k="A", name="ISOLATE SUB-A", detail="cut foothold · shed 44% city load · close tie",
         after=21, col=GREEN, pick=True),
    dict(k="B", name="SWITCH TRANSMISSION PATH", detail="close SUB-B ↔ LINE-1 tie only",
         after=34, col=AMBER, pick=False),
    dict(k="C", name="NO INTERVENTION", detail="cascade continues unchecked",
         after=87, col=RED, pick=False),
]

PHASES = [
    (0.0, "TWIN",       "00 · DIGITAL TWIN — SYNTHETIC GRID ONLINE"),
    (25.0, "ATTACK",    "04 · RED AGENT — UNSCRIPTED CHAIN GENERATION"),
    (48.4, "CASCADE",   "07 · CASCADE INTELLIGENCE — BLAST RADIUS PREDICTION"),
    (68.0, "DEFEND",    "08 · BLUE AI + HUMAN — EXPLAINABLE RESPONSE"),
    (100.0, "SELF-PLAY", "09 · SELF-PLAY — 120 BATTLES, ENGINE HARDENS"),
    (150.0, "PROOF",    "10 · PROOF — BEFORE / AFTER · LIVING DEFENSE"),
]

BLAST_K = 1.30       # display gain (model calibration)
CP_A, CP_B, CP_C, CP_D = 0.13, 0.25, 0.12, 0.35
RISK_A, RISK_B = 4.4, 6.85


def clamp01(v):
    return 0.0 if v < 0 else (1.0 if v > 1 else v)


def ease(t):
    t = clamp01(t)
    return t * t * (3 - 2 * t)


def ease_out(t):
    t = clamp01(t)
    return 1 - (1 - t) ** 3


def appear(t, t0, d=0.45):
    return ease((t - t0) / d)


def pulse(t, f=1.0, lo=0.0):
    return lo + (1 - lo) * (0.5 + 0.5 * math.sin(t * f * math.tau))


# ================================================================== renderer
class Renderer:
    def __init__(self, seed=7):
        self.seed = seed
        self.rng = random.Random(seed)
        self.b = Battle(FIELD0, seed=seed, sc=1.0)
        self.red = Swarm((GATE_X - 62, 505), n=3, sc=1.0, seed=11, spread=(30, 168), side="red")
        self.blue = Swarm((FIELD0[2] - 250, 380), n=3, sc=1.0, seed=23, spread=(120, 190), side="blue")
        self.blue2 = Swarm((FIELD0[0] + 300, 760), n=2, sc=1.0, seed=31, spread=(150, 120), side="blue")
        self.pops = []
        self.sched = []
        self.fired = set()
        self.t = 0.0
        self.detection = None
        self.selected = None
        self.opt_shown = 0.0
        self.cursor = (0.0, 0.0)
        self.zoom = 1.0
        self.camx = self.camy = 0.0
        self.spotlight = None
        self.chain_state = {c["n"]: "hidden" for c in CHAIN}
        self.minis = []
        self.series = dict(det=[], sev=[], dfn=[])
        self.battle_no = 0
        self.mini_cycle = -1
        self.red_wins = 0
        self.blue_wins = 0
        self.shielded = []
        self.replay_shots = 0
        self._build_minis()
        self._build_schedule()

    # -------------------------------------------------- setup
    def _build_minis(self):
        boxes = [(404, 152, 920, 548), (1000, 152, 1516, 548),
                 (404, 612, 920, 1008), (1000, 612, 1516, 1008)]
        for i, bx in enumerate(boxes):
            self.minis.append(dict(box=bx, b=Battle(bx, seed=500 + i, sc=0.42, mini=True),
                                   res=None, res_t=-9, idx=-1, done=True))

    def _build_schedule(self):
        S = self.sched
        b = self.b
        # ---- attack chain
        for c in CHAIN:
            S.append((c["t"], f"launch{c['n']}", (lambda cc: (lambda: self._launch(cc)))(c)))

        # ---- cascade beats
        def beat(t, key, fn):
            S.append((t, key, fn))

        beat(49.5, "c1", lambda: (b.sever("e6"),
                                   b.say("FEEDER 6 TRIPPED — PUMP STATION SUPPLY LOSS", "bad"),
                                   self.pop(self.b.xy("PUMP"), "SUPPLY LOSS", RED, dur=2.6, size=22)))
        beat(51.0, "c2", lambda: (b.say("HOSPITAL ON BACKUP POWER — 04:00 REMAINING", "bad"),
                                  self.pop(self.b.xy("HOSP"), "BACKUP 04:00", AMBER, dur=2.8, size=22)))
        beat(52.4, "c3", lambda: (b.sever("e7"),
                                  b.say("DISTRICT 7 DE-ENERGIZED — 320 MW LOST", "bad"),
                                  self.pop(self.b.xy("CITY"), "-320 MW", RED, dur=2.6, size=24)))
        beat(54.2, "c4", lambda: (b.restore("e8", GREEN),
                                  b.say("AUTO-RECLOSER: TIE LINE-2 ↔ CITY CLOSED", "warn"),
                                  self.pop(self.b.xy("LN2"), "TIE CLOSED", AMBER, dur=2.4, size=20)))
        beat(56.0, "c5", lambda: (b.say("TIE LINE-2 ↔ CITY AT 107% — OVERLOAD", "bad"),
                                  self.pop(self.b.xy("CITY"), "OVERLOAD 107%", ORANGE, dur=3.0, size=22)))
        beat(58.5, "c6", lambda: b.say("RAIL SIGNAL GRID — FEED AT RISK", "warn"))
        beat(57.0, "pred", lambda: (b.say("PREDICTED PATH: SUB-A → LINE-1 → PUMP → HOSPITAL", "red"),
                                    setattr(self, "spotlight", 1.0)))
        beat(60.0, "log_peak", lambda: b.say("BLAST ENVELOPE STABILIZING — 3 CRITICAL ASSETS", "bad"))
        beat(63.0, "alarm", lambda: self.pop((960, 300), "CASCADE PROBABILITY 87%", RED, dur=3.4, size=34))

        # ---- detection
        beat(T_DEF, "detect", self._detect)
        beat(70.5, "opt_in", lambda: setattr(self, "opt_shown", 1.0))
        beat(73.0, "cur", lambda: setattr(self, "cursor", (1.0, 0.0)))
        beat(77.6, "select", self._select)
        beat(79.4, "contain", self._contain)
        beat(81.2, "reroute", self._reroute)
        beat(83.0, "heal", self._heal)
        beat(86.0, "stabilize", lambda: (b.say("GRID STABILIZED — CASCADE 87% → 21%", "good"),
                                         self.pop((960, 260), "CASCADE HALTED", GREEN, dur=3.0, size=38)))
        beat(90.0, "score", lambda: (b.say("BATTLE 001 SCORED — PROTON +1 · PLAYBOOK UPDATED", "good")))

        # ---- self play
        beat(T_SELF, "selfplay", lambda: b.say("SELF-PLAY ENGAGED — 120 BATTLES QUEUED", "blue"))
        # ---- proof
        beat(T_PROOF + 2.0, "replay1", lambda: self._replay(0))
        beat(T_PROOF + 4.6, "replay2", lambda: self._replay(1))
        beat(T_PROOF + 7.2, "replay3", lambda: self._replay(2))
        beat(T_PROOF + 10.5, "hard", lambda: (b.say("HARDENING PLAYBOOK APPLIED TO TWIN", "good"),
                                              self.pop((960, 250), "TWIN HARDENED", GREEN, dur=3.0, size=38)))
        S.sort(key=lambda x: x[0])

    # -------------------------------------------------- helpers
    def pop(self, xy, txt, col, dur=2.2, size=20, rise=46):
        x = min(xy[0], 1300.0)
        self.pops.append(dict(t0=self.t, xy=(x, xy[1]), txt=txt, col=col, dur=dur,
                              size=size, rise=rise))

    def gate_pt(self, y):
        return (GATE_X, max(FIELD0[1] + 40, min(FIELD0[3] - 40, y)))

    # -------------------------------------------------- actions
    def _launch(self, c):
        b = self.b
        tgt = b.xy(c["tgt"])
        drone = self.red.drones[c["n"] % 3]
        start = self.red.pos(c["n"] % 3, self.t)
        self.red.dash_to(c["n"] % 3, (GATE_X - 62, tgt[1] * 0.5 + 530 * 0.5), dur=0.35, hold=0.5)
        if c["act"] == "reject":
            end = self.gate_pt(tgt[1])
            path = [start, (GATE_X - 150, start[1] * 0.6 + end[1] * 0.4), end]
        else:
            gp = self.gate_pt(tgt[1])
            path = [start, (GATE_X - 150, start[1] * 0.55 + tgt[1] * 0.45), gp,
                    (gp[0] + (tgt[0] - gp[0]) * 0.45, gp[1] + (tgt[1] - gp[1]) * 0.8), tgt]
        self.chain_state[c["n"]] = "flight"

        def on_hit(p):
            if c["act"] == "reject":
                self.chain_state[c["n"]] = "reject"
                b.burst(p.pos, RED, n=34, speed=(90, 420), size=2.4)
                b.shock(p.pos, RED, rmax=120, life=0.6, w=3)
                b.shake_it(6)
                b.say(f"VALIDATOR REJECT — {c['tl']}: NO CONTROL PATH", "bad")
                self.pop((GATE_X + 40, p.pos[1] - 40), "REJECTED", RED, dur=2.4, size=22)
                b.after(0.9, lambda: (self.chain_state.__setitem__(4, "gen"),
                                      b.say("RED AGENT REVISING STRATEGY — NEW CHAIN PROPOSED", "warn")))
                return
            self.chain_state[c["n"]] = "done"
            col = RED
            b.arc((p.pos[0] - 90, p.pos[1] - 60), p.pos, RED, life=0.35, amp=30, segs=12, w=3, branches=4)
            b.burst(p.pos, RED, n=30, speed=(100, 460), size=2.6)
            b.burst(p.pos, WHITE, n=12, speed=(40, 220), size=1.8)
            b.shock(p.pos, RED, rmax=150, life=0.7, w=3)
            b.shake_it(7)
            b.flash_it(0.12, (255, 120, 110))
            if c["act"] == "spoof":
                b.compromise("SUBA", 0.45)
                b.nodes["SUBA"].spoofed = True
                b.say("SUB-A SENSOR STREAM SPOOFED", "red")
                self.pop(b.xy("SUBA"), "SENSOR SPOOF", RED, dur=2.2, size=19)
            elif c["act"] == "delay":
                b.compromise("TELE", 0.6)
                for e in b.edges:
                    if e.a == "TELE" or e.b == "TELE":
                        e.state = 4
                b.nodes["CTRL"].degraded = True
                b.say("TELEMETRY STREAM DELAYED 4.2s — OPERATOR BLINDED", "red")
                self.pop(b.xy("TELE"), "TELEMETRY +4.2s", RED, dur=2.2, size=19)
                self.pop(b.xy("CTRL"), "SCADA BLIND", AMBER, dur=2.2, size=17)
            elif c["act"] == "setpoint":
                b.compromise("SUBA", 0.6)
                b.nodes["SUBA"].target_load = 1.05
                b.say("SUB-A SETPOINT ALTERED — TRANSFER LIMIT +12%", "red")
                self.pop(b.xy("SUBA"), "SETPOINT +12%", RED, dur=2.2, size=19)
            elif c["act"] == "trip":
                b.say("BREAKER 52-B FORCED OPEN — SUB-A → LINE-1", "bad")
                self.pop((960, 240), "BREAKER TRIP", ORANGE, dur=2.6, size=34)
                b.sever("e3")
                b.nodes["LN1"].hit_flash = 1.0
                b.after(0.35, lambda: (b.burst(b.xy("LN1"), RED, n=40, speed=(120, 560), size=2.8),
                                       b.shock(b.xy("LN1"), ORANGE, rmax=260, life=0.9, w=4),
                                       b.shake_it(12), b.flash_it(0.2, (255, 150, 120))))
        self.b.launch(path, scale(RED, 1.0), speed=760, on_hit=on_hit, size=5.5,
                      head=WHITE, trail=18, wobble=3.0)

    def _detect(self):
        b = self.b
        self.detection = 42.0
        b.detected = True
        b.ping(b.xy("CTRL"), CYAN, rmax=420, life=1.3, w=3)
        b.ping(b.xy("SUBA"), CYAN, rmax=300, life=1.1, w=2)
        b.shake_it(5)
        b.flash_it(0.14, (140, 220, 255))
        b.say("THREAT DETECTED — SENSOR MANIPULATION + CONTROL DISRUPTION", "blue")
        self.pop((960, 300), "THREAT DETECTED", CYAN, dur=3.2, size=40)
        for d in range(2):
            self.blue.dash_to(d, b.xy("SUBA"), dur=0.7, hold=2.0)
        self.blue2.dash_to(0, b.xy("HOSP"), dur=0.7, hold=2.0)

    def _select(self):
        self.selected = "A"
        self.b.say("OPERATOR SELECTS OPTION A — ISOLATE SUB-A", "good")
        self.pop((960, 300), "OPTION A SELECTED", GREEN, dur=2.6, size=30)

    def _contain(self):
        b = self.b
        b.say("ISOLATING SUB-A — CONTAINMENT BARRIER ACTIVE", "good")
        b.isolate("SUBA")
        b.shock(b.xy("SUBA"), CYAN, rmax=300, life=0.9, w=4)
        b.burst(b.xy("SUBA"), CYAN, n=36, speed=(100, 420), size=2.4)
        b.flash_it(0.12, (120, 220, 255))
        b.shake_it(6)
        for e in b.edges:
            if e.a == "SUBA" or e.b == "SUBA":
                if e.state != 2:
                    e.state = 2
                    e.sever_t = b.t
                    a, bb = b.xy(e.a), b.xy(e.b)
                    m = ((a[0] + bb[0]) / 2, (a[1] + bb[1]) / 2)
                    b.burst(m, CYAN, n=22, speed=(80, 330), size=2.2)
        self.pop(b.xy("SUBA"), "ISOLATED", CYAN, dur=2.4, size=22)

    def _reroute(self):
        b = self.b
        b.say("CLOSING TIE SUB-B ↔ LINE-1 — ALTERNATE FEED", "good")
        e = [x for x in b.edges if x.id == "e16"][0]
        e.state = 3
        e.sever_t = b.t
        a, bb = b.xy("SUBB"), b.xy("LN1")
        path = [a, ((a[0] + bb[0]) / 2, a[1] - 40), bb]
        b.launch(path, GREEN, speed=900, size=5.0, trail=20, head=WHITE,
                 on_hit=lambda p: (b.burst(p.pos, GREEN, n=26, speed=(90, 380), size=2.2),
                                   b.ping(p.pos, GREEN, rmax=180, life=0.8, w=3)))
        b.recompute()

    def _heal(self):
        b = self.b
        for eid in ("e6", "e7"):
            e = [x for x in b.edges if x.id == eid][0]
            if e.state == 2:
                e.state = 3
        b.nodes["CITY"].demand = 180.0
        b.total_demand = sum(n.demand for n in b.nodes.values())
        b.recompute()
        for nid in ("LN1", "PUMP", "HOSP", "RAIL", "CITY", "CTRL"):
            n = b.nodes[nid]
            if n.state != NOM:
                n.heal_flash = 1.0
            n.state = NOM
            n.backup = n.backup_max
            n.compromised = 0.0
            b.ping(n.xy, GREEN, rmax=170, life=0.9, w=2)
        b.nodes["TELE"].compromised = 0.0
        b.say("LOAD SHED 44% — CITY DISTRICT 7 ON ROTATION", "warn")
        b.say("PUMP STATION + HOSPITAL RE-ENERGIZED VIA TIE", "good")
        b.shield("HOSP")
        b.shield("PUMP")
        b.shield("RAIL")
        b.recompute()

    def _replay(self, k):
        b = self.b
        targets = ["SUBA", "LN1", "HOSP"]
        tgt = b.xy(targets[k % 3])
        start = self.red.pos(k % 3, self.t)
        gp = self.gate_pt(tgt[1])
        path = [start, (GATE_X - 150, start[1] * 0.5 + tgt[1] * 0.5), gp, tgt]
        self.red.dash_to(k % 3, (GATE_X - 62, tgt[1]), dur=0.4, hold=1.2)

        def blocked(p):
            b.burst(p.pos, CYAN, n=30, speed=(110, 420), size=2.4)
            b.shock(p.pos, CYAN, rmax=150, life=0.7, w=3)
            b.shake_it(4)
            b.ping(p.pos, CYAN, rmax=200, life=0.8, w=2)
            self.pop((p.pos[0] + 30, p.pos[1] - 50), "BLOCKED", CYAN, dur=1.8, size=20)
            b.say(f"ATTACK VECTOR {k+1} NEUTRALIZED BY LEARNED POLICY", "good")
        b.launch(path, RED, speed=820, on_hit=blocked, size=5.0, head=WHITE, trail=16)

    # -------------------------------------------------- update
    def update(self, t, dt):
        self.t = t
        # scheduled events
        while self.sched and self.sched[0][0] <= t:
            tt, key, fn = self.sched.pop(0)
            if key not in self.fired:
                self.fired.add(key)
                fn()
        # chain card generation states
        for c in CHAIN:
            if self.chain_state[c["n"]] == "hidden" and t >= c["t"] - 2.4:
                self.chain_state[c["n"]] = "gen"
        # camera
        if T_CASC <= t < 78:
            self.zoom = 1.0 + 0.055 * ease((t - T_CASC) / 3.0)
            self.camx = -60 * ease((t - T_CASC) / 4.0)
            self.camy = 90 * ease((t - T_CASC) / 4.0)
        elif t >= 78:
            k = ease((t - 78) / 3.0)
            self.zoom = 1.055 - 0.055 * k
            self.camx = -60 * (1 - k)
            self.camy = 90 * (1 - k)
        # swarms
        self.red.step(dt)
        self.blue.step(dt)
        self.blue2.step(dt)
        self.b.step(dt)
        # pops expire
        self.pops = [p for p in self.pops if t - p["t0"] < p["dur"]]
        if self.spotlight is not None:
            self.spotlight = max(0.0, self.spotlight - dt * 0.15)
        # self-play
        if T_SELF <= t < T_PROOF:
            self._update_minis(t, dt)
        # cursor
        if self.cursor[0] > 0:
            self.cursor = (1.0, min(1.0, self.cursor[1] + dt))

    # -------------------------------------------------- mini battles
    def _update_minis(self, t, dt):
        PERIOD = 1.55
        cyc = int((t - T_SELF) // PERIOD)
        ph = (t - T_SELF) - cyc * PERIOD
        for i, m in enumerate(self.minis):
            b = m["b"]
            bx = m["box"]
            if cyc != m["idx"] and ph < 0.05:
                m["idx"] = cyc
                m["done"] = False
                m["res"] = None
                b.heal_all()
                battle_no = cyc * 4 + i + 1
                m["no"] = battle_no
                u = min(1.0, (battle_no - 1) / 119.0)
                rr = random.Random(battle_no * 7919)
                pwin = 0.34 + (0.81 - 0.34) * (1 - math.exp(-4.0 * u))
                m["blue_win"] = rr.random() < pwin
                m["u"] = u
                tgt = rr.choice(["LN1", "SUBA", "CITY", "PUMP", "RAIL", "LN2"])
                m["tgt"] = tgt
                start = (bx[0] - 40, (bx[1] + bx[3]) / 2)
                end = b.xy(tgt)
                path = [start, (bx[0] + (bx[2] - bx[0]) * 0.35, start[1] * 0.4 + end[1] * 0.6), end]
                if m["blue_win"]:
                    mid = ((start[0] + end[0]) / 2, start[1] * 0.35 + end[1] * 0.65)
                    b.launch(path[:2] + [mid], RED, speed=1400, size=3.4, trail=12,
                             on_hit=lambda p: (b.burst(p.pos, CYAN, n=18, speed=(60, 240), size=1.8),
                                               b.ping(p.pos, CYAN, rmax=90, life=0.6, w=2),
                                               b.say("INTERCEPT — ATTACK BLOCKED", "good")))
                else:
                    b.launch(path, RED, speed=1400, size=3.4, trail=12,
                             on_hit=lambda p: (b.burst(p.pos, RED, n=20, speed=(70, 280), size=2.0),
                                               b.shock(p.pos, ORANGE, rmax=110, life=0.55, w=2),
                                               b.compromise(tgt, 0.8),
                                               b.say(f"BREACH — {tgt} DEGRADED", "bad")))
            if not m["done"] and ph > 0.95:
                m["done"] = True
                m["res"] = "BLUE" if m["blue_win"] else "RED"
                m["res_t"] = t
                if m["blue_win"]:
                    self.blue_wins += 1
                else:
                    self.red_wins += 1
                self.battle_no = max(self.battle_no, m.get("no", 0))
                u = m.get("u", 0.0)
                rr = random.Random(m.get("no", 1) * 104729)
                self.series["det"].append(9.0 + 33.0 * math.exp(-4.0 * u) + rr.uniform(-0.8, 0.8))
                self.series["sev"].append(2.1 + 5.7 * math.exp(-4.0 * u) + rr.uniform(-0.16, 0.16))
                self.series["dfn"].append(81.0 - 47.0 * math.exp(-4.0 * u) + rr.uniform(-1.6, 1.6))
            b.step(dt)

    # ================================================================== draw
    def render(self, t):
        cv = Canvas()
        cv.base.paste(background(), (0, 0))
        cv.d = ImageDraw.Draw(cv.base, "RGBA")
        if t < T_TITLE:
            self._title(cv, t)
        elif t < T_END:
            self._hud(cv, t)
        else:
            self._endcard(cv, t)
        img = cv.finish()
        arr = bloom(img, thr=0.50, strength=1.05)
        # global flash + shake
        shake = self.b.shake if self.b.shake > 0 else 0.0
        rng = np.random.default_rng(int(t * 30) & 0xFFFF)
        out = post(arr, grain=0.014, vignette=1.0,
                   aberration=min(6.0, shake * 0.45) if shake > 3 else 0.0,
                   rng=rng, flash=self.b.flash,
                   flash_color=self.b.flash_col)
        im = Image.fromarray(out)
        if shake > 0.3:
            dx = int((rng.random() - 0.5) * shake * 1.6)
            dy = int((rng.random() - 0.5) * shake * 1.6)
            im = im.transform((W, H), Image.AFFINE, (1, 0, -dx, 0, 1, -dy), resample=Image.BILINEAR)
        # phase caption + scanline overlay
        d = ImageDraw.Draw(im, "RGBA")
        if T_TITLE <= t < T_END:
            self._caption(d, t)
        return im

    # -------------------------------------------------- title
    def _title(self, cv, t):
        d, g = cv.d, cv.g
        # faint grid silhouette
        a = clamp01((t - 4.0) / 3.0)
        if a > 0:
            for e in EDGES:
                sp = next(s for s in NODES if s["id"] == e["a"])
                sp2 = next(s for s in NODES if s["id"] == e["b"])
                p0 = (W / 2 + (sp["x"] - 0.5) * 900, 560 + (sp["y"] - 0.5) * 620)
                p1 = (W / 2 + (sp2["x"] - 0.5) * 900, 560 + (sp2["y"] - 0.5) * 620)
                cv.d.line([p0, p1], fill=(30, 70, 110, int(90 * a)), width=1)
        # wordmark
        big = FDISP(150)
        txt = "NEXUS"
        w = d.textlength(txt, font=big)
        x = W / 2 - w / 2
        y = 300
        ra = clamp01((t - 0.7) / 0.9)
        if ra > 0:
            # glitch slices
            off = max(0.0, 1.0 - t * 1.4)
            for k in range(6):
                if off <= 0.001:
                    break
                yy = y + k * 26
                dx = (random.Random(int(t * 22) + k).uniform(-1, 1)) * 60 * off
                d.text((x + dx, yy), txt, font=big, fill=(int(255 * off * 0.7), 20, 40, 255))
            d.text((x, y), txt, font=big, fill=(240, 250, 255, int(255 * ra)))
            # chromatic
            g.text((x - 3, y), txt, font=big, fill=scale(RED, 0.28 * ra))
            g.text((x + 3, y), txt, font=big, fill=scale(CYAN, 0.28 * ra))
            # underline sweep
            ua = clamp01((t - 1.9) / 0.8)
            uw = w * ua
            g.line([(x, y + 172), (x + uw, y + 172)], fill=scale(CYAN, 0.5), width=8)
            d.line([(x, y + 172), (x + uw, y + 172)], fill=CYAN, width=2)
        # subtitle
        sa = appear(t, 2.6, 1.0)
        if sa:
            text(d, (W / 2, y + 200), "THE DIGITAL TWIN THAT ATTACKS ITSELF", FDISP(34),
                 scale(WHITE, sa), anchor="ma", tracking=4, glow_draw=g, glow_a=0.4 * sa)
            text(d, (W / 2, y + 244), "BEFORE REAL ATTACKERS DO.", FDISP(34),
                 scale(CYAN, sa), anchor="ma", tracking=4, glow_draw=g, glow_a=0.4 * sa)
        ta = appear(t, 4.0, 1.0)
        if ta:
            text(d, (W / 2, y + 300), "TEAM DECODE  ·  HACKATHON BLUEPRINT  ·  LIVE SIMULATION",
                 FUI(20), scale(AMBER, ta), anchor="ma", tracking=5, glow_draw=g, glow_a=0.35 * ta)
        # team plates
        for i, (name, tag, col, side) in enumerate(
                (("ULTRON", "RED AI SWARM · ATTACKER", RED, -1),
                 ("PROTON", "BLUE AI + HUMAN · DEFENDER", CYAN, 1))):
            aa = appear(t, 5.6 + i * 0.35, 0.9)
            if aa <= 0:
                continue
            w2, h2 = 400, 96
            x0 = W / 2 + side * (300 + (1 - aa) * 320) - (0 if side < 0 else w2)
            y0 = 640
            box = [x0, y0, x0 + w2, y0 + h2]
            d.rounded_rectangle(box, radius=8, fill=mix(PANEL, col, 0.07) + (int(230 * aa),),
                                outline=scale(col, 0.5 * aa) + (255,), width=2)
            g.rounded_rectangle(box, radius=8, outline=scale(col, 0.08 * aa))
            cx = x0 + 52 if side < 0 else x0 + w2 - 52
            if side < 0:
                neon_poly(cv, tri(cx, y0 + h2 / 2, 18, t * 1.4), scale(col, aa), w=2, glow=20,
                          ga=0.8, fill=scale(RED_DEEP, 0.6))
            else:
                neon_circle(cv, (cx, y0 + h2 / 2), 16, scale(col, aa), w=2, glow=20, ga=0.8)
                for k in range(6):
                    ang = t + k * math.tau / 6
                    px = cx + 20 * math.cos(ang)
                    py = y0 + h2 / 2 + 20 * math.sin(ang)
                    d.ellipse([px - 2, py - 2, px + 2, py + 2], fill=scale(col, aa))
            tx = x0 + 90 if side < 0 else x0 + 22
            text(d, (tx, y0 + 20), name, FDISP(34), scale(col, aa), tracking=6,
                 glow_draw=g, glow_a=0.5 * aa)
            text(d, (tx, y0 + 62), tag, FMONO(13), scale(col, 0.6 * aa))
        va = appear(t, 6.6, 0.6)
        if va:
            text(d, (W / 2, 668), "VS", FDISP(40), scale(WHITE, va), anchor="ma", tracking=3,
                 glow_draw=g, glow_a=0.5 * va)
        # bottom ticker
        if t > 7.2:
            k = int((t - 7.2) * 24) % 200
            msg = "RED AI  →  CASCADE  →  BLUE AI SELF-PLAY  →  HARDEN  →  REPEAT"
            text(d, (W / 2, 812), msg, FUI(18), scale(GREY, 0.9), anchor="ma", tracking=3)
        # glitch wipe out
        if t > T_TITLE - 0.5:
            a = (t - (T_TITLE - 0.5)) / 0.5
            for i in range(30):
                yy = int(i * H / 30)
                hh = int(H / 30)
                dx = int((random.Random(int(t * 60) + i).uniform(-1, 1)) * 200 * a)
                region = cv.base.crop((0, yy, W, yy + hh))
                cv.base.paste(region, (dx, yy))
            d.rectangle([0, 0, W, H], fill=(0, 0, 0, int(255 * a * 0.7)))

    # -------------------------------------------------- HUD master
    def _hud(self, cv, t):
        self._field(cv, t)
        self._gate(cv, t)
        if T_SELF <= t < T_PROOF:
            self._panel_selfplay_left(cv, t)
            self._panel_selfplay_right(cv, t)
            self._minis(cv, t)
        elif T_PROOF <= t:
            self._panel_proof_left(cv, t)
            self._panel_proof_right(cv, t)
            self._proof_field(cv, t)
        else:
            self._panel_ultron(cv, t)
            self._panel_proton(cv, t)
        self._topbar(cv, t)
        if not (T_SELF <= t < T_PROOF):
            self._bottombar(cv, t)
        self._pops(cv, t)
        if self.b.blast > 0.25 and t < T_PROOF:
            self._alarm_frame(cv, t)

    # -------------------------------------------------- battlefield
    def _field(self, cv, t):
        f = FIELD0
        z = self.zoom
        cx = (f[0] + f[2]) / 2 + self.camx
        cy = (f[1] + f[3]) / 2 + self.camy
        w = (f[2] - f[0]) / z
        h = (f[3] - f[1]) / z
        rect = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
        b = self.b
        b.set_rect(rect)
        for n in b.nodes.values():
            n.r = 34 * z
        self.red.anchor = (rect[0] - 58, cy)
        self.blue.anchor = (rect[2] - 200, rect[1] + 200)
        self.blue2.anchor = (rect[0] + 250, rect[3] - 165)
        # arena frame
        d, g = cv.d, cv.g
        bx = [rect[0] - 46, rect[1] - 46, rect[2] + 46, rect[3] + 46]
        d.rounded_rectangle(bx, radius=14, fill=(7, 12, 20, 150), outline=LINE_MID + (120,), width=1)
        for (px, py, sx, sy) in ((bx[0], bx[1], 1, 1), (bx[2], bx[1], -1, 1),
                                 (bx[0], bx[3], 1, -1), (bx[2], bx[3], -1, -1)):
            L = 22
            g.line([(px + sx * 2, py + sy * L), (px + sx * 2, py + sy * 2), (px + sx * L, py + sy * 2)],
                   fill=scale(CYAN, 0.10), width=6)
            d.line([(px + sx * 2, py + sy * L), (px + sx * 2, py + sy * 2), (px + sx * L, py + sy * 2)],
                   fill=scale(CYAN, 0.55), width=2)
        text(d, (bx[0] + 16, bx[1] + 12), "DIGITAL TWIN · SYNTHETIC GRID v0.1", FMONO(11),
             scale(CYAN, 0.55))
        text(d, (bx[2] - 16, bx[1] + 12), "ISOLATED SIM PLANE", FMONO(11),
             scale(GREEN, 0.55), anchor="ra")
        # title of field
        text(d, (bx[0] + 16, bx[3] - 18), "TOPOLOGY: 11 ASSETS · 15 LINKS · LIVE TELEMETRY",
             FMONO(11), scale(GREY, 0.6))
        # draw
        b.draw_edges(cv, t)
        if self.spotlight and self.spotlight > 0:
            self._predicted_path(cv, t)
        b.draw_nodes(cv, t, labels=True)
        b.draw_fx(cv)
        self.red.draw(cv, t, alert=0.7 if self.b.blast > 0.1 else 0.0)
        self.blue.draw(cv, t)
        self.blue2.draw(cv, t)
        # epicenter marker during cascade
        if T_CASC <= t < 90 and self.b.blast > 0.2:
            ep = b.xy("LN1")
            k = (t * 0.7) % 1.0
            neon_circle(cv, ep, 40 + 60 * k, scale(RED, 0.5 * (1 - k)), w=2, glow=10, ga=0.5)

    def _predicted_path(self, cv, t):
        b = self.b
        seq = ["SUBA", "LN1", "PUMP", "HOSP"]
        pts = [b.xy(s) for s in seq]
        a = min(1.0, self.spotlight)
        for i in range(len(pts) - 1):
            p0, p1 = pts[i], pts[i + 1]
            dx, dy = p1[0] - p0[0], p1[1] - p0[1]
            L = math.hypot(dx, dy) or 1
            ux, uy = dx / L, dy / L
            off = (t * 90) % 34
            s = 0
            while s < L - 18:
                s0 = s + off
                if s0 > L - 14:
                    break
                q0 = (p0[0] + ux * s0, p0[1] + uy * s0)
                q1 = (p0[0] + ux * min(L, s0 + 16), p0[1] + uy * min(L, s0 + 16))
                cv.g.line([q0, q1], fill=scale(RED, 0.28 * a), width=10)
                cv.d.line([q0, q1], fill=scale(RED, 0.95 * a), width=3)
                s += 34
            # arrow head
            ang = math.atan2(dy, dx)
            px, py = p1[0] - ux * 30, p1[1] - uy * 30
            tri_ = [(px + 14 * math.cos(ang), py + 14 * math.sin(ang)),
                    (px + 10 * math.cos(ang + 2.5), py + 10 * math.sin(ang + 2.5)),
                    (px + 10 * math.cos(ang - 2.5), py + 10 * math.sin(ang - 2.5))]
            cv.d.polygon(tri_, fill=scale(RED, a))
        text(cv.d, (pts[1][0], pts[1][1] - 70), "PREDICTED CASCADE PATH", FUI(13),
             scale(RED, a), anchor="ma", tracking=2.0, glow_draw=cv.g, glow_a=0.4 * a)

    def _gate(self, cv, t):
        if t >= T_SELF:
            return
        d, g = cv.d, cv.g
        y0, y1 = FIELD0[1] - 30, FIELD0[3] + 30
        sweep = (t * 0.35) % 1.0
        for i in range(int((y1 - y0) // 26)):
            yy = y0 + i * 26
            glow_a = 0.25 + 0.35 * max(0.0, 1 - abs(((yy - y0) / (y1 - y0)) - sweep) * 6)
            pts = hexpts(GATE_X, yy + 13, 11, math.pi / 6)
            cv.d.polygon(pts, outline=scale(CYAN, 0.28))
            cv.g.polygon(pts, outline=scale(CYAN, 0.10 * glow_a))
        g.line([(GATE_X, y0), (GATE_X, y1)], fill=scale(CYAN, 0.10), width=10)
        d.line([(GATE_X, y0), (GATE_X, y1)], fill=scale(CYAN, 0.42), width=1)
        d.rounded_rectangle([GATE_X - 56, 88, GATE_X + 56, 132], radius=6,
                            fill=(5, 9, 16, 235), outline=scale(CYAN, 0.30) + (255,))
        text(d, (GATE_X, 96), "ATTACK", FUI(11), scale(CYAN, 0.85), anchor="ma", tracking=1.6)
        text(d, (GATE_X, 112), "VALIDATOR", FUI(11), scale(CYAN, 0.85), anchor="ma", tracking=1.6)

    def _proof_field(self, cv, t):
        # hardened state: shields + re-attack
        b = self.b
        d, g = cv.d, cv.g
        text(d, (960, 168), "RE-ATTACK TEST · SAME CHAIN · HARDENED TWIN", FDISP(22),
             WHITE, anchor="ma", tracking=3, glow_draw=g, glow_a=0.4)
        for nid in ("HOSP", "PUMP", "RAIL", "CITY", "SUBA"):
            n = b.nodes[nid]
            if n.shielded < 1:
                n.shielded = 1.0

    # -------------------------------------------------- top bar
    def _topbar(self, cv, t):
        d, g = cv.d, cv.g
        d.rectangle([0, 0, W, 80], fill=(6, 10, 18, 235))
        d.line([(0, 80), (W, 80)], fill=LINE_MID + (220,), width=2)
        g.line([(0, 80), (W, 80)], fill=scale(CYAN, 0.10), width=6)
        # logo
        pts = hexpts(56, 40, 23, math.pi / 6)
        neon_poly(cv, pts, CYAN, w=2, glow=16, ga=0.7, fill=scale((0, 40, 60), 0.8))
        text(d, (56, 40), "N", FDISP(22), CYAN, anchor="mm", glow_draw=g, glow_a=0.5)
        text(d, (92, 17), "NEXUS", FDISP(26), WHITE, tracking=6, glow_draw=g, glow_a=0.4)
        text(d, (94, 49), "DIGITAL-TWIN WARGAMING ENGINE", FMONO(11), scale(CYAN, 0.7), tracking=1.0)
        # phase chips
        cur = None
        x = 470
        for i, (st, name, cap) in enumerate(PHASES):
            nxt = PHASES[i + 1][0] if i + 1 < len(PHASES) else T_TOTAL
            act = st <= t < nxt
            if act:
                cur = cap
            col = CYAN if act else GREY_D
            wch = chip(cv, (x, 26), name, col, size=13, pad=10, active=1.0 if act else 0.45)
            if act:
                d.rounded_rectangle([x, 26, x + wch, 41], radius=4, outline=scale(col, 0.9))
                g.rounded_rectangle([x, 26, x + wch, 41], radius=4, outline=scale(col, 0.18))
            x += wch + 10
        # right: battle + clock
        bt = "001" if t < T_SELF else f"{min(120, self.battle_no):03d}"
        text(d, (W - 300, 13), "BATTLE", FUI(12), scale(GREY, 0.8), tracking=2.4)
        text(d, (W - 300, 28), bt, FNUM(28), AMBER, glow_draw=g, glow_a=0.4)
        text(d, (W - 180, 13), "T+", FUI(12), scale(GREY, 0.8), tracking=2.4)
        text(d, (W - 180, 28), f"{int(t)//60:02d}:{int(t)%60:02d}", FNUM(28), WHITE)
        # progress bar
        d.rectangle([470, 60, W - 40, 64], fill=LINE_DIM + (200,))
        d.rectangle([470, 60, 470 + (W - 510) * (t / T_TOTAL), 64], fill=scale(CYAN, 0.85))
        g.rectangle([470, 59, 470 + (W - 510) * (t / T_TOTAL), 65], fill=scale(CYAN, 0.18))

    # -------------------------------------------------- bottom bar
    def _bottombar(self, cv, t):
        d, g = cv.d, cv.g
        y0 = 948
        box = [LP[2] + 16, y0, RP[0] - 16, 1022]
        panel(cv, box, accent=AMBER, glow=0.5)
        b = self.b
        vals = [
            ("BLAST RADIUS", f"{b.blast*100:4.1f}", "%", b.blast, AMBER),
            ("CRITICAL ASSETS", f"{b.crit_assets:d}", " / 4", b.crit_assets / 4.0, RED),
            ("CASCADE PROB", f"{b.cascade_p*100:4.1f}", "%", b.cascade_p, ORANGE),
            ("RISK SCORE", f"{b.risk:4.1f}", " / 10", b.risk / 10.0, RED),
        ]
        x = box[0] + 22
        for i, (lab, val, unit, frac, col) in enumerate(vals):
            text(d, (x, y0 + 10), lab, FUI(12), scale(col, 0.7), tracking=2.0)
            text(d, (x, y0 + 22), val, FNUM(30), col, glow_draw=g, glow_a=0.4)
            vw = d.textlength(val, font=FNUM(30))
            text(d, (x + vw + 6, y0 + 38), unit, FMONO(12), scale(col, 0.55))
            bar(cv, [x, y0 + 58, x + 200, y0 + 66], frac, col, segs=16)
            x += 258
        # latest event
        if b.log:
            lt, msg, kind = b.log[-1]
            col = {"bad": RED, "good": GREEN, "warn": AMBER, "red": RED, "blue": CYAN}.get(kind, GREY)
            age = t - lt
            a = max(0.0, 1 - age * 0.25)
            x2 = box[2] - 24
            text(d, (box[2] - 24, y0 + 10), "LATEST EVENT", FUI(11), scale(GREY, 0.6), anchor="ra", tracking=2)
            text(d, (box[2] - 24, y0 + 30), msg[:58], FMONO(15), scale(col, 0.4 + 0.6 * a),
                 anchor="ra", glow_draw=g if age < 0.7 else None, glow_a=0.3)

    # -------------------------------------------------- left panel: ULTRON
    def _panel_ultron(self, cv, t):
        d, g = cv.d, cv.g
        x0, y0, x1, y1 = LP
        a = appear(t, T_TITLE + 0.2, 0.8)
        if a <= 0:
            return
        ox = int(-40 * (1 - a))
        # team plate
        team_plate(cv, [x0 + ox, y0, x1 + ox, y0 + 84], "ULTRON", "RED AI SWARM · ATTACKER",
                   RED, score=self.red_wins + (1 if t > 90 and t < T_SELF else 0),
                   active=1.0, side="left", glyph="tri", t=t)
        # objective
        panel(cv, [x0 + ox, y0 + 92, x1 + ox, y0 + 168], title="OBJECTIVE", accent=RED, glow=0.6)
        text(d, (x0 + ox + 14, y0 + 118), "MAXIMIZE SIMULATED", FUI(16), WHITE, tracking=1.4)
        text(d, (x0 + ox + 14, y0 + 140), "INFRASTRUCTURE DISRUPTION", FUI(16), scale(RED, 0.95), tracking=1.4)
        # attack chain
        panel(cv, [x0 + ox, y0 + 176, x1 + ox, y0 + 620], title="GENERATED ATTACK CHAIN",
              accent=RED, glow=0.6, tag="LLM STRATEGIST")
        cy = y0 + 210
        for c in CHAIN:
            st = self.chain_state[c["n"]]
            if st == "hidden":
                continue
            self._chain_card(cv, [x0 + ox + 12, cy, x1 + ox - 12, cy + 62], c, t, st)
            cy += 70
        # swarm / threat
        panel(cv, [x0 + ox, y0 + 628, x1 + ox, y0 + 762], title="RED SWARM", accent=RED, glow=0.5)
        for i in range(3):
            px = x0 + ox + 34 + i * 44
            py = y0 + 692
            neon_poly(cv, tri(px, py, 12, t * 1.6 + i), RED, w=2, glow=14, ga=0.8, fill=scale(RED_DEEP, 0.7))
            text(d, (px, py + 20), f"U-{i+1:02d}", FMONO(10), scale(RED, 0.6), anchor="ma")
        text(d, (x0 + ox + 172, y0 + 664), "THREAT LEVEL", FUI(11), scale(GREY, 0.8), tracking=1.8)
        bar(cv, [x0 + ox + 172, y0 + 682, x1 + ox - 16, y0 + 700],
            min(1.0, self.b.blast * 1.15), RED, segs=18)
        text(d, (x0 + ox + 172, y0 + 712), f"ACTIONS EXEC {sum(1 for k,v in self.chain_state.items() if v=='done')}/5",
             FMONO(11), scale(RED, 0.65))
        # event stream
        log_panel(cv, [x0 + ox, y0 + 770, x1 + ox, y1], self.b.log, t,
                  title="EVENT STREAM", accent=RED, maxrows=15, tref=t)

    def _chain_card(self, cv, box, c, t, st):
        x0, y0, x1, y1 = box
        d, g = cv.d, cv.g
        colmap = dict(gen=CYAN, flight=AMBER, done=GREEN, reject=RED, queued=GREY_D)
        col = colmap.get(st, GREY)
        a = appear(t, c["t"] - 2.4, 0.4)
        fillc = mix(PANEL2, col, 0.07)
        d.rounded_rectangle([x0, y0, x1, y1], radius=6, fill=fillc + (int(240 * a),),
                            outline=scale(col, 0.35 + 0.3 * (st in ("flight",))) + (255,), width=1)
        g.rounded_rectangle([x0, y0, x1, y1], radius=6, outline=scale(col, 0.07 * a))
        # index
        d.rounded_rectangle([x0 + 8, y0 + 10, x0 + 34, y0 + 36], radius=4, fill=scale(col, 0.18) + (255,))
        text(d, (x0 + 21, y0 + 23), f"{c['n']:02d}", FNUM(18), scale(col, 0.95), anchor="mm")
        text(d, (x0 + 44, y0 + 10), c["name"], FUI(15), scale(WHITE, 0.95 * a), tracking=1.2,
             glow_draw=g, glow_a=0.25 * a)
        text(d, (x0 + 44, y0 + 30), f"→ {c['tl']}", FMONO(11), scale(col, 0.7 * a))
        # status chip
        st_txt = dict(gen="PLANNING", flight="IN FLIGHT", done="EXECUTED", reject="REJECTED",
                      queued="QUEUED")[st]
        chip(cv, (x1 - 88, y0 + 12), st_txt, col, size=11, pad=7, active=a)
        # progress
        if st == "flight":
            k = clamp01((t - c["t"]) / c["dur"])
            bar(cv, [x0 + 44, y1 - 12, x1 - 14, y1 - 6], k, AMBER, segs=24)
        elif st == "done":
            bar(cv, [x0 + 44, y1 - 12, x1 - 14, y1 - 6], 1.0, GREEN, segs=24)
        elif st == "reject":
            bar(cv, [x0 + 44, y1 - 12, x1 - 14, y1 - 6], 1.0, RED, segs=24)
            text(d, (x0 + 44, y1 - 26), c["note"], FMONO(10), scale(RED, 0.7))
        else:
            sweep = (t * 1.6) % 1.0
            px = x0 + 44 + (x1 - 58) * sweep
            d.rectangle([x0 + 44, y1 - 12, x1 - 14, y1 - 6], fill=LINE_DIM + (200,))
            d.rectangle([px, y1 - 12, min(x1 - 14, px + 40), y1 - 6], fill=scale(CYAN, 0.7))
            text(d, (x0 + 44, y1 - 26), c["note"], FMONO(10), scale(GREY, 0.6))

    # -------------------------------------------------- right panel: PROTON
    def _panel_proton(self, cv, t):
        d, g = cv.d, cv.g
        x0, y0, x1, y1 = RP
        a = appear(t, T_TITLE + 0.35, 0.8)
        if a <= 0:
            return
        ox = int(40 * (1 - a))
        team_plate(cv, [x0 + ox, y0, x1 + ox, y0 + 84], "PROTON", "BLUE AI + HUMAN · DEFENDER",
                   CYAN, score=self.blue_wins + (0 if t < 96 else 1), active=1.0, side="right",
                   glyph="hex", t=t)
        # detection
        panel(cv, [x0 + ox, y0 + 92, x1 + ox, y0 + 236], title="DETECTION", accent=CYAN, glow=0.6)
        if self.detection is None:
            status, col = "MONITORING", GREY
            if t > 26:
                status, col = "ANOMALY — ANALYZING", AMBER
        else:
            status, col = "THREAT DETECTED", RED
        text(d, (x0 + ox + 14, y0 + 118), status, FUI(17), col, tracking=1.4, glow_draw=g, glow_a=0.4)
        det = max(0.0, (t - 26.0)) if self.detection is None else self.detection
        text(d, (x0 + ox + 14, y0 + 150), "DETECTION LATENCY", FUI(11), scale(GREY, 0.8), tracking=1.8)
        text(d, (x0 + ox + 14, y0 + 166), f"{det:05.1f}s", FNUM(34),
             AMBER if self.detection is None else CYAN, glow_draw=g, glow_a=0.4)
        conf = 0.35 + 0.6 * clamp01((self.detection or 0) / 42.0) if self.detection else (
            0.2 + 0.3 * clamp01((t - 26) / 34))
        text(d, (x1 + ox - 14, y0 + 150), "CONFIDENCE", FUI(11), scale(GREY, 0.8), anchor="ra", tracking=1.8)
        bar(cv, [x1 + ox - 160, y0 + 174, x1 + ox - 14, y0 + 186], conf, CYAN, segs=14)
        text(d, (x1 + ox - 14, y0 + 196), f"{conf*100:.0f}%", FMONO(11), scale(CYAN, 0.7), anchor="ra")
        text(d, (x0 + ox + 14, y0 + 208),
             "SENSOR MANIPULATION + CONTROL DISRUPTION" if self.detection else "NO SIGNATURE MATCH",
             FMONO(11), scale(col, 0.65))
        # response options
        if self.opt_shown > 0:
            panel(cv, [x0 + ox, y0 + 244, x1 + ox, y0 + 620], title="RESPONSE OPTIONS",
                  accent=GREEN, glow=0.6, tag="RANKED BY NEXUS")
            cy = y0 + 276
            for i, o in enumerate(OPTIONS):
                aa = appear(t, 70.5 + i * 0.45, 0.5)
                self._option_card(cv, [x0 + ox + 12, cy, x1 + ox - 12, cy + 108], o, t, i, aa)
                cy += 118
        else:
            panel(cv, [x0 + ox, y0 + 244, x1 + ox, y0 + 620], title="RESPONSE OPTIONS",
                  accent=GREEN, glow=0.3)
            text(d, (x0 + ox + 180, y0 + 420), "AWAITING", FUI(18), scale(GREY_D, 0.9), anchor="ma", tracking=3)
            text(d, (x0 + ox + 180, y0 + 446), "DETECTION", FUI(18), scale(GREY_D, 0.9), anchor="ma", tracking=3)
        # human in the loop
        panel(cv, [x0 + ox, y0 + 628, x1 + ox, y1], title="HUMAN-IN-THE-LOOP", accent=AMBER, glow=0.5)
        if self.selected:
            text(d, (x0 + ox + 14, y0 + 656), "OPERATOR DECISION", FUI(11), scale(GREY, 0.8), tracking=1.8)
            text(d, (x0 + ox + 14, y0 + 676), "OPTION A · ISOLATE SUB-A", FUI(17), GREEN, tracking=1.2,
                 glow_draw=g, glow_a=0.35)
            text(d, (x0 + ox + 14, y0 + 704), "EXPLANATION", FUI(11), scale(GREY, 0.8), tracking=1.8)
            for i, ln in enumerate(["cuts attacker foothold at SUB-A,",
                                    "sheds 44% district-7 load, closes",
                                    "SUB-B ↔ LINE-1 tie to re-feed",
                                    "pump station + hospital."]):
                text(d, (x0 + ox + 14, y0 + 722 + i * 16), ln, FMONO(11), scale(GREEN, 0.8))
            yb = y0 + 796
            text(d, (x0 + ox + 14, yb), "CONTAINMENT", FUI(11), scale(GREY, 0.8), tracking=1.8)
            bar(cv, [x0 + ox + 120, yb + 2, x1 + ox - 16, yb + 14],
                appear(t, 79.4, 1.4), CYAN, segs=14)
            for i, (lab, ok) in enumerate([("SUB-A ISOLATED", t > 79.4), ("TIE CLOSED", t > 81.2),
                                           ("LOAD SHED 44%", t > 83.0), ("CRITICALS RE-FED", t > 84.0)]):
                yy = y0 + 830 + i * 26
                col = GREEN if ok else GREY_D
                neon_circle(cv, (x0 + ox + 26, yy + 8), 8, col, w=2, glow=10, ga=0.6,
                            fill=scale(col, 0.15) if ok else None)
                if ok:
                    d.line([(x0 + ox + 22, yy + 8), (x0 + ox + 26, yy + 12), (x0 + ox + 32, yy + 2)],
                           fill=WHITE, width=2)
                text(d, (x0 + ox + 44, yy), lab, FUI(14), scale(col, 0.9 if ok else 0.6), tracking=1.0)
        else:
            text(d, (x0 + ox + 14, y0 + 656), "OPERATOR", FUI(11), scale(GREY, 0.8), tracking=1.8)
            text(d, (x0 + ox + 14, y0 + 676), "STANDING BY", FUI(17), scale(AMBER, 0.9), tracking=1.2)
            # cursor animation
            if self.cursor[0] > 0:
                cx = x0 + ox + 60 + 120 * ease(min(1.0, self.cursor[1] / 1.6))
                cy = y0 + 276 + 60 + 118 * ease(clamp01((self.cursor[1] - 1.6) / 1.4))
                pts = [(cx, cy), (cx, cy + 22), (cx + 6, cy + 17), (cx + 11, cy + 26),
                       (cx + 14, cy + 24), (cx + 10, cy + 15), (cx + 17, cy + 14)]
                d.polygon(pts, fill=WHITE)
                g.polygon(pts, fill=scale(WHITE, 0.3))
                neon_circle(cv, (cx, cy), 18 + 8 * pulse(t, 2.0), scale(WHITE, 0.35), w=1, glow=8, ga=0.5)

    def _option_card(self, cv, box, o, t, i, a):
        x0, y0, x1, y1 = box
        d, g = cv.d, cv.g
        sel = (self.selected == o["k"])
        hov = (not self.selected) and self.cursor[0] > 0 and (
            self.cursor[1] > 1.6 and i == int(clamp01((self.cursor[1] - 1.6) / 1.4) * 2.999) % 3)
        col = o["col"]
        bd = scale(col, 0.9 if sel else (0.6 if hov else 0.3))
        d.rounded_rectangle([x0, y0, x1, y1], radius=6,
                            fill=mix(PANEL2, col, 0.05 + (0.12 if sel else 0)) + (int(240 * a),),
                            outline=bd + (255,), width=2 if sel else 1)
        g.rounded_rectangle([x0, y0, x1, y1], radius=6, outline=scale(col, (0.22 if sel else 0.06) * a))
        if sel:
            danger_stripes(cv, [x0, y0, x1, y0 + 4], col=col, a=0.5, w=12)
        d.rounded_rectangle([x0 + 10, y0 + 12, x0 + 38, y0 + 40], radius=4, fill=scale(col, 0.18) + (255,))
        text(d, (x0 + 24, y0 + 26), o["k"], FDISP(18), scale(col, 0.95), anchor="mm")
        text(d, (x0 + 50, y0 + 11), o["name"], FUI(16), scale(WHITE, 0.95 * a), tracking=1.1,
             glow_draw=g, glow_a=0.25 * a)
        text(d, (x0 + 50, y0 + 31), o["detail"], FMONO(10), scale(col, 0.62 * a))
        # cascade before/after
        text(d, (x0 + 14, y0 + 52), "CASCADE PROBABILITY", FUI(10), scale(GREY, 0.7), tracking=1.4)
        bx0 = x0 + 14
        bw = (x1 - x0 - 40)
        d.rectangle([bx0, y0 + 72, bx0 + bw * 0.87, y0 + 84], fill=scale(RED, 0.75))
        d.rectangle([bx0, y0 + 86, bx0 + bw * (o["after"] / 100.0), y0 + 98], fill=scale(col, 0.9))
        g.rectangle([bx0, y0 + 86, bx0 + bw * (o["after"] / 100.0), y0 + 98], fill=scale(col, 0.18))
        text(d, (x1 - 14, y0 + 68), "87%", FNUM(16), scale(RED, 0.9), anchor="ra")
        text(d, (x1 - 14, y0 + 84), f"{o['after']}%", FNUM(16), col, anchor="ra",
             glow_draw=g, glow_a=0.4)
        if sel:
            text(d, (x1 - 14, y0 + 12), "● SELECTED", FUI(12), GREEN, anchor="ra", tracking=1.6,
                 glow_draw=g, glow_a=0.4)

    # -------------------------------------------------- self-play panels
    def _panel_selfplay_left(self, cv, t):
        d, g = cv.d, cv.g
        x0, y0, x1, y1 = LP
        panel(cv, [x0, y0, x1, y0 + 150], title="SELF-PLAY ENGINE", accent=PURPLE, glow=0.6)
        text(d, (x0 + 14, y0 + 44), "BATTLES", FUI(11), scale(GREY, 0.8), tracking=1.8)
        text(d, (x0 + 14, y0 + 58), f"{min(120, self.battle_no):03d}", FNUM(46), AMBER,
             glow_draw=g, glow_a=0.45)
        text(d, (x0 + 150, y0 + 58), "/ 120", FNUM(22), scale(GREY, 0.8))
        bar(cv, [x0 + 14, y0 + 110, x1 - 14, y0 + 122], min(1.0, self.battle_no / 120.0), AMBER, segs=24)
        text(d, (x0 + 14, y0 + 128), "PARALLEL ARENAS: 4", FMONO(11), scale(AMBER, 0.6))
        # win rate
        panel(cv, [x0, y0 + 158, x1, y0 + 340], title="OUTCOME SPLIT", accent=PURPLE, glow=0.5)
        tot = max(1, self.red_wins + self.blue_wins)
        text(d, (x0 + 14, y0 + 194), "ULTRON (RED)", FUI(14), RED, tracking=1.2)
        text(d, (x1 - 14, y0 + 190), f"{self.red_wins/tot*100:.0f}%", FNUM(24), RED, anchor="ra")
        bar(cv, [x0 + 14, y0 + 216, x1 - 14, y0 + 232], self.red_wins / tot, RED, segs=20)
        text(d, (x0 + 14, y0 + 256), "PROTON (BLUE)", FUI(14), CYAN, tracking=1.2)
        text(d, (x1 - 14, y0 + 252), f"{self.blue_wins/tot*100:.0f}%", FNUM(24), CYAN, anchor="ra")
        bar(cv, [x0 + 14, y0 + 278, x1 - 14, y0 + 294], self.blue_wins / tot, CYAN, segs=20)
        text(d, (x0 + 14, y0 + 306), "ENGINE RATING", FUI(11), scale(GREY, 0.8), tracking=1.8)
        u = min(1.0, self.battle_no / 120.0)
        text(d, (x1 - 14, y0 + 300), f"{1180 + int(286*u)}", FNUM(24), GREEN, anchor="ra",
             glow_draw=g, glow_a=0.4)
        # event stream
        log_panel(cv, [x0, y0 + 348, x1, y1], self.b.log, t, title="BATTLE LOG",
                  accent=PURPLE, maxrows=38, tref=t, row_h=17)

    def _panel_selfplay_right(self, cv, t):
        d, g = cv.d, cv.g
        x0, y0, x1, y1 = RP
        s = self.series
        chart(cv, [x0, y0, x1, y0 + 250], s["det"], "DETECTION TIME", accent=CYAN,
              ymax=48, ymin=0, xlabel="BATTLES →", ylabel="SEC",
              cur=f"{s['det'][-1]:.1f}s" if s["det"] else "—", target=9)
        chart(cv, [x0, y0 + 258, x1, y0 + 508], s["sev"], "CASCADE SEVERITY", accent=ORANGE,
              ymax=9, ymin=0, xlabel="BATTLES →", ylabel="SEV",
              cur=f"{s['sev'][-1]:.1f}" if s["sev"] else "—", target=2.1, label_fmt="{:.1f}")
        chart(cv, [x0, y0 + 516, x1, y1], s["dfn"], "DEFENSE SUCCESS", accent=GREEN,
              ymax=100, ymin=0, xlabel="BATTLES →", ylabel="%",
              cur=f"{s['dfn'][-1]:.0f}%" if s["dfn"] else "—", target=81)

    def _minis(self, cv, t):
        d, g = cv.d, cv.g
        text(d, (960, 118), "SELF-PLAY · FOUR PARALLEL ARENAS", FDISP(24), WHITE, anchor="ma",
             tracking=4, glow_draw=g, glow_a=0.4)
        for i, m in enumerate(self.minis):
            bx = m["box"]
            b = m["b"]
            a = appear(t, T_SELF + 0.1 + i * 0.12, 0.6)
            d.rounded_rectangle([bx[0] - 8, bx[1] - 8, bx[2] + 8, bx[3] + 8], radius=10,
                                fill=(8, 13, 22, int(230 * a)), outline=LINE_MID + (int(200 * a),), width=1)
            b.draw_edges(cv, t, show_flow=True)
            b.draw_nodes(cv, t, labels=not True)
            b.draw_fx(cv)
            for nid in ("HOSP", "PUMP", "RAIL"):
                n = b.nodes[nid]
                text(d, (n.xy[0], n.xy[1] - 26), nid, FUI(11), scale(AMBER, 0.85), anchor="ma")
            text(d, (bx[0] + 4, bx[1] - 26), f"ARENA {i+1:02d}", FMONO(12), scale(CYAN, 0.6))
            if m.get("no"):
                text(d, (bx[2] - 4, bx[1] - 26), f"BATTLE {m['no']:03d}", FMONO(12),
                     scale(AMBER, 0.7), anchor="ra")
            # result chip
            if m["res"] and t - m["res_t"] < 1.0:
                col = GREEN if m["res"] == "BLUE" else RED
                aa = 1 - (t - m["res_t"]) / 1.0
                lab = "PROTON HOLDS" if m["res"] == "BLUE" else "ULTRON BREACH"
                wch = d.textlength(lab, font=FUI(15)) + 24
                cx = (bx[0] + bx[2]) / 2
                d.rounded_rectangle([cx - wch / 2, bx[3] - 46, cx + wch / 2, bx[3] - 18], radius=5,
                                    fill=scale(col, 0.18 * aa) + (255,), outline=scale(col, aa) + (255,))
                text(d, (cx, bx[3] - 42), lab, FUI(15), scale(col, aa), anchor="ma", tracking=1.4,
                     glow_draw=g, glow_a=0.4 * aa)

    # -------------------------------------------------- proof panels
    def _panel_proof_left(self, cv, t):
        d, g = cv.d, cv.g
        x0, y0, x1, y1 = LP
        a = appear(t, T_PROOF, 0.7)
        items = [("DETECTION TIME", 42, 9.0, RED, GREEN, True),
                 ("CASCADE SEVERITY", 7.8, 2.1, RED, GREEN, True),
                 ("DEFENSE SUCCESS", 34, 81, RED, GREEN, False)]
        bars_compare(cv, [x0, y0, x1, y0 + 332], items, "BEFORE  /  AFTER  ·  120 BATTLES")
        text(d, (x0 + 14, y0 + 302), "SEC  ·  SEVERITY INDEX  ·  PERCENT", FMONO(11),
             scale(GREY, 0.6))
        panel(cv, [x0, y0 + 338, x1, y1], title="HARDENING PLAYBOOK", accent=GREEN, glow=0.6)
        rows = [("H1", "SUB-A sensor cross-validation", 0.2),
                ("H2", "Telemetry heartbeat watchdog", 1.1),
                ("H3", "Tie-line auto-close on feed loss", 2.6),
                ("H4", "Adaptive load-shed ladder", 3.9),
                ("H5", "Control-path allowlist (SCADA)", 5.4)]
        y = y0 + 376
        for k, lab, delay in rows:
            aa = appear(t, T_PROOF + 0.3 + delay * 0.25, 0.5)
            if aa <= 0:
                continue
            d.rounded_rectangle([x0 + 12, y, x1 - 12, y + 46], radius=5,
                                fill=mix(PANEL2, GREEN, 0.05) + (int(230 * aa),),
                                outline=scale(GREEN, 0.25 * aa) + (255,))
            text(d, (x0 + 24, y + 14), k, FNUM(18), scale(GREEN, aa))
            text(d, (x0 + 58, y + 8), lab, FUI(13), scale(WHITE, 0.9 * aa), tracking=0.8)
            text(d, (x0 + 58, y + 26), "APPLIED TO TWIN", FMONO(10), scale(GREEN, 0.6 * aa), tracking=1.2)
            y += 54

    def _panel_proof_right(self, cv, t):
        d, g = cv.d, cv.g
        x0, y0, x1, y1 = RP
        panel(cv, [x0, y0, x1, y0 + 420], title="DISCOVERED CASCADE PATHS", accent=AMBER, glow=0.6)
        paths = [("SUB-A → LINE-1 → PUMP → HOSPITAL", 9.1),
                 ("SUB-B → LINE-2 → RAIL → CITY", 8.4),
                 ("TELEMETRY → SCADA → SUB-A → LINE-1", 7.6),
                 ("SUB-A → LINE-2 → CITY → HOSPITAL", 6.9),
                 ("GEN-01 → SUB-B → LINE-2 → RAIL", 6.2)]
        y = y0 + 44
        for i, (p, sc) in enumerate(paths):
            aa = appear(t, T_PROOF + 0.2 + i * 0.35, 0.5)
            if aa <= 0:
                continue
            col = mix(AMBER, RED, (sc - 6) / 3.2)
            text(d, (x0 + 14, y), f"{i+1:02d}", FNUM(16), scale(col, aa))
            text(d, (x0 + 44, y + 2), p, FMONO(11), scale(WHITE, 0.85 * aa))
            bar(cv, [x0 + 44, y + 20, x1 - 60, y + 28], sc / 10.0, col, segs=10)
            text(d, (x1 - 14, y - 2), f"{sc:.1f}", FNUM(20), scale(col, aa), anchor="ra",
                 glow_draw=g, glow_a=0.35 * aa)
            y += 52
        panel(cv, [x0, y0 + 428, x1, y1], title="WHY NEXUS WINS", accent=CYAN, glow=0.5)
        lines = ["observes + attacks + learns",
                 "generates unseen attack chains",
                 "twin becomes a battlefield",
                 "risk ranked by simulated impact",
                 "continuous, not periodic"]
        y = y0 + 472
        for i, ln in enumerate(lines):
            aa = appear(t, T_PROOF + 1.2 + i * 0.3, 0.5)
            if aa <= 0:
                continue
            neon_poly(cv, tri(x0 + 26, y + 8, 7, math.pi / 2), scale(CYAN, aa), w=1, glow=8, ga=0.6)
            text(d, (x0 + 44, y), ln, FUI(14), scale(CYAN, 0.85 * aa), tracking=0.8)
            y += 30

    def _proof_field(self, cv, t):
        pass

    # -------------------------------------------------- overlays
    def _pops(self, cv, t):
        d, g = cv.d, cv.g
        for p in self.pops:
            k = (t - p["t0"]) / p["dur"]
            a = 1.0 - k ** 2.2
            if a <= 0:
                continue
            y = p["xy"][1] - p["rise"] * ease(k)
            f = FDISP(p["size"])
            text(d, (p["xy"][0], y), p["txt"], f, scale(p["col"], a), anchor="ma",
                 tracking=2.5, glow_draw=g, glow_a=0.55 * a)

    def _alarm_frame(self, cv, t):
        d, g = cv.d, cv.g
        a = 0.16 + 0.14 * math.sin(t * 6.0)
        k = int(6 + 10 * self.b.blast)
        for i in range(k):
            col = RED if i % 2 else ORANGE
            d.rectangle([0, i * 4, W, i * 4 + 2], fill=col + (int(255 * a),))
            d.rectangle([0, H - i * 4 - 2, W, H - i * 4], fill=col + (int(255 * a),))
            d.rectangle([i * 4, 0, i * 4 + 2, H], fill=col + (int(255 * a),))
            d.rectangle([W - i * 4 - 2, 0, W - i * 4, H], fill=col + (int(255 * a),))
        if self.b.blast > 0.45:
            txt = "CASCADE PROPAGATION"
            w = d.textlength(txt, font=FDISP(20)) + 40
            x = W / 2
            d.rectangle([x - w / 2, 96, x + w / 2, 128], fill=(60, 0, 10, int(230 * (0.6 + 0.4 * math.sin(t * 8)))))
            text(d, (x, 112), txt, FDISP(20), RED, anchor="mm", tracking=3, glow_draw=g, glow_a=0.5)

    def _caption(self, d, t):
        cur = PHASES[0][2]
        for st, name, cap in PHASES:
            if t >= st:
                cur = cap
        w = d.textlength(cur, font=FUI(16)) + 46
        x = W / 2
        d.rounded_rectangle([x - w / 2, 1028, x + w / 2, 1062], radius=6, fill=(6, 10, 18, 240),
                            outline=scale(CYAN, 0.35) + (255,))
        d.line([(x - w / 2, 1028), (x - w / 2, 1062)], fill=AMBER, width=3)
        d.text((x, 1045), cur, font=FUI(16), fill=scale(WHITE, 0.92), anchor="mm")

    # -------------------------------------------------- end card
    def _endcard(self, cv, t):
        d, g = cv.d, cv.g
        a = appear(t, T_END, 0.8)
        # backdrop grid faint
        for e in EDGES:
            sp = next(s for s in NODES if s["id"] == e["a"])
            sp2 = next(s for s in NODES if s["id"] == e["b"])
            p0 = (W / 2 + (sp["x"] - 0.5) * 1100, 540 + (sp["y"] - 0.5) * 700)
            p1 = (W / 2 + (sp2["x"] - 0.5) * 1100, 540 + (sp2["y"] - 0.5) * 700)
            cv.d.line([p0, p1], fill=(24, 52, 84, int(70 * a)), width=1)
        y = 300
        text(d, (W / 2, y), "NEXUS", FDISP(140), scale(WHITE, a), anchor="ma", tracking=12,
             glow_draw=g, glow_a=0.45 * a)
        for i, ln in enumerate(["ATTACK THE TWIN.", "PREDICT THE CASCADE.", "HARDEN THE SYSTEM."]):
            aa = appear(t, T_END + 0.8 + i * 0.7, 0.7)
            if aa <= 0:
                continue
            text(d, (W / 2, y + 190 + i * 56), ln, FDISP(38),
                 scale([CYAN, AMBER, GREEN][i], aa), anchor="ma", tracking=6,
                 glow_draw=g, glow_a=0.45 * aa)
        aa = appear(t, T_END + 3.2, 0.8)
        if aa:
            text(d, (W / 2, y + 400), "TEAM DECODE", FUI(26), scale(WHITE, aa), anchor="ma", tracking=8)
            text(d, (W / 2, y + 440), "A WORKING CLOSED LOOP BEATS A PERFECT ARCHITECTURE",
                 FMONO(14), scale(GREY, 0.85 * aa), anchor="ma", tracking=2)
