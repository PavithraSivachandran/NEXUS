"""Render the NEXUS simulation film (parallel segments -> H.264)."""
import os
import subprocess
import sys
import time
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
from scenes import FPS, T_TOTAL

OUT = "/home/user/nexus_simulation.mp4"
TMP = "/home/user/nexus/_seg"


def render_segment(args):
    idx, start, end, path = args
    from scenes import Renderer
    r = Renderer()
    dt = 1.0 / FPS
    t = start * dt
    # replay state to segment start (cheap, deterministic)
    steps = int(round(start))
    t0 = 0.0
    for i in range(steps):
        t0 += dt
        r.update(t0, dt)
    cmd = [FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", "1920x1080", "-r", str(FPS), "-i", "-",
           "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                         stderr=subprocess.PIPE)
    n = end - start
    for i in range(n):
        t = (start + i) * dt
        r.update(t, dt)
        img = r.render(t)
        p.stdin.write(img.tobytes())
        if i % 200 == 0:
            print(f"[seg {idx}] {i}/{n}", flush=True)
    p.stdin.close()
    rc = p.wait()
    err = p.stderr.read().decode()[-500:]
    if rc != 0:
        print(f"[seg {idx}] FAILED rc={rc}\n{err}", flush=True)
    return idx, path, rc


def main():
    total = int(T_TOTAL * FPS)
    nseg = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    out = sys.argv[2] if len(sys.argv) > 2 else OUT
    os.makedirs(TMP, exist_ok=True)
    bounds = [int(total * i / nseg) for i in range(nseg)] + [total]
    jobs = [(i, bounds[i], bounds[i + 1], f"{TMP}/s{i:02d}.mp4") for i in range(nseg)]
    t_start = time.time()
    with mp.Pool(min(nseg, 2)) as pool:
        results = pool.map(render_segment, jobs)
    for i, path, rc in sorted(results):
        print(f"seg {i}: rc={rc}  {os.path.getsize(path)/1e6:.1f} MB")
    # concat
    lst = f"{TMP}/list.txt"
    with open(lst, "w") as f:
        for i in range(nseg):
            f.write(f"file '{TMP}/s{i:02d}.mp4'\n")
    cmd = [FFMPEG, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst,
           "-c", "copy", out]
    print(subprocess.run(cmd, capture_output=True, text=True).stderr[-800:])
    print(f"DONE in {(time.time()-t_start)/60:.1f} min -> {out}")


if __name__ == "__main__":
    main()
