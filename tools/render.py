#!/usr/bin/env python3
"""Unreel short renderer: JSON spec -> 1080x1920 MP4 with voice, word captions, SFX.

Usage: python3 render.py spec.json out.mp4
Spec: {"voice": "af_heart", "speed": 1.08, "accent": "#E8FF3A", "accent2": "#FF3B6B",
       "scenes": [{"type": hook|question|reveal|fact|twist|outro, "title": str,
                   "sub": str?, "label": str?, "say": str, "think": float?}]}
"""
import json, math, os, subprocess, sys, random
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS, SR = 1080, 1920, 30, 24000
HERE = os.path.dirname(os.path.abspath(__file__))
F_BLACK = "/usr/share/fonts/opentype/inter/InterDisplay-Black.otf"
F_XB = "/usr/share/fonts/opentype/inter/InterDisplay-ExtraBold.otf"
F_BOLD = "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf"
SAFE_L, SAFE_R = 80, W - 150          # keep clear of right-side UI
SAFE_BOTTOM = int(H * 0.78)            # keep clear of bottom ~20%
_fc = {}


def font(path, size):
    k = (path, size)
    if k not in _fc:
        _fc[k] = ImageFont.truetype(path, size)
    return _fc[k]


def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def wrap(draw, text, fpath, size, maxw):
    f = font(fpath, size)
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=f) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines, f


def fit(draw, text, fpath, maxw, maxh, start, minsize=48, lh=1.05):
    size = start
    while size > minsize:
        lines, f = wrap(draw, text, fpath, size, maxw)
        widest = max(draw.textlength(l, font=f) for l in lines)
        if widest <= maxw and len(lines) * size * lh <= maxh:
            return lines, f, size
        size -= 4
    lines, f = wrap(draw, text, fpath, minsize, maxw)
    return lines, f, minsize


# ---------------------------------------------------------------- audio
def tts(spec):
    from kokoro_onnx import Kokoro
    k = Kokoro(os.path.join(HERE, "models/kokoro.onnx"), os.path.join(HERE, "models/voices.bin"))
    out = []
    for sc in spec["scenes"]:
        s, sr = k.create(sc["say"], voice=spec.get("voice", "af_heart"),
                         speed=spec.get("speed", 1.08), lang="en-us")
        s = np.asarray(s, dtype=np.float32)
        # trim silence
        nz = np.where(np.abs(s) > 0.01)[0]
        s = s[max(nz[0] - 240, 0): nz[-1] + 1200] if len(nz) else s
        out.append(s)
    return out


def env(n, a=0.005, r=None):
    t = np.arange(n) / SR
    e = np.minimum(1, t / max(a, 1e-4))
    if r:
        e *= np.exp(-t / r)
    return e


def sfx_whoosh(d=0.35):
    n = int(SR * d)
    noise = np.random.default_rng(1).standard_normal(n)
    # sweep: moving-average lowpass with shrinking window
    out = np.zeros(n)
    acc = 0.0
    for i in range(n):
        a = 0.02 + 0.5 * (i / n)
        acc += a * (noise[i] - acc)
        out[i] = acc
    e = np.sin(np.pi * np.arange(n) / n) ** 2
    return (out * e * 0.5).astype(np.float32)


def sfx_hit(d=0.5):
    n = int(SR * d)
    t = np.arange(n) / SR
    f = 55 + 90 * np.exp(-t / 0.03)
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.18)
    click = np.random.default_rng(2).standard_normal(n) * np.exp(-t / 0.01) * 0.4
    return ((tone + click) * 0.8).astype(np.float32)


def sfx_tick():
    n = int(SR * 0.06)
    t = np.arange(n) / SR
    return (np.sin(2 * np.pi * 1400 * t) * np.exp(-t / 0.015) * 0.35).astype(np.float32)


def bed(total):
    n = int(SR * total)
    out = np.zeros(n, dtype=np.float32)
    beat = 0.5
    kn = int(SR * 0.25)
    t = np.arange(kn) / SR
    kick = np.sin(2 * np.pi * np.cumsum(45 + 70 * np.exp(-t / 0.02)) / SR) * np.exp(-t / 0.12)
    hat = np.random.default_rng(3).standard_normal(int(SR * 0.04)) * np.exp(-np.arange(int(SR * 0.04)) / SR / 0.008)
    i = 0
    while i * beat < total:
        p = int(i * beat * SR)
        seg = kick[: max(0, min(kn, n - p))]
        out[p:p + len(seg)] += seg * 0.10
        hp = int((i * beat + beat / 2) * SR)
        if hp < n:
            hs = hat[: max(0, min(len(hat), n - hp))]
            out[hp:hp + len(hs)] += hs * 0.025
        i += 1
    return out


# ---------------------------------------------------------------- timeline
def build_timeline(spec, voices):
    t = 0.0
    tl = []
    for sc, v in zip(spec["scenes"], voices):
        speak = len(v) / SR
        think = float(sc.get("think", 0)) if sc["type"] == "question" else 0.0
        pad = 0.25 if sc["type"] != "hook" else 0.15
        dur = speak + think + pad
        words = sc["say"].split()
        weights = np.array([len(w.strip(".,!?\"'")) + 2.5 for w in words], dtype=float)
        cum = np.concatenate([[0], np.cumsum(weights)]) / weights.sum() * speak
        tl.append(dict(sc=sc, start=t, dur=dur, speak=speak, think=think,
                       words=[(words[i], t + cum[i], t + cum[i + 1]) for i in range(len(words))]))
        t += dur
    return tl, t


def mix_audio(tl, voices, total):
    n = int(SR * (total + 0.1))
    vo = np.zeros(n, dtype=np.float32)
    fx = np.zeros(n, dtype=np.float32)
    wh, hit, tick = sfx_whoosh(), sfx_hit(), sfx_tick()

    def add(buf, clip, at):
        p = int(at * SR)
        c = clip[: max(0, min(len(clip), n - p))]
        buf[p:p + len(c)] += c

    for seg, v in zip(tl, voices):
        add(vo, v, seg["start"])
        typ = seg["sc"]["type"]
        if seg["start"] > 0:
            add(fx, wh * 0.6, max(0, seg["start"] - 0.12))
        if typ in ("reveal", "twist"):
            add(fx, hit, seg["start"])
        if typ == "question" and seg["think"] > 0:
            t0 = seg["start"] + seg["speak"]
            k = int(math.ceil(seg["think"]))
            for j in range(k):
                add(fx, tick, t0 + j * seg["think"] / k)
    b = bed(total + 0.1)[:n]
    mix = vo * 1.0 + fx * 0.8 + b
    peak = np.max(np.abs(mix)) or 1
    mix = mix / peak * 0.92
    return mix


# ---------------------------------------------------------------- visuals
def make_bg(accent, accent2):
    img = Image.new("RGB", (W, H), (11, 11, 15))
    d = ImageDraw.Draw(img)
    # soft glows
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    g = ImageDraw.Draw(glow)
    g.ellipse((-300, 200, 700, 1200), fill=tuple(int(c * 0.35) for c in accent2))
    g.ellipse((500, 900, 1500, 1900), fill=tuple(int(c * 0.22) for c in accent))
    glow = glow.filter(ImageFilter.GaussianBlur(220))
    img = Image.blend(img, glow, 0.6)
    # grid lines
    d = ImageDraw.Draw(img)
    for x in range(0, W, 90):
        d.line((x, 0, x, H), fill=(22, 22, 28), width=1)
    for y in range(0, H, 90):
        d.line((0, y, W, y), fill=(22, 22, 28), width=1)
    return img


def ease_out_back(x):
    c1, c3 = 1.70158, 2.70158
    x = min(max(x, 0), 1)
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def draw_text_block(img, lines, f, size, cx, cy, fill, scale=1.0, shadow=(0, 0, 0), lh=1.05, stroke=0):
    """Render lines centered at (cx, cy) with optional scale via separate layer."""
    tmp = Image.new("RGBA", (W, int(len(lines) * size * lh + size)), (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)
    y = 0
    for l in lines:
        tw = td.textlength(l, font=f)
        x = (W - tw) / 2
        td.text((x + 8, y + 10), l, font=f, fill=shadow + (200,))
        td.text((x, y), l, font=f, fill=fill + (255,), stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
        y += size * lh
    if abs(scale - 1) > 1e-3:
        nw, nh = max(1, int(tmp.width * scale)), max(1, int(tmp.height * scale))
        tmp = tmp.resize((nw, nh), Image.BICUBIC)
    img.alpha_composite(tmp, (int(cx - tmp.width / 2), int(cy - tmp.height / 2)))


def pill(img, text, cx, y, bg, fg, size=46):
    d = ImageDraw.Draw(img)
    f = font(F_BLACK, size)
    tw = d.textlength(text, font=f)
    pad = 26
    d.rounded_rectangle((cx - tw / 2 - pad, y, cx + tw / 2 + pad, y + size + 28), radius=40, fill=bg + (255,))
    d.text((cx - tw / 2, y + 10), text, font=f, fill=fg + (255,))


def render(spec, out):
    accent = hex2rgb(spec.get("accent", "#E8FF3A"))
    accent2 = hex2rgb(spec.get("accent2", "#FF3B6B"))
    white, black = (255, 255, 255), (0, 0, 0)
    voices = tts(spec)
    tl, total = build_timeline(spec, voices)
    audio = mix_audio(tl, voices, total)
    wav = out + ".wav"
    import soundfile as sf
    sf.write(wav, audio, SR)

    bg = make_bg(accent, accent2).convert("RGBA")
    cx = (SAFE_L + SAFE_R) / 2 + (W / 2 - (SAFE_L + SAFE_R) / 2) * 0  # text centered on full width
    maxw = SAFE_R - SAFE_L
    measure = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    pre = []
    for seg in tl:
        sc = seg["sc"]
        big = sc["type"] in ("reveal", "hook")
        start = 190 if big else 120
        lines, f, size = fit(measure, sc["title"].upper() if sc["type"] in ("reveal", "hook", "outro") else sc["title"],
                             F_BLACK, maxw, 520 if big else 460, start)
        sub = None
        if sc.get("sub"):
            sl, sf_, ss = fit(measure, sc["sub"].upper() if sc["type"] in ("hook",) else sc["sub"], F_XB, maxw, 260,
                              86 if sc["type"] == "hook" else 60, 36)
            sub = (sl, sf_, ss)
        pre.append((lines, f, size, sub))

    nframes = int(math.ceil(total * FPS))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "medium", "-crf", "19",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-shortest",
           "-movflags", "+faststart", out]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    wm_f = font(F_BLACK, 44)
    cap_f = font(F_BLACK, 74)
    rng = random.Random(7)

    for fi in range(nframes):
        t = fi / FPS
        si = max(i for i, s in enumerate(tl) if s["start"] <= t + 1e-9)
        seg = tl[si]
        sc = seg["sc"]
        lt = t - seg["start"]
        lines, f, size, sub = pre[si]

        # punch-in zoom on background per scene
        z = 1.0 + 0.04 * min(lt / max(seg["dur"], 0.1), 1)
        frame = bg
        if z > 1.001:
            bw, bh = int(W * z), int(H * z)
            frame = bg.resize((bw, bh), Image.BILINEAR).crop(((bw - W) // 2, (bh - H) // 2, (bw - W) // 2 + W, (bh - H) // 2 + H))
        frame = frame.copy()
        d = ImageDraw.Draw(frame)

        typ = sc["type"]
        main_y = 760
        # scene-specific entrance
        if typ == "hook" or fi == 0:
            sc_scale = 1.0 + 0.015 * math.sin(lt * 6)
        else:
            sc_scale = 0.6 + 0.4 * ease_out_back(lt / 0.28)
        if typ == "reveal":
            sc_scale = 1.35 - 0.35 * ease_out_back(lt / 0.22)
        shake = (rng.uniform(-10, 10), rng.uniform(-10, 10)) if typ in ("reveal", "twist") and lt < 0.18 else (0, 0)

        if sc.get("emoji"):
            ek = sc["emoji"]
            if ek not in _fc:
                ef = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", 109)
                el = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
                ImageDraw.Draw(el).text((10, 10), ek, font=ef, embedded_color=True)
                _fc[ek] = el.crop(el.getbbox()).resize((230, 230), Image.LANCZOS)
            em = _fc[ek]
            es = 0.5 + 0.5 * ease_out_back(lt / 0.3) if fi > 0 else 1.0
            em2 = em.resize((max(1, int(230 * es)), max(1, int(230 * es))), Image.BICUBIC)
            bob = 12 * math.sin(lt * 4)
            ey = None if typ == "question" else 1140
            if ey is not None:
                frame.alpha_composite(em2, (int(W / 2 - em2.width / 2), int(ey + bob - em2.height / 2)))
                d = ImageDraw.Draw(frame)
        if typ in ("question", "twist", "fact") and sc.get("label"):
            pill(frame, sc["label"], W / 2, 330, accent if typ != "twist" else accent2, black)
        color = accent if typ in ("reveal",) else white
        if typ == "hook":
            draw_text_block(frame, lines, f, size, W / 2 + shake[0], 640 + shake[1], accent, sc_scale, stroke=0)
            if sub:
                sl, sf_, ss = sub
                draw_text_block(frame, sl, sf_, ss, W / 2, 640 + len(lines) * size * 0.55 + 120, white, 1.0)
        else:
            draw_text_block(frame, lines, f, size, W / 2 + shake[0], main_y + shake[1] - (60 if sub else 0), color, sc_scale)
            if sub and (typ != "reveal" or lt > 0.35):
                sl, sf_, ss = sub
                yy = main_y - (60 if sub else 0) + len(lines) * size * 0.55 + 70 + len(sl) * ss * 0.5
                draw_text_block(frame, sl, sf_, ss, W / 2, yy, (230, 230, 235), 1.0)

        # countdown during think time
        if typ == "question" and seg["think"] > 0 and lt >= seg["speak"]:
            tt = lt - seg["speak"]
            remain = max(seg["think"] - tt, 0)
            num = max(1, int(math.ceil(remain / seg["think"] * 3)))
            frac = remain / seg["think"]
            ccy, r = 1240, 105
            d.ellipse((W / 2 - r, ccy - r, W / 2 + r, ccy + r), outline=(60, 60, 70), width=14)
            d.arc((W / 2 - r, ccy - r, W / 2 + r, ccy + r), -90, -90 + 360 * frac, fill=accent, width=14)
            nf = font(F_BLACK, 120)
            tw = d.textlength(str(num), font=nf)
            d.text((W / 2 - tw / 2, ccy - 78), str(num), font=nf, fill=white)

        # reveal flash
        if typ in ("reveal", "twist") and lt < 0.08:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - lt / 0.08))))
            frame.alpha_composite(fl)
            d = ImageDraw.Draw(frame)

        # word captions (current chunk of up to 3 words), not during think countdown
        cur = [w for w in seg["words"] if w[1] <= t < w[2] + 0.05]
        if cur and not (typ == "question" and lt >= seg["speak"]):
            wi = seg["words"].index(cur[-1])
            c0 = (wi // 3) * 3
            chunk = seg["words"][c0:c0 + 3]
            txt_parts = [w[0].upper() for w in chunk]
            full = " ".join(txt_parts)
            tw = d.textlength(full, font=cap_f)
            scale_cap = min(1.0, maxw / max(tw, 1))
            cf = cap_f if scale_cap >= 1 else font(F_BLACK, int(74 * scale_cap))
            tw = d.textlength(full, font=cf)
            x = W / 2 - tw / 2
            y = SAFE_BOTTOM - 110
            for j, w in enumerate(chunk):
                part = txt_parts[j] + (" " if j < len(chunk) - 1 else "")
                active = (c0 + j) == wi
                col = accent if active else white
                d.text((x, y), txt_parts[j], font=cf, fill=col, stroke_width=8, stroke_fill=(0, 0, 0))
                x += d.textlength(part, font=cf)

        # top: progress bar + wordmark
        d.rounded_rectangle((60, 70, W - 60, 82), radius=6, fill=(40, 40, 48))
        d.rounded_rectangle((60, 70, 60 + (W - 120) * min(t / total, 1), 82), radius=6, fill=accent)
        d.text((60, 108), "unreel", font=wm_f, fill=white)
        d.ellipse((60 + d.textlength("unreel", font=wm_f) + 8, 140, 60 + d.textlength("unreel", font=wm_f) + 22, 154), fill=accent)

        ff.stdin.write(frame.convert("RGB").tobytes())
    ff.stdin.close()
    ff.wait()
    os.remove(wav)
    return total


if __name__ == "__main__":
    spec = json.load(open(sys.argv[1]))
    dur = render(spec, sys.argv[2])
    print(f"done {sys.argv[2]} {dur:.1f}s")
