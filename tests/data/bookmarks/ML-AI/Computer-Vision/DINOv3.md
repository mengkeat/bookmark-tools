---
schema_version: 1
id: bc09c139c8e97fad07b6d096536872d2d3564d4e9c796f389c91d21fae32f172
title: DINOv3
url: https://www.youtube.com/watch?v=oGTasd3cliM
final_url: https://www.youtube.com/watch?v=oGTasd3cliM
canonical_url: https://www.youtube.com/watch?v=oGTasd3cliM
domain: www.youtube.com
type: video
tags: [self-supervised-learning, vision-transformer, computer-vision, dino, representation-learning]
added_at: 2026-03-28
last_fetched_at: 2026-03-28T00:00:00Z
last_success_at: 2026-03-28T00:00:00Z
created: 2026-03-28
last_updated: 2026-03-28
language: en
related: [vit, self-distillation, ssl]
parent_topic: ml-ai/computer-vision
visibility: private
status: ok
http_status: 200
content_type: text/html
content_hash: 229fa389c0abf8da2d243dd5cc41244c04e4ab45d5507e943cbf4f7ad1477a04
archive_path: 
classification_model: 
classification_prompt_version: v1
summary_model: 
source_kind: url
source_path: 
source_line: 
description: DINOv3 (self-supervised vision transformer) video tutorial/explanation.
---

Summary:
<!-- bookmark-tools:summary:start -->
DINO (DIstillation with NO labels) is a powerful self-supervised learning approach using self-distillation. Two views of the same image—created through data augmentation—are processed by student and teacher networks with identical architectures. The student learns to match the teacher's output distribution using cross-entropy loss, while the teacher's weights are updated as a moving average of the student's weights.

DINO improves feature learning by using multiple crops: two large global views and several smaller local crops. DINOv2 expanded output dimensions to 128,000, used 142 million images, and introduced patch-level losses using Vision Transformers (ViTs).

DINOv3 introduces Gram anchoring to preserve spatial relationships between image patches. It computes a Gram matrix capturing cosine similarities between all patch token embeddings, with a new loss term encouraging the student's Gram matrix to match that of a frozen teacher model checkpointed at 200,000 steps. The result is cleaner, sharper self-similarity maps with better semantic structure.
<!-- bookmark-tools:summary:end -->
