"""headless QA: text-overflow, exposure, region coverage per frame."""
import sys
sys.path.insert(0, "/home/user/nexus")
import numpy as np
from PIL import Image, ImageDraw

import fx
from theme import FUI, FMONO, FNUM, FDISP, FDISPR
from scenes import Renderer

LP_END, RP_START = 392, 1528
_boxes = []
_orig_text = ImageDraw.ImageDraw.text


def _patched(self, xy, *a, **kw):
    s = a[0] if a else kw.get("text", "")
    font = kw.get("font", a[1] if len(a) > 1 else None)
    anchor = kw.get("anchor")
    try:
        bb = self.textbbox(xy, s, font=font, anchor=anchor)
        _boxes.append((bb, str(s)[:38]))
    except Exception:
        pass
    return _orig_text(self, xy, *a, **kw)


ImageDraw.ImageDraw.text = _patched


def stats(img):
    a = np.asarray(img).astype(np.float32) / 255.0
    lum = a.mean(axis=2)
    over = float((lum > 0.97).mean())
    dark = float((lum < 0.02).mean())
    regions = {
        "top": lum[0:88, :].mean(),
        "left": lum[100:1058, 24:384].mean(),
        "center": lum[100:960, LP_END:RP_START].mean(),
        "right": lum[100:1058, RP_START:1896].mean(),
        "bottom": lum[960:1060, LP_END:RP_START].mean(),
    }
    return lum.mean(), over, dark, regions


def run(times):
    r = Renderer()
    dt = 1 / 30.0
    t = 0.0
    for tt in times:
        while t < tt - 1e-9:
            t += dt
            r.update(t, dt)
        _boxes.clear()
        img = r.render(t)
        mean, over, dark, reg = stats(img)
        bad = []
        for (x0, y0, x1, y1), s in _boxes:
            if x0 < -2 or x1 > 1922 or y0 < -2 or y1 > 1082:
                bad.append(f"OFFCANVAS {s!r} {(x0,y0,x1,y1)}")
            elif x0 < LP_END and x1 > LP_END + 4:
                bad.append(f"CROSS-L {s!r} {(x0,y0,x1,y1)}")
            elif x0 >= RP_START - 4 and x1 > 1900:
                bad.append(f"CROSS-R {s!r} {(x0,y0,x1,y1)}")
            elif LP_END <= x0 < RP_START and (x1 > RP_START + 4 or x0 < LP_END - 4):
                bad.append(f"CROSS-C {s!r} {(x0,y0,x1,y1)}")
        print(f"t={t:6.2f} mean={mean:.3f} over={over*100:5.2f}% dark={dark*100:5.1f}% "
              f"| " + "  ".join(f"{k}={v:.3f}" for k, v in reg.items()))
        for b in bad[:14]:
            print("   !", b)
        if len(bad) > 14:
            print(f"   ... +{len(bad)-14} more")


if __name__ == "__main__":
    args = [float(x) for x in sys.argv[1:]] or [14, 30, 44, 50, 62, 70, 76, 84, 95, 110, 140, 160, 176]
    run(args)
