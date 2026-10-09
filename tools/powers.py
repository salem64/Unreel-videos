#!/usr/bin/env python3
"""Unreel POWERS battle: two balls with elemental abilities that EVOLVE (level 1 -> 2 -> 3) while they fight.

python3 tools/powers.py out.mp4 [seed] ["HOOK1|HOOK2"] [palette] [fighters]
fighters: "fire,ice" | "🐉:fire,🐧:ice" | "red:lightning,blue:vampire" | "" (random abilities)
Abilities (lv1 / lv2 / lv3 names):
  fire 🔥      FIRE / BLAZE / INFERNO        - burning trail, touching it (or the ball) sets you on fire
  ice ❄️       ICE / FROST / BLIZZARD        - hits freeze the enemy (slow + blue), lv3 shoots ice shards
  lightning ⚡ SPARK / STORM / THUNDER GOD  - lightning bolts strike the enemy, faster each level
  vampire 🧛   BAT / VAMPIRE / DRACULA       - steals life on every hit
  poison 🧪    TOXIC / VENOM / PLAGUE        - leaves toxic puddles, poison stacks up
  ghost 👻     GHOST / PHANTOM / WRAITH      - teleports behind the enemy and strikes, untouchable after
  clone 🧬     SPLIT / SWARM / LEGION        - spawns mini clones that hunt and explode
  blackhole 🌀 VOID / BLACK HOLE / SINGULARITY - pulls the enemy in, damages everything close
  bomb 💣      BOMBER / DEMOLISHER / NUKE    - drops bombs with growing blast radius
  giant 🦣     BIG / HUGE / TITAN            - grows with every hit, hits harder the bigger it is
  glitch 👾    GLITCH / CORRUPTED / ERROR 404 - glitch-teleports next to the enemy with an RGB-split static burst
  laser 🔴     LASER / PLASMA / DEATH RAY    - rotating laser beams (1 / 2 / 3 beams, longer each level)
  meteor ☄️    METEOR / COMET / ARMAGEDDON   - meteors crash down on the enemy (warning circle, huge blast, screen shake)
  rocket 🚀    ROCKET / JET / HYPERSONIC     - rocket dashes at the enemy with a flame exhaust, massive ram damage
  tornado 🌪️   WIND / CYCLONE / HURRICANE    - tornadoes chase the enemy and spin it around
Most spectacular (use these most): laser, meteor, lightning, blackhole, bomb, glitch, rocket, tornado, clone, fire, ghost, ice.
Each ball levels up from the damage it deals ("EVOLVED" sticker, flash, new look). Sudden death after 35 s.
Prints seed, duration and winner (never reveal the winner in caption/title).
"""
import math, os, random, sys
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arena as A  # noqa: E402
import fx as fxlib  # noqa: E402

W, H, FPS, SR, CX, CY = A.W, A.H, A.FPS, A.SR, A.CX, A.CY
SUB = 6
R_ARENA = 430.0
ABIL = {
    "fire":      dict(emoji="🔥", names=("FIRE", "BLAZE", "INFERNO"), col=(255, 120, 30), col3=(255, 240, 200)),
    "ice":       dict(emoji="❄️", names=("ICE", "FROST", "BLIZZARD"), col=(90, 200, 255), col3=(230, 250, 255)),
    "lightning": dict(emoji="⚡", names=("SPARK", "STORM", "THUNDER GOD"), col=(255, 225, 40), col3=(255, 255, 210)),
    "vampire":   dict(emoji="🧛", names=("BAT", "VAMPIRE", "DRACULA"), col=(200, 20, 50), col3=(255, 60, 90)),
    "poison":    dict(emoji="🧪", names=("TOXIC", "VENOM", "PLAGUE"), col=(110, 230, 60), col3=(200, 255, 120)),
    "ghost":     dict(emoji="👻", names=("GHOST", "PHANTOM", "WRAITH"), col=(200, 190, 255), col3=(250, 245, 255)),
    "clone":     dict(emoji="🧬", names=("SPLIT", "SWARM", "LEGION"), col=(30, 220, 200), col3=(170, 255, 240)),
    "blackhole": dict(emoji="🌀", names=("VOID", "BLACK HOLE", "SINGULARITY"), col=(150, 70, 255), col3=(220, 180, 255)),
    "bomb":      dict(emoji="💣", names=("BOMBER", "DEMOLISHER", "NUKE"), col=(255, 80, 60), col3=(255, 200, 80)),
    "giant":     dict(emoji="🦣", names=("BIG", "HUGE", "TITAN"), col=(200, 140, 80), col3=(255, 210, 150)),
    "glitch":    dict(emoji="👾", names=("GLITCH", "CORRUPTED", "ERROR 404"), col=(255, 40, 200), col3=(120, 255, 255)),
    "laser":     dict(emoji="🔴", names=("LASER", "PLASMA", "DEATH RAY"), col=(255, 45, 70), col3=(255, 200, 210)),
    "meteor":    dict(emoji="☄️", names=("METEOR", "COMET", "ARMAGEDDON"), col=(170, 110, 255), col3=(255, 190, 120)),
    "rocket":    dict(emoji="🚀", names=("ROCKET", "JET", "HYPERSONIC"), col=(235, 235, 245), col3=(255, 170, 60)),
    "tornado":   dict(emoji="🌪️", names=("WIND", "CYCLONE", "HURRICANE"), col=(150, 210, 220), col3=(240, 255, 255)),
}
HYPE = ("laser", "meteor", "lightning", "blackhole", "bomb", "glitch", "rocket", "tornado", "clone", "fire", "ghost", "ice")
LV_XP = (0, 14, 36)          # damage dealt needed for level 2 and 3


def parse(extra, seed):
    rng = random.Random(seed * 13 + 7)
    items = [x.strip() for x in (extra or "").split(",") if x.strip()]
    names, abil = [], []
    for it in items[:2]:
        nm, _, ab = it.partition(":")
        if nm in ABIL and not ab:
            nm, ab = "", nm
        names.append(nm)
        abil.append(ab if ab in ABIL else "")
    while len(names) < 2:
        names.append("")
        abil.append("")
    for k in range(2):
        if not abil[k]:
            abil[k] = rng.choice([a for a in HYPE if a not in abil])
    emo = names if all(n and n.lower() not in ("red", "blue") for n in names) else None
    return emo, abil


# ------------------------------------------------------------------ simulation
def simulate(seed, abil):
    rng = random.Random(seed)
    dt = 1 / (FPS * SUB)
    balls = []
    for k in range(2):
        a = rng.uniform(0, 2 * math.pi)
        balls.append(dict(k=k, ab=abil[k], p=np.array([CX + (-180 if k == 0 else 180), CY + rng.uniform(-90, 90)]),
                          v=np.array([math.cos(a), math.sin(a)]) * 620, r=66.0, hp=100.0, lv=1, xp=0.0,
                          burn=0.0, burn_dps=0.0, frozen=0.0, poison=0.0, intang=0.0, flash=-9, lvl_t=-9,
                          cd=rng.uniform(0.3, 0.9), cd2=1.0, touch_cd=0.0, acc=0.0, glt=-9,
                          beam=rng.uniform(0, 6.28), dash=0.0, ex_t=0.0))
    flames, puddles, bolts, bombs, blasts, clones, shards = [], [], [], [], [], [], []
    meteors, tornados, exhaust, flashes = [], [], [], []
    last_laser = -9
    snd, nums, events = [], [], []
    frames = []
    t, end_t, winner = 0.0, None, None
    last_sizzle, last_wall = -9, -9

    def other(b):
        return balls[1 - b["k"]]

    def deal(src, dst, amt, kind="hit", show=True):
        nonlocal end_t, winner
        if end_t is not None or dst["hp"] <= 0 or amt <= 0:
            return 0.0
        if dst["intang"] > 0:
            return 0.0
        amt *= 0.62 * (1.0 + max(0.0, t - 35) / 6)        # global scale + sudden death ramp
        dst["hp"] = max(0.0, dst["hp"] - amt)
        src["xp"] += amt
        if kind == "hit":
            dst["flash"] = t
            snd.append((t, A.thud(), 0.9))
            snd.append((t, A.tone(A.SCALE[min(12, 3 + int((100 - dst["hp"]) / 9))], 0.3, 0.1, 0.18), 1.0))
        if show:
            if kind == "hit":
                nums.append((t, dst["p"].copy(), f"-{int(round(amt))}", (255, 230, 80)))
            else:
                dst["acc"] += amt
        if src["ab"] == "vampire" and kind == "hit":
            heal = amt * (0.6, 0.8, 1.0)[src["lv"] - 1]
            src["hp"] = min(100.0, src["hp"] + heal)
            nums.append((t + 0.05, src["p"].copy(), f"+{int(round(heal))}", (90, 255, 120)))
        # level up / evolve
        while src["lv"] < 3 and src["xp"] >= LV_XP[src["lv"]]:
            src["lv"] += 1
            src["lvl_t"] = t
            if src["ab"] == "giant":
                src["r"] = min(src["r"] + 14, 104)
            events.append((t, "evolve", src["k"], src["lv"]))
            snd.append((t, fxlib.boom(SR), 0.7))
            for i, f in enumerate((523.3, 659.3, 784.0, 1046.5)):
                snd.append((t + 0.06 * i, A.tone(f, 0.4, 0.15, 0.2), 1.0))
        if dst["hp"] <= 0 and end_t is None:
            end_t, winner = t, src["k"]
            snd.append((t + 0.15, A.fanfare(), 1.0))
        return amt

    while t < 80:
        for _ in range(SUB):
            alive = end_t is None
            for b in balls:
                o = other(b)
                if b["hp"] <= 0:
                    continue
                speed = 620 + 3 * (100 - b["hp"])
                if b["frozen"] > 0:
                    speed *= 0.25
                    b["frozen"] -= dt
                if b["dash"] > 0:
                    b["dash"] -= dt
                    speed = (1500, 1750, 2050)[b["lv"] - 1]
                    dv = o["p"] - b["p"]
                    b["v"] = b["v"] * 0.88 + dv / (np.linalg.norm(dv) + 1e-6) * speed * 0.12
                    b["ex_t"] -= dt
                    if b["ex_t"] <= 0:
                        b["ex_t"] = 0.025
                        exhaust.append([b["p"] - b["v"] / (np.linalg.norm(b["v"]) + 1e-6) * b["r"], t])
                # black hole pull on the enemy
                if alive and b["ab"] == "blackhole":
                    dv = b["p"] - o["p"]
                    dd = np.linalg.norm(dv) + 1e-6
                    pull = (260, 420, 650)[b["lv"] - 1]
                    o["v"] = o["v"] + dv / dd * pull * dt * 3
                    if dd < (200, 240, 290)[b["lv"] - 1]:
                        deal(b, o, (3, 5, 8)[b["lv"] - 1] * dt, "dot")
                if alive and t > 35:                       # sudden death: balls are drawn to each other
                    dv = o["p"] - b["p"]
                    b["v"] = b["v"] + dv / (np.linalg.norm(dv) + 1e-6) * 1400 * dt
                b["p"] = b["p"] + b["v"] * dt
                d = b["p"] - (CX, CY)
                dist = np.linalg.norm(d)
                if dist + b["r"] > R_ARENA:
                    nrm = d / dist
                    b["p"] = np.array([CX, CY]) + nrm * (R_ARENA - b["r"])
                    vn = np.dot(b["v"], nrm)
                    if vn > 0:
                        b["v"] = b["v"] - 2 * vn * nrm
                        if t - last_wall > 0.09:
                            snd.append((t, A.tone(A.SCALE[rng.randint(0, 6)], 0.22, 0.07, 0.1), 1.0))
                            last_wall = t
                sp = np.linalg.norm(b["v"]) + 1e-6
                b["v"] = b["v"] / sp * speed
                for key in ("intang", "touch_cd"):
                    b[key] = max(0.0, b[key] - dt)
                b["cd"] -= dt
                b["cd2"] -= dt
                # status damage
                if b["burn"] > 0:
                    b["burn"] -= dt
                    deal(o, b, b["burn_dps"] * dt, "dot")
                    if t - last_sizzle > 0.35:
                        snd.append((t, sizzle(), 0.35))
                        last_sizzle = t
                if b["poison"] > 0:
                    deal(o, b, 1.4 * b["poison"] * dt, "dot")
                    b["poison"] = max(0.0, b["poison"] - dt * 0.45)
                if not alive:
                    continue
                ab, lv = b["ab"], b["lv"]
                # --- abilities
                if ab == "fire" and b["cd"] <= 0:
                    b["cd"] = 0.05
                    flames.append([b["p"].copy(), t, (1.0, 1.5, 2.2)[lv - 1], b["k"]])
                elif ab == "poison" and b["cd"] <= 0:
                    b["cd"] = (0.7, 0.55, 0.4)[lv - 1]
                    puddles.append([b["p"].copy(), t, 4.5, b["k"], (44, 56, 70)[lv - 1]])
                elif ab == "lightning" and b["cd"] <= 0:
                    b["cd"] = (2.0, 1.6, 1.25)[lv - 1]
                    for i in range(lv):
                        src = b["p"].copy() if i == 0 else np.array([CX + rng.uniform(-300, 300), CY - R_ARENA + 20])
                        bolts.append((t + 0.05 * i, src, o["p"].copy(), b["k"]))
                    snd.append((t, zap(), 0.9))
                    if lv == 3:
                        flashes.append(t)
                    deal(b, o, (5, 4, 3.2)[lv - 1] * lv, "hit")
                elif ab == "laser":
                    b["beam"] += (1.7, 2.3, 2.9)[lv - 1] * dt
                    L = (290, 370, 450)[lv - 1]
                    for i in range(lv):
                        a_ = b["beam"] + 2 * math.pi * i / lv
                        u = np.array([math.cos(a_), math.sin(a_)])
                        s0, s1 = b["p"] + u * b["r"], b["p"] + u * (b["r"] + L)
                        ab_ = s1 - s0
                        tt_ = max(0.0, min(1.0, np.dot(o["p"] - s0, ab_) / np.dot(ab_, ab_)))
                        if np.linalg.norm(o["p"] - (s0 + tt_ * ab_)) < o["r"]:
                            deal(b, o, (12, 15, 18)[lv - 1] * dt, "dot")
                            o["flash"] = t
                            if t - last_laser > 0.25:
                                snd.append((t, sizzle(), 0.6))
                                last_laser = t
                elif ab == "meteor" and b["cd"] <= 0:
                    b["cd"] = (2.2, 1.7, 1.2)[lv - 1]
                    for i in range(1 if lv < 3 else 2):
                        tgt = o["p"] + o["v"] * 0.45 + np.array([rng.uniform(-60, 60), rng.uniform(-60, 60)]) * i * 2
                        dc = tgt - (CX, CY)
                        if np.linalg.norm(dc) > R_ARENA - 60:
                            tgt = np.array([CX, CY]) + dc / np.linalg.norm(dc) * (R_ARENA - 60)
                        meteors.append([tgt, t + 0.9 + 0.15 * i, b["k"], (115, 145, 185)[lv - 1], (9, 12, 15)[lv - 1], t])
                elif ab == "rocket" and b["cd"] <= 0:
                    b["cd"] = (3.0, 2.5, 2.0)[lv - 1]
                    b["dash"] = 0.55
                    snd.append((t, zap(), 0.5))
                    snd.append((t, A.tone(110, 0.6, 0.3, 0.3), 1.0))
                elif ab == "tornado" and b["cd"] <= 0:
                    b["cd"] = (3.0, 2.4, 1.8)[lv - 1]
                    a = rng.uniform(0, 6.28)
                    pos = o["p"] + np.array([math.cos(a), math.sin(a)]) * 170
                    dc = pos - (CX, CY)
                    if np.linalg.norm(dc) > R_ARENA - 90:
                        pos = np.array([CX, CY]) + dc / np.linalg.norm(dc) * (R_ARENA - 90)
                    tornados.append([pos, t, 3.2, b["k"], (95, 125, 155)[lv - 1]])
                    snd.append((t, sizzle(), 0.5))
                elif ab == "fire" and lv >= 2 and b["cd2"] <= 0:
                    b["cd2"] = (1.3, 0.9)[lv - 2]
                    dv = o["p"] - b["p"]
                    u = dv / (np.linalg.norm(dv) + 1e-6)
                    shards.append([b["p"] + u * (b["r"] + 6), u * 900, b["k"], "fire", 6])
                    snd.append((t, A.tone(330, 0.2, 0.08, 0.2), 1.0))
                elif ab == "ghost" and b["cd"] <= 0:
                    b["cd"] = (3.0, 2.4, 1.8)[lv - 1]
                    ov = o["v"] / (np.linalg.norm(o["v"]) + 1e-6)
                    target = o["p"] - ov * (b["r"] + o["r"] + 4)
                    if np.linalg.norm(target - (CX, CY)) + b["r"] < R_ARENA:
                        events.append((t, "blink", b["k"], b["p"].copy()))
                        b["p"] = target
                        b["intang"] = 0.6
                        snd.append((t, A.tone(220, 0.35, 0.15, 0.25), 1.0))
                        deal(b, o, (6, 8, 11)[lv - 1], "hit")
                elif ab == "clone" and b["cd"] <= 0:
                    b["cd"] = (3.2, 2.4, 1.7)[lv - 1]
                    if sum(1 for c in clones if c[2] == b["k"]) < (2, 3, 5)[lv - 1]:
                        a = rng.uniform(0, 6.28)
                        clones.append([b["p"].copy(), np.array([math.cos(a), math.sin(a)]) * 500, b["k"], t])
                        snd.append((t, fxlib.pop(SR), 0.6))
                elif ab == "bomb" and b["cd"] <= 0:
                    b["cd"] = (1.7, 1.4, 1.1)[lv - 1]
                    bombs.append([b["p"].copy(), t + 1.0, b["k"], (150, 190, 240)[lv - 1], (8, 11, 15)[lv - 1]])
                elif ab == "glitch" and b["cd"] <= 0:
                    b["cd"] = (2.4, 1.9, 1.4)[lv - 1]
                    for _try in range(8):
                        a = rng.uniform(0, 6.28)
                        tgt = o["p"] + np.array([math.cos(a), math.sin(a)]) * rng.uniform(b["r"] + o["r"] + 40, 230)
                        if np.linalg.norm(tgt - (CX, CY)) + b["r"] < R_ARENA:
                            break
                    else:
                        tgt = b["p"]
                    events.append((t, "glitch", b["k"], b["p"].copy()))
                    b["p"] = tgt
                    b["glt"] = t
                    snd.append((t, zap(), 0.6))
                    if np.linalg.norm(o["p"] - b["p"]) < 270:
                        deal(b, o, (5, 7, 9)[lv - 1], "hit")
                        o["v"] = -o["v"]                     # corrupted controls
                elif ab == "ice" and lv == 3 and b["cd2"] <= 0:
                    b["cd2"] = 1.6
                    dv = o["p"] - b["p"]
                    base = math.atan2(dv[1], dv[0])
                    for s_ in (-0.25, 0, 0.25):
                        u = np.array([math.cos(base + s_), math.sin(base + s_)])
                        shards.append([b["p"] + u * (b["r"] + 6), u * 950, b["k"], "ice", 3])
            if end_t is None:
                A_, B_ = balls
                dvec = B_["p"] - A_["p"]
                dd = np.linalg.norm(dvec) + 1e-6
                if dd < A_["r"] + B_["r"]:
                    nrm = dvec / dd
                    rel = np.dot(A_["v"] - B_["v"], nrm)
                    if rel > 0:
                        A_["v"] = A_["v"] - rel * nrm
                        B_["v"] = B_["v"] + rel * nrm
                    over = A_["r"] + B_["r"] - dd
                    A_["p"] = A_["p"] - nrm * over / 2
                    B_["p"] = B_["p"] + nrm * over / 2
                    snd.append((t, A.clank(), 0.35))
                    for att, vic in ((A_, B_), (B_, A_)):
                        if att["touch_cd"] > 0:
                            continue
                        att["touch_cd"] = 0.3
                        lv = att["lv"]
                        base = 4.0
                        if att["ab"] == "giant":
                            base = 4 + (att["r"] - 66) * 0.25 + 3 * lv
                        elif att["ab"] == "vampire":
                            base = (6, 8, 10)[lv - 1]
                        elif att["ab"] == "ice":
                            base = (5, 7, 9)[lv - 1]
                            vic["frozen"] = (0.8, 1.2, 1.6)[lv - 1]
                        elif att["ab"] == "fire":
                            vic["burn"], vic["burn_dps"] = 1.4, (3, 4.5, 6.5)[lv - 1]
                        elif att["ab"] == "rocket" and att["dash"] > 0:
                            base = (9, 11, 14)[lv - 1]
                            kb = vic["p"] - att["p"]
                            vic["v"] = vic["v"] + kb / (np.linalg.norm(kb) + 1e-6) * 1200
                            blasts.append((t, (att["p"] + vic["p"]) / 2, 110, att["k"]))
                            snd.append((t, fxlib.boom(SR), 0.6))
                            att["dash"] = 0.0
                        deal(att, vic, base, "hit")
                # fire trail burns
                for fl in flames:
                    vic = balls[1 - fl[3]]
                    if np.linalg.norm(vic["p"] - fl[0]) < vic["r"] * 0.8:
                        lvf = balls[fl[3]]["lv"]
                        vic["burn"], vic["burn_dps"] = max(vic["burn"], 0.7), (2.5, 3.5, 5)[lvf - 1]
                # poison puddles
                for pd_ in puddles:
                    vic = balls[1 - pd_[3]]
                    if np.linalg.norm(vic["p"] - pd_[0]) < pd_[4] + vic["r"] * 0.6:
                        cap = (5, 8, 12)[balls[pd_[3]]["lv"] - 1]
                        vic["poison"] = min(cap, vic["poison"] + dt * 2.2)
                # clones hunt and explode
                keep = []
                for c in clones:
                    tgt = balls[1 - c[2]]
                    dv = tgt["p"] - c[0]
                    dd2 = np.linalg.norm(dv) + 1e-6
                    c[1] = c[1] * 0.97 + dv / dd2 * 40
                    sp = np.linalg.norm(c[1]) + 1e-6
                    c[1] = c[1] / sp * 520
                    c[0] = c[0] + c[1] * dt
                    if np.linalg.norm(c[0] - (CX, CY)) > R_ARENA - 26:
                        c[0] = np.array([CX, CY]) + (c[0] - (CX, CY)) / np.linalg.norm(c[0] - (CX, CY)) * (R_ARENA - 27)
                    if dd2 < tgt["r"] + 26:
                        blasts.append((t, c[0].copy(), 90, c[2]))
                        snd.append((t, fxlib.boom(SR), 0.35))
                        deal(balls[c[2]], tgt, 6, "hit")
                        continue
                    keep.append(c)
                clones[:] = keep
                # bombs
                keep = []
                for bm in bombs:
                    if t >= bm[1]:
                        blasts.append((t, bm[0].copy(), bm[3], bm[2]))
                        snd.append((t, fxlib.boom(SR), 0.8))
                        vic = balls[1 - bm[2]]
                        if np.linalg.norm(vic["p"] - bm[0]) < bm[3] + vic["r"] * 0.5:
                            kb = vic["p"] - bm[0]
                            vic["v"] = vic["v"] + kb / (np.linalg.norm(kb) + 1e-6) * 900
                            deal(balls[bm[2]], vic, bm[4], "hit")
                        continue
                    keep.append(bm)
                bombs[:] = keep
                # ice shards
                keep = []
                for sh in shards:
                    sh[0] = sh[0] + sh[1] * dt
                    vic = balls[1 - sh[2]]
                    if np.linalg.norm(sh[0] - (CX, CY)) > R_ARENA:
                        continue
                    if np.linalg.norm(sh[0] - vic["p"]) < vic["r"]:
                        if sh[3] == "ice":
                            vic["frozen"] = max(vic["frozen"], 0.7)
                        else:
                            vic["burn"], vic["burn_dps"] = 1.5, 5
                            blasts.append((t, sh[0].copy(), 70, sh[2]))
                        deal(balls[sh[2]], vic, sh[4], "hit")
                        continue
                    keep.append(sh)
                shards[:] = keep
                # meteors
                keep = []
                for m in meteors:
                    if t >= m[1]:
                        blasts.append((t, m[0].copy(), m[3], m[2]))
                        snd.append((t, fxlib.boom(SR), 1.0))
                        vic = balls[1 - m[2]]
                        if np.linalg.norm(vic["p"] - m[0]) < m[3] + vic["r"] * 0.5:
                            kb = vic["p"] - m[0]
                            vic["v"] = vic["v"] + kb / (np.linalg.norm(kb) + 1e-6) * 1000
                            deal(balls[m[2]], vic, m[4], "hit")
                        continue
                    keep.append(m)
                meteors[:] = keep
                # tornados
                keep = []
                for tw in tornados:
                    if t - tw[1] > tw[2]:
                        continue
                    vic = balls[1 - tw[3]]
                    dv = vic["p"] - tw[0]
                    dd3 = np.linalg.norm(dv) + 1e-6
                    tw[0] = tw[0] + dv / dd3 * 170 * dt
                    if dd3 < tw[4] + vic["r"] * 0.5:
                        tang = np.array([-dv[1], dv[0]]) / dd3
                        vic["v"] = vic["v"] + tang * 2600 * dt
                        deal(balls[tw[3]], vic, (6, 8, 11)[balls[tw[3]]["lv"] - 1] * dt, "dot")
                    keep.append(tw)
                tornados[:] = keep
            # expire effects
            flames[:] = [f for f in flames if t - f[1] < f[2]]
            puddles[:] = [p_ for p_ in puddles if t - p_[1] < p_[2]]
            exhaust[:] = [e for e in exhaust if t - e[1] < 0.45]
            t += dt
        # flush accumulated DoT numbers
        for b in balls:
            if b["acc"] >= 3:
                col = (255, 140, 40) if b["burn"] > 0 else (140, 255, 90)
                nums.append((t, b["p"].copy(), f"-{int(b['acc'])}", col))
                b["acc"] = 0.0
        frames.append(dict(
            t=t,
            balls=[dict(p=b["p"].copy(), r=b["r"], hp=b["hp"], lv=b["lv"], ab=b["ab"], burn=b["burn"] > 0,
                        frozen=b["frozen"] > 0, poison=b["poison"], intang=b["intang"] > 0, fl=t - b["flash"] < 0.1,
                        lvl_t=b["lvl_t"], glt=b["glt"]) for b in balls],
            flames=[(f[0].copy(), t - f[1], f[2], f[3]) for f in flames[-160:]],
            puddles=[(p_[0].copy(), t - p_[1], p_[2], p_[3], p_[4]) for p_ in puddles],
            clones=[(c[0].copy(), c[2]) for c in clones],
            bombs=[(bm[0].copy(), bm[1] - t, bm[2], bm[3]) for bm in bombs],
            shards=[(sh[0].copy(), sh[1].copy(), sh[3]) for sh in shards],
            beams=[(b["p"].copy(), b["beam"], b["lv"], b["r"], b["k"]) for b in balls if b["ab"] == "laser" and b["hp"] > 0
                   and end_t is None],
            meteors=[(m[0].copy(), m[1] - t, m[3], m[5]) for m in meteors],
            tornados=[(tw[0].copy(), t - tw[1], tw[2], tw[4]) for tw in tornados],
            exhaust=[(e[0].copy(), t - e[1]) for e in exhaust]))
        if end_t is not None and t > end_t + 2.4:
            break
    return frames, snd, nums, events, end_t, winner, bolts, blasts, flashes


def sizzle():
    tt = np.arange(int(SR * 0.25)) / SR
    n = np.random.default_rng(3).standard_normal(len(tt))
    n = np.diff(n, prepend=0) * np.exp(-tt / 0.1) * 0.25
    return n.astype(np.float32)


def zap():
    tt = np.arange(int(SR * 0.3)) / SR
    n = np.random.default_rng(8).standard_normal(len(tt)) * np.exp(-tt / 0.05)
    tone_ = np.sign(np.sin(2 * np.pi * (1400 - 900 * tt / 0.3) * tt)) * np.exp(-tt / 0.08) * 0.3
    return ((n * 0.5 + tone_) * 0.6).astype(np.float32)


def jag(a, b, rng, n=9, amp=34):
    pts = [tuple(a)]
    for i in range(1, n):
        f = i / n
        p = a + (b - a) * f
        nrm = np.array([-(b - a)[1], (b - a)[0]])
        nrm = nrm / (np.linalg.norm(nrm) + 1e-6)
        pts.append(tuple(p + nrm * rng.uniform(-amp, amp)))
    pts.append(tuple(b))
    return pts


# ------------------------------------------------------------------ render
def render(out, seed, hook, palette, extra):
    emo, abil = parse(extra, seed)
    tries = 0
    while True:
        frames, snd, nums, events, end_t, winner, bolts, blasts, flashes = simulate(seed, abil)
        total = frames[-1]["t"]
        lvls = [frames[-1]["balls"][k]["lv"] for k in range(2)]
        strict = end_t and 20 <= total <= 46 and frames[-1]["balls"][winner]["hp"] <= 55 and max(lvls) >= 3 and min(lvls) >= 2
        loose = end_t and 15 <= total <= 55 and max(lvls) >= 2
        if strict or (tries >= 60 and loose) or (tries >= 150 and end_t and total <= 60):
            break
        seed += 1
        tries += 1
        if tries > 220:
            raise SystemExit("no seed in range - pick another ability pair")
    names = [("RED", (239, 68, 68)), ("BLUE", (59, 130, 246))]
    wname = (emo[winner] if emo else names[winner][0]) + f" ({abil[winner]})"
    print("seed", seed, "duration", round(total, 1), "abilities", abil, "winner", wname)

    # sprites per ball and level
    spr = {}
    for k in range(2):
        info = ABIL[abil[k]]
        for lv in (1, 2, 3):
            c = info["col"] if lv == 1 else tuple(int(a + (b - a) * (0.3 if lv == 2 else 0.55)) for a, b in zip(info["col"], info["col3"]))
            if emo:
                base = A.ball_sprite(66, emoji=emo[k], ring=c)
            else:
                base = A.flat_ball(66, c)
            spr[(k, lv)] = base
    white = A.flat_ball(66, (255, 255, 255))
    crown = fxlib.emoji_img("👑", 56)
    flame_e = fxlib.emoji_img("🔥", 40)
    ice_e = fxlib.emoji_img("❄️", 40)
    skull_e = fxlib.emoji_img("☠️", 34)
    bomb_e = fxlib.emoji_img("💣", 54)

    # stickers
    prng = random.Random(seed * 3 + 1)
    popups, last_pop = [], -9.0
    cand = []
    for ev in events:
        if ev[1] == "evolve":
            _, _, k, lv = ev
            info = ABIL[abil[k]]
            cand.append((ev[0], f"{info['names'][lv - 2]} → {info['names'][lv - 1]}", info["emoji"], 1.7, True, True))
    if nums:
        cand.append((nums[0][0], "FIRST BLOOD", "🩸", 1.3, False, False))
    cooked = [False, False]
    for f_ in frames:
        for k in range(2):
            if not cooked[k] and 0 < f_["balls"][k]["hp"] <= 30:
                cooked[k] = True
                who = "BRO" if emo else names[k][0]
                cand.append((f_["t"], f"{who} {prng.choice(A.COOKED)}", "💀", 1.5, True, False))
    if total > 36 and end_t and end_t > 35.3:
        cand.append((35.0, "SUDDEN DEATH", "⚡", 1.4, True, False))
    for (tp, text, em, dur, loud, force) in sorted(cand, key=lambda c: c[0]):
        if (tp - last_pop < 1.1 and not force) or (end_t and tp > end_t - 0.2):
            continue
        st = fxlib.sticker(text, em, size=58, angle=prng.choice([-6, -4, 4, 6]))
        popups.append((tp, st, W / 2, CY - 290, dur))
        snd.append((tp, fxlib.pop(SR), 0.6))
        last_pop = tp
    audio = A.mix(snd, total)
    HOLD = 0.55
    if end_t:
        audio = fxlib.insert_silence(audio, end_t, HOLD, SR)
    import soundfile as sf
    sf.write(out + ".wav", audio, SR)

    h0 = A.PALETTES.get(palette, 0.55)
    bg = A.make_bg()
    ff = A.open_ff(out)
    rng = random.Random(5)
    hist = [[], []]
    hits = [(nt, tuple(np_), i * 7 + 3) for i, (nt, np_, txt, col) in enumerate(nums) if col == (255, 230, 80)]
    ko_done = False
    for fi, f in enumerate(frames):
        t = f["t"]
        shake = (0, 0)
        for (bt, bp, br, bo) in blasts:
            if 0 <= t - bt < 0.18 and br > 140:
                shake = (rng.uniform(-14, 14), rng.uniform(-14, 14))
        img = bg.copy()
        glow = Image.new("RGB", (W // 2, H // 2), (0, 0, 0))
        gd = ImageDraw.Draw(glow)
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(lay)
        ac = A.hue_col(h0 + 0.01 * t, 0.58)
        box = (CX - R_ARENA, CY - R_ARENA, CX + R_ARENA, CY + R_ARENA)
        ld.ellipse(box, outline=ac + (255,), width=10)
        gd.ellipse(tuple(v / 2 for v in box), outline=ac, width=8)
        # puddles
        for (pp, age, life, ow, rad) in f["puddles"]:
            a_ = max(0.0, min(1.0, age / 0.3)) * max(0.0, min(1.0, (life - age) / 0.8))
            ld.ellipse((pp[0] - rad, pp[1] - rad * 0.7, pp[0] + rad, pp[1] + rad * 0.7), fill=(90, 220, 60, int(110 * a_)))
            gd.ellipse(((pp[0] - rad) / 2, (pp[1] - rad * 0.6) / 2, (pp[0] + rad) / 2, (pp[1] + rad * 0.6) / 2),
                       fill=tuple(int(c * 0.5 * a_) for c in (90, 220, 60)))
        # fire trail
        for (fp, age, life, ow) in f["flames"]:
            q = 1 - age / life
            rad = 10 + 26 * q
            col = (255, int(90 + 150 * q), int(20 * q))
            ld.ellipse((fp[0] - rad, fp[1] - rad, fp[0] + rad, fp[1] + rad), fill=col + (int(170 * q),))
            gd.ellipse(((fp[0] - rad) / 2, (fp[1] - rad) / 2, (fp[0] + rad) / 2, (fp[1] + rad) / 2),
                       fill=tuple(int(c * q * 0.8) for c in col))
        # black hole aura
        for k, b in enumerate(f["balls"]):
            if b["ab"] == "blackhole" and b["hp"] > 0:
                rad = (200, 240, 290)[b["lv"] - 1]
                p = b["p"]
                for i in range(3):
                    rr_ = rad * (0.45 + 0.27 * i)
                    a0 = (t * (140 + 60 * i)) % 360
                    ld.arc((p[0] - rr_, p[1] - rr_, p[0] + rr_, p[1] + rr_), a0, a0 + 250, fill=(160, 80, 255, 120 - 30 * i), width=6)
                gd.ellipse(((p[0] - rad * 0.6) / 2, (p[1] - rad * 0.6) / 2, (p[0] + rad * 0.6) / 2, (p[1] + rad * 0.6) / 2),
                           fill=(60, 20, 110))
        # bombs
        for (bp, left, ow, br) in f["bombs"]:
            blink = int(t * (6 if left > 0.4 else 16)) % 2
            ld.ellipse((bp[0] - br, bp[1] - br, bp[0] + br, bp[1] + br), outline=(255, 60, 60, 80 if blink else 30), width=4)
            lay.alpha_composite(bomb_e, (int(bp[0] - bomb_e.width / 2), int(bp[1] - bomb_e.height / 2)))
        # blasts
        for (bt, bp, br, bo) in blasts:
            age = t - bt
            if 0 <= age < 0.45:
                q = age / 0.45
                rr_ = br * (0.3 + 0.9 * q)
                ld.ellipse((bp[0] - rr_, bp[1] - rr_, bp[0] + rr_, bp[1] + rr_), fill=(255, 200, 80, int(150 * (1 - q))),
                           outline=(255, 255, 255, int(230 * (1 - q))), width=8)
                gd.ellipse(((bp[0] - rr_) / 2, (bp[1] - rr_) / 2, (bp[0] + rr_) / 2, (bp[1] + rr_) / 2),
                           fill=tuple(int(c * (1 - q)) for c in (255, 160, 40)))
        # clones
        for (cp, ow) in f["clones"]:
            c = ABIL["clone"]["col"]
            ld.ellipse((cp[0] - 26, cp[1] - 26, cp[0] + 26, cp[1] + 26), fill=c + (255,), outline=(255, 255, 255, 255), width=3)
            gd.ellipse(((cp[0] - 30) / 2, (cp[1] - 30) / 2, (cp[0] + 30) / 2, (cp[1] + 30) / 2), fill=c)
        # ice shards
        for (sp_, sv, kind) in f["shards"]:
            u = sv / (np.linalg.norm(sv) + 1e-6)
            if kind == "ice":
                ld.line([tuple(sp_ - u * 34), tuple(sp_)], fill=(200, 240, 255, 255), width=8)
                gd.line([tuple((sp_ - u * 34) / 2), tuple(sp_ / 2)], fill=(120, 200, 255), width=5)
            else:
                for j in range(6):
                    q = j / 6
                    pp = sp_ - u * 60 * q
                    rr_ = 22 * (1 - q * 0.7)
                    ld.ellipse((pp[0] - rr_, pp[1] - rr_, pp[0] + rr_, pp[1] + rr_), fill=(255, int(200 - 120 * q), 40, int(255 * (1 - q))))
                gd.ellipse(((sp_[0] - 30) / 2, (sp_[1] - 30) / 2, (sp_[0] + 30) / 2, (sp_[1] + 30) / 2), fill=(255, 140, 30))
        # rocket exhaust
        for (ep, age) in f["exhaust"]:
            q = age / 0.45
            rr_ = 30 * (1 - q) + 6
            ld.ellipse((ep[0] - rr_, ep[1] - rr_, ep[0] + rr_, ep[1] + rr_), fill=(255, int(220 - 160 * q), int(80 * (1 - q)), int(220 * (1 - q))))
            gd.ellipse(((ep[0] - rr_) / 2, (ep[1] - rr_) / 2, (ep[0] + rr_) / 2, (ep[1] + rr_) / 2), fill=(int(255 * (1 - q)), int(120 * (1 - q)), 0))
        # tornados
        for (tp_, age, life, tr_) in f["tornados"]:
            fade = min(1.0, age / 0.3, (life - age) / 0.4)
            for i in range(5):
                rr_ = tr_ * (0.35 + 0.16 * i)
                a0 = (t * (520 - 60 * i) + i * 70) % 360
                ld.arc((tp_[0] - rr_, tp_[1] - rr_ * 0.75, tp_[0] + rr_, tp_[1] + rr_ * 0.75), a0, a0 + 230,
                       fill=(225, 245, 250, int(200 * fade)), width=7 - i)
            gd.ellipse(((tp_[0] - tr_) / 2, (tp_[1] - tr_ * 0.7) / 2, (tp_[0] + tr_) / 2, (tp_[1] + tr_ * 0.7) / 2),
                       fill=tuple(int(c * 0.35 * fade) for c in (150, 210, 220)))
        # meteors (warning + falling rock)
        for (mp, left, mr, t0) in f["meteors"]:
            total_ = 0.9
            q = max(0.0, min(1.0, 1 - left / total_))
            ld.ellipse((mp[0] - mr * q, mp[1] - mr * q, mp[0] + mr * q, mp[1] + mr * q), outline=(255, 60, 60, 200), width=5)
            ld.ellipse((mp[0] - mr, mp[1] - mr, mp[0] + mr, mp[1] + mr), outline=(255, 60, 60, 90), width=3)
            st_ = mp + np.array([420, -1150])
            pos = st_ + (mp - st_) * q
            u = (mp - st_) / np.linalg.norm(mp - st_)
            for j in range(8):
                pp = pos - u * 26 * j
                rr_ = 34 * (1 - j / 9)
                ld.ellipse((pp[0] - rr_, pp[1] - rr_, pp[0] + rr_, pp[1] + rr_), fill=(255, int(210 - 18 * j), 60, int(240 * (1 - j / 8))))
            ld.ellipse((pos[0] - 30, pos[1] - 30, pos[0] + 30, pos[1] + 30), fill=(120, 80, 60, 255), outline=(255, 180, 80, 255), width=4)
            gd.ellipse(((pos[0] - 60) / 2, (pos[1] - 60) / 2, (pos[0] + 60) / 2, (pos[1] + 60) / 2), fill=(255, 120, 30))
        # laser beams
        for (bp, beam, lvb, br, bk) in f["beams"]:
            L = (290, 370, 450)[lvb - 1]
            for i in range(lvb):
                a_ = beam + 2 * math.pi * i / lvb
                u = np.array([math.cos(a_), math.sin(a_)])
                s0, s1 = bp + u * br, bp + u * (br + L)
                ld.line([tuple(s0), tuple(s1)], fill=(255, 40, 60, 220), width=20 + 4 * lvb)
                ld.line([tuple(s0), tuple(s1)], fill=(255, 235, 240, 255), width=7)
                gd.line([tuple(s0 / 2), tuple(s1 / 2)], fill=(255, 30, 60), width=14)
        # balls
        for k, b in enumerate(f["balls"]):
            hist[k].append((b["p"].copy(), b["intang"]))
            hist[k] = hist[k][-6:]
            if b["hp"] <= 0 and end_t and t > end_t + 0.4:
                continue
            info = ABIL[b["ab"]]
            p, r_ = b["p"], b["r"]
            lv = b["lv"]
            # aura grows with level
            aura = r_ + 14 + 12 * lv + 6 * math.sin(t * 7 + k)
            gd.ellipse(((p[0] - aura) / 2, (p[1] - aura) / 2, (p[0] + aura) / 2, (p[1] + aura) / 2),
                       fill=tuple(int(c * (0.12 + 0.12 * lv)) for c in info["col"]))
            if lv >= 2:
                a0 = (t * 220 + 90 * k) % 360
                ld.arc((p[0] - r_ - 16, p[1] - r_ - 16, p[0] + r_ + 16, p[1] + r_ + 16), a0, a0 + 120, fill=info["col"] + (230,), width=6)
                ld.arc((p[0] - r_ - 16, p[1] - r_ - 16, p[0] + r_ + 16, p[1] + r_ + 16), a0 + 180, a0 + 300, fill=info["col"] + (230,), width=6)
            if lv >= 3:
                for i in range(8):
                    aa = t * 3 + i * math.pi / 4
                    q1 = (p[0] + math.cos(aa) * (r_ + 24), p[1] + math.sin(aa) * (r_ + 24))
                    q2 = (p[0] + math.cos(aa) * (r_ + 44), p[1] + math.sin(aa) * (r_ + 44))
                    ld.line([q1, q2], fill=info["col3"] + (220,), width=5)
            # motion trail
            if b["hp"] > 0 and not b["intang"]:
                fxlib.draw_trail(ld, [h[0] for h in hist[k]], r_, info["col"])
            # ghost afterimages
            if b["ab"] == "ghost":
                for j, (hp_, it) in enumerate(hist[k][:-1]):
                    al = int(60 * (j + 1) / len(hist[k]))
                    ld.ellipse((hp_[0] - r_, hp_[1] - r_, hp_[0] + r_, hp_[1] + r_), fill=info["col"] + (al,))
            # evolve pulse
            pulse = 1.0
            age_l = t - b["lvl_t"]
            if 0 <= age_l < 0.5:
                pulse = 1 + 0.45 * math.sin(age_l / 0.5 * math.pi)
                rr_ = r_ + 200 * age_l
                ld.ellipse((p[0] - rr_, p[1] - rr_, p[0] + rr_, p[1] + rr_), outline=(255, 255, 255, int(255 * (1 - age_l / 0.5))), width=10)
            s_ = white if b["fl"] else spr[(k, lv)]
            sc = r_ / 66 * pulse
            if abs(sc - 1) > 0.01:
                s_ = s_.resize((int(s_.width * sc), int(s_.height * sc)), Image.BICUBIC)
            if 0 <= t - b["glt"] < 0.35:
                q = 1 - (t - b["glt"]) / 0.35
                off = int(16 * q) + 2
                for tint, dx in (((255, 0, 60), -off), ((0, 230, 255), off)):
                    tl = Image.new("RGBA", s_.size, tint + (0,))
                    tl.putalpha(s_.getchannel("A").point(lambda v: int(v * 0.55)))
                    lay.alpha_composite(tl, (int(p[0] - s_.width / 2 + dx), int(p[1] - s_.height / 2)))
                grng = random.Random(int(t * 1000) + k)
                for _ in range(6):
                    yy = p[1] + grng.uniform(-160, 160)
                    ld.rectangle((p[0] - grng.uniform(80, 300), yy, p[0] + grng.uniform(80, 300), yy + grng.uniform(4, 14)),
                                 fill=grng.choice([(255, 0, 200), (0, 255, 255), (255, 255, 255)]) + (int(140 * q),))
            if b["intang"]:
                s_ = s_.copy()
                s_.putalpha(s_.getchannel("A").point(lambda v: int(v * 0.45)))
            lay.alpha_composite(s_, (int(p[0] - s_.width / 2), int(p[1] - s_.height / 2)))
            if lv == 3:
                A.draw_crown(ld, p, r_)
            if b["frozen"]:
                ld.ellipse((p[0] - r_ - 6, p[1] - r_ - 6, p[0] + r_ + 6, p[1] + r_ + 6), fill=(170, 230, 255, 110), outline=(230, 250, 255, 255), width=4)
                lay.alpha_composite(ice_e, (int(p[0] + r_ * 0.5), int(p[1] - r_ * 1.1)))
            if b["burn"]:
                yb = int(p[1] - r_ - 30 + 6 * math.sin(t * 20))
                lay.alpha_composite(flame_e, (int(p[0] - r_ * 0.9), yb))
            if b["poison"] >= 1:
                lay.alpha_composite(skull_e, (int(p[0] + r_ * 0.55), int(p[1] + r_ * 0.3)))
                ld.text((p[0] + r_ * 0.55 + 34, p[1] + r_ * 0.3), f"x{int(b['poison'])}", font=A.font(30), fill=(150, 255, 90),
                        stroke_width=3, stroke_fill=(0, 0, 0))
        # lightning bolts
        for (bt, a_, b_, ow) in bolts:
            age = t - bt
            if 0 <= age < 0.22:
                pts = jag(a_, b_, random.Random(int(bt * 1000)), 10, 40)
                ld.line(pts, fill=(255, 255, 200, 255), width=7)
                ld.line(pts, fill=(255, 255, 255, 255), width=3)
                gd.line([(x / 2, y / 2) for x, y in pts], fill=(255, 230, 60), width=10)
        glow = glow.filter(ImageFilter.GaussianBlur(12)).resize((W, H), Image.BILINEAR)
        img = ImageChops.add(img, glow)
        img = img.convert("RGBA")
        for ft in flashes:
            if 0 <= t - ft < 0.08:
                img.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 230, 120)))
        if shake != (0, 0):
            lay = ImageChops.offset(lay, int(shake[0]), int(shake[1]))
        img.alpha_composite(lay)
        d = ImageDraw.Draw(img)
        fxlib.draw_hit_fx(d, hits, t)
        # damage / heal numbers
        for (nt, npos, txt, col) in nums:
            age = t - nt
            if 0 <= age < 0.8:
                fz = A.font(56)
                d.text((npos[0] - d.textlength(txt, font=fz) / 2 + 40, npos[1] - 110 - 90 * age), txt, font=fz, fill=col,
                       stroke_width=6, stroke_fill=(0, 0, 0))
        # HP bars + ability/level
        for k in range(2):
            b = f["balls"][k]
            info = ABIL[b["ab"]]
            x0 = 80 if k == 0 else W - 80 - 400
            y0 = 520
            d.rounded_rectangle((x0, y0, x0 + 400, y0 + 44), radius=22, fill=(40, 40, 52))
            if b["hp"] > 0:
                d.rounded_rectangle((x0, y0, x0 + 400 * b["hp"] / 100, y0 + 44), radius=22, fill=info["col"])
            lab = f"{int(math.ceil(b['hp']))}"
            d.text((x0 + 200 - d.textlength(lab, font=A.font(36)) / 2, y0 + 2), lab, font=A.font(36), fill=(255, 255, 255),
                   stroke_width=3, stroke_fill=(0, 0, 0))
            wl = f"{info['names'][b['lv'] - 1]}  LV{b['lv']}"
            we = fxlib.emoji_img(info["emoji"], 40)
            wx = x0 if k == 0 else x0 + 400 - d.textlength(wl, font=A.font(32)) - 50
            img.alpha_composite(we, (int(wx), y0 + 58))
            d = ImageDraw.Draw(img)
            d.text((wx + 48, y0 + 62), wl, font=A.font(32), fill=info["col3"] if b["lv"] == 3 else (230, 230, 240))
            if emo:
                e = fxlib.emoji_img(emo[k], 66)
                img.alpha_composite(e, (int(x0 + (10 if k == 1 else 330)), y0 - 76))
                d = ImageDraw.Draw(img)
        d.text((W / 2 - d.textlength("VS", font=A.font(56)) / 2, 506), "VS", font=A.font(56), fill=(255, 255, 255))
        A.draw_hook(d, hook)
        fxlib.draw_popups(img, popups, t)
        d = ImageDraw.Draw(img)
        if end_t and t >= end_t + 0.3:
            info = ABIL[abil[winner]]
            msg = f"{info['names'][frames[-1]['balls'][winner]['lv'] - 1]} WINS!"
            fz = A.font(110)
            while d.textlength(msg, font=fz) > 960:
                fz = A.font(fz.size - 6)
            d.text((W / 2 - d.textlength(msg, font=fz) / 2, CY - 60), msg, font=fz, fill=(255, 255, 255), stroke_width=9,
                   stroke_fill=(0, 0, 0))
        d.text((70, 150), "unreel", font=A.font(40), fill=(255, 255, 255))
        rgb = img.convert("RGB")
        ff.stdin.write(rgb.tobytes())
        if end_t and not ko_done and t >= end_t:
            ko_done = True
            for kf in fxlib.ko_frames(rgb, f["balls"][1 - winner]["p"], int(HOLD * FPS)):
                ff.stdin.write(kf.tobytes())
    A.close_ff(ff, out)
    return seed, total + HOLD, wname


if __name__ == "__main__":
    out = sys.argv[1]
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    pal = sys.argv[4] if len(sys.argv) > 4 else "neon"
    extra = sys.argv[5] if len(sys.argv) > 5 else ""
    hook_arg = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else ""
    if not hook_arg:
        _, ab = parse(extra, seed)
        hook_arg = f"{ab[0].upper()} VS {ab[1].upper()}|WHO WINS?"
    s, tot, w = render(out, seed, hook_arg.split("|"), pal, extra)
    print(f"done {out} seed={s} {tot:.1f}s winner={w}")
