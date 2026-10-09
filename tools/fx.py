"""Shared fun overlays for Unreel renderers: meme-style stickers (tilted pill with text + emoji) and a bass boom.

sticker(text, emoji=None, bg=(255, 221, 0), fg=(15, 15, 20), size=56, angle=-5) -> RGBA image
draw_popups(img, popups, t)  popups = [(t0, sprite, cx, cy, dur)]; pops in with a bounce, wiggles, fades out.
boom(sr) -> float32 mono array (synthesised low "boom" hit, meme-style, royalty-free)
"""
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont

F_BLACK = "/usr/share/fonts/opentype/inter/InterDisplay-Black.otf"
F_EMOJI = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
_c = {}


def _font(sz):
    if sz not in _c:
        _c[sz] = ImageFont.truetype(F_BLACK, sz)
    return _c[sz]


def emoji_img(e, size):
    k = ("e", e, size)
    if k not in _c:
        ef = ImageFont.truetype(F_EMOJI, 109)
        im = Image.new("RGBA", (420, 180), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((10, 10), e, font=ef, embedded_color=True)
        bb = im.getbbox()
        im = im.crop(bb) if bb else im
        s = size / max(im.width, im.height)
        _c[k] = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
    return _c[k]


def sticker(text, emoji=None, bg=(255, 221, 0), fg=(15, 15, 20), size=56, angle=-5, maxw=900):
    f = _font(size)
    d = ImageDraw.Draw(Image.new("L", (4, 4)))
    while d.textlength(text, font=f) > maxw - (size * 1.6 if emoji else 0) - 60 and size > 30:
        size -= 4
        f = _font(size)
    tw = int(d.textlength(text, font=f))
    es = int(size * 1.25)
    w = tw + 60 + (es + 16 if emoji else 0)
    h = int(size * 1.75)
    ss = 3
    pill = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    pd = ImageDraw.Draw(pill)
    pd.rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), radius=h * ss // 2, fill=(0, 0, 0, 255))
    pd.rounded_rectangle((5 * ss, 5 * ss, w * ss - 1 - 5 * ss, h * ss - 1 - 5 * ss), radius=h * ss // 2, fill=bg + (255,))
    pill = pill.resize((w, h), Image.LANCZOS)
    ImageDraw.Draw(pill).text((30, (h - size) / 2 - size * 0.08), text, font=f, fill=fg)
    if emoji:
        e = emoji_img(emoji, es)
        pill.alpha_composite(e, (30 + tw + 16, (h - e.height) // 2))
    # drop shadow
    out = Image.new("RGBA", (w + 24, h + 24), (0, 0, 0, 0))
    sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sh.putalpha(pill.getchannel("A").point(lambda v: int(v * 0.45)))
    out.alpha_composite(sh, (14, 14))
    out.alpha_composite(pill, (4, 4))
    return out.rotate(angle, resample=Image.BICUBIC, expand=True)


def _ease_back(x):
    x = max(0.0, min(1.0, x))
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def draw_popups(img, popups, t):
    """img: RGBA or RGB PIL image (modified in place). popups: list of (t0, sprite, cx, cy, dur)."""
    for (t0, spr, cx, cy, dur) in popups:
        a = t - t0
        if a < 0 or a > dur:
            continue
        s = 0.3 + 0.7 * _ease_back(a / 0.22)
        wig = 1 + 0.03 * math.sin(a * 18) * max(0, 1 - a / 0.6)
        op = 1.0 if a < dur - 0.25 else max(0.0, (dur - a) / 0.25)
        sp = spr
        sc = s * wig
        if abs(sc - 1) > 0.01:
            sp = spr.resize((max(1, int(spr.width * sc)), max(1, int(spr.height * sc))), Image.BICUBIC)
        if op < 0.99:
            sp = sp.copy()
            sp.putalpha(sp.getchannel("A").point(lambda v: int(v * op)))
        x0, y0 = int(cx - sp.width / 2), int(cy - sp.height / 2)
        W, H = img.size
        l, tp = max(0, -x0), max(0, -y0)
        r, b = min(sp.width, W - x0), min(sp.height, H - y0)
        if r <= l or b <= tp:
            continue
        crop = sp.crop((l, tp, r, b))
        if img.mode == "RGBA":
            img.alpha_composite(crop, (x0 + l, y0 + tp))
        else:
            img.paste(crop, (x0 + l, y0 + tp), crop)


def boom(sr=44100, d=0.7):
    t = np.arange(int(sr * d)) / sr
    f = 48 + 90 * np.exp(-t / 0.05)
    s = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t / 0.28)
    s += 0.5 * np.sin(4 * np.pi * np.cumsum(f) / sr) * np.exp(-t / 0.12)
    n = np.random.default_rng(7).standard_normal(len(t)) * np.exp(-t / 0.015) * 0.4
    s = np.tanh((s + n) * 2.2)
    return (s * 0.8).astype(np.float32)


def pop(sr=44100):
    t = np.arange(int(sr * 0.08)) / sr
    f = 600 + 900 * (t / 0.08)
    return (np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t / 0.025) * 0.5).astype(np.float32)
