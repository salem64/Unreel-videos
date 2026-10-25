#!/usr/bin/env python3
"""Melancholic text short over a slow flight through an own blocky voxel cave (no game footage, own textures).

Usage (from tools/sad):
  python3 ../sim3d/tts_lines.py <name>_lines.json /tmp/sad_vo
  python3 cave_reel.py sheet /tmp/s.png 1,5,9 --lines <name>_lines.json --vo /tmp/sad_vo
  python3 cave_reel.py render out.mp4 --lines <name>_lines.json --vo /tmp/sad_vo
"""
import json, math, os, subprocess, sys, wave
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy.ndimage import zoom

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import quiz as Q  # noqa: E402

W, H, FPS, SR = 1080, 1920, 30, 44100
RW, RH = 360, 640
ASP = RW / RH


def arg(name, default):
    for i, a in enumerate(sys.argv):
        if a == name:
            return sys.argv[i + 1]
    return default


VO_DIR = arg('--vo', '/tmp/sad_vo')
SPEC = json.load(open(arg('--lines', os.path.join(HERE, 'attached_lines.json'))))
LINES = SPEC['lines']
DURS = json.load(open(os.path.join(VO_DIR, 'durs.json')))
GAP, START0, TAIL = 0.75, 0.9, 2.2
STARTS = []
_t = START0
for d in DURS:
    STARTS.append(_t)
    _t += d + GAP
DUR = STARTS[-1] + DURS[-1] + TAIL
NF = int(round(DUR * FPS))

# ----------------------------------------------------------------------------- world: voxel cave
GX, GY, GZ = 48, 260, 40
rng = np.random.default_rng(7)


def noise3(shape, cells, seed):
    r = np.random.default_rng(seed).random(cells)
    return zoom(r, [s / c for s, c in zip(shape, cells)], order=3)[:shape[0], :shape[1], :shape[2]]


def path_c(y):
    return np.stack([24 + 7 * np.sin(y * 0.045) + 3 * np.sin(y * 0.11), 18 + 4 * np.sin(y * 0.06 + 1)], -1)


_yy = np.arange(GY, dtype=np.float32)
_pc = path_c(_yy)
_X, _Y, _Z = np.meshgrid(np.arange(GX), np.arange(GY), np.arange(GZ), indexing='ij')
_n = noise3((GX, GY, GZ), (10, 52, 9), 3)
_dx = _X - _pc[_Y, 0]
_dz = (_Z - _pc[_Y, 1]) * 1.25
dist = np.sqrt(_dx ** 2 + _dz ** 2)
radius = 4.6 + 3.2 * _n
SOLID = dist > radius
# stalactites / stalagmites
_s = noise3((GX, GY, GZ), (24, 130, 20), 5)
SOLID |= (_s > 0.78) & (dist > radius - 2.5) & (np.abs(_dz) > 2.0)
# block types: 0 stone, 1 deepslate-ish dark stone, 2 coal, 3 iron, 4 copper, 5 diamond, 6 moss
r = rng.random((GX, GY, GZ))
TYPE = np.zeros((GX, GY, GZ), np.int8)
TYPE[_Z < 9] = 1
TYPE[(r > 0.955)] = 2
TYPE[(r > 0.975)] = 3
TYPE[(r > 0.985)] = 4
TYPE[(r > 0.995)] = 5
_m = noise3((GX, GY, GZ), (8, 40, 8), 11)
TYPE[(_m > 0.66) & (TYPE == 0)] = 6
BASE = np.array([[118, 118, 122], [70, 70, 80], [112, 112, 116], [128, 120, 114], [124, 112, 106], [112, 116, 120], [86, 112, 70]], np.float32)
ORE = np.array([[0, 0, 0], [0, 0, 0], [28, 28, 30], [216, 176, 140], [214, 120, 80], [90, 230, 225], [0, 0, 0]], np.float32)

# torches on the tunnel floor/walls every ~13 blocks
TORCH = []
for y in range(8, GY - 4, 13):
    c = path_c(np.float32(y))
    side = 1 if (y // 13) % 2 else -1
    x = int(c[0])
    while x > 0 and x < GX - 1 and not SOLID[x, y, int(c[1])]:
        x += side
    TORCH.append(np.array([x - side * 0.7 + 0.5, y + 0.5, c[1] + 0.3], np.float32))
TORCH = np.array(TORCH)


def hash3(a, b, c, d=0):
    return (np.sin(a * 12.9898 + b * 78.233 + c * 37.719 + d * 4.581) * 43758.5453) % 1.0


# ----------------------------------------------------------------------------- camera
SPEED = 1.35


def cam_at(t):
    y = 6 + t * SPEED
    c = path_c(np.float32(y))
    ca = path_c(np.float32(y + 7))
    pos = np.array([c[0] + 0.5 + 0.25 * math.sin(t * 0.7), y, c[1] + 0.3 + 0.12 * math.sin(t * 1.9)], np.float32)
    tgt = np.array([ca[0] + 0.5, y + 7, ca[1] + 0.1], np.float32)
    f = tgt - pos
    f /= np.linalg.norm(f)
    up = np.array([0, 0, 1], np.float32)
    rr = np.cross(f, up); rr /= np.linalg.norm(rr)
    u = np.cross(rr, f)
    roll = 0.04 * math.sin(t * 0.4)
    rr, u = rr * math.cos(roll) + u * math.sin(roll), u * math.cos(roll) - rr * math.sin(roll)
    return pos, f, rr, u


_PY, _PX = np.mgrid[0:RH, 0:RW].astype(np.float32)
SX = ((_PX + 0.5) / RW * 2 - 1) * ASP
SY = 1 - (_PY + 0.5) / RH * 2
TH = math.tan(math.radians(62) / 2)


def render_world(t):
    O, f, rr, u = cam_at(t)
    D = f[None, None] + (SX * TH)[..., None] * rr[None, None] + (SY * TH)[..., None] * u[None, None]
    D = (D / np.linalg.norm(D, axis=-1, keepdims=True)).reshape(-1, 3).astype(np.float32)
    n = len(D)
    idx = np.floor(O).astype(np.int32)[None].repeat(n, 0)
    step = np.where(D > 0, 1, -1).astype(np.int32)
    Dn = np.where(np.abs(D) < 1e-6, 1e-6, D)
    nxt = idx + (step > 0)
    tmax = (nxt - O) / Dn
    tdel = np.abs(1.0 / Dn)
    hit_t = np.full(n, 40.0, np.float32)
    hit_ax = np.zeros(n, np.int32)
    hit_idx = np.zeros((n, 3), np.int32)
    hit = np.zeros(n, bool)
    act = np.arange(n)
    for _ in range(70):
        if len(act) == 0:
            break
        tm = tmax[act]
        ax = tm.argmin(1)
        tt = tm[np.arange(len(act)), ax]
        idx[act, ax] += step[act, ax]
        tmax[act, ax] += tdel[act, ax]
        ii = idx[act]
        oob = (ii[:, 0] < 0) | (ii[:, 0] >= GX) | (ii[:, 1] < 0) | (ii[:, 1] >= GY) | (ii[:, 2] < 0) | (ii[:, 2] >= GZ)
        cl = np.clip(ii, 0, [GX - 1, GY - 1, GZ - 1])
        sol = oob | SOLID[cl[:, 0], cl[:, 1], cl[:, 2]]
        done = sol | (tt > 30)
        if done.any():
            a = act[done]
            hit[a] = sol[done]
            hit_t[a] = tt[done]
            hit_ax[a] = ax[done]
            hit_idx[a] = cl[done]
        act = act[~done]
    P = O + D * hit_t[:, None]
    nrm_ = np.zeros((n, 3), np.float32)
    nrm_[np.arange(n), hit_ax] = -step[np.arange(n), hit_ax]
    # face uv -> 16x16 texels
    ua = np.where(hit_ax == 0, P[:, 1], P[:, 0])
    va = np.where(hit_ax == 2, P[:, 1], P[:, 2])
    tu = np.floor((ua % 1.0) * 16)
    tv = np.floor((va % 1.0) * 16)
    bx, by, bz = hit_idx[:, 0], hit_idx[:, 1], hit_idx[:, 2]
    ty = TYPE[bx, by, bz]
    hsh = hash3(bx * 1.0 + tu * 0.13, by * 1.0 + tv * 0.17, bz * 1.0, hit_ax)
    hsh2 = hash3(np.floor(tu / 3) + bx * 7.0, np.floor(tv / 3) + by * 3.0, bz * 5.0)
    col = BASE[ty] * (0.72 + 0.36 * hsh)[:, None]
    ore = (ty >= 2) & (ty <= 5) & (hsh2 > 0.72) & (hsh > 0.25)
    col[ore] = ORE[ty[ore]] * (0.8 + 0.3 * hsh[ore])[:, None]
    # moss only on top faces mostly
    moss = (ty == 6) & ~((hit_ax == 2) & (nrm_[:, 2] > 0))
    col[moss] = BASE[0] * (0.72 + 0.36 * hsh[moss])[:, None]
    # lighting: dim cold ambient + player glow + torches
    face = np.where(hit_ax == 2, np.where(nrm_[:, 2] > 0, 1.0, 0.55), np.where(hit_ax == 0, 0.8, 0.7))
    light = np.tile(np.array([0.30, 0.34, 0.46], np.float32), (n, 1)) * face[:, None]
    d2 = hit_t ** 2
    light += (1.25 / (1 + 0.022 * d2) * face)[:, None] * np.array([1.0, 0.95, 0.9], np.float32)
    near = TORCH[np.abs(TORCH[:, 1] - O[1]) < 34]
    for L in near:
        v = L - P
        dd = (v ** 2).sum(1)
        lam = np.clip((v * nrm_).sum(1) / np.sqrt(dd + 1e-6), 0, 1) * 0.75 + 0.25
        fl = 1.0 + 0.08 * math.sin(t * 11 + L[1])
        light += (fl * 5.0 / (1 + 0.4 * dd) * lam)[:, None] * np.array([1.0, 0.62, 0.28], np.float32)
    out = col * light
    fog = np.exp(-hit_t / 22.0)
    out = out * fog[:, None] + np.array([3, 4, 8], np.float32) * (1 - fog[:, None])
    out[~hit] = np.array([2, 2, 5], np.float32)
    img = out.reshape(RH, RW, 3)
    # torch flames as glows
    for L in near:
        v = L + np.array([0, 0, 0.35], np.float32) - O
        z = v @ f
        if z < 0.3:
            continue
        x = (v @ rr) / (z * TH) / ASP
        y = (v @ u) / (z * TH)
        px, py = (x + 1) / 2 * RW, (1 - y) / 2 * RH
        rp = 0.35 / (z * TH) * RH / 2
        if rp < 0.6 or not (-40 < px < RW + 40 and -40 < py < RH + 40):
            continue
        # occlusion test via depth at that pixel
        ix, iy = int(np.clip(px, 0, RW - 1)), int(np.clip(py, 0, RH - 1))
        if hit_t.reshape(RH, RW)[iy, ix] < z * 0.95 - 0.5:
            continue
        x0, x1 = int(max(0, px - 4 * rp)), int(min(RW, px + 4 * rp + 1))
        y0, y1 = int(max(0, py - 4 * rp)), int(min(RH, py + 4 * rp + 1))
        if x1 <= x0 or y1 <= y0:
            continue
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        g = np.exp(-(((xx - px) / rp) ** 2 + ((yy - py) / (rp * 1.4)) ** 2))
        g2 = np.exp(-(((xx - px) / (rp * 3.5)) ** 2 + ((yy - py) / (rp * 3.5)) ** 2))
        img[y0:y1, x0:x1] += g[..., None] * np.array([255, 210, 120]) * 0.9 + g2[..., None] * np.array([255, 140, 50]) * 0.18
    return img


# ----------------------------------------------------------------------------- post + text
_vy, _vx = np.mgrid[0:H, 0:W]
VIG = (1 - 0.55 * (((_vx - W / 2) / (W / 2)) ** 2 + ((_vy - H / 2) / (H / 2)) ** 2) ** 1.2).clip(0.25, 1).astype(np.float32)


def post(img, t):
    a = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).resize((W, H), Image.BICUBIC)
    small = np.asarray(a.resize((W // 8, H // 8), Image.BILINEAR), np.float32)
    br = np.clip(small - 120, 0, None) * 1.5
    bl = np.asarray(Image.fromarray(br.clip(0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(6)).resize((W, H), Image.BILINEAR), np.float32)
    out = np.asarray(a, np.float32) + bl * 0.8
    out = out * VIG[..., None]
    g = np.random.default_rng(int(t * 1000)).normal(0, 2.5, (H // 2, W // 2)).astype(np.float32)
    g = np.asarray(Image.fromarray(g).resize((W, H), Image.NEAREST))
    out = out + g[..., None]
    out = out * np.array([0.95, 0.97, 1.05], np.float32)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).convert('RGBA')


def wrap(d, text, f, width):
    words, lines, cur = text.split(), [], ''
    for w_ in words:
        tst = (cur + ' ' + w_).strip()
        if d.textlength(tst, font=f) <= width:
            cur = tst
        else:
            lines.append(cur)
            cur = w_
    if cur:
        lines.append(cur)
    return lines


def text_layer(img, t):
    cur = None
    for i, s in enumerate(STARTS):
        e = s + DURS[i] + GAP * 0.85
        if s - 0.15 <= t < e:
            cur = (i, s, e)
    if cur is None:
        return
    i, s, e = cur
    a = min(1.0, (t - s + 0.15) / 0.35) * min(1.0, max(0.0, (e - t) / 0.3))
    if i == len(LINES) - 1:
        a = min(1.0, (t - s + 0.15) / 0.35) * min(1.0, max(0.0, (DUR - 0.3 - t) / 0.6))
    lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    f = Q.font(Q.F_BOLD, 64)
    ls = wrap(d, LINES[i], f, 820)
    lh = 84
    y0 = 860 - len(ls) * lh / 2 - 12 * (1 - a)
    for k, ln in enumerate(ls):
        tw_ = d.textlength(ln, font=f)
        d.text(((W - tw_) / 2, y0 + k * lh), ln, font=f, fill=(255, 255, 255, int(255 * a)))
    sh = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ds = ImageDraw.Draw(sh)
    for k, ln in enumerate(ls):
        tw_ = ds.textlength(ln, font=f)
        ds.text(((W - tw_) / 2, y0 + k * lh + 4), ln, font=f, fill=(0, 0, 0, int(200 * a)))
    sh = sh.filter(ImageFilter.GaussianBlur(8))
    img.alpha_composite(sh)
    img.alpha_composite(lay)


def render_frame(fi):
    t = fi / FPS
    img = post(render_world(t), t)
    fade = min(1.0, t / 0.8)
    if fade < 1:
        img = Image.blend(Image.new('RGBA', (W, H), (0, 0, 0, 255)), img, fade)
    text_layer(img, t)
    return img.convert('RGB')


# ----------------------------------------------------------------------------- audio: soft piano + cave ambience + voice
NOTE = {'A2': 110.0, 'C3': 130.81, 'E3': 164.81, 'F2': 87.31, 'G2': 98.0, 'B2': 123.47, 'D3': 146.83,
        'A3': 220.0, 'C4': 261.63, 'E4': 329.63, 'F3': 174.61, 'G3': 196.0, 'B3': 246.94, 'D4': 293.66, 'G4': 392.0, 'A4': 440.0}


def piano(fr, dur, vol):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    s = np.zeros(n)
    for h, a in ((1, 1.0), (2, 0.45), (3, 0.18), (4, 0.08)):
        s += a * np.sin(2 * np.pi * fr * h * tt) * np.exp(-tt * (1.6 + h * 0.9))
    att = np.clip(tt / 0.008, 0, 1)
    return (s * att * vol).astype(np.float32)


def build_audio(path):
    from scipy.signal import fftconvolve, lfilter
    n = int((DUR + 0.5) * SR)
    tt = np.arange(n) / SR
    voice = np.zeros(n, np.float32)
    for i in range(len(LINES)):
        with wave.open(os.path.join(VO_DIR, f'l{i}.wav')) as w:
            a = np.frombuffer(w.readframes(w.getnframes()), '<i2').astype(np.float32) / 32767
        i0 = int(STARTS[i] * SR)
        voice[i0:i0 + len(a)] += a[: n - i0]
    mus = np.zeros(n, np.float32)
    prog = [('A2', ['A3', 'C4', 'E4', 'C4']), ('F2', ['F3', 'A3', 'C4', 'A3']), ('C3', ['G3', 'C4', 'E4', 'C4']), ('G2', ['G3', 'B3', 'D4', 'B3'])]
    beat = 0.62
    t0, k = 0.2, 0
    while t0 < DUR:
        bass, arp = prog[k % 4]
        seg = piano(NOTE[bass], 4.5, 0.32)
        i0 = int(t0 * SR); mus[i0:i0 + len(seg)] += seg[: n - i0]
        for j in range(8):
            nt = arp[j % 4]
            fr = NOTE[nt] * (2 if (j == 6 and k % 2) else 1)
            seg = piano(fr, 2.5, 0.16)
            i1 = int((t0 + j * beat / 2 * 1.0) * SR)
            if i1 < n:
                mus[i1:i1 + len(seg)] += seg[: n - i1]
        t0 += beat * 4
        k += 1
    rng = np.random.default_rng(1)
    ir = rng.uniform(-1, 1, int(SR * 2.2)) * np.exp(-np.arange(int(SR * 2.2)) / SR * 2.4)
    wet = fftconvolve(mus, ir)[:n] * 0.035
    mus = mus * 0.7 + wet
    mus = lfilter([0.35], [1, -0.65], mus).astype(np.float32)
    amb = lfilter([0.02], [1, -0.985], rng.uniform(-1, 1, n)).astype(np.float32) * 0.6
    drip = np.zeros(n, np.float32)
    for td in np.arange(1.3, DUR, 2.7) + rng.uniform(-0.5, 0.5, len(np.arange(1.3, DUR, 2.7))):
        i0 = int(td * SR)
        m = int(0.25 * SR)
        x = np.arange(m) / SR
        s = np.sin(2 * np.pi * (1300 + 900 * np.exp(-x * 30)) * x) * np.exp(-x * 25) * 0.12
        if i0 + m < n:
            drip[i0:i0 + m] += s
    drip = drip + fftconvolve(drip, ir[: SR])[:n] * 0.02
    mix_ = voice * 1.0 + mus * 0.55 / max(1e-6, np.abs(mus).max()) + amb + drip
    mix_ *= np.clip(tt / 0.6, 0, 1) * np.clip((DUR - tt) / 1.5, 0, 1)
    mix_ /= max(1e-6, np.abs(mix_).max()) / 0.9
    pcm = (mix_ * 32767).astype('<i2')
    with wave.open(path, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())


def _fb(fi):
    return render_frame(fi).tobytes()


def render_video(out):
    wav = out.rsplit('.', 1)[0] + '.wav'
    build_audio(wav)
    cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
           '-i', wav, '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11', '-c:v', 'libx264', '-preset', 'medium', '-crf', '23',
           '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-shortest', '-movflags', '+faststart', out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with Pool(2) as pool:
        for b in pool.imap(_fb, range(NF), chunksize=4):
            p.stdin.write(b)
    p.stdin.close()
    if p.wait() != 0:
        raise SystemExit('ffmpeg failed')
    os.remove(wav)


def sheet(out, times, cols=5):
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
        print('DUR', round(DUR, 2), 'NF', NF)
    else:
        render_video(sys.argv[2])
