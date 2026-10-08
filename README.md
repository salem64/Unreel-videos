# Unreel-videos

Rendered shorts for the Unreel channel, served to the scheduler via public raw links.
Videos in `videos/` are removed a few days after posting.

- `tools/setup.sh` – install voice engine + model
- `tools/render.py spec.json out.mp4` – render a 1080x1920 short (voice, captions, SFX)
- `tools/example.json` – example spec
- `tools/sim_ball.py out.mp4 [seed] ["LINE1|LINE2"]` – physics short: ball grows in a ring, note per bounce

## Posting flow (free tier)
- Metricool free plan: 50 posts/month, tracked in `state/metricool_count.json` (month, count). Reset count when the month changes.
- Night task (~03:53 Berlin): renders the video into `videos/`, then schedules via Metricool within budget: allowed today = floor((50 - count) / days left in month incl. today), max 2. Priority: TikTok, then YouTube. Instagram goes via vidIQ at midday (falls back to Metricool as 3rd priority if vidIQ has no Instagram account with publishingAvailable). Writes `videos/pending.json` (file, caption, first comment, titles) and sends Dimi the MP4 + YouTube title if YouTube was skipped (manual upload).
- Midday task (~11:53 Berlin): publishes `videos/pending.json` as an Instagram Reel via vidIQ (import raw URL with vidiq_video_upload, then vidiq_instagram_publish_reel), then deletes everything in `videos/` except `.gitkeep`.
