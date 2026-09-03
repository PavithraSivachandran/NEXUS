import sys, time
sys.path.insert(0, "/home/user/nexus")
from scenes import Renderer, FPS
import scenes

times = [float(x) for x in sys.argv[1:]] or [3, 8, 14, 29, 37, 50, 62, 70, 76, 84, 110, 160, 175]
r = Renderer()
dt = 1 / 30.0
t = 0.0
for tt in times:
    target = int(tt * 30)
    while int(round(t * 30)) < target:
        t += dt
        r.update(t, dt)
    st = time.time()
    img = r.render(t)
    img.save(f"/home/user/preview/f{target:05d}.png")
    print(f"t={t:6.2f} -> preview/f{target:05d}.png  ({time.time()-st:.2f}s)")
