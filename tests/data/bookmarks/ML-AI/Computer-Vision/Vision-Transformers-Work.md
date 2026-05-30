---
schema_version: 1
id: 4c4e437ee78c8b711f4de4ac342938048321e6f5fee3a79e53c35a356d635648
title: How Do Vision Transformers Work?
url: https://paperswithcode.com/paper/how-do-vision-transformers-work-1
final_url: https://paperswithcode.com/paper/how-do-vision-transformers-work-1
canonical_url: https://paperswithcode.com/paper/how-do-vision-transformers-work-1
domain: paperswithcode.com
type: paper
tags: [vision-transformer, attention, computer-vision, deep-learning, generalization]
added_at: 2026-03-28
last_fetched_at: 2026-03-28T00:00:00Z
last_success_at: 2026-03-28T00:00:00Z
created: 2026-03-28
last_updated: 2026-03-28
language: en
related: [vit, cnn, attention-mechanism]
parent_topic: ml-ai/computer-vision
visibility: private
status: ok
http_status: 200
content_type: text/html
content_hash: b5648523620a6726db9932bdf9a108fa86e62b1cb20ae2b44986d9c19973c65a
archive_path: 
classification_model: 
classification_prompt_version: v1
summary_model: 
source_kind: url
source_path: 
source_line: 
description: Paper explaining the inner workings of Vision Transformers (ViTs) for computer vision tasks.
---

Summary:
<!-- bookmark-tools:summary:start -->
The paper investigates the mechanisms behind the success of multi-head self-attention (MSA) in computer vision. It reveals that MSAs enhance both accuracy and generalization by flattening the loss landscape, a property that makes optimization easier and improves model robustness.

The authors find that MSAs and convolutional layers (Convs) exhibit fundamentally opposite behaviors. MSAs act as low-pass filters, preserving global structure and suppressing high-frequency noise, while Convs function as high-pass filters, emphasizing local details and edges. This contrast indicates that the two components are complementary rather than redundant.

The paper proposes AlterNet, a novel architecture that replaces the final convolutional blocks in each stage with MSA blocks. AlterNet outperforms CNNs not only in large data regimes but also in small data regimes, demonstrating the broad effectiveness of this design.
<!-- bookmark-tools:summary:end -->
