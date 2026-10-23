# Pixel story videos (Unreel) – runbook

**Since 2026-10-23 (Dimi's decision): the daily Unreel video is a PIXEL STORY video** – retro 8-bit look,
no voice, chiptune + sound effects, typewriter captions. It replaces the voiced explainers (`EXPLAINER.md`
is kept for reference only). Reference style: an Instagram reel where a girl has an allergic reaction,
a live "AIRWAY OPEN %" meter drops, a magnifier zooms into throat and thigh, the EpiPen saves her,
and it ends with a 2-option choice prompt. Copy only the MECHANICS, never that topic, art or text.

Dimi's feedback that defines the format:
- 2026-10-22 Venus video (planet spinning, slow day counter, no character): "too boring, didn't watch to
  the end, the others are much more energetic". → NEVER again: static planets, counters running > 3 s,
  scenes where nothing happens to a person.
- 2026-10-23 helmet-crack video (astronaut in danger, live meters, magnifier cut-ins, alarm, rescue):
  approved, "post this kind of video from now on". → `tools/pixel/helmet_reel.py` is THE template.

## The formula (every video)
1. **0–1 s: a person in danger + a question.** e.g. "HIS HELMET JUST CRACKED. / HOW LONG DOES HE HAVE?"
   Alarm sound, white flash, camera punch-in, screen shake, red pulsing border.
2. **Live stakes meters** the whole time (HUD panels): something dropping (pressure, oxygen, body temp,
   blood sugar, altitude, battery …) + a running timer. The viewer must want to see where it ends.
3. **Magnifier cut-ins** (circle with connector line to the body part / object), a new one every 3–5 s,
   each showing the mechanism happening (lungs inflating, bubbles boiling, oxygen dots fading …).
4. **One myth bust / twist** ("BUT NO, HE WON'T POP.", "BLOOD DOESN'T BOIL").
5. **Climax + rescue**: blackout/darkening, heartbeat speeding up, then the fix/rescue, meters go green,
   bright music. Always a happy, hopeful ending (nobody dies, nothing gory).
6. **Ending: 2-option choice prompt** ("YOUR HELMET CRACKS. / FIRST THING YOU DO?" → [ ] A / [▶] B),
   the right answer gets selected. Drives comments.
- Length 25–35 s. Something visibly changes every 2–3 s. Caption lines ≤ 24 characters, typed at 40 cps,
  big 2× words (`sc` = 2, ≤ 13 characters) for the 2–3 key moments.
- Music 140–160 bpm minor while in danger, switches to major after the rescue. SFX on every event
  (alarm beeps, crack, hiss, pops, heartbeat, whoosh on cut-ins, clang, success arpeggio, typing blips).

## Topic rules
- Survival / body / space / physics situations with a real mechanism and a correct "what to do".
  Ideas: fighter pilot pulls 9 G and blacks out (G-suit + strain), astronaut drifts off the ISS (SAFER
  jetpack), diver comes up too fast (the bends), climber in the 8,000 m death zone, lightning storm
  (why a car protects you), stranded at sea (why seawater makes thirst worse), capsule re-entry (heat
  shield, plasma radio blackout), ice-water fall (1-10-1 rule), brain freeze, rollercoaster loop.
  New ideas go into `state/pixel/topics.md`.
- Every fact checked with WebSearch/WebFetch (NASA, ESA, university, government, Wikipedia, medical
  bodies). `notes/<name>.md`: claim | checked value | source. Round numbers with "~" when sources vary.
  Safety advice must be correct; if unsure, leave it out. No real people, nothing political, no gore,
  nobody dies, no copied characters/logos.
- Never repeat a topic or hook (check `state/pixel/log.json`).

## How to build one
1. `cp tools/pixel/helmet_reel.py tools/pixel/<name>_reel.py` and adapt it. It imports the engine from
   `tools/pixel/iss_reel.py` (pixel font `text()`, `panel()`, `space()` starfield, `draw_globe()`,
   `outline_rgba()`, cabin scene `scene_cabin()`, simple astronaut `astronaut()`), so run it from that folder.
   Change: timeline constants, `CAPS`, state curves (meter functions), character sprite(s) (`suit()` is an
   example of building a sprite with PIL primitives + `outline_rgba`), background scene (`wide()`), the
   magnifier contents (`zoom_*()`, 101×101 px), `draw_hud()`, the options and `build_audio()` event times.
   Keep: 180×320 canvas scaled 6× nearest-neighbour, `camera()`, `danger_border()`, `shake()`, flashes,
   `apply_mag()`, `draw_caption()`, the render/ffmpeg pipeline.
2. Contact sheet: `cd tools/pixel && python3 <name>_reel.py sheet /tmp/s.png 0.3,1.2,...` (12–14 times,
   one per beat) and look at it ONCE: text inside the caption box (≤ 24 chars), HUD panels not off-screen,
   magnifier readable, nothing empty. Fix, then check only the fixed frames.
3. Render: `python3 <name>_reel.py render ../../videos/<YYYY-MM-DD>-pixel-<name>.mp4` (~30 s).
   ffprobe: 1080×1920, audio present, 25–40 s.
4. Every day ONE new thing for the engine (new sprite, new magnifier content, new effect, new sound,
   new transition) – note it in `state/ideas.md` "Built".

## Labels
No AI voice any more. Keep the platform labels conservative: TikTok isAigc true, Instagram
isAiGenerated true, YouTube isAiGeneratedContent false (no realistic synthetic footage).
