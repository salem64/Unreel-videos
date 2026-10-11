#!/usr/bin/env python3
"""Unreel arena physics shorts (called via tools/physics.py, or directly).

python3 tools/arena.py battle out.mp4 [seed] ["HOOK1|HOOK2"] [palette] [fighters]
    Ball vs ball with WEAPONS; every hit = damage and the attacker's weapon gets stronger.
    Weapons: sword (longer), spear (longer, long reach), dagger (spins faster), hammer (bigger head, huge knockback),
             saws (one more orbiting saw), spikes (longer spikes, contact damage), bow (one more arrow per volley;
             blade weapons can block arrows), flail (NEW 2026-10-11: spiked ball on a chain, every hit = longer chain
             + bigger ball, "WRECKING BALL" at long chain; chain can't block). Sudden death (damage ramps up) after 30 s.
    fighters: "red:sword,blue:bow" | "🥔:hammer,🍟:spikes" | "sword,bow" (colours) | "🐶,🐱" (random weapons) | "" (random).
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


def flat_ball(r, col):
    """Clean cartoon ball: flat colour, soft shade, small highlight, thick dark outline (no emoji, no gloss)."""
    ss = 3
    d = 2 * r * ss
    dark = tuple(int(c * 0.72) for c in col)
    line = tuple(int(c * 0.28) for c in col)
    im = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    mask = Image.new("L", (d, d), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, d - 1, d - 1), fill=255)
    body = Image.new("RGBA", (d, d), dark + (255,))
    bd = ImageDraw.Draw(body)
    bd.ellipse((-d * 0.10, -d * 0.10, d * 0.94, d * 0.94), fill=col + (255,))
    bd.ellipse((d * 0.20, d * 0.12, d * 0.42, d * 0.28), fill=(255, 255, 255, 70))
    im.paste(body, (0, 0), mask)
    ImageDraw.Draw(im).ellipse((ss * 3, ss * 3, d - 1 - ss * 3, d - 1 - ss * 3), outline=line + (255,), width=ss * 6)
    return im.resize((2 * r, 2 * r), Image.LANCZOS)


def draw_eyes(d, p, r, look, hp=100.0, dead=False):
    """Cartoon eyes looking towards `look` (unit vector); angry brows when hp is low, X eyes when dead."""
    lx, ly = look
    for sgn in (-1, 1):
        ex, ey = p[0] + sgn * r * 0.32, p[1] - r * 0.10
        ew, eh = r * 0.27, r * 0.34
        if dead:
            w_ = max(3, int(r * 0.08))
            d.line([(ex - ew * 0.7, ey - eh * 0.6), (ex + ew * 0.7, ey + eh * 0.6)], fill=(20, 20, 25), width=w_)
            d.line([(ex - ew * 0.7, ey + eh * 0.6), (ex + ew * 0.7, ey - eh * 0.6)], fill=(20, 20, 25), width=w_)
            continue
        d.ellipse((ex - ew, ey - eh, ex + ew, ey + eh), fill=(255, 255, 255), outline=(20, 20, 25), width=max(2, int(r * 0.04)))
        pr = r * 0.135
        px, py = ex + lx * ew * 0.45, ey + ly * eh * 0.45
        d.ellipse((px - pr, py - pr, px + pr, py + pr), fill=(20, 20, 25))
        d.ellipse((px - pr * 0.35 + pr * 0.3, py - pr * 0.35 - pr * 0.3, px + pr * 0.35 + pr * 0.3, py + pr * 0.35 - pr * 0.3), fill=(255, 255, 255))
        if hp < 35:
            w_ = max(3, int(r * 0.07))
            d.line([(ex - sgn * ew * 1.1, ey - eh * 1.35), (ex + sgn * ew * 0.9, ey - eh * 0.85)], fill=(20, 20, 25), width=w_)


def draw_crown(d, p, r):
    cx, top = p[0], p[1] - r - 6
    w_, h_ = r * 0.9, r * 0.5
    pts = [(cx - w_ / 2, top), (cx - w_ / 2, top - h_ * 0.6), (cx - w_ / 4, top - h_ * 0.25), (cx, top - h_),
           (cx + w_ / 4, top - h_ * 0.25), (cx + w_ / 2, top - h_ * 0.6), (cx + w_ / 2, top)]
    d.polygon(pts, fill=(255, 205, 40), outline=(90, 60, 0), width=4)


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
WEAPONS = {
    # type: start values; every hit upgrades the attacker's weapon (see upgrade())
    "sword":  dict(L=60, dmg=6, w=4.1, cd=0.35, emoji="🗡️"),
    "spear":  dict(L=120, dmg=7, w=2.4, cd=0.40, emoji="🔱"),
    "dagger": dict(L=36, dmg=4, w=7.0, cd=0.25, emoji="🔪"),
    "hammer": dict(L=70, dmg=9, w=2.8, cd=0.45, head=22, emoji="🔨"),
    "saws":   dict(n=2, dmg=4, w=3.6, cd=0.30, emoji="⚙️"),
    "spikes": dict(S=16, dmg=7, w=1.2, cd=0.40, emoji="🌵"),
    "bow":    dict(n=1, dmg=4, w=0.0, cd=0.00, period=1.1, emoji="🏹"),
    "flail":  dict(L=80, dmg=7, w=3.2, cd=0.40, head=20, emoji="⛓️"),
}
SEG_WEAPONS = ("sword", "spear", "dagger", "hammer")


def parse_fighters(extra, seed):
    """'red:sword,blue:bow' | '🥔:hammer,🍟:spikes' | 'sword,bow' | '🐶,🐱' | '' -> (emojis or None, [w1, w2])"""
    rng = random.Random(seed * 11 + 5)
    items = [x.strip() for x in (extra or "").split(",") if x.strip()]
    names, weps = [], []
    for it in items[:2]:
        nm, _, wp = it.partition(":")
        if nm in WEAPONS and not wp:
            nm, wp = "", nm
        names.append(nm)
        weps.append(wp if wp in WEAPONS else "")
    while len(names) < 2:
        names.append("")
        weps.append("")
    pool = list(WEAPONS)
    for k in range(2):
        if not weps[k]:
            weps[k] = rng.choice([w for w in pool if w not in weps])
    emo = names if all(n and n.lower() not in ("red", "blue") for n in names) else None
    return emo, weps


def sim_battle(seed, weps):
    rng = random.Random(seed)
    R, r = 430.0, 74.0
    balls = []
    for k in range(2):
        a = rng.uniform(0, 2 * math.pi)
        W0 = WEAPONS[weps[k]]
        b = dict(p=np.array([CX + (-170 if k == 0 else 170), CY + rng.uniform(-80, 80)]),
                 v=np.array([math.cos(a), math.sin(a)]) * 640, hp=100.0, ang=rng.uniform(0, 6.28),
                 cdt=0.0, flash=-9, type=weps[k], fire=0.6 + 0.3 * k)
        for key in ("L", "dmg", "w", "head", "n", "S", "period"):
            if key in W0:
                b[key] = float(W0[key])
        b["w"] = b.get("w", 0.0) * rng.choice([-1, 1])
        b["w0"] = abs(b["w"]) or 1.0
        balls.append(b)
    arrows = []                                    # [pos, vel, owner]
    dt = 1 / (FPS * SUB)
    t, frames, snd, pops, end_t, winner, events = 0.0, [], [], [], None, None, []
    last_wall = -1
    clank_cd = 0.0

    def unit(b, extra=0.0):
        return np.array([math.cos(b["ang"] + extra), math.sin(b["ang"] + extra)])

    def seg(b):
        u = unit(b)
        return b["p"] + u * (r - 6), b["p"] + u * (r + b["L"])

    def dist_seg(p, a, c):
        ab = c - a
        tt = clamp(np.dot(p - a, ab) / (np.dot(ab, ab) + 1e-9), 0, 1)
        return np.linalg.norm(p - (a + tt * ab))

    def upgrade(b, k):
        ty = b["type"]
        if ty == "sword":
            b["L"] = min(b["L"] + 14, 230); b["dmg"] += 1
        elif ty == "spear":
            b["L"] = min(b["L"] + 12, 260); b["dmg"] += 1
        elif ty == "dagger":
            b["w"] = math.copysign(min(abs(b["w"]) * 1.15, 18), b["w"]); b["dmg"] += 0.5
            if abs(b["w"]) >= 12 and not b.get("m1"):
                b["m1"] = 1; events.append((t, "SPEED DEMON", WEAPONS["dagger"]["emoji"], k))
        elif ty == "hammer":
            b["head"] = min(b["head"] + 4, 52); b["dmg"] += 1.5
            if b["head"] >= 38 and not b.get("m1"):
                b["m1"] = 1; events.append((t, "BIG HAMMER TIME", "🔨", k))
        elif ty == "saws":
            b["n"] = min(b["n"] + 1, 8)
            if b["n"] == 5:
                events.append((t, "SAW STORM", "⚙️", k))
        elif ty == "spikes":
            b["S"] = min(b["S"] + 6, 54); b["dmg"] += 2
            if b["S"] >= 40 and not b.get("m1"):
                b["m1"] = 1; events.append((t, "SPIKY BOY", "🌵", k))
        elif ty == "flail":
            b["L"] = min(b["L"] + 14, 210); b["head"] = min(b["head"] + 2.5, 40); b["dmg"] += 1
            if b["L"] >= 150 and not b.get("m1"):
                b["m1"] = 1; events.append((t, "WRECKING BALL", "⛓️", k))
        elif ty == "bow":
            b["n"] = min(b["n"] + 1, 6)
            if b["n"] == 3:
                events.append((t, "TRIPLE SHOT", "🏹", k))

    def hit(att, vic, k_att, mult, kb=500):
        nonlocal end_t, winner
        dmg = att["dmg"] * mult
        vic["hp"] = max(0.0, vic["hp"] - dmg)
        vic["flash"] = t
        d_ = vic["p"] - att["p"]
        vic["v"] = vic["v"] + d_ / (np.linalg.norm(d_) + 1e-6) * kb
        pops.append((t, vic["p"].copy(), -int(round(dmg))))
        snd.append((t, thud(), 1.0))
        snd.append((t, tone(SCALE[min(12, 3 + int((100 - vic["hp"]) / 9))], 0.3, 0.1, 0.2), 1.0))
        upgrade(att, k_att)
        if vic["hp"] <= 0 and end_t is None:
            end_t = t
            winner = k_att
            snd.append((t + 0.15, fanfare(), 1.0))

    sudden = False
    while t < 75:
        mult = 1.0 + max(0.0, t - 30) / 8          # sudden death after 30 s keeps fights short
        if t > 30 and not sudden and end_t is None:
            sudden = True
            events.append((t, "SUDDEN DEATH", "⚡", -1))
        for _ in range(SUB):
            for b in balls:
                if b["hp"] <= 0:
                    continue
                b["p"] = b["p"] + b["v"] * dt
                b["ang"] += b["w"] * dt
                b["cdt"] -= dt
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
                b["v"] = b["v"] / sp * (640 + 4 * (100 - b["hp"]))
            A, B = balls
            if end_t is None:
                dvec = B["p"] - A["p"]
                dd = np.linalg.norm(dvec)
                if dd < 2 * r:                                            # body collision
                    nrm = dvec / dd
                    rel = np.dot(A["v"] - B["v"], nrm)
                    if rel > 0:
                        A["v"] = A["v"] - rel * nrm
                        B["v"] = B["v"] + rel * nrm
                    over = 2 * r - dd
                    A["p"] = A["p"] - nrm * over / 2
                    B["p"] = B["p"] + nrm * over / 2
                    for k_, (att, vic) in enumerate(((A, B), (B, A))):  # spikes hurt on contact
                        if att["type"] == "spikes" and att["cdt"] <= 0:
                            hit(att, vic, k_, mult, 700)
                            att["cdt"] = WEAPONS["spikes"]["cd"]
                # clash between blade weapons
                clank_cd -= dt
                if clank_cd <= 0 and A["type"] in SEG_WEAPONS and B["type"] in SEG_WEAPONS:
                    a0, a1 = seg(A)
                    b0, b1 = seg(B)
                    if segs_cross(a0, a1, b0, b1):
                        A["w"] *= -1
                        B["w"] *= -1
                        clank_cd = 0.25
                        snd.append((t, clank(), 0.9))
                for k_, (att, vic) in enumerate(((A, B), (B, A))):
                    ty = att["type"]
                    if att["cdt"] > 0:
                        pass
                    elif ty in ("sword", "spear", "dagger"):
                        s0, s1 = seg(att)
                        if dist_seg(vic["p"], s0, s1) < r:
                            hit(att, vic, k_, mult)
                            att["cdt"] = WEAPONS[ty]["cd"]
                    elif ty == "hammer":
                        s0, s1 = seg(att)
                        hc = att["p"] + unit(att) * (r + att["L"] + att["head"])
                        if np.linalg.norm(vic["p"] - hc) < r + att["head"] or dist_seg(vic["p"], s0, s1) < r * 0.7:
                            hit(att, vic, k_, mult, 1000)
                            att["cdt"] = WEAPONS[ty]["cd"]
                    elif ty == "flail":
                        hc = att["p"] + unit(att) * (r + att["L"] + att["head"])
                        if np.linalg.norm(vic["p"] - hc) < r + att["head"]:
                            hit(att, vic, k_, mult, 850)
                            att["cdt"] = WEAPONS[ty]["cd"]
                    elif ty == "saws":
                        for i in range(int(att["n"])):
                            sc = att["p"] + unit(att, 2 * math.pi * i / att["n"]) * (r + 42)
                            if np.linalg.norm(vic["p"] - sc) < r + 22:
                                hit(att, vic, k_, mult, 400)
                                att["cdt"] = WEAPONS[ty]["cd"]
                                break
                    if ty == "bow":
                        att["fire"] -= dt
                        if att["fire"] <= 0:
                            att["fire"] = att["period"]
                            aim = math.atan2(vic["p"][1] - att["p"][1], vic["p"][0] - att["p"][0])
                            att["ang"] = aim
                            nn = int(att["n"])
                            for i in range(nn):
                                a_ = aim + math.radians(12) * (i - (nn - 1) / 2)
                                u = np.array([math.cos(a_), math.sin(a_)])
                                arrows.append([att["p"] + u * (r + 10), u * 1050, k_])
                            snd.append((t, tone(880, 0.12, 0.04, 0.15), 1.0))
                # arrows
                keep = []
                for ar in arrows:
                    ar[0] = ar[0] + ar[1] * dt
                    owner = ar[2]
                    vic = balls[1 - owner]
                    if np.linalg.norm(ar[0] - (CX, CY)) > R:
                        continue
                    if vic["type"] in SEG_WEAPONS:
                        s0, s1 = seg(vic)
                        if dist_seg(ar[0], s0, s1) < 10:
                            snd.append((t, clank(), 0.5))
                            continue                      # blocked!
                    if np.linalg.norm(ar[0] - vic["p"]) < r:
                        hit(balls[owner], vic, owner, mult, 250)
                        continue
                    keep.append(ar)
                arrows = keep
            t += dt
        frames.append(dict(t=t, balls=[dict(p=b["p"].copy(), ang=b["ang"], hp=b["hp"], fl=t - b["flash"] < 0.12, type=b["type"],
                                             L=b.get("L", 0), head=b.get("head", 0), n=b.get("n", 0), S=b.get("S", 0),
                                             spd=abs(b["w"]) / b["w0"], dmg=b["dmg"]) for b in balls],
                           arrows=[(a[0].copy(), a[1].copy(), a[2]) for a in arrows]))
        if end_t is not None and t > end_t + 2.2:
            break
    return frames, snd, pops, end_t, winner, events


def clamp(x, a, b):
    return max(a, min(b, x))


def segs_cross(p1, p2, p3, p4):
    def ccw(a, b, c):
        return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])
    return ccw(p1, p3, p4) != ccw(p2, p3, p4) and ccw(p1, p2, p3) != ccw(p1, p2, p4)


def weapon_label(b):
    ty = b["type"]
    if ty in ("sword", "spear"):
        return f"{ty.upper()}  LEN {int(b['L'])}"
    if ty == "dagger":
        return f"DAGGER  SPEED x{b['spd']:.1f}"
    if ty == "hammer":
        return f"HAMMER  SIZE {int(b['head'])}"
    if ty == "saws":
        return f"SAWS  x{int(b['n'])}"
    if ty == "spikes":
        return f"SPIKES  DMG {int(b['dmg'])}"
    if ty == "flail":
        return f"FLAIL  CHAIN {int(b['L'])}"
    return f"BOW  x{int(b['n'])} ARROWS"


def draw_weapon(d, gd, b, col):
    p, ang, ty, r = b["p"], b["ang"], b["type"], 74
    u = (math.cos(ang), math.sin(ang))
    nrm = (-u[1], u[0])
    steel = (225, 228, 238)

    def P(dist, off=0.0):
        return (p[0] + u[0] * dist + nrm[0] * off, p[1] + u[1] * dist + nrm[1] * off)

    def glow_line(a, b_, w):
        gd.line([(a[0] / 2, a[1] / 2), (b_[0] / 2, b_[1] / 2)], fill=col, width=w)

    if ty == "sword":
        a, e = P(r - 6), P(r + b["L"])
        d.polygon([P(r + 4, -9), P(r + b["L"] - 14, -9), P(r + b["L"] + 6, 0), P(r + b["L"] - 14, 9), P(r + 4, 9)], fill=steel)
        d.line([P(r + b["L"] * 0.15, 0), P(r + b["L"] - 10, 0)], fill=col, width=3)
        d.line([P(r + 2, -22), P(r + 2, 22)], fill=col, width=9)          # cross guard
        glow_line(a, e, 6)
    elif ty == "spear":
        a, e = P(r - 6), P(r + b["L"])
        d.line([a, e], fill=(150, 108, 66), width=9)
        d.polygon([P(r + b["L"] - 4, -14), P(r + b["L"] + 34, 0), P(r + b["L"] - 4, 14)], fill=steel, outline=col)
        glow_line(P(r + b["L"]), P(r + b["L"] + 34), 6)
    elif ty == "dagger":
        d.line([P(r - 6), P(r + 10)], fill=col, width=12)
        d.polygon([P(r + 10, -10), P(r + b["L"] + 4, -3), P(r + b["L"] + 16, 0), P(r + b["L"] + 4, 3), P(r + 10, 10)], fill=steel)
        glow_line(P(r + 10), P(r + b["L"] + 16), 5)
    elif ty == "hammer":
        hr = b["head"]
        d.line([P(r - 6), P(r + b["L"])], fill=(120, 120, 135), width=11)
        hc = P(r + b["L"] + hr)
        d.rounded_rectangle((hc[0] - hr, hc[1] - hr, hc[0] + hr, hc[1] + hr), radius=int(hr * 0.35), fill=(170, 172, 185), outline=col, width=5)
        gd.ellipse(((hc[0] - hr) / 2, (hc[1] - hr) / 2, (hc[0] + hr) / 2, (hc[1] + hr) / 2), fill=col)
    elif ty == "flail":
        hr, L = b["head"], b["L"]
        sag = 10 + L * 0.08                                  # chain bows behind the swing
        links = max(6, int(L / 13))
        prev = None
        for i in range(links + 1):
            f_ = i / links
            pt = P(r - 4 + (L + 4) * f_, -sag * math.sin(math.pi * f_))
            if prev is not None:
                d.line([prev, pt], fill=(150, 152, 165), width=5)
            d.ellipse((pt[0] - 5, pt[1] - 5, pt[0] + 5, pt[1] + 5), outline=(205, 208, 220), width=3)
            prev = pt
        hc = P(r + L + hr)
        for j in range(10):                                   # spikes on the ball
            aa = ang * 1.7 + j * math.pi / 5
            tip = (hc[0] + math.cos(aa) * (hr + 12), hc[1] + math.sin(aa) * (hr + 12))
            b1 = (hc[0] + math.cos(aa - 0.28) * hr, hc[1] + math.sin(aa - 0.28) * hr)
            b2 = (hc[0] + math.cos(aa + 0.28) * hr, hc[1] + math.sin(aa + 0.28) * hr)
            d.polygon([b1, tip, b2], fill=steel, outline=col)
        d.ellipse((hc[0] - hr, hc[1] - hr, hc[0] + hr, hc[1] + hr), fill=(95, 98, 112), outline=col, width=5)
        d.ellipse((hc[0] - hr * 0.5, hc[1] - hr * 0.6, hc[0] - hr * 0.05, hc[1] - hr * 0.15), fill=(160, 164, 180))
        gd.ellipse(((hc[0] - hr - 8) / 2, (hc[1] - hr - 8) / 2, (hc[0] + hr + 8) / 2, (hc[1] + hr + 8) / 2), fill=col)
    elif ty == "saws":
        n = int(b["n"])
        for i in range(n):
            a_ = ang + 2 * math.pi * i / n
            c = (p[0] + math.cos(a_) * (r + 42), p[1] + math.sin(a_) * (r + 42))
            pts = []
            for j in range(16):
                rad = 22 if j % 2 == 0 else 14
                aa = ang * 3 + j * math.pi / 8
                pts.append((c[0] + math.cos(aa) * rad, c[1] + math.sin(aa) * rad))
            d.polygon(pts, fill=steel, outline=col)
            d.ellipse((c[0] - 5, c[1] - 5, c[0] + 5, c[1] + 5), fill=col)
            gd.ellipse(((c[0] - 18) / 2, (c[1] - 18) / 2, (c[0] + 18) / 2, (c[1] + 18) / 2), fill=col)
    elif ty == "spikes":
        S = b["S"]
        for i in range(12):
            a_ = ang + 2 * math.pi * i / 12
            ca, sa = math.cos(a_), math.sin(a_)
            base1 = (p[0] + math.cos(a_ - 0.16) * (r - 4), p[1] + math.sin(a_ - 0.16) * (r - 4))
            base2 = (p[0] + math.cos(a_ + 0.16) * (r - 4), p[1] + math.sin(a_ + 0.16) * (r - 4))
            tip = (p[0] + ca * (r + S), p[1] + sa * (r + S))
            d.polygon([base1, tip, base2], fill=steel, outline=col)
            glow_line(((base1[0] + base2[0]) / 2, (base1[1] + base2[1]) / 2), tip, 3)
    elif ty == "bow":
        box = (p[0] - r - 20, p[1] - r - 20, p[0] + r + 20, p[1] + r + 20)
        a0 = math.degrees(ang) - 55
        d.arc(box, a0, a0 + 110, fill=(150, 108, 66), width=10)
        d.line([P(r + 20 - 0, 0)], fill=col)
        e1 = (p[0] + math.cos(math.radians(a0)) * (r + 20), p[1] + math.sin(math.radians(a0)) * (r + 20))
        e2 = (p[0] + math.cos(math.radians(a0 + 110)) * (r + 20), p[1] + math.sin(math.radians(a0 + 110)) * (r + 20))
        d.line([e1, e2], fill=(235, 235, 235), width=2)


def render_battle(out, seed, hook, palette, fighters_arg):
    emo, weps = parse_fighters(fighters_arg, seed)
    tries = 0
    while True:
        frames, snd, pops, end_t, winner, events = sim_battle(seed, weps)
        total = frames[-1]["t"]
        if end_t and 18 <= total <= 45:
            hp_left = frames[-1]["balls"][winner]["hp"]
            if hp_left <= 50:                        # close fight -> more suspense
                break
        seed += 1
        tries += 1
        if tries > 250:
            raise SystemExit("no seed in range")
    names = [("RED", (239, 68, 68)), ("BLUE", (59, 130, 246))]
    sprites = []
    for k in range(2):
        if emo:
            sprites.append(ball_sprite(74, emoji=emo[k], ring=names[k][1]))
        else:
            sprites.append(flat_ball(74, names[k][1]))
    flash_spr = [flat_ball(74, (255, 255, 255)) for _ in range(2)]
    wname = (emo[winner] if emo else names[winner][0])
    print("seed", seed, "duration", round(total, 1), "weapons", weps, "winner", wname, f"({weps[winner]})")
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
    cand = []
    if pops:
        cand.append((pops[0][0], "FIRST BLOOD", "🩸", 1.4, False))
    for (tt_, txt, em, k) in events:
        cand.append((tt_, txt, em, 1.4, txt == "SUDDEN DEATH"))
    cooked = [False, False]
    for f_ in frames:
        for k in range(2):
            hp = f_["balls"][k]["hp"]
            if not cooked[k] and 0 < hp <= 35:
                cooked[k] = True
                who = "BRO" if emo else names[k][0]
                cand.append((f_["t"], f"{who} {prng.choice(COOKED)}", emo[k] if emo else "💀", 1.6, True))
    lead = 0
    for f_ in frames:
        diff = f_["balls"][0]["hp"] - f_["balls"][1]["hp"]
        sgn = 1 if diff > 12 else (-1 if diff < -12 else 0)
        if sgn and lead and sgn != lead:
            cand.append((f_["t"], "COMEBACK?!", "😳", 1.4, False))
        if sgn:
            lead = sgn
    for c in sorted(cand, key=lambda c: c[0]):
        add_pop(*c)
    audio = mix(snd, total)
    HOLD = 0.55
    if end_t:
        audio = fxlib.insert_silence(audio, end_t, HOLD, SR)
    import soundfile as sf
    sf.write(out + ".wav", audio, SR)
    h0 = PALETTES.get(palette, 0.55)
    bg = make_bg()
    ff = open_ff(out)
    hits = [(pt, tuple(pp), i * 7 + 1) for i, (pt, pp, dmg) in enumerate(pops)]
    hist = [[], []]
    ko_done = False
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
        tl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        tld = ImageDraw.Draw(tl)
        for k, b in enumerate(f["balls"]):
            hist[k].append(b["p"].copy())
            hist[k] = hist[k][-9:]
            if b["hp"] > 0:
                fxlib.draw_trail(tld, hist[k], 74, names[k][1])
        img = img.convert("RGBA")
        img.alpha_composite(tl)
        img = img.convert("RGB")
        d = ImageDraw.Draw(img)
        for (ap, av, ow) in f["arrows"]:
            u = av / (np.linalg.norm(av) + 1e-6)
            tail = (ap[0] - u[0] * 46, ap[1] - u[1] * 46)
            d.line([tail, tuple(ap)], fill=(235, 220, 190), width=5)
            d.polygon([tuple(ap + u * 12), tuple(ap + np.array([-u[1], u[0]]) * 7), tuple(ap - np.array([-u[1], u[0]]) * 7)],
                      fill=names[ow][1])
            gd.line([(tail[0] / 2, tail[1] / 2), (ap[0] / 2, ap[1] / 2)], fill=names[ow][1], width=3)
        for k, b in enumerate(f["balls"]):
            if b["hp"] <= 0 and end_t and t > end_t + 0.4:
                continue
            col = names[k][1]
            draw_weapon(d, gd, b, col)
            spr = flash_spr[k] if b["fl"] else sprites[k]
            paste_c(img, spr, b["p"][0], b["p"][1])

            gd.ellipse(((b["p"][0] - 80) / 2, (b["p"][1] - 80) / 2, (b["p"][0] + 80) / 2, (b["p"][1] + 80) / 2),
                       fill=tuple(int(c * 0.25) for c in col))
        glow = glow.filter(ImageFilter.GaussianBlur(10)).resize((W, H), Image.BILINEAR)
        img = ImageChops.add(img, glow)
        hl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        fxlib.draw_hit_fx(ImageDraw.Draw(hl), hits, t)
        img = img.convert("RGBA")
        img.alpha_composite(hl)
        img = img.convert("RGB")
        d = ImageDraw.Draw(img)
        for (pt, pp, dmg) in pops:
            age = t - pt
            if 0 <= age < 0.8:
                fz = font(64)
                s_ = f"{dmg}"
                d.text((pp[0] - d.textlength(s_, font=fz) / 2, pp[1] - 120 - 90 * age), s_, font=fz,
                       fill=(255, 230, 80), stroke_width=6, stroke_fill=(0, 0, 0))
        # HP bars + weapon stats
        for k in range(2):
            b = f["balls"][k]
            hp = b["hp"]
            x0 = 80 if k == 0 else W - 80 - 400
            y0 = 520
            d.rounded_rectangle((x0, y0, x0 + 400, y0 + 44), radius=22, fill=(40, 40, 52))
            if hp > 0:
                d.rounded_rectangle((x0, y0, x0 + 400 * hp / 100, y0 + 44), radius=22, fill=names[k][1])
            lab = f"{int(math.ceil(hp))}"
            d.text((x0 + 200 - d.textlength(lab, font=font(36)) / 2, y0 + 2), lab, font=font(36), fill=(255, 255, 255),
                   stroke_width=3, stroke_fill=(0, 0, 0))
            wl = weapon_label(b)
            we = emoji_img(WEAPONS[b["type"]]["emoji"], 38)
            wx = x0 if k == 0 else x0 + 400 - d.textlength(wl, font=font(30)) - 48
            paste_c(img, we, wx + 19, y0 + 80)
            d = ImageDraw.Draw(img)
            d.text((wx + 46, y0 + 64), wl, font=font(30), fill=(220, 220, 230))
            if emo:
                e = emoji_img(emo[k], 70)
                paste_c(img, e, x0 + (40 if k == 1 else 360), y0 - 55)
                d = ImageDraw.Draw(img)
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
        if end_t and not ko_done and t >= end_t:
            ko_done = True
            loser = f["balls"][1 - winner]["p"]
            for kf in fxlib.ko_frames(img, loser, int(HOLD * FPS)):
                ff.stdin.write(kf.tobytes())
    close_ff(ff, out)
    return seed, total + HOLD, f"{wname} ({weps[winner]})"


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
    default = {"battle": "WHO WINS?|EVERY HIT = STRONGER WEAPON", "elimination": "LAST ONE INSIDE|WINS"}
    hook = (sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else default[mode]).split("|")
    pal = sys.argv[5] if len(sys.argv) > 5 else "neon"
    extra = sys.argv[6] if len(sys.argv) > 6 else ""
    if mode == "battle":
        s, tot, w = render_battle(out, seed, hook, pal, extra)
    else:
        s, tot, w = render_elim(out, seed, hook, pal, extra or "flags")
    print(f"done {out} seed={s} {tot:.1f}s winner={w}")
