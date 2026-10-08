# Unreel-videos

Rendered shorts for the Unreel channel, served to the scheduler via public raw links.
Videos in `videos/` are removed a few days after posting.

- `tools/setup.sh` – install voice engine + model
- `tools/render.py spec.json out.mp4` – render a 1080x1920 short (voice, captions, SFX)
- `tools/example.json` – example spec
- `tools/sim_ball.py out.mp4 [seed] ["LINE1|LINE2"]` – physics short: ball grows in a ring, note per bounce

## Posting flow (free tier)
- Night task (~03:53 Berlin): renders the video into `videos/`, schedules **TikTok** via Metricool (only while `state/metricool_count.json` count < 19 for the current month), writes `videos/pending.json` with caption/titles for the midday task, and sends the MP4 + YouTube title to Dimi for a manual YouTube upload.
- Midday task (~11:53 Berlin): publishes `videos/pending.json` as an Instagram Reel via vidIQ, then deletes everything in `videos/` except `.gitkeep`.
