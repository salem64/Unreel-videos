#!/usr/bin/env python3
"""3D-sim style "WHAT IF" short: all the air on Earth vanishes for 5 seconds (street scene).

Own numpy ray tracer (no GPU, no Blender): cut-away Earth with layers, tunnel POV with a 3D cartoon
character, surface scene, smooth HUD + word-pop captions, kokoro narrator voice, music + SFX.
Render: 540x960 traced, upscaled to 1080x1920 with bloom. ~0.3 s/frame on 2 cores.

Usage (from tools/sim3d):
  python3 tts_lines.py air_gone_lines.json /tmp/tunnel_vo          # voice first (durations drive the timeline)
  python3 earth_tunnel.py sheet /tmp/s.png 1,4,7,...  --vo /tmp/tunnel_vo
  python3 earth_tunnel.py render out.mp4 --vo /tmp/tunnel_vo
Reusable pieces for other 3D-sim videos: Cam/rays, star sky, earth_cutaway(), tunnel_pov(), surface_scene(),
character primitives (Char), post(), Overlay (HUD pills, captions, choice cards), audio mix.
"""
import json, math, os, subprocess, sys, wave
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', 'pixel'))
import quiz as Q  # noqa: E402  fonts, tts, sfx, music bed
from iss_reel import _noise_tex, _sample  # noqa: E402  tileable noise + bilinear lookup

W, H, FPS, SR = 1080, 1920, 30, 44100
RW, RH = 540, 960
ASP = RW / RH

VO_DIR = '/tmp/air_vo'
for i, a in enumerate(sys.argv):
    if a == '--vo':
        VO_DIR = sys.argv[i + 1]
LINES = json.load(open(os.path.join(HERE, 'air_gone_lines.json')))['lines']
DURS = json.load(open(os.path.join(VO_DIR, 'durs.json')))
GAP, START0, TAIL = 0.22, 0.3, 2.9
STARTS = []
_t = START0
for d in DURS:
    STARTS.append(_t)
    _t += d + GAP
DUR = STARTS[-1] + DURS[-1] + TAIL
NF = int(round(DUR * FPS))


def L(i):
    return STARTS[i]


def Lend(i):
    return STARTS[i] + DURS[i]


# ----------------------------------------------------------------------------- helpers
def nrm(v):
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def smooth(e0, e1, x):
    k = np.clip((x - e0) / (e1 - e0), 0, 1)
    return k * k * (3 - 2 * k)


def mix(a, b, k):
    k = np.asarray(k)[..., None] if np.ndim(k) else k
    return a * (1 - k) + b * k


def ease(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def C(h):
    h = h.lstrip('#')
    return np.array([int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)], np.float32)


_PY, _PX = np.mgrid[0:RH, 0:RW].astype(np.float32)
SX = ((_PX + 0.5) / RW * 2 - 1) * ASP
SY = 1 - (_PY + 0.5) / RH * 2


class Cam:
    def __init__(self, pos, target, fov=50, roll=0.0, up=(0, 0, 1)):
        self.pos = np.array(pos, np.float32)
        f = np.array(target, np.float32) - self.pos
        f /= np.linalg.norm(f)
        up = np.array(up, np.float32)
        if abs(f @ up) > 0.99:
            up = np.array([0, 1, 0], np.float32)
        r = np.cross(f, up); r /= np.linalg.norm(r)
        u = np.cross(r, f)
        cr, sr = math.cos(roll), math.sin(roll)
        r, u = r * cr + u * sr, u * cr - r * sr
        self.f, self.r, self.u = f, r, u
        self.th = math.tan(math.radians(fov) / 2)

    def rays(self, jitter=None):
        sx, sy = SX, SY
        if jitter is not None:
            sx, sy = sx + jitter[0], sy + jitter[1]
        d = (self.f[None, None] + (sx * self.th)[..., None] * self.r[None, None]
             + (sy * self.th)[..., None] * self.u[None, None])
        return nrm(d.reshape(-1, 3))

    def project(self, P):
        """world point -> full-res pixel (x, y) or None if behind."""
        v = np.array(P, np.float32) - self.pos
        z = v @ self.f
        if z <= 1e-4:
            return None
        x = (v @ self.r) / (z * self.th) / ASP
        y = (v @ self.u) / (z * self.th)
        return ((x + 1) / 2 * W, (1 - y) / 2 * H)


# ----------------------------------------------------------------------------- star sky
def _make_sky():
    rng = np.random.default_rng(9)
    h, w = 1024, 2048
    sky = np.zeros((h, w, 3), np.float32)
    neb = _noise_tex(21, w=512, h=256, octaves=((3, 1.0), (6, 0.5), (12, 0.25)))
    neb = np.asarray(Image.fromarray((neb * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32) / 255
    sky += (neb ** 3)[..., None] * C('3a1d6e')[None, None] * 0.55
    sky += (neb ** 6)[..., None] * C('1d4f8a')[None, None] * 0.6
    n = 5000
    ys, xs = rng.integers(0, h, n), rng.integers(0, w, n)
    b = rng.random(n) ** 3 * 255
    tint = rng.random(n)
    col = np.stack([b * (0.85 + 0.15 * tint), b * 0.92, b * (1.0 - 0.1 * tint)], 1)
    sky[ys, xs] = np.maximum(sky[ys, xs], col)
    return sky


SKY = _make_sky()


def space_bg(D):
    lon = np.arctan2(D[:, 1], D[:, 0])
    lat = np.arcsin(np.clip(D[:, 2], -1, 1))
    u = ((lon / (2 * np.pi) + 0.5) * (SKY.shape[1] - 1)).astype(int)
    v = ((0.5 - lat / np.pi) * (SKY.shape[0] - 1)).astype(int)
    return SKY[v, u]



ROCK = _noise_tex(31, w=256, h=256, octaves=((8, 1.0), (16, 0.6), (32, 0.4), (64, 0.25)))

# ----------------------------------------------------------------------------- 3D cartoon character (ray traced primitives)
SKIN, SHIRT, PANTS, SHOE, HAIR = C('f1c19a'), C('ef4444'), C('2c4a8c'), C('1b1b22'), C('3b2416')


def char_prims(t, scream=1.0, flail=1.0, wave=0.0, grab=None):
    """character in local coords (y up, z toward viewer = -z of view). list of (kind, data, colour)"""
    s1, s2 = math.sin(t * 9 * flail + 0.3), math.sin(t * 7.3 * flail + 1.7)
    P = []
    P.append(('cap', ((0, -0.05, 0), (0, 0.22, 0), 0.16), SHIRT))                     # torso
    P.append(('sph', ((0, 0.48, 0), 0.19), SKIN))                                      # head
    P.append(('sph', ((0, 0.55, 0.05), 0.175), HAIR))                                  # hair cap (behind)
    for sx in (-1, 1):
        P.append(('sph', ((0.07 * sx, 0.52, -0.165), 0.045), C('ffffff')))            # eyes
        P.append(('sph', ((0.07 * sx, 0.52, -0.2), 0.022), C('111111')))
        hip = (0.08 * sx, -0.14, 0)
        knee = (0.12 * sx + 0.05 * s2 * sx, -0.36, -0.06 * s1)
        foot = (0.14 * sx + 0.08 * s1, -0.58, -0.02 + 0.06 * s2 * sx)
        P.append(('cap', (hip, knee, 0.075), PANTS))
        P.append(('cap', (knee, foot, 0.068), PANTS))
        P.append(('sph', (foot, 0.08), SHOE))
        sh = (0.19 * sx, 0.2, 0)
        if grab is not None and sx == 1:
            el = ((sh[0] + grab[0]) / 2, (sh[1] + grab[1]) / 2 + 0.05, (sh[2] + grab[2]) / 2)
            hand = grab
        else:
            up = 0.3 + 0.12 * (s1 if sx > 0 else s2) * flail + wave * 0.15 * math.sin(t * 10)
            el = (0.36 * sx, 0.28 + up * 0.5, -0.05)
            hand = (0.42 * sx + 0.05 * s2, 0.5 + up, -0.06 * s1)
        P.append(('cap', (sh, el, 0.06), SHIRT))
        P.append(('cap', (el, hand, 0.052), SKIN))
        P.append(('sph', (hand, 0.07), SKIN))
    mo = 0.04 + 0.035 * scream * (0.7 + 0.3 * math.sin(t * 20))
    P.append(('sph', ((0, 0.4, -0.15), mo), C('5a1220')))                              # mouth
    return P


def _xf(p, R, T):
    return R @ np.array(p, np.float32) + T


def place(prims, R, T):
    out = []
    for k, d, c in prims:
        if k == 'sph':
            out.append(('sph', (_xf(d[0], R, T), d[1]), c))
        else:
            out.append(('cap', (_xf(d[0], R, T), _xf(d[1], R, T), d[2]), c))
    return out


def rotm(ax, ay, az):
    cx, sx, cy, sy, cz, sz = math.cos(ax), math.sin(ax), math.cos(ay), math.sin(ay), math.cos(az), math.sin(az)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]], np.float32)
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], np.float32)
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]], np.float32)
    return Rz @ Ry @ Rx


def trace_prims(O, D, prims, tmax):
    """returns hit mask, t, normal, colour for nearest primitive hit closer than tmax"""
    n = len(D)
    tb = tmax.copy()
    nb = np.zeros((n, 3), np.float32)
    cb = np.zeros((n, 3), np.float32)
    hit = np.zeros(n, bool)
    for kind, d, col in prims:
        if kind == 'sph':
            c, r = d
            oc = O - c
            b = D @ oc
            h = b * b - (oc @ oc - r * r)
            m = h > 0
            tt = np.where(m, -b - np.sqrt(np.where(m, h, 0)), np.inf)
            ok = (tt > 1e-3) & (tt < tb)
            if ok.any():
                tb[ok] = tt[ok]
                Pp = O + tt[ok, None] * D[ok]
                nb[ok] = (Pp - c) / r
                cb[ok] = col
                hit |= ok
        else:
            pa, pb, r = d
            ba = pb - pa
            oa = O - pa
            baba = ba @ ba
            bard = D @ ba
            baoa = oa @ ba
            rdoa = D @ oa
            oaoa = oa @ oa
            a = baba - bard * bard
            b = baba * rdoa - baoa * bard
            cc = baba * oaoa - baoa * baoa - r * r * baba
            h = b * b - a * cc
            m = h >= 0
            with np.errstate(divide='ignore', invalid='ignore'):
                tt = (-b - np.sqrt(np.where(m, h, 0))) / a
            y = baoa + tt * bard
            body = m & (y > 0) & (y < baba)
            tcap = np.full(n, np.inf, np.float32)
            for endp in (pa, pb):
                oc = O - endp
                bc = D @ oc
                hc = bc * bc - (oc @ oc - r * r)
                mc = hc > 0
                tc = np.where(mc, -bc - np.sqrt(np.where(mc, hc, 0)), np.inf)
                tcap = np.minimum(tcap, np.where(tc > 1e-3, tc, np.inf))
            tt = np.where(body, tt, tcap)
            ok = (tt > 1e-3) & (tt < tb) & np.isfinite(tt)
            if ok.any():
                tb[ok] = tt[ok]
                Pp = O + tt[ok, None] * D[ok]
                k = np.clip(((Pp - pa) @ ba) / baba, 0, 1)
                q = pa + k[:, None] * ba
                nb[ok] = (Pp - q) / r
                cb[ok] = col
                hit |= ok
    return hit, tb, nb, cb


def shade_char(D, n, base, key, rim_col):
    lam = np.clip((n * key).sum(1), 0, 1)
    toon = 0.42 + 0.58 * smooth(0.05, 0.35, lam)
    rim = (1 - np.clip(-(n * D).sum(1), 0, 1)) ** 3
    return base * toon[:, None] + rim[:, None] * rim_col * 0.9


# ----------------------------------------------------------------------------- post (upscale, bloom, vignette)
_vy, _vx = np.mgrid[0:H, 0:W]
VIG = (1 - 0.45 * (((_vx - W / 2) / (W / 2)) ** 2 + ((_vy - H / 2) / (H / 2)) ** 2) ** 1.4).clip(0.3, 1).astype(np.float32)
EDGE = np.minimum(np.minimum(_vx, W - 1 - _vx), np.minimum(_vy, H - 1 - _vy)).astype(np.float32)


def post(col, red=0.0, flash=0.0, zoom=1.0):
    a = np.clip(col, 0, 255).astype(np.uint8)
    img = Image.fromarray(a).resize((W, H), Image.BICUBIC)
    if zoom > 1.001:
        cw, ch = W / zoom, H / zoom
        img = img.crop((int((W - cw) / 2), int((H - ch) / 2), int((W + cw) / 2), int((H + ch) / 2))).resize((W, H), Image.BICUBIC)
    small = np.asarray(img.resize((W // 8, H // 8), Image.BILINEAR), np.float32)
    br = np.clip(small - 170, 0, None) * 1.6
    bl = np.asarray(Image.fromarray(br.clip(0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(5)).resize((W, H), Image.BILINEAR), np.float32)
    out = np.asarray(img, np.float32) + bl * 0.75
    out *= VIG[..., None]
    if red > 0:
        k = red * np.exp(-EDGE / 90)
        out = out * (1 - k[..., None]) + C('ff1e3c')[None, None] * k[..., None]
    if flash > 0:
        out = out * (1 - flash) + 255 * flash
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


# ----------------------------------------------------------------------------- overlay (HUD, captions, cards)
YEL = (255, 210, 63)
CYAN = (95, 230, 255)
REDC = (255, 80, 90)
GRN = (80, 230, 120)


def pill(d, x, y, label, value, vcol=(255, 255, 255), w=None):
    fl, fv = Q.font(Q.F_BOLD, 34), Q.font(Q.F_BLACK, 50)
    lw = d.textlength(label, font=fl)
    vw = d.textlength(value, font=fv)
    w = w or int(lw + vw + 72)
    d.rounded_rectangle([x, y, x + w, y + 78], 22, fill=(8, 12, 28, 175), outline=(255, 255, 255, 60), width=2)
    d.text((x + 26, y + 22), label, font=fl, fill=(170, 185, 215, 255))
    d.text((x + w - 26 - vw, y + 10), value, font=fv, fill=vcol + (255,))
    return y + 92


def bar_pill(d, x, y, label, frac, value, col):
    fl, fv = Q.font(Q.F_BOLD, 34), Q.font(Q.F_BLACK, 50)
    w = 560
    d.rounded_rectangle([x, y, x + w, y + 78], 22, fill=(8, 12, 28, 175), outline=(255, 255, 255, 60), width=2)
    d.text((x + 26, y + 22), label, font=fl, fill=(170, 185, 215, 255))
    bx0, bx1 = x + 200, x + w - 150
    d.rounded_rectangle([bx0, y + 30, bx1, y + 48], 9, fill=(255, 255, 255, 40))
    fw = int((bx1 - bx0) * max(0.0, min(1.2, frac)) / 1.2)
    if fw > 6:
        d.rounded_rectangle([bx0, y + 30, bx0 + fw, y + 48], 9, fill=col + (255,))
    vw = d.textlength(value, font=fv)
    d.text((x + w - 26 - vw, y + 10), value, font=fv, fill=col + (255,))
    return y + 92


KEYWORDS = {'AIR', 'FIVE', 'SECONDS', 'SILENCE', 'SOUND', 'BLACK', 'SKY', 'EARS', 'BOIL', 'PLANES', 'BIRDS', 'DROP',
            'FIRES', 'MYTH', 'EXPLODES', 'SKIN', 'TEN', 'FOURTEEN', 'NASA', 'BOOM', 'HOLD', 'BREATH', 'LUNGS', 'RUPTURE',
            'BREATHE', 'OUT', 'VANISHED', 'SUNLIGHT', 'NINETEEN', 'SIXTY-FIVE'}


def _chunks():
    out = []
    for i, line in enumerate(LINES):
        words = line.split()
        groups, cur = [], []
        for w_ in words:
            cur.append(w_)
            if len(cur) == 3 or w_[-1] in ',.?!':
                groups.append(cur)
                cur = []
        if cur:
            groups.append(cur)
        tot = sum(len(' '.join(g)) + 2 for g in groups)
        tt = STARTS[i]
        for g in groups:
            d_ = DURS[i] * (len(' '.join(g)) + 2) / tot
            out.append((tt, tt + d_, g))
            tt += d_
    return out


CHUNKS = _chunks()


def caption(img, t):
    cur = None
    for c in CHUNKS:
        if c[0] <= t < c[1] + 0.12:
            cur = c
    if cur is None:
        return
    words = cur[2]
    layer = Image.new('RGBA', (W, 300), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    parts = [(w_, YEL if w_.strip(',.?!').upper() in KEYWORDS else (255, 255, 255)) for w_ in words]
    size = 100
    while True:
        f = Q.font(Q.F_BLACK, size)
        widths = [d.textlength(w_.upper() + ' ', font=f) for w_, _ in parts]
        tot = sum(widths) - d.textlength(' ', font=f)
        if tot <= 900 or size <= 60:
            break
        size -= 4
    x = (W - tot) / 2
    for (w_, c), ww in zip(parts, widths):
        d.text((x, 100), w_.upper(), font=f, fill=c + (255,), stroke_width=10, stroke_fill=(0, 0, 0, 255))
        x += ww
    k = min(1.0, (t - cur[0]) / 0.09)
    sc = 1.18 - 0.18 * k
    if sc > 1.001:
        layer = layer.resize((int(W * sc), int(300 * sc)), Image.BICUBIC)
    img.alpha_composite(layer, (int((W - layer.width) / 2), int(1250 - layer.height / 2)))




# ----------------------------------------------------------------------------- street scene (NEW 2026-10-23): AABB buildings, air-dependent sky
def _boxes():
    rng = np.random.default_rng(5)
    pal = [C('c9b99a'), C('9fb4c8'), C('d49a8a'), C('a9c4a0'), C('c8c8d4'), C('e0c27a')]
    B = []
    for side in (-1, 1):
        y = -11.0 if side < 0 else -9.0
        for k in range(8):
            w = 4.2 + rng.random() * 1.2
            h = 6 + rng.random() * 9
            x0, x1 = (3.4, 7.4 + rng.random()) if side > 0 else (-7.4 - rng.random(), -3.4)
            B.append((np.array([x0, y, 0], np.float32), np.array([x1, y + w, h], np.float32), pal[int(rng.integers(0, len(pal)))]))
            y += w + 0.5
    B.append((np.array([-14, 44, 0], np.float32), np.array([14, 50, 24], np.float32), C('8ea0b8')))
    return B


BOXES = _boxes()
SUN_D = nrm(np.array([-0.3, 0.8, 0.42], np.float32))
KEY = nrm(np.array([-0.4, -0.6, 0.7], np.float32))


def trace_boxes(O, D, tmax):
    n = len(D)
    tb = tmax.copy()
    hit = np.zeros(n, bool)
    P = np.zeros((n, 3), np.float32)
    nor = np.zeros((n, 3), np.float32)
    bc = np.zeros((n, 3), np.float32)
    inv = 1.0 / np.where(np.abs(D) < 1e-6, 1e-6, D)
    for lo, hi, base in BOXES:
        t0 = (lo - O) * inv
        t1 = (hi - O) * inv
        tn = np.minimum(t0, t1)
        tf = np.maximum(t0, t1)
        te = tn.max(1)
        tx = tf.min(1)
        ok = (te < tx) & (te > 1e-3) & (te < tb)
        if not ok.any():
            continue
        ax = tn[ok].argmax(1)
        tb[ok] = te[ok]
        hit |= ok
        idx = np.where(ok)[0]
        Pp = O + te[ok, None] * D[ok]
        P[idx] = Pp
        nn = np.zeros((len(idx), 3), np.float32)
        nn[np.arange(len(idx)), ax] = -np.sign(D[idx, ax])
        nor[idx] = nn
        bc[idx] = base
    return hit, tb, P, nor, bc


def sky_color(D, air):
    up = np.clip(D[:, 2], -1, 1)
    blue = mix(C('bfe3ff'), C('2f7fe0'), smooth(0.0, 0.5, up))
    stars = space_bg(D)
    stars = np.clip(stars * 1.5, 0, 255)
    sky = mix(stars, blue, air)
    sd = D @ SUN_D
    sky = sky + (np.clip(sd, 0, 1) ** 80)[:, None] * 255 * 0.9 * air
    disc = smooth(0.99935, 0.99975, sd)
    sky = mix(sky, C('fffbe8') * 1.0, disc)
    return sky


def street(t, air, cam, ch=None, extra=None, dim=0.0, vig=0.0):
    """ch: dict(yaw, scream, flail, wave, puff)"""
    D = cam.rays()
    O = cam.pos
    n = len(D)
    col = sky_color(D, air)
    tb = np.full(n, 1e9, np.float32)
    with np.errstate(divide='ignore', invalid='ignore'):
        tg = -O[2] / D[:, 2]
    g = (D[:, 2] < 0) & (tg > 0)
    gi = np.where(g)[0]
    Pg = O + tg[gi, None] * D[gi]
    ax_ = np.abs(Pg[:, 0])
    nz = _sample(ROCK, (Pg[:, 0] * 30) % 255, (Pg[:, 1] * 30) % 255)
    asp = mix(C('3a3d46'), C('4d515c'), nz)
    dash = (np.abs(Pg[:, 0]) < 0.08) & ((Pg[:, 1] % 2.6) < 1.3)
    asp[dash] = C('e8c84a')
    edge = (np.abs(ax_ - 3.2) < 0.06)
    asp[edge] = C('d8d8d8')
    walk = ax_ > 2.6
    side = mix(C('9a9a9a'), C('b4b4b4'), nz)
    gc = np.where(walk[:, None], side, asp)
    fog = smooth(10, 70, tg[gi]) * 0.55 * air
    gc = mix(gc, C('c8e4ff'), fog)
    col[gi] = gc
    tb[gi] = tg[gi]
    hit, tbx, P, nor, bc = trace_boxes(O, D, tb)
    if hit.any():
        hi = np.where(hit)[0]
        Pp, nn, base = P[hi], nor[hi], bc[hi]
        lam = np.clip(nn @ KEY, 0, 1)
        shade = 0.5 + 0.5 * smooth(0.05, 0.6, lam)
        wall = base * shade[:, None]
        vert = np.abs(nn[:, 2]) < 0.5
        u = np.where(np.abs(nn[:, 0]) > 0.5, Pp[:, 1], Pp[:, 0])
        v = Pp[:, 2]
        fu = (u / 1.1) % 1.0
        fv = (v / 1.5) % 1.0
        win = vert & (fu > 0.2) & (fu < 0.8) & (fv > 0.28) & (fv < 0.78) & (v > 1.0)
        refl = mix(C('26364f'), C('6fa0d8'), smooth(0.2, 0.7, fv)) * air + C('06080e') * (1 - air)
        wall = np.where(win[:, None], refl * (0.6 + 0.5 * shade[:, None]), wall)
        wall = np.where((nn[:, 2] > 0.5)[:, None], base * 1.1, wall)
        fogk = smooth(10, 80, tbx[hi]) * 0.6 * air
        wall = mix(wall, C('c8e4ff'), fogk)
        col[hi] = wall
        tb[hi] = tbx[hi]
    prims = []
    if ch is not None:
        Rw = np.array([[1, 0, 0], [0, 0, 1], [0, 1, 0]], np.float32)
        yaw = ch.get('yaw', 0.0)
        cp = char_prims(t, scream=ch.get('scream', 0.3), flail=ch.get('flail', 0.2), wave=ch.get('wave', 0.0))
        prims += place(cp, Rw @ rotm(0, yaw, 0), np.array([0, 0, 0.58], np.float32))
    if extra:
        prims += extra
    if prims:
        hitc, tt, nn, cb = trace_prims(O, D, prims, tb)
        if hitc.any():
            col[hitc] = shade_char(D[hitc], nn[hitc], cb[hitc], KEY, C('fff0d0') * 0.5 * air + C('9ab0ff') * 0.25 * (1 - air))
    col = col.reshape(RH, RW, 3)
    if vig > 0:
        r2 = ((_PX / RW * 2 - 1) ** 2 + (_PY / RH * 2 - 1) ** 2)
        col = col * (1 - vig * np.clip(r2 * 0.9, 0, 1))[..., None]
    if dim:
        col = col * (1 - dim) + C('05070f') * dim
    return col, cam


def plane_prims(p, tilt, scale=1.0):
    """simple toy airliner at world pos p, nose along +x rotated by tilt (nose-down about y axis)"""
    c, s = math.cos(tilt), math.sin(tilt)
    def T(q):
        x, y, z = q
        return np.array([p[0] + (x * c - z * s) * scale, p[1] + y * scale, p[2] + (x * s + z * c) * scale], np.float32)
    W_, G_ = C('f4f6fa'), C('ef4444')
    return [('cap', (T((-1.2, 0, 0)), T((1.2, 0, 0)), 0.16 * scale), W_),
            ('sph', (T((1.25, 0, 0)), 0.16 * scale), W_),
            ('cap', (T((0.1, -1.5, 0)), T((0.1, 1.5, 0)), 0.05 * scale), W_),
            ('cap', (T((-1.15, 0, 0)), T((-1.3, 0, 0.45)), 0.04 * scale), G_),
            ('cap', (T((-1.2, -0.5, 0)), T((-1.2, 0.5, 0)), 0.03 * scale), W_)]


def bird_prims(p, ph, scale=1.0):
    fl = math.sin(ph) * 0.4
    B_ = C('2b2b33')
    return [('sph', (np.array(p, np.float32), 0.09 * scale), B_),
            ('cap', (np.array(p, np.float32), np.array([p[0] - 0.22 * scale, p[1], p[2] + fl * scale], np.float32), 0.03 * scale), B_),
            ('cap', (np.array(p, np.float32), np.array([p[0] + 0.22 * scale, p[1], p[2] + fl * scale], np.float32), 0.03 * scale), B_)]


# ----------------------------------------------------------------------------- timeline
TA = L(0) + 2.3            # air vanishes
TB = L(7) + 0.35           # air slams back
AIR_DROP, AIR_BACK = 0.55, 0.25
SLOW5 = 5.0


def air_at(t):
    if t < TA:
        return 1.0
    if t < TA + AIR_DROP:
        return 1.0 - ease((t - TA) / AIR_DROP)
    if t < TB:
        return 0.0
    return ease((t - TB) / AIR_BACK)


def scene_of(t):
    for i in range(len(STARTS) - 1, -1, -1):
        if t >= STARTS[i] - 0.11:
            return i
    return 0


def cam_for(i, t):
    k = (t - L(i)) / max(0.1, DURS[i])
    if i == 0:
        return Cam((2.2 - 1.2 * ease(k), -6.2 + 2.4 * ease(k), 1.5 - 0.3 * ease(k)), (0, 0, 0.95), fov=52)
    if i == 1:
        az = -1.45 + 0.9 * k
        return Cam((3.2 * math.cos(az), 3.2 * math.sin(az), 1.2), (0, 0, 0.9), fov=50)
    if i == 2:
        return Cam((0.5, -1.7, 0.55), (-0.2 + 0.4 * k, 4.0, 3.4 + 2.2 * k), fov=70)
    if i == 3:
        return Cam((0.1, -1.6 + 0.2 * k, 1.1), (0, 0, 1.0), fov=40)
    if i == 4:
        return Cam((0.0, -3.0, 1.4), (1.0, 14.0, 7.5 - 1.5 * k), fov=66)
    if i == 5:
        return Cam((1.1 - 0.3 * k, -3.0 + 0.5 * k, 0.95), (0, 0, 0.75), fov=46)
    if i == 6:
        return Cam((0.5 - 0.35 * k, -2.3 + 0.9 * k, 1.1), (0, 0, 0.98), fov=44)
    if i == 7:
        return Cam((0.0, -4.0, 1.3), (0, 0, 1.0), fov=58)
    return Cam((1.5, -4.4, 1.3), (0, 0, 0.95), fov=50)


def render_frame(fi):
    t = fi / FPS
    i = scene_of(t)
    air = air_at(t)
    cam = cam_for(i, t)
    red, flash, zoom = 0.0, 0.0, 1.0
    ch = dict(yaw=0.0, scream=0.3, flail=0.15, wave=0.0)
    extra = None
    vig = 0.0
    dim = 0.0
    if i == 0:
        ch.update(wave=1.0 if t < TA else 0.0, scream=0.2 if t < TA else 1.4, flail=0.5)
        red = 0.15 + 0.25 * (0.5 + 0.5 * math.sin(t * 9)) * ease((t - 0.3) / 1.0)
    elif i == 1:
        ch.update(scream=1.5, flail=0.3)
    elif i == 2:
        ch.update(scream=1.0, flail=0.2)
    elif i == 3:
        k = t - L(3)
        ch.update(scream=1.6, flail=0.05)
        extra = []
        for b in range(12):
            ph = (k * 0.8 + b * 0.231) % 1.0
            ang = b * 2.4
            rr = 0.010 + 0.022 * (1 - ph) * (0.6 + 0.4 * math.sin(b * 1.7))
            extra.append(('sph', (np.array([0.07 * math.sin(ang) * (0.3 + ph), -0.19 - 0.12 * ph, 0.97 + 0.22 * ph + 0.03 * math.cos(ang)], np.float32), rr + 0.006), C('d8f4ff')))
        red = 0.2
    elif i == 4:
        k = t - L(4)
        extra = []
        gv = 1.7
        extra += plane_prims((-6.0 + 3.2 * k, 14.0, 17.0 - 0.5 * gv * k * k), 0.25 + 0.5 * k, scale=1.7)
        extra += plane_prims((6.0 - 2.4 * k, 20.0, 21.0 - 0.5 * gv * k * k), -0.2 - 0.3 * k + math.pi, scale=1.5)
        for b in range(6):
            extra += bird_prims((-3 + b * 1.3, 8 + (b % 3) * 2.0, 12 + (b % 2) * 2 - 0.5 * gv * k * k), 0.0, scale=1.6)
        ch.update(flail=0.1)
        red = 0.1
    elif i == 5:
        ch.update(scream=0.7, flail=0.2)
    elif i == 6:
        k = (t - L(6)) / DURS[6]
        vig = 0.9 * smooth(0.3, 1.0, k)
        ch.update(scream=0.4, flail=0.1)
    elif i == 7:
        ch.update(scream=0.5, flail=0.3)
    else:
        ch.update(flail=0.2)
        dim = min(0.5, (t - L(8)) * 1.5)
    # camera shake when air slams back
    if TB <= t < TB + 0.9:
        a = 0.14 * math.exp(-(t - TB) * 4)
        cam.pos = cam.pos + np.array([a * math.sin(t * 61), 0, a * math.cos(t * 53)], np.float32)
    col, _ = street(t, air, cam, ch=ch, extra=extra, dim=dim, vig=vig)
    for b in STARTS[1:]:
        if b - 0.11 <= t < b + 0.12:
            p = (t - (b - 0.11)) / 0.23
            flash = max(flash, 0.55 * (1 - abs(p * 2 - 1)))
            zoom = 1 + 0.1 * (1 - ease(p))
    if TA <= t < TA + 0.5:
        p = (t - TA) / 0.5
        flash = max(flash, 0.7 * (1 - p))
        zoom = max(zoom, 1 + 0.12 * (1 - ease(p)))
    if TB <= t < TB + 0.5:
        p = (t - TB) / 0.5
        flash = max(flash, 0.9 * (1 - p))
        zoom = max(zoom, 1 + 0.16 * (1 - ease(p)))
    img = post(col, red=red, flash=flash, zoom=zoom).convert('RGBA')
    overlays(img, t, i, cam)
    hud(img, t, i)
    if t >= L(8):
        choice_cards(img, t, L(8))
    caption(img, t)
    return img.convert('RGB')


def overlays(img, t, i, cam):
    d = ImageDraw.Draw(img, 'RGBA')
    hp = cam.project((0, 0, 1.0))
    # air rushing out streaks in the hook
    if i == 0 and t < TA + 0.6:
        k = ease((t - 0.2) / 1.8)
        cx, cy = W / 2, H * 0.45
        rng = np.random.default_rng(2)
        for j in range(46):
            a = rng.random() * 2 * math.pi
            r0 = 120 + ((t * (500 + 700 * rng.random()) + rng.random() * 900) % 1100) * (0.3 + k)
            r1 = r0 + 60 + 180 * k * rng.random()
            al = int(150 * (0.2 + 0.8 * k))
            d.line([cx + r0 * math.cos(a), cy + r0 * math.sin(a), cx + r1 * math.cos(a), cy + r1 * math.sin(a)], fill=(255, 255, 255, al), width=5)
    # ear-pop rings on the face close-up
    if i == 3 and hp is not None:
        for e in range(3):
            ph = ((t - L(3)) * 1.1 + e / 3.0) % 1.0
            r = 90 + 480 * ph
            al = int(220 * (1 - ph))
            d.ellipse([hp[0] - r, hp[1] - r * 1.1, hp[0] + r, hp[1] + r * 1.1], outline=(255, 235, 120, al), width=10)
    # myth stamp
    if i == 5:
        k = ease((t - L(5) - 1.1) / 0.18)
        if k > 0:
            f = Q.font(Q.F_BLACK, 120)
            txt = 'MYTH'
            tw_ = d.textlength(txt, font=f)
            lay = Image.new('RGBA', (int(tw_) + 120, 240), (0, 0, 0, 0))
            ld = ImageDraw.Draw(lay)
            ld.rounded_rectangle([0, 20, lay.width - 1, 220], 30, outline=(255, 70, 80, 255), width=14, fill=(40, 0, 6, 190))
            ld.text((60, 40), txt, font=f, fill=(255, 70, 80, 255))
            sc = 1.5 - 0.5 * k
            lay = lay.rotate(-10, expand=True, resample=Image.BICUBIC)
            lay = lay.resize((int(lay.width * sc), int(lay.height * sc)), Image.BICUBIC)
            img.alpha_composite(lay, (int(W / 2 - lay.width / 2), 560))
        k2 = ease((t - L(5) - 2.6) / 0.2)
        if k2 > 0:
            f = Q.font(Q.F_BLACK, 84)
            txt = 'SKIN HOLDS ✓'.replace(' ✓', '')
            tw_ = d.textlength(txt, font=f)
            d.rounded_rectangle([(W - tw_) / 2 - 40, 800, (W + tw_) / 2 + 40, 920], 34, fill=(20, 140, 70, int(235 * k2)))
            d.text(((W - tw_) / 2, 812), txt, font=f, fill=(255, 255, 255, int(255 * k2)))
    # shock ring when air returns
    if TB <= t < TB + 0.8:
        p = (t - TB) / 0.8
        r = 80 + 1500 * ease(p)
        al = int(255 * (1 - p))
        cx, cy = (hp if hp else (W / 2, H * 0.5))
        d.ellipse([cx - r, cy - r * 0.8, cx + r, cy + r * 0.8], outline=(255, 255, 255, al), width=int(40 * (1 - p)) + 6)
        d.ellipse([cx - r * 0.8, cy - r * 0.64, cx + r * 0.8, cy + r * 0.64], outline=(255, 220, 140, int(al * 0.6)), width=10)
        if p < 0.6:
            f = Q.font(Q.F_BLACK, 190)
            tw_ = d.textlength('BOOM', font=f)
            sc = 1 + 0.4 * (1 - ease(p / 0.6))
            lay = Image.new('RGBA', (int(tw_) + 60, 260), (0, 0, 0, 0))
            ImageDraw.Draw(lay).text((30, 20), 'BOOM', font=f, fill=(255, 225, 90, 255), stroke_width=14, stroke_fill=(0, 0, 0, 255))
            lay = lay.resize((int(lay.width * sc), int(lay.height * sc)), Image.BICUBIC)
            img.alpha_composite(lay, (int(W / 2 - lay.width / 2), 470))


def timer5(t):
    return min(SLOW5, max(0.0, (t - L(1)) / (TB - L(1)) * SLOW5)) if t < TB else SLOW5


def hud(img, t, i):
    d = ImageDraw.Draw(img, 'RGBA')
    if t < 0.15 or t > L(8) - 0.05:
        return
    air = air_at(t)
    y = 190
    y = pill(d, 50, y, 'AIR', f'{air * 100:.0f}%', GRN if air > 0.6 else (REDC if air < 0.3 else YEL), w=520)
    y = pill(d, 50, y, 'PRESSURE', f'{air * 101.3:.0f} kPa', (255, 255, 255) if air > 0.6 else REDC, w=520)
    if t >= L(1) - 0.1 and t < TB + 0.4:
        y = pill(d, 50, y, 'TIMER ×0.25', f'{timer5(t):.1f} s', CYAN, w=520)
    if i == 1:
        k = ease((t - L(1)) / 0.7)
        db = 60 * (1 - k)
        y = pill(d, 50, y, 'SOUND', f'{db:.0f} dB', GRN if db > 20 else REDC, w=520)
        amp = max(0.0, 1 - (t - L(1)) / 0.6)
        pts = []
        for xx in range(0, 760, 8):
            pts.append((160 + xx, 560 + amp * 70 * math.sin(xx * 0.09 + t * 40) * math.sin(xx * 0.012)))
        d.line(pts, fill=(95, 230, 255, 255) if amp > 0.05 else (255, 80, 90, 255), width=8)
        if amp <= 0.05:
            f = Q.font(Q.F_BLACK, 56)
            d.text((W / 2 - d.textlength('NO SOUND', font=f) / 2, 610), 'NO SOUND', font=f, fill=(255, 80, 90, 255))
    if i == 4:
        k = t - L(4)
        y = pill(d, 50, y, 'FALLING', f'{1.7 * k * 4.0:.0f} m/s', REDC, w=520)
    if i == 6:
        k = (t - L(6)) / DURS[6]
        rem = max(0.0, 10.0 - timer5(t) * 1.0)
        frac = rem / 10.0
        y = bar_pill(d, 50, y, 'AWAKE', frac, f'{rem:.0f}s', GRN if frac > 0.6 else YEL)
        if k > 0.45:
            kk = ease((k - 0.45) / 0.12)
            y = pill(d, 50, y, 'NASA 1965', '14 s awake', (255, 210, 63), w=520)


# ----------------------------------------------------------------------------- choice cards (override)
def choice_cards(img, t, t0):
    d = ImageDraw.Draw(img)
    k = ease((t - t0) / 0.3)
    fq = Q.font(Q.F_BLACK, 66)
    q = "HOLD IT OR BREATHE OUT?"
    qw = d.textlength(q, font=fq)
    d.text(((W - qw) / 2, 470 - 40 * (1 - k)), q, font=fq, fill=(255, 255, 255, int(255 * k)), stroke_width=10, stroke_fill=(0, 0, 0, int(255 * k)))
    f = Q.font(Q.F_BLACK, 66)
    for j, (txt, col) in enumerate((("HOLD IT", REDC), ("BREATHE OUT", GRN))):
        kk = ease((t - t0 - 0.15 - j * 0.12) / 0.3)
        if kk <= 0:
            continue
        y = 640 + j * 190
        pulse = 1 + 0.03 * math.sin(t * 6 + j * 3)
        w_, h_ = 760 * pulse, 150 * pulse
        x = (W - w_) / 2 + (1 - kk) * (300 if j else -300)
        d.rounded_rectangle([x, y, x + w_, y + h_], 40, fill=(10, 14, 30, int(220 * kk)), outline=col + (int(255 * kk),), width=8)
        tw_ = d.textlength(txt, font=f)
        d.text((x + (w_ - tw_) / 2, y + (h_ - 80) / 2), txt, font=f, fill=col + (int(255 * kk),))


# ----------------------------------------------------------------------------- audio
def sfx_boom():
    n = int(1.1 * SR)
    tt = np.arange(n) / SR
    f = 120 * np.exp(-tt * 3.5) + 28
    ph = 2 * np.pi * np.cumsum(f) / SR
    sig = np.sin(ph) * np.exp(-tt * 3.2)
    rng = np.random.default_rng(8)
    from scipy.signal import lfilter
    nz = lfilter([0.25], [1, -0.75], rng.uniform(-1, 1, n)) * np.exp(-tt * 7)
    return (sig * 1.0 + nz * 1.6).astype(np.float32)


def build_audio(path):
    from scipy.signal import lfilter
    n = int((DUR + 0.5) * SR)
    tt = np.arange(n) / SR
    voice = np.zeros(n, np.float32)
    for i in range(len(LINES)):
        with wave.open(os.path.join(VO_DIR, f'l{i}.wav')) as w:
            a = np.frombuffer(w.readframes(w.getnframes()), '<i2').astype(np.float32) / 32767
        i0 = int(STARTS[i] * SR)
        voice[i0:i0 + len(a)] += a[: n - i0]
    fx = np.zeros(n, np.float32)

    def add(t0, sig, vol):
        i0 = int(t0 * SR)
        if 0 <= i0 < n:
            seg = sig[: n - i0]
            fx[i0:i0 + len(seg)] += seg * vol
    rng = np.random.default_rng(3)
    # city hum / wind before the air vanishes
    noise = rng.uniform(-1, 1, n).astype(np.float32)
    hum = lfilter([0.05], [1, -0.95], noise).astype(np.float32)
    live = ((tt < TA) | (tt >= TB + 0.1)).astype(np.float32)
    live = np.convolve(live, np.ones(int(SR * 0.05)) / int(SR * 0.05), mode='same')
    fx += hum * 0.22 * live * (np.clip((tt) / 0.2, 0, 1))
    for b in STARTS[1:]:
        if b < TA or b > TB:
            add(b - 0.2, Q.sfx_whoosh(0.35), 0.5)
    add(TA - 0.15, Q.sfx_whoosh(0.5)[::-1].copy(), 0.3)
    add(TB, sfx_boom(), 1.3)
    add(TB, Q.sfx_whoosh(0.5), 0.5)
    add(L(5) + 1.1, Q.sfx_pop(), 0.9)
    add(L(5) + 2.6, Q.sfx_tada(), 0.5)
    add(L(8) + 0.15, Q.sfx_tick(True), 0.6)
    add(L(8) + 0.27, Q.sfx_tick(False), 0.6)
    bed = Q.music_bed(DUR + 0.5, seed=11)[:n]
    if len(bed) < n:
        bed = np.pad(bed, (0, n - len(bed)))
    gate = ((tt < TA) | (tt >= TB + 0.1)).astype(np.float32)
    gate = np.convolve(gate, np.ones(int(SR * 0.12)) / int(SR * 0.12), mode='same')
    env = np.convolve(np.abs(voice), np.ones(int(SR * 0.08)) / int(SR * 0.08), mode='same')
    duck = 1 - 0.55 * np.clip(env / 0.05, 0, 1)
    silent = ((tt >= TA + 0.1) & (tt < TB)).astype(np.float32)
    fxg = fx * (1 - silent * 0.97)
    mix_ = voice * 1.0 + fxg * 0.55 + bed * 0.9 * duck * gate
    mix_ *= np.clip((DUR - tt) / 0.8, 0, 1)
    mix_ /= max(1e-6, np.abs(mix_).max()) / 0.9
    pcm = (mix_ * 32767).astype('<i2')
    with wave.open(path, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())


def _frame_bytes(fi):
    return render_frame(fi).tobytes()


def render_video(out):
    wav = out.rsplit('.', 1)[0] + '.wav'
    build_audio(wav)
    cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}',
           '-r', str(FPS), '-i', '-', '-i', wav,
           '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11',
           '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p',
           '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-shortest', '-movflags', '+faststart', out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with Pool(2) as pool:
        for b in pool.imap(_frame_bytes, range(NF), chunksize=4):
            p.stdin.write(b)
    p.stdin.close()
    if p.wait() != 0:
        raise SystemExit('ffmpeg failed')
    os.remove(wav)


def sheet(out, times, cols=7):
    tw_, th_ = 270, 480
    rows = (len(times) + cols - 1) // cols
    sh = Image.new('RGB', (cols * (tw_ + 6), rows * (th_ + 6)), (50, 50, 50))
    for k, t in enumerate(times):
        im = render_frame(int(round(t * FPS))).resize((tw_, th_), Image.BILINEAR)
        sh.paste(im, ((k % cols) * (tw_ + 6), (k // cols) * (th_ + 6)))
    sh.save(out)


if __name__ == '__main__':
    if sys.argv[1] == 'sheet':
        sheet(sys.argv[2], [float(x) for x in sys.argv[3].split(',')])
    elif sys.argv[1] == 'info':
        print('DUR', round(DUR, 2), 'starts', [round(s, 2) for s in STARTS], 'TA', TA, 'TB', TB)
    else:
        render_video(sys.argv[2])
