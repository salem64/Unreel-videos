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
- Instagram task (scheduled task id trig_01FCas76GxNu1YJNKdpDoRaX, one-shot): the night task sets its run time each day to Instagram's best hour (Metricool getBestTimeToPostByNetwork instagram) via update_trigger(run_once_at=<UTC>, enabled=true). It publishes `videos/pending.json` as an Instagram Reel via vidIQ (import raw URL with vidiq_video_upload, then vidiq_instagram_publish_reel), then deletes everything in `videos/` except `.gitkeep`.

## AI video queue (rendered weekly on Dimi's PC, RTX 4080 Super)
- Dimi's PC renders a weekly batch of 5–7 AI videos (ComfyUI: Wan 2.2 + MMAudio) in one session, e.g. on Sunday. The PC never needs to run at night.
- `jobs/<id>.json` – prompts/specs for the PC (written by Claude before the batch).
- `queue/<id>.mp4` + `queue/<id>.json` – finished AI videos with metadata: {"topic", "caption", "first_comment", "youtube_title", "tiktok_title", "ai_label": true}.
- Night task: if `queue/` has at least one video, post the oldest one (move it to `videos/`, use its metadata, AI label true) – at most one per day. If the queue is empty, use the cloud formats (quiz/physics) as usual. Mention in the report how many queue videos are left. If the queue is now empty or has only 1 video left, start the German report with a clear reminder: "⚠️ KI-Vorrat leer/fast leer – bitte am PC den Wochen-Batch starten." (only once AI videos have ever been in the queue, i.e. after the PC setup).
