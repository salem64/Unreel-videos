# 3D-sim "WHAT IF" videos (Unreel) – runbook
Current format since 2026-10-23 (format radar: 3D/sim animation with narrator voice is the most common
style among the strongest faceless science outliers; Dimi: "doesn't have to be pixel, make what performs").
Template: `tools/sim3d/earth_tunnel.py` (own numpy ray tracer, no GPU/Blender needed – Blender works but
Cycles takes ~5 s/frame on this machine, too slow). Voice: free local kokoro (`bash tools/setup.sh`),
lines in `tools/sim3d/<name>_lines.json`, generated with `tools/sim3d/tts_lines.py`; durations drive the timeline.

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
