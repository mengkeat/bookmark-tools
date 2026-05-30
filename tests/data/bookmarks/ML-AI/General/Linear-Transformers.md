---
schema_version: 1
id: b9a213436a28a446984a51d2bc162ccef07f6762a593c8445944f46d8d564aae
title: Linear Transformers
url: https://desh2608.github.io/2021-07-11-linear-transformers/
final_url: https://desh2608.github.io/2021-07-11-linear-transformers/
canonical_url: https://desh2608.github.io/2021-07-11-linear-transformers/
domain: desh2608.github.io
type: article
tags: [transformer, linear-attention, efficient-transformer, attention]
added_at: 2026-03-28
last_fetched_at: 2026-03-28T00:00:00Z
last_success_at: 2026-03-28T00:00:00Z
created: 2026-03-28
last_updated: 2026-03-28
language: en
related: [linformer, performer, longformer]
parent_topic: ml-ai/general
visibility: private
status: ok
http_status: 200
content_type: text/html
content_hash: f0436c14ced1beeec73f4ddd934cf51d3ebd1c35f4dd2ff2838b1c3c8850af94
archive_path: 
classification_model: 
classification_prompt_version: v1
summary_model: 
source_kind: url
source_path: 
source_line: 
description: Explanation and implementation of linear transformers - efficient transformer variants with linear complexity.
---

Summary:
<!-- bookmark-tools:summary:start -->
Transformers have O(n²) time and memory complexity due to pairwise interactions in self-attention, limiting use with long sequences. Efficient transformers reduce this to O(n) through three main approaches: low-rank approximation, local-global attention, and kernel-based methods.

Low-rank methods like Linformer and Nystromformer exploit the empirical low-rank property of attention matrices. Local-global approaches like Longformer and BigBird combine sliding window attention with task-specific global attention.

Kernel-based methods reinterpret softmax attention as a kernel function. The "Transformers are RNNs" paper shows linear attention can be computed by updating a hidden state over time. Performers use FAVOR+ with positive orthogonal random features to approximate the softmax kernel. "Transformers are RNNs: Fast autoregressive transformers with linear attention" demonstrates linear attention can match full transformer performance.
<!-- bookmark-tools:summary:end -->
