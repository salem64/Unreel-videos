#!/usr/bin/env python3
"""Retro pixel fact reel: On Venus, one day is longer than one year.
Reuses the pixel engine from iss_reel.py.
Usage: python3 venus_reel.py render out.mp4 | sheet out.png t1,t2,...
"""
import math, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw
import iss_reel as R
from iss_reel import (W, H, FPS, SR, hx, INK, BG, WHITE, CYAN, YELLOW, RED, GREEN, GREY, DGREY, ORANGE,
                      text, tw, panel, clamp, ease, ease_out, space, _sample, BAYER, LAND)

DUR = 32.5
NF = int(round(DUR * FPS))
CPS = 30.0

CAPS = [
    (0.30, "ON VENUS, ONE DAY IS", "LONGER THAN ONE YEAR.", 'yellow', 1),
    (3.50, "SOUNDS FAKE, RIGHT?", "LET'S CHECK.", 'cyan', 1),
    (6.60, "1 YEAR = 1 TRIP", "AROUND THE SUN.", 'cyan', 1),
    (9.60, "1 DAY = 1 FULL SPIN.", "WATCH BOTH:", 'yellow', 1),
    (16.95, "YEAR DONE: 225 DAYS.", "THE SPIN ISN'T DONE.", 'cyan', 1),
    (18.40, "SPIN DONE: 243 DAYS.", "THE DAY WINS.", 'green', 1),
    (20.70, "IT ALSO SPINS BACKWARDS,", "SUN RISES IN THE WEST.", 'yellow', 1),
    (24.00, "SUN-UP TO SUN-UP:", "STILL ABOUT 117 DAYS.", 'cyan', 1),
    (27.70, "SO ON VENUS YOU'D BE", "OLDER BEFORE TOMORROW.", 'yellow', 1),
]
SCENES = [(0.0, 'intro'), (6.3, 'orbit'), (20.5, 'surface'), (27.5, 'outro')]
IRIS_AT = [6.3, 20.5, 27.5]
IRIS_HALF = 0.22
ORBIT_T0, ORBIT_DUR = 6.3, 14.2
COUNT = (0.8, 10.5)        # local start, duration for days 0 -> 243
YEAR_D, SPIN_D = 224.7, 243.0
OPT1, OPT2 = "[ ] KNEW IT", "[ ] NO WAY"
OPT_T1 = 29.3
OPT_T2 = OPT_T1 + len(OPT1) / CPS + 0.15
SELECT_T = OPT_T2 + len(OPT2) / CPS + 0.25


def days_at(tl):
    return SPIN_D * clamp((tl - COUNT[0]) / COUNT[1])


def abs_time_of_day(d):
    return ORBIT_T0 + COUNT[0] + COUNT[1] * d / SPIN_D


def scene_at(t):
    name, st = SCENES[0][1], 0.0
    for s, n in SCENES:
        if t >= s:
            name, st = n, s
    return name, t - st


# ---------------------------------------------------------------- Venus globe
VCOL = np.array([hx('f6dc98'), hx('e8bd68'), hx('cf9447'), hx('a96a2e'), hx('7a4720')], np.uint8)
V_NIGHT = np.array(hx('2e1d12'), np.uint8)
V_ATM = np.array(hx('ffe6a0'), np.uint8)


def draw_venus(arr, cx, cy, r, rot, L, tilt=0.25):
    hh, ww = arr.shape[:2]
    x0, x1 = max(0, int(cx - r - 3)), min(ww, int(cx + r + 4))
    y0, y1 = max(0, int(cy - r - 3)), min(hh, int(cy + r + 4))
    if x0 >= x1 or y0 >= y1:
        return
    ys, xs = np.mgrid[y0:y1, x0:x1]
    nx, ny = (xs + 0.5 - cx) / r, (ys + 0.5 - cy) / r
    d2 = nx * nx + ny * ny
    inside = d2 <= 1.0
    nz = np.sqrt(np.clip(1 - d2, 0, 1))
    ct, st = math.cos(tilt), math.sin(tilt)
    ny2, nz2 = ny * ct - nz * st, ny * st + nz * ct
    lat = np.arcsin(np.clip(-ny2, -1, 1))
    lon = np.arctan2(nx, nz2) + rot
    th, twd = LAND.shape
    land = _sample(LAND, ((lon / (2 * np.pi)) % 1.0) * twd, (0.5 - lat / np.pi) * (th - 1))
    val = 0.5 * land + 0.5 * (np.sin(lat * 7 + land * 5) + 1) / 2
    Lv = np.array(L, np.float32)
    Lv /= np.linalg.norm(Lv)
    lam = nx * Lv[0] + ny * Lv[1] + nz * Lv[2]
    b = BAYER[ys % 4, xs % 4]
    idx = np.clip((val * 3.2 + (b - 0.5) * 0.7).astype(int), 0, 3)
    idx = idx + (lam < 0.3 + (b - 0.5) * 0.3)
    col = VCOL[np.clip(idx, 0, 4)]
    col[~(lam > (b - 0.5) * 0.25)] = V_NIGHT
    sub = arr[y0:y1, x0:x1]
    sub[inside] = col[inside]
    dd = np.sqrt(d2)
    rim = (dd > 1.0) & (dd <= 1.0 + 1.4 / max(r, 4))
    rl = (nx * Lv[0] + ny * Lv[1]) / np.maximum(dd, 1e-6)
    sub[rim & (rl > -0.2)] = V_ATM


def draw_sun(arr, cx, cy, r):
    yy, xx = np.mgrid[0:arr.shape[0], 0:arr.shape[1]]
    dist = np.hypot(xx - cx, yy - cy)
    arr[(dist <= r + 4) & (dist > r) & (((xx + yy) % 2) == 0)] = ORANGE
    arr[dist <= r] = YELLOW
    arr[dist <= r * 0.5] = hx('fff6c8')


# ---------------------------------------------------------------- scenes
def scene_big_venus(t, dim=False):
    arr = space(t)
    draw_venus(arr, 90, 185, 48, rot=-t * 0.12, L=(-0.6, -0.45, 0.66))
    if dim:
        arr = (arr.astype(np.float32) * 0.42 + np.array(INK, np.float32) * 0.58).astype(np.uint8)
    return Image.fromarray(arr)


SUN_C = (90, 190)
ORB_R = 62


def venus_pos(d):
    th = -2 * math.pi * d / YEAR_D - math.pi / 2  # start at the top, counter-clockwise
    return SUN_C[0] + ORB_R * math.cos(th), SUN_C[1] + ORB_R * math.sin(th)


def scene_orbit(t, tl):
    d_now = days_at(tl)
    arr = space(t)
    draw_sun(arr, *SUN_C, 9)
    vx, vy = venus_pos(min(d_now, YEAR_D) if d_now < YEAR_D else d_now)
    L = (SUN_C[0] - vx, SUN_C[1] - vy, 18.0)
    draw_venus(arr, vx, vy, 11, rot=0, L=L)
    img = Image.fromarray(arr)
    dr = ImageDraw.Draw(img)
    # orbit path: travelled part bright, rest dim (drawn under the planet)
    done = d_now / YEAR_D
    for k in range(120):
        f = k / 120
        if abs(f - (done % 1.0)) < 0.06 and done < 1:
            continue
        x, y = venus_pos(f * YEAR_D)
        if math.hypot(x - vx, y - vy) <= 13:
            continue
        dr.point((x, y), fill=CYAN if (f <= done or done >= 1) else DGREY)
    # start marker
    sx, sy = venus_pos(0)
    dr.line([(sx, sy - 14), (sx, sy - 12)], fill=WHITE)
    # spin marker: backwards (clockwise on screen), starts pointing up
    ang = math.pi / 2 - 2 * math.pi * d_now / SPIN_D
    ex, ey = vx + 11 * math.cos(ang), vy - 11 * math.sin(ang)
    dr.line([(vx, vy), (ex, ey)], fill=INK, width=4)
    dr.line([(vx, vy), (ex, ey)], fill=WHITE, width=2)
    dr.rectangle([ex - 2, ey - 2, ex + 2, ey + 2], fill=RED, outline=INK)
    return img


SKY = [hx('5a2c18'), hx('7a3a1c'), hx('a3561f'), hx('c97a2c'), hx('e2a447')]


def scene_surface(t, tl):
    arr = np.empty((H, W, 3), np.uint8)
    yy, xx = np.mgrid[0:H, 0:W]
    b = BAYER[yy % 4, xx % 4]
    g = np.clip((yy - 60) / 175.0, 0, 1) * 4 + (b - 0.5) * 0.9
    arr[:] = np.array(SKY, np.uint8)[np.clip(g.astype(int), 0, 4)]
    # rising sun in the WEST (left), blurred by thick clouds
    p = ease((tl - 0.6) / 6.0)
    sx, sy = 38, 240 - p * 44
    dist = np.hypot(xx - sx, yy - sy)
    arr[(dist <= 16) & (b < 0.35)] = hx('ffd27a')
    arr[dist <= 9] = hx('fff0b8')
    img = Image.fromarray(arr)
    d = ImageDraw.Draw(img)
    d.polygon([(0, 236), (30, 231), (55, 236), (90, 229), (125, 235), (150, 228), (180, 233), (180, 320), (0, 320)],
              fill=hx('7a3d1d'))
    d.polygon([(0, 252), (40, 248), (95, 254), (140, 247), (180, 251), (180, 320), (0, 320)], fill=hx('5e2c15'))
    for rx, ry, rw in ((20, 262, 9), (70, 270, 6), (120, 259, 11), (160, 275, 7), (45, 288, 12), (135, 292, 8)):
        d.polygon([(rx - rw, ry + 3), (rx - rw // 3, ry - 3), (rx + rw // 2, ry - 2), (rx + rw, ry + 3)],
                  fill=hx('3f1d0d'), outline=INK)
    for lx, lab in ((8, "W"), (166, "E")):
        d.rectangle([lx - 2, 236, lx + 6, 246], fill=INK)
        text(d, lx, 238, lab, WHITE)
    # backwards arrow along the sky: east -> west
    return img


# ---------------------------------------------------------------- UI
def bar(d, x, y, frac, col, n=14):
    filled = int(round(n * clamp(frac)))
    for i in range(n):
        d.rectangle([x + i * 3, y, x + i * 3 + 1, y + 4], fill=col if i < filled else DGREY)


def draw_hud(d, t, name, tl):
    if name == 'orbit' and tl > 0.4:
        dn = days_at(tl)
        panel(d, 10, 72, [("EARTH DAYS: ", WHITE), (f"{int(dn):>3}", CYAN)])
        yr, sp = dn / YEAR_D, dn / SPIN_D
        for y, lab, frac, col in ((87, "YEAR ", yr, CYAN), (102, "SPIN ", sp, YELLOW)):
            done = frac >= 1
            val = " ✓" if done else f"{int(frac * 100):>2}%"
            xs, _ = panel(d, 10, y, [(lab, WHITE), (val, GREEN if done else col)], extra_w=47)
            bar(d, 10 + 3 + 9 * 6 + 2, y + 4, frac, GREEN if done else col)
        if dn < 2:
            text(d, 103, 118, "START", GREY)
    elif name == 'surface' and tl > 0.4:
        panel(d, 10, 72, [("SUNRISE: ", WHITE), ("WEST", YELLOW)])
        if t >= 24.0:
            panel(d, 10, 87, [("SUN-UP TO SUN-UP: ", WHITE), ("117 D", CYAN)])
    elif name == 'outro' and t >= OPT_T1 - 0.15:
        d.rectangle([34, 146, 146, 192], fill=INK, outline=WHITE)
        d.rectangle([36, 148, 144, 190], outline=DGREY)
        n1 = int(clamp(int((t - OPT_T1) * CPS) + 1, 0, len(OPT1))) if t >= OPT_T1 else 0
        n2 = int(clamp(int((t - OPT_T2) * CPS) + 1, 0, len(OPT2))) if t >= OPT_T2 else 0
        x0 = 90 - tw(OPT1) // 2
        text(d, x0, 158, OPT1[:n1], WHITE)
        sel = t >= SELECT_T
        text(d, x0, 174, OPT2[:n2], (YELLOW if int(t * 3) % 2 == 0 else WHITE) if sel else WHITE)
        if sel:
            text(d, x0 + 6, 174, "▶", YELLOW)


_YY, _XX = np.mgrid[0:H, 0:W]
DIST = np.hypot(_XX - 90, _YY - 180)


def render(t):
    R.CAPS = CAPS
    name, tl = scene_at(t)
    if name == 'intro':
        img = scene_big_venus(t)
    elif name == 'orbit':
        img = scene_orbit(t, tl)
    elif name == 'surface':
        img = scene_surface(t, tl)
    else:
        img = scene_big_venus(t, dim=True)
    arr = np.array(img)
    for b in IRIS_AT:
        if b - IRIS_HALF <= t < b + IRIS_HALF:
            rad = int(205 * ease(abs(t - b) / IRIS_HALF) / 4) * 4
            arr[DIST > rad] = INK
    img = Image.fromarray(arr)
    d = ImageDraw.Draw(img)
    draw_hud(d, t, name, tl)
    R.draw_caption(d, t)
    return img


# ---------------------------------------------------------------- audio
def char_times():
    out = []
    for c in CAPS:
        t1, t2 = R.cap_line_times(c)
        out += [(t1 + i / CPS, 1) for i, ch in enumerate(c[1]) if ch != ' ']
        out += [(t2 + i / CPS, 2) for i, ch in enumerate(c[2]) if ch != ' ']
    out += [(OPT_T1 + i / CPS, 1) for i, ch in enumerate(OPT1) if ch != ' ']
    out += [(OPT_T2 + i / CPS, 2) for i, ch in enumerate(OPT2) if ch != ' ']
    return out


def build_audio(path):
    n = int((DUR + 0.5) * SR)
    out = np.zeros(n, np.float32)
    rng = np.random.default_rng(2)

    def add(t0, sig, vol=1.0):
        i0 = int(t0 * SR)
        if 0 <= i0 < n:
            seg = sig[: n - i0]
            out[i0:i0 + len(seg)] += seg * vol

    def tone(f, dur, wave_='sq', duty=0.5, decay=6.0, f_end=None):
        m = int(dur * SR)
        tt = np.arange(m) / SR
        ph = f * tt if f_end is None else np.cumsum(np.geomspace(f, f_end, m)) / SR
        frac = ph % 1.0
        w = np.where(frac < duty, 1.0, -1.0) if wave_ == 'sq' else 4 * np.abs(frac - 0.5) - 1
        env = np.exp(-decay * tt) * np.clip(tt / 0.004, 0, 1) * np.clip((dur - tt) / 0.01, 0, 1)
        return (w * env).astype(np.float32)

    def noise(dur, decay=20.0, hold=1):
        m = int(dur * SR)
        x = rng.uniform(-1, 1, m // hold + 2).repeat(hold)[:m]
        return (x * np.exp(-decay * np.arange(m) / SR)).astype(np.float32)

    # music: Dm Bb F C, 120 bpm, slightly dreamier than the ISS track
    e8 = 60 / 120 / 2
    chords = [([293.66, 349.23, 440, 587.33], 73.42), ([233.08, 293.66, 349.23, 466.16], 58.27),
              ([349.23, 440, 523.25, 698.46], 87.31), ([261.63, 329.63, 392, 523.25], 65.41)]
    pat = [0, 2, 1, 3, 2, 1, 3, 2]
    bar_i = 0
    while bar_i * 8 * e8 < DUR:
        arp, root = chords[bar_i % 4]
        for s in range(8):
            t0 = (bar_i * 8 + s) * e8
            add(t0, tone(arp[pat[s]], e8 * 0.95, duty=0.25, decay=6), 0.06)
            if s % 2 == 1:
                add(t0, noise(0.03, decay=90), 0.022)
        for bt in range(4):
            t0 = (bar_i * 8 + bt * 2) * e8
            add(t0, tone(root * 2, e8 * 1.9, 'tri', decay=3), 0.17)
            if bt in (0, 2):
                add(t0, tone(120, 0.12, 'tri', decay=25, f_end=45), 0.2)
        bar_i += 1
    out *= np.clip((DUR - np.arange(n) / SR) / 1.2, 0, 1).astype(np.float32)

    for tc, line in char_times():
        add(tc, tone(1150 if line == 1 else 1450, 0.028, decay=60), 0.07)
    for b in IRIS_AT:
        wsh = noise(0.4, decay=0, hold=3)
        wsh *= np.sin(np.linspace(0, np.pi, len(wsh))).astype(np.float32)
        add(b - 0.25, wsh, 0.06)
    for dd in range(10, 243, 10):  # counter ticks
        add(abs_time_of_day(dd), tone(1760, 0.025, decay=80), 0.045)
    arp = [523.25, 659.25, 783.99, 1046.5]
    for k, f in enumerate(arp):
        add(abs_time_of_day(YEAR_D) + k * 0.07, tone(f, 0.18, decay=8), 0.08)
    for k, f in enumerate(arp + [1318.5]):
        add(abs_time_of_day(SPIN_D) + k * 0.09, tone(f, 0.25, decay=6, duty=0.25), 0.09)
    add(20.5 + 0.6, tone(220, 6.0, duty=0.25, decay=0.2, f_end=440), 0.03)
    add(SELECT_T, tone(988, 0.07, decay=20), 0.09)
    add(SELECT_T + 0.07, tone(1318.5, 0.12, decay=12), 0.09)
    out *= 0.89 / float(np.max(np.abs(out)))
    pcm = (np.clip(out, -1, 1) * 32767).astype('<i2')
    with wave.open(path, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


def render_video(out):
    wav = out.rsplit('.', 1)[0] + '.wav'
    build_audio(wav)
    cmd = ['ffmpeg', '-y', '-loglevel', 'error',
           '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-', '-i', wav,
           '-vf', 'scale=1080:1920:flags=neighbor:out_color_matrix=bt709:out_range=tv,format=yuv420p',
           '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-tune', 'animation',
           '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
           '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for fi in range(NF):
        p.stdin.write(render(fi / FPS).tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise SystemExit('ffmpeg failed')


def sheet(out, times, cols=6):
    rows = (len(times) + cols - 1) // cols
    sh = Image.new('RGB', (cols * (W + 4), rows * (H + 4)), (60, 60, 60))
    for i, t in enumerate(times):
        sh.paste(render(t), ((i % cols) * (W + 4), (i // cols) * (H + 4)))
    sh.save(out)


if __name__ == '__main__':
    if sys.argv[1] == 'sheet':
        sheet(sys.argv[2], [float(x) for x in sys.argv[3].split(',')])
    else:
        render_video(sys.argv[2])
