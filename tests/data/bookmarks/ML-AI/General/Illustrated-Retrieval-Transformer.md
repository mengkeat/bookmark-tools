---
schema_version: 1
id: 23188f83a414084aedaa4def9056c8f2d993c76f199b52ab873b18846aa824b9
title: Illustrated Retrieval Transformer
url: https://jalammar.github.io/illustrated-retrieval-transformer/
final_url: https://jalammar.github.io/illustrated-retrieval-transformer/
canonical_url: https://jalammar.github.io/illustrated-retrieval-transformer/
domain: jalammar.github.io
type: article
tags: [transformer, retrieval, retro, deepmind, illustrated-guide]
added_at: 2026-03-28
last_fetched_at: 2026-03-28T00:00:00Z
last_success_at: 2026-03-28T00:00:00Z
created: 2026-03-28
last_updated: 2026-03-28
language: en
related: [llm, rag, attention-mechanism]
parent_topic: ml-ai/general
visibility: private
status: ok
http_status: 200
content_type: text/html
content_hash: 5fbcc0a03c1d08b8b13a1a5db1f8951a361c9b9880d372f5ac8359dfe8f357f5
archive_path: 
classification_model: 
classification_prompt_version: v1
summary_model: 
source_kind: url
source_path: 
source_line: 
description: Jay Alammar's illustrated guide to retrieval transformers - visual explanation of how retrieval-augmented transformers work.
---

Summary:
<!-- bookmark-tools:summary:start -->
DeepMind's RETRO (Retrieval-Enhanced TRansfOrmer) challenges the assumption that bigger models are always better. Despite having only 7.5 billion parameters—4% the size of GPT-3's Da Vinci model—RETRO achieves comparable performance by integrating retrieval mechanisms that access external knowledge.

RETRO decouples language understanding from factual knowledge by offloading storage to a separate database. It uses BERT to generate sentence embeddings that query a database of 2 trillion tokens, retrieving the two most similar text chunks for context.

Every third decoder block starting from layer 9 incorporates "chunked cross attention" (CCA), allowing the model to attend to retrieved neighbor-completion pairs. "The BERT sentence embedding is used to retrieve the nearest neighbors from RETRO's neural database. These are then added to the input of the language model."
<!-- bookmark-tools:summary:end -->
