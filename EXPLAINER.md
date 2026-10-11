# Explainer videos (Unreel) – runbook for the scheduled task

Short explainer videos for the Unreel channel (1080×1920, 30 fps, 35–55 s, English). Topics (Dimi 2026-10-10: "whatever performs better"): **space & physics** (theme space) and **money / side hustles / AI tools / tech** (theme money or tech), same style. The nightly analysis decides the mix by views/shares/comments per topic category. Since 2026-10-10 explainers REPLACE the quiz format in the nightly task "Unreel Daily Short" (Dimi's decision). That task alternates EXPLAINER and PHYSICS days and posts directly (no approval). When run from the nightly task: do steps 2–6 and 8 here, but posting (platforms, budget, best times, captions, hosting, cleanup, report) follows the nightly task prompt instead of step 7/9.

**Explainers only (Dimi 2026-10-11):** the nightly task makes ONE explainer EVERY day, no physics/battle videos any more.
**Series order:** the next part of a series may only be posted at least 1 day AFTER the latest `post_time` of that SAME series in `state/explainer/log.json` (so Part N+1 never goes out before Part N). If the next series part can't go out yet, make a one-off explainer (or a part of another series) instead – never a physics video.

**AI label:** explainers use an AI voice → TikTok isAigc true, Instagram isAiGenerated true, YouTube isAiGeneratedContent false (no realistic synthetic footage).

## Every run, in this order
1. **Setup:** `bash tools/setup.sh` (installs the voice and downloads the model, takes about 1 min).
2. **Analyse (keep it cheap):**
   - Use Metricool analytics (brand 7288133, TikTok) to fetch the stats of the last explainer posts.
   - Enter them in `state/explainer/log.json` under "metrics".
   - Read `state/explainer/learnings.md`, and add 1–2 lines if something clearly worked or flopped (views, comments, watch time).
   - Run at most one WebSearch for what's trending in space/physics right now (a news event, a viral question).
3. **Pick the topic:**
   - If `log.json` has a `next_promised` (the last video teased "Part N: …"), that video comes first.
   - Otherwise take the top entry of `state/explainer/topics.md`, or a trending space/physics question if it is clearly better.
   - Prefer series of 3–4 parts with a cliffhanger at the end, because those drive follows.
   - Every 2nd new series may be a one-off video.
**Money / AI rules (strict):** only honest, realistic, concrete ways (skills, freelancing, selling things you make, saving, compound interest basics, how a business really earns). No get-rich-quick, no "passive income in 7 days", no crypto/forex/trading tips, no specific stocks, no gambling, no MLM/dropshipping hype, no fake income claims. Every number needs a source (e.g. official stats, platform payout pages) and realistic ranges ("most people earn little at first"). Never sound like financial advice; say "this is how it works", not "you should invest in X". No real persons as the main subject.

4. **Research:**
   - Check every claim with WebSearch/WebFetch, preferring NASA, ESA, Wikipedia or university sources.
   - Write `notes/<name>.md` with a table (claim | checked value | source) plus the deliberate simplifications.
   - No false or exaggerated claims. If a fact is unclear, leave it out.
5. **Script:** write `tools/explainer_<name>.json` (scene kinds and fields are documented in the header of `tools/explainer.py`; the black holes parts 1–3 are the examples).
   - Structure: hook (0–2 s), countdown "pause and guess" with 3 options, answer, 2–4 steps each with its own animation, compare and/or stat (aha fact), quiz ending with "Comment X" + "PART N+1: …" teaser (or a question for one-offs).
   - Spoken lines short, every 3–6 s something new. Don't sound like AI: no "Did you know", no "mind-blowing", no em dashes.
   - **Only use the existing animations:** hook anim blackhole/sun/star/emoji; step anims bars, forces, squeeze, balance, collapse, escape, redgiant, whitedwarf (space) and emoji, grow (any topic, e.g. money growth), tokens (NEW 2026-10-11: chat box + candidate words with filling bars, picked word flies in – for AI/decision topics); compare visuals stretch/calm/sun/bigstar; stat bg bh/earth/whitedwarf (or none: set "bg": "none"). Set "theme": "money" or "tech" for non-space topics. Emojis work for objects (🌍🪐☄️💸📱🧠💻).
   - A new animation only if a topic truly needs it, at most one per run. Add it to `tools/explainer.py` without breaking existing ones, and test it.
6. **Render:**
   - Draft: `python3 tools/explainer.py tools/explainer_<name>.json /tmp/d.mp4 --draft`.
   - Check ONE contact sheet: `ffmpeg -i /tmp/d.mp4 -vf "fps=1/2.5,scale=200:356,tile=9x2" -frames:v 1 /tmp/s.png`, then look at it. Fix overlapping text or empty frames.
   - Final: render without `--draft`, about 2.5 min. Check that the length is 35–60 s and loudness is about −14 LUFS (`ffmpeg -i f.mp4 -af ebur128 -f null -`).
7. **Post (TikTok, best time):**
   - Read `state/metricool_count.json`. If count < 50, post via Metricool. If count ≥ 50, Dimi posts himself (see below).
   - Time: Metricool getBestTimeToPostByNetwork tiktok for today (Europe/Berlin). Take the best hour that is at least 1 h from now and in the afternoon/evening (16–20 h); the morning slot belongs to the quiz task. If today is too late, use tomorrow 18:00.
   - Host: copy the MP4 to `videos/<date>-<name>.mp4`, commit and push to main. Media URL: `https://raw.githubusercontent.com/salem64/Unreel-videos/main/videos/<file>`. Check that it returns HTTP 200.
   - Call createScheduledPost: providers tiktok, autoPublish true, tiktokData.title = short casual title, isAigc true (AI voice).
   - Caption and first comment follow the caption rules in README.md (lowercase, max 1 emoji, "part N" at the end for series, 3–5 hashtags incl. #unreel).
   - Afterwards: increase count by 1, delete the MP4 from `videos/` again (Metricool has its own copy), commit and push.
   - If Metricool fails or the budget is used up: send the MP4 to Dimi + caption + first comment so he can upload it from his phone.
8. **Update state:**
   - Add the entry to `log.json` (date, name, title, series, part, file, post time, caption, next_promised).
   - Strike the topic in `topics.md` and add new ideas.
   - Commit + push to main.
9. **Report to Dimi (German, 3–5 lines):**
   - Which video, when it goes online, a one-sentence reason for the topic choice.
   - Send the MP4 along.
   - Mention any problems.

## Motion (Dimi 2026-10-11: "more interactive, more happening on screen")
Every video automatically gets the MOTION PACK (camera push-in + punch zoom on cuts, drifting particles, progress bar, word pop captions, sparkle bursts, pulsing glows, count-up numbers). On top of that, prefer animated scene types (tokens, grow, forces, squeeze, compare, stat) over plain single-emoji steps; aim for something visibly moving or changing every 2–3 s. When a topic needs a visual that doesn't exist yet, build it as today's NEW feature.

## Rules
- Never spend money; free tiers only.
- Never touch the nightly quiz/physics state except `metricool_count.json`.
- Don't reuse music or footage from others; everything is generated by the renderer.
- Stay with existing animations unless a new one is really needed (token cost).
