#!/usr/bin/env python3
"""3D-sim style "WHAT IF" short: you fall into a hole straight through the Earth.

Own numpy ray tracer (no GPU, no Blender): cut-away Earth with layers, tunnel POV with a 3D cartoon
character, surface scene, smooth HUD + word-pop captions, kokoro narrator voice, music + SFX.
Render: 540x960 traced, upscaled to 1080x1920 with bloom. ~0.3 s/frame on 2 cores.

Usage (from tools/sim3d):
  python3 tts_lines.py tunnel_lines.json /tmp/tunnel_vo          # voice first (durations drive the timeline)
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

VO_DIR = '/tmp/claude-0/tunnel_vo'
for i, a in enumerate(sys.argv):
    if a == '--vo':
        VO_DIR = sys.argv[i + 1]
LINES = json.load(open(os.path.join(HERE, 'tunnel_lines.json')))['lines']
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


# ----------------------------------------------------------------------------- Earth model + fall simulation
R_KM = 6371.0
LAYERS = [(1221.5, 'inner'), (3480.0, 'outer'), (6336.0, 'mantle'), (6371.0, 'crust')]
_rk = np.array([0, 1221.5, 3480, 5701, 6371]) * 1e3
_gk = np.array([0, 4.40, 10.68, 9.99, 9.82])


def grav(r_m):
    return np.interp(abs(r_m), _rk, _gk)


def _simulate():
    dt = 0.25
    r, v, t = R_KM * 1e3, 0.0, 0.0
    T, Rr, V, G = [0.0], [r], [0.0], [grav(r)]
    while True:
        g = grav(r) * (1 if r > 0 else -1)
        v += g * dt
        r -= v * dt
        t += dt
        T.append(t); Rr.append(r); V.append(v); G.append(grav(r))
        if r <= -R_KM * 1e3 or v < 0:
            break
    return np.array(T), np.array(Rr), np.array(V), np.array(G)


SIM_T, SIM_R, SIM_V, SIM_G = _simulate()
FALL_TOTAL = SIM_T[-1]                      # ~2286 s = 38.1 min
VMAX = SIM_V.max()
FALL_V0, FALL_V1 = L(0), Lend(6)            # video window that covers the whole fall


def fall_state(t):
    """video time -> (real seconds, r_km signed, speed km/h, g %)"""
    k = min(1.0, max(0.0, (t - FALL_V0) / (FALL_V1 - FALL_V0)))
    tr = k * FALL_TOTAL
    r = np.interp(tr, SIM_T, SIM_R) / 1e3
    v = np.interp(tr, SIM_T, SIM_V) * 3.6
    g = np.interp(tr, SIM_T, SIM_G) / 9.82 * 100
    return tr, r, v, g


# ----------------------------------------------------------------------------- textures
LAND = _noise_tex(11)
CLOUD = _noise_tex(5, octaves=((16, 1.0), (32, 0.6), (64, 0.35)))
ROCK = _noise_tex(31, w=256, h=256, octaves=((8, 1.0), (16, 0.6), (32, 0.4), (64, 0.25)))
LAND_T = float(np.quantile(LAND, 0.6))
CLOUD_T = float(np.quantile(CLOUD, 0.86))


def layer_color(rn, nz=None, t=0.0):
    """rn = radius / Earth radius (0..1) -> emissive cut-face colour (N,3)"""
    nz = np.zeros_like(rn) if nz is None else nz
    mant = mix(C('7a1608'), C('ff7a1a'), smooth(0.99, 0.55, rn))
    mant = mant * (0.78 + 0.45 * nz)[:, None]
    outer = mix(C('ff9a1e'), C('ffd25a'), nz) * 1.08
    inner = mix(C('fff1b8'), C('ffffff'), smooth(0.19, 0.0, rn))
    col = np.where((rn > 0.9945)[:, None], C('6e5a48') * (0.8 + 0.4 * nz)[:, None], mant)
    col = np.where((rn < 0.5462)[:, None], outer, col)
    col = np.where((rn < 0.1917)[:, None], inner, col)
    for rb in (0.5462, 0.1917, 0.9945):
        col = col * (1 - 0.35 * np.exp(-((rn - rb) / 0.004) ** 2))[:, None]
    return col


def layer_color_depth(dep_km):
    rn = np.array([abs(R_KM - dep_km) / R_KM], np.float32)
    return layer_color(rn, np.array([0.55], np.float32))[0]


# ----------------------------------------------------------------------------- Earth cut-away scene
SUN = nrm(np.array([-0.35, -0.85, 0.45], np.float32))


def earth_cutaway(cam, t, dot_z=None, rot=0.0, rt=0.022):
    D = cam.rays()
    O = cam.pos
    col = space_bg(D)
    tbest = np.full(len(D), np.inf, np.float32)
    b = D @ O
    c = O @ O - 1.0
    disc = b * b - c
    idx = np.where(disc > 0)[0]
    # atmosphere glow for near misses
    dmin2 = np.maximum(O @ O - b * b, 0)
    halo = np.exp(-(np.sqrt(dmin2) - 1.0).clip(0) / 0.045) * (b < 0)
    col = col + halo[:, None] * C('4aa8ff') * 0.75
    if len(idx):
        Di, bi = D[idx], b[idx]
        sq = np.sqrt(disc[idx])
        t0, t1 = -bi - sq, -bi + sq
        P0 = O + t0[:, None] * Di
        inW = (P0[:, 0] > 0) & (P0[:, 1] < 0)
        # cut faces
        with np.errstate(divide='ignore', invalid='ignore'):
            tx = -O[0] / Di[:, 0]
            ty = -O[1] / Di[:, 1]
        Px = O + tx[:, None] * Di
        Py = O + ty[:, None] * Di
        vx = (tx >= t0 - 1e-5) & (tx <= t1) & (Px[:, 1] <= 0) & ((Px ** 2).sum(1) <= 1)
        vy = (ty >= t0 - 1e-5) & (ty <= t1) & (Py[:, 0] >= 0) & ((Py ** 2).sum(1) <= 1)
        tf = np.where(vx, tx, np.inf)
        tf = np.minimum(tf, np.where(vy, ty, np.inf))
        face = inW & np.isfinite(tf)
        surf = ~inW
        # --- surface
        si = np.where(surf)[0]
        if len(si):
            n = P0[si]
            cr, srr = math.cos(rot), math.sin(rot)
            xr = n[:, 0] * cr + n[:, 1] * srr
            yr = -n[:, 0] * srr + n[:, 1] * cr
            lat = np.arcsin(np.clip(n[:, 2], -1, 1))
            lon = np.arctan2(yr, xr)
            th, tw_ = LAND.shape
            u = ((lon / (2 * np.pi)) % 1.0) * tw_
            v = (0.5 - lat / np.pi) * (th - 1)
            h = _sample(LAND, u, v) + 0.08 * (_sample(LAND, u * 4 % tw_, v * 4 % th) - 0.5)
            cl = _sample(CLOUD, (u + t * 0.6) % tw_, v)
            land = smooth(LAND_T - 0.01, LAND_T + 0.01, h)
            ocean = mix(C('0a2a6e'), C('1d6fc0'), smooth(LAND_T - 0.2, LAND_T, h))
            gr = mix(C('3f8f4a'), C('9c8a55'), smooth(LAND_T + 0.08, LAND_T + 0.3, h))
            base = mix(ocean, gr, land)
            base = mix(base, C('eef4ff'), smooth(1.12, 1.25, np.abs(lat)))
            base = mix(base, C('f6f9ff'), smooth(CLOUD_T - 0.04, CLOUD_T + 0.12, cl) * 0.9)
            lam = n @ SUN
            dif = smooth(-0.2, 0.5, lam) * 0.95 + 0.06
            hv = nrm(SUN[None] - Di[si])
            spec = np.clip((n * hv).sum(1), 0, 1) ** 60 * (1 - land) * 0.8
            fres = (1 - np.abs((n * Di[si]).sum(1))) ** 2.5
            cs = base * dif[:, None] + spec[:, None] * 255 + fres[:, None] * C('5aaeff') * 0.9 * smooth(-0.3, 0.3, lam)[:, None]
            hole = np.sqrt(n[:, 0] ** 2 + n[:, 1] ** 2) < rt * 1.2
            cs[hole] = C('0b0d18')
            col[idx[si]] = cs
            tbest[idx[si]] = t0[si]
        # --- cut faces
        fi = np.where(face)[0]
        if len(fi):
            tff = tf[fi]
            P = O + tff[:, None] * Di[fi]
            rn = np.linalg.norm(P, axis=1)
            onx = np.abs(P[:, 0]) < 1e-3
            a2 = np.where(onx, P[:, 1], P[:, 0])
            nu = (np.arctan2(P[:, 2], a2) / (2 * np.pi) % 1.0) * 255
            nv = (rn * 255 * 0.7 + t * 8 * (rn < 0.55)) % 255
            nz = _sample(ROCK, nu, nv)
            cf = layer_color(rn, nz, t)
            dist = np.abs(a2)
            tun = dist < rt
            glow = np.exp(-np.clip(dist - rt, 0, None) / 0.012)
            cf = cf * (1 - 0.5 * glow)[:, None] + glow[:, None] * C('5fe6ff') * 0.9
            cf[tun] = C('0a0c16') + C('3fd8ff') * 0.25
            col[idx[fi]] = cf
            tbest[idx[fi]] = tff
    # falling dot (emissive sphere + glow)
    if dot_z is not None:
        cdot = np.array([0, 0, dot_z], np.float32)
        oc = O - cdot
        bb = D @ oc
        tc = -bb
        dperp = np.sqrt(np.maximum(oc @ oc - bb * bb, 0))
        front = tc < tbest + 0.05
        g = np.exp(-dperp / 0.028) * front
        col = col + g[:, None] * C('fff2b0') * 1.4
        col[(dperp < 0.026) & front] = C('ffffff')
    return col.reshape(RH, RW, 3), cam


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


# ----------------------------------------------------------------------------- tunnel POV
VIS_SPEED = None


def _vis_distance():
    ts = np.arange(0, DUR + 1, 1 / FPS)
    sp = np.array([fall_state(x)[2] for x in ts]) / (VMAX * 3.6)
    v = 4 + 70 * sp
    return ts, np.cumsum(v) / FPS


VIS_T, VIS_S = _vis_distance()


def tunnel_pov(t, dep_km, speed_frac, look_up, char=True, sky_dist=None, heat=0.0, shake=0.0, spin=0.0):
    rng_a = 0.04 * shake
    jit = (rng_a * math.sin(t * 53), rng_a * math.cos(t * 47)) if shake else None
    fwd = (0, 0, -1) if look_up else (0, 0, 1)
    tilt = 0.12 * math.sin(t * 0.9)
    cam = Cam((0, 0, 0), (math.sin(tilt) * 0.3, 0.12, fwd[2] * 3), fov=78, roll=spin, up=(0, 1, 0))
    D = cam.rays(jit)
    if heat > 0:
        D = nrm(D + heat * 0.006 * np.stack([np.sin(SY.ravel() * 40 + t * 12), np.cos(SX.ravel() * 33 + t * 9), 0 * SX.ravel()], 1))
    rho = np.sqrt(D[:, 0] ** 2 + D[:, 1] ** 2) + 1e-6
    tw = 1.0 / rho
    zh = tw * D[:, 2]
    S = float(np.interp(t, VIS_T, VIS_S))
    zs = zh + S * (1 if not look_up else 1)
    ang = (np.arctan2(D[:, 1], D[:, 0]) / (2 * np.pi) % 1.0) * 255
    blur = 1 + 10 * speed_frac
    nz = 0
    for k in range(3):
        nz = nz + _sample(ROCK, ang, ((zs - k * 0.25 * blur) * 18) % 255)
    nz = nz / 3
    base = layer_color_depth(dep_km)
    rock = base[None] * (0.55 + 0.6 * nz)[:, None]
    ph = (zs / 3.0) % 1.0
    w = 0.04 + 0.12 * speed_frac
    ring = np.exp(-((np.minimum(ph, 1 - ph)) / w) ** 2)
    col = rock + ring[:, None] * C('7ff0ff') * 1.1
    fog = np.exp(-np.abs(zh) * 0.045)
    far = base * 1.25 + 30
    col = col * fog[:, None] + far[None] * (1 - fog)[:, None]
    if sky_dist is not None:
        sky = (zh < -sky_dist) & look_up
        col[sky] = mix(C('bfe6ff'), C('6fb8ff'), smooth(0.9, 1.0, -D[sky, 2]))
    tb = np.where(np.isfinite(tw), np.abs(tw), 1e9).astype(np.float32)
    if char:
        sp = 0.6 + 0.4 * speed_frac
        Rm = rotm(0.3 * math.sin(t * 1.3), 0.28 * math.sin(t * 0.8), 0.9 * math.sin(t * 1.1 * sp) + spin)
        center = np.array([0.05 * math.sin(t * 2.1), -0.12, 2.45 * fwd[2]], np.float32)
        Rf = rotm(0, math.pi, 0) if not look_up else np.eye(3, dtype=np.float32)
        prims = place(char_prims(t, scream=1.0, flail=1.0), Rf @ Rm, center)
        hit, tt, n, cb = trace_prims(np.zeros(3, np.float32), D, prims, tb)
        if hit.any():
            key = nrm(np.array([0.3, 0.6, -fwd[2] * 0.7], np.float32))
            col[hit] = shade_char(D[hit], n[hit], cb[hit], key, base * 0.004 * 255 + 40)
    return col.reshape(RH, RW, 3)


# ----------------------------------------------------------------------------- surface scene (other side)
HOLE_R = 0.45


def surface_scene(t, char_z, grab=False, wave=0.0, dim=0.0):
    cam = Cam((0.4, -3.1, 1.35), (0, 0, 0.45), fov=52)
    D = cam.rays()
    O = cam.pos
    n = len(D)
    up = np.clip(D[:, 2], -1, 1)
    sky = mix(C('a8d8ff'), C('2f7fe0'), smooth(0.0, 0.45, up))
    sun_d = nrm(np.array([-0.5, 0.6, 0.35], np.float32))
    sky = sky + (np.clip(D @ sun_d, 0, 1) ** 60)[:, None] * 255 * 0.9
    col = sky.copy()
    tb = np.full(n, 1e9, np.float32)
    with np.errstate(divide='ignore', invalid='ignore'):
        tg = -O[2] / D[:, 2]
    g = (D[:, 2] < 0) & (tg > 0)
    P = O + np.where(g, tg, 0)[:, None] * D
    rr = np.sqrt(P[:, 0] ** 2 + P[:, 1] ** 2)
    ground = g & (rr > HOLE_R)
    gi = np.where(ground)[0]
    gz = _sample(ROCK, (P[gi, 0] * 40) % 255, (P[gi, 1] * 40) % 255)
    gcol = mix(C('3d8b3a'), C('6bbf4e'), gz)
    gcol = mix(gcol, C('7a5a3a'), smooth(HOLE_R + 0.14, HOLE_R + 0.02, rr[gi]))
    fogk = smooth(6, 30, tg[gi])
    gcol = mix(gcol, C('a9d4ff'), fogk * 0.4)
    col[gi] = gcol
    tb[gi] = tg[gi]
    hi = np.where(g & (rr <= HOLE_R))[0]
    if len(hi):
        Dh = D[hi]
        a = Dh[:, 0] ** 2 + Dh[:, 1] ** 2
        b = O[0] * Dh[:, 0] + O[1] * Dh[:, 1]
        c = O[0] ** 2 + O[1] ** 2 - HOLE_R ** 2
        tw_ = (-b + np.sqrt(np.maximum(b * b - a * c, 0))) / np.maximum(a, 1e-6)
        z = O[2] + tw_ * Dh[:, 2]
        dep = np.clip(-z, 0, None)
        hcol = mix(C('6a4a30'), C('0a0606'), smooth(0, 1.2, dep)) + C('ff6a1a') * 0.25 * smooth(1.5, 4, dep)[:, None]
        col[hi] = hcol
        tb[hi] = tw_
    gp = (HOLE_R + 0.02, 0.0, 0.02) if grab else None
    Rm = rotm(0, 0, 0)
    prims = char_prims(t, scream=0.3 if grab else 1.0, flail=0.3, wave=wave,
                       grab=None if gp is None else np.array(gp) - np.array([0, 0, char_z]))
    # character stands upright (y up -> world z up), faces camera (-y)
    Rw = np.array([[1, 0, 0], [0, 0, 1], [0, 1, 0]], np.float32)
    Rw = Rw @ rotm(0, 0, 0)
    # local z toward viewer -> world -y
    Rw = np.array([[1, 0, 0], [0, 0, 1], [0, 1, 0]], np.float32)
    prims = place(prims if gp is None else char_prims(t, 0.3, 0.3, wave, grab=np.array([gp[0], gp[2] - char_z, -gp[1]], np.float32)),
                  Rw @ Rm, np.array([0, 0, char_z], np.float32))
    hit, tt, nn, cb = trace_prims(O, D, prims, tb)
    if hit.any():
        col[hit] = shade_char(D[hit], nn[hit], cb[hit], nrm(np.array([-0.4, -0.6, 0.7], np.float32)), C('fff0d0') * 0.5)
    col = col.reshape(RH, RW, 3)
    if dim:
        col = col * (1 - dim) + C('05070f') * dim
    return col, cam


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


def minimap(d, cx, cy, r, rk):
    d.ellipse([cx - r - 8, cy - r - 8, cx + r + 8, cy + r + 8], fill=(8, 12, 28, 160))
    for rr, c in ((1.0, (190, 70, 30)), (0.546, (255, 170, 40)), (0.192, (255, 240, 190))):
        R_ = r * rr
        d.ellipse([cx - R_, cy - R_, cx + R_, cy + R_], fill=c + (255,))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(80, 170, 255, 255), width=5)
    d.line([cx, cy - r, cx, cy + r], fill=(10, 12, 20, 255), width=6)
    py = cy - rk / R_KM * r
    d.ellipse([cx - 13, py - 13, cx + 13, py + 13], fill=(255, 255, 255, 255), outline=(255, 220, 90, 255), width=4)


KEYWORDS = {'HOLE', 'EARTH', 'FALL', 'FASTER', 'THIRTY', 'THOUSAND', 'ZERO', 'CENTER', 'FIVE', 'SUN',
            'SLOW', 'THIRTY-EIGHT', 'OTHER', 'SIDE', 'GRAB', 'FOREVER', 'JUMP', 'STRONGER', 'DEGREES', 'BACK'}


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


def choice_cards(img, t, t0):
    d = ImageDraw.Draw(img)
    k = ease((t - t0) / 0.3)
    fq = Q.font(Q.F_BLACK, 88)
    q = "WOULD YOU JUMP IN?"
    qw = d.textlength(q, font=fq)
    d.text(((W - qw) / 2, 470 - 40 * (1 - k)), q, font=fq, fill=(255, 255, 255, int(255 * k)), stroke_width=10, stroke_fill=(0, 0, 0, int(255 * k)))
    f = Q.font(Q.F_BLACK, 70)
    for i, (txt, col) in enumerate((("NO WAY", REDC), ("I'D JUMP", GRN))):
        kk = ease((t - t0 - 0.15 - i * 0.12) / 0.3)
        if kk <= 0:
            continue
        y = 640 + i * 190
        pulse = 1 + 0.03 * math.sin(t * 6 + i * 3)
        w_, h_ = 760 * pulse, 150 * pulse
        x = (W - w_) / 2 + (1 - kk) * (300 if i else -300)
        d.rounded_rectangle([x, y, x + w_, y + h_], 40, fill=(10, 14, 30, int(220 * kk)), outline=col + (int(255 * kk),), width=8)
        tw_ = d.textlength(txt, font=f)
        d.text((x + (w_ - tw_) / 2, y + (h_ - 84) / 2), txt, font=f, fill=col + (int(255 * kk),))


def hud(img, t, scene):
    d = ImageDraw.Draw(img, 'RGBA')
    tr, rk, v, g = fall_state(t)
    if FALL_V0 + 0.5 <= t <= Lend(6) + 0.3:
        dep = R_KM - rk
        y = 190
        y = pill(d, 50, y, 'DEPTH', f'{dep:,.0f} km', (255, 255, 255), w=520)
        sp_col = REDC if v > 30000 else (YEL if v > 15000 else (255, 255, 255))
        y = pill(d, 50, y, 'SPEED', f'{v:,.0f} km/h', sp_col, w=520)
        mm, ss = divmod(int(tr), 60)
        y = pill(d, 50, y, 'TIME', f'{mm:02d}:{ss:02d}', CYAN, w=520)
        if L(2) + 1.0 <= t < L(4):
            y = bar_pill(d, 50, y, 'GRAVITY', g / 100, f'{g:.0f}%', GRN if g > 60 else (YEL if g > 20 else REDC))
        if L(4) - 0.1 <= t < L(5):
            k = ease((t - L(4)) / 1.2)
            y = pill(d, 50, y, 'HEAT', f'{int(5000 * k):,}+ °C', (255, 120, 60), w=520)
        minimap(d, 900, 300, 120, rk)
    if L(7) + 1.4 <= t < L(8):
        f = Q.font(Q.F_BLACK, 80)
        k = ease((t - L(7) - 1.4) / 0.25)
        txt = 'GRABBED ✓' if True else ''
        f2 = Q.font(Q.F_BLACK, 80)
        tw_ = d.textlength('GRABBED!', font=f2)
        d.rounded_rectangle([(W - tw_) / 2 - 40, 330, (W + tw_) / 2 + 40, 450], 36, fill=(20, 140, 70, int(230 * k)))
        d.text(((W - tw_) / 2, 345), 'GRABBED!', font=f2, fill=(255, 255, 255, int(255 * k)))


# ----------------------------------------------------------------------------- timeline
def scene_of(t):
    for i in range(len(STARTS) - 1, -1, -1):
        if t >= STARTS[i] - 0.11:
            return i
    return 0


def render_frame(fi):
    t = fi / FPS
    i = scene_of(t)
    tr, rk, v, g = fall_state(t)
    dep = R_KM - rk
    sf = v / (VMAX * 3.6)
    red, zoom, flash = 0.0, 1.0, 0.0
    if i == 0:
        k = (t - L(0)) / DURS[0]
        col = tunnel_pov(t, max(dep, 2.0), max(sf, 0.15 + 0.3 * k), look_up=True, sky_dist=1.0 + 30 * ease(k), shake=1.0)
        red = 0.25
    elif i in (1, 6):
        if i == 1:
            k = (t - L(1)) / (L(2) - L(1))
            az, el, dist = -1.15 + 0.35 * k, 0.32, 4.9 - 0.4 * k
            tgt = (0, 0, 0.15)
        else:
            k = (t - L(6)) / (L(7) - L(6))
            az, el, dist = -0.55 - 0.3 * k, 0.05 - 0.3 * ease(k), 4.6 - 0.3 * k
            tgt = (0, 0, -0.2 * ease(k))
        cam = Cam((dist * math.cos(el) * math.cos(az), dist * math.cos(el) * math.sin(az), dist * math.sin(el)), tgt, fov=50)
        col, _ = earth_cutaway(cam, t, dot_z=rk / R_KM, rot=0.4 + t * 0.03)
    elif i == 3:
        k = (t - L(3)) / (L(4) - L(3))
        az = -0.75 + 0.25 * k
        cam = Cam((2.9 * math.cos(az), 2.9 * math.sin(az), 0.3), (0, 0, rk / R_KM * 0.3), fov=46)
        col, cam = earth_cutaway(cam, t, dot_z=rk / R_KM, rot=0.4 + t * 0.03)
    elif i in (2, 4, 5):
        heat = 1.0 if i == 4 else 0.0
        col = tunnel_pov(t, dep, sf, look_up=(i != 2), heat=heat, shake=0.6 + 0.6 * sf, spin=0.0 if i != 2 else t * 0.4)
        red = 0.35 * sf if i == 2 else (0.45 if i == 4 else 0.0)
    else:
        if i == 7:
            k = (t - L(7))
            zc = -1.1 + 1.25 * ease(k / 1.3)
            grab = k > 1.3
            col, _ = surface_scene(t, zc if not grab else 0.15, grab=grab)
        else:
            col, _ = surface_scene(t, 0.15, grab=True, dim=min(0.55, (t - L(8)) * 2))
    for b in STARTS[1:]:
        if b - 0.11 <= t < b + 0.12:
            p = (t - (b - 0.11)) / 0.23
            flash = 0.55 * (1 - abs(p * 2 - 1))
            zoom = 1 + 0.1 * (1 - ease(p))
    img = post(col, red=red, flash=flash, zoom=zoom).convert('RGBA')
    hud(img, t, i)
    if i == 3 and L(3) + 1.2 <= t < L(4):
        _arrows(img, t, cam)
    if t >= L(8):
        choice_cards(img, t, L(8))
    caption(img, t)
    return img.convert('RGB')


def _arrows(img, t, cam):
    d = ImageDraw.Draw(img, 'RGBA')
    c = cam.project((0, 0, 0))
    if c is None:
        return
    k = ease((t - L(3) - 1.2) / 0.5)
    for j in range(8):
        a = j * math.pi / 4 + 0.2
        r0 = 300 - 60 * ((t * 1.5 + j * 0.13) % 1.0)
        x0, y0 = c[0] + r0 * math.cos(a), c[1] + r0 * math.sin(a)
        x1, y1 = c[0] + (r0 - 120) * math.cos(a), c[1] + (r0 - 120) * math.sin(a)
        d.line([x0, y0, x1, y1], fill=(0, 0, 0, int(200 * k)), width=22)
        d.line([x0, y0, x1, y1], fill=(255, 255, 255, int(255 * k)), width=12)
        ha = math.atan2(y1 - y0, x1 - x0)
        d.polygon([(x1 + 30 * math.cos(ha), y1 + 30 * math.sin(ha)),
                   (x1 + 22 * math.cos(ha + 2.3), y1 + 22 * math.sin(ha + 2.3)),
                   (x1 + 22 * math.cos(ha - 2.3), y1 + 22 * math.sin(ha - 2.3))], fill=(255, 255, 255, int(255 * k)), outline=(0, 0, 0, int(200 * k)))


# ----------------------------------------------------------------------------- audio
def build_audio(path):
    n = int((DUR + 0.5) * SR)
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
    for b in STARTS[1:]:
        add(b - 0.2, Q.sfx_whoosh(0.35), 0.5)
    rng = np.random.default_rng(3)
    tt = np.arange(n) / SR
    spd = np.interp(tt, VIS_T, [fall_state(x)[2] / (VMAX * 3.6) for x in VIS_T])
    falling = ((tt >= L(0)) & (tt < L(7))).astype(np.float32)
    noise = rng.uniform(-1, 1, n).astype(np.float32)
    k = 0.02 + 0.2 * spd
    lp = np.zeros(n, np.float32)
    acc = 0.0
    # one-pole low-pass with speed-dependent cutoff (rumble/wind)
    from scipy.signal import lfilter
    lp = lfilter([0.06], [1, -0.94], noise).astype(np.float32)
    rumble = lp * (0.15 + 1.1 * spd) * falling
    sizzle = lfilter([1, -1], [1, -0.3], noise).astype(np.float32) * 0.08 * ((tt >= L(4)) & (tt < L(5)))
    fx += rumble * 0.9 + sizzle
    add(L(7) + 0.2, Q.sfx_whoosh(0.5), 0.6)
    add(L(7) + 1.3, Q.sfx_pop(), 0.9)
    add(L(7) + 1.4, Q.sfx_tada(), 0.6)
    add(L(8) + 0.15, Q.sfx_tick(True), 0.6)
    add(L(8) + 0.27, Q.sfx_tick(False), 0.6)
    bed = Q.music_bed(DUR + 0.5, seed=7)[:n]
    if len(bed) < n:
        bed = np.pad(bed, (0, n - len(bed)))
    env = np.convolve(np.abs(voice), np.ones(int(SR * 0.08)) / int(SR * 0.08), mode='same')
    duck = 1 - 0.55 * np.clip(env / 0.05, 0, 1)
    mix_ = voice * 1.0 + fx * 0.55 + bed * 0.9 * duck
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
        print('DUR', round(DUR, 2), 'starts', [round(s, 2) for s in STARTS], 'fall', FALL_TOTAL, 'vmax km/h', VMAX * 3.6)
    else:
        render_video(sys.argv[2])
