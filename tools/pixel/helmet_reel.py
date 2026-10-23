#!/usr/bin/env python3
"""Energetic retro pixel reel: an astronaut's helmet cracks - what happens to his body?
Stakes + live meters + magnifier cut-ins + alarms, like the reference reel.
Usage: python3 helmet_reel.py render out.mp4 | sheet out.png t1,t2,...
"""
import math, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw
import iss_reel as R
from iss_reel import (W, H, FPS, SR, hx, INK, WHITE, CYAN, YELLOW, RED, GREEN, GREY, DGREY, ORANGE,
                      text, tw, panel, clamp, ease, ease_out, space, draw_globe, outline_rgba, BAYER)

R.FLOAT_T = -1.0  # cabin scene: always show the "ok" sparkles
DUR = 30.0
NF = int(round(DUR * FPS))
CPS = 40.0
COLS = {'cyan': CYAN, 'yellow': YELLOW, 'red': RED, 'green': GREEN, 'white': WHITE}

CRACK, VAC0 = 0.6, 2.4
S2, S3, S4, S5, S6, S7 = 5.0, 9.6, 14.2, 19.0, 23.4, 26.4
EXHALE, SWELL, BLACKOUT = 7.9, 11.9, 17.4
PULL0, PULL1, HATCH, REP0, REP1 = 19.5, 21.2, 21.8, 22.0, 23.2

CAPS = [
    (0.10, "HIS HELMET JUST CRACKED.", "HOW LONG DOES HE HAVE?", 'red', 1),
    (2.70, "THE AIR RUSHES OUT.", "THE CLOCK IS RUNNING.", 'yellow', 1),
    (5.10, "RULE NO. 1:", "BREATHE OUT!", 'red', 2),
    (6.50, "AIR HELD IN THE LUNGS", "EXPANDS AND TEARS THEM.", 'yellow', 1),
    (8.00, "SO HE EXHALES.", "LUNGS SAFE.", 'green', 1),
    (9.70, "HIS SPIT STARTS", "BOILING ON HIS TONGUE.", 'yellow', 1),
    (11.90, "HIS BODY SWELLS UP,", "BUT NO, HE WON'T POP.", 'cyan', 1),
    (14.30, "NO AIR IN HIS LUNGS =", "NO OXYGEN FOR HIS BRAIN.", 'yellow', 1),
    (16.60, "AFTER ~15 SECONDS:", "BLACKOUT.", 'red', 2),
    (19.10, "HIS BUDDY PULLS HIM IN.", "GO GO GO!", 'yellow', 1),
    (21.90, "AIR BACK WITHIN ~90 S", "= STILL SURVIVABLE.", 'green', 1),
    (23.50, "HE WAKES UP.", "HE'S OK.", 'green', 2),
    (26.50, "YOUR HELMET CRACKS.", "FIRST THING YOU DO?", 'cyan', 1),
]
OPT1, OPT2 = "[ ] HOLD BREATH", "[ ] BREATHE OUT"
OPT_T1 = 27.3
OPT_T2 = OPT_T1 + len(OPT1) / CPS + 0.15
SELECT_T = OPT_T2 + len(OPT2) / CPS + 0.3


def cap_times(c):
    return c[0], c[0] + len(c[1]) / CPS + (0.1 if c[1] else 0.0)


# ---------------------------------------------------------------- state curves
def pressure(t):
    return 1 - ease((t - 0.7) / 1.7)


def vac_time(t):
    return min(t, REP0) - VAC0


def o2(t):
    if t < 8:
        return 1.0
    if t < BLACKOUT:
        return 1 - 0.75 * ease((t - 8) / (BLACKOUT - 8))
    if t < REP0:
        return 0.25
    return 0.25 + 0.75 * ease((t - REP0) / 1.6)


def swell_f(t):
    if t < SWELL:
        return 1.0
    return 1 + 0.1 * ease((t - SWELL) / 1.5) * (1 - ease((t - REP0) / 1.2))


def limp_f(t):
    return ease((t - BLACKOUT) / 1.0) * (1 - ease((t - REP0) / 1.0))


def panic_f(t):
    return clamp((t - CRACK) / 0.2) * (1 - ease((t - BLACKOUT + 0.6) / 0.6))


# ---------------------------------------------------------------- characters
SUIT, SUIT2, PACK, GLOVE = hx('f2f2f2'), hx('c3c9db'), hx('9aa3bd'), hx('6f7896')
VISOR, VHI, GOLD = hx('1d2a5c'), hx('6fa8ff'), hx('d9a441')
CRACK_SEGS = [((24, 10), (20, 7)), ((24, 10), (28, 8)), ((24, 10), (22, 15)), ((20, 7), (17, 9)),
              ((22, 15), (25, 17)), ((24, 10), (29, 13)), ((28, 8), (30, 6))]


def suit(t, crack=0.0, swell=1.0, buddy=False, limp=0.0, panic=0.0):
    im = Image.new('RGBA', (46, 54), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    A = lambda c: c + (255,)
    w = math.sin(t * (2 + 14 * panic))
    d.rounded_rectangle([14, 13, 32, 31], 3, fill=A(PACK))
    for hip, kx, fx in ((19, 17 - limp * 2, 16), (27, 29 + limp * 2, 30)):
        knee, foot = (kx, 40), (fx + w * 2 * panic, 47)
        d.line([(hip, 31), knee], fill=A(SUIT), width=6)
        d.line([knee, foot], fill=A(SUIT), width=5)
        d.rectangle([foot[0] - 3, foot[1] - 1, foot[0] + 3, foot[1] + 3], fill=A(GLOVE))
        if not buddy:
            d.line([(knee[0] - 2, 36), (knee[0] + 2, 36)], fill=A(RED), width=2)
    d.rounded_rectangle([15, 18, 31, 33], 3, fill=A(SUIT))
    d.rectangle([19, 22, 27, 27], fill=A(SUIT2))
    d.point([(20, 24), (22, 24)], fill=A(RED))
    d.point([(25, 24)], fill=A(GREEN))
    for sh, sign in (((15, 20), -1), ((31, 20), 1)):
        up = limp * 10
        el = (sh[0] + sign * 6, sh[1] + 5 - up * 0.5 + w * 3 * panic * sign)
        hd = (sh[0] + sign * 9, sh[1] + 11 - up + w * 5 * panic)
        d.line([sh, el], fill=A(SUIT), width=5)
        d.line([el, hd], fill=A(SUIT), width=4)
        d.rectangle([hd[0] - 2, hd[1] - 2, hd[0] + 2, hd[1] + 2], fill=A(GLOVE))
        if not buddy:
            d.point([(sh[0] + sign * 3, sh[1] + 2)], fill=A(RED))
    d.ellipse([13, 2, 33, 21], fill=A(SUIT))
    d.ellipse([16, 5, 30, 17], fill=A(GOLD if buddy else VISOR))
    d.line([(18, 9), (20, 7)], fill=A(WHITE if buddy else VHI))
    if crack > 0:
        n = int(math.ceil(clamp(crack) * len(CRACK_SEGS)))
        for p, q in CRACK_SEGS[:n]:
            d.line([p, q], fill=A(WHITE))
    im = Image.fromarray(outline_rgba(np.array(im)), 'RGBA')
    if abs(swell - 1.0) > 0.01:
        im = im.resize((round(46 * swell), round(54 * swell)), Image.NEAREST)
    if limp > 0.02:
        im = im.rotate(-25 * limp, resample=Image.NEAREST, expand=True)
    return im


def paste_c(img, spr, x, y):
    img.paste(spr, (int(round(x - spr.width / 2)), int(round(y - spr.height / 2))), spr)


def a_pos(t):
    x, y = 124 + 1.5 * math.sin(t * 0.9), 146 + 2 * math.sin(t * 1.4)
    if t >= PULL0:
        k = ease((t - PULL0) / (PULL1 - PULL0))
        x, y = x + (74 - x) * k, y + (152 - y) * k
    if t >= PULL1:
        x = 74 + (6 - 74) * ease((t - PULL1) / 0.45)
    return x, y


def b_pos(t):
    x, y = 52, 156 + 1.5 * math.sin(t * 1.2 + 1)
    if t >= PULL1:
        x = 52 + (2 - 52) * ease((t - PULL1) / 0.45)
    return x, y


# ---------------------------------------------------------------- wide scene
def draw_airlock(d, t):
    d.rectangle([-1, 122, 36, 182], fill=hx('b8c0dc'), outline=INK)
    for y in (132, 152, 172):
        d.line([(0, y), (35, y)], fill=hx('8a94b8'))
    for x in (10, 24):
        d.line([(x, 123), (x, 181)], fill=hx('8a94b8'))
    d.rectangle([-1, 112, 7, 122], fill=hx('8a94b8'), outline=INK)
    d.ellipse([28, 124, 44, 180], fill=hx('8a94b8'), outline=INK)
    if t >= HATCH:
        d.ellipse([31, 132, 41, 172], fill=hx('c3c9db'), outline=INK)
        d.line([(36, 134), (36, 170)], fill=INK)
    else:
        d.ellipse([31, 132, 41, 172], fill=hx('05060f'), outline=INK)
    light = GREEN if t >= REP1 else (RED if int(t * 4) % 2 == 0 else hx('5a1020'))
    d.rectangle([14, 125, 19, 129], fill=light, outline=INK)
    d.line([(4, 178), (26, 178)], fill=YELLOW)


def draw_tether(d, t, ax, ay):
    if t >= PULL1:
        return
    x0, y0, x1, y1 = 38, 158, ax - 6, ay + 6
    slack = 14 * (1 - ease((t - PULL0) / 0.6))
    pts = []
    for i in range(41):
        s = i / 40
        pts.append((x0 + (x1 - x0) * s, y0 + (y1 - y0) * s + slack * 4 * s * (1 - s)))
    d.point(pts, fill=YELLOW)


def wide(t):
    arr = space(t)
    draw_globe(arr, 90, 640, 380, rot=5.3 + t * 0.006, tilt=1.3)
    img = Image.fromarray(arr)
    d = ImageDraw.Draw(img)
    ax, ay = a_pos(t)
    bx, by = b_pos(t)
    draw_tether(d, t, ax, ay)
    paste_c(img, suit(t, buddy=True, panic=0.6 if PULL0 <= t < HATCH else 0.0), bx, by)
    paste_c(img, suit(t, crack=(t - CRACK) / 0.25 if t >= CRACK else 0, swell=swell_f(t),
                      limp=limp_f(t), panic=panic_f(t)), ax, ay)
    draw_airlock(ImageDraw.Draw(img), t)
    return img, ax, ay


# ---------------------------------------------------------------- magnifier contents (101x101)
D = 101


def lerpc(a, b, k):
    k = clamp(k)
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


_rng = np.random.default_rng(7)
AIR = [(_rng.uniform(-0.7, 0.7), _rng.uniform(-0.7, 0.7), _rng.uniform(0, 6.28)) for _ in range(16)]


def zoom_lungs(tl):
    im = Image.new('RGB', (D, D), hx('3c1222'))
    d = ImageDraw.Draw(im)
    for y in range(24, 96, 12):
        d.arc([2, y - 14, 98, y + 26], 200, 340, fill=hx('d9c7c7'), width=2)
    ex = EXHALE - S2
    s = 1 + 0.34 * ease(tl / 2.5) if tl < ex else 1.34 - 0.46 * ease((tl - ex) / 0.5)
    d.rectangle([46, -1, 54, 36], fill=hx('d9809a'), outline=INK)
    for y in range(3, 34, 5):
        d.line([(47, y), (53, y)], fill=hx('b05a78'))
    d.line([(50, 34), (33, 46)], fill=hx('d9809a'), width=4)
    d.line([(50, 34), (67, 46)], fill=hx('d9809a'), width=4)
    blink = int(tl * 6) % 2 == 0
    for cx in (31, 69):
        rx, ry, cy = 16 * s, 26 * s, 62
        d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=hx('ff7aa0'), outline=INK)
        d.ellipse([cx - rx * 0.5, cy - ry * 0.75, cx + rx * 0.1, cy - ry * 0.3], fill=hx('ffb3c6'))
        if tl < ex and s > 1.2 and blink:
            d.ellipse([cx - rx - 2, cy - ry - 2, cx + rx + 2, cy + ry + 2], outline=RED, width=2)
        for ux, uy, ph in AIR:
            if tl < ex:
                jx = math.sin(tl * 9 + ph) * 1.5
                px, py = cx + ux * rx + jx, cy + uy * ry
            else:
                k = (tl - ex) * 1.8 + (ph / 6.28) * 0.2
                px = cx + ux * rx + (50 - cx - ux * rx) * clamp(k * 1.5)
                py = cy + uy * ry - k * 90
                if py < 0:
                    continue
            d.point([(px, py), (px + 1, py)], fill=WHITE)
    return im


BUB = [(42 + (i * 37) % 17, i * 0.11) for i in range(10)]


def zoom_face(tl):
    im = Image.new('RGB', (D, D), hx('0b1430'))
    d = ImageDraw.Draw(im)
    sw = 1 + 0.18 * ease((tl - (SWELL - S3)) / 1.4)
    d.ellipse([50 - 31 * sw, 8, 50 + 31 * sw, 70], fill=hx('3b2414'))
    d.ellipse([50 - 29 * sw, 18, 50 + 29 * sw, 100], fill=hx('f0bf8a'), outline=INK)
    if sw > 1.02:
        for cx in (50 - 18 * sw, 50 + 18 * sw):
            d.ellipse([cx - 6, 60, cx + 6, 70], fill=hx('e89a7a'))
    d.line([(35, 47), (43, 50)], fill=hx('15151f'), width=2)
    d.line([(57, 50), (65, 47)], fill=hx('15151f'), width=2)
    d.ellipse([37, 62, 63, 86], fill=hx('5a1a22'), outline=INK)
    d.pieslice([40, 70, 60, 92], 180, 360, fill=hx('ff8fa0'))
    if tl > 0.3:
        for bx, off in BUB:
            age = (tl - 0.3 - off) % 0.7
            if tl - 0.3 - off < 0:
                continue
            y = 76 - age * 26
            r = 1 + age * 3.5
            if age < 0.62:
                d.ellipse([bx - r, y - r, bx + r, y + r], outline=WHITE)
            else:
                d.point([(bx - 3, y), (bx + 3, y), (bx, y - 3), (bx, y + 3)], fill=WHITE)
    if sw > 1.02:
        o = 3 * math.sin(tl * 10)
        for side in (-1, 1):
            x = 50 + side * (31 * sw + 4 + o)
            for y in (44, 74):
                d.polygon([(x, y - 4), (x + side * 5, y), (x, y + 4)], fill=YELLOW, outline=INK)
    for p, q in (((96, 4), (82, 18)), ((82, 18), (88, 30)), ((82, 18), (70, 22)), ((88, 30), (84, 40))):
        d.line([p, q], fill=WHITE)
    return im


VESSEL = [(52, 104), (52, 74), (52, 62)]
BRANCHES = [[(52, 74), (36, 62), (30, 46)], [(52, 74), (68, 62), (74, 46)], [(52, 62), (52, 40)]]


def _along(path, s):
    segs = list(zip(path[:-1], path[1:]))
    L = [math.dist(a, b) for a, b in segs]
    tot, acc = sum(L), 0.0
    target = s * tot
    for (a, b), l in zip(segs, L):
        if acc + l >= target:
            k = (target - acc) / l
            return a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k
        acc += l
    return segs[-1][1]


def zoom_brain(t):
    o = o2(t)
    im = Image.new('RGB', (D, D), hx('120a14'))
    d = ImageDraw.Draw(im)
    d.ellipse([2, 4, 104, 124], fill=hx('f0bf8a'), outline=INK)
    d.ellipse([10, 12, 96, 82], fill=hx('e6d2c0'), outline=INK)
    bc = lerpc(hx('7a6a80'), hx('ef8fae'), (o - 0.25) / 0.75)
    d.ellipse([16, 18, 90, 74], fill=bc, outline=INK)
    dk = lerpc(hx('4e4458'), hx('c25c80'), (o - 0.25) / 0.75)
    for k, (x0, y0) in enumerate([(22, 26), (40, 22), (58, 26), (26, 46), (48, 42), (66, 46), (36, 58), (58, 58)]):
        d.arc([x0, y0, x0 + 18, y0 + 12], 200 + k * 10, 340 + k * 10, fill=dk, width=2)
    vc = lerpc(hx('6a3070'), RED, (o - 0.25) / 0.75)
    paths = [VESSEL + b[1:] for b in BRANCHES]
    for p in paths:
        d.line(p, fill=INK, width=5)
        d.line(p, fill=vc, width=3)
    n = int(round(5 * o))
    for pi, p in enumerate(paths):
        for i in range(n):
            s = (t * 0.9 + i / max(n, 1) + pi * 0.13) % 1.0
            x, y = _along(p, s)
            d.rectangle([x - 1, y - 1, x + 1, y + 1], fill=WHITE if o > 0.5 else hx('ffd0d8'))
    if t >= BLACKOUT and int(t * 3) % 2 == 0:
        text(d, 38, 86, "Z Z Z", hx('aab0d0'))
    return im


# ---------------------------------------------------------------- magnifier
MAG_C, MAG_R = (90, 242), 50
_my, _mx = np.mgrid[0:D, 0:D]
MASKS = {}


def mag_mask(r):
    if r not in MASKS:
        MASKS[r] = Image.fromarray(((_mx - 50) ** 2 + (_my - 50) ** 2 <= r * r).astype(np.uint8) * 255, 'L')
    return MASKS[r]


def apply_mag(img, t, ax, ay):
    if not (S2 <= t < S5):
        return img
    k = ease_out((t - S2) / 0.3) * (1 - ease((t - (S5 - 0.25)) / 0.25))
    pulse = 0
    for sw_t in (S3, S4):
        if sw_t <= t < sw_t + 0.2:
            pulse = 4 * math.sin(math.pi * (t - sw_t) / 0.2)
    r = int(min(50, MAG_R * k + pulse))
    if r < 3:
        return img
    sw = swell_f(t)
    if t < S3:
        content, off = zoom_lungs(t - S2), (0, 1)
    elif t < S4:
        content, off = zoom_face(t - S3), (0, -16)
    else:
        content, off = zoom_brain(t), (0, -18)
    for sw_t in (S2, S3, S4):
        if sw_t <= t < sw_t + 0.07:
            content = Image.blend(content, Image.new('RGB', (D, D), WHITE), 0.6)
    d = ImageDraw.Draw(img)
    tx, ty = ax + off[0] * sw, ay + off[1] * sw
    dx, dy = tx - MAG_C[0], ty - MAG_C[1]
    L = math.hypot(dx, dy)
    ex, ey = MAG_C[0] + dx / L * (r + 3), MAG_C[1] + dy / L * (r + 3)
    d.line([(tx, ty), (ex, ey)], fill=INK, width=3)
    d.line([(tx, ty), (ex, ey)], fill=CYAN)
    d.ellipse([tx - 3, ty - 3, tx + 3, ty + 3], outline=CYAN)
    img.paste(content, (MAG_C[0] - 50, MAG_C[1] - 50), mag_mask(r))
    d = ImageDraw.Draw(img)
    cx, cy = MAG_C
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=CYAN)
    d.ellipse([cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1], outline=WHITE)
    d.ellipse([cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2], outline=WHITE)
    d.ellipse([cx - r - 3, cy - r - 3, cx + r + 3, cy + r + 3], outline=INK)
    return img


# ---------------------------------------------------------------- camera / fx
_YY, _XX = np.mgrid[0:H, 0:W]
EDGE = np.minimum(np.minimum(_XX, W - 1 - _XX), np.minimum(_YY, H - 1 - _YY))
BAY = BAYER[_YY % 4, _XX % 4]


def camera(img, z, fx, fy):
    if z <= 1.001:
        return img
    cw, ch = W / z, H / z
    x0 = clamp(fx - cw / 2, 0, W - cw)
    y0 = clamp(fy - ch / 2, 0, H - ch)
    return img.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((W, H), Image.NEAREST)


def danger_border(arr, t):
    if 0.7 <= t < BLACKOUT:
        a = 1.0
    elif BLACKOUT <= t < REP1:
        a = 0.5
    else:
        return
    th = (5 + 5 * abs(math.sin(math.pi * t * 2))) * a
    m = (EDGE < th) & (BAY < 0.55 + 0.45 * (1 - EDGE / max(th, 1)))
    arr[m] = RED


def shake(t):
    for t0, dur, amp in ((CRACK, 0.45, 3), (16.6, 0.4, 2), (HATCH, 0.3, 2)):
        if t0 <= t < t0 + dur:
            k = int((t - t0) * FPS)
            return (amp if k % 2 == 0 else -amp), ((amp - 1) if k % 3 == 0 else -(amp - 1))
    return 0, 0


# ---------------------------------------------------------------- UI
def draw_caption(d, t):
    if t < 0.1:
        return
    x0, y0, x1, y1 = 10, 38, 169, 70
    d.rectangle([x0, y0, x1, y1], fill=INK, outline=WHITE)
    d.rectangle([x0 + 2, y0 + 2, x1 - 2, y1 - 2], outline=DGREY)
    cur = None
    for c in CAPS:
        if t >= c[0]:
            cur = c
    if cur is None:
        return
    st, l1, l2, cn, sc = cur
    t1, t2 = cap_times(cur)
    n1 = len(l1) if t >= t2 else int(clamp(int((t - t1) * CPS) + 1, 0, len(l1)))
    n2 = int(clamp(int((t - t2) * CPS) + 1, 0, len(l2))) if t >= t2 else 0
    col = COLS[cn]
    ya, yb = (43, 55) if sc == 1 else (42, 52)
    if l1:
        text(d, 90 - tw(l1) // 2, ya, l1[:n1], WHITE)
    xb = 90 - tw(l2, sc) // 2
    text(d, xb, yb, l2[:n2], WHITE if (sc == 2 and 0 <= t - t2 < 0.4 and int(t * 12) % 2 == 0) else col, sc)
    if int(t * 3) % 2 == 0 and not (sc == 2 and n2 >= len(l2)):
        if n2 > 0 or not l1:
            text(d, xb + n2 * 6 * sc, yb, "█", col, sc)
        else:
            text(d, 90 - tw(l1) // 2 + n1 * 6, ya, "█", WHITE)


def o2_panel(d, y, t):
    o = o2(t)
    blink = int(t * 4) % 2 == 0
    c = GREEN if o > 0.6 else (YELLOW if o > 0.4 else (RED if blink else hx('7a1020')))
    panel(d, 10, y, [("BRAIN O2: ", WHITE)], extra_w=62)
    filled = int(round(20 * o))
    for i in range(20):
        d.rectangle([73 + i * 3, y + 4, 74 + i * 3, y + 8], fill=c if i < filled else DGREY)


def draw_hud(d, t):
    blink = int(t * 4) % 2 == 0
    if t < S6:
        if 0.25 <= t < VAC0 + 0.15:
            p = pressure(t)
            panel(d, 10, 75, [("SUIT PRESSURE: ", WHITE), (f"{round(100 * p):>3}%", RED if (p < 0.6 and blink) else YELLOW)])
        elif t >= VAC0 + 0.15:
            stopped = t >= REP0
            panel(d, 10, 75, [("IN VACUUM: ", WHITE),
                              (f"0:{int(vac_time(t)):02d}", (GREEN if blink else WHITE) if stopped else RED)])
        if S2 <= t < S3:
            if t < EXHALE:
                panel(d, 10, 90, [("LUNGS: ", WHITE), ("HOLDING AIR!", RED if blink else YELLOW)])
            else:
                panel(d, 10, 90, [("LUNGS: ", WHITE), ("EXHALED ✓", GREEN)])
        elif S3 <= t < S4:
            panel(d, 10, 90, [("SPIT: ", WHITE), ("BOILING", YELLOW if blink else ORANGE)])
            if t >= SWELL:
                panel(d, 10, 105, [("BODY: ", WHITE), ("SWELLING", ORANGE)])
        elif t >= S4:
            o2_panel(d, 90, t)
            if BLACKOUT <= t < REP0:
                panel(d, 10, 105, [("STATUS: ", WHITE), ("BLACKED OUT", RED if blink else hx('7a1020'))])
            elif t >= REP0:
                a = ease((t - REP0) / (REP1 - REP0))
                panel(d, 10, 105, [("AIRLOCK AIR: ", WHITE), (f"{round(100 * a):>3}%", GREEN if a >= 1 else CYAN)])
    elif t < S7:
        panel(d, 10, 75, [("STATUS: ", WHITE), ("AWAKE ✓", GREEN)])
        panel(d, 10, 90, [("TIME IN VACUUM: ", WHITE), ("0:19", CYAN)])
    elif t >= OPT_T1 - 0.15:
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


# ---------------------------------------------------------------- frame
def render(t):
    if t < S6:
        img, ax, ay = wide(t)
        img = apply_mag(img, t, ax, ay)
        bump = ease((t - 0.65) / 0.25) * (1 - ease((t - 2.1) / 0.5))
        img = camera(img, 1 + 0.45 * bump, ax, ay - 14)
    else:
        mode = 'freefall' if t < S7 else 'outro'
        tl = t - (S6 if t < S7 else S7)
        img = R.scene_cabin(t, tl, mode)
        img = camera(img, 1 + 0.3 * (1 - ease(tl / 0.3)), 90, 170)
    arr = np.array(img)
    if BLACKOUT <= t < S5 + 0.3:
        k = ease((t - BLACKOUT) / 0.5) * (1 - ease((t - S5) / 0.3)) * (0.6 + 0.1 * math.sin(t * 9))
        arr = (arr * (1 - k) + np.array(INK) * k).astype(np.uint8)
    danger_border(arr, t)
    for ft, a in ((CRACK, 0.8), (S6, 0.6), (S7, 0.5)):
        if ft <= t < ft + 0.07:
            arr = (arr * (1 - a) + np.array(WHITE) * a).astype(np.uint8)
    img = Image.fromarray(arr)
    d = ImageDraw.Draw(img)
    draw_hud(d, t)
    draw_caption(d, t)
    dx, dy = shake(t)
    if dx or dy:
        img = Image.fromarray(np.roll(np.roll(np.array(img), dx, axis=1), dy, axis=0))
    return img


# ---------------------------------------------------------------- audio
def char_times():
    out = []
    for c in CAPS:
        t1, t2 = cap_times(c)
        out += [(t1 + i / CPS, 1) for i, ch in enumerate(c[1]) if ch != ' ']
        out += [(t2 + i / CPS, 2) for i, ch in enumerate(c[2]) if ch != ' ']
    out += [(OPT_T1 + i / CPS, 1) for i, ch in enumerate(OPT1) if ch != ' ']
    out += [(OPT_T2 + i / CPS, 2) for i, ch in enumerate(OPT2) if ch != ' ']
    return out


def build_audio(path):
    n = int((DUR + 0.5) * SR)
    mus = np.zeros(n, np.float32)
    sfx = np.zeros(n, np.float32)
    rng = np.random.default_rng(4)

    def add(buf, t0, sig, vol=1.0):
        i0 = int(t0 * SR)
        if 0 <= i0 < n:
            seg = sig[: n - i0]
            buf[i0:i0 + len(seg)] += seg * vol

    def tone(f, dur, wave_='sq', duty=0.5, decay=6.0, f_end=None):
        m = int(dur * SR)
        tt = np.arange(m) / SR
        ph = f * tt if f_end is None else np.cumsum(np.geomspace(f, f_end, m)) / SR
        frac = ph % 1.0
        w = np.where(frac < duty, 1.0, -1.0) if wave_ == 'sq' else 4 * np.abs(frac - 0.5) - 1
        env = np.exp(-decay * tt) * np.clip(tt / 0.003, 0, 1) * np.clip((dur - tt) / 0.01, 0, 1)
        return (w * env).astype(np.float32)

    def noise(dur, decay=20.0, hold=1, swell=False):
        m = int(dur * SR)
        x = rng.uniform(-1, 1, m // hold + 2).repeat(hold)[:m]
        env = np.exp(-decay * np.arange(m) / SR)
        if swell:
            env = np.sin(np.linspace(0, np.pi, m))
        return (x * env).astype(np.float32)

    # music: 150 bpm, tense minor loop, switches to bright major after rescue
    e16 = 60 / 150 / 4
    tense = [(110, [440, 523.25, 659.25]), (110, [440, 523.25, 659.25]),
             (87.31, [349.23, 440, 523.25]), (98, [392, 493.88, 587.33])]
    bright = [(130.81, [523.25, 659.25, 783.99]), (98, [392, 493.88, 587.33]),
              (110, [440, 523.25, 659.25]), (87.31, [349.23, 440, 523.25])]
    bar = 0
    while bar * 16 * e16 < DUR:
        tb = bar * 16 * e16
        root, ch = (bright if tb >= S6 - 0.5 else tense)[bar % 4]
        for s in range(16):
            t0 = tb + s * e16
            add(mus, t0, tone(ch[s % 3] * (2 if (s // 4) % 2 else 1), e16 * 0.9, duty=0.125, decay=14), 0.04)
            if s % 2 == 0:
                add(mus, t0, tone(root * (2 if s % 4 == 2 else 1), e16 * 1.8, duty=0.5, decay=8), 0.06)
                add(mus, t0, noise(0.02, decay=150), 0.03)
            if s % 4 == 0:
                add(mus, t0, tone(130, 0.11, 'tri', decay=22, f_end=45), 0.28)
            if s % 8 == 4:
                add(mus, t0, noise(0.12, decay=28, hold=4), 0.12)
        bar += 1
    tt = np.arange(n) / SR
    g = np.ones(n, np.float32)
    g[(tt >= CRACK) & (tt < 1.3)] = 0.12
    g[(tt >= BLACKOUT) & (tt < S5)] = 0.2
    g *= np.clip((DUR - tt) / 1.0, 0, 1)
    mus *= g

    for tc, line in char_times():
        add(sfx, tc, tone(1150 if line == 1 else 1450, 0.025, decay=60), 0.06)
    add(sfx, CRACK, noise(0.3, decay=16, hold=2), 0.4)
    add(sfx, CRACK, tone(2600, 0.07, decay=40, f_end=900), 0.15)
    add(sfx, CRACK, tone(90, 0.35, 'tri', decay=8, f_end=40), 0.35)
    add(sfx, 0.7, noise(1.9, decay=1.3), 0.13)
    t0 = 0.8
    while t0 < 4.8:
        add(sfx, t0, tone(880, 0.12, decay=4), 0.07)
        add(sfx, t0 + 0.25, tone(660, 0.12, decay=4), 0.07)
        t0 += 0.5
    t0 = 14.4
    while t0 < BLACKOUT:
        add(sfx, t0, tone(880, 0.1, decay=4), 0.045)
        t0 += 0.6
    for st in (S2, S3, S4):
        add(sfx, st - 0.05, noise(0.25, swell=True, hold=3), 0.08)
        add(sfx, st, tone(700, 0.12, decay=10, f_end=1400), 0.06)
    add(sfx, S2 + 0.1, tone(180, 2.6, 'tri', decay=0.3, f_end=420), 0.07)
    add(sfx, EXHALE, noise(0.6, swell=True, hold=2), 0.14)
    for bx, off in BUB:
        k = 0
        while True:
            tp = S3 + 0.3 + off + 0.62 + k * 0.7
            if tp >= S4:
                break
            add(sfx, tp, tone(1800, 0.03, decay=50, f_end=2800), 0.05)
            k += 1
    add(sfx, SWELL, tone(140, 1.8, 'tri', decay=0.4, f_end=260), 0.09)
    hb, iv = S4, 0.75
    while hb < BLACKOUT:
        add(sfx, hb, tone(70, 0.12, 'tri', decay=18, f_end=40), 0.4)
        add(sfx, hb + 0.14, tone(65, 0.12, 'tri', decay=18, f_end=40), 0.28)
        iv = max(0.38, iv * 0.9)
        hb += iv
    add(sfx, BLACKOUT, tone(55, 1.6, 'tri', decay=0.8), 0.2)
    for tp in (PULL0, PULL1):
        add(sfx, tp, noise(0.45, swell=True, hold=3), 0.12)
    add(sfx, HATCH, tone(110, 0.4, decay=6), 0.14)
    add(sfx, HATCH, noise(0.2, decay=20, hold=20), 0.22)
    add(sfx, REP0, noise(1.2, swell=True), 0.07)
    add(sfx, REP0, tone(300, 1.2, duty=0.25, decay=0.3, f_end=900), 0.04)
    hb = REP1
    while hb < S7:
        add(sfx, hb, tone(70, 0.12, 'tri', decay=18, f_end=40), 0.3)
        add(sfx, hb + 0.15, tone(65, 0.12, 'tri', decay=18, f_end=40), 0.2)
        hb += 0.85
    for k, f in enumerate([523.25, 659.25, 783.99, 1046.5, 1318.5]):
        add(sfx, S6 + 0.05 + k * 0.08, tone(f, 0.25, decay=6, duty=0.25), 0.09)
    add(sfx, S7 - 0.05, noise(0.3, swell=True, hold=3), 0.08)
    add(sfx, SELECT_T, tone(988, 0.07, decay=20), 0.09)
    add(sfx, SELECT_T + 0.07, tone(1318.5, 0.12, decay=12), 0.09)

    out = mus + sfx
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
