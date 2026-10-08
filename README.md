# Unreel-videos

Rendered shorts for the Unreel channel, served to the scheduler via public raw links.
Videos in `videos/` are removed a few days after posting.

- `tools/setup.sh` – install voice engine + model
- `tools/quiz.py spec.json out.mp4` – MAIN FORMAT: multiple-choice quiz short (voice, 4 options, countdown, green reveal + confetti, music bed, SFX). Spec format in the file header, example `tools/quiz_example.json`.
- `tools/physics.py <escape|multiply|grow> out.mp4 [seed] ["LINE1|LINE2"] [neon|sunset|ice|candy|lime]` – satisfying physics shorts (auto-picks a seed with 15–45 s length and an early first escape)
- `tools/sim_ball.py` – the "grow" physics variant (used by physics.py grow)
- `tools/render.py` – older text/fact renderer (not used any more)

## Posting flow (free tier)
- Metricool free plan: 50 posts/month, tracked in `state/metricool_count.json` (month, count). Reset count when the month changes.
- Night task (~03:53 Berlin): renders the video into `videos/`, then schedules via Metricool within budget: allowed today = floor((50 - count) / days left in month incl. today), max 2. Priority: TikTok, then YouTube. Instagram goes via vidIQ at midday (falls back to Metricool as 3rd priority if vidIQ has no Instagram account with publishingAvailable). Writes `videos/pending.json` (file, caption, first comment, titles) and sends Dimi the MP4 + YouTube title if YouTube was skipped (manual upload).
- Instagram task (scheduled task id trig_01FCas76GxNu1YJNKdpDoRaX, one-shot): the night task sets its run time each day to Instagram's best hour (Metricool getBestTimeToPostByNetwork instagram) via update_trigger(run_once_at=<UTC>, enabled=true). It publishes `videos/pending.json` as an Instagram Reel via vidIQ (import raw URL with vidiq_video_upload, then vidiq_instagram_publish_reel), then deletes everything in `videos/` except `.gitkeep`.

## Formats (decided 2026-10-08 by Dimi: no AI-generated video, only well-designed quizzes + physics)
QUIZ (quiz.py) – categories rotate: general knowledge, geography/capitals, flags ("Which country's flag is this?" with the flag emoji), science, space, animals, food, inventions, history (nothing tragic), true-or-false (2 options), "which is bigger/older/faster".
- 5 questions (sometimes 6), levels EASY → MEDIUM → HARD → EXPERT → IMPOSSIBLE ("each question gets harder").
- Every answer verified with WebSearch; exactly one clearly correct option; 3 plausible wrong options; vary the correct letter (never the same letter twice in a row); question ≤ 70 chars, options ≤ 22 chars.
- One fitting emoji per question; hook varies ("Only 3% get 5/5", "Average person gets 2/5", "Your brain age if you get all 5"); theme preset differs from the last quiz.
- reveal_say: answer + a short surprising extra fact (≤ 10 words).
PHYSICS (physics.py) – variants escape / multiply / grow, palette and hook vary.

## Learning what works (state/performance.json)
List of posts: {"date", "file", "format" (quiz|physics), "variant" (quiz category or physics mode), "hook", "theme", "metrics": {platform: {views, likes, comments, shares, saves}}}.
Night task: update metrics of posts from the last 14 days (Metricool analytics, vidIQ Instagram insights), then choose today's format: with < 6 measured posts alternate quiz/quiz/physics with different categories/variants; afterwards ~70 % the format/variant with the best average views (and shares/comments) per post, ~30 % something else to keep testing. Never the same quiz category twice in a row. Use at most one vidIQ trending call per night for topic ideas.

## AI video pipeline (retired)
`pc/` (ComfyUI worker, installers) is no longer used; no new jobs are written. The PC is not needed for anything.
