#!/usr/bin/env python3
"""3D-sim style "NEVER DO X" short: never pour water on a grease fire (kitchen scene, pan + oil + flames, steam inset, fireball).

Own numpy ray tracer (no GPU, no Blender): cut-away Earth with layers, tunnel POV with a 3D cartoon
character, surface scene, smooth HUD + word-pop captions, kokoro narrator voice, music + SFX.
Render: 540x960 traced, upscaled to 1080x1920 with bloom. ~0.3 s/frame on 2 cores.

Usage (from tools/sim3d):
  python3 tts_lines.py kitchen_fire_lines.json /tmp/tunnel_vo          # voice first (durations drive the timeline)
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

VO_DIR = '/tmp/kitchen_vo'
for i, a in enumerate(sys.argv):
    if a == '--vo':
        VO_DIR = sys.argv[i + 1]
LINES = json.load(open(os.path.join(HERE, 'kitchen_fire_lines.json')))['lines']
DURS = json.load(open(os.path.join(VO_DIR, 'durs.json')))
GAP, START0, TAIL = 0.22, 0.3, 1.8
EXTRA_GAP = {11: 1.4}   # thinking pause (3-2-1) before the answer reveal
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




KEYWORDS = {'FIRE', 'OIL', 'WATER', 'NEVER', 'STEAM', 'SEVENTEEN', 'HUNDRED', 'FIREBALL', 'CEILING', 'MYTH', 'NOPE', 'SPLASH', 'ERUPT', 'HEAT', 'LID', 'AIR', 'BAKING', 'SODA', 'FLOUR', 'BURNS', 'OUT', 'CALL', 'EMERGENCY', 'HEAVIER', 'BOTTOM', 'FLASHES', 'NINETY', 'METAL'}




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



# ----------------------------------------------------------------------------- NEW 2026-10-25: kitchen (room boxes, pan+oil+lid, flame/steam/fireball glow blobs)
PAN_C = (0.15, 2.75)
PAN_Z0, PAN_H, PAN_R = 0.97, 0.15, 0.36
RIM_Z = PAN_Z0 + PAN_H
OIL_Z = PAN_Z0 + PAN_H * 0.62
CHAR_S = 1.4
CHAR_T = np.array([-0.75, 1.75, 0.58 * CHAR_S], np.float32)
CHAR_YAW = -math.pi / 2


def _kb(lo, hi, col, tag):
    return (np.array(lo, np.float32), np.array(hi, np.float32), C(col), tag)


ROOM = [
    _kb((-3.2, -4, -0.3), (3.2, 3.6, 0), 'b9b2a6', 'floor'),
    _kb((-3.2, 3.4, 0), (3.2, 3.6, 3.1), 'eadcc2', 'wall'),
    _kb((-3.2, -4, 0), (-3.0, 3.6, 3.1), 'e3d4ba', 'wall'),
    _kb((3.0, -4, 0), (3.2, 3.6, 3.1), 'e3d4ba', 'wall'),
    _kb((-3.2, -4, 2.9), (3.2, 3.6, 3.1), 'f1ece0', 'ceil'),
    _kb((-2.6, 2.1, 0), (2.05, 3.4, 0.9), '8a5a3a', 'cab'),
    _kb((-2.65, 2.05, 0.9), (2.1, 3.4, 0.95), 'cfc8bc', 'top'),
    _kb((-0.55, 2.2, 0.9), (0.85, 3.3, 0.97), '1c1c20', 'stove'),
    _kb((2.15, 2.3, 0), (3.0, 3.4, 2.2), 'a8b0b8', 'steel'),
    _kb((1.2, 3.0, 1.75), (2.0, 3.4, 2.5), '8a5a3a', 'cab'),
    _kb((-0.55, 2.55, 1.95), (0.85, 3.4, 2.15), 'a8b0b8', 'steel'),
    _kb((-2.0, 3.35, 1.3), (-0.9, 3.4, 2.4), '9ed4ff', 'window'),
]


def trace_room(O, D, tmax):
    n = len(D)
    tb = tmax.copy()
    hit = np.zeros(n, bool)
    P = np.zeros((n, 3), np.float32)
    nor = np.zeros((n, 3), np.float32)
    idx_ = np.full(n, -1, np.int32)
    inv = 1.0 / np.where(np.abs(D) < 1e-6, 1e-6, D)
    for k, (lo, hi, base, tag) in enumerate(ROOM):
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
        ii = np.where(ok)[0]
        P[ii] = O + te[ok, None] * D[ok]
        nn = np.zeros((len(ii), 3), np.float32)
        nn[np.arange(len(ii)), ax] = -np.sign(D[ii, ax])
        nor[ii] = nn
        idx_[ii] = k
    return hit, tb, P, nor, idx_


def room_color(P, nor, idx_, fire, heat, soot, dim):
    n = len(P)
    base = np.zeros((n, 3), np.float32)
    for k, (lo, hi, col, tag) in enumerate(ROOM):
        m = idx_ == k
        if m.any():
            base[m] = col
    tags = np.array([r[3] for r in ROOM] + ['none'])[np.where(idx_ >= 0, idx_, len(ROOM))]
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    fl = tags == 'floor'
    if fl.any():
        chk = ((np.floor(x[fl] / 0.6) + np.floor(y[fl] / 0.6)) % 2)
        base[fl] = np.where(chk[:, None] > 0, C('d8d2c6')[None], C('8f8a82')[None])
    bs = (tags == 'wall') & (nor[:, 1] < -0.5) & (z > 0.95) & (z < 1.65)
    if bs.any():
        gx = ((x[bs] / 0.22) % 1.0) < 0.06
        gz = ((z[bs] / 0.22) % 1.0) < 0.06
        base[bs] = np.where((gx | gz)[:, None], C('b9ae98')[None], C('f4f0e6')[None])
    wd = tags == 'window'
    if wd.any():
        base[wd] = mix(C('bfe6ff'), C('ffffff'), np.clip((z[wd] - 1.3), 0, 1))
        frame = (np.abs(x[wd] + 1.45) < 0.04) | (np.abs(z[wd] - 1.85) < 0.04)
        base[np.where(wd)[0][frame]] = C('f5f5f5')
    # light
    lam = np.clip(nor @ KEY, 0, 1)
    shade = 0.7 + 0.3 * lam
    Lp = np.array([PAN_C[0], PAN_C[1], RIM_Z + 0.3 + 3.0 * max(0.0, fire - 0.9)], np.float32)
    d2 = ((P - Lp) ** 2).sum(1)
    fglow = (fire * (0.55 + 1.2 * max(0.0, fire - 0.9)) / (0.7 + d2))[:, None] * C('ff9a3c')[None] / 255.0
    col = base * shade[:, None] * (np.array([1.0, 0.96, 0.9], np.float32) * 0.55) + base * fglow
    # burner ring glow on the stove top
    st = (tags == 'stove') & (nor[:, 2] > 0.5)
    if st.any():
        rr = np.sqrt((x[st] - PAN_C[0]) ** 2 + (y[st] - PAN_C[1]) ** 2)
        ring = smooth(0.52, 0.46, rr) * smooth(0.25, 0.32, rr)
        col[st] = col[st] + (ring * heat)[:, None] * C('ff3a10')[None] * 0.9
    # soot on ceiling
    ce = tags == 'ceil'
    if ce.any() and soot > 0:
        rr = np.sqrt((x[ce] - PAN_C[0]) ** 2 + (y[ce] - PAN_C[1]) ** 2)
        sk = np.exp(-(rr / 1.3) ** 2) * soot
        col[ce] = col[ce] * (1 - 0.8 * sk)[:, None]
    return col * (1 - dim) + C('0a0a10') * dim * 0.4


def trace_pan(O, D, tb, lid, ft):
    """open pan with oil disc (+ optional lid {'x','z'} offsets). returns hit, t, colour"""
    n = len(D)
    cx, cy = PAN_C
    ox, oy = O[0] - cx, O[1] - cy
    dx, dy, dz = D[:, 0], D[:, 1], D[:, 2]
    a = np.maximum(dx * dx + dy * dy, 1e-8)
    b = ox * dx + oy * dy
    c_ = ox * ox + oy * oy - PAN_R * PAN_R
    disc = b * b - a * c_
    m = disc > 0
    s = np.sqrt(np.where(m, disc, 0))
    t1 = (-b - s) / a
    t2 = (-b + s) / a
    z1 = O[2] + t1 * dz
    z2 = O[2] + t2 * dz
    best = tb.copy()
    col = np.zeros((n, 3), np.float32)
    hit = np.zeros(n, bool)
    # outer wall
    ok = m & (t1 > 1e-3) & (z1 >= PAN_Z0) & (z1 <= RIM_Z) & (t1 < best)
    if ok.any():
        px = ox + t1[ok] * dx[ok]
        py = oy + t1[ok] * dy[ok]
        nn = np.stack([px, py, np.zeros_like(px)], 1) / PAN_R
        lam = np.clip(nn @ KEY, 0, 1)
        sp = np.clip((nn * nrm(KEY[None] * -1 + 0)).sum(1), 0, 1) ** 8
        col[ok] = C('2f333b')[None] * (0.55 + 0.7 * lam)[:, None] + (sp * 90)[:, None] + C('ff8a30')[None] * (0.25 * ft)
        best[ok] = t1[ok]
        hit |= ok
    # inner wall (ray enters through the open top)
    ok = m & (z1 > RIM_Z) & (t2 > 1e-3) & (z2 >= PAN_Z0) & (z2 <= RIM_Z) & (t2 < best)
    if ok.any():
        col[ok] = C('141519')[None] * (0.8 + 0.2 * ft) + C('ff7a20')[None] * (0.35 * ft)
        best[ok] = t2[ok]
        hit |= ok
    # oil surface
    with np.errstate(divide='ignore', invalid='ignore'):
        to = (OIL_Z - O[2]) / dz
    px = ox + to * dx
    py = oy + to * dy
    r2 = px * px + py * py
    ok = (to > 1e-3) & (r2 < (PAN_R - 0.025) ** 2) & (to < best) & (dz < 0)
    if ok.any():
        wx = px[ok] + cx
        wy = py[ok] + cy
        rip = _sample(ROCK, (wx * 60 + ft * 17) % 255, (wy * 60) % 255)
        oc = mix(C('5a3508'), C('c88a22'), rip)
        oc = oc + (ft * (0.4 + 0.6 * rip))[:, None] * C('ff7a1a')[None] * 0.5
        col[ok] = oc
        best[ok] = to[ok]
        hit |= ok
    # lid
    if lid is not None:
        lz = RIM_Z + 0.03 + lid['z']
        lcx, lcy = cx + lid['x'], cy
        with np.errstate(divide='ignore', invalid='ignore'):
            tl = (lz - O[2]) / dz
        qx = O[0] + tl * dx - lcx
        qy = O[1] + tl * dy - lcy
        rr = np.sqrt(qx * qx + qy * qy)
        ok = (tl > 1e-3) & (rr < PAN_R * 1.1) & (tl < best)
        if ok.any():
            ring = 0.88 + 0.12 * np.sin(rr[ok] * 70)
            lc = C('b4bcc6')[None] * ring[:, None] * (0.85 + 0.25 * np.clip(1 - rr[ok] / (PAN_R * 1.1), 0, 1))[:, None]
            col[ok] = lc
            best[ok] = tl[ok]
            hit |= ok
    return hit, best, col


# ---- glow blobs (flames, steam, fireball, smoke) composited in screen space
def add_blob(img, cam, P, r, color, k, mode='add', ay=1.0):
    q = cam.project(P)
    if q is None:
        return
    z = float((np.array(P, np.float32) - cam.pos) @ cam.f)
    rpx = r / (z * cam.th) * RH / 2
    if rpx < 0.8:
        return
    px, py = q[0] / 2, q[1] / 2
    ry = rpx * ay
    x0, x1 = int(max(0, px - 2.6 * rpx)), int(min(RW, px + 2.6 * rpx + 1))
    y0, y1 = int(max(0, py - 2.6 * ry)), int(min(RH, py + 2.6 * ry + 1))
    if x1 <= x0 or y1 <= y0:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    g = np.exp(-(((xx - px) / rpx) ** 2 + ((yy - py) / ry) ** 2))
    if mode == 'add':
        img[y0:y1, x0:x1] += g[..., None] * (np.asarray(color, np.float32) * k)[None, None]
    else:
        a = np.clip(g * k, 0, 1)[..., None]
        img[y0:y1, x0:x1] = img[y0:y1, x0:x1] * (1 - a) + np.asarray(color, np.float32)[None, None] * a


def flame_blobs(t, fire, scale=1.0, c=PAN_C, z=RIM_Z, R=0.30):
    out = []
    if fire <= 0.01:
        return out
    for j in range(16):
        ph = j * 2.399
        r = R * 0.8 * math.sqrt((j + 0.5) / 16)
        px, py = c[0] + r * math.cos(ph), c[1] + r * math.sin(ph)
        fl = math.sin(t * (9 + j % 5) + j * 1.7) * 0.5 + 0.5
        for lv, (col, k) in enumerate(((255 * np.array([1.0, 0.82, 0.35]), 0.17), (255 * np.array([1.0, 0.45, 0.1]), 0.15), (255 * np.array([0.85, 0.2, 0.06]), 0.12))):
            hh = (0.06 + lv * 0.16 * (0.65 + 0.5 * fl)) * fire * scale
            rad = (0.065 - lv * 0.014) * (0.5 + 0.5 * fire) * scale
            out.append(('add', (px + 0.03 * math.sin(t * 6 + j + lv), py, z + 0.02 + hh), rad, col, k, 1.6))
    return out


def eruption_blobs(t, t0, power=1.0, seed=3):
    p = t - t0
    if p < 0 or p > 3.0:
        return [], 0.0
    rng = np.random.default_rng(seed)
    out = []
    rise = min(p / 0.55, 1.0)
    fadeb = max(0.0, 1.0 - max(0.0, p - 0.7) / 1.6)
    top = RIM_Z + (2.9 - RIM_Z - 0.1) * power
    for j in range(26):
        ang = rng.uniform(0, 2 * math.pi)
        rr = rng.uniform(0, 0.5) * power
        h = rng.uniform(0.15, 1.0)
        zc = RIM_Z + (top - RIM_Z) * h * ease(rise)
        spread = (0.2 + 0.7 * h) * ease(min(1.0, p / 0.7)) * power
        pos = (PAN_C[0] + rr * math.cos(ang) * 0.6 + spread * math.cos(ang) * 0.9, PAN_C[1] + rr * math.sin(ang) * 0.25 - 0.1 * spread, zc)
        rad = (0.16 + 0.28 * rng.random()) * (0.5 + 0.8 * ease(rise)) * (0.5 + 0.5 * power)
        col = 255 * np.array([1.0, 0.65 - 0.4 * h, 0.2 - 0.12 * h])
        out.append(('add', pos, rad, col, 0.55 * fadeb, 1.0))
    # burning droplets
    for j in range(40):
        ang = rng.uniform(0, 2 * math.pi)
        sp = rng.uniform(1.0, 3.2) * power
        vz = rng.uniform(1.8, 4.2) * power
        x_ = PAN_C[0] + sp * math.cos(ang) * p * 0.75
        y_ = PAN_C[1] + sp * math.sin(ang) * p * 0.45
        z_ = RIM_Z + vz * p - 4.5 * p * p
        if 0.1 < z_ < 2.85:
            out.append(('add', (x_, y_, z_), 0.045, 255 * np.array([1.0, 0.7, 0.2]), 1.2 * fadeb, 1.4))
    # smoke
    if p > 0.35:
        for j in range(10):
            ang = rng.uniform(0, 2 * math.pi)
            zc = min(2.8, RIM_Z + 0.4 + (p - 0.3) * 1.3 + 0.2 * j * 0.1)
            out.append(('mix', (PAN_C[0] + 0.5 * math.cos(ang), PAN_C[1] + 0.3 * math.sin(ang), zc - 0.15 * j * 0.2), 0.35 + 0.1 * j * 0.1, np.array([40, 36, 36]), 0.5 * min(1, (p - 0.35) / 0.5), 1.0))
    fire_light = max(0.0, 1.0 - abs(p - 0.4) / 1.2) * power
    return out, fire_light


def steam_blobs(t, amt, t0=0.0):
    out = []
    if amt <= 0.01:
        return out
    for j in range(9):
        ph = (t * 0.9 + j * 0.37) % 1.0
        out.append(('mix', (PAN_C[0] + 0.12 * math.sin(j * 2.1 + t * 2), PAN_C[1] + 0.1 * math.cos(j * 1.7), RIM_Z + 0.05 + ph * 0.9 * amt), 0.10 + 0.22 * ph * amt,
                    np.array([235, 240, 245]), 0.55 * (1 - ph) * min(1, amt), 1.0))
    return out


def kitchen(t, cam, st, ch=None, extra=None, vig=0.0, dim=0.0):
    D = cam.rays()
    O = cam.pos
    n = len(D)
    # background: ceiling/walls are boxes, so everything hits; fall back to dark
    col = np.tile(C('202228')[None], (n, 1))
    tb = np.full(n, 1e9, np.float32)
    hit, tbx, P, nor, idx_ = trace_room(O, D, tb)
    if hit.any():
        hi = np.where(hit)[0]
        col[hi] = room_color(P[hi], nor[hi], idx_[hi], st['firelight'], st['heat'], st['soot'], dim)
        tb[hi] = tbx[hi]
    phit, pbest, pcol = trace_pan(O, D, tb, st.get('lid'), st['fire'])
    if phit.any():
        col[phit] = pcol[phit]
        tb[phit] = pbest[phit]
    prims = []
    if ch is not None:
        Rw = np.array([[1, 0, 0], [0, 0, 1], [0, 1, 0]], np.float32)
        s = ch.get('s', CHAR_S)
        T = np.array([ch.get('x', CHAR_T[0]), ch.get('y', CHAR_T[1]), 0.58 * s + ch.get('lift', 0.0)], np.float32)
        R = Rw @ rotm(ch.get('lean', 0.0), ch.get('yaw', CHAR_YAW), ch.get('roll', 0.0))
        if ch.get('grab') is not None:
            g = np.array(ch['grab'], np.float32) - T
            gl = (R.T @ g) / s
            nlen = np.linalg.norm(gl)
            if nlen > 0.85:
                gl = gl / nlen * 0.85
            cp = char_prims(t, scream=ch.get('scream', 0.3), flail=ch.get('flail', 0.2), grab=tuple(gl))
        else:
            cp = char_pose(t, ch.get('pose', 'up'), scream=ch.get('scream', 0.3), flail=ch.get('flail', 0.2))
        prims += place(scale_prims(cp, s), R, T)
    for k_, d_, c_ in (extra or []):
        if k_ == 'sph':
            prims.append((k_, (np.asarray(d_[0], np.float32), float(d_[1])), c_))
        else:
            prims.append((k_, (np.asarray(d_[0], np.float32), np.asarray(d_[1], np.float32), float(d_[2])), c_))
    # pan handle
    hd0 = np.array([PAN_C[0] - PAN_R + 0.02, PAN_C[1] - 0.04, PAN_Z0 + 0.09], np.float32)
    hd1 = np.array([PAN_C[0] - PAN_R - 0.45, PAN_C[1] - 0.22, PAN_Z0 + 0.12], np.float32)
    prims.append(('cap', (hd0, hd1, 0.025), C('15161a')))
    if st.get('lid') is not None:
        lz = RIM_Z + 0.03 + st['lid']['z'] + 0.03
        prims.append(('sph', (np.array([PAN_C[0] + st['lid']['x'], PAN_C[1], lz + 0.02], np.float32), 0.04), C('15161a')))
    hitc, tt, nn, cb = trace_prims(O, D, prims, tb)
    if hitc.any():
        fl = st['firelight']
        sc = shade_char(D[hitc], nn[hitc], cb[hitc], KEY, C('ff9a3c') * (0.25 + 0.5 * fl) + C('ffffff') * 0.1)
        col[hitc] = sc * 0.95
    col = col.reshape(RH, RW, 3)
    for mode, Pw, r, cc, k, ay in st['blobs']:
        add_blob(col, cam, Pw, r, cc, k, mode, ay)
    if vig > 0:
        r2 = ((_PX / RW * 2 - 1) ** 2 + (_PY / RH * 2 - 1) ** 2)
        col = col * (1 - vig * np.clip(r2 * 0.9, 0, 1))[..., None]
    return col


# ----------------------------------------------------------------------------- timeline
TH0 = L(0) + max(0.9, DURS[0] - 0.8)          # the water cup starts flying
TH1 = L(1) + 0.18                              # water enters the oil
T_SINK = (TH1, L(2) + 0.2)                     # drop sinks to the bottom
TB4 = L(4) + 0.12                              # eruption
T_HOT = L(3)                                   # steam builds
TB5 = SPLIT5 = None
SPLIT = {0: L(0) + DURS[0] * 0.42, 1: L(1) + DURS[1] * 0.5, 2: L(2) + DURS[2] * 0.5, 3: L(3) + DURS[3] * 0.5,
         4: L(4) + DURS[4] * 0.38, 5: L(5) + DURS[5] * 0.5, 6: L(6) + DURS[6] * 0.5, 7: L(7) + DURS[7] * 0.5,
         8: L(8) + DURS[8] * 0.5, 9: L(9) + DURS[9] * 0.5}
CUTS = sorted(list(STARTS[1:]) + list(SPLIT.values()))
TB5 = L(5) + 0.95                              # tiny splash erupts
T_LID = (SPLIT[6] + 0.1, SPLIT[6] + 0.75)      # lid slides on
T_OFF = L(6) + 0.55                            # heat switched off
SPOON = SPLIT[8]


def scene_of(t):
    for i in range(len(STARTS) - 1, -1, -1):
        if t >= STARTS[i] - 0.11:
            return i
    return 0


def half_of(i, t):
    return 1 if (i in SPLIT and t >= SPLIT[i]) else 0


def state_at(t, i):
    """world state: fire level, heat, lid, blobs"""
    fire, heat, soot, lid = 1.0, 1.0, 0.0, None
    blobs = []
    fl_extra = 0.0
    if t >= TB4:
        soot = min(1.0, (t - TB4) / 2.0)
    # fire level through the story
    if t < TB4:
        fire = 1.0
    elif t < TB5 - 0.2:
        fire = 0.75
    elif t < T_LID[1]:
        fire = 0.75
    if t >= TB5:
        fire = max(fire, 0.8)
    if t >= T_OFF:
        heat = max(0.0, 1.0 - (t - T_OFF) / 0.4)
    if t >= T_LID[0]:
        k = ease((t - T_LID[0]) / (T_LID[1] - T_LID[0]))
        lid = {'x': 1.1 * (1 - k), 'z': 0.5 * (1 - k) ** 2}
        if k >= 1.0:
            lid = {'x': 0.0, 'z': 0.0}
        fire = fire * (1 - ease((t - T_LID[1] + 0.25) / 0.25))
    # scene 8 small fire (separate replay), scene 9 spreading fire
    if i == 8:
        lid = None
        heat = 0.0
        if t < SPOON:
            fire = 0.45
            powder = ease((t - (L(8) + 0.35)) / 0.5)
            fire = 0.45 * (1 - powder)
        else:
            fire = 0.5 + 0.9 * ease((t - SPOON - 0.5) / 0.4)
            fire = fire if fire < 1.4 else 1.4
    if i == 9:
        lid = None
        heat = 1.0
        fire = 1.0
        soot = 0.6
    if i >= 10:
        lid = {'x': 0.0, 'z': 0.0}
        fire = 0.0
        heat = 0.0
    # eruption blobs
    fl_light = fire * 0.9
    e1, light1 = eruption_blobs(t, TB4, 1.0, seed=3)
    blobs += e1
    fl_light = max(fl_light, light1 * 1.4)
    if i == 5:
        e2, light2 = eruption_blobs(t, TB5, 0.42, seed=8)
        blobs += e2
        fl_light = max(fl_light, light2 * 1.2)
        if TB5 - 0.9 <= t < TB5:
            pass
    blobs += flame_blobs(t, fire * (1.25 if i == 9 else 1.0), scale=(1.0 if i != 8 else 0.55), z=RIM_Z)
    if i == 9:
        for j in range(8):
            blobs += [('add', (0.15 + 0.5 * math.sin(j * 1.9 + t * 3), 3.15, 1.0 + 0.25 * j * 0.5 + 0.1 * math.sin(t * 9 + j)), 0.16, 255 * np.array([1.0, 0.5, 0.12]), 0.2, 1.6)]
    # steam before the blast
    steam = 0.0
    if TH1 + 0.6 <= t < TB4:
        steam = ease((t - TH1 - 0.6) / 2.0)
    if TB5 - 0.5 < t < TB5 + 1.5 and i == 5:
        steam = max(steam, 0.5)
    if t >= T_LID[0] - 0.1 and t < T_LID[1] + 0.8:
        steam = max(steam, 0.7 * (1 - ease((t - T_LID[0]) / 0.9)))
    blobs += steam_blobs(t, steam)
    # smoke after lid
    if lid is not None and i == 7:
        blobs += steam_blobs(t, 0.15)
    firelight = min(1.6, fl_light)
    return dict(fire=fire, heat=heat, soot=soot, lid=lid, blobs=blobs, firelight=firelight)


def water_prims(t):
    """thrown water cup/ball and the tiny drop of scene 5, baking soda powder etc. returns (prims, hand_grab)"""
    prims = []
    grab = None
    W_C = C('59b8ff')
    start = np.array([CHAR_T[0] + 0.55, CHAR_T[1] + 0.1, 1.55], np.float32)
    target = np.array([PAN_C[0], PAN_C[1], OIL_Z + 0.02], np.float32)
    if t < TH0:
        k = ease((t - L(0)) / max(0.1, TH0 - L(0)))
        pos = start + np.array([-0.1 * k, 0, 0.1 * math.sin(t * 5)], np.float32)
        grab = pos
        prims.append(('sph', (pos, 0.12), W_C))
        prims.append(('cap', (pos + np.array([0, 0, -0.12], np.float32), pos + np.array([0, 0, 0.05], np.float32), 0.14), C('f2f2f5')))
        prims.append(('sph', (pos + np.array([0, 0, 0.06], np.float32), 0.13), W_C))
    elif t < TH1:
        k = (t - TH0) / (TH1 - TH0)
        pos = start + (target - start) * k + np.array([0, 0, 0.55 * math.sin(math.pi * k)], np.float32)
        if k < 0.45:
            grab = pos
        else:
            grab = start + (target - start) * 0.45 + np.array([0, 0, 0.55 * math.sin(math.pi * 0.45)], np.float32)
        prims.append(('sph', (pos, 0.11), W_C))
        for j in range(4):
            prims.append(('sph', (pos + np.array([0.05 * math.sin(j * 2.3 + t * 30), 0.05 * math.cos(j * 1.7), -0.06 * j], np.float32), 0.04), W_C))
    return prims, grab


def tiny_drop(t):
    if TB5 - 0.9 <= t < TB5:
        k = (t - (TB5 - 0.9)) / 0.9
        z = 2.3 + (OIL_Z + 0.03 - 2.3) * k * k
        return [('sph', (np.array([PAN_C[0] + 0.05, PAN_C[1] + 0.02, z], np.float32), 0.035), C('59b8ff'))]
    return []


def cam_for(i, h, t):
    if i in SPLIT and h == 1:
        t0, t1 = SPLIT[i], (STARTS[i + 1] if i + 1 < len(STARTS) else DUR)
    elif i in SPLIT:
        t0, t1 = L(i), SPLIT[i]
    else:
        t0, t1 = L(i), (STARTS[i + 1] if i + 1 < len(STARTS) else DUR)
    k = min(1.0, max(0.0, (t - t0) / max(0.2, t1 - t0)))
    e = ease(k)
    pc = (PAN_C[0], PAN_C[1], 1.1)
    if i == 0 and h == 0:      # wide kitchen, push in, fire raging
        return Cam((0.7 - 0.2 * e, -2.4 + 1.2 * e, 1.8 - 0.2 * e), (-0.1, 2.6, 1.1), fov=56)
    if i == 0:                 # hand with the cup
        return Cam((-0.2 + 0.2 * e, -0.2, 1.8), (-0.1 + 0.3 * e, 2.3, 1.3), fov=50)
    if i == 1 and h == 0:      # low-ish: drop hits the oil
        return Cam((0.9 - 0.2 * e, 0.4, 1.7 - 0.15 * e), (0.15, 2.75, 1.1), fov=34)
    if i == 1:
        return Cam((0.7, -0.5, 1.9 - 0.2 * e), pc, fov=40)
    if i == 2 and h == 0:
        return Cam((0.5 + 0.1 * e, 0.0, 1.7), pc, fov=38 - 4 * e)
    if i == 2:
        return Cam((-0.5 + 0.3 * e, 0.2, 1.5), pc, fov=36 - 4 * e, roll=0.05 - 0.05 * e)
    if i == 3 and h == 0:
        return Cam((0.6 + 0.2 * e, 0.1, 1.5), pc, fov=36 - 4 * e)
    if i == 3:
        return Cam((0.9, -0.3, 1.7), (0.15, 2.75, 1.3), fov=44 - 6 * e, roll=0.04 * math.sin(t * 20))
    if i == 4 and h == 0:      # blast from a low wide angle
        return Cam((0.5, -1.2, 1.1), (0.15, 2.75, 1.6 + 0.3 * e), fov=64)
    if i == 4:                 # ceiling view
        return Cam((-0.4, 0.0, 1.2), (0.15, 2.6, 2.2), fov=68 - 6 * e)
    if i == 5 and h == 0:
        return Cam((0.6 - 0.2 * e, 0.0, 1.7), pc, fov=36 - 3 * e)
    if i == 5:
        return Cam((-0.7, -0.5, 1.2), (0.15, 2.7, 1.5), fov=62)
    if i == 6 and h == 0:      # burner / heat off
        return Cam((1.0, 0.3, 1.4), (0.15, 2.7, 1.0), fov=44 + 6 * e)
    if i == 6:                 # lid slides on
        return Cam((0.5 - 0.3 * e, 0.2, 1.8), pc, fov=38)
    if i == 7 and h == 0:
        return Cam((0.15, 0.2, 1.9 - 0.1 * e), (0.15, 2.75, 1.05), fov=36 - 6 * e)
    if i == 7:
        return Cam((-0.5 + 0.3 * e, -0.8, 1.6), (0.0, 2.7, 1.2), fov=56)
    if i == 8:
        return Cam((0.6 - 0.2 * e, 0.4, 1.8), (0.1, 2.75, 1.15), fov=40)
    if i == 9 and h == 0:      # character runs for the exit
        return Cam((-0.3, -1.2, 1.6), (-1.0 - 0.8 * e, 1.8, 1.1), fov=60)
    if i == 9:
        return Cam((0.6, -1.0, 1.5), (0.15, 2.8, 1.3), fov=62 - 6 * e)
    return Cam((0.45, -1.0 + 0.4 * e, 1.7), (0.15, 2.6, 1.05), fov=56)


def render_frame(fi):
    t = fi / FPS
    i = scene_of(t)
    h = half_of(i, t)
    cam = cam_for(i, h, t)
    st = state_at(t, i)
    red, flash, zoom = 0.0, 0.0, 1.0
    ch = dict(pose='up', scream=0.3, flail=0.2)
    extra, grab = water_prims(t) if i <= 1 else ([], None)
    if i == 5:
        extra = tiny_drop(t)
    if i == 0:
        ch.update(grab=grab, scream=0.4, flail=0.3)
        if grab is None:
            ch['pose'] = 'point'
    elif i == 1:
        ch.update(pose='cower', scream=0.6, flail=0.2)
    elif i == 2:
        ch.update(pose='ears', scream=0.8, x=-0.95)
    elif i == 3:
        ch.update(pose='cower', scream=1.0, x=-1.0)
    elif i == 4:
        p_ = t - TB4
        ch.update(pose='up', scream=1.0, flail=1.0)
        if p_ > 0:
            ch.update(x=-0.75 - 0.9 * ease(p_ / 0.5), lift=0.25 * math.sin(min(1, p_ / 0.7) * math.pi), lean=0.5 * ease(p_ / 0.4), yaw=CHAR_YAW + 0.7 * ease(p_ / 0.6))
    elif i == 5:
        ch.update(pose='flex', scream=0.2, flail=0.1)
        if h == 1:
            ch.update(pose='cower', scream=1.0)
    elif i == 6:
        ch.update(pose='flex', scream=0.1, flail=0.1)
        if t >= T_LID[0]:
            lid = st['lid']
            ch.update(grab=np.array([PAN_C[0] + lid['x'] - 0.1, PAN_C[1] - 0.25, RIM_Z + 0.06 + lid['z']], np.float32), pose='up')
    elif i == 7:
        ch.update(pose='flex', scream=0.0, flail=0.1)
    elif i == 8:
        ch.update(pose='point', scream=0.2, x=-0.5)
        bx = np.array([-0.15, 2.1, 1.75], np.float32)
        extra = [('cap', (bx, bx + np.array([0.0, 0.0, 0.0], np.float32) + np.array([0.0, 0.12, 0.0], np.float32), 0.1), C('2d7ad6' if h == 0 else 'd9c9a0'))]
        k_ = ease((t - (L(8) + 0.2)) / 0.4) if h == 0 else ease((t - (SPOON + 0.15)) / 0.4)
        for j in range(14):
            ph_ = (t * 2.2 + j * 0.31) % 1.0
            if k_ > 0 and ((h == 0 and t < SPOON) or (h == 1 and t >= SPOON)):
                extra.append(('sph', (np.array([bx[0] + 0.1 * math.sin(j * 3.1) , bx[1] + 0.3 + 0.35 * ph_, 1.7 - 0.55 * ph_], np.float32), 0.025), C('ffffff' if h == 0 else 'e8d9a8')))
    elif i == 9:
        k = (t - L(9)) / (STARTS[10] - L(9))
        ch.update(pose='up', scream=1.0, flail=1.0, x=-0.75 - 1.7 * ease(k), y=1.75 - 0.5 * ease(k), yaw=CHAR_YAW - 1.0 * ease(min(1, k * 2)), lean=0.0)
        red = 0.25
    else:
        ch.update(pose='flex' if i == 11 else 'point', scream=0.0, flail=0.1, x=-0.75)
    cp_c = dict(ch)
    if i == 8:
        cp_c['pose'] = 'point'
    # camera shake
    if TB4 <= t < TB4 + 1.2 and i == 4:
        a_ = 0.07 * math.exp(-(t - TB4) * 3.0)
        cam.pos = cam.pos + np.array([a_ * math.sin(t * 61), a_ * math.sin(t * 47 + 1), a_ * math.sin(t * 53 + 2)], np.float32)
        flash = max(flash, 0.7 * max(0.0, 1 - (t - TB4) / 0.35))
        red = max(red, 0.3 * math.exp(-(t - TB4) * 1.5))
        zoom = max(zoom, 1 + 0.12 * math.exp(-(t - TB4) * 5))
    if TB5 <= t < TB5 + 0.6 and i == 5:
        a_ = 0.03 * math.exp(-(t - TB5) * 4.0)
        cam.pos = cam.pos + np.array([a_ * math.sin(t * 61), a_ * math.sin(t * 47 + 1), 0], np.float32)
        flash = max(flash, 0.35 * max(0.0, 1 - (t - TB5) / 0.2))
    dim = 0.45 if i >= 10 else 0.0
    col = kitchen(t, cam, st, ch=cp_c, extra=extra, vig=0.0, dim=dim)
    for b in CUTS:
        if b - 0.11 <= t < b + 0.12:
            p_ = (t - (b - 0.11)) / 0.23
            flash = max(flash, 0.4 * (1 - abs(p_ * 2 - 1)))
            zoom = max(zoom, 1 + 0.12 * (1 - ease(p_)))
    zoom *= 1 + 0.04 * ((t * 1.7) % 1.0)
    img = post(col, red=red, flash=flash, zoom=zoom).convert('RGBA')
    overlays(img, t, i, h, cam)
    hud(img, t, i)
    if t >= L(10):
        choice_cards(img, t, L(10))
    caption(img, t)
    return img.convert('RGB')


# ----------------------------------------------------------------------------- side-view inset card (water sinks / flashes / expands)
def _card(img, x0, y0, x1, y1):
    d = ImageDraw.Draw(img, 'RGBA')
    d.rounded_rectangle([x0, y0, x1, y1], 36, fill=(8, 12, 28, 205), outline=(255, 255, 255, 80), width=3)
    return d


def inset(img, t, i, h):
    x0, y0, x1, y1 = 150, 470, 930, 900
    d = _card(img, x0, y0, x1, y1)
    cx = (x0 + x1) // 2
    # pan side view
    px0, px1, py0, py1 = cx - 270, cx + 270, 640, 800
    oil_top = 680
    if i == 3:
        py0 = py1 = -1000
    if i != 3:
        d.rectangle([px0, oil_top, px1, py1], fill=(206, 134, 34, 255))
        d.rectangle([px0 - 22, 630, px0, py1 + 22], fill=(70, 74, 84, 255))
        d.rectangle([px1, 630, px1 + 22, py1 + 22], fill=(70, 74, 84, 255))
        d.rectangle([px0 - 22, py1, px1 + 22, py1 + 22], fill=(70, 74, 84, 255))
        # flames on the surface
        for j in range(9):
            fx = px0 + 30 + j * 62
            hh = 38 + 24 * (math.sin(t * 9 + j * 1.9) * 0.5 + 0.5)
            d.polygon([(fx - 26, oil_top), (fx, oil_top - hh), (fx + 26, oil_top)], fill=(255, 130, 30, 255))
            d.polygon([(fx - 13, oil_top), (fx, oil_top - hh * 0.6), (fx + 13, oil_top)], fill=(255, 220, 90, 255))
    f = Q.font(Q.F_BLACK, 40)
    if i == 1:
        k = ease((t - TH1) / (T_SINK[1] - TH1 + 0.001))
        yy = 520 + (py1 - 34 - 520) * k
        r = 30
        d.ellipse([cx - r, yy - r, cx + r, yy + r], fill=(89, 184, 255, 255), outline=(255, 255, 255, 255), width=4)
        d.text((px0 + 14, oil_top + 14), 'OIL 0.92', font=f, fill=(255, 255, 255, 255), stroke_width=5, stroke_fill=(0, 0, 0, 255))
        d.text((cx + 80, 540 + 140 * k), 'WATER 1.00', font=f, fill=(150, 215, 255, 255), stroke_width=5, stroke_fill=(0, 0, 0, 255))
        # arrow
        d.line([cx + 160, 510, cx + 160, 600], fill=(255, 255, 255, 220), width=8)
        d.polygon([(cx + 140, 595), (cx + 180, 595), (cx + 160, 635)], fill=(255, 255, 255, 220))
    elif i == 2:
        k = ease((t - L(2)) / DURS[2])
        by = py1 - 34
        r = 24 + 120 * ease(k * 1.6)
        sh = 6 * math.sin(t * 50) * k
        d.ellipse([cx - r + sh, by - r, cx + r + sh, by + r - 6], fill=(240, 245, 255, 235), outline=(255, 255, 255, 255), width=4)
        d.text((cx - 120, by - 10), 'STEAM', font=f, fill=(40, 60, 90, 255)) if r > 90 else None
        d.text((px0 + 14, oil_top + 14), '190+ C', font=f, fill=(255, 255, 255, 255), stroke_width=5, stroke_fill=(0, 0, 0, 255))
    else:
        k = ease((t - L(3)) / DURS[3])
        # 1 unit of water vs 1,700 units of steam
        d.rectangle([x0 + 90, 760 - 40, x0 + 130, 760], fill=(89, 184, 255, 255))
        d.text((x0 + 70, 770), 'WATER', font=Q.font(Q.F_BOLD, 34), fill=(150, 215, 255, 255))
        R_ = 40 + 190 * k
        d.ellipse([cx + 80 - R_ * 0.8, 650 - R_ * 0.6, cx + 80 + R_ * 0.8, 650 + R_ * 0.6], fill=(240, 245, 255, 235))
        d.ellipse([cx + 80 - R_ * 0.4 - 40, 650 - R_ * 0.7, cx + 80 + R_ * 0.5, 650 + R_ * 0.3], fill=(250, 252, 255, 235))
        n_ = int(1 + 1699 * ease(k * 1.15))
        txt = f'x{n_:,}'
        fb = Q.font(Q.F_BLACK, 84)
        tw_ = d.textlength(txt, font=fb)
        d.text((cx + 80 - tw_ / 2, 618), txt, font=fb, fill=(25, 40, 80, 255))


def draw_check(d, cx, cy, r, ok):
    col = (30, 170, 80, 255) if ok else (230, 50, 60, 255)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col, outline=(255, 255, 255, 255), width=6)
    if ok:
        d.line([(cx - r * 0.45, cy), (cx - r * 0.1, cy + r * 0.38), (cx + r * 0.5, cy - r * 0.4)], fill=(255, 255, 255, 255), width=14, joint='curve')
    else:
        d.line([(cx - r * 0.4, cy - r * 0.4), (cx + r * 0.4, cy + r * 0.4)], fill=(255, 255, 255, 255), width=14)
        d.line([(cx - r * 0.4, cy + r * 0.4), (cx + r * 0.4, cy - r * 0.4)], fill=(255, 255, 255, 255), width=14)


def overlays(img, t, i, h, cam):
    d = ImageDraw.Draw(img, 'RGBA')
    if i == 0 and h == 0:
        _sticker(img, 'GREASE FIRE', 110, REDC, W / 2, 640, -5, ease((t - L(0) - 0.15) / 0.15))
    if i == 0 and h == 1:
        _sticker(img, 'NEVER', 190, REDC, W / 2, 640, 5, ease((t - SPLIT[0]) / 0.15), sub='pour water on it')
    if i in (1, 2, 3):
        inset(img, t, i, h)
    if i == 1:
        _sticker(img, 'HEAVIER', 110, CYAN, W / 2, 1000, -4, ease((t - L(1) - 0.3) / 0.15), sub='water sinks')
    if i == 2:
        _sticker(img, 'FLASH!', 140, YEL, W / 2, 1000, 4, ease((t - L(2) - 1.3) / 0.15), sub='water boils at 100 C')
    if i == 3:
        _sticker(img, '1,700x', 150, YEL, W / 2, 1010, -4, ease((t - L(3) - 0.9) / 0.15), sub='more room')
    if i == 4:
        if t >= TB4:
            _sticker(img, 'BOOM', 280, REDC, W / 2, 620, -6, ease((t - TB4) / 0.12))
        if h == 1:
            _sticker(img, 'FIREBALL', 110, YEL, W / 2, 900, 5, ease((t - SPLIT[4]) / 0.15), sub='up to the ceiling')
    if i == 5 and h == 0:
        _sticker(img, 'MYTH', 190, (255, 255, 255), W / 2, 560, -6, ease((t - L(5) - 0.2) / 0.15))
        _sticker(img, 'TINY SPLASH = SAFE', 64, YEL, W / 2, 790, 4, ease((t - L(5) - 0.5) / 0.15))
    if i == 5 and h == 1:
        _sticker(img, 'NOPE', 230, REDC, W / 2, 620, -6, ease((t - SPLIT[5]) / 0.12), sub='still erupts')
    if i == 6 and h == 0:
        _sticker(img, 'HEAT OFF', 140, GRN, W / 2, 620, -4, ease((t - L(6) - 0.1) / 0.15))
    if i == 6 and h == 1:
        _sticker(img, 'METAL LID', 130, YEL, W / 2, 620, 4, ease((t - SPLIT[6] - 0.05) / 0.15), sub='on top, stays on')
    if i == 7:
        _sticker(img, 'NO AIR', 150, CYAN, W / 2, 560, -4, ease((t - L(7) - 0.1) / 0.15))
        _sticker(img, 'NO FIRE', 150, YEL, W / 2, 780, 4, ease((t - L(7) - 0.9) / 0.15))
    if i == 8 and h == 0:
        _sticker(img, 'BAKING SODA', 100, GRN, W / 2, 620, -4, ease((t - L(8) - 0.1) / 0.15))
        if t > L(8) + 1.0:
            draw_check(d, W / 2, 850, 70 * (1.4 - 0.4 * ease((t - L(8) - 1.0) / 0.2)), True)
    if i == 8 and h == 1:
        _sticker(img, 'FLOUR', 140, REDC, W / 2, 620, 4, ease((t - SPLIT[8]) / 0.15), sub='just burns')
        if t > SPLIT[8] + 0.9:
            draw_check(d, W / 2, 880, 70 * (1.4 - 0.4 * ease((t - SPLIT[8] - 0.9) / 0.2)), False)
    if i == 9:
        _sticker(img, 'GET OUT', 170, REDC, W / 2, 600, -5, ease((t - L(9) - 0.1) / 0.15))
        if t > L(9) + 1.0:
            _sticker(img, 'CALL FOR HELP', 80, YEL, W / 2, 820, 4, ease((t - L(9) - 1.0) / 0.15))
    if L(10) + DURS[10] <= t < L(11):
        k = (t - L(10) - DURS[10]) / (L(11) - L(10) - DURS[10])
        n_ = 3 - int(k * 3)
        _sticker(img, str(max(1, n_)), 200, YEL, W / 2, 1180, 0, ease(((k * 3) % 1.0) / 0.2))


def hud(img, t, i):
    d = ImageDraw.Draw(img, 'RGBA')
    if t > L(10) - 0.05:
        return
    h = half_of(i, t)
    y = 190
    if i == 0:
        y = pill(d, 50, y, 'OIL FIRE', 'BURNING', REDC, w=520)
        y = pill(d, 50, y, 'OIL TEMP', '190+ C', YEL, w=520)
    elif i == 1:
        y = pill(d, 50, y, 'OIL', '0.92 g/cm3', YEL, w=520)
        y = pill(d, 50, y, 'WATER', '1.00 g/cm3', CYAN, w=520)
    elif i == 2:
        y = pill(d, 50, y, 'OIL TEMP', '190+ C', REDC, w=520)
        y = pill(d, 50, y, 'WATER BOILS', '100 C', CYAN, w=520)
    elif i == 3:
        n_ = int(1 + 1699 * ease((t - L(3)) / DURS[3] * 1.15))
        y = pill(d, 50, y, 'VOLUME', f'x{n_:,}', YEL, w=520)
        y = pill(d, 50, y, 'PRESSURE', 'BUILDING', REDC, w=520)
    elif i == 4:
        y = pill(d, 50, y, 'STATUS', 'ERUPTION' if t >= TB4 else 'STEAM', REDC, w=520)
        if t >= TB4:
            y = pill(d, 50, y, 'FLAMES', 'EVERYWHERE', REDC, w=520)
    elif i == 5:
        y = pill(d, 50, y, 'SPLASH', 'TINY', CYAN, w=520)
        if t >= TB5:
            y = pill(d, 50, y, 'RESULT', 'STILL BOOM', REDC, w=520)
    elif i == 6:
        y = pill(d, 50, y, 'HEAT', 'OFF' if t >= T_OFF else 'ON', GRN if t >= T_OFF else REDC, w=520)
        if t >= T_LID[0]:
            y = pill(d, 50, y, 'LID', 'SLIDING ON' if t < T_LID[1] else 'ON', YEL if t < T_LID[1] else GRN, w=520)
    elif i == 7:
        k = ease((t - L(7) - 0.3) / 1.3)
        y = bar_pill(d, 50, y, 'OXYGEN', 1.0 * (1 - k) * (1.2 / 1.0) * 0.83, f'{21 * (1 - k):.0f}%', CYAN if k < 0.8 else REDC)
        y = pill(d, 50, y, 'FIRE', 'OUT' if k > 0.9 else 'DYING', GRN if k > 0.9 else YEL, w=520)
    elif i == 8:
        if h == 0:
            y = pill(d, 50, y, 'BAKING SODA', 'SAFE', GRN, w=520)
        else:
            y = pill(d, 50, y, 'FLOUR', 'FLAMMABLE', REDC, w=520)
    elif i == 9:
        y = pill(d, 50, y, 'FIRE', 'SPREADING', REDC, w=520)
        y = pill(d, 50, y, 'ACTION', 'EXIT + CALL', YEL, w=520)


def choice_cards(img, t, t0):
    d = ImageDraw.Draw(img)
    k = ease((t - t0) / 0.3)
    fq = Q.font(Q.F_BLACK, 66)
    q = "YOUR FIRST MOVE?"
    qw = d.textlength(q, font=fq)
    d.text(((W - qw) / 2, 470 - 40 * (1 - k)), q, font=fq, fill=(255, 255, 255, int(255 * k)), stroke_width=10, stroke_fill=(0, 0, 0, int(255 * k)))
    f = Q.font(Q.F_BLACK, 66)
    for j, (txt, col) in enumerate((("METAL LID", YEL), ("WATER", CYAN))):
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
    if t >= L(11):
        k = ease((t - L(11)) / 0.25)
        y0, y1 = 640, 830
        d.line([(W - 760) / 2 + 30, y1 + 75, (W + 760) / 2 - 30, y1 + 75], fill=REDC + (int(255 * k),), width=14)
        cx, cy, r = (W + 760) / 2 - 20, y0 + 75, 70 * (1.4 - 0.4 * k)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(30, 170, 80, int(255 * k)), outline=(255, 255, 255, int(255 * k)), width=6)
        d.line([(cx - r * 0.45, cy), (cx - r * 0.1, cy + r * 0.38), (cx + r * 0.5, cy - r * 0.4)], fill=(255, 255, 255, int(255 * k)), width=14, joint='curve')


# ----------------------------------------------------------------------------- audio
def sfx_boom():
    n = int(1.6 * SR)
    tt = np.arange(n) / SR
    rng = np.random.default_rng(6)
    low = np.sin(2 * np.pi * np.cumsum(70 * np.exp(-tt * 2.0) + 30) / SR) * np.exp(-tt * 2.2)
    from scipy.signal import lfilter
    noise = lfilter([0.3], [1, -0.7], rng.uniform(-1, 1, n)) * np.exp(-tt * 3.0)
    return (low * 0.9 + noise * 0.8).astype(np.float32)


def sfx_hiss(dur, vol=1.0):
    from scipy.signal import lfilter
    n = int(dur * SR)
    tt = np.arange(n) / SR
    rng = np.random.default_rng(2)
    x = rng.uniform(-1, 1, n)
    x = x - lfilter([0.5], [1, -0.5], x)       # high-pass-ish
    return (x * np.sin(np.pi * np.clip(tt / dur, 0, 1)) ** 0.7 * 0.35 * vol).astype(np.float32)


def sfx_splash():
    n = int(0.5 * SR)
    tt = np.arange(n) / SR
    rng = np.random.default_rng(9)
    from scipy.signal import lfilter
    x = lfilter([0.5], [1, -0.4], rng.uniform(-1, 1, n)) * np.exp(-tt * 9)
    return x.astype(np.float32)


def sfx_thunk():
    n = int(0.4 * SR)
    tt = np.arange(n) / SR
    return (np.sin(2 * np.pi * 120 * tt) * np.exp(-tt * 14) + np.sin(2 * np.pi * 1800 * tt) * np.exp(-tt * 60) * 0.4).astype(np.float32)


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
    # fire crackle bed that follows the fire level
    fire_env = np.array([state_at(x / 10.0, scene_of(x / 10.0))['fire'] for x in range(int(DUR * 10) + 6)], np.float32)
    fe = np.interp(tt, np.arange(len(fire_env)) / 10.0, fire_env)
    crack = (rng.uniform(-1, 1, n) * (rng.random(n) > 0.9992 - 0.0006 * fe)).astype(np.float32)
    crack = lfilter([0.6], [1, -0.4], crack).astype(np.float32)
    rumble = lfilter([0.05], [1, -0.95], rng.uniform(-1, 1, n)).astype(np.float32)
    fx += (rumble * 0.28 + crack * 1.4) * fe
    for b in CUTS:
        add(b - 0.2, Q.sfx_whoosh(0.35), 0.5)
    add(TH0, Q.sfx_whoosh(0.4), 0.6)
    add(TH1, sfx_splash(), 0.9)
    add(L(2), sfx_hiss(DURS[2] + 0.5, 0.9), 0.8)
    add(L(3), sfx_hiss(DURS[3] + 0.6, 1.2), 0.9)
    add(TB4, sfx_boom(), 1.6)
    add(TB5 - 0.1, sfx_splash(), 0.6)
    add(TB5, sfx_boom(), 0.9)
    add(T_OFF, Q.sfx_tick(True), 0.8)
    add(T_LID[1] - 0.05, sfx_thunk(), 1.1)
    add(L(7) + 0.5, sfx_hiss(1.4, 0.5), 0.5)
    add(L(2) + 0.9, Q.sfx_tick(True), 0.7)
    add(L(10) + 0.15, Q.sfx_tick(True), 0.6)
    add(L(10) + 0.27, Q.sfx_tick(False), 0.6)
    pause0 = L(10) + DURS[10]
    for q in range(3):
        add(pause0 + q * (L(11) - pause0) / 3, Q.sfx_tick(q % 2 == 0), 0.7)
    add(L(11) - 0.05, Q.sfx_tada(), 0.7)
    bed = Q.music_bed(DUR + 0.5, seed=21)[:n]
    if len(bed) < n:
        bed = np.pad(bed, (0, n - len(bed)))
    env = np.convolve(np.abs(voice), np.ones(int(SR * 0.08)) / int(SR * 0.08), mode='same')
    duck = 1 - 0.55 * np.clip(env / 0.05, 0, 1)
    mix_ = voice * 1.0 + fx * 0.6 + bed * 0.8 * duck
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
        print('DUR', round(DUR, 2), 'starts', [round(x, 2) for x in STARTS], 'TH0', round(TH0, 2), 'TH1', round(TH1, 2), 'TB4', round(TB4, 2), 'TB5', round(TB5, 2), 'cuts', [round(x, 2) for x in CUTS])
    else:
        render_video(sys.argv[2])
