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
            | "tokens" (NEW 2026-10-11: chat box types "prompt", candidate words [[word, pct], ...] slide in with filling
              bars, candidate "pick" gets highlighted and flies into the sentence - great for AI/"how it decides" topics)
            | "absorb" (NEW: streams of "emojis" fly into a "target" emoji that grows with every hit + "counter" counts up,
              "counter_label", "prefix", "suffix", "n_items" (default 18) - e.g. books into a brain, coins into a piggy bank, gas into a star)
            | "split" (NEW: big "word" gets sliced into "parts" that fly apart as coloured chips, "label" below)
            | "dice" (NEW: dice tumble, the ending of "prompt" changes every roll through "endings" - randomness/luck topics)
            | "claim" (NEW 2026-10-12: user question bubble + AI answer card + confidence meter climbing to "confidence" % +
              red "verdict" stamp (e.g. "MADE UP") slams on it; at:{"stamp": word} times the stamp - for hallucination/fact-check topics)
  step/hook anim "funnel" (NEW 2026-10-13: 👀 views rain into a funnel with a live "views" counter, only every "keep"-th view
            drops out of the spout as a 🪙 coin and stacks up; "payout" text (hook: "sub") under the pile - money/creator-pay/"how much do you really get" topics)
  step anim "crowd" (NEW 2026-10-14: grid of little people (default 10x10) pops in as a wave, then "hit" of them light up gold one by one
            with a "hit_emoji" (default 💳) while a live "n / total" counter counts; "label" under it - for "only X of 100 do Y" topics)
  step anim "hawking" (NEW 2026-10-16: particle pairs pop up at a black hole's edge, one escapes (cyan), one falls in (orange);
            mode "shrink" = hole shrinks + big "10^N YEARS" counter climbs to years_exp, hole pops away at the end; years_label)
  step anim "scramble" (NEW 2026-10-17: coloured letter "tiles" fly into a target and come out as dots; mode "fire" = dots keep
            the tile colours (info scrambled but recoverable), mode "hole" = black hole, dots all grey + big "?" pops; "label" at bottom,
            label_col cyan|orange|white, "q" - for information-paradox / shredder / hash / encryption topics)
  hook/step anim "compound" (NEW 2026-10-18: stacked bars grow year by year, cyan = money you paid in, gold = interest, live counters
            for total / paid in / interest + a "cross_label" sticker when interest passes what you paid in; fields monthly (default 100),
            rate (% per year, default 5), years (default 30), cross_label; for compound-interest / savings / growth-over-time topics)
  step/hook anim "speedstack" (NEW 2026-10-19: speedometer on a log scale; "frames": [[label, kmh, emoji, shown_text(optional)], ...] -
            the needle swings to the speed you have compared to each thing in turn (couch, Earth, Sun, galaxy ...), big number counts
            up, speed streaks fly past, finished frames stay in a list below; for "how fast / how big does it depend on who you ask" topics)
  hook anim "chat" (NEW: "chat" text is typed word by word into a chat bubble next to a bouncing "emoji")
  stat bg "dots" (NEW: grid of up to 300 dots fills in sync with the counter, "dot_label" e.g. "1 dot = 1 billion")
  compare   left {title, sub, emoji, verdict}, right {...}
  stat      value, unit, label, src
  quiz      title, options [[text, emoji], ...], next
Every scene shows auto captions of "say" (word timing estimated from text length).
MOTION PACK (2026-10-11, applies to every scene automatically): slow camera push-in + punch-zoom on every cut,
drifting glowing particles in the theme colours, video progress bar at the top, spoken word pops bigger in the
captions, sparkle bursts when emojis/answers appear, pulsing glow behind step emojis, bar values count up.
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
        prng = random.Random(7)
        self.parts = [(prng.uniform(0, W), prng.uniform(0, H), prng.uniform(18, 60), prng.uniform(3, 9),
                       prng.uniform(0, 6.28), prng.choice([ORANGE, CYAN, WHITE])) for _ in range(34)]
        self.total = 1.0

    def particles(self, img, t):
        lay = Image.new("RGBA", (W // 2, H // 2), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        for (x0, y0, sp, r, ph, col) in self.parts:
            y = (y0 - t * sp) % H
            x = x0 + 40 * math.sin(t * 0.7 + ph)
            a = int(120 + 80 * math.sin(t * 2 + ph))
            d.ellipse(((x - r * 2.2) / 2, (y - r * 2.2) / 2, (x + r * 2.2) / 2, (y + r * 2.2) / 2), fill=col + (a // 4,))
            d.ellipse(((x - r) / 2, (y - r) / 2, (x + r) / 2, (y + r) / 2), fill=col + (a,))
        lay = lay.filter(ImageFilter.GaussianBlur(1.5)).resize((W, H), Image.BILINEAR)
        img.alpha_composite(lay)

    def burst(self, img, cx, cy, lt, delay, rad=170, n=12):
        """Sparkle ring that flies outwards when something appears."""
        p = (lt - delay) / 0.55
        if not 0 < p < 1:
            return
        d = ImageDraw.Draw(img)
        e = ease_out_cubic(p)
        for i in range(n):
            a = i * 2 * math.pi / n + 0.3
            rr = rad * (0.35 + 0.9 * e)
            x, y = cx + math.cos(a) * rr, cy + math.sin(a) * rr
            sz = 11 * (1 - p) + 2
            col = (ORANGE if i % 2 else CYAN) + (int(255 * (1 - p)),)
            d.ellipse((x - sz, y - sz, x + sz, y + sz), fill=col)

    def glow(self, img, cx, cy, r, t, col=None, a=70):
        k = ("glow", r, col or CYAN)
        if k not in self.cache:
            S = 2 * r
            yy, xx = np.mgrid[0:S, 0:S] - r
            dd = np.sqrt(xx ** 2 + yy ** 2) / r
            al = (np.clip(1 - dd, 0, 1) ** 2 * 255).astype(np.uint8)
            im = Image.new("RGBA", (S, S), (col or CYAN) + (0,))
            im.putalpha(Image.fromarray(al, "L"))
            self.cache[k] = im
        paste_c(img, self.cache[k], cx, cy, scale=1 + 0.08 * math.sin(t * 4), opacity=a / 255)

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
        fb = font(F_BLACK, 74)
        total = sum(d0.textlength(p + " ", font=(fb if (chunk_first + i) == idx else f)) for i, p in enumerate(parts))
        im = Image.new("RGBA", (int(total) + 40, 110), (0, 0, 0, 0))
        dd = ImageDraw.Draw(im)
        x = 20
        for i, p in enumerate(parts):
            cur = (chunk_first + i) == idx
            ff_ = fb if cur else f
            dd.text((x, 4 if cur else 14), p, font=ff_, fill=(ORANGE if cur else WHITE) + (255,), stroke_width=6, stroke_fill=(0, 0, 0))
            x += d0.textlength(p + " ", font=ff_)
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
        self.particles(img, t)
        fg = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        getattr(self, "s_" + sc["kind"])(fg, sc, lt, t)
        # camera: slow push-in over the scene + punch zoom on the cut
        z = 1 + 0.035 * clamp(lt / max(1.0, sc["_dur"]))
        if sc["_i"] > 0:
            z += 0.07 * (1 - ease_out_cubic(clamp(lt / 0.35)))
        if z > 1.002:
            nw, nh = int(W * z), int(H * z)
            big = fg.resize((nw, nh), Image.BILINEAR)
            fg = big.crop(((nw - W) // 2, (nh - H) // 2, (nw - W) // 2 + W, (nh - H) // 2 + H))
        img.alpha_composite(fg)
        # progress bar
        d = ImageDraw.Draw(img)
        pw = int(W * clamp(t / self.total))
        d.rectangle((0, 0, W, 12), fill=(255, 255, 255, 40))
        if pw > 0:
            d.rectangle((0, 0, pw, 12), fill=ORANGE + (255,))
            d.ellipse((pw - 10, -4, pw + 10, 16), fill=CYAN + (255,))
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
            self.glow(img, CX, 880, 300, t, ORANGE, 90)
            e = e.rotate(6 * math.sin(t * 2.5), resample=Image.BICUBIC, expand=True)
            self.pop_in(img, e, CX, 880 + 15 * math.sin(t * 3), lt, 0.1, 0.5)
            self.burst(img, CX, 880, lt, 0.2, 230, 14)
            self.pop_in(img, self.T("ht", sc["title"], F_BLACK, 900, 260, 96, WHITE, stroke=4), CX, 380, lt, 0.05)
            self.slide_in(img, self.T("hs", sc["sub"], F_BLACK, 900, 120, 70, ORANGE, stroke=4), CX, 1250, lt, 0.5)
            return
        if sc.get("anim") == "funnel":
            self.pop_in(img, self.T("ht", sc["title"], F_BLACK, 900, 260, 96, WHITE, stroke=4), CX, 380, lt, 0.05)
            self.funnel_core(img, sc, lt, t, sc.get("sub", ""))
            return
        if sc.get("anim") == "speedstack":
            self.pop_in(img, self.T("ht", sc["title"], F_BLACK, 900, 260, 96, WHITE, stroke=4), CX, 380, lt, 0.05)
            self.speedstack_core(img, sc, lt, t, 840)
            return
        if sc.get("anim") == "compound":
            self.pop_in(img, self.T("ht", sc["title"], F_BLACK, 900, 260, 96, WHITE, stroke=4), CX, 380, lt, 0.05)
            self.slide_in(img, self.T("hs", sc["sub"], F_BLACK, 900, 120, 60, ORANGE, stroke=4), CX, 520, lt, 0.4)
            self.compound_core(img, sc, lt, t)
            return
        if sc.get("anim") == "chat":
            e = emoji_sprite(sc.get("emoji", "🤖"), 230)
            self.glow(img, 230, 1000, 230, t, ORANGE, 80)
            paste_c(img, e.rotate(8 * math.sin(t * 3), resample=Image.BICUBIC, expand=True), 230, 1000 - 25 * abs(math.sin(t * 3.5)))
            words = sc.get("chat", "").split()
            k = int(clamp((lt - 0.5) / max(0.5, sc["_dur"] - 1.2)) * len(words) + 0.999) if lt > 0.5 else 0
            bub = rrect(640, 420, 50, (255, 255, 255, 235))
            dd = ImageDraw.Draw(bub)
            dd.polygon([(0, 330), (60, 300), (60, 370)], fill=(255, 255, 255, 235))
            if k == 0:
                for j in range(3):
                    yy = 210 - 18 * max(0, math.sin(t * 8 - j))
                    dd.ellipse((250 + j * 60, yy - 18, 286 + j * 60, yy + 18), fill=(120, 120, 140, 255))
            else:
                lines, f, fs = fit(" ".join(words[:k]), F_BLACK, 560, 360, 64, 34)
                yy = 40
                for ln in lines:
                    dd.text((40, yy), ln, font=f, fill=INK)
                    yy += int(fs * 1.12)
            self.pop_in(img, bub, 650, 930, lt, 0.2)
            self.pop_in(img, self.T("ht", sc["title"], F_BLACK, 900, 260, 96, WHITE, stroke=4), CX, 380, lt, 0.05)
            self.slide_in(img, self.T("hs", sc["sub"], F_BLACK, 900, 120, 70, ORANGE, stroke=4), CX, 1300, lt, 0.5)
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
        self.glow(img, CX, 640, 260, t, GREEN, 90)
        self.pop_in(img, e, CX, 640 + 12 * math.sin(t * 4), lt, 0.0, 0.5)
        self.burst(img, CX, 640, lt, 0.1, 220, 16)
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
            if lt > 0.3 + 0.35 * i:
                self.glow(img, x, 960, int(size * 0.85), t + i, CYAN if i % 2 else ORANGE, 75)
            es = emoji_sprite(em, size).rotate(7 * math.sin(t * 2.2 + i * 1.3), resample=Image.BICUBIC, expand=True)
            self.pop_in(img, es, x, 960 + 12 * math.sin(t * 3 + i), lt, 0.3 + 0.35 * i, 0.45)
            self.burst(img, x, 960, lt, 0.35 + 0.35 * i, int(size * 0.75), 10)
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
            vv = int(round(v * ease_out_cubic(p))) if isinstance(v, int) else v
            txt = sc.get("prefix", "") + f"{vv:,}" + sc.get("suffix", "")
            paste_c(img, self.T(("gv", sc["n"], i), txt, F_BLACK, int(bw), 60, 44, WHITE, stroke=3), x, 1190 - h, opacity=min(1, p * 2))
            if labels[i]:
                paste_c(img, self.T(("gl", sc["n"], i), labels[i], F_BOLD, int(bw), 50, 34, (200, 210, 230)), x, 1260, opacity=p)

    def a_tokens(self, img, sc, lt, t):
        """Chat box types the prompt, candidate next words slide in with filling bars, the picked one flies in."""
        prompt = sc.get("prompt", "The sky is")
        cands = sc.get("candidates", [["blue", 62], ["clear", 21], ["falling", 9]])
        pick = sc.get("pick", 0)
        tp = 0.3                                     # typing start
        nch = int(clamp((lt - tp) / 1.0) * len(prompt))
        t_c = tp + 1.15                              # candidates start
        t_pick = t_c + 0.3 * len(cands) + 0.9
        t_fly = t_pick + 0.5
        box = self.cache.get("tokbox")
        if box is None:
            box = rrect(920, 190, 40, (255, 255, 255, 34), outline=CYAN + (200,), width=4)
            self.cache["tokbox"] = box
        self.pop_in(img, box, CX, 720, lt, 0.05)
        d = ImageDraw.Draw(img)
        f = font(F_BLACK, 70)
        shown = prompt[:nch]
        x0 = CX - 420
        d.text((x0, 680), shown, font=f, fill=WHITE + (255,))
        xe = x0 + d.textlength(shown + " ", font=f)
        fly = clamp((lt - t_fly) / 0.45)
        if fly >= 1:
            d.text((xe, 680), cands[pick][0], font=f, fill=ORANGE + (255,))
            xe += d.textlength(cands[pick][0], font=f)
        if lt > tp and int(lt * 2.5) % 2 == 0:                     # blinking cursor
            d.rectangle((xe + 6, 688, xe + 14, 752), fill=CYAN + (255,))
        if lt > tp - 0.1:
            self.slide_in(img, self.T("tklab", "NEXT WORD?", F_BLACK, 600, 70, 46, CYAN), CX, 600, lt, tp)
        for i, (wd, pct) in enumerate(cands):
            y = 930 + i * 140
            p = clamp((lt - t_c - 0.3 * i) / 0.35)
            if p <= 0:
                continue
            chosen = i == pick and lt >= t_pick
            if i == pick and t_pick <= lt < t_fly + 0.45:
                self.glow(img, CX, y, 300, t * 2, ORANGE, 110)
            chip = rrect(880, 112, 30, (ORANGE + (255,)) if chosen else (255, 255, 255, 40))
            dd = ImageDraw.Draw(chip)
            dd.text((30, 22), wd, font=font(F_BLACK, 58), fill=INK if chosen else WHITE)
            bp = clamp((lt - t_c - 0.3 * i - 0.2) / 0.7)
            bx0, bx1 = 360, 360 + 380 * pct / 100 * ease_out_cubic(bp)
            dd.rounded_rectangle((360, 38, 740, 74), radius=18, fill=(0, 0, 0, 90))
            if bx1 > bx0 + 4:
                dd.rounded_rectangle((bx0, 38, bx1, 74), radius=18, fill=(INK if chosen else CYAN) + (255,))
            ps = f"{int(round(pct * ease_out_cubic(bp)))}%"
            dd.text((860 - dd.textlength(ps, font=font(F_BLACK, 50)), 28), ps, font=font(F_BLACK, 50), fill=INK if chosen else WHITE)
            x_off = 120 * (1 - ease_out_cubic(p)) * (1 if i % 2 else -1)
            sc_ = 1 + (0.06 * math.sin(t * 8) if chosen and lt < t_fly + 0.6 else 0)
            paste_c(img, chip, CX + x_off, y, scale=sc_, opacity=p)
            if i == pick:
                self.burst(img, CX + 380, y, lt, t_pick, 120, 12)
        if 0 < fly < 1:                                             # picked word flies up into the sentence
            sy = 930 + pick * 140
            ex, ey = xe + 80, 715
            fx_ = CX - 260 + (ex - (CX - 260)) * ease_out_cubic(fly)
            fy_ = sy + (ey - sy) * ease_out_cubic(fly) - 120 * math.sin(math.pi * fly)
            paste_c(img, self.T(("tkf", pick), cands[pick][0], F_BLACK, 400, 90, 70, ORANGE, stroke=4), fx_, fy_)

    def a_absorb(self, img, sc, lt, t):
        """Streams of emojis fly into a target that grows with every hit; a counter counts up."""
        ems = sc.get("emojis", ["📚"])
        tgt = sc.get("target", "🧠")
        N = sc.get("n_items", 18)
        tx, ty = CX, 950
        rng = random.Random(11)
        hits = 0
        last_hit = -9
        flying = []
        for i in range(N):
            t0 = 0.35 + i * 0.16
            ang = rng.uniform(0, 2 * math.pi)
            sx, sy = tx + math.cos(ang) * 620, ty + math.sin(ang) * 520
            q = (lt - t0) / 0.6
            if q >= 1:
                hits += 1
                last_hit = max(last_hit, t0 + 0.6)
            elif q > 0:
                flying.append((ems[i % len(ems)], sx, sy, q, i))
        frac = hits / N
        bump = 0.18 * max(0, 1 - (lt - last_hit) / 0.18)
        self.glow(img, tx, ty, int(230 + 120 * frac), t, ORANGE, int(70 + 80 * frac))
        paste_c(img, emoji_sprite(tgt, 220), tx, ty, scale=0.8 + 0.55 * frac + bump)
        for (em, sx, sy, q, i) in flying:
            e = ease_out_cubic(q) if False else q * q
            x = sx + (tx - sx) * e
            y = sy + (ty - sy) * e - 90 * math.sin(math.pi * q)
            spr = emoji_sprite(em, 110).rotate(q * 300 * (1 if i % 2 else -1), resample=Image.BICUBIC, expand=True)
            paste_c(img, spr, x, y, scale=1 - 0.55 * q)
        if last_hit > 0:
            self.burst(img, tx, ty, lt, last_hit - 0.05, 180, 10)
        cv = sc.get("counter")
        if cv is not None:
            val = int(round(float(cv) * frac))
            txt = sc.get("prefix", "") + f"{val:,}" + sc.get("suffix", "")
            paste_c(img, text_sprite([txt], font(F_BLACK, 110), 110, ORANGE + (255,), stroke=6, stroke_fill=(0, 0, 0)), CX, 1250,
                    scale=1 + bump * 0.5)
            if sc.get("counter_label"):
                paste_c(img, self.T(("acl", sc["n"]), sc["counter_label"], F_BLACK, 880, 70, 44, WHITE, stroke=3), CX, 1345)

    def funnel_core(self, img, sc, lt, t, payout):
        """NEW 2026-10-13 'funnel': lots of views (eyes) rain into a funnel, only a few coins drop out of the spout.
        Fields: views (int, counter target), views_label, keep (every Nth view becomes a coin, default 9), n_items (default 54), payout (text under the pile)."""
        N = int(sc.get("n_items", 54))
        keep = int(sc.get("keep", 9))
        dur = max(3.0, sc["_dur"] - 1.2)
        top_y, spout_y, mouth_w, spout_w = 800, 1080, 840, 70
        # funnel body
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dd = ImageDraw.Draw(lay)
        pts = [(CX - mouth_w / 2, top_y), (CX + mouth_w / 2, top_y), (CX + spout_w / 2, spout_y), (CX + spout_w / 2, spout_y + 70),
               (CX - spout_w / 2, spout_y + 70), (CX - spout_w / 2, spout_y)]
        dd.polygon(pts, fill=CYAN + (38,))
        dd.line(pts + [pts[0]], fill=CYAN + (210,), width=8, joint="curve")
        img.alpha_composite(lay)
        rng = random.Random(5)
        step = dur / N
        seen = 0
        coins = []
        for i in range(N):
            t0 = 0.25 + i * step
            x0 = CX + rng.uniform(-mouth_w / 2 + 60, mouth_w / 2 - 60)
            q = lt - t0
            if q < 0:
                continue
            kept = (i % keep) == keep - 1
            fall = 0.55
            if q < fall:
                y = 715 + (top_y + 40 - 715) * (q / fall) ** 2
                x = x0
                a = 1.0
                sz = 96
                spr = emoji_sprite("👀", sz).rotate(q * 180, resample=Image.BICUBIC, expand=True)
                paste_c(img, spr, x, y)
                continue
            seen += 1
            q2 = (q - fall) / 0.75
            if q2 < 1:
                # slide down the funnel wall towards the spout
                e = q2 * q2 * 0.5 + q2 * 0.5
                yy = top_y + 40 + (spout_y - top_y - 40) * e
                half = (mouth_w / 2 - (mouth_w / 2 - spout_w / 2) * ((yy - top_y) / (spout_y - top_y))) - 40
                xx = CX + (x0 - CX) * (half / (mouth_w / 2 - 60))
                if kept:
                    paste_c(img, emoji_sprite("👀", 90), xx, yy, scale=1 - 0.25 * q2)
                else:
                    paste_c(img, emoji_sprite("👀", 90), xx, yy, scale=1 - 0.55 * q2, opacity=1 - 0.9 * q2 ** 1.5)
            elif kept:
                coins.append((i, q - fall - 0.75))
        # coins dropping out of the spout and stacking up
        base_y = 1330
        landed = 0
        for k, (i, qc) in enumerate(coins):
            dropt = 0.45
            if qc < dropt:
                y = spout_y + 40 + (base_y - spout_y - 40) * (qc / dropt) ** 2
                paste_c(img, emoji_sprite("🪙", 84), CX, y, scale=1.0)
                self.burst(img, CX, spout_y + 60, qc, 0.0, 70, 6)
            else:
                landed += 1
                row, col = divmod(landed - 1, 5)
                cx_ = CX - 120 + col * 60 + (30 if row % 2 else 0)
                paste_c(img, emoji_sprite("🪙", 76), cx_, base_y - row * 34)
        # counters
        frac = seen / N
        views = int(float(sc.get("views", 1000000)) * frac)
        vs = f"{views:,}"
        paste_c(img, text_sprite([vs], font(F_BLACK, 100), 100, WHITE + (255,), stroke=6, stroke_fill=(0, 0, 0)), CX, 575)
        paste_c(img, self.T(("fvl", sc["_i"]), sc.get("views_label", "VIEWS"), F_BLACK, 600, 50, 36, CYAN, stroke=3), CX, 640)
        if landed > 0 and payout:
            pp = clamp((lt - 0.0) / 0.01)
            paste_c(img, self.T(("fpo", sc["_i"]), payout, F_BLACK, 900, 120, 100, ORANGE, stroke=6), CX, 1400,
                    scale=1 + 0.06 * math.sin(t * 6))

    def a_funnel(self, img, sc, lt, t):
        self.funnel_core(img, sc, lt, t, sc.get("payout", ""))

    def a_crowd(self, img, sc, lt, t):
        """NEW 2026-10-14 'crowd': a grid of little people (default 10x10 = 100) pops in as a wave, then a few of them
        light up gold one by one (💳 pops above them) while a live counter shows how many of the crowd do it.
        Fields: total (default 100), cols (default 10), hit (how many light up, default 5), hit_emoji (default 💳),
        label (text under the counter, e.g. "OF EVERY 100 USERS PAY"), hit_start (seconds, default 1.7), seed."""
        total = int(sc.get("total", 100))
        cols = int(sc.get("cols", 10))
        rows = (total + cols - 1) // cols
        hit = int(sc.get("hit", 5))
        cell = min(62, 800 // cols)
        x0 = CX - cols * cell / 2 + cell / 2
        y0 = 600 + cell / 2
        if ("ppl", cell) not in self.cache:
            for name, body, head in (("g", (110, 125, 150, 255), (140, 155, 180, 255)), ("y", ORANGE + (255,), (255, 214, 140, 255))):
                S = int(cell * 0.9)
                sp = Image.new("RGBA", (S, S), (0, 0, 0, 0))
                dd = ImageDraw.Draw(sp)
                dd.ellipse((S * 0.32, S * 0.04, S * 0.68, S * 0.40), fill=head)
                dd.rounded_rectangle((S * 0.16, S * 0.45, S * 0.84, S * 1.0), radius=int(S * 0.26), fill=body)
                self.cache[("ppl", cell, name)] = sp
            self.cache[("ppl", cell)] = True
        rng = random.Random(sc.get("seed", 3))
        chosen = rng.sample(range(total), hit)
        t_hit = float(sc.get("hit_start", 1.7))
        lit = 0
        order = {idx: k for k, idx in enumerate(sorted(chosen, key=lambda i: (i % cols) * 3 + i // cols))}
        for i in range(total):
            r_, c_ = divmod(i, cols)
            x, y = x0 + c_ * cell, y0 + r_ * cell
            p = clamp((lt - 0.15 - (r_ + c_) * 0.04) / 0.35)
            if p <= 0:
                continue
            if i in chosen:
                th = t_hit + order[i] * 0.45
                q = clamp((lt - th) / 0.4)
            else:
                q = 0.0
            if q > 0:
                if lt - th < 0.45 * 1.0 and q > 0:
                    pass
                lit += 1 if lt >= th else 0
                self.glow(img, x, y, int(cell * 1.1), t + i, ORANGE, 110)
                paste_c(img, self.cache[("ppl", cell, "y")], x, y, scale=1.0 + 0.5 * math.sin(math.pi * min(1, q)) + 0.12 * q)
                self.burst(img, x, y, lt, th, int(cell * 0.9), 6)
                if q > 0.3:
                    paste_c(img, emoji_sprite(sc.get("hit_emoji", "💳"), int(cell * 0.62)), x + cell * 0.22, y - cell * 0.42,
                            scale=ease_out_back(clamp((q - 0.3) / 0.7)))
            else:
                dim = 1.0 if lit == 0 else 0.55 + 0.45 * (1 - clamp((lt - t_hit) / 3.0))
                paste_c(img, self.cache[("ppl", cell, "g")], x, y, scale=ease_out_back(p), opacity=min(1, p * 2) * dim)
        bump = 0.0
        txt = f"{lit} / {total}"
        paste_c(img, text_sprite([txt], font(F_BLACK, 120), 120, ORANGE + (255,), stroke=7, stroke_fill=(0, 0, 0)), CX, 600 + rows * cell + 85,
                scale=1 + 0.05 * math.sin(t * 6) * (1 if lit else 0))
        if sc.get("label"):
            paste_c(img, self.T(("crl", sc["n"]), sc["label"], F_BLACK, 900, 70, 46, WHITE, stroke=3), CX, 600 + rows * cell + 175)

    def compound_core(self, img, sc, lt, t):
        """NEW 2026-10-18 'compound': one stacked bar per year grows left to right. Cyan = money you paid in, gold = interest.
        Live counters (total / paid in / interest) and a sticker when interest passes the paid-in money.
        Fields: monthly (default 100), rate (% per year, default 5), years (default 30), cross_label (sticker text)."""
        monthly = float(sc.get("monthly", 100))
        years = int(sc.get("years", 30))
        r = float(sc.get("rate", 5)) / 100 / 12
        bal = (lambda m: monthly * (((1 + r) ** m - 1) / r)) if r else (lambda m: monthly * m)
        final = bal(years * 12)
        dur = max(3.0, sc["_dur"] - 1.4)
        p = clamp((lt - 0.3) / dur)
        yc = years * p
        base_y, maxh = 1380, 460
        bw = 860.0 / years
        x0 = CX - 430
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((x0 - 10, base_y, x0 + 870, base_y + 8), radius=4, fill=(255, 255, 255, 120))
        cross = None
        for m_ in range(1, years * 12 + 1):
            if bal(m_) - monthly * m_ > monthly * m_:
                cross = m_ / 12.0
                break
        for i in range(years):
            fr = clamp(yc - i)
            if fr <= 0:
                break
            m = (i + fr) * 12
            tot, paid = bal(m), monthly * m
            h_t, h_p = maxh * tot / final, maxh * paid / final
            x = x0 + bw * i
            d.rectangle((x + 1.5, base_y - h_p, x + bw - 1.5, base_y), fill=CYAN + (255,))
            if h_t - h_p > 0.5:
                d.rectangle((x + 1.5, base_y - h_t, x + bw - 1.5, base_y - h_p), fill=ORANGE + (255,))
        m = yc * 12
        tot, paid = bal(m), monthly * m
        paste_c(img, text_sprite([f"${int(round(tot)):,}"], font(F_BLACK, 130), 130, WHITE + (255,), stroke=7, stroke_fill=(0, 0, 0)), CX, 690)
        paste_c(img, text_sprite([f"YOU PAID IN ${int(round(paid)):,}"], font(F_BLACK, 46), 46, CYAN + (255,), stroke=4, stroke_fill=(0, 0, 0)), CX, 800)
        paste_c(img, text_sprite([f"INTEREST ${int(round(tot - paid)):,}"], font(F_BLACK, 56), 56, ORANGE + (255,), stroke=5, stroke_fill=(0, 0, 0)), CX, 868,
                scale=1 + 0.04 * math.sin(t * 6) * (p > 0.02))
        for yy in (10, 20, 30):
            if yy <= years:
                paste_c(img, text_sprite([f"{yy}y"], font(F_BLACK, 34), 34, (200, 210, 230, 255), stroke=3, stroke_fill=(0, 0, 0)), x0 + bw * yy - bw / 2, base_y + 38)
        if cross and sc.get("cross_label") and yc >= cross:
            lab = rrect(840, 120, 40, ORANGE + (255,))
            dd = ImageDraw.Draw(lab)
            f = font(F_BLACK, 54)
            tx = sc["cross_label"]
            dd.text((420 - dd.textlength(tx, font=f) / 2, 28), tx, font=f, fill=INK)
            self.pop_in(img, lab.rotate(5, resample=Image.BICUBIC, expand=True), CX - 90, 1010, lt, 0.3 + dur * cross / years, 0.35)
            self.burst(img, CX - 90, 1010, lt, 0.3 + dur * cross / years, 260, 12)
        if p >= 1:
            self.burst(img, x0 + 860, base_y - maxh, lt, 0.3 + dur, 200, 12)

    def a_compound(self, img, sc, lt, t):
        self.compound_core(img, sc, lt, t)

    def speedstack_core(self, img, sc, lt, t, cy=900):
        """NEW 2026-10-19 'speedstack': a speedometer on a log scale. "frames": [[label, kmh, emoji, shown_text(optional)], ...]
        - one frame after the other the needle swings to the speed you have compared to that thing (couch, Earth, Sun, galaxy ...),
        the big number counts up, speed streaks fly past (longer = faster) and every finished frame stays in a list below."""
        fr = sc["frames"]
        n = len(fr)
        dur = max(2.5, sc["_dur"])
        per = (dur - 0.5) / n
        x_ = max(0.0, lt - 0.3)
        idx = min(n - 1, int(x_ / per))
        loc = x_ - idx * per
        vmax = max(f[1] for f in fr) * 1.2
        la = lambda v: 0.0 if v <= 0 else min(1.0, math.log10(1 + v) / math.log10(1 + vmax))
        prev = fr[idx - 1][1] if idx > 0 else 0
        cur = fr[idx][1]
        k = clamp(loc / 0.7)
        a_prev, a_cur = la(prev), la(cur)
        a_now = a_prev + (a_cur - a_prev) * ease_out_back(k)
        a_now = max(0.0, min(1.04, a_now))
        val = prev + (cur - prev) * ease_out_cubic(k)
        # speed streaks
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dl = ImageDraw.Draw(lay)
        rng = random.Random(5)
        spd = 0.15 + 2.6 * (a_prev + (a_cur - a_prev) * k)
        for i in range(30):
            y = 520 + rng.random() * 900
            ph = rng.random()
            ln = 40 + 330 * spd * (0.4 + rng.random())
            x = (ph * (W + 400) - t * (300 + 1500 * spd) * (0.5 + rng.random() * 0.6)) % (W + 400) - 200
            dl.line((x, y, x + ln, y), fill=(255, 255, 255, int(55 + 40 * rng.random())), width=3)
        img.alpha_composite(lay)
        d = ImageDraw.Draw(img)
        R0 = 270
        bb = (CX - R0, cy - R0, CX + R0, cy + R0)
        d.arc(bb, 180, 360, fill=(255, 255, 255, 50), width=38)
        if a_now > 0.004:
            d.arc(bb, 180, 180 + 180 * min(1.0, a_now), fill=ORANGE + (255,), width=38)
        for j in range(0, 11):
            aa = math.pi * (1 + j / 10.0)
            r1, r2 = R0 + 30, R0 + (52 if j % 5 == 0 else 42)
            d.line((CX + math.cos(aa) * r1, cy + math.sin(aa) * r1, CX + math.cos(aa) * r2, cy + math.sin(aa) * r2),
                   fill=(255, 255, 255, 160), width=4)
        na = math.pi * (1 + a_now)
        tipx, tipy = CX + math.cos(na) * (R0 - 40), cy + math.sin(na) * (R0 - 40)
        d.line((CX, cy, tipx, tipy), fill=WHITE + (255,), width=12)
        d.ellipse((CX - 26, cy - 26, CX + 26, cy + 26), fill=CYAN + (255,))
        d.ellipse((CX - 11, cy - 11, CX + 11, cy + 11), fill=(10, 14, 30, 255))
        # emoji of the current frame orbits the hub
        em = emoji_sprite(fr[idx][2] if len(fr[idx]) > 2 else "🌍", 120)
        orb = t * (1.2 + 5 * spd)
        paste_c(img, em, CX + math.cos(orb) * 150 * 0.0, cy - 150 + 12 * math.sin(t * 5), scale=0.6 + 0.4 * ease_out_back(clamp(loc / 0.4)))
        # big number
        shown = fr[idx][3] if len(fr[idx]) > 3 and k >= 1 else f"{int(round(val)):,}"
        paste_c(img, text_sprite([shown], font(F_BLACK, 118), 118, WHITE + (255,), stroke=7, stroke_fill=(0, 0, 0)), CX, cy + 120,
                scale=1 + 0.03 * math.sin(t * 7))
        paste_c(img, text_sprite(["KM/H"], font(F_BLACK, 46), 46, CYAN + (255,), stroke=4, stroke_fill=(0, 0, 0)), CX, cy + 205)
        # label sticker (what you compare to)
        lab = fr[idx][0]
        sp = rrect(860, 96, 34, ORANGE + (255,))
        dd = ImageDraw.Draw(sp)
        lines, ff, fs = fit("vs " + lab if False else lab, F_BLACK, 800, 70, 52, 30)
        dd.text((430 - dd.textlength(lines[0], font=ff) / 2, 48 - fs * 0.6), lines[0], font=ff, fill=INK)
        paste_c(img, sp, CX, cy + 300, scale=0.8 + 0.2 * ease_out_back(clamp(loc / 0.35)))
        self.burst(img, CX, cy + 300, loc, 0.0, 260, 10)
        # finished frames as a list
        rows = [i for i in range(idx)]
        for r_, i in enumerate(rows):
            yy = cy + 375 + r_ * 38
            txt = fr[i][0] + "  " + (fr[i][3] if len(fr[i]) > 3 else f"{int(fr[i][1]):,}")
            paste_c(img, self.T(("ssr", txt), txt, F_BOLD, 800, 40, 34, (200, 210, 230)), CX, yy, opacity=0.85)

    def a_speedstack(self, img, sc, lt, t):
        self.speedstack_core(img, sc, lt, t)

    def a_hawking(self, img, sc, lt, t):
        """NEW 2026-10-16 'hawking': particle pairs flicker into existence at the edge of a black hole, one flies away
        (cyan), its partner falls in (orange).  mode "pairs" (default): hole stays the same size, "ESCAPES" / "FALLS IN"
        labels.  mode "shrink": the hole shrinks while the escapes keep coming and a big "10^N YEARS" counter climbs to
        "years_exp" (default 67); at the end the hole pops away (poof).  Fields: mode, years_exp, years_label."""
        shrink = sc.get("mode", "pairs") == "shrink"
        cy = 900
        dur = max(2.0, sc["_dur"])
        q = clamp((lt - 0.5) / max(1.0, dur - 1.6)) if shrink else 0.0
        scale = 0.95 - 0.78 * ease_out_cubic(q) if shrink else 0.95
        gone = shrink and lt > dur - 0.7
        if shrink and gone:
            k = clamp((lt - (dur - 0.7)) / 0.5)
            self.draw_bh(img, CX, cy, max(0.05, scale * (1 - k)), t, 1 - k)
            self.burst(img, CX, cy, lt, dur - 0.7, 200, 16)
        else:
            self.draw_bh(img, CX, cy, scale, t)
        d = ImageDraw.Draw(img)
        Rr = self.bh_R * scale * 1.05
        npair = 14 if shrink else 9
        life = 1.5
        rng = random.Random(11)
        for i in range(npair):
            t0 = 0.35 + i * (0.38 if not shrink else (dur - 1.8) / npair)
            ph = (lt - t0) / life
            ang = -math.pi * (0.1 + 0.8 * rng.random())
            if gone or not 0 < ph < 1:
                continue
            bx, by = CX + math.cos(ang) * Rr, cy + math.sin(ang) * Rr
            ux, uy = math.cos(ang), math.sin(ang)
            spark = clamp(ph / 0.15)
            self.glow(img, bx, by, 55, t + i, WHITE, int(130 * (1 - ph) * spark))
            # escaping partner (cyan) flies outwards with a trail
            e = ease_out_cubic(ph)
            for kk in range(7):
                pe = ease_out_cubic(max(0.0, ph - kk * 0.03))
                x, y = bx + ux * 420 * pe, by + uy * 420 * pe
                r = 14 - kk * 1.6
                d.ellipse((x - r, y - r, x + r, y + r), fill=CYAN + (int(255 * (1 - ph) * (1 - kk / 8)),))
            # falling partner (orange) is pulled into the hole
            for kk in range(5):
                pf = clamp(ph - kk * 0.03) ** 1.6
                x, y = bx - ux * 0.0 + (CX - bx) * pf, by + (cy - by) * pf
                r = 12 - kk * 1.8
                d.ellipse((x - r, y - r, x + r, y + r), fill=ORANGE + (int(255 * (1 - 0.5 * ph) * (1 - kk / 6)),))
        if not shrink:
            self.pop_in(img, self.T("hw1", "ESCAPES", F_BLACK, 400, 70, 56, CYAN, stroke=4), CX + 300, 660, lt, 0.9)
            self.pop_in(img, self.T("hw2", "FALLS IN", F_BLACK, 400, 70, 56, ORANGE, stroke=4), CX - 280, 1320, lt, 1.4)
            return
        n = int(round(float(sc.get("years_exp", 67)) * ease_out_cubic(clamp((lt - 0.4) / max(1.0, dur - 1.3)))))
        f1, f2 = font(F_BLACK, 170), font(F_BLACK, 90)
        a = "10"
        w1, w2 = d.textlength(a, font=f1), d.textlength(str(n), font=f2)
        x0 = CX - (w1 + w2 + 20) / 2
        pulse = 1 + 0.03 * math.sin(t * 7)
        for off, col in (((5, 5), (0, 0, 0)), ((0, 0), ORANGE)):
            d.text((x0 + off[0], 1190 + off[1]), a, font=f1, fill=col + (255,))
            d.text((x0 + w1 + 20 + off[0], 1170 + off[1]), str(n), font=f2, fill=(WHITE if off == (0, 0) else col) + (255,))
        paste_c(img, self.T("hwy", sc.get("years_label", "YEARS FROM NOW"), F_BLACK, 800, 70, 52, WHITE, stroke=4), CX, 1400, opacity=clamp((lt - 0.3) / 0.3))

    def a_scramble(self, img, sc, lt, t):
        """NEW 2026-10-17 'scramble': coloured letter tiles ("tiles", default 5) fly into a target and come out as dots.
        mode "fire" (target = flame emoji): the dots keep the tile colours = information scrambled but still there.
        mode "hole" (target = black hole): the dots come out all the same grey = nothing visible about what went in; a big
        "?" pops at the end ("q", default "?").  Fields: mode, tiles ["H","I",..], label (shown at the bottom),
        label_col ("cyan"|"orange"|"white"), q.  For info-paradox / hash / encryption / shredder style topics."""
        hole = sc.get("mode", "fire") == "hole"
        tiles = sc.get("tiles", ["B", "O", "O", "K", "S"])
        pal = [ORANGE, CYAN, (244, 114, 182), (52, 211, 153), (250, 204, 21), (167, 139, 250)]
        tx, ty = CX, 980
        dur = max(2.5, sc["_dur"])
        if hole:
            self.draw_bh(img, tx, ty, 0.8, t)
        else:
            self.glow(img, tx, ty, 260, t, (255, 120, 30), 110)
            paste_c(img, emoji_sprite("🔥", 250), tx, ty, scale=1 + 0.06 * math.sin(t * 9))
        n = len(tiles)
        gap = (dur - 2.4) / max(1, n)
        gap = clamp(gap, 0.25, 0.5)
        rng = random.Random(5)
        d = ImageDraw.Draw(img)
        arrived = 0
        for i, ch in enumerate(tiles):
            col = pal[i % len(pal)]
            t0 = 0.4 + i * gap
            q = (lt - t0) / 0.7
            sx, sy = 150 + (i % 2) * 40, 640 + i * 20
            if 0 < q < 1:
                e = q * q
                x = sx + (tx - sx) * e
                y = sy + (ty - sy) * e - 110 * math.sin(math.pi * q)
                spr = self.cache.get(("tile", ch, col))
                if spr is None:
                    spr = rrect(120, 120, 26, col + (255,))
                    dd = ImageDraw.Draw(spr)
                    f = font(F_BLACK, 78)
                    dd.text((60 - dd.textlength(ch, font=f) / 2, 12), ch, font=f, fill=INK)
                    self.cache[("tile", ch, col)] = spr
                paste_c(img, spr.rotate(q * 200, resample=Image.BICUBIC, expand=True), x, y, scale=1 - 0.6 * q)
            elif q >= 1:
                arrived += 1
                # outgoing dots
                for k in range(4):
                    ph = (lt - (t0 + 0.7) - k * 0.1) / 1.3
                    ang = rng.uniform(-0.9, 0.9) + (-0.35 if k % 2 else 0.35)
                    if not 0 < ph < 1:
                        continue
                    e = ease_out_cubic(ph)
                    x = tx + 120 + math.cos(ang) * 420 * e
                    y = ty + math.sin(ang) * 380 * e + 40 * math.sin(t * 5 + k)
                    r = 17 * (1 - 0.4 * ph)
                    c = (170, 175, 190) if hole else col
                    d.ellipse((x - r, y - r, x + r, y + r), fill=c + (int(255 * (1 - ph * 0.6)),))
                    if q >= 1 and k == 0 and ph < 0.08:
                        self.burst(img, tx, ty, lt, t0 + 0.7, 120, 8)
        lab = sc.get("label")
        if lab:
            colname = sc.get("label_col", "cyan")
            c = {"cyan": CYAN, "orange": ORANGE, "white": WHITE}.get(colname, CYAN)
            self.pop_in(img, self.T(("scl", lab), lab, F_BLACK, 900, 150, 64, c, stroke=5), CX, 1390, lt, 0.4 + n * gap + 0.4)
        if hole:
            self.pop_in(img, self.T("scq", sc.get("q", "?"), F_BLACK, 300, 240, 220, WHITE, stroke=8), CX + 280, 700, lt, 0.4 + n * gap + 0.9)

    def a_split(self, img, sc, lt, t):
        """A word gets sliced into pieces (e.g. tokens) that fly apart as coloured chips."""
        word = sc.get("word", "unbelievable")
        parts = sc.get("parts", [word])
        cut = 1.1
        fz = font(F_BLACK, 120)
        d0 = ImageDraw.Draw(Image.new("L", (4, 4)))
        widths = [d0.textlength(p_, font=fz) for p_ in parts]
        totw = sum(widths)
        scale = min(1.0, 900 / (totw + 60 * len(parts)))
        p = clamp((lt - cut - 0.2) / 0.6)
        x = CX - (totw * scale + p * 60 * (len(parts) - 1)) / 2
        cols_ = [ORANGE, CYAN, (167, 139, 250), (52, 211, 153), (250, 204, 21)]
        for i, (pt, w_) in enumerate(zip(parts, widths)):
            col = cols_[i % len(cols_)] if p > 0 else WHITE
            chip = text_sprite([pt], fz, 120, col + (255,), stroke=6, stroke_fill=(0, 0, 0))
            cx = x + w_ * scale / 2
            cy = 960 - 40 * math.sin(math.pi * p) * (1 if i % 2 else -1)
            rot = 10 * math.sin(math.pi * p) * (1 if i % 2 else -1)
            if abs(rot) > 0.5:
                chip = chip.rotate(rot, resample=Image.BICUBIC, expand=True)
            self.pop_in(img, chip, cx, cy, lt, 0.2, 0.4) if lt < 0.6 else paste_c(img, chip, cx, cy, scale=scale)
            if p > 0.6:
                tag = self.T(("spt", i), f"#{i + 1}", F_BLACK, 200, 60, 40, col)
                paste_c(img, tag, cx, 1060, opacity=clamp((p - 0.6) / 0.4))
            x += w_ * scale + p * 60
        # the knife slash
        s_ = clamp((lt - cut) / 0.25)
        if 0 < s_ < 1 or (1 <= s_ and lt < cut + 0.45):
            d = ImageDraw.Draw(img)
            a_ = min(1, s_)
            x0 = CX - 520 + 1040 * a_
            alpha = int(255 * (1 - clamp((lt - cut - 0.25) / 0.2)))
            d.line([(CX - 520, 1030), (x0, 890)], fill=WHITE + (alpha,), width=10)
            d.line([(CX - 520, 1030), (x0, 890)], fill=CYAN + (alpha // 2,), width=26)
        if sc.get("label"):
            self.slide_in(img, self.T(("spl", sc["n"]), sc["label"], F_BLACK, 880, 140, 60, ORANGE, stroke=4), CX, 1230, lt, cut + 0.8)

    def a_dice(self, img, sc, lt, t):
        """Dice tumble; every roll the ending of the sentence changes."""
        prompt = sc.get("prompt", "The sky is")
        ends = sc.get("endings", ["blue", "clear", "huge"])
        period = 1.25
        k = int(max(0, lt - 0.3) / period)
        ph = (max(0, lt - 0.3) % period) / period
        rolling = ph < 0.55 and lt > 0.3
        box = self.cache.get("dicebox")
        if box is None:
            box = rrect(920, 170, 40, (255, 255, 255, 34), outline=ORANGE + (200,), width=4)
            self.cache["dicebox"] = box
        paste_c(img, box, CX, 700)
        d = ImageDraw.Draw(img)
        f = font(F_BLACK, 70)
        x0 = CX - 420
        d.text((x0, 660), prompt, font=f, fill=WHITE + (255,))
        xe = x0 + d.textlength(prompt + " ", font=f)
        if not rolling and lt > 0.3:
            end = ends[k % len(ends)]
            pp = clamp((ph - 0.55) / 0.15)
            spr = text_sprite([end], f, 70, ORANGE + (255,))
            paste_c(img, spr, xe + spr.width / 2, 700 - 4, scale=0.5 + 0.5 * ease_out_back(pp))
            if pp < 1:
                self.burst(img, xe + spr.width / 2, 700, ph, 0.55, 110, 10)
        else:
            d.text((xe, 660), "???", font=f, fill=(255, 255, 255, 120))
        # two dice tumbling
        for j in range(2):
            bx = CX - 150 + 300 * j
            hop = abs(math.sin(math.pi * ph * 2)) * (1 - ph) * 260 if rolling else 0
            rot = (ph * 720 + j * 90) if rolling else (j * 12 - 6)
            de = emoji_sprite("🎲", 210).rotate(rot, resample=Image.BICUBIC, expand=True)
            paste_c(img, de, bx, 1080 - hop)
            d.ellipse((bx - 90 + hop * 0.1, 1180, bx + 90 - hop * 0.1, 1210), fill=(0, 0, 0, 110))
        tag = self.T("dicecnt", "ROLL", F_BLACK, 400, 60, 40, CYAN)
        paste_c(img, self.T(("dk", k), f"ROLL #{k + 1}", F_BLACK, 400, 60, 44, CYAN), CX, 1290)

    def a_claim(self, img, sc, lt, t):
        """NEW 2026-10-12: chat answer card + confidence meter that climbs to 9x% while a red stamp (verdict) slams on it.
        Fields: question, answer, confidence (int), verdict (e.g. "MADE UP"), conf_label. Stamp time via at:{"stamp": word}."""
        d = ImageDraw.Draw(img)
        q = self.T(("cq", sc["n"]), sc.get("question", "Who wrote this?"), F_BOLD, 640, 110, 50, WHITE)
        qb = self.cache.get(("cqb", sc["n"]))
        if qb is None:
            qb = rrect(q.width + 70, q.height + 50, 36, (96, 165, 250, 235) if CYAN[2] > 200 else CYAN + (235,))
            paste_c(qb, q, qb.width // 2, qb.height // 2)
            self.cache[("cqb", sc["n"])] = qb
        self.slide_in(img, qb, 1010 - qb.width / 2, 640, lt, 0.15)
        a = self.T(("ca", sc["n"]), sc.get("answer", "It was written by ..."), F_BOLD, 760, 200, 56, WHITE)
        ab = self.cache.get(("cab", sc["n"]))
        if ab is None:
            ab = rrect(900, a.height + 100, 40, (255, 255, 255, 40), outline=(255, 255, 255, 120), width=4)
            paste_c(ab, a, ab.width // 2, ab.height // 2)
            self.cache[("cab", sc["n"])] = ab
        ay = 880
        self.slide_in(img, ab, CX, ay, lt, 0.7)
        # confidence meter
        conf = sc.get("confidence", 97)
        my = ay + ab.height // 2 + 130
        if lt > 1.4:
            p = ease_out_cubic(clamp((lt - 1.4) / 1.6))
            d.rounded_rectangle((CX - 400, my, CX + 400, my + 52), 26, fill=(255, 255, 255, 40))
            wbar = max(2, int(800 * conf / 100 * p))
            col = (int(255 * p + 60 * (1 - p)), int(200 - 140 * p), 70)
            d.rounded_rectangle((CX - 400, my, CX - 400 + wbar, my + 52), 26, fill=col + (255,))
            lab = text_sprite([sc.get("conf_label", "CONFIDENCE") + "  %d%%" % int(conf * p)], font(F_BLACK, 46), 46, WHITE + (255,), stroke=3, stroke_fill=(0, 0, 0))
            paste_c(img, lab, CX, my - 44)
        # stamp
        ts = sc["_at"].get("stamp", 3.3) if sc.get("_at") else 3.3
        sp = (lt - ts)
        if sp > 0:
            e = ease_out_back(clamp(sp / 0.28))
            stamp = self.cache.get(("cst", sc["n"]))
            if stamp is None:
                txt = text_sprite([sc.get("verdict", "MADE UP")], font(F_BLACK, 110), 110, RED + (255,), stroke=0)
                stamp = rrect(txt.width + 80, txt.height + 50, 26, (0, 0, 0, 0), outline=RED + (255,), width=12)
                paste_c(stamp, txt, stamp.width // 2, stamp.height // 2)
                self.cache[("cst", sc["n"])] = stamp
            st = stamp.rotate(-11, resample=Image.BICUBIC, expand=True)
            shake = 14 * math.sin(sp * 60) * max(0, 1 - sp / 0.4)
            sy = my + 230
            paste_c(img, st, CX + shake, sy, scale=2.2 - 1.2 * e, opacity=min(1, sp * 6))
            self.burst(img, CX, sy, sp, 0.05, 380, 14)

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
        if bg == "dots":
            nd = min(300, int(sc["value"]))
            cols_ = 20
            d = ImageDraw.Draw(img)
            on = int(nd * ease_out_cubic(clamp((lt - 0.2) / 2.2)))
            for i in range(nd):
                gx, gy = i % cols_, i // cols_
                x, y = CX - 19 * 22 + gx * 44, 1000 + gy * 24
                if i < on:
                    fresh = i > on - 12
                    r_ = 13 if fresh else 10
                    d.ellipse((x - r_, y - r_, x + r_, y + r_), fill=(WHITE if fresh else (ORANGE if (i // cols_) % 2 else CYAN)) + (255,))
                else:
                    d.ellipse((x - 4, y - 4, x + 4, y + 4), fill=(255, 255, 255, 40))
            if sc.get("dot_label"):
                self.slide_in(img, self.T("sdl", sc["dot_label"], F_BLACK, 860, 70, 44, CYAN), CX, 1385, lt, 1.0)
        v = float(sc["value"]) * ease_out_cubic(p)
        s = "~" + sc.get("prefix", "") + str(int(round(v))) + sc.get("unit", "")
        big = text_sprite([s], font(F_BLACK, 260), 260, ORANGE + (255,), stroke=8, stroke_fill=(0, 0, 0))
        paste_c(img, big, CX, 640, scale=1 + 0.05 * math.sin(t * 6) * (p >= 1))
        self.slide_in(img, self.T("sl", sc["label"], F_BLACK, 880, 220, 66, WHITE, stroke=4), CX, 900, lt, 0.6)
        self.slide_in(img, self.T("ss", sc["src"], F_BOLD, 860, 80, 38, (180, 190, 210)), CX, 1300 if bg != "dots" else 1650, lt, 1.0)

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
        if k == "step" and sc.get("anim") == "claim":
            add(fx, boom, s0 + sc["_at"].get("stamp", 3.3), 0.7)
        if k == "step" and sc.get("anim") == "crowd":
            for j in range(int(sc.get("hit", 5))):
                add(fx, correct, s0 + float(sc.get("hit_start", 1.7)) + j * 0.45, 0.35)
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
    r.total = total
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
