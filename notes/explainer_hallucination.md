# How AI works PART 2: why AI makes stuff up (2026-10-12)

| claim | checked value | source |
|---|---|---|
| Language models predict the next word/token from patterns, not from a fact lookup | yes (part 1 basis) | Axios 2025-06-04 "Why AI is still making things up" |
| When they lack an answer they tend to guess instead of saying "I don't know" | yes; researchers say hallucinations may never be fully eliminated | Axios 2025-06-04; Anthropic dev guide suggests allowing "I don't know" |
| Many benchmarks/tests give 0 for "I don't know" but credit a lucky guess, so guessing is rewarded in training/eval | OpenAI research "Why language models hallucinate" (Sep 2025), phrased as "many tests" (page not fetchable tonight, claim kept general) | OpenAI 2025 / arXiv 2509.04664 |
| NY lawyers filed a brief with fake ChatGPT cases, were fined $5,000 | $5,000 fine | Bloomberg Law 2023 "Phony ChatGPT Brief Leads to $5,000 Fine for NY Lawyers" (Mata v. Avianca) |
| Example citation "Dr. Alan Fennick" | fictional, made up for the demo on purpose (shown as MADE UP) | n/a |

Simplifications: "sounds most likely" = highest probability next token; "I don't know scores zero" is true for many (not all) tests.
