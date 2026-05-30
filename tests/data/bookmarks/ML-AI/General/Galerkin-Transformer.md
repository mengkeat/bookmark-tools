---
schema_version: 1
id: d188637c821d3c61b66d1091abf69fc688ffe93fbbc77427a88097676cdb1413
title: Galerkin Transformer
url: https://scaomath.github.io/blog/galerkin-transformer/
final_url: https://scaomath.github.io/blog/galerkin-transformer/
canonical_url: https://scaomath.github.io/blog/galerkin-transformer/
domain: scaomath.github.io
type: article
tags: [transformer, galerkin-method, operator-learning, pde, neural-operator]
added_at: 2026-03-28
last_fetched_at: 2026-03-28T00:00:00Z
last_success_at: 2026-03-28T00:00:00Z
created: 2026-03-28
last_updated: 2026-03-28
language: en
related: [attention-mechanism, scientific-computing, approximation-theory]
parent_topic: ml-ai/general
visibility: private
status: ok
http_status: 200
content_type: text/html
content_hash: fe391ec222f5473abd54d90caafc88ec2133dcf42927e58596fe2606c093a3ca
archive_path: 
classification_model: 
classification_prompt_version: v1
summary_model: 
source_kind: url
source_path: 
source_line: 
description: Blog post explaining the Galerkin Transformer architecture.
---

Summary:
<!-- bookmark-tools:summary:start -->
The Galerkin Transformer reinterprets the attention mechanism through approximation theory in Hilbert spaces. The core idea treats sequence length as analogous to discretization size in numerical methods for operator equations, enabling resolution-invariant representation.

The key insight is that linear attention (without softmax) can be interpreted as a Petrov-Galerkin projection. The columns of Q, K, and V matrices are treated as discretized basis functions rather than token embeddings. The operation Q(K^T V) approximates a bilinear form in infinite-dimensional Hilbert spaces.

The Galerkin Transformer outperformed Fourier Neural Operator (FNO) on PDE benchmarks including Burgers' equation and Darcy flow, achieving fourfold improvement in accuracy. "The approximation power depends on d_model, i.e., how many basis functions we are willing to pay to approximate an operator's responses."
<!-- bookmark-tools:summary:end -->
