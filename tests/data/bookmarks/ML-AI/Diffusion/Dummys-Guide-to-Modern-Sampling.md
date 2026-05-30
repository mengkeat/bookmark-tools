---
schema_version: 1
id: cd73823966faf0ae821098e9a364947f720426b4c4409292774e16b849c32068
title: Dummys guide to modern sampling
url: https://rentry.co/samplers
final_url: https://rentry.co/samplers
canonical_url: https://rentry.co/samplers
domain: rentry.co
type: reference
tags: [llm, sampling, temperature, tokenization, generation]
added_at: 2026-03-28
last_fetched_at: 2026-03-28T00:00:00Z
last_success_at: 2026-03-28T00:00:00Z
created: 2026-03-28
last_updated: 2026-03-28
language: en
related: [llm-inference, text-generation]
parent_topic: ml-ai/diffusion
visibility: private
status: ok
http_status: 200
content_type: text/html
content_hash: 560371eb7681baaebc8f4484dc1aad5bb2ee849b3f39eb2a8ddea9f8a4c70526
archive_path: 
classification_model: 
classification_prompt_version: v1
summary_model: 
source_kind: url
source_path: 
source_line: 
description: 'Guide/tutorial on modern sampling techniques, likely for machine learning and statistics.'
---

Summary:
<!-- bookmark-tools:summary:start -->
Large Language Models (LLMs) generate text by predicting the next token in a sequence based on patterns learned during training. A token can be a whole word, a sub-word, or a character. LLMs use sub-word tokenization (like Byte Pair Encoding or SentencePiece) to balance efficiency and flexibility.

Core sampling methods include:
- **Temperature** scaling: Low temperatures (<1.0) sharpen peaks, high temperatures (>1.0) flatten the distribution
- **Top-K** sampling: Limits selection to the K most likely tokens
- **Top-P (nucleus sampling)**: Dynamically selects the smallest set of tokens whose cumulative probability exceeds threshold P
- **Min-P**: Sets a floor relative to the highest probability token
- **Mirostat**: Acts like a thermostat, dynamically adjusting surprisal threshold to maintain consistent unpredictability

The order in which samplers are applied significantly impacts results. "Mirostat keeps text generation at a consistent level of unpredictability by dynamically adjusting how conservative or creative the sampling is."
<!-- bookmark-tools:summary:end -->
