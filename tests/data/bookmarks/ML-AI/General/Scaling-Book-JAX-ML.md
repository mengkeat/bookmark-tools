---
schema_version: 1
id: 667756c486cca6a088efb4126527ce2d1bce3d1cea031fc2f7ced19586e6b69b
title: How to Scale Your Model
url: https://jax-ml.github.io/scaling-book/
final_url: https://jax-ml.github.io/scaling-book/
canonical_url: https://jax-ml.github.io/scaling-book/
domain: jax-ml.github.io
type: book
tags: [scaling, distributed-training, tpu, gpu, jax, model-parallelism]
added_at: 2026-03-28
last_fetched_at: 2026-03-28T00:00:00Z
last_success_at: 2026-03-28T00:00:00Z
created: 2026-03-28
last_updated: 2026-03-28
language: en
related: [parallelism, optimization, efficiency]
parent_topic: ml-ai/general
visibility: private
status: ok
http_status: 200
content_type: text/html
content_hash: 7f9be62f0aa9b56ee5acc6fc19d179064ef051d7cef34184290b205c22684571
archive_path: 
classification_model: 
classification_prompt_version: v1
summary_model: 
source_kind: url
source_path: 
source_line: 
description: 'Book/guide on scaling machine learning models, particularly in JAX ecosystem.'
---

Summary:
<!-- bookmark-tools:summary:start -->
Three to four years ago, researchers could ignore hardware details. Today, even small LLMs operate so close to hardware limits that efficiency at scale is no longer optional. A 20% benchmark improvement is meaningless if it costs 20% lower hardware efficiency.

The core challenge is achieving strong scaling—doubling chips should halve training time. However, communication overhead limits this. The book introduces roofline analysis to understand performance constraints by compute, memory bandwidth, and communication.

The book covers the Transformer architecture quantitatively, four primary parallelism strategies (data, tensor, pipeline, expert), and memory-saving techniques like rematerialization and ZeRO optimizer sharding. "Given some number of chips, how do I train a model of a given size with a given batch size as efficiently as possible?" is framed as the central question.
<!-- bookmark-tools:summary:end -->
