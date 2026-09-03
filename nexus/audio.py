"""Cinematic soundtrack for the NEXUS simulation film (pure numpy synthesis)."""
import sys
import numpy as np
from scipy.signal import butter, lfilter, sosfilt

SR = 44100
DUR = 180.0
N = int(DUR * SR)
rng = np.random.default_rng(9)

M = np.zeros(N, dtype=np.float64)


def env(n, attack=0.002, decay=0.25, curve=1.0):
    a = max(1, int(attack * SR))
    e = np.exp(-np.arange(n) / max(1e-6, decay * SR) / curve)
    e[:a] *= np.linspace(0, 1, a)
    return e


def add(sig, t, g=1.0):
    i = int(t * SR)
    if i >= N or g == 0:
        return
    if i < 0:
        sig = sig[-i:]
        i = 0
    n = min(len(sig), N - i)
    if n <= 0:
        return
    M[i:i + n] += sig[:n] * g


def noise(n, seed=0):
    return np.random.default_rng(seed).standard_normal(n)


def lp(x, f, q=0.707):
    sos = butter(2, min(0.98, f / (SR / 2)), btype="low", output="sos")
    return sosfilt(sos, x)


def hp(x, f):
    sos = butter(2, min(0.98, f / (SR / 2)), btype="high", output="sos")
    return sosfilt(sos, x)


def bp(x, f0, f1):
    sos = butter(2, [max(0.001, f0 / (SR / 2)), min(0.98, f1 / (SR / 2))], btype="band",
                 output="sos")
    return sosfilt(sos, x)


def tone(f, dur, amp=0.2, decay=0.3, attack=0.004, harm=0.0, detune=0.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    s = np.sin(2 * np.pi * f * t) + detune * np.sin(2 * np.pi * f * 1.005 * t)
    if harm:
        s += harm * np.sin(4 * np.pi * f * t) + harm * 0.5 * np.sin(6 * np.pi * f * t)
    return s * env(n, attack, decay) * amp


def sweep(f0, f1, dur, amp=0.2, decay=None, kind="exp"):
    n = int(dur * SR)
    t = np.linspace(0, 1, n)
    f = f0 * (f1 / f0) ** t if kind == "exp" else f0 + (f1 - f0) * t
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * env(n, 0.005, decay or dur / 3.0) * amp


# ---------------------------------------------------------------- effects
def impact(t, amp=0.55, f0=140, f1=38, dur=1.5, nseed=1, noise_amp=0.8, lp_f=1800):
    n = int(dur * SR)
    s = sweep(f0, f1, dur, amp * 0.9, decay=dur / 4.0)
    nz = lp(noise(n, nseed), lp_f)
    s += nz * env(n, 0.001, dur / 7.0) * amp * noise_amp
    add(s, t)


def zap(t, amp=0.32, dur=0.42, f=900):
    n = int(dur * SR)
    s = sweep(f * 2.6, f * 0.35, dur, amp, decay=dur / 5.0)
    s += bp(noise(n, int(t * 100) % 9999), 1800, 7000) * env(n, 0.001, dur / 8.0) * amp * 0.8
    add(s, t - 0.02)


def blip(t, f=1400, amp=0.16, dur=0.10):
    add(tone(f, dur, amp, decay=dur / 3.0), t)


def whoosh(t, dur=0.9, amp=0.22):
    n = int(dur * SR)
    x = noise(n, int(t * 77) % 9999)
    # band sweeps up then down
    idx = np.linspace(0, 1, n)
    sos_up = butter(2, [200 / (SR / 2), 6000 / (SR / 2)], btype="band", output="sos")
    s = sosfilt(sos_up, x)
    s *= np.sin(np.pi * idx) ** 0.7
    s = np.tanh(s * 3.0) * amp
    add(s, t)


def alarm(t, amp=0.22, n=2, f=880):
    for i in range(n):
        add(tone(f, 0.22, amp, decay=0.07, harm=0.25), t + i * 0.34)


def chime(t, notes=(523.25, 783.99, 1046.5), amp=0.14, dur=2.2):
    for i, f in enumerate(notes):
        add(tone(f, dur, amp * (1 - i * 0.16), decay=dur / 3.5, attack=0.01), t + i * 0.06)


def riser(t, dur=3.0, amp=0.20, f0=90, f1=1400):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    k = tt / dur
    s = np.sin(2 * np.pi * np.cumsum(f0 * (f1 / f0) ** k) / SR)
    s *= k ** 2
    nz = bp(noise(n, 7), 400, 6000) * k ** 2 * 0.5
    add((s + nz) * amp * env(n, 0.01, dur), t)


# ---------------------------------------------------------------- beds
def drone(t0, t1, f, amp=0.10, lfo=0.13, detune=0.5):
    n = int((t1 - t0) * SR)
    tt = np.arange(n) / SR
    s = np.sin(2 * np.pi * f * tt)
    s += detune * np.sin(2 * np.pi * f * 1.5 * tt + 0.6)
    s += 0.35 * np.sin(2 * np.pi * f * 2.0 * tt + 1.2)
    trem = 0.72 + 0.28 * np.sin(2 * np.pi * lfo * tt)
    s *= trem
    s *= np.minimum(1.0, np.minimum(tt / 2.0, (n / SR - tt) / 2.0))
    add(s, t0, amp)


def pulse_track(t0, t1, bpm, amp=0.30, f0=58):
    spb = 60.0 / bpm
    t = t0
    i = 0
    while t < t1:
        n = int(0.45 * SR)
        s = sweep(f0 * 1.9, f0, 0.45, 1.0, decay=0.10)
        s += lp(noise(n, i), 400) * env(n, 0.001, 0.03) * 0.35
        add(s, t, amp * (0.65 if i % 4 == 0 else 0.42))
        t += spb
        i += 1


def hat_track(t0, t1, bpm, amp=0.05):
    spb = 60.0 / bpm / 2
    t = t0
    i = 0
    while t < t1:
        n = int(0.06 * SR)
        s = hp(noise(n, 1000 + i), 6000) * env(n, 0.001, 0.012)
        add(s, t, amp * (0.6 if i % 2 else 1.0))
        t += spb
        i += 1


# ================================================================== score
print("beds…")
drone(0, 12, 41.2, 0.16, 0.10)
drone(11, 100, 41.2, 0.11, 0.16)
drone(11, 100, 61.74, 0.05, 0.11)
drone(100, 150, 55.0, 0.13, 0.28)
drone(150, 180, 49.0, 0.12, 0.08)
drone(170, 180, 73.4, 0.08, 0.05)

# title
impact(1.0, 0.62, 160, 34, 2.2, nseed=3)
chime(1.0, (261.6, 392.0, 523.25), 0.10, 2.6)
blip(2.6, 1760, 0.09)
blip(3.9, 2093, 0.08)
whoosh(5.5, 0.8, 0.18)
impact(5.95, 0.40, 220, 60, 1.1)
whoosh(5.85, 0.8, 0.18)
impact(6.3, 0.40, 180, 50, 1.1)
impact(7.3, 0.5, 300, 44, 1.4)
chime(7.35, (523.25, 659.25), 0.09, 1.8)
whoosh(10.6, 1.0, 0.26)
impact(11.0, 0.5, 200, 40, 1.6)

# healthy twin: soft ticks
for i in range(26):
    t = 11.5 + i * 0.5
    if t > 24.8:
        break
    blip(t, 1200 + (i % 3) * 180, 0.05, 0.075)
for i, t in enumerate((13.0, 15.5, 18.0, 20.5, 23.0)):
    add(tone(146.83, 1.4, 0.055, decay=0.45, attack=0.02), t)

# attack chain
for i, t in enumerate((26.0, 31.0, 36.0, 41.0)):
    zap(t, 0.28)
    blip(t - 2.2, 900, 0.06, 0.09)
zap(36.0, 0.30)
alarm(36.9, 0.20, 1, 320)          # rejected
blip(37.9, 660, 0.08, 0.14)        # revise
riser(42.0, 5.0, 0.16, 70, 900)
zap(47.0, 0.34)
impact(47.9, 0.85, 180, 32, 2.6, nseed=11, lp_f=2600)   # breaker trip
whoosh(47.9, 1.4, 0.24)

# cascade
impact(49.5, 0.45, 150, 40, 1.4)
impact(52.4, 0.52, 130, 36, 1.8)
alarm(51.0, 0.17, 2, 740)
blip(54.2, 520, 0.12, 0.18)
alarm(56.0, 0.20, 3, 660)
drone(48.4, 78.0, 32.7, 0.16, 0.22)
pulse_track(48.4, 68.0, 92, 0.26, 52)
riser(60.0, 8.0, 0.20, 60, 700)

# detection + defence
alarm(68.0, 0.30, 2, 990)
chime(68.0, (659.25, 987.77), 0.10, 1.6)
whoosh(68.0, 1.2, 0.20)
for i in range(3):
    blip(70.5 + i * 0.45, 1200 + i * 220, 0.09, 0.12)
blip(77.6, 1568, 0.14, 0.2)
impact(79.4, 0.55, 240, 70, 1.6, nseed=21, lp_f=3000)
whoosh(79.4, 1.0, 0.22)
zap(81.2, 0.22)
sweep_out = sweep(220, 880, 1.2, 0.14, decay=0.5)
add(sweep_out, 81.2)
chime(83.0, (523.25, 659.25, 783.99, 1046.5), 0.13, 2.6)
impact(86.0, 0.35, 120, 60, 1.2)
chime(90.0, (392.0, 587.33, 784.0), 0.11, 2.4)
drone(88.0, 100.0, 65.41, 0.10, 0.07)
drone(88.0, 100.0, 98.0, 0.055, 0.05)
for i, t in enumerate((90.6, 93.0, 95.4, 97.8)):
    blip(t, 1320 + i * 180, 0.055, 0.14)
    add(tone(196.0, 1.6, 0.05, decay=0.5, attack=0.02), t)

# self-play
impact(100.0, 0.5, 160, 44, 1.6)
sweep_ = sweep(40, 120, 1.4, 0.16, decay=0.6)
add(sweep_, 100.0)
pulse_track(100.0, 150.0, 138, 0.30, 62)
hat_track(100.5, 150.0, 138, 0.045)
for i in range(50):
    t = 100.5 + i * 0.98
    blip(t, 1800 if i % 4 == 0 else 2400, 0.03, 0.04)
riser(140.0, 9.0, 0.18, 80, 1200)

# proof
impact(150.0, 0.55, 170, 40, 2.0)
chime(150.2, (392.0, 523.25, 659.25), 0.12, 2.6)
for i, t in enumerate((152.0, 154.6, 157.2)):
    zap(t, 0.26)
    impact(t + 1.2, 0.34, 300, 90, 0.9, nseed=30 + i, lp_f=4000)
    blip(t + 1.2, 2093, 0.07, 0.12)
chime(160.5, (523.25, 783.99, 1046.5, 1318.5), 0.15, 3.2)
impact(160.5, 0.45, 120, 45, 2.2)

# end card
whoosh(171.4, 1.2, 0.24)
impact(172.0, 0.65, 150, 30, 3.0)
chime(172.2, (261.63, 329.63, 392.0, 523.25), 0.16, 4.0)
chime(176.0, (392.0, 523.25, 659.25, 783.99, 1046.5), 0.13, 4.5)

# ---------------------------------------------------------------- master
print("mastering…")
peak = np.max(np.abs(M))
M *= 0.92 / max(1e-6, peak)
M = np.tanh(M * 1.25) * 0.85
# stereo haas width
d = int(0.011 * SR)
L = M.copy()
R = np.concatenate([np.zeros(d), M[:-d]]) * 0.86 + M * 0.14
st = np.stack([L, R], axis=1)
st = np.clip(st, -1, 1)
wav = (st * 32767).astype(np.int16)
wav.tofile("/tmp/nexus_audio.raw")

import wave
with wave.open("/home/user/nexus/nexus_score.wav", "wb") as f:
    f.setnchannels(2)
    f.setsampwidth(2)
    f.setframerate(SR)
    f.writeframes(wav.tobytes())
print("audio written: nexus_score.wav", wav.shape, f"{wav.nbytes/1e6:.1f} MB")
