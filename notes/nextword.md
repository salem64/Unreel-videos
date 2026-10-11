# How ChatGPT guesses the next word (one-off, theme tech) - 2026-10-11

| claim | checked value | source |
|---|---|---|
| LLMs like ChatGPT generate text one token at a time by predicting the next token | yes (autoregressive language model) | Brown et al. 2020 "Language Models are Few-Shot Learners"; OpenAI docs |
| 1 token ≈ 3/4 of an English word | "1 token is approximately three-quarters of a word"; 100 tokens ≈ 75 words | https://help.openai.com/en/articles/4936856-what-are-tokens-and-how-to-count-them |
| GPT-3 trained on ~300 billion tokens | "GPT-3 175B is trained with 300 Billion tokens" (175B parameters) | Brown et al. 2020; https://lambda.ai/blog/demystifying-gpt-3 |
| Randomness (sampling/temperature) -> same prompt can give different answers | yes, sampling with temperature > 0 | OpenAI API docs (temperature) |

Simplifications: "the sky is" percentages (62/21/9 %) are an illustrative EXAMPLE, labelled "Example" on screen, not measured values. "Googling" option: modern ChatGPT can also search the web, but the core text generation is still next-token prediction (hook says "one tiny trick", not "never searches"). Training is simplified to "learns which words usually follow which".
