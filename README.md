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
- Night task (~03:53 Berlin): renders the video into `videos/`, then schedules via Metricool within budget: allowed today = floor((50 - count) / days left in month incl. today), max 2; if that is 0 but posts are left, allowed = 1 (TikTok only). If Metricool refuses with a limit error, count = 50 for the rest of the month. Platforms without a Metricool post that day get a manual-upload block in the report (MP4 + caption + title) so Dimi can post from his phone in 1 minute. Priority: TikTok, then YouTube. Instagram goes via vidIQ at midday (falls back to Metricool as 3rd priority if vidIQ has no Instagram account with publishingAvailable). Writes `videos/pending.json` (file, caption, first comment, titles) and sends Dimi the MP4 + YouTube title if YouTube was skipped (manual upload).
- Instagram task (scheduled task id trig_01FCas76GxNu1YJNKdpDoRaX, one-shot): the night task sets its run time each day to Instagram's best hour (Metricool getBestTimeToPostByNetwork instagram) via update_trigger(run_once_at=<UTC>, enabled=true). It publishes `videos/pending.json` as an Instagram Reel via vidIQ (import raw URL with vidiq_video_upload, then vidiq_instagram_publish_reel), then deletes everything in `videos/` except `.gitkeep`.

## Formats (decided 2026-10-08 by Dimi: no AI-generated video, only well-designed quizzes + physics; ALWAYS VARY)
VARIETY RULE: never repeat the variant of the previous video; avoid any variant used in the last 3 videos unless the learning loop clearly favours it. Also vary theme/palette, hook wording and emoji sets every time.

QUIZ variants (tools/quiz.py):
- classic: 5 (sometimes 6) questions EASY → MEDIUM → HARD → EXPERT → IMPOSSIBLE, 4 options. Categories rotate: general knowledge, geography/capitals, science, space, animals, food, inventions, history (nothing tragic), sports facts, language/words.
- flags / picture: "visual": true on every question – big flag or emoji ("Which country's flag is this?", "What is this?").
- emoji puzzle: "visual": true, emoji combo in "emoji" (e.g. "🐝🍃" → Belief), "Guess the word/movie-free/phrase".
- this or that: 2 options with emojis ({"t": "Blue whale", "e": "🐋"}) – which is bigger/heavier/older/faster/hotter.
- true or false speed round: 8–10 questions, options ["True", "False"], "think": 2.
- mixed: mix of the above in one video.
Rules for all quizzes: every answer verified with WebSearch; exactly one clearly correct option; plausible wrong options; vary the correct letter; question ≤ 70 chars, options ≤ 22 chars; reveal_say = answer + short surprising extra (≤ 10 words); hooks vary ("Only 3% get 5/5", "Average person gets 2/5", "Name all 3 flags", "Bet you can't get 10/10").

PHYSICS variants (tools/physics.py <mode> …):
- escape (rings with gaps shatter), multiply (every escape = 2 more balls), grow (ball grows each bounce)
- battle (ball vs ball, growing swords, HP bars; fighters "red,blue" or emoji pairs like "🐶,🐱", "🔥,💧", "🍕,🍔")
- elimination (last ball inside wins; sets flags / animals / food / fruits / colors) – caption: "Pick your winner before it starts 👇"
The script prints the winner – never reveal it in caption/title.

## Trends, new ideas, humor
- Trend scan every night: one vidIQ call (alternate: vidiq_trending_videos for shorts / vidiq_instagram_tiktok_outlier_search for "quiz", "ball battle", "satisfying physics", "flag quiz" …) + WebSearch for currently viral short formats. Note in state/ideas.md which trending formats/hooks/mechanics could be copied in OUR style (never copy their footage, music or branding – only the idea/mechanic).
- Innovation day (every Sunday, or any night a trend clearly fits): build ONE new variant – a new physics mode (new file tools/<name>.py or a new mode in tools/arena.py, e.g. ball race, gravity maze, colour takeover, clock/hourglass, marble run, "every bounce = +1 ball") or a new quiz layout in tools/quiz.py (e.g. "odd one out", "guess the price", "would you rather", "finish the pattern"). Never break existing modes: test-render the old example + the new one, look at frames, and only commit if both work; otherwise revert (git checkout) and use an existing variant. Add the new variant to the variant list above and to state/ideas.md as "built".
- Humor: every video gets at least one funny touch – a cheeky hook ("Your teacher would be ashamed if you miss #1"), a funny reveal line ("Sydney is crying right now"), funny fighters/sets (🥔 vs 🍟, 🐌 vs 🐢), funny tiers ("0 = certified potato 🥔"), meme-style captions. Keep it friendly, no insults of groups, nothing political/sexual/tragic.

## Caption & comment style (must NOT sound AI-written) – overrides any example wording elsewhere
Write like a real 19-year-old running a meme/quiz page, not like a marketer:
- Short. Caption 1 line (max ~12 words) + hashtags. First comment max ~8 words.
- Mostly lowercase, casual, slang allowed sparingly (ngl, lowkey, fr, bro, nah, 💀). Max 1 emoji per text, sometimes none.
- NO typical AI phrases/patterns: no "Be honest…", "Did you know", "Can you guess", "mind-blowing", "Let's see", "Drop your answer below", "Test your knowledge", "Only true geniuses", no em dashes (—), no "…" at the end of every line, no rhetorical triple questions, no exclamation-mark spam.
- Sound like an opinion or reaction, not an instruction. Good: "q4 is actually evil", "i got 2/5 and im not ok", "blue got robbed fr", "nobody gets the last one", "the turnip one is cursed 💀", "pick a country before it starts". Bad: "Be honest… did you know the turnip one? 👀", "Comment your score below and challenge your friends! 🧠🔥".
- 3–5 hashtags only, no #fyp/#viral spam (#unreel + 2–4 specific ones).
- Vary wording every day; never reuse a caption or comment from the last 30 days (check performance.json / git log).
- YouTube title can be a bit cleaner but still casual ("only 3% get the last one #shorts").

## Learning what works (state/performance.json)
List of posts: {"date", "file", "format" (quiz|physics), "variant" (quiz category or physics mode), "hook", "theme", "metrics": {platform: {views, likes, comments, shares, saves}}}.
Night task: update metrics of posts from the last 14 days (Metricool analytics, vidIQ Instagram insights), then choose today's format: with < 6 measured posts alternate quiz/quiz/physics with different categories/variants; afterwards ~70 % the format/variant with the best average views (and shares/comments) per post, ~30 % something else to keep testing. Never the same quiz category twice in a row. Use at most one vidIQ trending call per night for topic ideas.

## AI video pipeline (retired)
`pc/` (ComfyUI worker, installers) is no longer used; no new jobs are written. The PC is not needed for anything.
