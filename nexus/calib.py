import sys
sys.path.insert(0, "/home/user/nexus")
import scenes
from scenes import Renderer

r = Renderer()
dt = 1 / 30.0
marks = [20, 30, 36, 42, 48, 49, 50, 52, 54, 58, 62, 66, 68, 72, 78, 80, 82, 84, 86, 90, 96]
mi = 0
t = 0.0
n = int(180 / dt)
rows = []
for i in range(n):
    t = i * dt
    r.update(t, dt)
    while mi < len(marks) and t >= marks[mi]:
        b = r.b
        st = {k: v.state for k, v in b.nodes.items()}
        rows.append((marks[mi], b.blast, b.crit_assets, b.cascade_p, b.risk,
                     {e.id: round(e.load, 2) for e in b.edges if e.kind == 'power'},
                     {k: v.state for k, v in b.nodes.items() if v.state}))
        mi += 1
print(f"{'t':>6} {'blast':>6} {'crit':>4} {'casc':>6} {'risk':>5}")
for t_, bl, cr, cp, rk, loads, sts in rows:
    print(f"{t_:6.1f} {bl*100:6.1f} {cr:4d} {cp*100:6.1f} {rk:5.1f}   {sts}")
print()
for t_, bl, cr, cp, rk, loads, sts in rows:
    print(f"{t_:6.1f} loads={loads}")
