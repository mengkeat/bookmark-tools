---
schema_version: 1
id: c30cd24ce2b48c689e50468f27833c1e976840e6a2c4e4dd575f6b6e7135c90f
title: JAX Autodiff Cookbook
url: https://jax.readthedocs.io/en/latest/notebooks/autodiff_cookbook.html
final_url: https://jax.readthedocs.io/en/latest/notebooks/autodiff_cookbook.html
canonical_url: https://jax.readthedocs.io/en/latest/notebooks/autodiff_cookbook.html
domain: jax.readthedocs.io
type: documentation
tags: [jax, autodiff, gradient, automatic-differentiation, deep-learning]
added_at: 2026-03-28
last_fetched_at: 2026-03-28T00:00:00Z
last_success_at: 2026-03-28T00:00:00Z
created: 2026-03-28
last_updated: 2026-03-28
language: en
related: [hessian, jacobian, optimization]
parent_topic: ml-ai/general
visibility: private
status: ok
http_status: 200
content_type: text/html
content_hash: 397eb3785947967a35fe4ce31e0b4e60d7f03c169ae5c2fa8fd77eb4eb06da36
archive_path: 
classification_model: 
classification_prompt_version: v1
summary_model: 
source_kind: url
source_path: 
source_line: 
description: JAX documentation on automatic differentiation with practical examples and notebooks.
---

Summary:
<!-- bookmark-tools:summary:start -->
JAX provides a powerful automatic differentiation system enabling efficient computation of gradients, Jacobians, Hessians, and higher-order derivatives. The core function `grad` transforms a scalar function into one that computes its gradient, supporting repeated application for higher-order derivatives.

A key advanced feature is the Hessian-vector product (HVP), implemented efficiently via `grad` of a gradient-dot-vector function, avoiding full Hessian materialization—crucial for networks with millions of parameters. JAX offers `jacfwd` and `jacrev` for full Jacobian matrices, with forward-mode efficient for "tall" Jacobians and reverse-mode for "wide" ones.

The foundational primitives are `jvp` (Jacobian-vector product) for forward-mode with constant memory cost, and `vjp` (vector-Jacobian product) for reverse-mode essential in deep learning. Using `vmap`, JAX can batch these operations to compute Jacobian-matrix products efficiently.
<!-- bookmark-tools:summary:end -->
