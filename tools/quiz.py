#!/usr/bin/env python3
"""Unreel multiple-choice quiz renderer: JSON spec -> 1080x1920 MP4 (voice, music bed, SFX, animations).

Usage: python3 tools/quiz.py spec.json out.mp4

Spec (see tools/quiz_example.json):
{
  "theme": "violet",                      # preset: violet | ocean | sunset | forest | crimson | midnight
                                          # or {"bg1": "#..", "bg2": "#..", "accent": "#..", "accent2": "#.."}
  "title": "GENERAL KNOWLEDGE",           # small banner shown during the whole video
  "voice": "af_heart", "speed": 1.08,
  "hook": {"title": "ONLY 3% GET 5/5", "sub": "General knowledge - 5 questions", "emoji": "🧠",
           "say": "Only three percent get all five right."},
  "questions": [
    {"q": "What is the capital of Australia?", "say": "What's the capital of Australia?",   # say optional
     "options": ["Sydney", "Canberra", "Melbourne", "Perth"], "answer": 1,                # index into options
     "emoji": "🇦🇺", "level": "EASY", "think": 3,                                        # level/think optional
     "reveal_say": "Canberra! Not Sydney."}                                                # spoken after reveal
  ],
  "outro": {"title": "HOW MANY DID YOU GET?", "say": "How many did you get? Comment your score!",
            "tiers": [["0-2", "🥔", "Potato"], ["3-4", "🧠", "Smart"], ["5", "👑", "Genius"]]}   # optional
}
2-4 options per question (2 = true/false or "which is bigger"). 4-10 questions -> ~30-55 s.
Options may be plain strings or {"t": "Elephant", "e": "🐘"} (emoji shown in the answer row).
"roast": "sydney fans in shambles" (+ optional "react": "💀") = funny sticker after the reveal (+ boom sound).
"trap": <index of the most tempting WRONG option> = 🤡 appears on it at the reveal.
"visual": true on a question = big picture layout (huge emoji/flag/emoji puzzle like "🐝🦵", short question).
Speed round: 8-10 two-option questions with "think": 2.
"""
import json, math, os, random, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fx as fxlib  # noqa: E402  (stickers, boom)

W, H, FPS = 1080, 1920, 30
SR = 44100
HERE = os.path.dirname(os.path.abspath(__file__))
F_BLACK = "/usr/share/fonts/opentype/inter/InterDisplay-Black.otf"
F_XB = "/usr/share/fonts/opentype/inter/InterDisplay-ExtraBold.otf"
F_BOLD = "/usr/share/fonts/opentype/inter/InterDisplay-Bold.otf"
F_EMOJI = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"

CX = 535                     # content centre (slightly left: right edge has the like/comment buttons)
CW = 880                     # content width
GREEN = (34, 197, 94)
RED = (239, 68, 68)
WHITE = (255, 255, 255)
INK = (20, 20, 28)

THEMES = {
    "violet":   {"bg1": "#2A0E61", "bg2": "#0B0620", "accent": "#FFD23F", "accent2": "#A855F7"},
    "ocean":    {"bg1": "#063A5B", "bg2": "#020B18", "accent": "#3EE6FF", "accent2": "#2563EB"},
    "sunset":   {"bg1": "#5B1238", "bg2": "#12051A", "accent": "#FF9F1C", "accent2": "#F43F5E"},
    "forest":   {"bg1": "#0B4031", "bg2": "#03120D", "accent": "#B6FF3B", "accent2": "#10B981"},
    "crimson":  {"bg1": "#5A0A12", "bg2": "#140306", "accent": "#FFE14D", "accent2": "#EF4444"},
    "midnight": {"bg1": "#151B3D", "bg2": "#05060F", "accent": "#7CFFCB", "accent2": "#6366F1"},
}
LEVEL_COLORS = {"EASY": (34, 197, 94), "MEDIUM": (250, 204, 21), "HARD": (249, 115, 22),
                "EXPERT": (239, 68, 68), "IMPOSSIBLE": (217, 70, 239), "BONUS": (56, 189, 248)}

_fc = {}


def font(path, size):
    k = (path, int(size))
    if k not in _fc:
        _fc[k] = ImageFont.truetype(path, int(size))
    return _fc[k]


def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def opt_text(o):
    return o if isinstance(o, str) else o.get("t", "")


def opt_emoji(o):
    return None if isinstance(o, str) else o.get("e")


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out_back(x):
    x = clamp(x)
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def ease_out_cubic(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def wrap(text, f, maxw):
    d = ImageDraw.Draw(Image.new("L", (4, 4)))
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def fit(text, path, maxw, maxh, start, minsize=34, lh=1.12):
    d = ImageDraw.Draw(Image.new("L", (4, 4)))
    size = start
    while size >= minsize:
        f = font(path, size)
        lines = wrap(text, f, maxw)
        if max(d.textlength(l, font=f) for l in lines) <= maxw and len(lines) * size * lh <= maxh:
            return lines, f, size
        size -= 2
    f = font(path, minsize)
    return wrap(text, f, maxw), f, minsize


# ------------------------------------------------------------------ sprites
def rrect(w, h, r, fill, outline=None, width=0, ss=3):
    """Anti-aliased rounded rectangle sprite (drawn at ss x and downsampled)."""
    im = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), radius=r * ss, fill=fill,
                        outline=outline, width=width * ss)
    return im.resize((w, h), Image.LANCZOS)


def circle(d_, fill, outline=None, width=0, ss=3):
    im = Image.new("RGBA", (d_ * ss, d_ * ss), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((0, 0, d_ * ss - 1, d_ * ss - 1), fill=fill, outline=outline, width=width * ss)
    return im.resize((d_, d_), Image.LANCZOS)


def shadow_of(sprite, blur=22, alpha=0.55, grow=0):
    a = sprite.getchannel("A")
    pad = blur * 3
    big = Image.new("L", (sprite.width + 2 * pad, sprite.height + 2 * pad), 0)
    big.paste(a, (pad, pad))
    big = big.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: int(v * alpha))
    sh = Image.new("RGBA", big.size, (0, 0, 0, 255))
    sh.putalpha(big)
    return sh, pad


def emoji_sprite(e, size):
    k = ("emoji", e, size)
    if k not in _fc:
        ef = ImageFont.truetype(F_EMOJI, 109)
        im = Image.new("RGBA", (420, 180), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((10, 10), e, font=ef, embedded_color=True)
        bb = im.getbbox()
        im = im.crop(bb) if bb else im
        s = size / max(im.width, im.height)
        _fc[k] = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
    return _fc[k]


def paste(base, sprite, x, y, opacity=1.0):
    """alpha_composite with clipping and opacity; x, y = top-left (floats ok)."""
    x, y = int(round(x)), int(round(y))
    if opacity <= 0.01:
        return
    if opacity < 0.99:
        sprite = sprite.copy()
        sprite.putalpha(sprite.getchannel("A").point(lambda v: int(v * opacity)))
    l, t = max(0, -x), max(0, -y)
    r, b = min(sprite.width, W - x), min(sprite.height, H - y)
    if r <= l or b <= t:
        return
    if (l, t, r, b) != (0, 0, sprite.width, sprite.height):
        sprite = sprite.crop((l, t, r, b))
    base.alpha_composite(sprite, (x + l, y + t))


def paste_c(base, sprite, cx, cy, scale=1.0, opacity=1.0):
    if scale <= 0.02:
        return
    if abs(scale - 1) > 0.01:
        sprite = sprite.resize((max(1, int(sprite.width * scale)), max(1, int(sprite.height * scale))), Image.BICUBIC)
    paste(base, sprite, cx - sprite.width / 2, cy - sprite.height / 2, opacity)


def text_sprite(lines, f, size, fill, lh=1.12, align="center", stroke=0, stroke_fill=(0, 0, 0), maxw=None):
    d = ImageDraw.Draw(Image.new("L", (4, 4)))
    wmax = int(max(d.textlength(l, font=f) for l in lines)) + 2 * stroke + 8
    if maxw:
        wmax = max(wmax, maxw)
    h = int(len(lines) * size * lh + size * 0.35 + 2 * stroke)
    im = Image.new("RGBA", (wmax, h), (0, 0, 0, 0))
    dd = ImageDraw.Draw(im)
    y = stroke
    for l in lines:
        tw = dd.textlength(l, font=f)
        x = (wmax - tw) / 2 if align == "center" else stroke + 4
        dd.text((x, y), l, font=f, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
        y += size * lh
    return im


# ------------------------------------------------------------------ audio
def resample(x, sr_in, sr_out):
    from scipy.signal import resample_poly
    g = math.gcd(sr_in, sr_out)
    return resample_poly(x, sr_out // g, sr_in // g).astype(np.float32)


def tts_all(texts, voice, speed):
    from kokoro_onnx import Kokoro
    k = Kokoro(os.path.join(HERE, "models/kokoro.onnx"), os.path.join(HERE, "models/voices.bin"))
    out = []
    for t in texts:
        if not t:
            out.append(np.zeros(1, dtype=np.float32))
            continue
        s, sr = k.create(t, voice=voice, speed=speed, lang="en-us")
        s = np.asarray(s, dtype=np.float32)
        nz = np.where(np.abs(s) > 0.01)[0]
        if len(nz):
            s = s[max(nz[0] - 200, 0): nz[-1] + 1500]
        out.append(resample(s, sr, SR))
    return out


def _t(d):
    return np.arange(int(SR * d)) / SR


def sfx_pop():
    t = _t(0.09)
    f = 520 + 700 * (t / 0.09)
    return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.03) * 0.5).astype(np.float32)


def sfx_tick(hi=True):
    t = _t(0.05)
    f = 2200 if hi else 1650
    noise = np.random.default_rng(5).standard_normal(len(t)) * np.exp(-t / 0.003) * 0.3
    return ((np.sin(2 * np.pi * f * t) * np.exp(-t / 0.012) + noise) * 0.45).astype(np.float32)


def bell(f, d=0.9):
    t = _t(d)
    s = sum(a * np.sin(2 * np.pi * f * m * t) * np.exp(-t / (dec)) for m, a, dec in
            ((1, 1.0, 0.35), (2.0, 0.45, 0.2), (3.0, 0.2, 0.12), (4.2, 0.12, 0.08)))
    return (s * np.minimum(1, t / 0.002)).astype(np.float32)


def sfx_correct():
    a, b = bell(1046.5), bell(1568.0)
    out = np.zeros(int(SR * 1.1), dtype=np.float32)
    out[:len(a)] += a * 0.35
    p = int(SR * 0.09)
    out[p:p + len(b)] += b[:len(out) - p] * 0.4
    return out


def sfx_whoosh(d=0.32):
    n = int(SR * d)
    noise = np.random.default_rng(1).standard_normal(n).astype(np.float32)
    from scipy.signal import lfilter
    out = np.zeros(n, dtype=np.float32)
    seg = n // 16
    for i in range(16):  # rising band
        a = 0.03 + 0.4 * (i / 16)
        y = lfilter([a], [1, -(1 - a)], noise[i * seg:(i + 1) * seg])
        out[i * seg:(i + 1) * seg] = y
    e = np.sin(np.pi * np.arange(n) / n) ** 2
    return (out * e * 0.9).astype(np.float32)


def sfx_tada():
    out = np.zeros(int(SR * 1.6), dtype=np.float32)
    for i, f in enumerate((523.3, 659.3, 784.0, 1046.5)):
        b = bell(f, 1.2) * 0.25
        p = int(SR * 0.07 * i)
        out[p:p + len(b)] += b[:len(out) - p]
    return out


def music_bed(total, seed=0):
    """Light upbeat loop: kick, offbeat hats, soft clap, bass and plucked chord arpeggios (Am F C G)."""
    from scipy.signal import lfilter
    rng = np.random.default_rng(seed)
    n = int(SR * total) + SR
    out = np.zeros(n, dtype=np.float32)
    bpm = 112
    beat = 60 / bpm
    prog = [(57, [69, 72, 76]), (53, [65, 69, 72]), (48, [67, 72, 76]), (55, [67, 71, 74])]  # midi
    mf = lambda m: 440 * 2 ** ((m - 69) / 12)

    def add(sig, at, g):
        p = int(at * SR)
        if p >= n:
            return
        s = sig[:n - p]
        out[p:p + len(s)] += s * g

    tk = _t(0.3)
    kick = np.sin(2 * np.pi * np.cumsum(48 + 110 * np.exp(-tk / 0.025)) / SR) * np.exp(-tk / 0.13)
    th = _t(0.05)
    hat = lfilter([1, -1], [1], rng.standard_normal(len(th))) * np.exp(-th / 0.01) * 0.25
    tc = _t(0.18)
    clap = lfilter([0.5], [1, -0.5], rng.standard_normal(len(tc))) * np.exp(-tc / 0.04) * 0.35
    nbeats = int(total / beat) + 2
    for i in range(nbeats):
        t0 = i * beat
        bar = (i // 4) % 4
        root, chord = prog[bar]
        add(kick, t0, 0.55)
        add(hat, t0 + beat / 2, 0.5)
        if i % 4 in (1, 3):
            add(clap, t0, 0.45)
        # bass on every beat
        tb = _t(beat * 0.9)
        fb = mf(root - 12)
        bass = (np.sin(2 * np.pi * fb * tb) + 0.3 * np.sin(4 * np.pi * fb * tb)) * np.exp(-tb / 0.35) * np.minimum(1, tb / 0.01)
        add(bass, t0, 0.35)
        # pluck arpeggio, 8th notes
        for j in range(2):
            m = chord[(i * 2 + j) % 3] + (12 if (i * 2 + j) % 6 >= 3 else 0)
            tp = _t(0.32)
            f = mf(m)
            pl = (np.sin(2 * np.pi * f * tp) + 0.25 * np.sin(4 * np.pi * f * tp)) * np.exp(-tp / 0.12) * np.minimum(1, tp / 0.004)
            add(pl, t0 + j * beat / 2, 0.12)
    return out[:int(SR * total)]


# ------------------------------------------------------------------ main
def render(spec, out):
    th = spec.get("theme", "violet")
    th = dict(THEMES.get(th, THEMES["violet"])) if isinstance(th, str) else {**THEMES["violet"], **th}
    bg1, bg2 = hex2rgb(th["bg1"]), hex2rgb(th["bg2"])
    accent, accent2 = hex2rgb(th["accent"]), hex2rgb(th["accent2"])
    voice, speed = spec.get("voice", "af_heart"), spec.get("speed", 1.08)
    qs = spec["questions"]
    nq = len(qs)
    hook = spec.get("hook", {})
    outro = spec.get("outro", {})
    lo = max(1, (nq - 1) // 2)
    mid = f"{lo + 1}" if lo + 1 == nq - 1 else f"{lo + 1}-{nq - 1}"
    tiers = outro.get("tiers") or [[f"0-{lo}", "🥔", "Potato"], [mid, "🧠", "Smart"],
                                   [f"{nq}/{nq}", "👑", "Genius"]]

    # ---------------- voice
    texts = [hook.get("say", hook.get("title", ""))]
    for q in qs:
        texts += [q.get("say", q["q"]), q.get("reveal_say", opt_text(q["options"][q["answer"]]) + "!")]
    texts.append(outro.get("say", "How many did you get? Comment your score!"))
    vo = tts_all(texts, voice, speed)
    dur = lambda a: len(a) / SR

    # ---------------- timeline
    tl = []
    t = 0.0
    hook_d = max(dur(vo[0]) + 0.25, 1.8)
    tl.append(dict(kind="hook", start=t, dur=hook_d, voice=vo[0]))
    t += hook_d
    for i, q in enumerate(qs):
        ask_v, rev_v = vo[1 + 2 * i], vo[2 + 2 * i]
        n_opt = len(q["options"])
        ask = max(dur(ask_v) + 0.25, 0.45 + 0.13 * n_opt + 0.5)
        think = float(q.get("think", 3))
        rev = max(dur(rev_v) + 0.45, 2.5 if q.get("roast") else 1.5)
        tl.append(dict(kind="q", i=i, q=q, start=t, ask=ask, think=think, rev=rev, dur=ask + think + rev,
                       voice=ask_v, rvoice=rev_v))
        t += ask + think + rev
    out_d = max(dur(vo[-1]) + 1.3, 3.2)
    tl.append(dict(kind="outro", start=t, dur=out_d, voice=vo[-1]))
    total = t + out_d

    # ---------------- audio mix
    n = int(SR * (total + 0.2))
    voice_tr = np.zeros(n, dtype=np.float32)
    fx = np.zeros(n, dtype=np.float32)

    def add(buf, clip, at, g=1.0):
        p = int(at * SR)
        if p >= n:
            return
        c = clip[:n - p]
        buf[p:p + len(c)] += c * g

    fx_tr = fx
    boomsnd = fxlib.boom(SR)
    pop, tick_hi, tick_lo, correct, whoosh, tada = sfx_pop(), sfx_tick(True), sfx_tick(False), sfx_correct(), sfx_whoosh(), sfx_tada()
    for seg in tl:
        add(voice_tr, seg["voice"], seg["start"] + (0.05 if seg["kind"] != "hook" else 0.0))
        if seg["start"] > 0:
            add(fx, whoosh, max(0, seg["start"] - 0.12), 0.5)
        if seg["kind"] == "q":
            for k in range(len(seg["q"]["options"])):
                add(fx, pop, seg["start"] + 0.45 + 0.13 * k, 0.55)
            t0 = seg["start"] + seg["ask"]
            steps = int(seg["think"] * 2)
            for k in range(steps):
                add(fx, tick_hi if k % 2 == 0 else tick_lo, t0 + k * 0.5, 0.7 if k % 2 == 0 else 0.5)
            tr = t0 + seg["think"]
            add(fx, correct, tr, 0.8)
            add(voice_tr, seg["rvoice"], tr + 0.3)
            if seg["q"].get("roast"):
                add(fx_tr, boomsnd, tr + 0.55, 0.55)
        if seg["kind"] == "outro":
            add(fx, tada, seg["start"] + 0.1, 0.6)
    bed = np.zeros(n, dtype=np.float32)
    mb = music_bed(total + 0.2)
    bed[:len(mb)] = mb[:n]
    # duck music under voice (smoothed envelope)
    env = np.abs(voice_tr)
    k = int(SR * 0.08)
    env = np.convolve(env, np.ones(k) / k, mode="same")
    env = np.clip(env / (env.max() + 1e-6) * 4, 0, 1)
    bed *= (1 - 0.55 * env)
    fade = np.ones(n, dtype=np.float32)
    fl = int(SR * 0.8)
    fade[-fl:] = np.linspace(1, 0, fl)
    mix = voice_tr * 1.0 + fx * 0.6 + bed * 0.22 * fade
    mix = np.tanh(mix * 1.1) / np.tanh(1.1)
    mix = mix / (np.max(np.abs(mix)) + 1e-6) * 0.93
    wav = out + ".wav"
    import soundfile as sf
    sf.write(wav, mix, SR)

    # ---------------- static visuals
    yy = np.linspace(0, 1, H)[:, None]
    xx = np.linspace(0, 1, W)[None, :]
    g = np.clip(yy * 0.85 + xx * 0.15, 0, 1)[..., None]
    base = (np.array(bg1)[None, None, :] * (1 - g) + np.array(bg2)[None, None, :] * g)
    grain = np.random.default_rng(3).normal(0, 3.0, (H, W, 1))
    base = np.clip(base + grain, 0, 255).astype(np.uint8)
    base = Image.fromarray(base, "RGB").convert("RGBA")
    # subtle dotted pattern
    dots = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(dots)
    for y in range(40, H, 60):
        for x in range(40 + (30 if (y // 60) % 2 else 0), W, 60):
            dd.ellipse((x - 2, y - 2, x + 2, y + 2), fill=(255, 255, 255, 14))
    base.alpha_composite(dots)

    def blob(col, r, a):
        yy_, xx_ = np.mgrid[-r:r, -r:r]
        d = np.sqrt(xx_ ** 2 + yy_ ** 2) / r
        al = (np.clip(1 - d, 0, 1) ** 2.2 * a * 255).astype(np.uint8)
        im = Image.new("RGBA", (2 * r, 2 * r), col + (0,))
        im.putalpha(Image.fromarray(al, "L"))
        return im

    blobs = [(blob(accent2, 520, 0.45), 0.13, 0.0, 200, 520), (blob(accent, 420, 0.22), 0.09, 2.0, 820, 1350),
             (blob(accent2, 380, 0.30), 0.11, 4.0, 300, 1650)]
    prng = random.Random(11)
    parts = [(prng.uniform(0, W), prng.uniform(0, H), prng.uniform(18, 55), prng.uniform(2, 5), prng.uniform(0.3, 1))
             for _ in range(34)]

    # header pieces
    title_txt = spec.get("title", "GENERAL KNOWLEDGE").upper()
    tl_lines, tf, ts = fit(title_txt, F_BLACK, 760, 60, 50, 30)
    title_spr = text_sprite(tl_lines, tf, ts, accent + (255,))
    wm = text_sprite(["unreel"], font(F_BLACK, 38), 38, (255, 255, 255, 200))

    def chip(text, col, fg=INK, size=40):
        f = font(F_BLACK, size)
        tw = int(ImageDraw.Draw(Image.new("L", (4, 4))).textlength(text, font=f))
        h = size + 30
        im = rrect(tw + 56, h, h // 2, col + (255,))
        ImageDraw.Draw(im).text((28, 12), text, font=f, fill=fg)
        return im

    # per-question sprites
    CARD_W, CARD_H, CARD_Y = CW, 270, 690
    ROW_W = CW
    qspr = []
    for i, q in enumerate(qs):
        vis = bool(q.get("visual"))           # big picture question (flags, emoji puzzles, "what is this?")
        CARD_H, CARD_Y = (170, 790) if vis else (270, 690)
        q_ry, q_rr, q_em = (612, 150, 250) if vis else (575, 112, 170)
        card = rrect(CARD_W, CARD_H, 42, (255, 255, 255, 255))
        lines, f, s = fit(q["q"], F_XB, CARD_W - 110, CARD_H - 56, 66 if not vis else 58, 38, 1.12)
        txt = text_sprite(lines, f, s, INK + (255,), 1.12)
        card.alpha_composite(txt, ((CARD_W - txt.width) // 2, (CARD_H - txt.height) // 2 + 6))
        card_sh, card_pad = shadow_of(card, 26, 0.6)
        n_opt = len(q["options"])
        row_h = 112 if n_opt > 2 else 130
        gap = 20
        rows = []
        for k, o in enumerate(q["options"]):
            letter = "ABCD"[k]
            states = {}
            for st in ("normal", "correct", "dim"):
                if st == "correct":
                    im = rrect(ROW_W, row_h, row_h // 2 - 6, GREEN + (255,), (255, 255, 255, 255), 4)
                    lc = circle(row_h - 30, (255, 255, 255, 255))
                    lcol = GREEN
                else:
                    im = rrect(ROW_W, row_h, row_h // 2 - 6, (255, 255, 255, 34), (255, 255, 255, 70), 3)
                    lc = circle(row_h - 30, accent + (255,))
                    lcol = INK
                im.alpha_composite(lc, (15, 15))
                dr = ImageDraw.Draw(im)
                lf = font(F_BLACK, int(row_h * 0.42))
                if st == "correct":
                    # check mark
                    cx_, cy_, r_ = 15 + (row_h - 30) / 2, row_h / 2, (row_h - 30) / 2
                    dr.line([(cx_ - r_ * 0.42, cy_ + r_ * 0.02), (cx_ - r_ * 0.1, cy_ + r_ * 0.33),
                             (cx_ + r_ * 0.45, cy_ - r_ * 0.32)], fill=GREEN, width=int(r_ * 0.22), joint="curve")
                else:
                    lw = dr.textlength(letter, font=lf)
                    dr.text((15 + (row_h - 30 - lw) / 2, row_h / 2 - row_h * 0.27), letter, font=lf, fill=lcol)
                tx = row_h + 8
                if opt_emoji(o):
                    es = emoji_sprite(opt_emoji(o), int(row_h * 0.62))
                    im.alpha_composite(es, (tx + 4, (row_h - es.height) // 2))
                    tx += es.width + 22
                ol, of, os_ = fit(opt_text(o), F_XB, ROW_W - tx - 60, row_h - 20, 58, 32, 1.05)
                ot = text_sprite(ol, of, os_, WHITE + (255,), 1.05, align="left")
                im.alpha_composite(ot, (tx, int((row_h - ot.height) / 2 + 4)))
                if st == "dim":
                    im.putalpha(im.getchannel("A").point(lambda v: int(v * 0.32)))
                states[st] = im
            rows.append(states)
        area_top = CARD_Y + CARD_H + 44
        area_h = 4 * 112 + 3 * 20
        used = n_opt * row_h + (n_opt - 1) * gap
        y0 = area_top + (area_h - used) / 2
        lvl = q.get("level", "").upper()
        lvl_col = LEVEL_COLORS.get(lvl, accent)
        chip_txt = f"QUESTION {i + 1}/{nq}" + (f"  ·  {lvl}" if lvl else "")
        qspr.append(dict(card=card, card_sh=card_sh, card_pad=card_pad, rows=rows, row_h=row_h, gap=gap, y0=y0,
                         card_y=CARD_Y, ry=q_ry, rr=q_rr,
                         chip=chip(chip_txt, lvl_col), emoji=emoji_sprite(q.get("emoji", "❓"), q_em),
                         roast=fxlib.sticker(q["roast"].upper(), q.get("react", "💀"), size=62, angle=-4, maxw=960)
                         if q.get("roast") else None,
                         trap=q.get("trap")))

    # hook sprites
    hk_lines, hk_f, hk_s = fit(hook.get("title", "ONLY 3% GET 5/5").upper(), F_BLACK, CW, 520, 150, 70, 1.02)
    hook_txt = text_sprite(hk_lines, hk_f, hk_s, WHITE + (255,), 1.02, stroke=0)
    hook_sh, hook_pad = shadow_of(hook_txt, 18, 0.8)
    hs_lines, hs_f, hs_s = fit(hook.get("sub", f"{nq} questions · no googling").upper(), F_XB, CW, 140, 54, 30)
    hook_sub = text_sprite(hs_lines, hs_f, hs_s, accent + (255,))
    hook_emoji = emoji_sprite(hook.get("emoji", "🧠"), 240)

    # outro sprites
    ot_lines, ot_f, ot_s = fit(outro.get("title", "HOW MANY DID YOU GET?").upper(), F_BLACK, CW, 330, 112, 60, 1.03)
    out_txt = text_sprite(ot_lines, ot_f, ot_s, WHITE + (255,), 1.03)
    out_sh, out_pad = shadow_of(out_txt, 18, 0.8)
    tier_spr = []
    for k, (rng_, em, lab) in enumerate(tiers):
        im = rrect(CW, 128, 40, (255, 255, 255, 30), (255, 255, 255, 60), 3)
        dr = ImageDraw.Draw(im)
        dr.text((40, 30), rng_, font=font(F_BLACK, 62), fill=accent)
        e = emoji_sprite(em, 84)
        im.alpha_composite(e, (300, (128 - e.height) // 2))
        lsz = 56
        while lsz > 30 and dr.textlength(lab.upper(), font=font(F_BLACK, lsz)) > CW - 450:
            lsz -= 2
        dr.text((420, (128 - lsz) / 2 - 4), lab.upper(), font=font(F_BLACK, lsz), fill=WHITE)
        tier_spr.append(im)
    cta = chip("COMMENT YOUR SCORE 👇".replace(" 👇", ""), accent, INK, 44)
    point = emoji_sprite("👇", 90)
    check_big = emoji_sprite("✅", 150)
    clown = emoji_sprite("🤡", 80)

    # confetti generator
    def confetti(seed, cx, cy):
        r = random.Random(seed)
        cols = [accent, accent2, GREEN, (255, 255, 255), (56, 189, 248), (244, 63, 94)]
        return [(cx + r.uniform(-300, 300), cy + r.uniform(-20, 20), r.uniform(-650, 650), r.uniform(-1500, -500),
                 r.uniform(10, 20), r.uniform(0, 6.28), r.uniform(-12, 12), r.choice(cols)) for _ in range(70)]

    # ---------------- frames
    nframes = int(math.ceil(total * FPS))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "medium", "-crf", "18",
           "-pix_fmt", "yuv420p", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "44100", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    conf_cache = {}
    for fi in range(nframes):
        t = fi / FPS
        seg = max((s for s in tl if s["start"] <= t + 1e-9), key=lambda s: s["start"])
        lt = t - seg["start"]
        fr = base.copy()
        # moving glow blobs
        for spr, sp, ph, bx, by in blobs:
            x = bx + 140 * math.sin(t * sp * 2 * math.pi * 0.5 + ph)
            y = by + 110 * math.cos(t * sp * 2 * math.pi * 0.4 + ph)
            paste(fr, spr, x - spr.width / 2, y - spr.height / 2)
        d = ImageDraw.Draw(fr)
        for (px, py, spd, pr, pa) in parts:
            y = (py - t * spd) % H
            x = px + 12 * math.sin(t * 0.8 + py)
            d.ellipse((x - pr, y - pr, x + pr, y + pr), fill=(255, 255, 255, int(40 * pa)))

        # header: wordmark + title + progress
        paste(fr, wm, 70, 178, 1.0)
        paste_c(fr, title_spr, CX, 290)
        qi_now = seg["i"] if seg["kind"] == "q" else (-1 if seg["kind"] == "hook" else nq)
        seg_w = (CW - (nq - 1) * 12) / nq
        for k in range(nq):
            x0 = CX - CW / 2 + k * (seg_w + 12)
            if k < qi_now or (k == qi_now and seg["kind"] == "q" and lt >= seg["ask"] + seg["think"]):
                col = accent + (255,)
            elif k == qi_now:
                col = accent + (int(110 + 80 * math.sin(t * 8)),)
            else:
                col = (255, 255, 255, 50)
            d.rounded_rectangle((x0, 345, x0 + seg_w, 357), radius=6, fill=col)

        if seg["kind"] == "hook":
            s = 1.0 if fi == 0 else 0.9 + 0.1 * ease_out_back(lt / 0.35)
            pulse = 1 + 0.02 * math.sin(lt * 7)
            paste_c(fr, hook_emoji, CX, 620 + 10 * math.sin(lt * 4), s)
            paste_c(fr, hook_sh, CX + 6, 1010 + 10, s * pulse)
            paste_c(fr, hook_txt, CX, 1010, s * pulse)
            paste_c(fr, hook_sub, CX, 1010 + hook_txt.height / 2 + 90, 1.0, clamp(lt / 0.3) if fi else 1)
        elif seg["kind"] == "q":
            sp = qspr[seg["i"]]
            ask, think = seg["ask"], seg["think"]
            phase_t = lt - ask           # <0 asking, 0..think countdown, >think reveal
            rev_t = lt - ask - think
            # chip
            paste_c(fr, sp["chip"], CX, 435, 0.6 + 0.4 * ease_out_back(lt / 0.3))
            # emoji / timer ring
            ry, rr = sp["ry"], sp["rr"]
            ring = Image.new("RGBA", (2 * rr + 40, 2 * rr + 40), (0, 0, 0, 0))
            rd = ImageDraw.Draw(ring)
            box = (20, 20, 20 + 2 * rr, 20 + 2 * rr)
            rd.ellipse(box, fill=(255, 255, 255, 22), outline=(255, 255, 255, 45), width=14)
            if phase_t < 0:
                frac = 1.0
                rcol = accent
            elif rev_t < 0:
                frac = 1 - phase_t / think
                rcol = (int(255 * min(1, 2 * (1 - frac))), int(220 * min(1, 2 * frac)), 60)
            else:
                frac, rcol = 1.0, GREEN
            if frac > 0.002:
                rd.arc(box, -90, -90 + 360 * frac, fill=rcol + (255,), width=14)
            ring_s = 0.5 + 0.5 * ease_out_back(lt / 0.35)
            paste_c(fr, ring, CX, ry, ring_s)
            if phase_t < 0:
                paste_c(fr, sp["emoji"], CX, ry + 6 * math.sin(lt * 5), ring_s)
            elif rev_t < 0:
                num = int(math.ceil(think - phase_t))
                st = (think - phase_t) - (num - 1)  # 1 -> 0 within the second
                key = ("num", num, rcol)
                if key not in conf_cache:
                    conf_cache[key] = text_sprite([str(num)], font(F_BLACK, 150), 150, rcol + (255,))
                ns = 1.0 + 0.35 * clamp((st - 0.75) / 0.25)
                paste_c(fr, conf_cache[key], CX, ry + 4, ns)
            else:
                paste_c(fr, check_big, CX, ry, 0.4 + 0.6 * ease_out_back(rev_t / 0.3))
            # card
            ce = ease_out_cubic(lt / 0.35)
            cy_off = 60 * (1 - ce)
            paste(fr, sp["card_sh"], CX - CARD_W / 2 - sp["card_pad"], sp["card_y"] - sp["card_pad"] + 14 + cy_off, ce)
            paste(fr, sp["card"], CX - CARD_W / 2, sp["card_y"] + cy_off, ce)
            # options
            ans = seg["q"]["answer"]
            for k, states in enumerate(sp["rows"]):
                at = lt - (0.45 + 0.13 * k)
                if at < 0:
                    continue
                e = ease_out_back(at / 0.32)
                x = CX - ROW_W / 2 + 260 * (1 - e)
                y = sp["y0"] + k * (sp["row_h"] + sp["gap"])
                op = clamp(at / 0.15)
                if rev_t >= 0:
                    if k == ans:
                        pul = 1 + 0.06 * math.sin(clamp(rev_t / 0.35) * math.pi)
                        paste_c(fr, states["correct"], CX, y + sp["row_h"] / 2, pul)
                    else:
                        mix_ = clamp(rev_t / 0.2)
                        paste(fr, states["normal"], x, y, 1 - mix_)
                        paste(fr, states["dim"], x, y, mix_)
                else:
                    paste(fr, states["normal"], x, y, op)
            # confetti on reveal
            if 0 <= rev_t < 1.4:
                y_ans = sp["y0"] + ans * (sp["row_h"] + sp["gap"]) + sp["row_h"] / 2
                pts = conf_cache.setdefault(("c", seg["i"]), confetti(seg["i"] + 7, CX, y_ans))
                d = ImageDraw.Draw(fr)
                for (x0, y0, vx, vy, sz, a0, av, col) in pts:
                    x = x0 + vx * rev_t
                    y = y0 + vy * rev_t + 0.5 * 2600 * rev_t ** 2
                    a = a0 + av * rev_t
                    w2, h2 = sz / 2, sz / 4
                    ca, sa = math.cos(a), math.sin(a)
                    poly = [(x + ca * dx - sa * dy, y + sa * dx + ca * dy) for dx, dy in ((-w2, -h2), (w2, -h2), (w2, h2), (-w2, h2))]
                    d.polygon(poly, fill=col + (int(255 * clamp(1.4 - rev_t)),))
            # funny bits: clown on the trap option, roast sticker over the card
            if rev_t >= 0.3 and sp["trap"] is not None and sp["trap"] != ans and sp["trap"] < len(sp["rows"]):
                yk = sp["y0"] + sp["trap"] * (sp["row_h"] + sp["gap"]) + sp["row_h"] / 2
                paste_c(fr, clown, CX + ROW_W / 2 - 70, yk, 0.4 + 0.6 * ease_out_back((rev_t - 0.3) / 0.25))
            if sp["roast"] is not None:
                fxlib.draw_popups(fr, [(0.55, sp["roast"], CX, sp["card_y"] + sp["card"].height - 6, seg["rev"] - 0.55)], rev_t)
            # reveal flash
            if 0 <= rev_t < 0.12:
                fl = Image.new("RGBA", (W, H), (255, 255, 255, int(70 * (1 - rev_t / 0.12))))
                fr.alpha_composite(fl)
        else:  # outro
            s = 0.85 + 0.15 * ease_out_back(lt / 0.35)
            paste_c(fr, out_sh, CX + 6, 560 + 10, s)
            paste_c(fr, out_txt, CX, 560, s)
            for k, ts_ in enumerate(tier_spr):
                at = lt - (0.35 + 0.18 * k)
                if at < 0:
                    continue
                e = ease_out_back(at / 0.3)
                paste(fr, ts_, CX - CW / 2 + 300 * (1 - e), 790 + k * 152, clamp(at / 0.15))
            at = lt - 1.0
            if at > 0:
                cs = 0.5 + 0.5 * ease_out_back(at / 0.3)
                cy_ = 1290
                paste_c(fr, cta, CX - 50, cy_, cs * (1 + 0.03 * math.sin(lt * 6)))
                paste_c(fr, point, CX + cta.width / 2 + 10, cy_ + 8 * math.sin(lt * 7), cs)

        ff.stdin.write(fr.convert("RGB").tobytes())
    ff.stdin.close()
    ff.wait()
    os.remove(wav)
    return total


if __name__ == "__main__":
    spec = json.load(open(sys.argv[1]))
    d = render(spec, sys.argv[2])
    print(f"done {sys.argv[2]} {d:.1f}s")
