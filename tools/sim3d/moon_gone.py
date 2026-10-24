#!/usr/bin/env python3
"""3D-sim style "WHAT IF" short: the Moon vanishes tonight (night street, harbor tides, space globe, dung beetle).

Own numpy ray tracer (no GPU, no Blender): cut-away Earth with layers, tunnel POV with a 3D cartoon
character, surface scene, smooth HUD + word-pop captions, kokoro narrator voice, music + SFX.
Render: 540x960 traced, upscaled to 1080x1920 with bloom. ~0.3 s/frame on 2 cores.

Usage (from tools/sim3d):
  python3 tts_lines.py moon_gone_lines.json /tmp/tunnel_vo          # voice first (durations drive the timeline)
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

VO_DIR = '/tmp/moon_vo'
for i, a in enumerate(sys.argv):
    if a == '--vo':
        VO_DIR = sys.argv[i + 1]
LINES = json.load(open(os.path.join(HERE, 'moon_gone_lines.json')))['lines']
DURS = json.load(open(os.path.join(VO_DIR, 'durs.json')))
GAP, START0, TAIL = 0.22, 0.3, 1.8
EXTRA_GAP = {10: 1.4}   # thinking pause (3-2-1) before the answer reveal
STARTS = []
_t = START0
for _i, d in enumerate(DURS):
    _t += EXTRA_GAP.get(_i, 0.0)
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




KEYWORDS = {'MOON', 'VANISHED', 'TONIGHT', 'SECONDS', 'DARK', 'HUNDRED', 'BRIGHTER', 'STARLIGHT', 'TIDES', 'THIRD', 'BEETLES',
            'MILKY', 'WAY', 'MYTH', 'FLIPS', 'MILLIONS', 'YEARS', 'DAY', 'TWENTY', 'FOUR', 'CENTIMETERS', 'DRIFTING', 'NIGHTS',
            'TINY', 'FIRST', '1.3', 'LIGHT', 'WOBBLE', 'INSTANTLY', 'NOPE', 'HOURS'}




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






POSES = {  # (elbow, hand) per side in local coords (x mirrored), y up, face toward -z
    'ears':  ((0.36, 0.36, -0.02), (0.21, 0.5, -0.02)),
    'mouth': ((0.26, 0.2, -0.2), (0.06, 0.4, -0.24)),
    'flex':  ((0.44, 0.24, 0.0), (0.4, 0.52, -0.04)),
    'down':  ((0.25, 0.02, 0.0), (0.27, -0.2, -0.02)),
    'cower': ((0.33, 0.5, -0.12), (0.1, 0.74, -0.08)),
}


def char_pose(t, pose, scream=0.5, flail=0.2):
    """char_prims with arm poses: up (flailing), ears, mouth, flex, down, cower, point (right arm up, left down)"""
    P = char_prims(t, scream=scream, flail=flail)
    if pose == 'up':
        return P
    out = [p for p in P if not (p[0] == 'cap' and abs(p[1][0][1] - 0.2) < 1e-6 and p[2] is SHIRT and p[1][0][0] != 0)]
    # drop old arm pieces: upper arm caps start at shoulder (±0.19,0.2,0); forearm/hand follow them
    keep = []
    skip = 0
    for p in P:
        if skip:
            skip -= 1
            continue
        if p[0] == 'cap' and tuple(np.round(p[1][0], 3)) in ((0.19, 0.2, 0), (-0.19, 0.2, 0)):
            skip = 2  # forearm + hand
            continue
        keep.append(p)
    jit = 0.015 * math.sin(t * 13)
    for sx in (-1, 1):
        if pose == 'point':
            el, hd = ((0.3, 0.55, -0.05), (0.32, 0.92, -0.1)) if sx > 0 else POSES['down']
        else:
            el, hd = POSES[pose]
        sh = (0.19 * sx, 0.2, 0.0)
        el = (el[0] * sx, el[1] + jit, el[2])
        hd = (hd[0] * sx, hd[1] + jit, hd[2])
        keep.append(('cap', (sh, el, 0.06), SHIRT))
        keep.append(('cap', (el, hd, 0.052), SKIN))
        keep.append(('sph', (hd, 0.07), SKIN))
    return keep


def scale_prims(P, s):
    out = []
    for k, d, c in P:
        if k == 'sph':
            out.append((k, (tuple(np.array(d[0]) * s), d[1] * s), c))
        else:
            out.append((k, (tuple(np.array(d[0]) * s), tuple(np.array(d[1]) * s), d[2] * s), c))
    return out




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




# ----------------------------------------------------------------------------- NEW 2026-10-24: night sky + moon, night street, harbor (tides), space globe, beetle, clock
from iss_reel import LAND, CLOUD, LAND_T, HIGH_T, CLOUD_T  # noqa: E402

BOXES[-1] = (BOXES[-1][0], np.array([14, 50, 7], np.float32), BOXES[-1][2])   # lower end building so the moon is visible down the street
MOON_D = nrm(np.array([0.0, 0.95, 0.31], np.float32))
_mu = nrm(np.cross(MOON_D, np.array([0, 0, 1], np.float32))[None])[0]
_mv = np.cross(_mu, MOON_D)
MOON_R = 0.09


def night_sky(D, moon, bright=1.0):
    """dark gradient + stars (+ milky band) + big textured moon with halo; moon in 0..1"""
    up = np.clip(D[:, 2], -1, 1)
    base = mix(C('0a1230'), C('02030a'), smooth(0.0, 0.8, up))
    stars = np.clip(space_bg(D) * 1.9, 0, 255) * bright
    sky = base + stars
    md = D @ MOON_D
    ang = np.arccos(np.clip(md, -1, 1))
    if moon > 0.001:
        halo = np.exp(-(ang / 0.22) ** 2) * 0.55 + np.exp(-(ang / 0.07) ** 2) * 0.6
        sky = sky + halo[:, None] * C('9db8ff')[None] * moon
        disc = smooth(MOON_R, MOON_R * 0.965, ang)
        near = disc > 0.001
        if near.any():
            idx = np.where(near)[0]
            Dn = D[idx]
            pu = (Dn @ _mu) / MOON_R
            pv = (Dn @ _mv) / MOON_R
            tx = (pu * 0.5 + 0.5) * 60 + 20
            ty = (pv * 0.5 + 0.5) * 60 + 20
            nz = _sample(ROCK, tx % 255, ty % 255)
            nz2 = _sample(ROCK, (tx * 2.3) % 255, (ty * 2.3) % 255)
            m = 0.72 + 0.28 * smooth(0.35, 0.65, nz) - 0.14 * smooth(0.55, 0.8, nz2)
            r2 = np.clip(pu * pu + pv * pv, 0, 1)
            m = m * (1 - 0.35 * r2)                                   # limb darkening
            moonc = C('f2f0e2')[None] * m[:, None]
            sky[idx] = mix(sky[idx], moonc * 1.05, disc[idx] * moon)
    return sky


def hash01(a, b):
    return (np.sin(a * 12.9898 + b * 78.233) * 43758.5453) % 1.0


def night_street(t, moon, cam, ch=None, extra=None, dim=0.0, vig=0.0):
    """street() at night: moon-dependent light, lit windows, stars"""
    D = cam.rays()
    O = cam.pos
    n = len(D)
    amb = 0.17 + 0.58 * moon
    tint = np.array([0.80, 0.90, 1.12], np.float32)
    haze = C('0b1736') * (0.5 + 1.1 * moon)
    col = night_sky(D, moon)
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
    asp[np.abs(ax_ - 3.2) < 0.06] = C('d8d8d8')
    walk = ax_ > 2.6
    side = mix(C('9a9a9a'), C('b4b4b4'), nz)
    gc = np.where(walk[:, None], side, asp) * amb * tint
    # warm street-lamp pools keep the street from being pitch black
    for ly in (-2.0, 6.0, 14.0):
        pool = np.exp(-(((Pg[:, 0] - 2.6) ** 2 + (Pg[:, 1] - ly) ** 2) / 5.0))
        gc = gc + pool[:, None] * C('ffb866')[None] * 0.42
    gc = mix(gc, haze, smooth(10, 70, tg[gi]) * 0.6)
    col[gi] = gc
    tb[gi] = tg[gi]
    hit, tbx, P, nor, bc = trace_boxes(O, D, tb)
    if hit.any():
        hi = np.where(hit)[0]
        Pp, nn, base = P[hi], nor[hi], bc[hi]
        lam = np.clip(nn @ KEY, 0, 1)
        shade = 0.55 + 0.45 * smooth(0.05, 0.6, lam)
        wall = base * shade[:, None] * amb * tint
        vert = np.abs(nn[:, 2]) < 0.5
        u = np.where(np.abs(nn[:, 0]) > 0.5, Pp[:, 1], Pp[:, 0])
        v = Pp[:, 2]
        iu, iv = np.floor(u / 1.1), np.floor(v / 1.5)
        fu = (u / 1.1) % 1.0
        fv = (v / 1.5) % 1.0
        win = vert & (fu > 0.2) & (fu < 0.8) & (fv > 0.28) & (fv < 0.78) & (v > 1.0)
        lit = hash01(iu + np.floor(Pp[:, 0] * 0.3), iv + np.floor(Pp[:, 1] * 0.3)) > 0.52
        wc = np.where(lit[:, None], C('ffd27a')[None] * 1.0, C('1a2540')[None] * (0.6 + 0.8 * moon))
        wall = np.where(win[:, None], wc, wall)
        wall = np.where((nn[:, 2] > 0.5)[:, None], base * amb * 0.9, wall)
        wall = mix(wall, haze, smooth(10, 80, tbx[hi]) * 0.6)
        col[hi] = wall
        tb[hi] = tbx[hi]
    prims = []
    if ch is not None:
        Rw = np.array([[1, 0, 0], [0, 0, 1], [0, 1, 0]], np.float32)
        cp = char_pose(t, ch.get('pose', 'up'), scream=ch.get('scream', 0.3), flail=ch.get('flail', 0.2))
        prims += place(cp, Rw @ rotm(ch.get('lean', 0.0), ch.get('yaw', 0.0), ch.get('roll', 0.0)),
                       np.array([ch.get('x', 0.0), ch.get('y', 0.0), 0.58 + ch.get('lift', 0.0)], np.float32))
    if extra:
        for k_, d_, c_ in extra:
            if k_ == 'sph':
                prims.append((k_, (np.asarray(d_[0], np.float32), float(d_[1])), c_))
            else:
                prims.append((k_, (np.asarray(d_[0], np.float32), np.asarray(d_[1], np.float32), float(d_[2])), c_))
    if prims:
        hitc, tt, nn, cb = trace_prims(O, D, prims, tb)
        if hitc.any():
            sc = shade_char(D[hitc], nn[hitc], cb[hitc], KEY, C('9fc0ff') * (0.25 + 0.45 * moon) + C('ffb866') * 0.2)
            col[hitc] = sc * (0.62 + 0.38 * moon)
    col = col.reshape(RH, RW, 3)
    if vig > 0:
        r2 = ((_PX / RW * 2 - 1) ** 2 + (_PY / RH * 2 - 1) ** 2)
        col = col * (1 - vig * np.clip(r2 * 0.9, 0, 1))[..., None]
    if dim:
        col = col * (1 - dim) + C('05070f') * dim
    return col


# ---- harbor: quay wall with tide ruler, moonlit water whose level (tide) is animated
HB = []
_r = np.random.default_rng(12)
for _k in range(9):
    _x0 = -16 + _k * 3.6 + _r.random() * 0.6
    HB.append((np.array([_x0, 12 + _r.random() * 4, 0], np.float32), np.array([_x0 + 3.2, 16 + _r.random() * 5, 5 + _r.random() * 9], np.float32), C('8a93a8')))
HB.append((np.array([-12, 0, -3], np.float32), np.array([12, 5, 2.0], np.float32), C('9a9488')))   # the quay


def trace_boxes_l(O, D, tmax, boxes):
    n = len(D)
    tb = tmax.copy()
    hit = np.zeros(n, bool)
    P = np.zeros((n, 3), np.float32)
    nor = np.zeros((n, 3), np.float32)
    bc = np.zeros((n, 3), np.float32)
    inv = 1.0 / np.where(np.abs(D) < 1e-6, 1e-6, D)
    for lo, hi, base in boxes:
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
        P[idx] = O + te[ok, None] * D[ok]
        nn = np.zeros((len(idx), 3), np.float32)
        nn[np.arange(len(idx)), ax] = -np.sign(D[idx, ax])
        nor[idx] = nn
        bc[idx] = base
    return hit, tb, P, nor, bc


HIGH_MARK = 1.5


def harbor(t, level, moon, cam, ch=None, extra=None, vig=0.0, dim=0.0, ripple=1.0):
    D = cam.rays()
    O = cam.pos
    n = len(D)
    amb = 0.38 + 0.5 * moon
    tint = np.array([0.82, 0.92, 1.1], np.float32)
    haze = C('0b1736') * (0.5 + 1.0 * moon)
    col = night_sky(D, moon)
    tb = np.full(n, 1e9, np.float32)
    with np.errstate(divide='ignore', invalid='ignore'):
        tw = (level - O[2]) / D[:, 2]
    w = (D[:, 2] < 0) & (tw > 0)
    wi = np.where(w)[0]
    Pw = O + tw[wi, None] * D[wi]
    ph = t * 1.6
    nx_ = _sample(ROCK, (Pw[:, 0] * 14 + ph * 9) % 255, (Pw[:, 1] * 14) % 255) - 0.5
    ny_ = _sample(ROCK, (Pw[:, 0] * 14) % 255, (Pw[:, 1] * 14 - ph * 7) % 255) - 0.5
    nrmw = nrm(np.stack([nx_ * 0.35 * ripple, ny_ * 0.35 * ripple, np.ones_like(nx_)], 1).astype(np.float32))
    Dw = D[wi]
    Rf = Dw - 2 * (Dw * nrmw).sum(1, keepdims=True) * nrmw
    Rf[:, 2] = np.abs(Rf[:, 2])
    refl = night_sky(nrm(Rf), moon, bright=0.7)
    fres = 0.25 + 0.6 * (1 - np.clip(-(Dw * nrmw).sum(1), 0, 1)) ** 3
    deep = C('06202e') * (0.5 + 0.9 * moon)
    wc = mix(deep[None].repeat(len(wi), 0), refl, fres)
    wc = mix(wc, haze, smooth(8, 60, tw[wi]) * 0.6)
    col[wi] = wc
    tb[wi] = tw[wi]
    hit, tbx, P, nor, bc = trace_boxes_l(O, D, tb, HB)
    if hit.any():
        hi = np.where(hit)[0]
        Pp, nn, base = P[hi], nor[hi], bc[hi]
        shade = 0.6 + 0.4 * np.clip(nn @ KEY, 0, 1)
        wall = base * shade[:, None] * amb * tint
        isq = Pp[:, 1] < 6.0
        top = nn[:, 2] > 0.5
        face = isq & (np.abs(nn[:, 1]) > 0.5)
        # stone courses + wet band below the highest tide mark, darker where the water was
        z = Pp[:, 2]
        course = 0.88 + 0.12 * (np.sin(z * 19.0) > 0.4)
        wall = np.where(face[:, None], wall * course[:, None], wall)
        wetk = smooth(HIGH_MARK + 0.08, HIGH_MARK - 0.05, z) * 0.45
        wall = np.where(face[:, None], wall * (1 - wetk[:, None]) + C('0c2230')[None] * wetk[:, None] * (0.5 + moon), wall)
        # tide ruler (x 1.55..1.95): white board, red ticks every 0.25 m
        ruler = face & (Pp[:, 0] > 1.55) & (Pp[:, 0] < 1.95) & (z > 0.0) & (z < 2.0)
        tick = ((z / 0.25) % 1.0) < 0.12
        rc = np.where(tick[:, None], C('ef3b4c')[None], C('f2f4f8')[None]) * (0.55 + 0.6 * moon)
        wall = np.where(ruler[:, None], rc, wall)
        wall = np.where(top[:, None] & isq[:, None], wall * 1.05, wall)
        far = ~isq
        if far.any():
            vert = np.abs(nn[:, 2]) < 0.5
            u = Pp[:, 0]
            fu = (u / 1.1) % 1.0
            fv = (z / 1.5) % 1.0
            win = far & vert & (fu > 0.2) & (fu < 0.8) & (fv > 0.28) & (fv < 0.78) & (z > 1.0)
            lit = hash01(np.floor(u / 1.1), np.floor(z / 1.5) + np.floor(Pp[:, 1])) > 0.5
            wc2 = np.where(lit[:, None], C('ffd27a')[None], C('1a2540')[None])
            wall = np.where(win[:, None], wc2, wall)
        wall = mix(wall, haze, smooth(8, 50, tbx[hi]) * 0.5)
        col[hi] = wall
        tb[hi] = tbx[hi]
    prims = []
    if ch is not None:
        Rw = np.array([[1, 0, 0], [0, 0, 1], [0, 1, 0]], np.float32)
        cp = char_pose(t, ch.get('pose', 'up'), scream=ch.get('scream', 0.3), flail=ch.get('flail', 0.2))
        prims += place(cp, Rw @ rotm(0, ch.get('yaw', 0.0), 0),
                       np.array([ch.get('x', -0.9), ch.get('y', 1.4), 2.0 + 0.58], np.float32))
    for k_, d_, c_ in (extra or []):
        if k_ == 'sph':
            prims.append((k_, (np.asarray(d_[0], np.float32), float(d_[1])), c_))
        else:
            prims.append((k_, (np.asarray(d_[0], np.float32), np.asarray(d_[1], np.float32), float(d_[2])), c_))
    # mooring bollards on the quay top
    for bx in (-3.0, 4.2):
        prims.append(('cap', (np.array([bx, 0.7, 2.0], np.float32), np.array([bx, 0.7, 2.38], np.float32), 0.14), C('3b4350')))
    if prims:
        hitc, tt, nn, cb = trace_prims(O, D, prims, tb)
        if hitc.any():
            sc = shade_char(D[hitc], nn[hitc], cb[hitc], KEY, C('9fc0ff') * (0.25 + 0.45 * moon))
            col[hitc] = sc * (0.62 + 0.38 * moon)
    col = col.reshape(RH, RW, 3)
    if vig > 0:
        r2 = ((_PX / RW * 2 - 1) ** 2 + (_PY / RH * 2 - 1) ** 2)
        col = col * (1 - vig * np.clip(r2 * 0.9, 0, 1))[..., None]
    if dim:
        col = col * (1 - dim) + C('05070f') * dim
    return col


# ---- space: Earth globe (tilt, spin, axis line) + Moon on an orbit slot
SUND = nrm(np.array([0.6, -0.55, 0.45], np.float32))


def space(t, cam, tilt, spin, moon_pos=None, moon_r=0.27, show_axis=True, axis_col=None):
    D = cam.rays()
    O = cam.pos
    n = len(D)
    col = space_bg(D) * 1.0
    # atmosphere glow from the closest approach to Earth
    tca = -(D @ O)
    Pc = O + tca[:, None] * D
    rc = np.linalg.norm(Pc, axis=1)
    glow = np.exp(-np.clip(rc - 1.0, 0, None) * 11.0) * (tca > 0) * (rc >= 1.0)
    col = col + glow[:, None] * C('4aa8ff')[None] * 0.55
    tb = np.full(n, 1e9, np.float32)
    # Earth
    b = D @ O
    h = b * b - (O @ O - 1.0)
    m = h > 0
    te = np.where(m, -b - np.sqrt(np.where(m, h, 0)), np.inf)
    ok = np.isfinite(te) & (te > 0)
    if ok.any():
        idx = np.where(ok)[0]
        Pp = O + te[idx, None] * D[idx]
        nn = Pp
        ct, st = math.cos(tilt), math.sin(tilt)
        # body frame: axis tilted about the x-axis by `tilt`
        bx = nn[:, 0]
        by = nn[:, 1] * ct + nn[:, 2] * st
        bz = -nn[:, 1] * st + nn[:, 2] * ct
        lat = np.arcsin(np.clip(bz, -1, 1))
        lon = np.arctan2(by, bx) + spin
        th_, tw_ = LAND.shape
        v = (0.5 - lat / np.pi) * (th_ - 1)
        hgt = _sample(LAND, ((lon / (2 * np.pi)) % 1.0) * tw_, v)
        cl = _sample(CLOUD, (((lon - spin * 0.5) / (2 * np.pi)) % 1.0) * tw_, v)
        land = hgt > LAND_T
        oc = mix(C('1b4fa8'), C('2d78e0'), smooth(0.2, 0.9, np.clip(0.5 + 0.5 * bz, 0, 1)))
        lc = mix(C('2f7a3c'), C('4fb056'), smooth(LAND_T, HIGH_T, hgt))
        lc = mix(lc, C('b49b5c'), smooth(HIGH_T - 0.02, HIGH_T + 0.03, hgt))
        base = np.where(land[:, None], lc, oc)
        base = mix(base, C('eaf2ff'), smooth(1.12, 1.3, np.abs(lat)))
        base = mix(base, C('f6f9ff'), smooth(CLOUD_T, CLOUD_T + 0.08, cl) * 0.85)
        lam = np.clip(nn @ SUND, 0, 1)
        shade = 0.12 + 0.88 * smooth(0.0, 0.5, lam)
        rim = (1 - np.clip(-(D[idx] * nn).sum(1), 0, 1)) ** 3
        col[idx] = base * shade[:, None] + rim[:, None] * C('7fc8ff') * 0.35
        tb[idx] = te[idx]
    prims = []
    if moon_pos is not None:
        prims.append(('sph', (np.array(moon_pos, np.float32), moon_r), C('cfcfd2')))
    if show_axis:
        ax = np.array([0, -math.sin(tilt), math.cos(tilt)], np.float32)
        prims.append(('cap', (ax * 1.0, ax * 1.55, 0.018), axis_col if axis_col is not None else C('ffd23f')))
        prims.append(('cap', (-ax * 1.0, -ax * 1.55, 0.018), axis_col if axis_col is not None else C('ffd23f')))
    if prims:
        hitc, tt, nn, cb = trace_prims(O, D, prims, tb)
        if hitc.any():
            sc = shade_char(D[hitc], nn[hitc], cb[hitc], SUND, C('ffffff') * 0.15)
            # moon crater noise (cheap): modulate by position noise
            col[hitc] = sc
    return col.reshape(RH, RW, 3)


def beetle_prims(p, hd, ph, ball=True):
    """dung beetle at ground pos p heading angle hd (rad, 0 = +y), with rolled ball behind it"""
    f = np.array([math.sin(hd), math.cos(hd), 0], np.float32)
    s = np.array([math.cos(hd), -math.sin(hd), 0], np.float32)
    p = np.array(p, np.float32)
    B, D_ = C('2a2a36'), C('4a4a58')
    S = 1.7
    z = lambda v: np.array([0, 0, v], np.float32)
    P = [('sph', (p + z(0.05 * S), 0.06 * S), B),
         ('sph', (p + f * 0.07 * S + z(0.05 * S), 0.045 * S), D_),
         ('sph', (p + f * 0.12 * S + z(0.05 * S), 0.028 * S), B)]
    for j, k in enumerate((-0.04, 0.0, 0.05)):
        for sgn in (-1, 1):
            sw = 0.03 * math.sin(ph * 2 + j * 2.1 + sgn)
            a = p + f * (0.04 + k) * S + z(0.04 * S)
            b_ = a + s * sgn * 0.07 * S + f * sw * S + z(-0.04 * S)
            P.append(('cap', (a, b_, 0.008 * S), B))
    if ball:
        P.append(('sph', (p - f * 0.1 * S + s * 0.2 * S + z(0.07 * S), 0.07 * S), C('8a6238')))
    return P




def _sticker(img, txt, size, col, cx, cy, rot, k, sub=None):
    f = Q.font(Q.F_BLACK, size)
    d0 = ImageDraw.Draw(img)
    tw_ = d0.textlength(txt, font=f)
    if sub:
        tw_ = max(tw_, d0.textlength(sub, font=Q.font(Q.F_BOLD, 40)))
    lay = Image.new('RGBA', (int(tw_) + 80, int(size * 1.6) + (60 if sub else 0)), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    ld.text(((lay.width - d0.textlength(txt, font=f)) / 2, 10), txt, font=f, fill=col + (255,), stroke_width=12, stroke_fill=(0, 0, 0, 255))
    if sub:
        fs = Q.font(Q.F_BOLD, 40)
        ld.text(((lay.width - ld.textlength(sub, font=fs)) / 2, size * 1.35), sub, font=fs, fill=(255, 255, 255, 255), stroke_width=6, stroke_fill=(0, 0, 0, 255))
    sc = 1.5 - 0.5 * k
    lay = lay.rotate(rot, expand=True, resample=Image.BICUBIC)
    lay = lay.resize((max(1, int(lay.width * sc)), max(1, int(lay.height * sc))), Image.BICUBIC)
    img.alpha_composite(lay, (int(cx - lay.width / 2), int(cy - lay.height / 2)))




# ----------------------------------------------------------------------------- timeline
TA = L(1) + 1.3                       # moon vanishes (1.3 s light delay)
SPLIT = {1: TA, 3: L(3) + DURS[3] * 0.52, 4: L(4) + DURS[4] * 0.45, 5: L(5) + DURS[5] * 0.5,
         6: L(6) + DURS[6] * 0.45, 8: L(8) + DURS[8] * 0.5}
CUTS = sorted(list(STARTS[1:]) + [v for k, v in SPLIT.items() if k != 1])
TIDE_T0, TIDE_T1 = L(4) - 0.2, L(4) + DURS[4]


def scene_of(t):
    for i in range(len(STARTS) - 1, -1, -1):
        if t >= STARTS[i] - 0.11:
            return i
    return 0


def half_of(i, t):
    return 1 if (i in SPLIT and t >= SPLIT[i]) else 0


def moon_at(i, h, t):
    if i == 0:
        return 1.0
    if i == 1:
        return 1.0 if t < TA else 0.0
    if i == 3:
        return 1.0 if h == 0 else 0.0
    if i == 5:
        return 1.0 if h == 0 else 0.0
    return 0.0


def tide_amp(t):
    k = ease((t - TIDE_T0) / (TIDE_T1 - TIDE_T0))
    return 0.5 * (1 - k) + 0.1667 * k


def tide_level(t):
    return 1.0 + tide_amp(t) * math.sin((t - L(4)) * 4.2 + 1.2)


def tilt_at(t):
    k = (t - L(6)) / (STARTS[7] - L(6))
    return math.radians(23.5 + 52 * ease(k) * (0.6 + 0.4 * math.sin(t * 1.3)))


def years_at(t):
    k = ease((t - SPLIT[6]) / (STARTS[7] - SPLIT[6]))
    return 10_000_000 * k


def cam_for(i, h, t):
    if i in SPLIT and h == 1:
        t0, t1 = SPLIT[i], (STARTS[i + 1] if i + 1 < len(STARTS) else DUR)
    elif i in SPLIT:
        t0, t1 = L(i), SPLIT[i]
    else:
        t0, t1 = L(i), (STARTS[i + 1] if i + 1 < len(STARTS) else DUR)
    k = min(1.0, max(0.0, (t - t0) / max(0.2, t1 - t0)))
    e = ease(k)
    if i == 0:                 # wide dolly-in, moon high above the street
        return Cam((2.4 - 1.5 * e, -8.5 + 5.0 * e, 1.9 - 0.5 * e), (0.0, 3.0, 3.2 - 0.6 * e), fov=58)
    if i == 1 and h == 0:      # low angle fast push-in on the moon
        tgt = np.array([0.35, -1.4, 0.35], np.float32) + MOON_D * 10
        return Cam((0.35, -1.4, 0.35), tgt, fov=76 - 26 * e, roll=0.12 - 0.12 * e)
    if i == 1:                 # wide: dark, character cowers
        return Cam((1.8 - 0.5 * e, -4.6, 1.4), (0, 0, 1.1), fov=60)
    if i == 2:                 # orbit in the dark, lit windows
        az = -1.9 + 1.5 * e
        return Cam((2.8 * math.cos(az), 2.8 * math.sin(az), 1.2), (0, 0, 1.0), fov=54)
    if i == 3:                 # full moon vs none, wide
        return Cam((1.5 - 0.5 * e, -7.0 + 0.8 * e, 1.4), (-0.3, 2.0, 2.6), fov=60)
    if i == 4 and h == 0:      # harbor wide: water pumping up and down
        return Cam((0.4, -6.5 + 1.2 * e, 2.2 - 0.3 * e), (0.4, 1.0, 1.55), fov=58)
    if i == 4:                 # ruler close-up
        return Cam((1.75 - 0.1 * e, -2.4 + 0.3 * e, 1.15), (1.75, 0.0, 1.05), fov=40)
    if i == 5 and h == 0:      # beetle rolling a ball under the moon (ground-level)
        return Cam((0.5 - 0.1 * e, -1.25, 0.25), (0.2, 1.0, 0.55), fov=66)
    if i == 5:                 # beetle circling, stars
        return Cam((-0.5 + 0.3 * e, -1.1, 0.25), (0.2, 0.6, 0.35), fov=66, roll=0.08)
    if i == 6 and h == 0:      # Earth wobble
        return Cam((0.0, -6.5 + 0.5 * e, 0.8), (0, 0, 0), fov=44, up=(0, 0, 1))
    if i == 6:
        return Cam((0.0, -5.8 + 0.8 * e, -0.6), (0, 0, 0.2), fov=44)
    if i == 7:                 # clock: hero close-up
        return Cam((0.9 - 0.4 * e, -2.4 + 0.5 * e, 1.1), (0, 0, 1.0), fov=46)
    if i == 8 and h == 0:      # Earth and Moon, moon slowly pulls away
        return Cam((0.0, -9.5, 0.5), (0, 0, 1.4), fov=48)
    if i == 8:                 # close on the moon with arrow
        return Cam((0.0, -4.6 + 0.8 * e, 3.0), (0, 0, 3.3 + 0.25 * e), fov=42)
    return Cam((1.5, -4.4, 1.3), (0, 0, 0.95), fov=50)


POSE_OF = {(0, 0): ('point', 0.4, 0.1), (1, 0): ('up', 0.3, 0.2), (1, 1): ('cower', 1.4, 0.1), (2, 0): ('ears', 0.6, 0.1),
           (3, 0): ('point', 0.4, 0.1), (3, 1): ('cower', 0.8, 0.1), (4, 0): ('flex', 0.2, 0.1), (4, 1): ('flex', 0.2, 0.1),
           (7, 0): ('flex', 0.2, 0.1), (9, 0): ('down', 0.3, 0.1), (10, 0): ('flex', 0.2, 0.1)}


def render_frame(fi):
    t = fi / FPS
    i = scene_of(t)
    h = half_of(i, t)
    cam = cam_for(i, h, t)
    red, flash, zoom = 0.0, 0.0, 1.0
    moon = moon_at(i, h, t)
    # moon fade-out pop at TA (scene 1 first half)
    if i == 1 and h == 0 and t > TA - 0.25:
        moon = 1.0 + 0.5 * math.sin((t - (TA - 0.25)) * 40)
    pose, scream, flail = POSE_OF.get((i, h), POSE_OF.get((i, 0), ('up', 0.3, 0.2)))
    ch = dict(pose=pose, scream=scream, flail=flail)
    vig = dim = 0.0
    if i in (0, 1, 2, 3):
        if i == 0:
            ch['yaw'] = 3.14159 + 0.0     # looks up toward the moon (back to camera): turn toward camera instead
            ch['yaw'] = 0.0
        if i == 1 and h == 1:
            red = 0.18 * math.exp(-(t - TA) * 2.0)
        if i == 2:
            ch['lift'] = 0.0
        col = night_street(t, min(moon, 1.3), cam, ch=ch, extra=None, dim=dim, vig=vig)
        if i == 1 and h == 0:
            pass
    elif i == 4:
        col = harbor(t, tide_level(t), 0.0 if True else 0, cam, ch=dict(pose='flex', scream=0.2, flail=0.1, yaw=0.0), vig=0.0)
    elif i == 5:
        k = t - L(5)
        if h == 0:
            p = (0.15 + 0.5 * k, -0.2 + 0.9 * k * 0.4, 0.0)
            hd = math.atan2(0.5, 0.36)
            bp = beetle_prims(p, hd, t * 9)
            col = night_street(t, moon, cam, ch=None, extra=bp, dim=0.0, vig=0.0)
        else:
            k2 = t - SPLIT[5]
            ang = k2 * 3.4
            p = (0.25 + 0.38 * math.sin(ang), 0.25 - 0.38 * math.cos(ang) + 0.2, 0.0)
            hd = -ang + 3.14159
            bp = beetle_prims(p, hd, t * 12)
            col = night_street(t, 0.0, cam, ch=None, extra=bp, dim=0.0, vig=0.0)
    elif i == 6:
        tilt = tilt_at(t)
        col = space(t, cam, tilt, t * 0.6, moon_pos=None, show_axis=True)
    elif i == 8:
        drift = 0.12 * ease((t - L(8)) / DURS[8])
        col = space(t, cam, math.radians(23.5), t * 0.5, moon_pos=(0.0, 0.0, 3.0 + drift), show_axis=False)
    else:
        col = night_street(t, 0.0, cam, ch=ch, extra=None, dim=0.55 if i >= 9 else 0.0, vig=0.0)
    for b in CUTS:
        if b - 0.11 <= t < b + 0.12:
            p_ = (t - (b - 0.11)) / 0.23
            flash = max(flash, 0.45 * (1 - abs(p_ * 2 - 1)))
            zoom = max(zoom, 1 + 0.12 * (1 - ease(p_)))
    zoom *= 1 + 0.04 * ((t * 1.7) % 1.0)
    if TA <= t < TA + 0.5:
        p_ = (t - TA) / 0.5
        flash = max(flash, 0.9 * (1 - p_))
        zoom = max(zoom, 1 + 0.2 * (1 - ease(p_)))
    img = post(col, red=red, flash=flash, zoom=zoom).convert('RGBA')
    overlays(img, t, i, h, cam)
    hud(img, t, i)
    if t >= L(9):
        choice_cards(img, t, L(9))
    caption(img, t)
    return img.convert('RGB')


def lux_at(t, i, h):
    return 0.25 if moon_at(i, h, t) > 0.5 else 0.002


def draw_clock(img, cx, cy, r, k):
    d = ImageDraw.Draw(img, 'RGBA')
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(8, 12, 28, 215), outline=(255, 255, 255, 230), width=10)
    for j in range(24):
        a = j * math.pi / 12 - math.pi / 2
        l0 = r * (0.8 if j % 6 == 0 else 0.88)
        d.line([cx + l0 * math.cos(a), cy + l0 * math.sin(a), cx + r * 0.95 * math.cos(a), cy + r * 0.95 * math.sin(a)],
               fill=(255, 255, 255, 255), width=8 if j % 6 == 0 else 4)
    a = k * 2 * math.pi - math.pi / 2
    d.line([cx, cy, cx + r * 0.72 * math.cos(a), cy + r * 0.72 * math.sin(a)], fill=YEL + (255,), width=14)
    d.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], fill=YEL + (255,))


def overlays(img, t, i, h, cam):
    d = ImageDraw.Draw(img, 'RGBA')
    if i == 0:
        k = ease((t - L(0) - 0.5) / 0.12)
        if t > L(0) + 0.5:
            _sticker(img, 'MOON DELETED', 92, REDC, W / 2, 700, -6, k)
    if i == 1 and h == 0:
        # warning ring around the moon's screen position
        q = cam.project(MOON_D * 40 + cam.pos)
        if q is not None:
            kk = (t - L(1)) % 0.5 / 0.5
            r = 120 + 360 * kk
            d.ellipse([q[0] - r, q[1] - r, q[0] + r, q[1] + r], outline=(255, 235, 150, int(200 * (1 - kk))), width=8)
    if TA <= t < TA + 0.6:
        p_ = (t - TA) / 0.6
        if i == 1:
            _sticker(img, 'POOF', 190, (255, 255, 255), W / 2, 640, 0, ease(p_ / 0.25))
    if i == 1 and h == 1 and t > TA + 0.5:
        _sticker(img, '1.3 s LATE', 100, CYAN, W / 2, 620, 6, ease((t - TA - 0.5) / 0.15), sub='moonlight travel time')
    if i == 2:
        _sticker(img, 'DARK', 190, (255, 255, 255), W / 2, 640, -5, ease((t - L(2) - 0.15) / 0.15))
    if i == 3 and h == 0:
        _sticker(img, 'FULL MOON', 100, YEL, W / 2, 600, -5, ease((t - L(3) - 0.25) / 0.15), sub='0.25 lux')
    if i == 3 and h == 1:
        _sticker(img, 'STARLIGHT', 100, CYAN, W / 2, 600, 5, ease((t - SPLIT[3] - 0.1) / 0.15), sub='0.002 lux')
        _sticker(img, 'up to 100x', 84, YEL, W / 2, 860, -4, ease((t - SPLIT[3] - 0.5) / 0.15))
    if i == 4 and h == 0:
        _sticker(img, 'TIDES', 150, (255, 255, 255), W / 2, 560, -5, ease((t - L(4) - 0.1) / 0.15))
    if i == 4 and h == 1:
        _sticker(img, '1/3', 200, YEL, W / 2, 600, 4, ease((t - SPLIT[4] - 0.1) / 0.15), sub='as high')
    if i == 5 and h == 0:
        _sticker(img, 'NAVIGATING BY MOON', 64, YEL, W / 2, 620, -3, ease((t - L(5) - 0.2) / 0.15))
    if i == 5 and h == 1:
        _sticker(img, 'NO MOON?', 110, REDC, W / 2, 560, -5, ease((t - SPLIT[5] - 0.0) / 0.15))
        if t > SPLIT[5] + 0.8:
            _sticker(img, 'MILKY WAY', 100, CYAN, W / 2, 800, 5, ease((t - SPLIT[5] - 0.8) / 0.15), sub='plan B')
    if i == 6 and h == 0:
        _sticker(img, 'FLIPS?', 130, REDC, W / 2, 540, -6, ease((t - L(6) - 0.1) / 0.15))
        _sticker(img, 'MYTH', 150, (255, 255, 255), W / 2, 820, 8, ease((t - L(6) - 0.55) / 0.15))
    if i == 6 and h == 1:
        _sticker(img, 'MILLIONS OF YEARS', 70, YEL, W / 2, 560, -4, ease((t - SPLIT[6] - 0.1) / 0.15))
    if i == 7:
        k = (t - L(7)) / DURS[7]
        draw_clock(img, W / 2, 560, 170, ease(k))
        _sticker(img, '24 h', 130, GRN, W / 2, 860, 4, ease((t - L(7) - 0.5) / 0.15))
    if i == 8 and h == 0:
        _sticker(img, 'DRIFTING AWAY', 80, (255, 255, 255), W / 2, 540, -4, ease((t - L(8) - 0.1) / 0.15))
    if i == 8 and h == 1:
        k = ease((t - SPLIT[8]) / 0.3)
        f = Q.font(Q.F_BLACK, 110)
        txt = '+3.8 cm / year'
        tw_ = d.textlength(txt, font=f)
        d.rounded_rectangle([(W - tw_) / 2 - 40, 520, (W + tw_) / 2 + 40, 680], 36, fill=(20, 140, 70, int(235 * k)))
        d.text(((W - tw_) / 2, 540), txt, font=f, fill=(255, 255, 255, int(255 * k)))
    if L(9) + DURS[9] <= t < L(10):
        k = (t - L(9) - DURS[9]) / (L(10) - L(9) - DURS[9])
        n_ = 3 - int(k * 3)
        _sticker(img, str(max(1, n_)), 200, YEL, W / 2, 1180, 0, ease(((k * 3) % 1.0) / 0.2))


def hud(img, t, i):
    d = ImageDraw.Draw(img, 'RGBA')
    if t > L(9) - 0.05:
        return
    h = half_of(i, t)
    y = 190
    if i == 0:
        y = pill(d, 50, y, 'MOON', 'HERE', GRN, w=520)
    elif i == 1:
        if t < TA:
            y = pill(d, 50, y, 'LIGHT DELAY', f'{min(1.3, max(0.0, t - L(1))):.1f} s', CYAN, w=520)
            y = pill(d, 50, y, 'MOON', 'HERE', GRN, w=520)
        else:
            y = pill(d, 50, y, 'MOON', 'GONE', REDC, w=520)
    elif i in (2, 3):
        lx = lux_at(t, i, h)
        y = pill(d, 50, y, 'NIGHT LIGHT', f'{lx:.3f} lux' if lx < 0.01 else f'{lx:.2f} lux', GRN if lx > 0.1 else REDC, w=520)
        y = pill(d, 50, y, 'MOON', 'HERE' if lx > 0.1 else 'GONE', GRN if lx > 0.1 else REDC, w=520)
    elif i == 4:
        rng_ = tide_amp(t) / 0.5
        y = bar_pill(d, 50, y, 'TIDE RANGE', rng_, f'{rng_ * 100:.0f}%', GRN if rng_ > 0.6 else YEL)
        y = pill(d, 50, y, 'WATER', f'{tide_level(t):.2f} m', CYAN, w=520)
    elif i == 5:
        if h == 0:
            y = pill(d, 50, y, 'COMPASS', 'MOON', GRN, w=520)
        else:
            y = pill(d, 50, y, 'COMPASS', 'LOST?', REDC, w=520)
            if t > SPLIT[5] + 0.8:
                y = pill(d, 50, y, 'SWITCH TO', 'MILKY WAY', CYAN, w=520)
    elif i == 6:
        y = pill(d, 50, y, 'TILT', f'{math.degrees(tilt_at(t)):.1f} deg', YEL, w=520)
        if h == 1:
            y = pill(d, 50, y, 'TIME', f'{years_at(t) / 1e6:.1f} million yr', REDC, w=520)
    elif i == 7:
        y = pill(d, 50, y, 'DAY LENGTH', '24.0 h', GRN, w=520)
        y = pill(d, 50, y, 'MOON SLOWS US', '2 ms / century', YEL, w=520)
    elif i == 8:
        k = ease((t - L(8)) / DURS[8])
        y = pill(d, 50, y, 'MOON DRIFT', f'+{3.8 * k:.1f} cm', YEL, w=520)
        y = pill(d, 50, y, 'DISTANCE', '384,400 km', (255, 255, 255), w=520)


# ----------------------------------------------------------------------------- choice cards (override)
def choice_cards(img, t, t0):
    d = ImageDraw.Draw(img)
    k = ease((t - t0) / 0.3)
    fq = Q.font(Q.F_BLACK, 66)
    q = "WHAT WOULD YOU NOTICE FIRST?"
    qw = d.textlength(q, font=fq)
    if qw > 980:
        fq = Q.font(Q.F_BLACK, 56)
        qw = d.textlength(q, font=fq)
    d.text(((W - qw) / 2, 470 - 40 * (1 - k)), q, font=fq, fill=(255, 255, 255, int(255 * k)), stroke_width=10, stroke_fill=(0, 0, 0, int(255 * k)))
    f = Q.font(Q.F_BLACK, 66)
    for j, (txt, col) in enumerate((("DARK NIGHTS", YEL), ("TINY TIDES", CYAN))):
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
    if t >= L(10):
        k = ease((t - L(10)) / 0.25)
        y0, y1 = 640, 830
        d.line([(W - 760) / 2 + 30, y1 + 75, (W + 760) / 2 - 30, y1 + 75], fill=REDC + (int(255 * k),), width=14)
        cx, cy, r = (W + 760) / 2 - 20, y0 + 75, 70 * (1.4 - 0.4 * k)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(30, 170, 80, int(255 * k)), outline=(255, 255, 255, int(255 * k)), width=6)
        d.line([(cx - r * 0.45, cy), (cx - r * 0.1, cy + r * 0.38), (cx + r * 0.5, cy - r * 0.4)], fill=(255, 255, 255, int(255 * k)), width=14, joint='curve')


# ----------------------------------------------------------------------------- audio
def sfx_pop():
    n = int(0.6 * SR)
    tt = np.arange(n) / SR
    ph = 2 * np.pi * np.cumsum(220 * np.exp(-tt * 14) + 40) / SR
    rng = np.random.default_rng(4)
    return (np.sin(ph) * np.exp(-tt * 9) + rng.uniform(-1, 1, n) * np.exp(-tt * 40) * 0.8).astype(np.float32)


def sfx_rise(dur=1.0):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    f = 200 + 900 * (tt / dur) ** 2
    return (np.sin(2 * np.pi * np.cumsum(f) / SR) * (tt / dur) * 0.5).astype(np.float32)


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
    cricket = (np.sin(2 * np.pi * 4200 * tt) * (np.sin(2 * np.pi * 7 * tt) > 0.6) * 0.02).astype(np.float32)
    wind = lfilter([0.04], [1, -0.96], rng.uniform(-1, 1, n)).astype(np.float32) * 0.15
    fx += cricket + wind
    for b in CUTS:
        add(b - 0.2, Q.sfx_whoosh(0.35), 0.5)
    add(L(1), sfx_rise(1.3), 0.45)
    add(TA, sfx_pop(), 1.4)
    add(TA, Q.sfx_whoosh(0.5), 0.5)
    add(L(0) + 0.5, Q.sfx_tick(True), 0.7)
    add(SPLIT[4] + 0.1, Q.sfx_tada(), 0.5)
    add(SPLIT[6] + 0.55, Q.sfx_tada(), 0.4)
    add(L(9) + 0.15, Q.sfx_tick(True), 0.6)
    add(L(9) + 0.27, Q.sfx_tick(False), 0.6)
    pause0 = L(9) + DURS[9]
    for q in range(3):
        add(pause0 + q * (L(10) - pause0) / 3, Q.sfx_tick(q % 2 == 0), 0.7)
    add(L(10) - 0.05, Q.sfx_tada(), 0.7)
    bed = Q.music_bed(DUR + 0.5, seed=17)[:n]
    if len(bed) < n:
        bed = np.pad(bed, (0, n - len(bed)))
    env = np.convolve(np.abs(voice), np.ones(int(SR * 0.08)) / int(SR * 0.08), mode='same')
    duck = 1 - 0.55 * np.clip(env / 0.05, 0, 1)
    mix_ = voice * 1.0 + fx * 0.6 + bed * 0.85 * duck
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
        print('DUR', round(DUR, 2), 'starts', [round(x, 2) for x in STARTS], 'TA', round(TA, 2), 'cuts', [round(x, 2) for x in CUTS])
    else:
        render_video(sys.argv[2])


