#!/usr/bin/env python3
"""Unreel satisfying physics shorts (neon look, note per bounce).

Usage: python3 tools/physics.py <mode> out.mp4 [seed] ["HOOK LINE 1|HOOK LINE 2"] [palette] [extra]
Modes:
  escape    - a ball is trapped in 10-16 rotating rings with gaps; every escaped ring shatters.  Hook e.g. "CAN IT|ESCAPE?"
  multiply  - a rotating ring with a gap; every ball that escapes spawns 2 new ones inside.   Hook e.g. "EVERY ESCAPE|= 2 MORE BALLS"
  grow      - see tools/sim_ball.py (ball grows with every bounce)
  battle    - ball vs ball with growing swords and HP bars (tools/arena.py), 6th arg fighters "red,blue" or "🐶,🐱"
  elimination - last ball inside the ring wins (tools/arena.py), 6th arg set: flags|animals|food|fruits|colors
Palettes: neon (default), sunset, ice, candy, lime
The script tries seeds from the given one upward until the video is 15-45 s long and the first escape happens
within 3.5 s (strong hook), and prints the seed used.
"""
import colorsys, math, random, subprocess, sys
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont
import os as _os
sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import fx as fxlib  # noqa: E402  funny stickers + boom

W, H, FPS, SR = 1080, 1920, 30, 44100
SUB = 16
CX, CY = W / 2, 1010
F = "/usr/share/fonts/opentype/inter/InterDisplay-Black.otf"
PALETTES = {"neon": (0.55, 0.12), "sunset": (0.0, 0.05), "ice": (0.5, 0.07), "candy": (0.85, 0.1), "lime": (0.25, 0.08)}
SCALE = [261.6, 293.7, 329.6, 392.0, 440.0, 523.3, 587.3, 659.3, 784.0, 880.0, 1046.5, 1174.7, 1318.5]
MELODY = [0, 2, 4, 5, 4, 2, 3, 5, 7, 6, 4, 5, 7, 8, 9, 7, 8, 10, 9, 7, 5, 4, 2, 4]


def hue_col(h, l=0.6, s=1.0):
    return tuple(int(c * 255) for c in colorsys.hls_to_rgb(h % 1.0, l, s))


# ------------------------------------------------------------------ simulations
def sim_escape(seed):
    rng = random.Random(seed)
    n_rings = rng.randint(10, 16)
    r_in, r_out = 150, 470
    radii = np.linspace(r_in, r_out, n_rings)
    rings = []
    for i, R in enumerate(radii):
        rings.append(dict(R=R, rot=rng.uniform(0, 2 * math.pi), speed=rng.choice([-1, 1]) * rng.uniform(0.7, 1.6),
                          gap=math.radians(rng.uniform(38, 50)), alive=True, t_dead=None))
    g = 1500.0
    pos = np.array([CX + rng.uniform(-30, 30), CY - 40.0])
    vel = np.array([rng.uniform(-400, 400), 0.0])
    r = 16.0
    dt = 1 / (FPS * SUB)
    t, frames, events, end_t = 0.0, [], [], None
    while t < 60:
        for _ in range(SUB):
            vel[1] += g * dt
            pos += vel * dt
            d = pos - (CX, CY)
            dist = math.hypot(*d)
            for ring in rings:
                if not ring["alive"]:
                    continue
                R = ring["R"]
                if dist - r > R + 6:            # passed through the gap -> escaped
                    ring["alive"], ring["t_dead"] = False, t
                    events.append((t, "escape"))
                    continue
                if dist + r >= R - 4 and dist < R:
                    ang = (math.atan2(d[1], d[0]) - ring["rot"]) % (2 * math.pi)
                    half = ring["gap"] / 2 - math.asin(min(1, r / R))
                    if ang < half or ang > 2 * math.pi - half:
                        continue                # inside the gap: let it pass
                    n = d / dist
                    vn = float(np.dot(vel, n))
                    if vn > 0:
                        pos[:] = (CX, CY) + n * (R - 4 - r - 0.5)
                        vel -= 2 * vn * n
                        sp = math.hypot(*vel)
                        tgt = max(sp, 1050)
                        vel *= tgt / sp
                        tang = np.array([-n[1], n[0]])
                        vel += tang * rng.uniform(-90, 90)
                        if not events or t - events[-1][0] > 0.06:
                            events.append((t, "bounce"))
                break                            # only the innermost alive ring matters
            for ring in rings:
                ring["rot"] += ring["speed"] * dt
            t += dt
        alive = sum(1 for x in rings if x["alive"])
        frames.append(dict(t=t, balls=[(pos[0], pos[1], r, 0)], rings=[(x["R"], x["rot"], x["gap"], x["alive"], x["t_dead"])
                                                                       for x in rings], count=alive))
        if alive == 0 and end_t is None:
            end_t = t
        if end_t is not None and t > end_t + 2.0:
            break
        if dist > 1400:
            vel *= 0
    return frames, events, end_t, n_rings


def sim_multiply(seed, cap=400):
    rng = np.random.default_rng(seed)
    R = 440.0
    gap = math.radians(52)
    rot, rspeed = float(rng.uniform(0, 6.28)), float(rng.choice([-1, 1]) * rng.uniform(0.8, 1.3))
    g = 1300.0
    r = 13.0
    P = np.array([[CX, CY - 100.0]])
    V = np.array([[float(rng.uniform(-300, 300)), 0.0]])
    inside = np.array([True])
    hue = np.array([0.0])
    dt = 1 / (FPS * SUB)
    t, frames, events, end_t, nid = 0.0, [], [], None, 1
    while t < 60:
        for _ in range(SUB):
            V[:, 1] += g * dt
            P += V * dt
            D = P - (CX, CY)
            dist = np.hypot(D[:, 0], D[:, 1]) + 1e-6
            # escaped?
            esc = inside & (dist - r > R + 8)
            if esc.any():
                k = int(esc.sum())
                inside[esc] = False
                for _ in range(k):
                    events.append((t, "escape"))
                for _ in range(2 * k):
                    if inside.sum() >= cap:
                        break
                    a = rng.uniform(0, 2 * math.pi)
                    P = np.vstack([P, [CX + 20 * math.cos(a), CY + 20 * math.sin(a)]])
                    V = np.vstack([V, [700 * math.cos(a), 700 * math.sin(a) - 300]])
                    inside = np.append(inside, True)
                    hue = np.append(hue, (nid * 0.061) % 1.0)
                    nid += 1
                D = P - (CX, CY)
                dist = np.hypot(D[:, 0], D[:, 1]) + 1e-6
            hit = inside & (dist + r >= R - 4) & (dist < R + 2)
            if hit.any():
                ang = (np.arctan2(D[:, 1], D[:, 0]) - rot) % (2 * math.pi)
                half = gap / 2 - math.asin(r / R)
                in_gap = (ang < half) | (ang > 2 * math.pi - half)
                hit &= ~in_gap
                N = D / dist[:, None]
                vn = (V * N).sum(1)
                hit &= vn > 0
                if hit.any():
                    idx = np.where(hit)[0]
                    P[idx] = np.array([CX, CY]) + N[idx] * (R - 4 - r - 0.5)
                    V[idx] -= 2 * vn[idx, None] * N[idx]
                    sp = np.hypot(V[idx, 0], V[idx, 1]) + 1e-6
                    V[idx] *= (np.maximum(sp, 950) / sp)[:, None]
                    T = np.stack([-N[idx, 1], N[idx, 0]], 1)
                    V[idx] += T * rng.uniform(-80, 80, len(idx))[:, None]
                    if not events or t - events[-1][0] > 0.05:
                        events.append((t, "bounce"))
            rot += rspeed * dt
            t += dt
        # drop balls far off-screen
        keep = inside | (P[:, 1] < H + 60)
        P, V, inside, hue = P[keep], V[keep], inside[keep], hue[keep]
        n_in = int(inside.sum())
        frames.append(dict(t=t, balls=[(P[i, 0], P[i, 1], r, hue[i]) for i in range(len(P))],
                           rings=[(R, rot, gap, True, None)], count=n_in))
        if n_in >= cap and end_t is None:
            end_t = t
        if end_t is not None and t > end_t + 2.0:
            break
    return frames, events, end_t, cap


# ------------------------------------------------------------------ audio
def tone(f, d=0.5, dec=0.22, g=0.25):
    tt = np.arange(int(SR * d)) / SR
    s = np.sin(2 * np.pi * f * tt) + 0.35 * np.sin(4 * np.pi * f * tt) + 0.12 * np.sin(6 * np.pi * f * tt)
    return (s * np.exp(-tt / dec) * np.minimum(1, tt / 0.003) * g).astype(np.float32)


def shatter():
    tt = np.arange(int(SR * 0.35)) / SR
    n = np.random.default_rng(9).standard_normal(len(tt))
    n = np.diff(n, prepend=0) * np.exp(-tt / 0.06) * 0.25
    return (n + tone(1568, 0.35, 0.12, 0.18)[:len(n)]).astype(np.float32)


def make_audio(events, total, end_t, mode):
    n = int(SR * (total + 0.5))
    a = np.zeros(n, dtype=np.float32)

    def add(sig, at, g=1.0):
        p = int(at * SR)
        if p >= n:
            return
        s = sig[:n - p]
        a[p:p + len(s)] += s * g

    bi = 0
    last_esc = -1
    for (t, kind) in events:
        if kind == "bounce":
            add(tone(SCALE[MELODY[bi % len(MELODY)]]), t)
            bi += 1
        elif kind == "escape":
            if mode == "escape":
                add(shatter(), t, 1.0)
            elif t - last_esc > 0.045:
                add(tone(SCALE[MELODY[bi % len(MELODY)]] * 2, 0.25, 0.08, 0.16), t)
                bi += 1
                last_esc = t
    if end_t:
        tt = np.arange(int(SR * 1.8)) / SR
        ch = sum(np.sin(2 * np.pi * f * tt) for f in (523.3, 659.3, 784.0, 1046.5)) * np.exp(-tt / 0.7) * 0.2
        add(ch.astype(np.float32), end_t)
    a = np.tanh(a * 1.2)
    a /= max(np.max(np.abs(a)), 1e-6) / 0.9
    return a


# ------------------------------------------------------------------ video
def render(mode, out, seed, hook, palette):
    tries = 0
    while True:
        if mode == "escape":
            frames, events, end_t, n0 = sim_escape(seed)
        else:
            frames, events, end_t, n0 = sim_multiply(seed)
        total = frames[-1]["t"]
        first_esc = next((t for t, k in events if k == "escape"), 99)
        if end_t and 15 <= total <= 45 and first_esc < 3.5:
            break
        seed += 1
        tries += 1
        if tries > 60:
            raise SystemExit("no seed in range")
    print("seed", seed, "duration", round(total, 1), "events", len(events))
    audio = make_audio(events, total, end_t, mode)
    # funny milestone stickers
    prng = random.Random(seed * 7 + 3)
    popups, done = [], set()
    if mode == "escape":
        first = next((t for t, k in events if k == "escape"), None)
        marks = [(first, "HE'S GETTING OUT", "😳")]
        for f_ in frames:
            if f_["count"] == n0 // 2 and "half" not in done:
                done.add("half")
                marks.append((f_["t"], "HALFWAY THERE", "👀"))
            if f_["count"] == 1 and "one" not in done:
                done.add("one")
                marks.append((f_["t"], "ONE MORE...", "😬"))
    else:
        marks = []
        for lim, txt, em in ((20, "IT'S MULTIPLYING", "😳"), (120, "THIS IS GETTING OUT OF HAND", "💀"), (280, "BRO STOP", "😭")):
            tt_ = next((f_["t"] for f_ in frames if f_["count"] >= lim), None)
            marks.append((tt_, txt, em))
    last = -9
    for tt_, txt, em in sorted((m for m in marks if m[0] is not None), key=lambda m: m[0]):
        if tt_ - last < 1.5 or (end_t and tt_ > end_t - 0.3):
            continue
        popups.append((tt_, fxlib.sticker(txt, em, size=58, angle=prng.choice([-6, -4, 4, 6])), W / 2, CY - 250, 1.5))
        p0 = int(tt_ * SR)
        sfx = fxlib.pop(SR) * 0.8
        audio[p0:p0 + len(sfx)] += sfx[:max(0, len(audio) - p0)]
        last = tt_
    audio = audio / max(np.max(np.abs(audio)), 1e-6) * 0.9
    import soundfile as sf
    sf.write(out + ".wav", audio, SR)

    h0, hstep = PALETTES.get(palette, PALETTES["neon"])
    font_big = ImageFont.truetype(F, 96)
    font_cnt = ImageFont.truetype(F, 140)
    font_lab = ImageFont.truetype(F, 40)
    font_wm = ImageFont.truetype(F, 40)
    # background: dark radial vignette
    yy, xx = np.mgrid[0:H, 0:W]
    dd = np.hypot((xx - CX) / W, (yy - CY) / H)
    base = np.clip(28 - dd * 40, 4, 28)
    bg = np.stack([base * 0.8, base * 0.8, base * 1.15], -1).astype(np.uint8)
    bg = Image.fromarray(bg, "RGB")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-i", out + ".wav", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
           "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "44100", "-c:a", "aac", "-b:a", "192k", "-shortest",
           "-movflags", "+faststart", out]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    trail = []
    shards = []          # (x, y, vx, vy, t0, col)
    seen_dead = set()
    rr = random.Random(seed)
    label = "RINGS LEFT" if mode == "escape" else "BALLS"
    for fi, f in enumerate(frames):
        t = f["t"]
        img = bg.copy()
        glow = Image.new("RGB", (W // 2, H // 2), (0, 0, 0))
        gd = ImageDraw.Draw(glow)
        d = ImageDraw.Draw(img)
        nr = len(f["rings"])
        for k, (R, rot, gap, alive, t_dead) in enumerate(f["rings"]):
            col = hue_col(h0 + hstep * k + 0.02 * t, 0.58)
            if not alive:
                if k not in seen_dead:
                    seen_dead.add(k)
                    for j in range(28):       # shatter the ring into flying shards
                        a = rot + gap / 2 + (2 * math.pi - gap) * j / 28
                        x, y = CX + R * math.cos(a), CY + R * math.sin(a)
                        sp = rr.uniform(200, 600)
                        shards.append((x, y, math.cos(a) * sp, math.sin(a) * sp - 200, t, col))
                continue
            a0 = math.degrees(rot + gap / 2)
            a1 = math.degrees(rot - gap / 2 + 2 * math.pi)
            box = (CX - R, CY - R, CX + R, CY + R)
            d.arc(box, a0, a1, fill=col, width=9)
            gd.arc(tuple(v / 2 for v in box), a0, a1, fill=col, width=9)
        # shards
        alive_sh = []
        for (x, y, vx, vy, t0, col) in shards:
            dtt = t - t0
            if dtt > 1.4:
                continue
            alive_sh.append((x, y, vx, vy, t0, col))
            px, py = x + vx * dtt, y + vy * dtt + 0.5 * 1500 * dtt * dtt
            fade = 1 - dtt / 1.4
            c = tuple(int(v * fade) for v in col)
            d.rectangle((px - 5, py - 5, px + 5, py + 5), fill=c)
        shards = alive_sh
        # balls (+ trail for single ball)
        if mode == "escape":
            bx, by, br, _ = f["balls"][0]
            trail.append((bx, by))
            trail = trail[-14:]
            for j, (tx, ty) in enumerate(trail[:-1]):
                al = (j + 1) / len(trail)
                c = tuple(int(v * al * 0.7) for v in (255, 255, 255))
                rad = br * (0.4 + 0.6 * al)
                d.ellipse((tx - rad, ty - rad, tx + rad, ty + rad), fill=c)
            d.ellipse((bx - br, by - br, bx + br, by + br), fill=(255, 255, 255))
            gd.ellipse(((bx - br * 2) / 2, (by - br * 2) / 2, (bx + br * 2) / 2, (by + br * 2) / 2), fill=(255, 255, 255))
        else:
            for (bx, by, br, hh) in f["balls"]:
                c = hue_col(hh, 0.62)
                d.ellipse((bx - br, by - br, bx + br, by + br), fill=c)
                gd.ellipse(((bx - br) / 2, (by - br) / 2, (bx + br) / 2, (by + br) / 2), fill=c)
        glow = glow.filter(ImageFilter.GaussianBlur(10)).resize((W, H), Image.BILINEAR)
        img = ImageChops.add(img, glow)
        d = ImageDraw.Draw(img)
        # hook
        y = 215
        fb = font_big
        while fb.size > 50 and max(d.textlength(l, font=fb) for l in hook) > 940:
            fb = ImageFont.truetype(F, fb.size - 4)
        for line in hook:
            tw = d.textlength(line, font=fb)
            d.text(((W - tw) / 2, y), line, font=fb, fill=(255, 255, 255), stroke_width=7, stroke_fill=(0, 0, 0))
            y += int(fb.size * 1.17)
        # counter
        s = str(f["count"])
        ccol = hue_col(h0 + 0.03 * t, 0.66)
        tw = d.textlength(s, font=font_cnt)
        d.text(((W - tw) / 2, CY + 500), s, font=font_cnt, fill=ccol, stroke_width=5, stroke_fill=(0, 0, 0))
        lw = d.textlength(label, font=font_lab)
        d.text(((W - lw) / 2, CY + 660), label, font=font_lab, fill=(170, 170, 185))
        if end_t and t >= end_t:
            msg = "ESCAPED!" if mode == "escape" else f"{f['count']} BALLS!"
            sc = min(1.0, (t - end_t) / 0.25)
            ft = ImageFont.truetype(F, max(10, int(130 * (0.6 + 0.4 * sc))))
            tw = d.textlength(msg, font=ft)
            d.text(((W - tw) / 2, CY - 80), msg, font=ft, fill=(255, 255, 255), stroke_width=8, stroke_fill=(0, 0, 0))
        fxlib.draw_popups(img, popups, t)
        d = ImageDraw.Draw(img)
        d.text((70, 150), "unreel", font=font_wm, fill=(255, 255, 255))
        ff.stdin.write(img.tobytes())
    ff.stdin.close()
    ff.wait()
    import os
    os.remove(out + ".wav")
    return seed, total


if __name__ == "__main__":
    mode, out = sys.argv[1], sys.argv[2]
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    default = {"escape": "CAN IT|ESCAPE?", "multiply": "EVERY ESCAPE|= 2 MORE BALLS"}
    hook = (sys.argv[4] if len(sys.argv) > 4 else default.get(mode, "WAIT FOR|THE ENDING")).split("|")
    pal = sys.argv[5] if len(sys.argv) > 5 else "neon"
    if mode in ("battle", "elimination"):
        extra = sys.argv[6] if len(sys.argv) > 6 else ""
        subprocess.run([sys.executable, __file__.replace("physics.py", "arena.py"), mode, out, str(seed),
                        sys.argv[4] if len(sys.argv) > 4 else "", pal, extra], check=True)
    elif mode == "grow":
        subprocess.run([sys.executable, __file__.replace("physics.py", "sim_ball.py"), out, str(seed), "|".join(hook)], check=True)
    else:
        s, tot = render(mode, out, seed, hook, pal)
        print(f"done {out} seed={s} {tot:.1f}s")
