# Unreel-videos

Rendered shorts for the Unreel channel, served to the scheduler via public raw links.
Videos in `videos/` are removed a few days after posting.

- `tools/setup.sh` – install voice engine + model
- `tools/render.py spec.json out.mp4` – render a 1080x1920 short (voice, captions, SFX)
- `tools/example.json` – example spec
- `tools/sim_ball.py out.mp4 [seed] ["LINE1|LINE2"]` – physics short: ball grows in a ring, note per bounce
