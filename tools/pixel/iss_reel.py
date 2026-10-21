#!/usr/bin/env python3
"""Retro pixel explainer reel: Why do astronauts float on the ISS?

Frames are drawn at 180x320 and scaled 6x (nearest neighbour) to 1080x1920.
Usage:
  python3 iss_reel.py render out.mp4
  python3 iss_reel.py sheet sheet.png 1.5,5,6.7,...
"""
import math, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw

W, H, FPS = 180, 320, 30
DUR = 43.5
NF = int(round(DUR * FPS))
SR = 44100


def hx(s):
    s = s.lstrip('#')
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


INK = hx('05060f'); BG = hx('0b1030'); WHITE = hx('f2f2f2'); CYAN = hx('3ee6ff')
YELLOW = hx('ffd23f'); RED = hx('ff3b5c'); GREEN = hx('5dff7a'); GREY = hx('8a94b8')
DGREY = hx('3a4166'); ORANGE = hx('ff9a3c'); BLUEW = hx('6fd3ff')
COLS = {'cyan': CYAN, 'yellow': YELLOW, 'red': RED, 'green': GREEN, 'white': WHITE}


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


# ---------------------------------------------------------------- pixel font
FONT = {
    'A': [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    'B': ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."],
    'C': [".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."],
    'D': ["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."],
    'E': ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
    'F': ["#####", "#....", "#....", "####.", "#....", "#....", "#...."],
    'G': [".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".####"],
    'H': ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    'I': [".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."],
    'J': ["..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."],
    'K': ["#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"],
    'L': ["#....", "#....", "#....", "#....", "#....", "#....", "#####"],
    'M': ["#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"],
    'N': ["#...#", "#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#"],
    'O': [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    'P': ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
    'Q': [".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"],
    'R': ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
    'S': [".####", "#....", "#....", ".###.", "....#", "....#", "####."],
    'T': ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    'U': ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    'V': ["#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."],
    'W': ["#...#", "#...#", "#...#", "#.#.#", "#.#.#", "#.#.#", ".#.#."],
    'X': ["#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"],
    'Y': ["#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."],
    'Z': ["#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"],
    '0': [".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."],
    '1': ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
    '2': [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
    '3': ["####.", "....#", "....#", ".###.", "....#", "....#", "####."],
    '4': ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
    '5': ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."],
    '6': ["..##.", ".#...", "#....", "####.", "#...#", "#...#", ".###."],
    '7': ["#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."],
    '8': [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."],
    '9': [".###.", "#...#", "#...#", ".####", "....#", "...#.", ".##.."],
    '.': [".....", ".....", ".....", ".....", ".....", ".##..", ".##.."],
    ',': [".....", ".....", ".....", ".....", ".##..", "..#..", ".#..."],
    '?': [".###.", "#...#", "....#", "...#.", "..#..", ".....", "..#.."],
    '!': ["..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#.."],
    ':': [".....", ".##..", ".##..", ".....", ".##..", ".##..", "....."],
    '%': ["##...", "##..#", "...#.", "..#..", ".#...", "#..##", "...##"],
    '-': [".....", ".....", ".....", "#####", ".....", ".....", "....."],
    "'": ["..#..", "..#..", ".#...", ".....", ".....", ".....", "....."],
    '/': [".....", "....#", "...#.", "..#..", ".#...", "#....", "....."],
    '=': [".....", ".....", "#####", ".....", "#####", ".....", "....."],
    '+': [".....", "..#..", "..#..", "#####", "..#..", "..#..", "....."],
    '~': [".....", ".....", ".#...", "#.#.#", "...#.", ".....", "....."],
    '[': [".###.", ".#...", ".#...", ".#...", ".#...", ".#...", ".###."],
    ']': [".###.", "...#.", "...#.", "...#.", "...#.", "...#.", ".###."],
    '▶': [".#...", ".##..", ".###.", ".####", ".###.", ".##..", ".#..."],
    '█': ["#####"] * 7,
    '✓': [".....", "....#", "....#", "...#.", "#.#..", ".#...", "....."],
}
for _k, _v in FONT.items():
    assert len(_v) == 7 and all(len(r) == 5 for r in _v), _k
GLYPH = {ch: [(x, y) for y, row in enumerate(rows) for x, c in enumerate(row) if c == '#']
         for ch, rows in FONT.items()}


def text(d, x, y, s, col, sc=1):
    for i, ch in enumerate(s):
        pts = GLYPH.get(ch)
        if not pts:
            continue
        ox = x + i * 6 * sc
        if sc == 1:
            d.point([(ox + px, y + py) for px, py in pts], fill=col)
        else:
            for px, py in pts:
                d.rectangle([ox + px * sc, y + py * sc, ox + px * sc + sc - 1, y + py * sc + sc - 1], fill=col)


def tw(s, sc=1):
    return (len(s) * 6 - 1) * sc


# ---------------------------------------------------------------- timeline
CPS = 30.0  # typed characters per second
CAPS = [  # start, line1, line2, colour of line2, scale
    (0.30, "HE'S 400 KM ABOVE EARTH.", "WHY IS HE FLOATING?", 'cyan', 1),
    (3.60, "MOST PEOPLE SAY:", "THERE'S NO GRAVITY.", 'cyan', 1),
    (6.60, "", "WRONG.", 'red', 2),
    (8.40, "GRAVITY AT 400 KM:", "STILL ALMOST 90%!", 'yellow', 1),
    (12.70, "SO WHY DOESN'T THE ISS", "CRASH DOWN?", 'cyan', 1),
    (15.00, "IT DOES FALL.", "ALL THE TIME.", 'yellow', 1),
    (17.70, "BUT IT ALSO FLIES", "SIDEWAYS, LIKE THIS:", 'cyan', 1),
    (21.00, "FASTER = IT LANDS", "FARTHER AWAY...", 'cyan', 1),
    (24.00, "AT 28,000 KM/H, EARTH", "CURVES AWAY UNDER IT.", 'yellow', 1),
    (26.60, "IT FALLS... BUT KEEPS", "MISSING THE GROUND.", 'cyan', 1),
    (29.80, "HE FALLS WITH THE ISS.", "SAME SPEED, SAME TIME.", 'cyan', 1),
    (32.40, "NOTHING PUSHES ON HIM", "= HE FLOATS.", 'green', 1),
    (35.20, "1 LAP = 92 MINUTES.", "ABOUT 16 SUNRISES A DAY.", 'yellow', 1),
    (39.20, "BE HONEST,", "YOU THOUGHT...", 'cyan', 1),
]
SCENES = [(0.0, 'intro'), (8.0, 'altitude'), (12.5, 'falling'), (17.5, 'cannon'),
          (29.5, 'freefall'), (35.0, 'laps'), (39.0, 'outro')]
IRIS_AT = [8.0, 17.5, 29.5, 35.0, 39.0]
IRIS_HALF = 0.22
WRONG_T = 6.6
CLIMB = (0.3, 3.0)          # altitude scene: start, duration (local)
STATUS_FALL_T = 15.0
FLOAT_T = 32.4
OPT1 = "[ ] FREE FALL"
OPT2 = "[ ] NO GRAVITY"
OPT_T1 = 40.35
OPT_T2 = OPT_T1 + len(OPT1) / CPS + 0.15
SELECT_T = OPT_T2 + len(OPT2) / CPS + 0.25


def cap_line_times(c):
    st, l1, l2 = c[0], c[1], c[2]
    t2 = st + len(l1) / CPS + (0.12 if l1 else 0.0)
    return st, t2


def char_times():
    out = []
    for c in CAPS:
        t1, t2 = cap_line_times(c)
        out += [(t1 + i / CPS, 1) for i, ch in enumerate(c[1]) if ch != ' ']
        out += [(t2 + i / CPS, 2) for i, ch in enumerate(c[2]) if ch != ' ']
    out += [(OPT_T1 + i / CPS, 1) for i, ch in enumerate(OPT1) if ch != ' ']
    out += [(OPT_T2 + i / CPS, 2) for i, ch in enumerate(OPT2) if ch != ' ']
    return out


def scene_at(t):
    name, st = SCENES[0][1], 0.0
    for s, n in SCENES:
        if t >= s:
            name, st = n, s
    return name, t - st


# ---------------------------------------------------------------- sprites
def outline_rgba(a):
    m = a[:, :, 3] > 0
    p = np.pad(m, 1)
    dil = p[1:-1, 1:-1] | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]
    e = dil & ~m
    a[e, :3] = INK
    a[e, 3] = 255
    return a


def sprite(rows, pal):
    h, w = len(rows), len(rows[0])
    assert all(len(r) == w for r in rows), rows
    a = np.zeros((h + 2, w + 2, 4), np.uint8)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch != '.':
                a[y + 1, x + 1, :3] = pal[ch]
                a[y + 1, x + 1, 3] = 255
    return Image.fromarray(outline_rgba(a), 'RGBA')


ISS_PAL = {'P': hx('1c3a8c'), 'p': hx('3f74d9'), 'T': hx('c2c8dc'), 'M': hx('f0f2f7'),
           'm': hx('98a2c2'), 'R': hx('e2e8f2')}
ISS = sprite([
    "...............................",
    ".PpP.PpP...............PpP.PpP.",
    ".PpP.PpP...............PpP.PpP.",
    ".PpP.PpP......mMm......PpP.PpP.",
    ".PpP.PpP......mMm......PpP.PpP.",
    ".PpP.PpP.....RmMmR.....PpP.PpP.",
    "TTTTTTTTTTTTTTTMTTTTTTTTTTTTTTT",
    ".PpP.PpP.....RmMmR.....PpP.PpP.",
    ".PpP.PpP......mMm......PpP.PpP.",
    ".PpP.PpP......mMm......PpP.PpP.",
    ".PpP.PpP.....mmMmm.....PpP.PpP.",
    ".PpP.PpP...............PpP.PpP.",
    "...............................",
], ISS_PAL)
ISS_MINI = sprite(["Pp.M.pP", "TTTMTTT", "Pp.M.pP"], ISS_PAL)


def astronaut(t):
    im = Image.new('RGBA', (34, 42), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    A = lambda c: c + (255,)
    SK, HA = A(hx('f0bf8a')), A(hx('3b2414'))
    SH, SH2 = A(hx('2f62d6')), A(hx('234aa6'))
    PA, SO, EY, MO = A(hx('9c8a5e')), A(hx('f4f4f4')), A(hx('15151f')), A(hx('b5654c'))
    s1, s2 = math.sin(t * 1.7), math.sin(t * 1.7 + 1.3)
    legs = [((15, 25), (11 + s2 * 0.8, 31), (13 + s2, 36)),
            ((19, 25), (23 - s2 * 0.8, 30), (21, 36 + s2 * 0.6))]
    for hip, knee, foot in legs:
        d.line([hip, knee], fill=PA, width=4)
        d.line([knee, foot], fill=PA, width=3)
        d.ellipse([knee[0] - 2, knee[1] - 2, knee[0] + 1, knee[1] + 1], fill=PA)
        d.rectangle([foot[0] - 1, foot[1] - 1, foot[0] + 1, foot[1] + 1], fill=SO)
    d.rectangle([13, 15, 21, 26], fill=SH)
    d.rectangle([19, 16, 21, 26], fill=SH2)
    arms = [((13, 16), (8, 19 - s1 * 1.5), (4, 14 - s1 * 2.2)),
            ((21, 16), (26, 18 + s1 * 1.5), (30, 13 + s1 * 2.2))]
    for sh, el, hd in arms:
        d.line([sh, el], fill=SH, width=3)
        d.line([el, hd], fill=SK, width=2)
        d.rectangle([hd[0] - 1, hd[1] - 1, hd[0] + 1, hd[1] + 1], fill=SK)
    d.rectangle([16, 13, 18, 15], fill=SK)
    d.ellipse([12, 4, 22, 15], fill=SK)
    d.pieslice([12, 3, 22, 14], 180, 360, fill=HA)
    d.rectangle([12, 7, 13, 10], fill=HA)
    d.rectangle([21, 7, 22, 9], fill=HA)
    d.point([(15, 10), (19, 10)], fill=EY)
    d.point([(16, 12), (17, 12), (18, 12)], fill=MO)
    a = np.array(im)
    return Image.fromarray(outline_rgba(a), 'RGBA')


def arrow_down(d, x, y0, length, col):
    hb = y0 + length - 4
    d.rectangle([x - 2, y0 - 1, x + 1, hb], fill=INK)
    d.polygon([(x - 4, hb - 1), (x + 3, hb - 1), (x - 0.5, y0 + length + 1.5)], fill=INK)
    d.rectangle([x - 1, y0, x, hb], fill=col)
    d.polygon([(x - 3, hb), (x + 2, hb), (x - 0.5, y0 + length)], fill=col)


# ---------------------------------------------------------------- globe
def _noise_tex(seed, w=256, h=128, octaves=((6, 1.0), (12, 0.5), (24, 0.25), (48, 0.12))):
    r = np.random.default_rng(seed)
    tex = np.zeros((h, w), np.float32)
    for cells, amp in octaves:
        gw, gh = cells, max(3, cells // 2 + 1)
        g = r.random((gh, gw)).astype(np.float32)
        g3 = np.concatenate([g, g, g], axis=1)
        im = Image.fromarray((g3 * 255).astype(np.uint8), 'L').resize((w * 3, h), Image.BICUBIC)
        tex += amp * (np.asarray(im, np.float32)[:, w:2 * w] / 255.0)
    tex -= tex.min()
    tex /= tex.max()
    return tex


LAND = _noise_tex(11)
CLOUD = _noise_tex(5, octaves=((16, 1.0), (32, 0.6), (64, 0.35)))
LAND_T = float(np.quantile(LAND, 0.6))
HIGH_T = float(np.quantile(LAND, 0.93))
CLOUD_T = float(np.quantile(CLOUD, 0.88))
G = {k: np.array(hx(v), np.uint8) for k, v in dict(
    ocean='2d6fd8', ocean2='1f50a8', ocean_n='0f1f4f', land='47a84f', land2='2f7a3c',
    land_n='12301f', high='a08850', ice='e8f1ff', cloud='f4f7ff', cloud_n='2b3558',
    atm='7fd8ff').items()}
BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], np.float32) / 16.0


def _sample(tex, u, v):
    """Bilinear lookup (wraps in u) so coastlines stay smooth on big globes."""
    th, twd = tex.shape
    u0, v0 = np.floor(u).astype(int), np.floor(v).astype(int)
    fu, fv = u - u0, v - v0
    u0 %= twd
    u1 = (u0 + 1) % twd
    v0c, v1c = np.clip(v0, 0, th - 1), np.clip(v0 + 1, 0, th - 1)
    return (tex[v0c, u0] * (1 - fu) * (1 - fv) + tex[v0c, u1] * fu * (1 - fv)
            + tex[v1c, u0] * (1 - fu) * fv + tex[v1c, u1] * fu * fv)


def draw_globe(arr, cx, cy, r, rot, tilt=0.35, L=(-0.6, -0.45, 0.66)):
    hh, ww = arr.shape[:2]
    x0, x1 = max(0, int(cx - r - 3)), min(ww, int(cx + r + 4))
    y0, y1 = max(0, int(cy - r - 3)), min(hh, int(cy + r + 4))
    if x0 >= x1 or y0 >= y1:
        return
    ys, xs = np.mgrid[y0:y1, x0:x1]
    nx = (xs + 0.5 - cx) / r
    ny = (ys + 0.5 - cy) / r
    d2 = nx * nx + ny * ny
    inside = d2 <= 1.0
    nz = np.sqrt(np.clip(1 - d2, 0, 1))
    ct, st = math.cos(tilt), math.sin(tilt)
    ny2 = ny * ct - nz * st
    nz2 = ny * st + nz * ct
    lat = np.arcsin(np.clip(-ny2, -1, 1))
    lon = np.arctan2(nx, nz2) + rot
    th, twd = LAND.shape
    v = (0.5 - lat / np.pi) * (th - 1)
    hgt = _sample(LAND, ((lon / (2 * np.pi)) % 1.0) * twd, v)
    cl = _sample(CLOUD, (((lon - rot * 0.4) / (2 * np.pi)) % 1.0) * twd, v)
    Lv = np.array(L, np.float32)
    Lv /= np.linalg.norm(Lv)
    lam = nx * Lv[0] + ny * Lv[1] + nz * Lv[2]
    b = BAYER[ys % 4, xs % 4]
    day = lam > (b - 0.5) * 0.25
    lit = lam > 0.35 + (b - 0.5) * 0.3
    land = hgt > LAND_T
    col = np.empty(nx.shape + (3,), np.uint8)
    col[:] = G['ocean2']
    col[lit] = G['ocean']
    col[land] = G['land2']
    col[land & lit] = G['land']
    col[hgt > HIGH_T] = G['high']
    col[np.abs(lat) > 1.22] = G['ice']
    col[cl > CLOUD_T] = G['cloud']
    night = ~day
    col[night] = G['ocean_n']
    col[night & land] = G['land_n']
    col[night & (cl > CLOUD_T)] = G['cloud_n']
    sub = arr[y0:y1, x0:x1]
    sub[inside] = col[inside]
    dd = np.sqrt(d2)
    rim = (dd > 1.0) & (dd <= 1.0 + 1.3 / r)
    rl = (nx * Lv[0] + ny * Lv[1]) / np.maximum(dd, 1e-6)
    sub[rim & (rl > -0.3)] = G['atm']


_rng = np.random.default_rng(3)
STARS = [(int(_rng.integers(0, W)), int(_rng.integers(0, H)), float(_rng.random() * 6.28),
          int(_rng.integers(0, 3))) for _ in range(90)]


def draw_stars(arr, t):
    for x, y, ph, b in STARS:
        v = 0.5 + 0.5 * math.sin(t * 2.0 + ph)
        if b == 2:
            c = WHITE if v > 0.3 else GREY
        elif b == 1:
            c = GREY if v > 0.5 else DGREY
        else:
            c = DGREY
        arr[y, x] = c


def space(t):
    arr = np.empty((H, W, 3), np.uint8)
    arr[:] = BG
    draw_stars(arr, t)
    return arr


# ---------------------------------------------------------------- cabin (drawn at half resolution)
CW, CH = 90, 160
BACK = (27, 62, 62, 108)
CEIL, FLOOR, LWALL, RWALL, BACKW = hx('414c7d'), hx('252c55'), hx('323b6a'), hx('2c3463'), hx('39437a')
SEAM, EDGE, LIGHT, RAIL, FRAME = hx('222951'), hx('1a2045'), hx('fff3c4'), hx('c8b25a'), hx('b8c0dc')


def lerp_rect(a, b, k):
    return tuple(a[i] + (b[i] - a[i]) * k for i in range(4))


def draw_module(d):
    O = (-1, -1, CW, CH)
    ox0, oy0, ox1, oy1 = O
    bx0, by0, bx1, by1 = BACK
    d.polygon([(ox0, oy0), (ox1, oy0), (bx1, by0), (bx0, by0)], fill=CEIL)
    d.polygon([(ox0, oy1), (ox1, oy1), (bx1, by1), (bx0, by1)], fill=FLOOR)
    d.polygon([(ox0, oy0), (bx0, by0), (bx0, by1), (ox0, oy1)], fill=LWALL)
    d.polygon([(ox1, oy0), (bx1, by0), (bx1, by1), (ox1, oy1)], fill=RWALL)
    d.rectangle(BACK, fill=BACKW)
    for fx in (1 / 3, 2 / 3):
        xo, xi = ox0 + (ox1 - ox0) * fx, bx0 + (bx1 - bx0) * fx
        d.line([(xo, oy0), (xi, by0)], fill=SEAM)
        d.line([(xo, oy1), (xi, by1)], fill=SEAM)
    for fy in (1 / 3, 2 / 3):
        yo, yi = oy0 + (oy1 - oy0) * fy, by0 + (by1 - by0) * fy
        d.line([(ox0, yo), (bx0, yi)], fill=SEAM)
        d.line([(ox1, yo), (bx1, yi)], fill=SEAM)
    for k in (0.3, 0.62):
        r = lerp_rect(O, BACK, k)
        d.rectangle(r, outline=SEAM)
        cx, hw = (r[0] + r[2]) / 2, (r[2] - r[0]) * 0.18
        d.rectangle([cx - hw, r[1] - 2, cx + hw, r[1] - 1], fill=LIGHT)
    for p, q in [((ox0, oy0), (bx0, by0)), ((ox1, oy0), (bx1, by0)),
                 ((ox0, oy1), (bx0, by1)), ((ox1, oy1), (bx1, by1))]:
        d.line([p, q], fill=EDGE)
    d.rectangle(BACK, outline=EDGE)
    d.line([(0, 76), (bx0 - 1, 83)], fill=RAIL)
    d.line([(0, 77), (bx0 - 1, 84)], fill=hx('7d6f36'))
    d.line([(CW - 1, 76), (bx1 + 1, 83)], fill=RAIL)
    d.line([(CW - 1, 77), (bx1 + 1, 84)], fill=hx('7d6f36'))
    d.polygon([(3, 96), (11, 98), (11, 108), (3, 107)], fill=hx('d9822b'), outline=INK)
    d.line([(7, 97), (7, 107)], fill=hx('a85f1c'))
    d.polygon([(79, 58), (86, 54), (86, 65), (79, 68)], fill=hx('6b7390'), outline=INK)
    d.polygon([(80, 59), (85, 56), (85, 64), (80, 66)], fill=hx('5ac8e8'))


def draw_window(s, t):
    cx, cy, r = 36, 75, 8
    size = 2 * r + 1
    tmp = np.empty((size, size, 3), np.uint8)
    tmp[:] = hx('03040c')
    for sx, sy in [(3, 4), (11, 2), (6, 9), (14, 6), (2, 12), (9, 5)]:
        tmp[sy, sx] = WHITE
    draw_globe(tmp, r + 2, r + 21, 18, rot=0.4 + t * 0.12, tilt=1.25, L=(-0.5, -0.6, 0.6))
    yy, xx = np.mgrid[0:size, 0:size]
    m = (xx - r) ** 2 + (yy - r) ** 2 <= r * r
    arr = np.array(s)
    sub = arr[cy - r:cy + r + 1, cx - r:cx + r + 1]
    sub[m] = tmp[m]
    s = Image.fromarray(arr)
    d = ImageDraw.Draw(s)
    d.ellipse([cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1], outline=FRAME)
    d.ellipse([cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2], outline=EDGE)
    return s


def scene_cabin(t, tl, mode):
    s = Image.new('RGB', (CW, CH), BACKW)
    d = ImageDraw.Draw(s)
    draw_module(d)
    s = draw_window(s, t)
    d = ImageDraw.Draw(s)
    # floating pen
    px, py, ang = 18, 114 + 2 * math.sin(t * 1.1), t * 0.8
    ex, ey = 2.6 * math.cos(ang), 2.6 * math.sin(ang)
    d.line([(px - ex, py - ey), (px + ex, py + ey)], fill=YELLOW)
    d.point((round(px + ex), round(py + ey)), fill=RED)
    # floating water ball
    wx, wy = 74, 100 + 1.5 * math.sin(t * 1.6 + 1)
    d.ellipse([wx - 1, wy - 1, wx + 1, wy + 1], fill=BLUEW)
    d.point((round(wx), round(wy) - 1), fill=WHITE)
    # astronaut
    a = astronaut(t)
    ax = 33 + round(1.2 * math.sin(t * 0.7))
    ay = 85 + round(2.5 * math.sin(t * 1.3))
    s.paste(a, (ax, ay), a)
    if mode == 'freefall':
        if t < FLOAT_T and tl > 0.3:
            off = int((t * 10) % 4)
            arrow_down(d, 78, 88 + off, 14, YELLOW)
            arrow_down(d, 13, 88 + off, 14, YELLOW)
        elif t >= FLOAT_T:
            cx, cy = ax + 17, ay + 20
            for i in range(6):
                an = i * math.pi / 3 + t * 1.5
                sx, sy = cx + 22 * math.cos(an), cy + 22 * math.sin(an)
                on = int(t * 8 + i) % 2 == 0
                c = GREEN if on else WHITE
                d.point([(sx, sy), (sx - 1, sy), (sx + 1, sy), (sx, sy - 1), (sx, sy + 1)], fill=c)
    big = s.resize((W, H), Image.NEAREST)
    if mode == 'outro':
        arr = np.asarray(big).astype(np.float32)
        arr = arr * 0.42 + np.array(INK, np.float32) * 0.58
        big = Image.fromarray(arr.astype(np.uint8))
    return big


# ---------------------------------------------------------------- space scenes
R_E = 6371.0
ALT_KM = 400


def grav(h):
    return (R_E / (R_E + h)) ** 2


def climb_p(tl):
    return ease((tl - CLIMB[0]) / CLIMB[1])


def space_arc(t):
    arr = space(t)
    draw_globe(arr, 90, 610, 370, rot=5.3 + t * 0.006, tilt=1.3)
    img = Image.fromarray(arr)
    img.paste(ISS, (90 - 16, 150 - 7), ISS)
    return img


def scene_altitude(t, tl):
    img = space_arc(t)
    d = ImageDraw.Draw(img)
    p = climb_p(tl)
    my = 237 - p * (237 - 163)
    for y in range(int(my) + 4, 240, 3):
        d.point((90, y), fill=GREY)
    arrow_down(d, 101, int(my) - 3, int(round(22 * grav(ALT_KM * p))), RED)
    d.polygon([(90, my - 3), (93, my), (90, my + 3), (87, my)], fill=YELLOW, outline=INK)
    d.point((90, round(my)), fill=WHITE)
    return img


def scene_falling(t, tl):
    img = space_arc(t)
    d = ImageDraw.Draw(img)
    arrow_down(d, 91, 158, 9, RED)
    if t >= STATUS_FALL_T:
        for i, sx in enumerate((82, 90, 98)):
            ph = (t * 2.5 + i * 0.37) % 1.0
            y = int(140 - ph * 9)
            d.line([(sx, y), (sx, y + 2)], fill=WHITE)
    rr = int(42 * ease_out((tl - 0.2) / 0.5))
    if rr > 2:
        crop = img.crop((90 - 21, 150 - 21, 90 + 22, 150 + 22)).resize((86, 86), Image.NEAREST)
        mask = Image.new('L', (86, 86), 0)
        ImageDraw.Draw(mask).ellipse([43 - rr, 43 - rr, 43 + rr, 43 + rr], fill=255)
        img.paste(crop, (90 - 43, 150 - 43), mask)
        d = ImageDraw.Draw(img)
        d.ellipse([90 - rr, 150 - rr, 90 + rr, 150 + rr], outline=CYAN)
        d.ellipse([90 - rr - 1, 150 - rr - 1, 90 + rr + 1, 150 + rr + 1], outline=WHITE)
        d.ellipse([90 - rr - 2, 150 - rr - 2, 90 + rr + 2, 150 + rr + 2], outline=WHITE)
        d.ellipse([90 - rr - 3, 150 - rr - 3, 90 + rr + 3, 150 + rr + 3], outline=INK)
    return img


# Newton's cannon
CAN_C = (90.0, 190.0)
CAN_R = 46.0
CAN_R0 = 69.5
ORBIT_T = 3.2
VC = 2 * math.pi * CAN_R0 / ORBIT_T
GM = VC * VC * CAN_R0
SIM_DT = 1 / 600
SHOTS = [(1.9, 12 / 28, "12,000"), (4.1, 20 / 28, "20,000"), (6.9, 1.0, "28,000")]
CANNON_T0 = 17.5


def simulate(frac, tmax=6.0):
    x, y, vx, vy = 0.0, -CAN_R0, VC * frac, 0.0
    pts, t = [(x, y)], 0.0
    while t < tmax:
        r3 = math.hypot(x, y) ** 3
        vx -= GM * x / r3 * SIM_DT
        vy -= GM * y / r3 * SIM_DT
        x += vx * SIM_DT
        y += vy * SIM_DT
        t += SIM_DT
        pts.append((x, y))
        if math.hypot(x, y) <= CAN_R:
            return np.array(pts), t
    return np.array(pts), None


TRAJ = [simulate(f) for _, f, _ in SHOTS]


def scene_cannon(t, tl):
    arr = space(t)
    draw_globe(arr, CAN_C[0], CAN_C[1], CAN_R, rot=3.3, tilt=0.35)
    img = Image.fromarray(arr)
    d = ImageDraw.Draw(img)
    d.polygon([(77, 148), (90, 124), (103, 148)], fill=hx('6f6680'), outline=INK)
    d.polygon([(85, 133), (90, 124), (95, 133), (92, 131), (90, 134), (88, 131)], fill=WHITE)
    latest = max([i for i, s in enumerate(SHOTS) if tl >= s[0]], default=-1)
    for i, (tf, frac, _) in enumerate(SHOTS):
        tau = tl - tf
        if tau < 0:
            continue
        pts, crash = TRAJ[i]
        idx = min(len(pts) - 1, int(tau / SIM_DT))
        if i == 2:
            trail_col = CYAN if tau >= ORBIT_T else YELLOW
        else:
            trail_col = YELLOW if i == latest else GREY
        tr = pts[:idx:14]
        d.point([(CAN_C[0] + x, CAN_C[1] + y) for x, y in tr], fill=trail_col)
        bx, by = CAN_C[0] + pts[idx][0], CAN_C[1] + pts[idx][1]
        if crash is not None and tau >= crash:
            k = tau - crash
            if k < 0.5:
                rad = 1 + k * 10
                d.ellipse([bx - rad, by - rad, bx + rad, by + rad], outline=ORANGE if k < 0.25 else GREY)
            d.point([(bx, by), (bx + 1, by)], fill=ORANGE)
        else:
            d.rectangle([bx - 1, by - 1, bx + 1, by + 1], fill=YELLOW)
            d.point((bx, by), fill=WHITE)
        if tau < 0.6:
            for j in range(3):
                sx = 86 - tau * 14 - j * 3
                sy = 118 - tau * 10 + j
                rad = 1 + tau * 4
                d.ellipse([sx - rad, sy - rad, sx + rad, sy + rad], fill=GREY if tau > 0.15 else WHITE)
    # cannon on top of the mountain
    d.rectangle([84, 122, 87, 124], fill=hx('7a5a3a'), outline=INK)
    d.rectangle([82, 119, 89, 122], fill=hx('5b6380'), outline=INK)
    if latest >= 0 and tl - SHOTS[latest][0] < 0.12:
        d.rectangle([90, 119, 93, 122], fill=WHITE)
    return img


# accelerating lap time-lapse
LAP_D = [0.6 * 0.84 ** k for k in range(16)]
LAP_CUM = np.concatenate([[0.0], np.cumsum(LAP_D)])
LAPS_T0 = 35.0
LAP_START = 0.25


def laps_progress(tl):
    tau = tl - LAP_START
    if tau <= 0:
        return 0.0
    if tau >= LAP_CUM[-1]:
        return 16 + (tau - LAP_CUM[-1]) / LAP_D[-1]
    k = int(np.searchsorted(LAP_CUM, tau, side='right') - 1)
    return k + (tau - LAP_CUM[k]) / LAP_D[k]


def scene_laps(t, tl):
    arr = space(t)
    sx, sy = 26, 112
    yy, xx = np.mgrid[0:H, 0:W]
    dist = np.hypot(xx - sx, yy - sy)
    glow = (dist <= 10) & (dist > 6) & (((xx + yy) % 2) == 0)
    arr[glow] = ORANGE
    arr[dist <= 6] = YELLOW
    arr[dist <= 3] = hx('fff6c8')
    cx, cy = 102, 188
    draw_globe(arr, cx, cy, 38, rot=tl * 2.4, tilt=0.4, L=(-0.62, -0.5, 0.6))
    img = Image.fromarray(arr)
    d = ImageDraw.Draw(img)
    a, b, phi = 54, 14, -0.22
    cphi, sphi = math.cos(phi), math.sin(phi)

    def pos(th):
        px, py = a * math.cos(th), b * math.sin(th)
        return cx + px * cphi - py * sphi, cy + px * sphi + py * cphi

    # orbit path: back half is hidden by the globe, front half drawn on top
    front = []
    for k in range(0, 72):
        th = k / 72 * 2 * math.pi
        (front if math.sin(th) > 0 else []).append(pos(th))
        if math.sin(th) <= 0:
            x, y = pos(th)
            if math.hypot(x - cx, y - cy) > 38:
                d.point((x, y), fill=DGREY)
    d.point(front, fill=GREY)
    th = 2 * math.pi * laps_progress(tl) + math.pi / 2
    x, y = pos(th)
    if math.sin(th) > 0 or math.hypot(x - cx, y - cy) > 39:
        img.paste(ISS_MINI, (int(round(x)) - 4, int(round(y)) - 2), ISS_MINI)
    return img


# ---------------------------------------------------------------- UI layers
def panel(d, x, y, parts, border=GREY, extra_w=0):
    n = sum(len(s) for s, _ in parts)
    w = n * 6 - 1 + 6 + extra_w
    d.rectangle([x, y, x + w, y + 12], fill=INK, outline=border)
    xs, cx = [], x + 3
    for s, c in parts:
        xs.append(cx)
        text(d, cx, y + 3, s, c)
        cx += len(s) * 6
    return xs, x + w


def gravity_panel(d, y, g, vcol=YELLOW):
    xs, xe = panel(d, 10, y, [("GRAVITY: ", WHITE), (f"{round(100 * g):>3}%", vcol)], extra_w=63)
    filled = int(round(20 * g))
    for i in range(20):
        bx = 94 + i * 3
        d.rectangle([bx, y + 4, bx + 1, y + 8], fill=GREEN if i < filled else DGREY)


def draw_hud(d, t, name, tl):
    blink = int(t * 4) % 2 == 0
    if name == 'intro' and t >= 3.9:
        wrong = t >= WRONG_T
        xs, _ = panel(d, 10, 72, [("GRAVITY: ", WHITE), ("0%?", RED if wrong else GREY)])
        if wrong:
            d.line([(xs[1] - 1, 78), (xs[1] + 17, 78)], fill=RED)
    elif name == 'altitude':
        p = climb_p(tl)
        h = ALT_KM * p
        panel(d, 10, 72, [("ALTITUDE: ", WHITE), (f"{int(round(h)):>3} KM", CYAN)])
        gravity_panel(d, 87, grav(h), YELLOW if (p < 1 or blink) else WHITE)
    elif name == 'falling':
        gravity_panel(d, 72, grav(ALT_KM))
        if t >= STATUS_FALL_T:
            panel(d, 10, 87, [("STATUS: ", WHITE), ("FALLING", RED if blink else YELLOW)])
    elif name == 'cannon':
        latest = max([i for i, s in enumerate(SHOTS) if tl >= s[0]], default=-1)
        spd = SHOTS[latest][2] + " KM/H" if latest >= 0 else "---"
        panel(d, 10, 72, [("SPEED: ", WHITE), (spd, CYAN)])
        if latest >= 0:
            tau = tl - SHOTS[latest][0]
            crash = TRAJ[latest][1]
            if crash is not None and tau >= crash:
                res, c = "CRASH!", RED
            elif latest == 2 and tau >= ORBIT_T:
                res, c = "ORBIT!", GREEN
            else:
                res, c = "FLYING...", GREY
            panel(d, 10, 87, [("RESULT: ", WHITE), (res, c)])
    elif name == 'freefall':
        if t >= FLOAT_T:
            panel(d, 10, 72, [("STATUS: ", WHITE), ("FLOATING ✓", GREEN)])
            if t >= FLOAT_T + 0.4:
                panel(d, 10, 87, [("WEIGHT FELT: ", WHITE), ("0 KG", CYAN)])
        elif tl > 0.3:
            panel(d, 10, 72, [("STATUS: ", WHITE), ("FREE FALL", YELLOW)])
            for lx, lab in ((144, "HIM"), (14, "ISS")):
                d.rectangle([lx - 2, 162, lx + tw(lab) + 1, 172], fill=INK)
                text(d, lx, 164, lab, YELLOW)
    elif name == 'laps' and tl > 0.15:
        panel(d, 10, 72, [("LAP TIME: ", WHITE), ("92 MIN", CYAN)])
        n = min(16, int(laps_progress(tl)))
        panel(d, 10, 87, [("SUNRISES: ", WHITE), (f"{n:>2}", YELLOW)])
    elif name == 'outro' and t >= OPT_T1 - 0.15:
        d.rectangle([24, 146, 156, 192], fill=INK, outline=WHITE)
        d.rectangle([26, 148, 154, 190], outline=DGREY)
        n1 = clamp(int((t - OPT_T1) * CPS) + 1, 0, len(OPT1)) if t >= OPT_T1 else 0
        n2 = clamp(int((t - OPT_T2) * CPS) + 1, 0, len(OPT2)) if t >= OPT_T2 else 0
        x0 = 90 - tw(OPT2) // 2
        text(d, x0, 158, OPT1[:int(n1)], WHITE)
        sel = t >= SELECT_T
        text(d, x0, 174, OPT2[:int(n2)], (YELLOW if int(t * 3) % 2 == 0 else WHITE) if sel else WHITE)
        if sel:
            text(d, x0 + 6, 174, "▶", YELLOW)


def draw_caption(d, t):
    if t < 0.15:
        return
    x0, y0, x1, y1 = 10, 40, 169, 66
    d.rectangle([x0, y0, x1, y1], fill=INK, outline=WHITE)
    d.rectangle([x0 + 2, y0 + 2, x1 - 2, y1 - 2], outline=DGREY)
    cur = None
    for c in CAPS:
        if t >= c[0]:
            cur = c
    blink = int(t * 3) % 2 == 0
    mid = (x0 + x1 + 1) // 2
    if cur is None:
        if blink:
            text(d, mid - 2, 49, "█", WHITE)
        return
    st, l1, l2, cname, sc = cur
    t1, t2 = cap_line_times(cur)
    n1 = len(l1) if t >= t2 else clamp(int((t - t1) * CPS) + 1, 0, len(l1))
    n2 = clamp(int((t - t2) * CPS) + 1, 0, len(l2)) if t >= t2 else 0
    n1, n2 = int(n1), int(n2)
    if l1:
        ya, yb = 45, 55
        xa = mid - tw(l1) // 2
        text(d, xa, ya, l1[:n1], WHITE)
    else:
        ya, yb = 0, 53 - 7 * sc // 2
    xb = mid - tw(l2, sc) // 2
    text(d, xb, yb, l2[:n2], COLS[cname], sc)
    if blink:
        if n2 > 0 or not l1:
            text(d, xb + n2 * 6 * sc, yb, "█", COLS[cname], sc)
        else:
            text(d, xa + n1 * 6, ya, "█", WHITE)


# ---------------------------------------------------------------- frame
_YY, _XX = np.mgrid[0:H, 0:W]
DIST = np.hypot(_XX - 90, _YY - 180)


def render(t):
    name, tl = scene_at(t)
    if name in ('intro', 'freefall', 'outro'):
        img = scene_cabin(t, tl, name)
    elif name == 'altitude':
        img = scene_altitude(t, tl)
    elif name == 'falling':
        img = scene_falling(t, tl)
    elif name == 'cannon':
        img = scene_cannon(t, tl)
    else:
        img = scene_laps(t, tl)
    arr = np.array(img)
    for b in IRIS_AT:
        if b - IRIS_HALF <= t < b + IRIS_HALF:
            p = abs(t - b) / IRIS_HALF
            rad = int(205 * ease(p) / 4) * 4
            arr[DIST > rad] = INK
    img = Image.fromarray(arr)
    d = ImageDraw.Draw(img)
    draw_hud(d, t, name, tl)
    draw_caption(d, t)
    if WRONG_T <= t < WRONG_T + 0.36:
        k = int((t - WRONG_T) * FPS)
        arr = np.array(img).astype(np.float32)
        if k % 4 < 2:
            arr = arr * 0.7 + np.array(RED, np.float32) * 0.3
        dx = [3, -3, 2, -2, 1, -1, 0, 0, 0, 0, 0][min(k, 10)]
        arr = np.roll(arr, dx, axis=1)
        img = Image.fromarray(arr.astype(np.uint8))
    return img


# ---------------------------------------------------------------- audio
def build_audio(path):
    n = int((DUR + 0.5) * SR)
    out = np.zeros(n, np.float32)
    rng = np.random.default_rng(1)

    def add(t0, sig, vol=1.0):
        i0 = int(t0 * SR)
        if i0 < 0 or i0 >= n:
            return
        seg = sig[: n - i0]
        out[i0:i0 + len(seg)] += seg * vol

    def tone(f, dur, wave_='sq', duty=0.5, decay=6.0, f_end=None, attack=0.004):
        m = int(dur * SR)
        tt = np.arange(m) / SR
        ph = f * tt if f_end is None else np.cumsum(np.geomspace(f, f_end, m)) / SR
        frac = ph % 1.0
        w = np.where(frac < duty, 1.0, -1.0) if wave_ == 'sq' else 4 * np.abs(frac - 0.5) - 1
        env = np.exp(-decay * tt) * np.clip(tt / attack, 0, 1) * np.clip((dur - tt) / 0.01, 0, 1)
        return (w * env).astype(np.float32)

    def noise(dur, decay=20.0, hold=1):
        m = int(dur * SR)
        x = rng.uniform(-1, 1, m // hold + 2).repeat(hold)[:m]
        tt = np.arange(m) / SR
        return (x * np.exp(-decay * tt)).astype(np.float32)

    # music: Am F C G arpeggios, 128 bpm
    e8 = 60 / 128 / 2
    chords = [([220, 261.63, 329.63, 440], 110), ([174.61, 220, 261.63, 349.23], 87.31),
              ([261.63, 329.63, 392, 523.25], 130.81), ([196, 246.94, 293.66, 392], 98)]
    pat = [0, 1, 2, 3, 2, 1, 2, 3]
    bar = 0
    while bar * 8 * e8 < DUR:
        arp, root = chords[bar % 4]
        for st in range(8):
            t0 = (bar * 8 + st) * e8
            add(t0, tone(arp[pat[st]] * 2, e8 * 0.95, duty=0.25, decay=7), 0.055)
            if st % 2 == 1:
                add(t0, noise(0.03, decay=90), 0.025)
        for bt in range(4):
            t0 = (bar * 8 + bt * 2) * e8
            add(t0, tone(root, e8 * 1.9, 'tri', decay=3), 0.16)
            if bt in (0, 2):
                add(t0, tone(120, 0.12, 'tri', decay=25, f_end=45), 0.22)
        bar += 1
    fade = np.clip((DUR - np.arange(n) / SR) / 1.2, 0, 1).astype(np.float32)
    out *= fade

    for tc, line in char_times():
        add(tc, tone(1150 if line == 1 else 1450, 0.028, decay=60), 0.07)
    add(WRONG_T, tone(220, 0.3, decay=3, f_end=110), 0.16)
    add(WRONG_T + 0.18, tone(196, 0.35, decay=3, f_end=90), 0.16)
    for b in IRIS_AT:
        wsh = noise(0.4, decay=0, hold=3)
        wsh *= np.sin(np.linspace(0, np.pi, len(wsh))).astype(np.float32)
        add(b - 0.25, wsh, 0.06)
    add(8.0 + CLIMB[0], tone(300, CLIMB[1], duty=0.25, decay=0.3, f_end=900), 0.025)
    add(12.5 + 0.2, tone(600, 0.14, decay=15, f_end=1300), 0.08)
    for k in range(4):
        add(STATUS_FALL_T + k * 0.12, tone(880 if k % 2 == 0 else 660, 0.1, decay=10), 0.06)
    for i, (tf, _, _) in enumerate(SHOTS):
        add(CANNON_T0 + tf, noise(0.3, decay=12, hold=6), 0.22)
        add(CANNON_T0 + tf, tone(180, 0.2, decay=10, f_end=60), 0.12)
        crash = TRAJ[i][1]
        if crash is not None:
            add(CANNON_T0 + tf + crash, noise(0.3, decay=14, hold=14), 0.24)
    arp = [523.25, 659.25, 783.99, 1046.5]
    for k, f in enumerate(arp):
        add(CANNON_T0 + SHOTS[2][0] + ORBIT_T + k * 0.07, tone(f, 0.18, decay=8), 0.08)
    for k, f in enumerate(arp + [1318.5]):
        add(FLOAT_T + k * 0.09, tone(f, 0.25, decay=6, duty=0.25), 0.09)
    for k in range(1, 17):
        add(LAPS_T0 + LAP_START + LAP_CUM[k], tone(1760, 0.03, decay=70), 0.06)
    add(SELECT_T, tone(988, 0.07, decay=20), 0.09)
    add(SELECT_T + 0.07, tone(1318.5, 0.12, decay=12), 0.09)

    peak = float(np.max(np.abs(out)))
    if peak > 0:
        out *= 0.89 / peak
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
           '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
           '-i', wav,
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
        sheet(sys.argv[2], [float(x) for x in sys.argv[3].split(',')],
              int(sys.argv[4]) if len(sys.argv) > 4 else 6)
    else:
        render_video(sys.argv[2])
