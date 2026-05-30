---
schema_version: 1
id: e25c22d40f509e7923baa43db88b19d5d95364807ede8859c38dd13ec867c0e8
title: Lie Derivative for Measure Learned Equivariance (in CNNs)
url: https://arxiv.org/abs/2210.02984
final_url: https://arxiv.org/abs/2210.02984
canonical_url: https://arxiv.org/abs/2210.02984
domain: arxiv.org
type: paper
tags: [equivariance, cnn, vision-transformer, deep-learning, lie-derivative]
added_at: 2026-03-28
last_fetched_at: 2026-03-28T00:00:00Z
last_success_at: 2026-03-28T00:00:00Z
created: 2026-03-28
last_updated: 2026-03-28
language: en
related: [geometric-deep-learning, symmetry, transformer]
parent_topic: ml-ai/computer-vision
visibility: private
status: ok
http_status: 200
content_type: text/html
content_hash: 4ca6656ed42d1695cb09cca6f0c1546a211001019f79340f8d65949a4cb33fbb
archive_path: 
classification_model: 
classification_prompt_version: v1
summary_model: 
source_kind: url
source_path: 
source_line: 
description: ArXiv paper on using Lie derivatives for learning equivariant representations in convolutional neural networks.
---

Summary:
<!-- bookmark-tools:summary:start -->
The paper introduces the Lie derivative as a principled, low-hyperparameter method for quantifying equivariance in deep learning models. Equivariance ensures that a model's internal representations transform predictably under data symmetries like translation or rotation.

Using the Lie derivative, the study evaluates hundreds of pretrained models including CNNs, vision transformers, and MLP-Mixers. The method reveals that equivariance is not solely determined by architecture—even models without explicit equivariant design can develop strong symmetry properties through training.

A key finding links equivariance violations to spatial aliasing caused by common operations such as pointwise non-linearities (e.g., ReLU). Contrary to the assumption that CNNs are inherently superior in equivariance, the results show that vision transformers often surpass them in learned equivariance post-training. "As models get larger and more accurate they tend to display more equivariance, regardless of architecture."
<!-- bookmark-tools:summary:end -->
