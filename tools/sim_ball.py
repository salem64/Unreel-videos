#!/usr/bin/env python3
"""Satisfying physics short: a ball bounces inside a ring, grows and plays a note on every hit.
Usage: python3 sim_ball.py out.mp4 [seed] ["HOOK LINE 1|HOOK LINE 2"]
"""
import math, subprocess, sys, colorsys, random
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS, SR = 1080, 1920, 60, 44100
SUB = 8
OUT = sys.argv[1]
rng = random.Random(int(sys.argv[2]) if len(sys.argv) > 2 else 3)
F = "/usr/share/fonts/opentype/inter/InterDisplay-Black.otf"

CX, CY, R = W / 2, 1000, 430          # ring
g = 1400.0                             # gravity px/s^2
pos = np.array([CX + 60.0, CY - 150.0])
vel = np.array([rng.uniform(-500, 500), 0.0])
r = 22.0
GROW = 6.5
MAX_T = 40.0

# pentatonic melody notes (Hz) – cycles upward as the ball grows
scale = [261.6, 293.7, 329.6, 392.0, 440.0, 523.3, 587.3, 659.3, 784.0, 880.0, 1046.5]
melody = [0, 2, 4, 5, 4, 2, 3, 5, 7, 6, 4, 5, 7, 8, 9, 7, 8, 10]

hits, trail, frames_state = [], [], []
t, dt = 0.0, 1.0 / (FPS * SUB)
end_t = None
while t < MAX_T:
    for _ in range(SUB):
        vel[1] += g * dt
        pos += vel * dt
        d = pos - np.array([CX, CY])
        dist = np.linalg.norm(d)
        if dist + r >= R:
            n = d / dist
            pos = np.array([CX, CY]) + n * (R - r - 0.5)
            vn = np.dot(vel, n)
            if vn > 0:
                vel = vel - 2 * vn * n
                # keep energy alive + small tangential kick for chaos
                speed = np.linalg.norm(vel)
                target = max(speed, 1100)
                vel = vel / speed * target
                tang = np.array([-n[1], n[0]])
                vel += tang * rng.uniform(-60, 60)
                if not hits or t - hits[-1][0] > 0.12:
                    r = min(r + GROW, R - 2)
                    hits.append((t, len(hits)))
        t += dt
    trail.append((pos.copy(), r))
    trail = trail[-18:]
    frames_state.append((pos.copy(), r, list(trail), len(hits)))
    if r >= R - 6 and end_t is None:
        end_t = t
    if end_t is not None and t > end_t + 1.5:
        break
total = t
print("hits", len(hits), "duration", round(total, 1))

# ---------------- audio
n = int(SR * (total + 0.5))
audio = np.zeros(n, dtype=np.float32)
for (ht, i) in hits:
    f = scale[melody[i % len(melody)]]
    L = int(SR * 0.6)
    tt = np.arange(L) / SR
    tone = (np.sin(2 * np.pi * f * tt) + 0.35 * np.sin(2 * np.pi * 2 * f * tt) + 0.12 * np.sin(2 * np.pi * 3 * f * tt))
    tone *= np.exp(-tt / 0.25) * np.minimum(1, tt / 0.003)
    p = int(ht * SR)
    seg = tone[: max(0, min(L, n - p))]
    audio[p:p + len(seg)] += seg.astype(np.float32) * 0.25
# final chord
if end_t:
    p = int(end_t * SR); L = int(SR * 1.5); tt = np.arange(L) / SR
    chord = sum(np.sin(2 * np.pi * f * tt) for f in (523.3, 659.3, 784.0, 1046.5)) * np.exp(-tt / 0.6) * 0.18
    seg = chord[: max(0, min(L, n - p))]; audio[p:p + len(seg)] += seg.astype(np.float32)
audio /= max(np.max(np.abs(audio)), 1e-6) / 0.9
import soundfile as sf
sf.write(OUT + ".wav", audio, SR)

# ---------------- video
font_big = ImageFont.truetype(F, 92)
font_cnt = ImageFont.truetype(F, 150)
font_wm = ImageFont.truetype(F, 44)
bg = Image.new("RGB", (W, H), (8, 8, 12))
cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
       "-i", "-", "-i", OUT + ".wav", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
       "-r", "30", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", OUT]
ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)


def col(i, l=0.55):
    h = (i * 0.045) % 1.0
    return tuple(int(c * 255) for c in colorsys.hls_to_rgb(h, l, 0.95))


hook = (sys.argv[3] if len(sys.argv) > 3 else "WILL IT FILL|THE CIRCLE?").upper().split("|")
for fi, (p, rr, tr, nh) in enumerate(frames_state):
    img = bg.copy()
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    c = col(nh)
    gd.ellipse((CX - R - 30, CY - R - 30, CX + R + 30, CY + R + 30), outline=c, width=50)
    glow = glow.filter(ImageFilter.GaussianBlur(40))
    img = Image.blend(img, glow, 0.5)
    d = ImageDraw.Draw(img)
    d.ellipse((CX - R, CY - R, CX + R, CY + R), outline=c, width=10)
    for k, (tp, trr) in enumerate(tr[:-1]):
        a = (k + 1) / len(tr)
        cc = tuple(int(v * a * 0.6) for v in col(nh))
        d.ellipse((tp[0] - trr, tp[1] - trr, tp[0] + trr, tp[1] + trr), fill=cc)
    d.ellipse((p[0] - rr, p[1] - rr, p[0] + rr, p[1] + rr), fill=col(nh, 0.62), outline=(255, 255, 255), width=4)
    # hook text (always visible from frame 1)
    y = 190
    for line in hook:
        tw = d.textlength(line, font=font_big)
        d.text(((W - tw) / 2, y), line, font=font_big, fill=(255, 255, 255), stroke_width=6, stroke_fill=(0, 0, 0))
        y += 105
    s = str(nh)
    tw = d.textlength(s, font=font_cnt)
    d.text(((W - tw) / 2, CY + R + 60), s, font=font_cnt, fill=col(nh, 0.65))
    lab = "BOUNCES"
    lf = ImageFont.truetype(F, 40)
    d.text(((W - d.textlength(lab, font=lf)) / 2, CY + R + 225), lab, font=lf, fill=(160, 160, 170))
    d.text((60, 70), "unreel", font=font_wm, fill=(255, 255, 255))
    ff.stdin.write(img.tobytes())
ff.stdin.close(); ff.wait()
import os; os.remove(OUT + ".wav")
print("done", OUT)
