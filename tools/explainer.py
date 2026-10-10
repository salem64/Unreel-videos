#!/usr/bin/env python3
"""Unreel explainer renderer (cloud version, no PC needed): JSON spec -> 1080x1920 MP4.

Usage: python3 tools/explainer.py spec.json out.mp4 [--draft]

Spec (example: tools/explainer_blackholes3.json):
{
  "series": "BLACK HOLES - PART 3", "voice": "af_heart", "speed": 1.0,
  "theme": "space",            # space (stars, orange/cyan) | money (dark green, gold/mint) | tech (dark violet, pink/blue)
  "scenes": [ {"kind": "<kind>", "say": "spoken text", ...fields}, ... ]
}
Scene kinds and fields:
  hook      title, sub, anim ("blackhole" | "sun" | "star" | "emoji" + emoji)
  countdown title, options [[letter, text, emoji], ...], count (seconds, default 3)
  answer    letter, word, sub, emoji
  step      n, title, anim: space/physics "bars" | "forces" | "squeeze" | "balance" | "collapse" | "escape" | "redgiant" | "whitedwarf";
            generic (any topic) "emoji" (emojis [..], label) | "grow" (values [..], labels [..], prefix "$", suffix)
  compare   left {title, sub, emoji, verdict}, right {...}
  stat      value, unit, label, src
  quiz      title, options [[text, emoji], ...], next
Every scene shows auto captions of "say" (word timing estimated from text length).
Look: dark space, starfield, orange + cyan accents.
"""
import json, math, os, random, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quiz as Q  # noqa: E402  (shared helpers: fonts, sprites, tts, sfx)
from quiz import (font, fit, wrap, text_sprite, rrect, circle, paste, paste_c, emoji_sprite,  # noqa: E402
                  shadow_of, clamp, ease_out_back, ease_out_cubic, F_BLACK, F_XB, F_BOLD, SR, FPS)

W, H = Q.W, Q.H
CX = 535
ORANGE = (255, 149, 56)
CYAN = (62, 230, 255)
WHITE = (255, 255, 255)
RED = (239, 68, 68)
GREEN = (34, 197, 94)
INK = (14, 14, 22)


# ------------------------------------------------------------------ audio
def ambient_bed(total, seed=0):
    """Dark ambient pad (Am - F - C - G, 4 s each) with a soft pulse; synthesised, royalty-free."""
    n = int(SR * total) + SR
    t = np.arange(n) / SR
    out = np.zeros(n, dtype=np.float32)
    prog = [[57, 60, 64], [53, 57, 60], [48, 55, 60], [55, 59, 62]]
    mf = lambda m: 440 * 2 ** ((m - 69) / 12)
    seg = 4.0
    for i in range(int(total / seg) + 2):
        a, b = int(i * seg * SR), int(min(n, (i + 1.3) * seg * SR))
        if a >= n:
            break
        tt = t[a:b] - i * seg
        env = np.minimum(1, tt / 1.2) * np.minimum(1, np.maximum(0, (seg * 1.3 - tt)) / 1.4)
        for m in prog[i % 4] + [prog[i % 4][0] - 12]:
            f = mf(m)
            s = np.sin(2 * np.pi * f * tt) + 0.35 * np.sin(2 * np.pi * f * 2.003 * tt) + 0.2 * np.sin(2 * np.pi * f * 0.998 * tt)
            out[a:b] += (s * env * 0.07).astype(np.float32)
    # soft heartbeat pulse every 0.75 s
    beat = 0.75
    tk = np.arange(int(SR * 0.35)) / SR
    kick = np.sin(2 * np.pi * np.cumsum(42 + 70 * np.exp(-tk / 0.03)) / SR) * np.exp(-tk / 0.12)
    for i in range(int(total / beat) + 1):
        p = int(i * beat * SR)
        k = kick[:max(0, n - p)]
        out[p:p + len(k)] += (k * 0.25).astype(np.float32)
    return out[:int(SR * total)]


def sfx_riser(d=0.6):
    tt = np.arange(int(SR * d)) / SR
    f = 200 + 1400 * (tt / d) ** 2
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * (tt / d) ** 1.5 * 0.25
    noise = np.random.default_rng(2).standard_normal(len(tt)) * (tt / d) ** 2 * 0.08
    return (s + noise).astype(np.float32)


# ------------------------------------------------------------------ visuals: static
THEMES = {
    # name: (bg top, bg bottom, blob1, blob2, accent1, accent2, stars)
    "space": ((10, 12, 30), (2, 2, 8), (90, 40, 160), (20, 90, 140), (255, 149, 56), (62, 230, 255), True),
    "money": ((6, 30, 22), (2, 8, 6), (16, 120, 70), (180, 140, 20), (255, 200, 40), (52, 211, 153), False),
    "tech":  ((14, 10, 34), (3, 2, 10), (120, 40, 200), (20, 120, 200), (244, 114, 182), (96, 165, 250), False),
}


def make_background(theme="space"):
    th = THEMES[theme]
    yy = np.linspace(0, 1, H)[:, None, None]
    top = np.array(th[0])
    bot = np.array(th[1])
    base = top * (1 - yy) + bot * yy
    base = np.broadcast_to(base, (H, W, 3)).copy()
    grain = np.random.default_rng(3).normal(0, 2.5, (H, W, 1))
    base = np.clip(base + grain, 0, 255).astype(np.uint8)
    img = Image.fromarray(base, "RGB").convert("RGBA")

    def blob(col, r, a):
        yy_, xx_ = np.mgrid[-r:r, -r:r]
        d = np.sqrt(xx_ ** 2 + yy_ ** 2) / r
        al = (np.clip(1 - d, 0, 1) ** 2.2 * a * 255).astype(np.uint8)
        im = Image.new("RGBA", (2 * r, 2 * r), col + (0,))
        im.putalpha(Image.fromarray(al, "L"))
        return im
    img.alpha_composite(blob(th[2], 600, 0.35), (-300, 200))
    img.alpha_composite(blob(th[3], 520, 0.30), (500, 1100))
    return img


def make_stars(seed, n, big):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    rng = random.Random(seed)
    for _ in range(n):
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        r = rng.uniform(0.8, 2.6 if big else 1.4)
        a = rng.randint(90, 255)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, a))
    return im


def make_blackhole(R):
    """Black hole sprite: glow + orange photon ring + black shadow. Size 4R x 4R, centre in the middle."""
    S = 4 * R
    yy, xx = np.mgrid[0:S, 0:S] - S / 2
    d = np.sqrt(xx ** 2 + yy ** 2) / R
    rgb = np.zeros((S, S, 3))
    a = np.zeros((S, S))
    ring = np.exp(-((d - 1.08) / 0.07) ** 2)
    glow = np.exp(-np.maximum(d - 1.0, 0) / 0.35) * (d > 1.0)
    col_r, col_g, col_b = 255, 150, 60
    inten = np.clip(ring * 1.0 + glow * 0.55, 0, 1)
    rgb[..., 0] = col_r
    rgb[..., 1] = col_g + 90 * ring
    rgb[..., 2] = col_b + 120 * ring
    a = inten
    inside = d < 1.0
    rgb[inside] = 0
    a[inside] = 1.0
    arr = np.dstack([np.clip(rgb, 0, 255), np.clip(a, 0, 1) * 255]).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def make_disk(R):
    """Flat accretion disk (ellipse) sprite, front part drawn separately over the hole."""
    S = 6 * R
    yy, xx = np.mgrid[0:S // 2, 0:S] - np.array([S / 4, S / 2])[:, None, None]
    yy = yy * 3.2  # squash
    d = np.sqrt(xx ** 2 + yy ** 2) / R
    band = np.clip(1 - np.abs(d - 2.0) / 0.9, 0, 1) ** 1.6
    arr = np.zeros((S // 2, S, 4))
    arr[..., 0] = 255
    arr[..., 1] = 120 + 110 * band
    arr[..., 2] = 40 + 120 * band ** 3
    arr[..., 3] = band * 230
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


# ------------------------------------------------------------------ renderer
class R:
    def __init__(self, spec, draft):
        self.spec = spec
        self.draft = draft
        theme = spec.get("theme", "space")
        th = THEMES[theme]
        global ORANGE, CYAN
        ORANGE, CYAN = th[4], th[5]
        self.bg = make_background(theme)
        self.stars1 = make_stars(1, 260 if th[6] else 40, False)
        self.stars2 = make_stars(2, 70 if th[6] else 0, True)
        self.bh_R = 150
        self.bh = make_blackhole(self.bh_R)
        self.disk = make_disk(self.bh_R)
        self.wm = text_sprite(["unreel"], font(F_BLACK, 36), 36, (255, 255, 255, 170))
        ser = spec.get("series", "").upper()
        self.series = text_sprite([ser], font(F_BLACK, 34), 34, CYAN + (255,)) if ser else None
        self.cache = {}

    # -------- generic pieces
    def T(self, key, text, path, maxw, maxh, start, col, minsize=34, stroke=0):
        k = (key, text, start, col, maxw)
        if k not in self.cache:
            lines, f, s = fit(text, path, maxw, maxh, start, minsize)
            self.cache[k] = text_sprite(lines, f, s, col + (255,), stroke=stroke, stroke_fill=(0, 0, 0))
        return self.cache[k]

    def pop_in(self, img, spr, cx, cy, lt, delay=0.0, dur=0.45):
        p = clamp((lt - delay) / dur)
        if p <= 0:
            return
        paste_c(img, spr, cx, cy, scale=0.4 + 0.6 * ease_out_back(p), opacity=min(1, p * 2))

    def slide_in(self, img, spr, cx, cy, lt, delay=0.0, dur=0.4, dy=60):
        p = clamp((lt - delay) / dur)
        if p <= 0:
            return
        paste_c(img, spr, cx, cy + dy * (1 - ease_out_cubic(p)), opacity=p)

    def draw_bh(self, img, cx, cy, scale, t, opacity=1.0):
        bh, disk = self.bh, self.disk
        if abs(scale - 1) > 0.01:
            bh = bh.resize((int(bh.width * scale), int(bh.height * scale)), Image.BICUBIC)
            disk = disk.resize((int(disk.width * scale), int(disk.height * scale)), Image.BICUBIC)
        # back half of disk, hole, front half of disk (lower half)
        back = disk.crop((0, 0, disk.width, disk.height // 2))
        front = disk.crop((0, disk.height // 2, disk.width, disk.height))
        paste(img, back, cx - disk.width / 2, cy - disk.height / 2, opacity)
        paste_c(img, bh, cx, cy, 1.0, opacity)
        paste(img, front, cx - disk.width / 2, cy, opacity)
        # orbiting hot specks
        d = ImageDraw.Draw(img)
        Rr = self.bh_R * scale
        for i in range(40):
            ang = t * (1.6 + (i % 5) * 0.25) + i * 0.83
            rad = Rr * (1.5 + (i % 7) * 0.12)
            x = cx + math.cos(ang) * rad
            y = cy + math.sin(ang) * rad / 3.2
            if math.sin(ang) < 0 and abs(x - cx) < Rr * 1.05:
                continue  # hidden behind hole
            r = 2 + (i % 3)
            d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 230, 170, int(200 * opacity)))

    def sun_sprite(self, col):
        k = ("sun", col)
        if k not in self.cache:
            R0 = 200
            S = 4 * R0
            yy, xx = np.mgrid[0:S, 0:S] - S / 2
            d = np.sqrt(xx ** 2 + yy ** 2) / R0
            core = np.clip(1 - d, 0, 1) ** 0.35
            glow = np.exp(-np.maximum(d - 1, 0) / 0.25) * 0.6
            a = np.where(d <= 1, 1.0, glow)
            rng = np.random.default_rng(4)
            noise = rng.normal(0, 1, (S // 16, S // 16))
            noise = np.kron(noise, np.ones((16, 16)))[:S, :S]
            light = np.clip(0.75 + 0.25 * core + 0.04 * noise * (d <= 1), 0, 1.15)
            rgb = np.dstack([np.clip(col[c] * light + 60 * core * (d <= 1), 0, 255) for c in range(3)])
            arr = np.dstack([rgb, np.clip(a, 0, 1) * 255]).astype(np.uint8)
            self.cache[k] = Image.fromarray(arr, "RGBA")
        return self.cache[k]

    def draw_sun(self, img, cx, cy, r, t, col=(255, 196, 64), opacity=1.0):
        if r < 1:
            return
        spr = self.sun_sprite(col)
        sc = r * (1 + 0.015 * math.sin(t * 4)) / 200
        paste_c(img, spr, cx, cy, scale=sc, opacity=opacity)

    def captions(self, img, sc, lt):
        words = sc["_words"]
        if not words:
            return
        idx = max([i for i, w in enumerate(words) if w[1] <= lt] or [0])
        # chunks of up to 4 words, broken at sentence ends
        if "_chunks" not in sc:
            ch, cur = [], []
            for i, w in enumerate(words):
                cur.append(i)
                if len(cur) == 4 or w[0][-1] in ".?!,:":
                    ch.append(cur)
                    cur = []
            if cur:
                ch.append(cur)
            sc["_chunks"] = ch
        ids = next(c for c in sc["_chunks"] if idx in c)
        ws = [words[i] for i in ids]
        chunk_first = ids[0]
        f = font(F_BLACK, 62)
        d0 = ImageDraw.Draw(Image.new("L", (4, 4)))
        parts = [w[0] for w in ws]
        total = sum(d0.textlength(p + " ", font=f) for p in parts)
        im = Image.new("RGBA", (int(total) + 40, 100), (0, 0, 0, 0))
        dd = ImageDraw.Draw(im)
        x = 20
        for i, p in enumerate(parts):
            cur = (chunk_first + i) == idx
            dd.text((x, 10), p, font=f, fill=(ORANGE if cur else WHITE) + (255,), stroke_width=6, stroke_fill=(0, 0, 0))
            x += d0.textlength(p + " ", font=f)
        if im.width > 940:
            im = im.resize((940, int(im.height * 940 / im.width)), Image.LANCZOS)
        paste_c(img, im, CX, 1500)

    # -------- frame
    def frame(self, t, sc, lt):
        img = self.bg.copy()
        off = int(t * 14) % H
        s1 = Image.new("RGBA", (W, H))
        s1.paste(self.stars1.crop((0, 0, W, H - off)), (0, off))
        s1.paste(self.stars1.crop((0, H - off, W, H)), (0, 0))
        img.alpha_composite(s1)
        off2 = int(t * 32) % H
        s2 = Image.new("RGBA", (W, H))
        s2.paste(self.stars2.crop((0, 0, W, H - off2)), (0, off2))
        s2.paste(self.stars2.crop((0, H - off2, W, H)), (0, 0))
        img.alpha_composite(s2)
        getattr(self, "s_" + sc["kind"])(img, sc, lt, t)
        if self.series:
            paste_c(img, self.series, CX, 150)
        paste_c(img, self.wm, CX, 1820)
        self.captions(img, sc, lt)
        # scene transition flash
        if lt < 0.12 and sc["_i"] > 0:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(90 * (1 - lt / 0.12))))
            img.alpha_composite(fl)
        return img

    # -------- scenes
    def s_hook(self, img, sc, lt, t):
        sc_ = 0.6 + 0.5 * ease_out_cubic(clamp(lt / 1.2))
        if sc.get("anim") == "sun":
            self.draw_sun(img, CX - 120, 880, 150 * sc_, t)
            self.draw_bh(img, CX + 200, 930, 0.55 * sc_, t)
            self.pop_in(img, self.T("hq", "?", F_BLACK, 200, 200, 170, ORANGE, stroke=6), CX + 30, 700, lt, 0.6)
            self.pop_in(img, self.T("ht", sc["title"], F_BLACK, 900, 260, 96, WHITE, stroke=4), CX, 380, lt, 0.05)
            self.slide_in(img, self.T("hs", sc["sub"], F_BLACK, 900, 120, 70, ORANGE, stroke=4), CX, 1250, lt, 0.5)
            return
        if sc.get("anim") == "emoji":
            e = emoji_sprite(sc.get("emoji", "💸"), 300)
            self.pop_in(img, e, CX, 880 + 15 * math.sin(t * 3), lt, 0.1, 0.5)
            self.pop_in(img, self.T("ht", sc["title"], F_BLACK, 900, 260, 96, WHITE, stroke=4), CX, 380, lt, 0.05)
            self.slide_in(img, self.T("hs", sc["sub"], F_BLACK, 900, 120, 70, ORANGE, stroke=4), CX, 1250, lt, 0.5)
            return
        if sc.get("anim") == "star":
            self.draw_sun(img, CX, 900, 220 * sc_, t, (120, 180, 255))
            self.pop_in(img, self.T("ht", sc["title"], F_BLACK, 900, 260, 96, WHITE, stroke=4), CX, 380, lt, 0.05)
            self.slide_in(img, self.T("hs", sc["sub"], F_BLACK, 900, 120, 70, ORANGE, stroke=4), CX, 1250, lt, 0.5)
            return
        self.draw_bh(img, CX, 900, sc_ * (1 + 0.02 * math.sin(t * 3)), t)
        # little astronaut falling in
        a = emoji_sprite("🧑‍🚀", 110)
        p = clamp(lt / max(1, sc["_dur"]))
        ax, ay = CX + 330 * (1 - p), 560 + 330 * p
        a2 = a.rotate(lt * 90, resample=Image.BICUBIC, expand=True)
        paste_c(img, a2, ax, ay, scale=1 - 0.6 * p)
        self.pop_in(img, self.T("ht", sc["title"], F_BLACK, 900, 260, 96, WHITE, stroke=4), CX, 380, lt, 0.05)
        self.slide_in(img, self.T("hs", sc["sub"], F_BLACK, 900, 120, 70, ORANGE, stroke=4), CX, 1250, lt, 0.5)

    def s_countdown(self, img, sc, lt, t):
        self.pop_in(img, self.T("ct", sc["title"], F_BLACK, 880, 140, 84, WHITE, stroke=4), CX, 330, lt, 0.0)
        for i, (L, txt, em) in enumerate(sc["options"]):
            y = 560 + i * 190
            card = self.cache.get(("card", i))
            if card is None:
                card = rrect(860, 160, 36, (255, 255, 255, 30), outline=(255, 255, 255, 90), width=3)
                dd = ImageDraw.Draw(card)
                dd.ellipse((24, 24, 136, 136), fill=CYAN + (255,))
                f = font(F_BLACK, 68)
                dd.text((80 - dd.textlength(L, font=f) / 2, 38), L, font=f, fill=INK)
                dd.text((170, 40), txt, font=font(F_BLACK, 66), fill=WHITE)
                e = emoji_sprite(em, 100)
                card.alpha_composite(e, (860 - 40 - e.width, (160 - e.height) // 2))
                self.cache[("card", i)] = card
            self.slide_in(img, card, CX, y, lt, 0.25 + 0.15 * i, dy=0)
        # countdown ring
        c0 = sc["_cstart"]
        if lt >= c0:
            k = lt - c0
            n = sc.get("count", 3)
            num = max(1, n - int(k))
            frac = k - int(k)
            ring = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
            dd = ImageDraw.Draw(ring)
            dd.ellipse((10, 10, 290, 290), outline=(255, 255, 255, 60), width=18)
            dd.arc((10, 10, 290, 290), -90, -90 + 360 * (1 - frac), fill=ORANGE + (255,), width=18)
            f = font(F_BLACK, 150)
            s = str(num)
            dd.text((150 - dd.textlength(s, font=f) / 2, 55), s, font=f, fill=WHITE)
            paste_c(img, ring, CX, 1210, scale=1 + 0.15 * max(0, 1 - frac * 4))

    def s_answer(self, img, sc, lt, t):
        e = emoji_sprite(sc["emoji"], 260)
        self.pop_in(img, e, CX, 640 + 12 * math.sin(t * 4), lt, 0.0, 0.5)
        badge = self.cache.get("badge")
        if badge is None:
            badge = rrect(520, 150, 75, GREEN + (255,))
            dd = ImageDraw.Draw(badge)
            s = "IT'S " + sc["letter"] + " ✓"
            s = "IT'S " + sc["letter"]
            f = font(F_BLACK, 84)
            dd.text((260 - dd.textlength(s, font=f) / 2, 26), s, font=f, fill=WHITE)
            self.cache["badge"] = badge
        self.pop_in(img, badge, CX, 330, lt, 0.1)
        # stretched word
        p = clamp((lt - sc["_at"].get("call", 1.2)) / 0.8)
        if p > 0:
            wspr = self.T("aw", sc["word"], F_BLACK, 1500, 200, 110, ORANGE, stroke=5)
            sx = 0.3 + 0.6 * ease_out_back(p)
            ww = wspr.resize((max(1, int(wspr.width * sx)), max(1, int(wspr.height * (1.25 - 0.35 * ease_out_cubic(p))))), Image.BICUBIC)
            if ww.width > 980:
                ww = ww.resize((980, ww.height), Image.BICUBIC)
            paste_c(img, ww, CX, 1000, opacity=p)
            self.slide_in(img, self.T("as", sc["sub"], F_BOLD, 860, 120, 52, WHITE), CX, 1160, lt, sc["_at"].get("call", 1.2) + 0.3)

    def step_header(self, img, sc, lt):
        chip = self.cache.get(("chip", sc["n"]))
        if chip is None:
            chip = rrect(230, 76, 38, CYAN + (255,))
            dd = ImageDraw.Draw(chip)
            s = "STEP " + str(sc["n"])
            f = font(F_BLACK, 44)
            dd.text((115 - dd.textlength(s, font=f) / 2, 12), s, font=f, fill=INK)
            self.cache[("chip", sc["n"])] = chip
        self.pop_in(img, chip, CX, 280, lt)
        self.slide_in(img, self.T(("st", sc["n"]), sc["title"], F_BLACK, 900, 220, 80, WHITE, stroke=4), CX, 430, lt, 0.15)

    def s_step(self, img, sc, lt, t):
        self.step_header(img, sc, lt)
        getattr(self, "a_" + sc["anim"])(img, sc, lt, t)

    def a_emoji(self, img, sc, lt, t):
        # one or more emojis pop in one after another (e.g. "📱➡️💵"), with optional big label
        ems = sc.get("emojis", ["💡"])
        n = len(ems)
        gap = 900 / max(n, 1)
        size = min(260, int(gap * 0.8))
        for i, em in enumerate(ems):
            x = CX - 450 + gap * (i + 0.5)
            self.pop_in(img, emoji_sprite(em, size), x, 960 + 12 * math.sin(t * 3 + i), lt, 0.3 + 0.35 * i, 0.45)
        if sc.get("label"):
            self.slide_in(img, self.T(("el", sc["n"]), sc["label"], F_BLACK, 880, 140, 64, ORANGE, stroke=4), CX, 1230, lt, 0.3 + 0.35 * n)

    def a_grow(self, img, sc, lt, t):
        # money/number growth: bars rising left to right with values ("values": [10, 20, 40], "prefix": "$")
        vals = sc.get("values", [1, 2, 4, 8])
        labels = sc.get("labels", [""] * len(vals))
        n = len(vals)
        mx = max(vals)
        d = ImageDraw.Draw(img)
        bw = 760 / n
        for i, v in enumerate(vals):
            p = clamp((lt - 0.3 - 0.3 * i) / 0.5)
            if p <= 0:
                continue
            x = CX - 380 + bw * (i + 0.5)
            h = 520 * (v / mx) * ease_out_back(p)
            col = tuple(int(CYAN[c] + (ORANGE[c] - CYAN[c]) * i / max(1, n - 1)) for c in range(3))
            d.rounded_rectangle((x - bw * 0.35, 1220 - h, x + bw * 0.35, 1220), radius=16, fill=col + (255,))
            txt = sc.get("prefix", "") + f"{v:,}" + sc.get("suffix", "")
            paste_c(img, self.T(("gv", sc["n"], i), txt, F_BLACK, int(bw), 60, 44, WHITE, stroke=3), x, 1190 - h, opacity=p)
            if labels[i]:
                paste_c(img, self.T(("gl", sc["n"], i), labels[i], F_BOLD, int(bw), 50, 34, (200, 210, 230)), x, 1260, opacity=p)

    def a_bars(self, img, sc, lt, t):
        # black hole on the left (small), bars of gravity rising towards it
        self.draw_bh(img, 180, 950, 0.55, t)
        n = 6
        d = ImageDraw.Draw(img)
        for i in range(n):
            p = clamp((lt - 0.3 - 0.18 * i) / 0.5)
            x = 900 - i * 105
            hgt = (60 + 330 * ((i + 1) / n) ** 2.2) * ease_out_back(p)
            col = tuple(int(CYAN[c] + (ORANGE[c] - CYAN[c]) * i / (n - 1)) for c in range(3))
            d.rounded_rectangle((x - 38, 1150 - hgt, x + 38, 1150), radius=14, fill=col + (255,))
        lab = self.T("bl", "← CLOSER = STRONGER PULL", F_BLACK, 860, 80, 50, ORANGE)
        self.slide_in(img, lab, CX + 60, 1230, lt, 1.4)

    def _arrow(self, d, x, y0, y1, w, col):
        if abs(y1 - y0) < w * 2:
            return
        sgn = 1 if y1 > y0 else -1
        ye = y1 - sgn * w * 1.4
        d.rectangle((x - w / 2, min(y0, ye), x + w / 2, max(y0, ye)), fill=col)
        tip = y1
        d.polygon([(x - w * 1.4, tip - sgn * w * 1.6), (x + w * 1.4, tip - sgn * w * 1.6), (x, tip)], fill=col)

    def a_forces(self, img, sc, lt, t):
        # astronaut feet first (upside down), hole below; long arrow at feet, short at head
        self.draw_bh(img, CX, 1330, 0.75, t)
        a = emoji_sprite("🧑‍🚀", 240).rotate(180, expand=True)
        y = 840 + 10 * math.sin(t * 3)
        paste_c(img, a, CX - 40, y)
        d = ImageDraw.Draw(img)
        ph = clamp((lt - 0.6) / 0.6)
        pf = clamp((lt - sc["_at"].get("feet", 1.2)) / 0.6)
        if ph > 0:
            self._arrow(d, CX + 170, 700, 700 + 90 * ease_out_back(ph), 18, CYAN + (255,))
            paste_c(img, self.T("fh", "HEAD", F_BLACK, 300, 60, 44, CYAN), CX + 300, 720, opacity=ph)
        if pf > 0:
            self._arrow(d, CX + 170, 930, 930 + 260 * ease_out_back(pf), 26, ORANGE + (255,))
            paste_c(img, self.T("ff", "FEET", F_BLACK, 300, 60, 44, ORANGE), CX + 300, 960, opacity=pf)

    def a_squeeze(self, img, sc, lt, t):
        p = ease_out_cubic(clamp((lt - 0.4) / max(1.0, sc["_dur"] - 1.2)))
        self.draw_bh(img, CX, 1280, 0.7, t)
        a = emoji_sprite("🧑‍🚀", 230)
        sx, sy = 1 - 0.6 * p, 1 + 1.5 * p
        aa = a.resize((max(4, int(a.width * sx)), int(a.height * sy)), Image.BICUBIC)
        paste_c(img, aa, CX, 860 + 60 * p)
        d = ImageDraw.Draw(img)
        # squeeze arrows from the sides, stretch arrows up/down
        if p > 0.05:
            o = int(255 * min(1, p * 3))
            for sgn in (-1, 1):
                x0 = CX + sgn * 330
                x1 = CX + sgn * (90 + 60 * (1 - p))
                d.line((x0, 860, x1, 860), fill=CYAN + (o,), width=16)
                d.polygon([(x1, 860), (x1 + sgn * 34, 836), (x1 + sgn * 34, 884)], fill=CYAN + (o,))
        if p > 0.6:
            e = emoji_sprite("🍝", 150)
            self.pop_in(img, e, CX + 280, 640, lt, sc["_dur"] * 0.6)

    def _radial_arrows(self, d, cx, cy, r0, r1, n, col, w, rot=0.0):
        for i in range(n):
            a = rot + i * 2 * math.pi / n
            x0, y0 = cx + math.cos(a) * r0, cy + math.sin(a) * r0
            x1, y1 = cx + math.cos(a) * r1, cy + math.sin(a) * r1
            d.line((x0, y0, x1, y1), fill=col, width=w)
            ux, uy = (x1 - x0), (y1 - y0)
            L = math.hypot(ux, uy) or 1
            ux, uy = ux / L, uy / L
            hx, hy = -uy, ux
            d.polygon([(x1 + ux * w * 1.6, y1 + uy * w * 1.6), (x1 + hx * w * 1.4, y1 + hy * w * 1.4),
                       (x1 - hx * w * 1.4, y1 - hy * w * 1.4)], fill=col)

    def a_balance(self, img, sc, lt, t):
        cy = 980
        self.draw_sun(img, CX, cy, 190, t, (120, 180, 255))
        d = ImageDraw.Draw(img)
        p1 = clamp((lt - 0.5) / 0.5)
        p2 = clamp((lt - sc["_at"].get("out", 1.6)) / 0.5)
        wob = 12 * math.sin(t * 7)
        if p1 > 0:
            self._radial_arrows(d, CX, cy, 400 + wob, 400 - 140 * ease_out_back(p1) + wob, 8, CYAN + (255,), 16, 0.39)
            paste_c(img, self.T("bg", "GRAVITY", F_BLACK, 400, 70, 50, CYAN, stroke=3), CX - 250, 660, opacity=p1)
        if p2 > 0:
            self._radial_arrows(d, CX, cy, 210 - wob, 210 + 120 * ease_out_back(p2) - wob, 8, ORANGE + (255,), 16, 0.0)
            paste_c(img, self.T("bf", "FUEL", F_BLACK, 400, 70, 50, ORANGE, stroke=3), CX + 260, 660, opacity=p2)

    def a_collapse(self, img, sc, lt, t):
        cy = 980
        tc = sc["_at"].get("collapse", 2.0)
        if lt < tc:
            q = clamp(lt / tc)
            r = 230 - 40 * q
            shake = 6 * q * math.sin(t * 40)
            self.draw_sun(img, CX + shake, cy, r, t, (int(120 + 135 * q), int(180 - 40 * q), int(255 - 175 * q)))
            d = ImageDraw.Draw(img)
            self._radial_arrows(d, CX, cy, r + 200, r + 40, 8, CYAN + (255,), 16, 0.39)
            if lt > 0.4:
                paste_c(img, self.T("cf", "FUEL: EMPTY", F_BLACK, 600, 70, 56, RED, stroke=3), CX, 1330, opacity=clamp((lt - 0.4) / 0.3))
        else:
            k = lt - tc
            q = ease_out_cubic(clamp(k / 0.35))
            if q < 1:
                self.draw_sun(img, CX, cy, 190 * (1 - q) + 2, t, (255, 140, 80))
            # flash ring
            if k < 0.8:
                d = ImageDraw.Draw(img)
                rr = 60 + 900 * k
                d.ellipse((CX - rr, cy - rr, CX + rr, cy + rr), outline=(255, 255, 255, int(220 * (1 - k / 0.8))), width=14)
            self.draw_bh(img, CX, cy, 0.75 * ease_out_back(clamp((k - 0.15) / 0.5)) + 0.01, t, clamp((k - 0.15) / 0.3))

    def a_escape(self, img, sc, lt, t):
        cy = 1000
        self.draw_bh(img, CX, cy, 0.9, t)
        d = ImageDraw.Draw(img)
        for i in range(10):
            ang = -math.pi / 2 + (i - 4.5) * 0.28
            ph = (lt * 0.7 + i * 0.13) % 1.0
            dist = 160 + 330 * math.sin(math.pi * ph)
            x = CX + math.cos(ang) * dist
            y = cy + math.sin(ang) * dist / 1.1
            for k in range(6):
                pk = max(0.0, ph - k * 0.025)
                dk = 160 + 330 * math.sin(math.pi * pk)
                xk, yk = CX + math.cos(ang) * dk, cy + math.sin(ang) * dk / 1.1
                r = 9 - k
                d.ellipse((xk - r, yk - r, xk + r, yk + r), fill=(255, 245, 160, 255 - k * 38))
        paste_c(img, self.T("el", "LIGHT CAN'T GET OUT", F_BLACK, 800, 70, 52, ORANGE, stroke=3), CX, 1300, opacity=clamp((lt - 0.8) / 0.4))

    def a_redgiant(self, img, sc, lt, t):
        cy = 1000
        q = ease_out_cubic(clamp((lt - 0.6) / max(1.0, sc["_dur"] - 1.6)))
        r = 90 + 330 * q
        col = (255, int(196 - 110 * q), int(64 - 20 * q))
        ex = CX + 360
        e = emoji_sprite("🌍", 60)
        self.draw_sun(img, CX - 120, cy, r, t, col)
        swallowed = (CX - 120 + r) > ex + 10
        if not swallowed:
            paste_c(img, e, ex, cy)
            paste_c(img, self.T("re", "EARTH", F_BLACK, 300, 60, 36, WHITE, stroke=3), ex, cy + 70)
        else:
            paste_c(img, e, ex, cy, opacity=0.25)
        paste_c(img, self.T("rl", "RED GIANT", F_BLACK, 600, 80, 64, WHITE, stroke=5), CX, 1450 - 200, opacity=clamp((q - 0.4) * 3))

    def a_whitedwarf(self, img, sc, lt, t):
        cy = 1000
        q = ease_out_cubic(clamp((lt - 0.3) / 1.6))
        if q < 1:
            self.draw_sun(img, CX, cy, 380 * (1 - q) + 30, t, (255, int(86 + 150 * q), int(44 + 210 * q)), opacity=1 - 0.3 * q)
        d = ImageDraw.Draw(img)
        if q > 0.3:
            rr = 120 + 360 * q
            d.ellipse((CX - rr, cy - rr * 0.9, CX + rr, cy + rr * 0.9), outline=(255, 120, 180, int(110 * (1 - q * 0.5))), width=30)
        if q >= 0.99:
            self.draw_sun(img, CX, cy, 30, t, (225, 235, 255))
        paste_c(img, self.T("wl", "WHITE DWARF", F_BLACK, 600, 80, 64, (200, 220, 255), stroke=4), CX, 1250, opacity=clamp((q - 0.7) * 3))

    def s_compare(self, img, sc, lt, t):
        L, Rt = sc["left"], sc["right"]
        for side, c, cx, delay, key in ((L, RED, 290, 0.0, "l"), (Rt, GREEN, 790, sc["_at"].get("giant", 2.0), "r")):
            p = clamp((lt - delay) / 0.45)
            if p <= 0:
                continue
            card = self.cache.get(("cmp", key))
            if card is None:
                card = rrect(470, 920, 40, (255, 255, 255, 26), outline=c + (200,), width=5)
                dd = ImageDraw.Draw(card)
                f = font(F_BLACK, 62)
                dd.text((235 - dd.textlength(side["title"], font=f) / 2, 40), side["title"], font=f, fill=WHITE)
                lines, f2, s2 = fit(side["sub"], F_BOLD, 420, 120, 40, 28)
                y = 120
                for ln in lines:
                    dd.text((235 - dd.textlength(ln, font=f2) / 2, y), ln, font=f2, fill=(200, 210, 230))
                    y += s2 * 1.15
                lines, f3, s3 = fit(side["verdict"], F_BLACK, 420, 200, 50, 30)
                y = 700
                for ln in lines:
                    dd.text((235 - dd.textlength(ln, font=f3) / 2, y), ln, font=f3, fill=c)
                    y += s3 * 1.15
                self.cache[("cmp", key)] = card
            paste_c(img, card, cx, 960, scale=0.85 + 0.15 * ease_out_back(p), opacity=p)
            ls = lt - delay
            vis = side.get("visual", "stretch" if key == "l" else "calm")
            if vis == "sun":
                self.draw_sun(img, cx, 860, 55, t, opacity=p)
                paste_c(img, self.T(("cx", key), side.get("big", ""), F_BLACK, 400, 120, 90, WHITE, stroke=4), cx, 1090, opacity=p)
                continue
            if vis == "bigstar":
                q = clamp(ls / 1.6)
                self.draw_sun(img, cx, 860, 140 * (0.8 + 0.2 * q), t, (120, 180, 255), opacity=p)
                paste_c(img, self.T(("cx", key), side.get("big", ""), F_BLACK, 400, 120, 90, WHITE, stroke=4), cx, 1090, opacity=p)
                continue
            if vis == "stretch":
                self.draw_bh(img, cx, 900, 0.42, t, p)
                e = emoji_sprite("🧑‍🚀", 90)
                q = clamp(ls / 1.5)
                e2 = e.resize((max(4, int(90 * (1 - 0.7 * q))), int(e.height * (1 + 1.5 * q))), Image.BICUBIC)
                paste_c(img, e2, cx, 760, opacity=p)
            else:
                self.draw_bh(img, cx, 900, 0.62, t, p)
                e = emoji_sprite("😌", 90)
                q = clamp(ls / 2.0)
                paste_c(img, e, cx, 660 + 150 * q, opacity=p)
        self.pop_in(img, self.T("vs", "VS", F_BLACK, 200, 120, 90, ORANGE, stroke=5), 540, 960, lt, 0.3)

    def s_stat(self, img, sc, lt, t):
        bg = sc.get("bg", "bh")
        if bg == "bh":
            self.draw_bh(img, CX, 1080, 1.0, t, 0.55)
        elif bg == "earth":
            e = emoji_sprite("🌍", 300)
            q = clamp((lt - 0.8) / 1.5)
            paste_c(img, e, CX, 1180, scale=1 - 0.88 * ease_out_cubic(q))
            if q > 0.9:
                self.draw_bh(img, CX, 1180, 0.12, t, (q - 0.9) * 10)
        elif bg == "whitedwarf":
            self.draw_sun(img, CX, 1100, 40, t, (225, 235, 255))
        p = clamp((lt - 0.2) / 1.6)
        v = float(sc["value"]) * ease_out_cubic(p)
        s = "~" + str(int(round(v))) + sc.get("unit", "")
        big = text_sprite([s], font(F_BLACK, 260), 260, ORANGE + (255,), stroke=8, stroke_fill=(0, 0, 0))
        paste_c(img, big, CX, 640, scale=1 + 0.05 * math.sin(t * 6) * (p >= 1))
        self.slide_in(img, self.T("sl", sc["label"], F_BLACK, 880, 220, 66, WHITE, stroke=4), CX, 900, lt, 0.6)
        self.slide_in(img, self.T("ss", sc["src"], F_BOLD, 860, 80, 38, (180, 190, 210)), CX, 1300, lt, 1.0)

    def s_quiz(self, img, sc, lt, t):
        self.pop_in(img, self.T("qt", sc["title"], F_BLACK, 900, 240, 90, WHITE, stroke=4), CX, 380, lt)
        nopt = len(sc["options"])
        cols = [RED, GREEN] if nopt == 2 else [(234, 88, 12), (37, 99, 235), (8, 145, 178)]
        cw = 420 if nopt == 2 else 280
        for i, (txt, em) in enumerate(sc["options"]):
            col = cols[i % len(cols)]
            card = self.cache.get(("qo", i))
            if card is None:
                card = rrect(cw, 300, 40, col + (255,))
                dd = ImageDraw.Draw(card)
                e = emoji_sprite(em, 120)
                card.alpha_composite(e, ((cw - e.width) // 2, 30))
                lines, f, fs = fit(txt, F_BLACK, cw - 30, 90, 70, 34)
                dd.text((cw / 2 - dd.textlength(lines[0], font=f) / 2, 175 + (70 - fs) / 2), lines[0], font=f, fill=WHITE)
                self.cache[("qo", i)] = card
            cx = (300 + i * 480) if nopt == 2 else (CX - 300 + i * 300)
            wob = 1 + 0.04 * math.sin(t * 5 + i * 2)
            self.pop_in(img, card.resize((int(card.width * wob), int(card.height * wob))), cx, 760, lt, 0.3 + 0.2 * i)
        self.slide_in(img, self.T("qc", "COMMENT BELOW", F_BLACK, 900, 100, 70, ORANGE), CX, 1010, lt, 0.9)
        nx = sc.get("next")
        if nx:
            p = clamp((lt - sc["_at"].get("part", 2.5)) / 0.4)
            if p > 0:
                tag = self.cache.get("next")
                if tag is None:
                    lines, f, s = fit(nx, F_BLACK, 760, 140, 48, 30)
                    tag = rrect(860, 200, 40, CYAN + (255,))
                    dd = ImageDraw.Draw(tag)
                    y = (200 - len(lines) * s * 1.12) / 2
                    for ln in lines:
                        dd.text((430 - dd.textlength(ln, font=f) / 2, y), ln, font=f, fill=INK)
                        y += s * 1.12
                    self.cache["next"] = tag
                paste_c(img, tag, CX, 1230, scale=0.6 + 0.4 * ease_out_back(p), opacity=p)


def word_times(text, dur):
    """Estimate when each word is spoken (proportional to characters, small pauses at punctuation)."""
    ws = text.split()
    if not ws:
        return []
    weights = [len(w) + 2 + (5 if w[-1] in ".?!" else 2 if w[-1] in ",:" else 0) for w in ws]
    tot = sum(weights)
    out, acc = [], 0.0
    for w, wt in zip(ws, weights):
        out.append((w, dur * acc / tot))
        acc += wt
    return out


def main():
    spec_path, out = sys.argv[1], sys.argv[2]
    draft = "--draft" in sys.argv
    spec = json.load(open(spec_path))
    scenes = spec["scenes"]
    voices = Q.tts_all([s.get("say", "") for s in scenes], spec.get("voice", "af_heart"), spec.get("speed", 1.0))
    t = 0.0
    LEAD = 0.25
    for i, sc in enumerate(scenes):
        vd = len(voices[i]) / SR
        sc["_i"] = i
        sc["_start"] = t
        sc["_vstart"] = LEAD
        sc["_words"] = [(w, LEAD + wt) for w, wt in word_times(sc.get("say", ""), vd)]
        sc["_at"] = {}
        for key, word in sc.get("at", {}).items():
            hit = [wt for w, wt in sc["_words"] if w.lower().strip(".,?!'\"").startswith(word.lower())]
            sc["_at"][key] = hit[0] if hit else LEAD
        dur = LEAD + vd + sc.get("pad", 0.45)
        if sc["kind"] == "countdown":
            sc["_cstart"] = dur - 0.2
            dur = sc["_cstart"] + sc.get("count", 3) + 0.2
        sc["_dur"] = dur
        t += dur
    total = t + 0.6
    print(f"total {total:.1f}s", flush=True)

    # audio
    n = int(SR * total)
    voice = np.zeros(n, dtype=np.float32)
    fx = np.zeros(n, dtype=np.float32)

    def add(tr, sig, at, g=1.0):
        p = int(at * SR)
        s = sig[:max(0, n - p)]
        tr[p:p + len(s)] += s * g
    whoosh, tick_hi, tick_lo, correct, tada = Q.sfx_whoosh(), Q.sfx_tick(True), Q.sfx_tick(False), Q.sfx_correct(), Q.sfx_tada()
    import fx as fxl
    boom = fxl.boom(SR)
    for i, sc in enumerate(scenes):
        s0 = sc["_start"]
        add(voice, voices[i], s0 + sc["_vstart"])
        if i > 0:
            add(fx, whoosh, max(0, s0 - 0.12), 0.5)
        k = sc["kind"]
        if k == "hook":
            add(fx, boom, s0 + 0.05, 0.6)
        if k == "countdown":
            for j in range(sc.get("count", 3)):
                add(fx, tick_hi if j % 2 == 0 else tick_lo, s0 + sc["_cstart"] + j, 0.8)
        if k == "answer":
            add(fx, correct, s0 + 0.1, 0.8)
            add(fx, sfx_riser(0.7), s0 + max(0, sc["_at"].get("call", 1.2) - 0.7), 0.6)
        if k == "stat":
            add(fx, boom, s0 + 1.8, 0.45)
        if k == "quiz":
            add(fx, tada, s0 + 0.1, 0.5)
    bed = ambient_bed(total)
    env = np.convolve(np.abs(voice), np.ones(int(SR * 0.08)) / int(SR * 0.08), mode="same")
    env = np.clip(env / (env.max() + 1e-6) * 4, 0, 1)
    bed = bed[:n] * (1 - 0.5 * env)
    fl = int(SR * 0.8)
    bed[-fl:] *= np.linspace(1, 0, fl)
    mix = voice + fx * 0.55 + bed * 0.9
    mix = np.tanh(mix * 1.1) / np.tanh(1.1)
    mix = mix / (np.max(np.abs(mix)) + 1e-6) * 0.93
    import soundfile as sf
    wav = out + ".wav"
    sf.write(wav, mix, SR)

    r = R(spec, draft)
    ow, oh = (540, 960) if draft else (W, H)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{ow}x{oh}",
           "-r", str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "veryfast" if draft else "medium",
           "-crf", "26" if draft else "19", "-pix_fmt", "yuv420p", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
           "-ar", "44100", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    nframes = int(total * FPS)
    si = 0
    for fi in range(nframes):
        tt = fi / FPS
        while si + 1 < len(scenes) and tt >= scenes[si + 1]["_start"]:
            si += 1
        sc = scenes[si]
        img = r.frame(tt, sc, tt - sc["_start"])
        if tt > total - 0.6:
            img.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, int(255 * clamp((tt - (total - 0.6)) / 0.6)))))
        if draft:
            img = img.resize((ow, oh), Image.BILINEAR)
        ff.stdin.write(img.convert("RGB").tobytes())
        if fi % 150 == 0:
            print(f"frame {fi}/{nframes}", flush=True)
    ff.stdin.close()
    ff.wait()
    os.remove(wav)
    print("DONE", out, flush=True)


if __name__ == "__main__":
    main()
