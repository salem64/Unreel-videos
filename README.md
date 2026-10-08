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

## AI video queue (rendered automatically on Dimi's PC, RTX 4080 Super)
- PC side: Windows scheduled task "Unreel Worker" runs `pythonw.exe -s pc/worker.py --root <root> --auto` every 30 min while Dimi is logged in. It quietly exits when jobs/ is empty or the GPU is busy (gaming), otherwise renders all jobs and pushes them to queue/.
- REFILL RULE (night task): after posting, count queue videos (excluding test-*) + jobs/*.json. If that total is ≤ 1, write new jobs right away so that queue + jobs = 7 (same rules as the weekly planner: verified facts, "What if"/fact visuals, follow "Prompt rules for AI clips", job format in pc/worker.py docstring), commit "Refill AI jobs: <n> new", push. The PC renders them automatically the next time it is on and idle.
- Dimi's PC renders a weekly batch of 5–7 AI videos (ComfyUI: Wan 2.2 + MMAudio) in one session. Content direction: "What if…" and unbelievable-fact visuals (space, nature, animals, scale comparisons) that fit the Unreel niche – NOT glass/fruit ASMR (saturated), e.g. on Sunday. The PC never needs to run at night.
- `jobs/<id>.json` – prompts/specs for the PC (written by Claude before the batch).
- `queue/<id>.mp4` + `queue/<id>.json` – finished AI videos with metadata: {"topic", "caption", "first_comment", "youtube_title", "tiktok_title", "ai_label": true}.
- Night task: ignore queue files starting with `test-` (Dimi reviews those first). If `queue/` has at least one other video, post the oldest one (move it to `videos/`, use its metadata, AI label true) – at most one per day. If the queue is empty, use the cloud formats (quiz/physics) as usual. Mention in the report how many queue videos are left. If the queue is now empty or has only 1 video left, start the German report with a clear reminder: "⚠️ KI-Vorrat leer/fast leer – bitte am PC den Wochen-Batch starten." (only once AI videos have ever been in the queue, i.e. after the PC setup).

## Prompt rules for AI clips (jobs/*.json) – ALWAYS follow
Pipeline v2 (preferred, used automatically when a clip has "image_prompt" and the v2 models are installed): Z-Image Turbo renders a start frame from "image_prompt", Wan 2.2 14B animates it with "prompt" (576x1024, default mode "max" = full 20 steps without speed LoRAs for the best motion; set env UNREEL_V2_MODE=fast for the 4-step LoRAs), RIFE doubles the frame rate, MMAudio adds sound. Every clip MUST therefore have:
- "image_prompt": a detailed photorealistic still image description (vertical 9:16, lighting, every important object, the main subject exactly as it should look, its size and position in frame). This decides WHAT is seen.
- "prompt": ONLY the motion – camera move + what moves in the scene (rules below). This decides HOW it moves.
- "audio_prompt": natural sounds matching the scene.
Rules for "prompt" (and for v1 clips without image_prompt):
Wan 2.2 5B turns calm, photo-like descriptions into near-static images. Every clip prompt must:
1. Start with "Dynamic cinematic shot, vertical frame" and describe a clear camera move (forward drive/flight, orbit, tracking shot, push-in) that lasts the whole clip.
2. Contain at least 3 visible moving elements: e.g. clouds racing across the sky, trees/grass swaying strongly in wind, birds/animals moving, water waves, cars, particles, rotating objects.
3. Describe the main subject very concretely (shape, size, colors, position in frame, what it looks like up close) – never rely on a name alone ("planetary rings" alone became star trails; "one huge solid flat band of white and beige stripes arching across the sky like Saturn's rings" is better).
4. Prefer daylight or clearly lit scenes; avoid night-sky/star scenes (they render as long-exposure star trails).
5. Never write calm/still/serene/quiet/peaceful scenes. No people's faces or hands in close-up.
6. Use 2–3 clips per video with different camera moves, each clip a different angle on the same idea.

## ComfyUI workflow file
`pc/unreel_workflow_v2_api.json` (best quality) and `pc/unreel_workflow_api.json` (v1) are the exact graphs the worker sends to ComfyUI (Wan 2.2 5B text-to-video → MMAudio sound → SaveVideo), exported in API format. Drag it into the ComfyUI window to open it, edit the prompt and press Run to experiment manually. The worker builds this same graph in code (`workflow()` in pc/worker.py); keep both in sync if you change settings.
