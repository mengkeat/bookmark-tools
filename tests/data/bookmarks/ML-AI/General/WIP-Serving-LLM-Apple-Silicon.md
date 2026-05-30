---
schema_version: 1
id: c050e190dad5877116fb73b3475571dc779200c8c9c78317dbb85b70304f4e4b
title: Course on Serving LLM on Apple Silicon for System Engineers
url: https://github.com/skyzh/tiny-llm
final_url: https://github.com/skyzh/tiny-llm
canonical_url: https://github.com/skyzh/tiny-llm
domain: github.com
type: course
tags: [llm-inference, apple-silicon, mlx, serving, system-engineering]
added_at: 2026-03-28
last_fetched_at: 2026-03-28T00:00:00Z
last_success_at: 2026-03-28T00:00:00Z
created: 2026-03-28
last_updated: 2026-03-28
language: en
related: [kv-cache, flash-attention, continuous-batching]
parent_topic: ml-ai/general
visibility: private
status: ok
http_status: 200
content_type: text/html
content_hash: da67cf285dc41a15811b9b8991a0bc7d1416e4cc5c016ea8d9584d9684ef33b3
archive_path: 
classification_model: 
classification_prompt_version: v1
summary_model: 
source_kind: url
source_path: 
source_line: 
description: Work-in-progress course/repository on serving Large Language Models on Apple Silicon hardware for system engineers.
---

Summary:
<!-- bookmark-tools:summary:start -->
tiny-llm is an educational project for systems engineers to learn LLM inference serving on Apple Silicon using MLX. The course guides participants through building a minimal version of vLLM using only low-level MLX array and matrix operations, avoiding high-level neural network APIs.

The curriculum spans three weeks: Week 1 implements core model components (attention, RoPE) in pure Python; Week 2 builds an inference system with KV caching, continuous batching, and flash attention; Week 3 explores external system integration.

"The goal is to learn the techniques behind efficiently serving a large language model." The project uses Qwen2 as the model and includes a companion book at https://skyzh.github.io/tiny-llm/. MLX makes LLM serving education more approachable compared to NVIDIA GPU tooling complexity.
<!-- bookmark-tools:summary:end -->
