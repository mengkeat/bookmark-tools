---
schema_version: 1
id: 282e83d29d28e3682af4d90d796207b161ad58ce66857e1e02c713f48b94985b
title: 'Understanding Diffusion Models: A Unified Perspective'
url: https://arxiv.org/abs/2208.11970
final_url: https://arxiv.org/abs/2208.11970
canonical_url: https://arxiv.org/abs/2208.11970
domain: arxiv.org
type: paper
tags: [diffusion-models, generative-ai, vae, score-based, theory]
added_at: 2026-03-28
last_fetched_at: 2026-03-28T00:00:00Z
last_success_at: 2026-03-28T00:00:00Z
created: 2026-03-28
last_updated: 2026-03-28
language: en
related: [generative-models, ddpm, imagen, dall-e]
parent_topic: ml-ai/diffusion
visibility: private
status: ok
http_status: 200
content_type: text/html
content_hash: 826d218fd18258f20d02c0f463145d04058b96310a8abb04b81e84da26dc3e92
archive_path: 
classification_model: 
classification_prompt_version: v1
summary_model: 
source_kind: url
source_path: 
source_line: 
description: ArXiv paper providing a unified perspective on diffusion models for generative AI.
---

Summary:
<!-- bookmark-tools:summary:start -->
This paper provides a comprehensive and unified view of diffusion models by bridging the variational and score-based perspectives. The authors derive Variational Diffusion Models (VDM) as a specific instance of a Markovian Hierarchical Variational Autoencoder, showing that three critical assumptions make the Evidence Lower Bound (ELBO) tractable and scalable.

The paper proves that optimizing a VDM is equivalent to training a neural network to predict one of three targets: the original input from its noisy version, the initial noise added during noisification, or the score function (gradient of the log-density) of the noisy data at any noise level. "Optimizing a VDM boils down to learning a neural network to predict one of three potential objectives."

The work explicitly links the variational autoencoder formulation of diffusion models with score-based generative modeling using Tweedie's Formula, demonstrating that minimizing the ELBO in VDM corresponds to score matching in the limit.
<!-- bookmark-tools:summary:end -->
