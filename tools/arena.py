#!/usr/bin/env python3
"""Unreel arena physics shorts (called via tools/physics.py, or directly).

python3 tools/arena.py battle out.mp4 [seed] ["HOOK1|HOOK2"] [palette] [fighters]
    Ball vs ball: two balls with spinning swords bounce in an arena; every hit = -damage and a LONGER sword.
    fighters: "red,blue" (default) or two emojis/flags separated by comma, e.g. "🐶,🐱" or "🔥,💧".
python3 tools/arena.py elimination out.mp4 [seed] ["HOOK1|HOOK2"] [palette] [set]
    Last one standing: 8-12 balls in a rotating ring with a gap; whoever falls out is eliminated.
    set: flags (default) | animals | food | fruits | colors  - or a comma list of emojis.
The script searches seeds upward until the length is good (battle 18-45 s, elimination 20-50 s) and prints the seed
and the winner (use it for the caption / report, never reveal it in the caption).
"""
import colorsys, math, random, subprocess, sys
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont
import os as _os
sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import fx as fxlib  # noqa: E402  funny stickers + boom

COOKED = ["IS COOKED", "IS IN DANGER", "NEEDS A MEDIC", "IS FINISHED"]
OUT_LINES = ["BYE", "SKILL ISSUE", "SEE YA", "NOT LIKE THIS", "PACK YOUR BAGS", "TRIPPED", "GONE", "RIP"]

W, H, FPS, SR = 1080, 1920, 30, 44100
SUB = 8
CX, CY = W / 2, 1090
F = "/usr/share/fonts/opentype/inter/InterDisplay-Black.otf"
F_EMOJI = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
SETS = {
    "flags": ["🇺🇸", "🇧🇷", "🇩🇪", "🇯🇵", "🇫🇷", "🇮🇹", "🇬🇧", "🇪🇸", "🇲🇽", "🇨🇦", "🇰🇷", "🇦🇺", "🇳🇱", "🇵🇹", "🇦🇷", "🇸🇪"],
    "animals": ["🐶", "🐱", "🦊", "🐼", "🐸", "🐵", "🦁", "🐯", "🐷", "🐨", "🐰", "🐻"],
    "food": ["🍕", "🍔", "🌮", "🍣", "🍩", "🍟", "🌭", "🥐", "🍪", "🧁", "🍦", "🥨"],
    "fruits": ["🍎", "🍌", "🍇", "🍓", "🍉", "🍍", "🥝", "🍑", "🍒", "🥥", "🍋", "🥭"],
}
COLORS = [(239, 68, 68), (59, 130, 246), (34, 197, 94), (250, 204, 21), (168, 85, 247), (249, 115, 22),
          (236, 72, 153), (20, 184, 166), (255, 255, 255), (132, 204, 22), (99, 102, 241), (244, 63, 94)]
COLOR_NAMES = ["RED", "BLUE", "GREEN", "YELLOW", "PURPLE", "ORANGE", "PINK", "TEAL", "WHITE", "LIME", "INDIGO", "ROSE"]
PALETTES = {"neon": 0.55, "sunset": 0.02, "ice": 0.52, "candy": 0.88, "lime": 0.27}
SCALE = [261.6, 293.7, 329.6, 392.0, 440.0, 523.3, 587.3, 659.3, 784.0, 880.0, 1046.5, 1174.7, 1318.5]
_fc = {}


def font(sz):
    if sz not in _fc:
        _fc[sz] = ImageFont.truetype(F, sz)
    return _fc[sz]


def hue_col(h, l=0.6, s=1.0):
    return tuple(int(c * 255) for c in colorsys.hls_to_rgb(h % 1.0, l, s))


def emoji_img(e, size):
    k = (e, size)
    if k not in _fc:
        ef = ImageFont.truetype(F_EMOJI, 109)
        im = Image.new("RGBA", (300, 180), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((10, 10), e, font=ef, embedded_color=True)
        im = im.crop(im.getbbox())
        s = size / max(im.width, im.height)
        _fc[k] = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
    return _fc[k]


def ball_sprite(r, col=None, emoji=None, ring=(255, 255, 255)):
    ss = 3
    d = 2 * r
    im = Image.new("RGBA", (d * ss, d * ss), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    if emoji:
        dr.ellipse((0, 0, d * ss - 1, d * ss - 1), fill=(245, 245, 250, 255))
    else:
        dr.ellipse((0, 0, d * ss - 1, d * ss - 1), fill=col + (255,))
        hl = tuple(min(255, int(c * 0.6 + 255 * 0.4)) for c in col)
        dr.ellipse((d * ss * 0.18, d * ss * 0.12, d * ss * 0.55, d * ss * 0.45), fill=hl + (255,))
    im = im.resize((d, d), Image.LANCZOS)
    if emoji:
        e = emoji_img(emoji, int(d * 0.78))
        im.alpha_composite(e, ((d - e.width) // 2, (d - e.height) // 2))
    o = Image.new("RGBA", (d * ss, d * ss), (0, 0, 0, 0))
    ImageDraw.Draw(o).ellipse((2, 2, d * ss - 3, d * ss - 3), outline=ring + (255,), width=4 * ss)
    im.alpha_composite(o.resize((d, d), Image.LANCZOS))
    return im


def paste_c(base, spr, x, y):
    x0, y0 = int(x - spr.width / 2), int(y - spr.height / 2)
    l, t = max(0, -x0), max(0, -y0)
    r, b = min(spr.width, W - x0), min(spr.height, H - y0)
    if r > l and b > t:
        base.paste(spr.crop((l, t, r, b)), (x0 + l, y0 + t), spr.crop((l, t, r, b)))


def tone(f, d=0.4, dec=0.18, g=0.25):
    tt = np.arange(int(SR * d)) / SR
    s = np.sin(2 * np.pi * f * tt) + 0.35 * np.sin(4 * np.pi * f * tt) + 0.12 * np.sin(6 * np.pi * f * tt)
    return (s * np.exp(-tt / dec) * np.minimum(1, tt / 0.003) * g).astype(np.float32)


def thud():
    tt = np.arange(int(SR * 0.25)) / SR
    s = np.sin(2 * np.pi * np.cumsum(60 + 160 * np.exp(-tt / 0.02)) / SR) * np.exp(-tt / 0.08)
    n = np.random.default_rng(4).standard_normal(len(tt)) * np.exp(-tt / 0.01) * 0.5
    return ((s + n) * 0.6).astype(np.float32)


def clank():
    tt = np.arange(int(SR * 0.5)) / SR
    s = sum(np.sin(2 * np.pi * f * tt) * np.exp(-tt / dd) for f, dd in ((2093, 0.12), (3136, 0.08), (4186, 0.05), (1397, 0.2)))
    return (s * 0.18).astype(np.float32)


def fanfare():
    out = np.zeros(int(SR * 2.2), dtype=np.float32)
    for i, f in enumerate((523.3, 659.3, 784.0, 1046.5)):
        t_ = tone(f, 1.6, 0.6, 0.22)
        p = int(SR * 0.09 * i)
        out[p:p + len(t_)] += t_[:len(out) - p]
    return out


def mix(events, total):
    n = int(SR * (total + 0.5))
    a = np.zeros(n, dtype=np.float32)
    for at, sig, g in events:
        p = int(at * SR)
        if p < n:
            s = sig[:n - p]
            a[p:p + len(s)] += s * g
    a = np.tanh(a * 1.3)
    return a / max(np.max(np.abs(a)), 1e-6) * 0.9


# ------------------------------------------------------------------ battle
def sim_battle(seed, fighters):
    rng = random.Random(seed)
    R, r = 430.0, 74.0
    balls = []
    for k in range(2):
        a = rng.uniform(0, 2 * math.pi)
        balls.append(dict(p=np.array([CX + (-170 if k == 0 else 170), CY + rng.uniform(-80, 80)]),
                          v=np.array([math.cos(a), math.sin(a)]) * 640, hp=100.0, L=60.0, ang=rng.uniform(0, 6.28),
                          w=rng.choice([-1, 1]) * rng.uniform(3.6, 4.6), cd=0.0, flash=-9, dmg=6))
    dt = 1 / (FPS * SUB)
    t, frames, snd, pops, end_t, winner = 0.0, [], [], [], None, None
    last_wall = -1
    clank_cd = 0.0

    def seg(b):
        u = np.array([math.cos(b["ang"]), math.sin(b["ang"])])
        return b["p"] + u * (r - 6), b["p"] + u * (r + b["L"])

    def dist_seg(p, a, b):
        ab = b - a
        tt = clamp(np.dot(p - a, ab) / (np.dot(ab, ab) + 1e-9), 0, 1)
        return np.linalg.norm(p - (a + tt * ab))

    while t < 70:
        for _ in range(SUB):
            for b in balls:
                if b["hp"] <= 0:
                    continue
                b["p"] = b["p"] + b["v"] * dt
                b["ang"] += b["w"] * dt
                b["cd"] -= dt
                d = b["p"] - (CX, CY)
                dist = np.linalg.norm(d)
                if dist + r > R:
                    nrm = d / dist
                    b["p"] = np.array([CX, CY]) + nrm * (R - r)
                    vn = np.dot(b["v"], nrm)
                    if vn > 0:
                        b["v"] = b["v"] - 2 * vn * nrm
                        if t - last_wall > 0.08:
                            snd.append((t, tone(SCALE[rng.randint(0, 6)], 0.25, 0.08, 0.12), 1.0))
                            last_wall = t
                sp = np.linalg.norm(b["v"])
                b["v"] = b["v"] / sp * (640 + 4 * (100 - b["hp"]))     # gets a bit faster when hurt
            A, B = balls
            if end_t is None:
                dvec = B["p"] - A["p"]
                dd = np.linalg.norm(dvec)
                if dd < 2 * r:                                           # body collision (elastic, equal mass)
                    nrm = dvec / dd
                    rel = np.dot(A["v"] - B["v"], nrm)
                    if rel > 0:
                        A["v"] = A["v"] - rel * nrm
                        B["v"] = B["v"] + rel * nrm
                    over = 2 * r - dd
                    A["p"] = A["p"] - nrm * over / 2
                    B["p"] = B["p"] + nrm * over / 2
                # sword clash
                a0, a1 = seg(A)
                b0, b1 = seg(B)
                clank_cd -= dt
                if clank_cd <= 0 and segs_cross(a0, a1, b0, b1):
                    A["w"] *= -1
                    B["w"] *= -1
                    clank_cd = 0.25
                    snd.append((t, clank(), 0.9))
                # sword hits
                for att, vic in ((A, B), (B, A)):
                    s0, s1 = seg(att)
                    if att["cd"] <= 0 and dist_seg(vic["p"], s0, s1) < r:
                        vic["hp"] = max(0.0, vic["hp"] - att["dmg"])
                        att["L"] = min(att["L"] + 14, 230)
                        att["dmg"] += 1
                        att["cd"] = 0.35
                        vic["flash"] = t
                        kb = vic["p"] - att["p"]
                        vic["v"] = vic["v"] + kb / (np.linalg.norm(kb) + 1e-6) * 500
                        pops.append((t, vic["p"].copy(), -att["dmg"] + 1))
                        snd.append((t, thud(), 1.0))
                        snd.append((t, tone(SCALE[min(12, 3 + int((100 - vic["hp"]) / 9))], 0.3, 0.1, 0.2), 1.0))
                        if vic["hp"] <= 0:
                            end_t = t
                            winner = 0 if att is A else 1
                            snd.append((t + 0.15, fanfare(), 1.0))
            t += dt
        frames.append(dict(t=t, balls=[(b["p"].copy(), b["ang"], b["L"], b["hp"], t - b["flash"] < 0.12) for b in balls]))
        if end_t is not None and t > end_t + 2.2:
            break
    return frames, snd, pops, end_t, winner


def clamp(x, a, b):
    return max(a, min(b, x))


def segs_cross(p1, p2, p3, p4):
    def ccw(a, b, c):
        return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])
    return ccw(p1, p3, p4) != ccw(p2, p3, p4) and ccw(p1, p2, p3) != ccw(p1, p2, p4)


def render_battle(out, seed, hook, palette, fighters):
    tries = 0
    while True:
        frames, snd, pops, end_t, winner = sim_battle(seed, fighters)
        total = frames[-1]["t"]
        if end_t and 18 <= total <= 45:
            hp_left = frames[-1]["balls"][winner][3]
            if hp_left <= 45:                        # close fight -> more suspense
                break
        seed += 1
        tries += 1
        if tries > 200:
            raise SystemExit("no seed in range")
    emo = fighters if fighters and fighters[0] not in ("red",) else None
    names = [("RED", (239, 68, 68)), ("BLUE", (59, 130, 246))]
    sprites = []
    for k in range(2):
        if emo:
            sprites.append(ball_sprite(74, emoji=emo[k], ring=names[k][1]))
        else:
            sprites.append(ball_sprite(74, col=names[k][1]))
    flash_spr = [ball_sprite(74, col=(255, 255, 255)) for _ in range(2)]
    wname = (emo[winner] if emo else names[winner][0])
    print("seed", seed, "duration", round(total, 1), "winner", wname)
    # funny commentary stickers derived from the fight
    prng = random.Random(seed * 3 + 1)
    popups, last_pop = [], -9.0

    def add_pop(tp, text, emoji, dur=1.4, loud=False):
        nonlocal last_pop
        if tp - last_pop < 1.2 or (end_t and tp > end_t - 0.3):
            return
        spr = fxlib.sticker(text, emoji, size=58, angle=prng.choice([-6, -4, 4, 6]))
        popups.append((tp, spr, W / 2, CY - 300, dur))
        snd.append((tp, fxlib.boom(SR) if loud else fxlib.pop(SR), 0.6 if loud else 0.8))
        last_pop = tp
    if pops:
        add_pop(pops[0][0], "FIRST BLOOD", "🩸")
    cooked = [False, False]
    for f_ in frames:
        for k in range(2):
            hp = f_["balls"][k][3]
            if not cooked[k] and 0 < hp <= 35:
                cooked[k] = True
                who = "BRO" if emo else names[k][0]
                add_pop(f_["t"], f"{who} {prng.choice(COOKED)}", emo[k] if emo else "💀", 1.6, loud=True)
    hp_hist = [(f_["t"], f_["balls"][0][3] - f_["balls"][1][3]) for f_ in frames]
    lead = 0
    for tt_, diff in hp_hist:
        sgn = 1 if diff > 12 else (-1 if diff < -12 else 0)
        if sgn and lead and sgn != lead:
            add_pop(tt_, "COMEBACK?!", "😳")
        if sgn:
            lead = sgn
    audio = mix(snd, total)
    import soundfile as sf
    sf.write(out + ".wav", audio, SR)
    h0 = PALETTES.get(palette, 0.55)
    bg = make_bg()
    ff = open_ff(out)
    for f in frames:
        t = f["t"]
        img = bg.copy()
        glow = Image.new("RGB", (W // 2, H // 2), (0, 0, 0))
        gd = ImageDraw.Draw(glow)
        d = ImageDraw.Draw(img)
        ac = hue_col(h0 + 0.01 * t, 0.58)
        box = (CX - 430, CY - 430, CX + 430, CY + 430)
        d.ellipse(box, outline=ac, width=10)
        gd.ellipse(tuple(v / 2 for v in box), outline=ac, width=8)
        for k, (p, ang, L, hp, fl) in enumerate(f["balls"]):
            if hp <= 0 and end_t and t > end_t + 0.4:
                continue
            col = names[k][1]
            u = (math.cos(ang), math.sin(ang))
            a = (p[0] + u[0] * 68, p[1] + u[1] * 68)
            b = (p[0] + u[0] * (74 + L), p[1] + u[1] * (74 + L))
            d.line([a, b], fill=(230, 232, 240), width=16)
            d.line([a, b], fill=col, width=6)
            gd.line([(a[0] / 2, a[1] / 2), (b[0] / 2, b[1] / 2)], fill=col, width=6)
            spr = flash_spr[k] if fl else sprites[k]
            paste_c(img, spr, p[0], p[1])
            gd.ellipse(((p[0] - 82) / 2, (p[1] - 82) / 2, (p[0] + 82) / 2, (p[1] + 82) / 2), fill=col)
        glow = glow.filter(ImageFilter.GaussianBlur(10)).resize((W, H), Image.BILINEAR)
        img = ImageChops.add(img, glow)
        d = ImageDraw.Draw(img)
        # damage popups
        for (pt, pp, dmg) in pops:
            age = t - pt
            if 0 <= age < 0.8:
                fz = font(64)
                s = f"{dmg}"
                d.text((pp[0] - d.textlength(s, font=fz) / 2, pp[1] - 120 - 90 * age), s, font=fz,
                       fill=(255, 230, 80), stroke_width=6, stroke_fill=(0, 0, 0))
        # HP bars
        for k in range(2):
            hp = f["balls"][k][3]
            x0 = 80 if k == 0 else W - 80 - 400
            y0 = 520
            d.rounded_rectangle((x0, y0, x0 + 400, y0 + 44), radius=22, fill=(40, 40, 52))
            if hp > 0:
                d.rounded_rectangle((x0, y0, x0 + 400 * hp / 100, y0 + 44), radius=22, fill=names[k][1])
            lab = f"{int(math.ceil(hp))}"
            d.text((x0 + 200 - d.textlength(lab, font=font(36)) / 2, y0 + 2), lab, font=font(36), fill=(255, 255, 255),
                   stroke_width=3, stroke_fill=(0, 0, 0))
            if emo:
                e = emoji_img(emo[k], 70)
                paste_c(img, e, x0 + (40 if k == 1 else 360), y0 - 55)
            else:
                nm = names[k][0]
                tx = x0 if k == 0 else x0 + 400 - d.textlength(nm, font=font(44))
                d.text((tx, y0 - 62), nm, font=font(44), fill=names[k][1])
        d.text((W / 2 - d.textlength("VS", font=font(56)) / 2, 506), "VS", font=font(56), fill=(255, 255, 255))
        draw_hook(d, hook)
        fxlib.draw_popups(img, popups, t)
        d = ImageDraw.Draw(img)
        if end_t and t >= end_t + 0.3:
            msg = f"{names[winner][0]} WINS!" if not emo else "WINS!"
            fz = font(120)
            d.text((W / 2 - d.textlength(msg, font=fz) / 2, CY - 70 + (60 if emo else 0)), msg, font=fz, fill=(255, 255, 255),
                   stroke_width=9, stroke_fill=(0, 0, 0))
            if emo:
                paste_c(img, emoji_img(emo[winner], 170), W / 2, CY - 110)
        d.text((70, 150), "unreel", font=font(40), fill=(255, 255, 255))
        ff.stdin.write(img.tobytes())
    close_ff(ff, out)
    return seed, total, wname


# ------------------------------------------------------------------ elimination
def sim_elim(seed, n):
    rng = random.Random(seed)
    R, r = 430.0, 52.0
    gap = math.radians(rng.uniform(34, 42))
    rot, rs = rng.uniform(0, 6.28), rng.choice([-1, 1]) * rng.uniform(0.6, 1.0)
    g = 1000.0
    P, V = [], []
    while len(P) < n:
        p = np.array([CX + rng.uniform(-260, 260), CY + rng.uniform(-260, 200)])
        if all(np.linalg.norm(p - q) > 2 * r + 4 for q in P):
            P.append(p)
            a = rng.uniform(0, 6.28)
            V.append(np.array([math.cos(a), math.sin(a)]) * 600)
    alive = [True] * n
    out_t = [None] * n
    dt = 1 / (FPS * SUB)
    t, frames, snd, end_t, winner = 0.0, [], [], None, None
    last_b = -1
    bi = 0
    while t < 80:
        for _ in range(SUB):
            for i in range(n):
                V[i] = V[i] + np.array([0, g * dt])
                P[i] = P[i] + V[i] * dt
            idx = [i for i in range(n) if alive[i]]
            for a_ in range(len(idx)):
                for b_ in range(a_ + 1, len(idx)):
                    i, j = idx[a_], idx[b_]
                    dv = P[j] - P[i]
                    dd = math.hypot(dv[0], dv[1])
                    if dd < 2 * r and dd > 1e-6:
                        nrm = dv / dd
                        rel = np.dot(V[i] - V[j], nrm)
                        if rel > 0:
                            V[i] = V[i] - rel * nrm
                            V[j] = V[j] + rel * nrm
                        ov = 2 * r - dd
                        P[i] = P[i] - nrm * ov / 2
                        P[j] = P[j] + nrm * ov / 2
            for i in idx:
                d = P[i] - (CX, CY)
                dist = math.hypot(d[0], d[1])
                if dist - r > R + 8:
                    alive[i] = False
                    out_t[i] = t
                    snd.append((t, tone(392, 0.5, 0.2, 0.25), 1.0))
                    snd.append((t + 0.08, tone(261.6, 0.6, 0.25, 0.25), 1.0))
                    continue
                if dist + r >= R - 4 and dist < R:
                    ang = (math.atan2(d[1], d[0]) - rot) % (2 * math.pi)
                    half = gap / 2 - math.asin(r / R)
                    if ang < half or ang > 2 * math.pi - half:
                        continue
                    nrm = d / dist
                    vn = np.dot(V[i], nrm)
                    if vn > 0:
                        P[i] = np.array([CX, CY]) + nrm * (R - 4 - r - 0.5)
                        V[i] = V[i] - 2 * vn * nrm
                        sp = math.hypot(V[i][0], V[i][1])
                        V[i] = V[i] / sp * max(sp, 820)
                        tg = np.array([-nrm[1], nrm[0]])
                        V[i] = V[i] + tg * rng.uniform(-90, 90)
                        if t - last_b > 0.07:
                            snd.append((t, tone(SCALE[bi % 11], 0.3, 0.1, 0.13), 1.0))
                            bi += 1
                            last_b = t
            rot += rs * dt
            t += dt
        left = [i for i in range(n) if alive[i]]
        frames.append(dict(t=t, P=[p.copy() for p in P], alive=list(alive), out=list(out_t), rot=rot, gap=gap, left=len(left)))
        if len(left) == 1 and end_t is None:
            end_t, winner = t, left[0]
            snd.append((t, fanfare(), 1.0))
        if end_t is not None and t > end_t + 2.5:
            break
    return frames, snd, end_t, winner


def render_elim(out, seed, hook, palette, set_):
    if set_ in SETS:
        pool = SETS[set_]
    elif set_ == "colors" or not set_:
        pool = None
    else:
        pool = [s for s in set_.split(",") if s.strip()]
    tries = 0
    while True:
        rr = random.Random(seed)
        n = min(rr.randint(8, 12), len(pool) if pool else 12)
        frames, snd, end_t, winner = sim_elim(seed, n)
        total = frames[-1]["t"]
        if end_t and 20 <= total <= 50:
            outs = sorted(x for x in frames[-1]["out"] if x is not None)
            if outs and outs[0] < 5.0:                   # first elimination early (hook)
                break
        seed += 1
        tries += 1
        if tries > 200:
            raise SystemExit("no seed in range")
    rr = random.Random(seed * 7 + 1)
    items = rr.sample(pool, n) if pool else list(range(n))
    sprites = []
    for k in range(n):
        if pool:
            sprites.append(ball_sprite(52, emoji=items[k], ring=hue_col(k / n, 0.6)))
        else:
            sprites.append(ball_sprite(52, col=COLORS[k]))
    wname = items[winner] if pool else COLOR_NAMES[winner]
    print("seed", seed, "duration", round(total, 1), "balls", n, "winner", wname, "field", " ".join(map(str, items)) if pool else "colors")
    prng = random.Random(seed * 5 + 2)
    popups, last_pop = [], -9.0
    outs_all = sorted((ot, k) for k, ot in enumerate(frames[-1]["out"]) if ot is not None)
    for idx, (ot, k) in enumerate(outs_all):
        if ot - last_pop < 1.1:
            continue
        left = n - idx - 1
        if left == 2:
            txt, em = "FINAL TWO", "😳"
        elif pool:
            txt, em = prng.choice(OUT_LINES), items[k]
        else:
            txt, em = f"{COLOR_NAMES[k]} {prng.choice(['IS OUT', 'GONE', 'SKILL ISSUE'])}", "💀"
        popups.append((ot, fxlib.sticker(txt, em, size=56, angle=prng.choice([-6, -4, 4, 6])), W / 2, CY - 270, 1.3))
        snd.append((ot, fxlib.pop(SR), 0.7))
        last_pop = ot
    audio = mix(snd, total)
    import soundfile as sf
    sf.write(out + ".wav", audio, SR)
    h0 = PALETTES.get(palette, 0.55)
    bg = make_bg()
    ff = open_ff(out)
    for f in frames:
        t = f["t"]
        img = bg.copy()
        glow = Image.new("RGB", (W // 2, H // 2), (0, 0, 0))
        gd = ImageDraw.Draw(glow)
        d = ImageDraw.Draw(img)
        col = hue_col(h0 + 0.015 * t, 0.58)
        rot, gap = f["rot"], f["gap"]
        box = (CX - 430, CY - 430, CX + 430, CY + 430)
        a0, a1 = math.degrees(rot + gap / 2), math.degrees(rot - gap / 2 + 2 * math.pi)
        d.arc(box, a0, a1, fill=col, width=11)
        gd.arc(tuple(v / 2 for v in box), a0, a1, fill=col, width=8)
        glow = glow.filter(ImageFilter.GaussianBlur(10)).resize((W, H), Image.BILINEAR)
        img = ImageChops.add(img, glow)
        for k in range(n):
            p = f["P"][k]
            if not f["alive"][k] and (p[1] > H + 50):
                continue
            paste_c(img, sprites[k], p[0], p[1])
        d = ImageDraw.Draw(img)
        draw_hook(d, hook)
        # eliminated tray
        outs = sorted([(f["out"][k], k) for k in range(n) if f["out"][k] is not None])
        lab = f"{f['left']} LEFT"
        d.text((W / 2 - d.textlength(lab, font=font(60)) / 2, 470), lab, font=font(60), fill=col)
        for j, (ot, k) in enumerate(outs):
            x = 110 + j * 78
            spr = sprites[k].resize((60, 60), Image.LANCZOS)
            paste_c(img, spr, x, 600)
            d.line([(x - 22, 578), (x + 22, 622)], fill=(239, 68, 68), width=6)
            d.line([(x - 22, 622), (x + 22, 578)], fill=(239, 68, 68), width=6)
        fxlib.draw_popups(img, popups, t)
        d = ImageDraw.Draw(img)
        if end_t and t >= end_t + 0.2:
            msg = "WINS!"
            fz = font(130)
            if not pool:
                msg = f"{COLOR_NAMES[winner]} WINS!"
                mx = W / 2 - d.textlength(msg, font=fz) / 2
            else:
                mx = W / 2 - d.textlength(msg, font=fz) / 2 + 70
                paste_c(img, sprites[winner].resize((150, 150), Image.LANCZOS), mx - 95, CY + 545)
                d = ImageDraw.Draw(img)
            d.text((mx, CY + 470), msg, font=fz, fill=(255, 255, 255),
                   stroke_width=9, stroke_fill=(0, 0, 0))
        d.text((70, 150), "unreel", font=font(40), fill=(255, 255, 255))
        ff.stdin.write(img.convert("RGB").tobytes())
    close_ff(ff, out)
    return seed, total, wname


# ------------------------------------------------------------------ shared
def make_bg():
    yy, xx = np.mgrid[0:H, 0:W]
    dd = np.hypot((xx - CX) / W, (yy - CY) / H)
    base = np.clip(28 - dd * 40, 4, 28)
    return Image.fromarray(np.stack([base * 0.8, base * 0.8, base * 1.15], -1).astype(np.uint8), "RGB")


def draw_hook(d, hook):
    y = 215
    sz = 92
    while sz > 50 and max(d.textlength(l, font=font(sz)) for l in hook) > 940:
        sz -= 4
    for line in hook:
        fz = font(sz)
        d.text(((W - d.textlength(line, font=fz)) / 2, y), line, font=fz, fill=(255, 255, 255), stroke_width=7,
               stroke_fill=(0, 0, 0))
        y += int(sz * 1.15)


def open_ff(out):
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-i", out + ".wav", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
           "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "44100", "-c:a", "aac", "-b:a", "192k", "-shortest",
           "-movflags", "+faststart", out]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)


def close_ff(ff, out):
    import os
    ff.stdin.close()
    ff.wait()
    os.remove(out + ".wav")


if __name__ == "__main__":
    mode, out = sys.argv[1], sys.argv[2]
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    default = {"battle": "WHO WINS?|EVERY HIT = LONGER SWORD", "elimination": "LAST ONE INSIDE|WINS"}
    hook = (sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else default[mode]).split("|")
    pal = sys.argv[5] if len(sys.argv) > 5 else "neon"
    extra = sys.argv[6] if len(sys.argv) > 6 else ""
    if mode == "battle":
        fighters = [x for x in extra.split(",") if x] if extra and extra != "red,blue" else None
        s, tot, w = render_battle(out, seed, hook, pal, fighters)
    else:
        s, tot, w = render_elim(out, seed, hook, pal, extra or "flags")
    print(f"done {out} seed={s} {tot:.1f}s winner={w}")
