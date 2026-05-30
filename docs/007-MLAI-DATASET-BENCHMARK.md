# ML-AI Personal Dataset Benchmark Report

**Date:** 2026-05-30  
**Git SHA:** `deeda20ce98f` / `7a5d048`  
**Corpus:** 47 real bookmark notes across 6 ML-AI subfolders (schema v1)  
**Test dataset:** `tests/data/bookmarks/ML-AI/`  
**Eval fixtures:** 16 classification cases, 18 search queries, 1 e2e case  
**Mode:** Heuristic classification (no LLM); BM25 search (no embeddings)  
**Unit test status:** 396 passed, 7 subtests passed

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Test Corpus Description](#2-test-corpus-description)
3. [Classification Benchmark](#3-classification-benchmark)
4. [Search Retrieval Benchmark](#4-search-retrieval-benchmark)
5. [End-to-End Benchmark](#5-end-to-end-benchmark)
6. [Comparison with Previous Benchmarks](#6-comparison-with-previous-benchmarks)
7. [Recommendations](#7-recommendations)
8. [Snapshot File Inventory](#8-snapshot-file-inventory)

---

## 1. Executive Summary

This report presents the first evaluation of the bookmark-tools pipeline against a real, personalized dataset of 47 ML-AI bookmark notes. Previous benchmarks used either BEIR public datasets (nfcorpus, scifact) or a minimal 3-case classification fixture against a synthetic vault. The new dataset provides a grounded test of how the system performs in its intended domain.

### Key findings

| Suite | Metric | Score | Assessment |
|-------|--------|-------|------------|
| Classification (16 cases) | Folder accuracy | 62.5% | Moderate — topic-specific folders work well; general-purpose and cross-domain folders are weak |
| Classification (16 cases) | Type accuracy | 50.0% | Poor — heuristic defaults to `article` for everything |
| Classification (16 cases) | Tag F1 | 30.8% | Low — tags overgenerate from content tokens, diluting precision |
| Search BM25 (18 queries) | MRR | 0.806 | Strong — first relevant result is usually at rank 1 |
| Search BM25 (18 queries) | Recall@5 | 69.0% | Good — most relevant documents found in top 5 |
| Search BM25 (18 queries) | NDCG@5 | 0.711 | Good — ranking quality is solid for keyword queries |
| E2E (1 case) | All metrics | 100% | Perfect — deterministic smoke test passes |

### Technical Summary (Postgrad)

The heuristic classification pipeline demonstrates a characteristic asymmetric error profile: folder assignment relies on token-overlap similarity against a 47-note profile, yielding high accuracy for topically coherent subfolders (Diffusion, RL, Agents) but failing for cross-domain content that lacks discriminative vocabulary. The BM25 retrieval pipeline, operating on a small but domain-focused corpus, achieves MRR=0.806 and NDCG@5=0.711, consistent with BM25's well-documented strength on keyword-matching tasks in domain-specific corpora. The recall ceiling at 69.0% reflects the limitation of bag-of-words matching for semantic queries where relevant documents use different terminology than the query.

### Plain-Language Summary (Layman)

We tested the bookmarking tool against a collection of 47 real bookmarks about machine learning and AI topics, organized into 6 folders. Here's what we found:

- **Sorting into folders:** The tool correctly chose the right folder about 63% of the time. It's great at recognizing specific topics like "Reinforcement Learning" or "Diffusion Models" but gets confused when content could fit multiple places.
- **Picking the right type** (article, tutorial, course, etc.): The tool only got this right 50% of the time because, without AI help, it defaults to calling everything an "article."
- **Tagging:** Tags were only moderately useful — the tool tends to add too many generic tags, which dilutes the quality.
- **Search:** When searching through the bookmarks, the tool found what you were looking for about 81% of the time on the first try — this is quite good. About 69% of all relevant results appeared in the top 5 search results.

---

## 2. Test Corpus Description

### 2.1 Technical Description (Postgrad)

The test corpus comprises 47 bookmark notes sourced from a real Obsidian vault (`~/code/obsidian-vault/Vault/Bookmarks/ML-AI/`), converted to schema v1 format. Each note contains 30 frontmatter fields, a generated summary block, and conforms to the project's schema v1 validation.

**Corpus statistics:**

| Property | Value |
|----------|-------|
| Total notes | 47 |
| Subfolders | 6 (Agents, Computer-Vision, Diffusion, General, LLMs, Reinforcement-Learning) |
| Unique tags | 132 |
| Unique domains | ~40 |
| Date range | All created 2026-03-28 (batch import) |
| Note types | article (15), reference (7), paper (6), course (6), tutorial (5), tool (2), book (2), video (2), documentation (1), newsletter (1) |
| Visibility | All `private` |
| Language | All `en` |

**Folder distribution:**

| Folder | Notes | Types |
|--------|-------|-------|
| ML-AI/General | 28 | article (12), reference (5), tutorial (3), course (2), paper (1), tool (2), book (1), documentation (1), video (1) |
| ML-AI/LLMs | 6 | reference (2), course (2), tutorial (1), course (1) |
| ML-AI/Computer-Vision | 6 | paper (4), video (2), article (1) |
| ML-AI/Diffusion | 3 | course (1), paper (1), reference (1) |
| ML-AI/Reinforcement-Learning | 3 | article (1), book (1), course (1) |
| ML-AI/Agents | 1 | newsletter (1) |

The distribution is heavily skewed toward `ML-AI/General` (60% of notes), which creates a classification challenge: the General folder is a heterogeneous catch-all, while niche folders (Agents, Diffusion, RL) have very few exemplars for similarity-based routing.

### 2.1 Plain-Language Description (Layman)

We took 47 real bookmarks from a personal collection about machine learning and AI topics. These bookmarks point to all sorts of resources: blog posts, academic papers, video tutorials, online courses, GitHub repositories, and more.

The bookmarks are organized into 6 topic-based folders:

- **General** (28 bookmarks) — The largest folder, covering broad ML topics like neural networks, JAX, GPU computing, and statistics
- **LLMs** (6 bookmarks) — Resources about large language models like ChatGPT
- **Computer Vision** (6 bookmarks) — About image understanding and visual AI
- **Diffusion** (3 bookmarks) — About the AI technique behind image generators like DALL-E
- **Reinforcement Learning** (3 bookmarks) — About training AI through trial and error
- **Agents** (1 bookmark) — About AI systems that take actions

The biggest challenge is that the "General" folder is a catch-all with nearly two-thirds of all bookmarks. This makes it harder for any automated system to tell whether a new bookmark belongs in "General" or in a more specific folder.

---

## 3. Classification Benchmark

### 3.1 Aggregate Metrics

| Metric | Score | Interpretation |
|--------|-------|----------------|
| Folder accuracy | 0.6250 | 10/16 cases classified to the correct folder |
| Type accuracy | 0.5000 | 8/16 cases assigned the correct type |
| Tag precision | 0.2109 | Only 21% of predicted tags are relevant |
| Tag recall | 0.5729 | 57% of expected tags are captured |
| Tag F1 | 0.3082 | Harmonic mean of precision and recall |

### 3.2 Per-Case Breakdown

#### 3.2.1 Technical Analysis (Postgrad)

The classification was performed in heuristic-only mode (`--force-heuristic`), which uses token-overlap similarity against the vault profile's `NoteProfile.tokens` sets. The heuristic pipeline derives folder, type, and tags from content token frequency and similarity to existing notes.

**Folder classification analysis:**

| Expected Folder | N | Folder Acc | Type Acc | Tag F1 | Failure Mode |
|----------------|---|------------|----------|--------|-------------|
| ML-AI/Agents | 1 | 1.00 | 0.00 | 0.55 | Type defaults to `article` |
| ML-AI/Diffusion | 2 | 1.00 | 0.50 | 0.27 | Type defaults to `article`; 1 of 2 types wrong |
| ML-AI/General | 3 | 1.00 | 0.67 | 0.30 | Strong folder, moderate type |
| ML-AI/Reinforcement-Learning | 2 | 1.00 | 0.50 | 0.36 | Folder correct; type weak |
| ML-AI/Computer-Vision | 2 | 0.50 | 0.00 | 0.18 | Self-supervised content lacks "vision" tokens; misrouted to ML-AI root |
| ML-AI/LLMs | 3 | 0.33 | 0.33 | 0.36 | 2/3 LLM cases misrouted to General — content lacks discriminative "LLM" vocabulary |
| Development | 3 | 0.00 | 1.00 | 0.25 | All 3 dev cases routed to ML-AI root; no Development notes exist in the profile |

**Folder confusion matrix:**

```
Expected                    Predicted
                            ML-AI  Agents  CV  Diffusion  General  LLMs  RL
Development                   3      .      .      .         .       .     .
ML-AI/Agents                  .      1      .      .         .       .     .
ML-AI/Computer-Vision         1      .      1      .         .       .     .
ML-AI/Diffusion               .      .      .      2         .       .     .
ML-AI/General                 .      .      .      .         3       .     .
ML-AI/LLMs                    .      .      .      .         2       1     .
ML-AI/Reinforcement-Learning  .      .      .      .         .       .     2
```

Key observations:

1. **Development folder is unreachable.** The profile contains only ML-AI notes (47 across 6 subfolders). With zero Development exemplars, the similarity scorer has no anchor for Development-bound content, and all three Development cases collapse to the `ML-AI` root folder.

2. **LLM content blends into General.** Two of three LLM cases (`ml-llm-inference`, `ml-llm-course`) were classified into `ML-AI/General` rather than `ML-AI/LLMs`. Their content discusses "inference," "serving," "Stanford," and "transformers" — tokens that overlap significantly with the General folder's existing notes on similar topics. Only `ml-llm-finetuning` (with distinctive "fine-tuning," "LoRA," "DPO" tokens) was correctly routed.

3. **Self-supervised learning lacks spatial anchors.** The `ml-self-supervised-vision` case discusses "visual representations" and "self-supervised learning" without using the specific terms "computer vision" or "vision transformer" that anchor the CV folder's notes. The heuristic relies on exact token overlap, so synonyms and related concepts fail.

4. **Topic-specific folders with strong vocabulary work well.** Diffusion (2/2), RL (2/2), Agents (1/1), and General (3/3) all achieve 100% folder accuracy. These folders have distinctive token profiles: "diffusion models," "reinforcement learning," "arxiv," and general ML terminology respectively.

**Type classification analysis:**

The heuristic classifier defaults to `article` for all content types except when strong signals exist (e.g., explicit "course" tokens matching existing course notes). The type confusion is extreme:

```
Expected      Predicted
              article   (all others)
article          8          0
book             1          0
course           2          0
newsletter       1          0
paper            2          0
tutorial         2          0
```

Every non-article type is collapsed to `article`. This is a known limitation of the heuristic: without LLM-based semantic understanding, distinguishing "a tutorial about transformers" from "a paper about transformers" requires deeper language comprehension than token overlap provides.

**Tag classification analysis:**

| Metric | Value | Notes |
|--------|-------|-------|
| Mean predicted tags per case | 7.5 | Consistent — heuristic generates a fixed-size tag set |
| Mean expected tags per case | 2.6 | Curated tags are selective |
| Mean tag overlap | 1.7 | Only ~1-2 tags match on average |
| Tag precision | 0.211 | Low — many predicted tags are noise |
| Tag recall | 0.573 | Moderate — most relevant tags captured |

The precision-recall imbalance reveals a systematic overgeneration: the heuristic extracts too many content-derived tokens as tags. For example, `ml-attention-mechanism` predicted tags like `['attention', 'transformer', 'deep-learning', 'architecture', 'explanation', 'comprehensive', 'derivation', 'practical']` when the expected set was `['attention', 'transformer', 'deep-learning']`. Words like "explanation," "comprehensive," and "derivation" are noise — they describe the writing style, not the topic.

Two cases achieved 0% tag F1:
- `ml-self-supervised-vision`: predicted `['learning', 'ml-ai', 'representations', 'self-supervised', 'survey', 'visual']` vs expected `['computer-vision', 'representation-learning', 'self-supervised-learning']`. The tokens partially overlap in meaning ("self-supervised" ≈ "self-supervised-learning") but the exact string matching doesn't bridge the gap.
- `ml-diffusion-models`: predicted `['denoising', 'diffusion', 'generative', 'guidance', 'image', 'models', 'score', 'synthesis']` vs expected `['diffusion-models', 'generative-ai', 'deep-learning']`. Same issue: "diffusion" vs "diffusion-models" and "generative" vs "generative-ai" are semantically equivalent but lexically different.

#### 3.2.1 Plain-Language Analysis (Layman)

Imagine you have a pile of 47 bookmarks about machine learning, and you ask a simple rule-based system to sort new bookmarks into the same folders. Here's what happened:

**What worked well:**
- **Niche topics like "Diffusion Models" and "Reinforcement Learning" were sorted correctly every time.** These topics have unique words that make them easy to identify.
- **The catch-all "General" folder was correctly identified** for broad ML content.
- **The "Agents" folder (about AI agents that take actions) was correctly identified**, though there was only one test case.

**What didn't work:**
- **Content about LLMs (like ChatGPT) was often put in "General" instead of the "LLMs" folder.** This is because the content talks about things like "inference" and "transformers" which also appear in General-folder bookmarks. The system can't tell the difference without deeper understanding.
- **A test about "self-supervised learning for images" was put in the wrong folder** because it didn't use the exact phrase "computer vision" that the system was looking for.
- **All three Development bookmarks were put in the ML-AI folder instead.** This makes sense — the system had never seen a Development bookmark before, so it didn't know that folder existed.

**Type classification** (article vs. tutorial vs. course vs. paper, etc.) was essentially broken. Without an AI model to help, the system calls everything an "article." It can't tell the difference between a blog post and a university course just by looking at the words.

**Tags** were partially useful but had a specific problem: the system generates too many of them. It might correctly tag something with "transformer" and "deep-learning" but also add noise like "comprehensive," "practical," and "derivation." This makes the tags less useful because the important ones get buried.

### 3.3 Tag Deep Dive

#### 3.3.1 Technical Analysis (Postgrad)

The tag derivation pipeline in the heuristic classifier extracts candidate tags from content tokens, existing note similarity, and domain-specific vocabulary. The evaluation reveals three distinct failure modes:

**Failure Mode 1: Lexical mismatch (compound vs. atomic tags)**

| Predicted | Expected | Similarity |
|-----------|----------|------------|
| `self-supervised` | `self-supervised-learning` | Hyphenated prefix match |
| `diffusion` | `diffusion-models` | Substring match |
| `generative` | `generative-ai` | Substring match |
| `reinforcement` | `reinforcement-learning` | Prefix match |

The heuristic tokenizes on whitespace and punctuation, producing atomic tokens. Expected tags are often compound hyphenated forms. A fuzzy matching or stemming pass could recover significant precision here.

**Failure Mode 2: Style words as tags**

Words like "comprehensive," "practical," "derivation," "explanation," "guide," "getting," and "started" appear frequently in predicted tags but never in expected tags. These are stop words in the domain-specific sense — they describe the pedagogical approach, not the topic. A domain-specific stop word list or minimum-document-frequency filter would reduce this noise.

**Failure Mode 3: Tag count calibration**

The heuristic consistently produces 6-8 tags per case, while the curated expected tags average 2.6. This 3x overgeneration is the primary driver of the low precision (0.211). A confidence threshold or top-k selection (e.g., only the 3 strongest tags) would improve precision at minimal recall cost.

#### 3.3.1 Plain-Language Analysis (Layman)

The tagging system has three main problems:

1. **Close-but-not-exact matches:** The system might tag something as "diffusion" when the correct tag is "diffusion-models." To a human, these mean the same thing, but the computer treats them as completely different.

2. **Including filler words:** The system picks up words like "comprehensive" and "practical" from the text and treats them as tags. But these describe how something was written, not what it's about. It's like labeling a cookbook as "hardcover" — technically true, but not helpful.

3. **Too many tags:** The system generates about 7-8 tags per bookmark, but only about 2-3 are actually useful. If you're searching for bookmarks about "transformers," having to sift through tags like "comprehensive," "practical," and "derivation" makes the useful tags harder to find.

---

## 4. Search Retrieval Benchmark

### 4.1 Aggregate Metrics

| Metric | @5 | @10 |
|--------|-----|------|
| Precision | 0.2000 | 0.1000 |
| Recall | 0.6898 | 0.6898 |
| MRR | 0.8056 | — |
| NDCG | 0.7110 | 0.7110 |

**Note:** Recall@5 = Recall@10, indicating that the BM25 index returns all results within the top 5 positions (the corpus is small and queries are well-targeted).

### 4.2 Per-Query Analysis

#### 4.2.1 Technical Analysis (Postgrad)

**By query mode hint:**

| Mode | Queries | Hit Rate | Mean Rank | Notes |
|------|---------|----------|-----------|-------|
| bm25 | 7 | 7/7 (100%) | 1.0 | Every BM25-targeted query found its target at rank 1 |
| semantic | 6 | 3/6 (50%) | — | 3 semantic queries returned zero BM25 results |
| hybrid | 5 | 5/5 (100%) | 1.0 | Hybrid queries also found targets at rank 1 |

**BM25 mode (keyword queries):**

All 7 keyword-optimized queries succeeded at rank 1. These queries contain exact terms present in the bookmark titles, descriptions, and tags. For example, "flash attention memory efficient transformer" directly matches the note titled "Articles like Flash Attention from First Principles" with tags `['flash-attention', 'transformer', 'deep-learning', 'optimization']`.

**Semantic mode (conceptual queries):**

Three of six semantic queries returned zero BM25 results:

| Query | Why BM25 Failed | Relevant Notes |
|-------|----------------|----------------|
| "how to scale distributed training across GPUs" | No note contains the exact phrase "how to scale" or "distributed training across GPUs" | Scaling-Book-JAX-ML, Ultrascale-Playbook, GPU-Computing |
| "self-supervised representation learning without labels" | "without labels" doesn't appear; "representation learning" appears but the query's other tokens dilute the match | DINOv3, SSL Cookbook, ViTs Work |
| "probabilistic Bayesian uncertainty deep learning" | "Bayesian" and "uncertainty" appear in only one note (Probabilistic AI); "probabilistic" token is in the note but the query has high semantic density that BM25 can't exploit | Probabilistic AI, KL-MLE, Statistics+DL |

These failures are characteristic of the BM25 lexical gap: queries that express information needs in different vocabulary than the documents use. This is precisely the scenario where semantic (embedding-based) search should outperform BM25, as embeddings can bridge synonymous and related concepts.

**Recall ceiling analysis:**

Overall recall is capped at 0.6898, meaning ~31% of relevant documents are never retrieved. This has two causes:

1. **Lexical gap:** The 3 completely missed semantic queries contribute 9 unretrieved relevant documents.
2. **Partial retrieval:** Queries like "generative models image generation" found 4/4 relevant notes but "understanding attention mechanism in transformers" found only 2/4 in the top 5.

The recall@5 = recall@10 identity shows that the BM25 ranking exhausts its relevant results within 5 positions. For this 47-note corpus, expanding the result window beyond 5 provides no benefit under BM25.

**NDCG analysis:**

NDCG@5 = 0.711 indicates good but not perfect ranking quality. The discount from 1.0 is driven by:
- The 3 completely missed semantic queries (contributing 0 gain)
- Multi-relevant queries where not all relevant notes appear in top positions (e.g., "attention mechanism" has rank-1 hits for Flash-Attention and Illustrated-Retrieval-Transformer but misses Linear-Transformers and Random-Transformer)

#### 4.2.1 Plain-Language Analysis (Layman)

We tested 18 different search queries against the 47 ML-AI bookmarks. Here's how it broke down:

**Keyword searches (7 queries): 100% success**

When you search for specific words that appear in the bookmarks — like "flash attention transformer" or "JAX autodiff cookbook" — the search finds the right bookmark every time, and it's always the #1 result.

Think of it like using the index of a book: if you look up a word that's actually in the index, you'll find it immediately.

**Concept searches (6 queries): 50% success**

When you search for a concept using different words than what's in the bookmarks — like "how to scale distributed training across GPUs" — the search fails half the time. The problem isn't that the right bookmarks don't exist; it's that they use different words. The bookmark might say "model parallelism" while you search for "distributed training."

It's like looking for a recipe for "chicken soup" in a cookbook that calls it "poultry broth" — same thing, different name.

**Mixed searches (5 queries): 100% success**

Queries that combine specific keywords with broader concepts worked well, since the keyword part was enough to find the match.

**Why recall is only 69%:**

Out of all the bookmarks that *should* have been found, only about 69% actually appeared in the search results. The remaining 31% are the ones hiding behind the "different words" problem. This is the main limitation of keyword-based search, and it's exactly the kind of problem that AI-powered (semantic) search is designed to solve.

### 4.3 Recall by Query Mode

| Mode | Total Relevant Docs | Found in Top 5 | Recall |
|------|--------------------|-----------------|--------|
| bm25 | 9 | 9 | 100% |
| semantic | 21 | 7 | 33% |
| hybrid | 9 | 9 | 100% |

This stark contrast confirms that the BM25 retrieval is highly effective for keyword-precise queries but fundamentally limited for concept-level retrieval. The semantic and hybrid modes (which combine BM25 with embedding-based search) should recover much of this gap when API keys are configured.

---

## 5. End-to-End Benchmark

### 5.1 Results

| Metric | Score |
|--------|-------|
| Folder accuracy | 1.0 |
| Type accuracy | 1.0 |
| Tag precision | 0.333 |
| Tag recall | 1.0 |
| Tag F1 | 0.5 |
| Retrieval success rate | 1.0 |
| Retrieval MRR | 1.0 |

### 5.2 Technical Analysis (Postgrad)

The single e2e case (`example-domain-local`) uses deterministic inline HTML with the query "example domain." The test exercises the full pipeline: HTML parsing → classification → note rendering → FTS index build → retrieval query. The perfect classification scores reflect that the test content is explicitly designed to be unambiguous. The extra predicted tags (`domain`, `fixture`, `local`, `used`) reduce tag precision to 0.333 while retaining perfect recall.

This test serves as a smoke test for pipeline integration rather than a quality benchmark. It verifies that all pipeline stages connect correctly and produce well-formed output, not that classification or search quality is high.

### 5.2 Plain-Language Analysis (Layman)

The end-to-end test is like a "system check" — it verifies that the entire bookmarking pipeline works from start to finish without errors. It uses a deliberately simple test case (a generic "Example Domain" webpage) to make sure:

1. The webpage can be read and understood ✓
2. The bookmark gets sorted into the right folder ✓
3. The right type (article) is assigned ✓
4. The bookmark can be found by searching for it later ✓

It's not designed to be a difficult test — it's designed to confirm nothing is broken.

---

## 6. Comparison with Previous Benchmarks

### 6.1 Technical Comparison (Postgrad)

**Classification: Previous vs. Current**

| Metric | Previous (3 cases, synthetic vault) | Current (16 cases, 47-note vault) | Delta |
|--------|--------------------------------------|-----------------------------------|-------|
| Folder accuracy | 1.000 | 0.625 | -0.375 |
| Type accuracy | 1.000 | 0.500 | -0.500 |
| Tag precision | 0.333 | 0.211 | -0.122 |
| Tag recall | 1.000 | 0.573 | -0.427 |
| Tag F1 | 0.500 | 0.308 | -0.192 |

The apparent regression is not a regression at all. The previous benchmark used 3 cases designed to be trivially classifiable (Python/SQLite/Testing content against a single-folder Development vault). The current benchmark introduces 13 new cases spanning 7 folders with diverse content types. The larger, more challenging test set provides a more realistic assessment.

The previous 100% scores were artifacts of an unchallenging test, not evidence of robust classification. The current 62.5% folder accuracy against a realistic multi-folder profile is a more honest baseline.

**Search: BEIR vs. Personal**

| Metric | BEIR/nfcorpus (323 queries, 3633 docs) | BEIR/scifact (300 queries, 5000 docs) | Personal (18 queries, 47 docs) |
|--------|----------------------------------------|--------------------------------------|-------------------------------|
| MRR | 0.331 | 0.047 | 0.806 |
| P@5 | 0.185 | 0.009 | 0.200 |
| Recall@5 | 0.083 | 0.045 | 0.690 |
| NDCG@5 | 0.226 | 0.045 | 0.711 |

The personal dataset dramatically outperforms BEIR on all metrics. This is expected and does not indicate superior retrieval quality in general. The personal dataset has three advantages:

1. **Small corpus (47 vs. 3633/5000):** Fewer documents means less competition for top positions, boosting precision and MRR.
2. **Domain coherence:** All 47 notes are about ML/AI, so queries within this domain have high vocabulary overlap with documents.
3. **Query-document alignment:** The queries were written with knowledge of the corpus content, ensuring vocabulary overlap.

BEIR datasets test retrieval in a more adversarial setting: larger corpora, cross-domain queries, and relevance judgments that penalize shallow matching. The personal dataset complements BEIR by testing retrieval quality in the actual deployment domain.

### 6.1 Plain-Language Comparison (Layman)

**The numbers went down for classification, but that's actually good news.**

The previous test only had 3 simple test cases — like only testing a student on questions they've already seen. Of course they scored 100%! Now with 16 realistic test cases across 7 different folders, the score dropped to about 63%. This isn't the system getting worse — it's us asking harder, more realistic questions.

**The search numbers went way up compared to the public benchmarks.**

Our personal bookmarks search scored 81% MRR (finding the right result at #1) compared to 33% for a public academic benchmark. But this isn't really a fair comparison:

- Our test has only 47 bookmarks (the academic test has thousands)
- Our bookmarks are all about similar topics, making them easier to search through
- We wrote our search queries knowing what bookmarks exist

Think of it this way: finding a specific book is easier in your personal bookshelf (you know what's there) than in a library (thousands of books on every topic).

---

## 7. Recommendations

### 7.1 Technical Recommendations (Postgrad)

#### High Priority

1. **Integrate LLM classification.** The heuristic classifier's 50% type accuracy is a hard ceiling imposed by the bag-of-words approach. LLM-based classification (even with a small model like `gpt-4.1-mini`) should recover type discrimination. The infrastructure is already in place (`call_llm()` in `classify.py`); this is a configuration change, not an engineering change.

2. **Implement compound-tag fuzzy matching.** The tag evaluation penalizes "diffusion" vs. "diffusion-models" as a complete miss. A containment or prefix-match scoring strategy (e.g., Jaccard on tokenized tag components) would more accurately reflect the semantic overlap and likely improve measured tag F1 by 10-15 percentage points without any code changes.

3. **Add domain stop words for tag filtering.** Words like "comprehensive," "practical," "guide," "introduction," and "overview" should be excluded from tag candidates. A curated stop list or a minimum-IDF threshold would reduce tag noise.

#### Medium Priority

4. **Run semantic/hybrid search benchmarks.** The 50% miss rate on semantic queries is the strongest motivation for embedding-based retrieval. Running the personal search benchmark with `--mode semantic` and `--mode hybrid` would quantify the improvement.

5. **Calibrate tag generation to top-k.** Emitting the top 3-4 tags by confidence score rather than all candidates above a flat threshold would improve precision from 0.21 to an estimated 0.40-0.50.

6. **Add more eval cases for weak folders.** The LLMs and Computer-Vision folders have only 2-3 cases each. Expanding to 8-10 cases per folder would provide statistically meaningful per-folder metrics.

#### Low Priority

7. **Cross-domain eval cases.** Add cases that span Development + ML-AI to test cross-folder disambiguation with a mixed profile.

8. **Temporal and URL-based features.** The heuristic currently ignores the URL domain and creation date. Domain heuristics (e.g., `arxiv.org` → `paper`, `youtube.com` → `video`) could boost type accuracy cheaply.

### 7.1 Plain-Language Recommendations (Layman)

**Most important things to fix:**

1. **Turn on AI-powered classification.** Right now the system runs without any AI help (that's what "heuristic" means), which is why it calls everything an "article." Simply enabling the AI model that's already built into the tool should fix a lot of the type-mixing problems.

2. **Make the tagging system less chatty.** The system should learn to stop tagging things with filler words. Just because an article mentions "comprehensive derivations" doesn't mean "comprehensive" should be a tag.

3. **Be smarter about similar tags.** If the system tags something as "diffusion" but the expected tag is "diffusion-models," that should count as close enough — not a complete miss.

**Worth doing soon:**

4. **Test the AI-powered search.** We only tested basic keyword search. The tool also has an AI-powered semantic search mode that should find bookmarks even when you use different words than what's in the bookmark. This should fix the 31% of bookmarks that keyword search misses.

5. **Limit the number of tags.** Instead of generating 7-8 tags per bookmark, the system should pick just the 3-4 best ones. Quality over quantity.

---

## 8. Snapshot File Inventory

| File | Suite | Date |
|------|-------|------|
| `evals/results/20260530T014400Z__classification.json` | Classification (heuristic, 16 cases) | 2026-05-30 |
| `evals/results/20260530T014409Z__search-personal.json` | Search BM25 (18 queries, 47 docs) | 2026-05-30 |
| `evals/results/20260530T014417Z__e2e.json` | E2E (1 case) | 2026-05-30 |
