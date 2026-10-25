# 3D-sim "WHAT IF" videos (Unreel) – runbook
Current format since 2026-10-23 (format radar: 3D/sim animation with narrator voice is the most common
style among the strongest faceless science outliers; Dimi: "doesn't have to be pixel, make what performs").
Template: `tools/sim3d/earth_tunnel.py` (own numpy ray tracer, no GPU/Blender needed – Blender works but
Cycles takes ~5 s/frame on this machine, too slow). Voice: free local kokoro (`bash tools/setup.sh`),
lines in `tools/sim3d/<name>_lines.json`, generated with `tools/sim3d/tts_lines.py`; durations drive the timeline.

PACING RULES (Dimi 2026-10-23, v1 of air-gone was "nicht spannend"): big visual event within 1-1.5 s, a cut or sub-shot every
1.5-2 s (SPLIT dict in air_gone.py), voice speed 1.2, ~30 s, a different pose/prop/sticker per line, never a static frame.

Formula: hook question with the person already in danger in the first second (voice + big word-pop
captions with yellow keywords), live HUD pills (depth/speed/time/gravity/heat …) + mini-map, a cut every
3–5 s alternating wide sim shot ↔ POV close-up, whip flash + zoom punch on cuts, red edge pulse when it
gets dangerous, a myth bust, a payoff, and a 2-card choice question at the end ("WOULD YOU …?").
30–40 s, voice am_michael speed 1.1, music bed ducked under the voice, loudness ≈ −14 LUFS.

Reusable pieces in earth_tunnel.py: Cam (rays/project), space_bg star sky, earth_cutaway (layers, tunnel,
glowing dot), tunnel_pov (rushing rings, depth-coloured walls, heat shimmer), surface_scene (ground, hole,
sky), 3D cartoon character (char_prims + trace_prims + shade_char, toon shading + rim light), post (upscale,
bloom, vignette, red edge, flash, zoom), pill/bar_pill/minimap HUD, caption(), choice_cards(), build_audio().
New video: copy earth_tunnel.py to <name>.py, write <name>_lines.json, adapt scenes/HUD/keywords, run
`python3 tts_lines.py <name>_lines.json /tmp/<name>_vo`, then `python3 <name>.py sheet /tmp/s.png <times> --vo /tmp/<name>_vo`
(look once, fix), then `python3 <name>.py render ../../videos/<date>-sim3d-<name>.mp4 --vo /tmp/<name>_vo` (~9 min).
Note: the template reads `tunnel_lines.json` – change that filename in the copy.

## Second template: tools/sim3d/air_gone.py (street scene, 2026-10-23)
Use it for any "what if X happens in a normal city street" idea. New pieces: `street(t, air, cam, ch, extra, dim, vig)` renders road +
AABB buildings (`trace_boxes`, window pattern, fog that vanishes when air=0) + sky_color(D, air) (blue <-> star sky) + the 3D character;
`extra` takes world-space prims (sph/cap) e.g. `plane_prims`, `bird_prims`, bubbles; `cam_for(i,t)` holds one camera per line;
`overlays()` draws streaks, rings, MYTH stamp, BOOM; `hud()` pills; `build_audio()` mutes everything except the narrator between TA and TB
(silence gimmick) and adds `sfx_boom()`. Copy the file, change lines JSON name + `air_at`/TA/TB logic. Render ~12 min (1170 frames).
Check frames with `python3 air_gone.py sheet /tmp/s.png t1,t2,... --vo /tmp/air_vo` (~40 s for 21 frames).

## Third template: tools/sim3d/moon_gone.py (night / sky / ocean / space, 2026-10-24)
Use for "what if the Moon/Sun/Earth ..." ideas. New pieces: `night_sky(D, moon)` (textured moon disc + halo, stars), `night_street` (moon-dependent
ambient, lit windows, lamp pools; pass moon 0..1), `harbor(t, level, moon, cam, ch)` (quay + tide ruler + water at animated `level`; wet band under HIGH_MARK),
`space(t, cam, tilt, spin, moon_pos)` (Earth globe via iss_reel LAND/CLOUD textures, axis line, optional Moon sphere), `beetle_prims`, `draw_clock`.
Keep the street canyon open: lower BOXES[-1] and put MOON_D along the street axis (x=0) or the moon is hidden behind buildings.
Per-scene HUD pills in `hud()`, stickers in `overlays()`, cards in `choice_cards()` (correct answer = first card). Render ~12 min, 1110 frames.

## Fourth template: tools/sim3d/kitchen_fire.py (indoor kitchen / "NEVER do X", 2026-10-25)
Use it for indoor cooking/home-safety "never do X" ideas. Pieces: `ROOM` tagged boxes + `trace_room`/`room_color` (checker floor, backsplash tiles, window, soot on ceiling, fire-light that follows `st['firelight']`), `trace_pan` (analytic pan walls, oil disc, optional lid {'x','z'}),
`add_blob(img, cam, P, r, color, k, mode='add'|'mix', ay)` screen-space glow blobs used for `flame_blobs`, `steam_blobs`, `eruption_blobs` (fireball up to the ceiling + burning droplets + smoke), `state_at(t, i)` builds fire/heat/lid/blobs per time,
`inset()` side-view explainer card (sinking drop, steam bubble, x1,700 counter), char `grab` target (hand follows cup/lid). Keep blob k small (0.15-0.5) or the bloom washes the frame out. Render ~15 min, 1230 frames.
