# Phase 5 Evaluation Report — Chunked Retrieval

**Date:** 2026-05-27  
**Phase under review:** Phase 5 — Chunked search and ranking improvements  
**Compared against:** `docs/BENCHMARK-RESULTS.md` / pre-Phase-5 snapshots from `20260527T1003xxZ`  
**Current code snapshot:** `21b6775acf19` (`docs(search): document chunked retrieval`) with uncommitted report/plan edits  
**Previous code snapshot:** `e2a10e84fabb` with pre-Phase-5 retrieval behavior  
**Python:** 3.13.4  
**Primary result:** Chunked retrieval is functionally working, but BM25 benchmark quality is a small regression on NFCorpus and a clearer regression on SciFact. The implementation improves observability and long-note recall capabilities, but the current chunk-level BM25 scoring needs ranking calibration before it should be considered a quality win.

---

## 1. Executive summary

Phase 5 introduced section-aware retrieval:

- `bookmark_tools/chunking.py` splits notes by Markdown sections, then by a character budget.
- FTS5 indexes chunks rather than one whole-note body row.
- `note_chunks` stores derived chunk records in the unified catalog.
- Search results now include matching `section`, `chunk_index`, and snippets.
- Default search dedupes by bookmark/note; `--show-chunks` exposes multiple chunks per note.
- Semantic search now embeds chunks rather than only the first 500 body characters.
- Semantic and hybrid modes now support `--tag`.
- Initial exact-match boosts were added for title, tag, domain, folder, and topic signals.

The Phase 5 eval run was intentionally compared against the previous full benchmark run using the same BEIR datasets and BM25-only mode. Semantic/hybrid quality could not be benchmarked without embedding API calls, so the search comparison below is specifically a **BM25 chunked FTS vs pre-Phase-5 note-level FTS** comparison.

### Headline comparison

| Suite | Dataset | Previous key result | Phase 5 key result | Change |
|---|---|---:|---:|---:|
| Search BM25 | BEIR/nfcorpus | nDCG@5 0.2313 | 0.2256 | -0.0057 (-2.47%) |
| Search BM25 | BEIR/nfcorpus | MRR 0.3374 | 0.3309 | -0.0065 (-1.93%) |
| Search BM25 | BEIR/scifact | nDCG@5 0.0500 | 0.0454 | -0.0046 (-9.27%) |
| Search BM25 | BEIR/scifact | MRR 0.0533 | 0.0467 | -0.0067 (-12.50%) |
| Classification | synthetic fixtures | Tag F1 0.5000 | 0.5000 | unchanged |
| E2E | inline HTML case | Retrieval MRR 1.0000 | 1.0000 | unchanged |
| Unit tests | full suite | 355 passed + 7 subtests | 396 passed | expanded coverage |

### Bottom line

Phase 5 is a **capability improvement** but not yet a **ranking-quality improvement** on the BM25 benchmarks:

1. **Functional acceptance criteria are met.** Long body/archive content can now be chunked and matched beyond the old embedding/body-prefix limit. Results identify section/chunk context. Tests cover chunk indexing, dedupe, snippets, semantic chunk matching, and tag filtering.
2. **BM25 metrics slightly regressed.** NFCorpus is down by about 1–2.5% on most top-rank metrics, with a small Recall@5 improvement. SciFact is down about 8–12.5%, though the absolute score is still very low both before and after.
3. **The likely cause is chunk granularity.** Splitting each note into multiple FTS rows changes BM25 length normalization and term co-occurrence. Queries that previously matched terms spread across an entire note may no longer match the same row unless all required terms appear in one chunk. Repeating metadata per chunk helps but does not fully preserve note-level evidence aggregation.
4. **The implementation should stay, but ranking needs the next iteration.** Chunking is required for long notes and semantic retrieval. The next quality step should add note-level aggregation across chunk hits, tune chunk size/overlap, and preserve a note-level fallback score.

---

## 2. Eval commands run

The following commands were run after Phase 5 implementation:

```bash
uv run bookmark-eval run search --dataset beir:nfcorpus --mode bm25 --limit 100
uv run bookmark-eval run search --dataset beir:scifact --mode bm25 --limit 100
uv run bookmark-eval run classification --force-heuristic
uv run bookmark-eval run e2e --force-heuristic
uv run bookmark-eval run ablation --dataset beir:nfcorpus --mode bm25 --limit 100 \
  --models text-embedding-3-small,text-embedding-3-large \
  --dimensions 256,512
uv run ruff check bookmark_tools tests
uv run ruff format --check bookmark_tools tests
uv run pytest tests/
```

Semantic/hybrid BEIR runs were not included because they require an embedding API key and would incur API calls for thousands of chunks. The ablation run is therefore BM25-only, matching the previous report.

---

## 3. Snapshot inventory

### Previous snapshots used for comparison

| Suite | Dataset | Snapshot |
|---|---|---|
| Search | BEIR/nfcorpus | `evals/results/20260527T100309Z__search-beir-nfcorpus.json` |
| Search | BEIR/scifact | `evals/results/20260527T100324Z__search-beir-scifact.json` |
| Classification | bundled fixtures | `evals/results/20260527T100331Z__classification.json` |
| E2E | bundled case | `evals/results/20260527T100345Z__e2e.json` |
| Ablation | BEIR/nfcorpus, BM25-only | `evals/results/20260527T100354Z__ablation-beir-nfcorpus.json` |

### Phase 5 snapshots generated

| Suite | Dataset | Snapshot |
|---|---|---|
| Search | BEIR/nfcorpus | `evals/results/20260527T121122Z__search-beir-nfcorpus.json` |
| Search | BEIR/scifact | `evals/results/20260527T121130Z__search-beir-scifact.json` |
| Classification | bundled fixtures | `evals/results/20260527T121133Z__classification.json` |
| E2E | bundled case | `evals/results/20260527T121134Z__e2e.json` |
| Ablation | BEIR/nfcorpus, BM25-only, 4 combos | `evals/results/20260527T121149Z__ablation-beir-nfcorpus.json` |

---

## 4. Search benchmark comparison — BEIR/nfcorpus

**Dataset:** NFCorpus  
**Corpus size:** 3,633 docs  
**Queries:** 323  
**Mode:** BM25  
**Previous behavior:** one FTS row per bookmark note/body  
**Phase 5 behavior:** one FTS row per derived chunk, deduped to one note result by default

### 4.1 Aggregate metric comparison

| Metric | Previous | Phase 5 | Absolute delta | Relative delta |
|---|---:|---:|---:|---:|
| P@5 | 0.188854 | 0.185139 | -0.003715 | -1.97% |
| P@10 | 0.138390 | 0.138080 | -0.000310 | -0.22% |
| Recall@5 | 0.081753 | 0.082963 | +0.001210 | +1.48% |
| Recall@10 | 0.093266 | 0.093159 | -0.000107 | -0.12% |
| MRR | 0.337440 | 0.330930 | -0.006510 | -1.93% |
| nDCG@5 | 0.231280 | 0.225558 | -0.005722 | -2.47% |
| nDCG@10 | 0.201904 | 0.198918 | -0.002986 | -1.48% |

### 4.2 Interpretation

NFCorpus shows a small but real top-rank regression:

- **nDCG@5 fell by 2.47%.** This means the ordering of the top five results is slightly worse after chunking.
- **MRR fell by 1.93%.** First relevant results are, on average, slightly lower in the ranking.
- **P@5 fell by 1.97%, while P@10 was nearly flat.** Top-five precision is more sensitive to the new scoring behavior than top-ten precision.
- **Recall@5 improved by 1.48%.** Chunking helped some relevant documents enter the first five results, even though their order/precision was slightly worse overall.
- **Recall@10 is essentially unchanged.** At ten results, the same broad set of relevant documents is being found.

This is the expected shape of an early chunking migration: chunking can surface local matches more precisely, but raw BM25 over chunks no longer has exactly the same evidence aggregation as BM25 over full notes.

### 4.3 What likely changed mechanically

Pre-Phase-5 FTS represented each note as one searchable row. A query could match terms anywhere in the title, frontmatter fields, description, and full body. Phase 5 represents each note as multiple chunk rows. Metadata is repeated per chunk, but body terms are local to a section/chunk.

This changes scoring in several ways:

1. **Length normalization changed.** FTS5 BM25 scores shorter chunks differently from full documents. A term in a short chunk can score strongly, but metadata repeated across many chunks also changes corpus statistics.
2. **Term co-occurrence became local.** The query builder uses AND-style prefix matching. If query terms are spread across separate sections, the old note-level row could match while no single chunk may match, or a weaker metadata-only chunk may win.
3. **Deduping selects the best chunk per note.** This is desirable for UX, but it means note-level relevance is represented by one chunk's score rather than an aggregate score across all matching chunks.
4. **Metadata repetition can overweight multi-chunk notes.** Title/tags/folder are inserted with each chunk. This improves matching but can distort IDF/field statistics compared with one row per note.
5. **Initial boosts are simple.** Exact title/tag/domain/topic/folder boosts are helpful for personal search but do not address BEIR's abstract/query relevance patterns.

### 4.4 NFCorpus conclusion

The NFCorpus result is not alarming, but it is not yet a retrieval-quality win. The Phase 5 implementation should be kept because it unlocks long-note/chunk snippets and semantic chunking, but BM25 ranking should be improved before claiming search quality improved.

Recommended target for the next retrieval iteration: recover at least the previous NFCorpus nDCG@5 of **0.2313** while preserving chunk snippets and `--show-chunks`.

---

## 5. Search benchmark comparison — BEIR/scifact

**Dataset:** SciFact  
**Corpus size:** 5,183 docs  
**Queries:** 300  
**Mode:** BM25  
**Previous behavior:** one FTS row per bookmark note/body  
**Phase 5 behavior:** one FTS row per derived chunk, deduped to one note result by default

### 5.1 Aggregate metric comparison

| Metric | Previous | Phase 5 | Absolute delta | Relative delta |
|---|---:|---:|---:|---:|
| P@5 | 0.010667 | 0.009333 | -0.001333 | -12.50% |
| P@10 | 0.005333 | 0.004667 | -0.000667 | -12.50% |
| Recall@5 | 0.049167 | 0.045000 | -0.004167 | -8.47% |
| Recall@10 | 0.049167 | 0.045000 | -0.004167 | -8.47% |
| MRR | 0.053333 | 0.046667 | -0.006667 | -12.50% |
| nDCG@5 | 0.050012 | 0.045377 | -0.004635 | -9.27% |
| nDCG@10 | 0.050012 | 0.045377 | -0.004635 | -9.27% |

### 5.2 Interpretation

SciFact regressed more visibly than NFCorpus, although the absolute scores remain very low before and after:

- **nDCG@5 dropped from 0.0500 to 0.0454.** This is a 9.27% relative decline.
- **MRR dropped by 12.50%.** The few successful first relevant hits became less frequent.
- **Recall@5 and Recall@10 are identical within each run.** As in the previous benchmark, adding ranks 6–10 does not surface additional relevant documents. The matched relevant documents are either already in the top five or absent.
- **BM25 remains fundamentally weak for SciFact.** Scientific fact-checking queries are paraphrased claims, so exact lexical matching is a poor fit.

### 5.3 Why SciFact is more sensitive to chunking

SciFact claims often need semantic equivalence rather than literal token overlap. Chunking does not solve that by itself. It can even make BM25 worse if:

1. Claim terms are distributed across an abstract and no single chunk captures enough evidence.
2. Local chunks remove context that helped full-document matching.
3. Very short abstract sections amplify isolated lexical matches that are not actually relevant.
4. Deduped best-chunk ranking selects a lexical fragment rather than a globally relevant abstract.

The Phase 5 semantic chunking work is likely more important for SciFact than chunked BM25. However, a semantic/hybrid BEIR run is needed to verify that hypothesis.

### 5.4 SciFact conclusion

SciFact confirms that chunked BM25 alone is not sufficient. The next meaningful SciFact improvement should come from semantic/hybrid retrieval and/or query expansion, not from further lexical-only tuning.

---

## 6. Classification benchmark comparison

**Dataset:** bundled synthetic classification fixtures  
**Cases:** 3  
**Mode:** heuristic (`--force-heuristic`)

Phase 5 did not change classification logic, and the metrics are unchanged.

| Metric | Previous | Phase 5 | Delta |
|---|---:|---:|---:|
| Folder accuracy | 1.0000 | 1.0000 | +0.0000 |
| Type accuracy | 1.0000 | 1.0000 | +0.0000 |
| Tag precision | 0.3333 | 0.3333 | +0.0000 |
| Tag recall | 1.0000 | 1.0000 | +0.0000 |
| Tag F1 | 0.5000 | 0.5000 | +0.0000 |

Per-case predictions remain the same:

| Case | Result |
|---|---|
| `dev-python-cli` | folder/type correct; tag F1 0.500 |
| `dev-sqlite-fts` | folder/type correct; tag F1 0.500 |
| `dev-testing-strategy` | folder/type correct; tag F1 0.500 |

The existing tag overgeneration issue remains unchanged. This is expected: Phase 5 was a retrieval/indexing change, not a classifier change.

---

## 7. End-to-end benchmark comparison

**Dataset:** bundled inline HTML E2E case  
**Cases:** 1  
**Mode:** heuristic (`--force-heuristic`)

Phase 5 did not regress the end-to-end ingest/search smoke test.

| Metric | Previous | Phase 5 | Delta |
|---|---:|---:|---:|
| Folder accuracy | 1.0000 | 1.0000 | +0.0000 |
| Type accuracy | 1.0000 | 1.0000 | +0.0000 |
| Tag precision | 0.3333 | 0.3333 | +0.0000 |
| Tag recall | 1.0000 | 1.0000 | +0.0000 |
| Tag F1 | 0.5000 | 0.5000 | +0.0000 |
| Retrieval success rate | 1.0000 | 1.0000 | +0.0000 |
| Retrieval MRR | 1.0000 | 1.0000 | +0.0000 |

Retrieval detail remains successful:

| Case | Query | Required top K | Phase 5 rank | Success |
|---|---|---:|---:|---|
| `example-domain-local` | `example domain` | 5 | 1 | ✅ |

This confirms the new chunked index still supports the basic ingest → index → search path.

---

## 8. Ablation benchmark comparison

**Dataset:** BEIR/nfcorpus  
**Mode:** BM25-only  
**Combinations:**

- `text-embedding-3-small`, 256 dimensions
- `text-embedding-3-small`, 512 dimensions
- `text-embedding-3-large`, 256 dimensions
- `text-embedding-3-large`, 512 dimensions

Because this ablation was run in BM25-only mode, all embedding model/dimension combinations produce identical metrics within a run. This matches the previous report and remains expected.

### 8.1 Phase 5 ablation metrics

| Model | Dimensions | P@5 | P@10 | Recall@5 | Recall@10 | MRR | nDCG@5 | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| text-embedding-3-small | 256 | 0.1851 | 0.1381 | 0.0830 | 0.0932 | 0.3309 | 0.2256 | 0.1989 |
| text-embedding-3-small | 512 | 0.1851 | 0.1381 | 0.0830 | 0.0932 | 0.3309 | 0.2256 | 0.1989 |
| text-embedding-3-large | 256 | 0.1851 | 0.1381 | 0.0830 | 0.0932 | 0.3309 | 0.2256 | 0.1989 |
| text-embedding-3-large | 512 | 0.1851 | 0.1381 | 0.0830 | 0.0932 | 0.3309 | 0.2256 | 0.1989 |

### 8.2 Comparison to previous ablation

The ablation's BM25 baseline moved exactly with the search benchmark because both exercise the same BM25 path:

| Metric | Previous ablation BM25 | Phase 5 ablation BM25 | Delta |
|---|---:|---:|---:|
| P@5 | 0.1889 | 0.1851 | -0.0037 |
| P@10 | 0.1384 | 0.1381 | -0.0003 |
| Recall@5 | 0.0818 | 0.0830 | +0.0012 |
| Recall@10 | 0.0933 | 0.0932 | -0.0001 |
| MRR | 0.3374 | 0.3309 | -0.0065 |
| nDCG@5 | 0.2313 | 0.2256 | -0.0057 |
| nDCG@10 | 0.2019 | 0.1989 | -0.0030 |

The ablation infrastructure remains healthy. It is now more important to run semantic/hybrid ablations when API access is available, because Phase 5 materially changed semantic indexing from note-level body prefixes to chunk-level embeddings.

---

## 9. Unit test and static check status

After Phase 5 and this report update, the full local validation command set passed:

| Check | Result |
|---|---|
| `uv run ruff check bookmark_tools tests` | ✅ passed |
| `uv run ruff format --check bookmark_tools tests` | ✅ passed |
| `uv run pytest tests/` | ✅ 396 passed |

The previous report recorded 355 tests plus 7 subtests. The suite now has 396 tests, reflecting added coverage for:

- section-aware chunk generation,
- chunked FTS indexing,
- chunk snippets and section names,
- default note-level dedupe,
- `--show-chunks`,
- semantic chunk embedding,
- semantic `--tag` filtering,
- catalog chunk row behavior.

---

## 10. Detailed analysis of Phase 5 outcomes

### 10.1 What improved

#### 10.1.1 Long-note and archive retrieval capability

Before Phase 5, search indexing treated each note as one document and semantic embeddings used only a short body prefix. That meant long archived content could be underrepresented, especially in semantic mode. Phase 5 makes long-note retrieval structurally possible by indexing chunks and embedding chunk text.

This matters for real bookmark vaults more than it may show in BEIR:

- Obsidian notes often contain summaries, notes, excerpts, and archive blocks.
- User queries often target a specific section or detail rather than the whole page.
- A section/chunk result gives users a useful explanation of *why* a bookmark matched.

#### 10.1.2 Result explainability

Search results now include:

- `section`,
- `chunk_index`,
- `snippet`.

This is a product-quality improvement even where aggregate BM25 metrics are flat or slightly down. Users can see whether a match came from `summary`, `notes`, `archive`, or another section.

#### 10.1.3 Better retrieval controls

`--show-chunks` allows users and agents to inspect multiple matching sections from the same bookmark. Default dedupe keeps ordinary search output note-centric, which is the right UX default for bookmark search.

#### 10.1.4 Semantic path is now correctly shaped

The previous semantic implementation embedded a short note-level text with only the first 500 body characters. Phase 5 embeds chunk text with section context. That should improve long-note semantic recall once semantic/hybrid benchmarks are run with an API key.

### 10.2 What regressed

#### 10.2.1 BM25 top-rank quality

The most important regression is NFCorpus nDCG@5: **0.2313 → 0.2256**. This is small but meaningful because Phase 5 was expected to improve retrieval or at least remain neutral.

The regression is not catastrophic:

- P@10 and Recall@10 are almost unchanged.
- Recall@5 improved slightly on NFCorpus.
- E2E smoke search still succeeds at rank 1.

But top-rank ordering needs tuning.

#### 10.2.2 SciFact lexical retrieval

SciFact dropped more in relative terms. Since SciFact was already a poor BM25 fit, the practical impact is limited; nevertheless, the result shows chunked lexical scoring does not automatically improve semantically difficult datasets.

### 10.3 Why tests pass while evals regress

The tests validate functional behavior:

- chunks are created,
- chunks are indexed,
- snippets and sections are returned,
- semantic search can match a deep chunk,
- filters work,
- the catalog remains consistent.

The BEIR evals validate ranking quality. A system can be functionally correct and still rank slightly worse. This is exactly why the eval baseline was necessary before Phase 5.

### 10.4 Why chunking still belongs in the architecture

The BM25 regression should not be interpreted as evidence that chunking was wrong. Chunking is a prerequisite for:

- long archived notes,
- section-specific snippets,
- semantic retrieval beyond body prefixes,
- graph edges by section/context,
- future reranking and answer generation.

The issue is the current **scoring model**, not the chunk representation.

---

## 11. Recommendations

### 11.1 Add note-level score aggregation over chunks

Instead of ranking notes by their single best chunk only, aggregate evidence across matching chunks:

- max chunk score,
- sum of top N chunk scores,
- weighted title/tag/folder score,
- count of matching sections,
- best snippet from highest scoring chunk.

A simple candidate formula:

```text
note_score = max_chunk_score
           + 0.15 * sum(next_best_2_chunk_scores)
           + metadata_boosts
```

This preserves chunk snippets while recovering evidence aggregation from the old note-level index.

### 11.2 Keep a note-level FTS fallback row or shadow index

Maintain both:

1. chunk-level FTS rows for snippets and section search,
2. note-level FTS rows for broad BM25 ranking.

Then fuse note-level and chunk-level BM25 with RRF or a weighted sum. This would likely recover the pre-Phase-5 baseline while keeping chunk UX.

### 11.3 Tune chunk size and overlap against NFCorpus

Current chunking uses a character budget. The next eval should compare:

| Variant | Max chars | Overlap | Hypothesis |
|---|---:|---:|---|
| current | 1600 | 160 | baseline Phase 5 |
| larger chunks | 2400 | 240 | better term co-occurrence, less fragmentation |
| smaller chunks | 1000 | 120 | better snippets, possibly worse BM25 |
| section-only | no intra-section split | 0 | closer to note-level ranking for abstract-like docs |

For BEIR abstracts, section-only or larger chunks may perform better because documents are not long Obsidian notes.

### 11.4 Relax or revise AND query behavior for chunked search

The query builder currently creates an AND-style prefix query. For chunked rows, this can be too strict. Consider:

- OR query fallback when AND returns too few candidates,
- phrase/title exact boosts separately from body chunk matching,
- two-stage retrieval: broad OR candidate generation, then score/rerank.

### 11.5 Run semantic/hybrid Phase 5 evals when API access is available

Phase 5's biggest expected quality gain is semantic chunk retrieval. The most important future commands are:

```bash
uv run bookmark-eval run search --dataset beir:scifact --mode semantic,hybrid --limit 100
uv run bookmark-eval run search --dataset beir:nfcorpus --mode semantic,hybrid --limit 100
uv run bookmark-eval run ablation --dataset beir:scifact --mode semantic,hybrid \
  --models text-embedding-3-small,text-embedding-3-large \
  --dimensions 256,512
```

SciFact should be the priority because it is the benchmark most likely to benefit from semantic retrieval.

### 11.6 Add per-query diff tooling

Aggregate metrics show the regression but not which queries changed. Add a report that lists:

- queries improved by Phase 5,
- queries regressed by Phase 5,
- old top 10 vs new top 10,
- section/chunk responsible for each new hit,
- whether relevant docs were missed due to chunk term separation.

This would make ranking fixes much faster.

---

## 12. Acceptance criteria status

Phase 5 acceptance criteria from `PLAN.md`:

| Acceptance criterion | Status | Evidence |
|---|---|---|
| A long archived note can match content beyond the first 500 body characters. | ✅ Met functionally | Added semantic chunk tests and chunk FTS tests for deep/archive terms. |
| Search results identify the matching section/chunk. | ✅ Met | `SearchResult` and CLI/JSON/CSV output include `section` and `chunk_index`. |
| Eval metrics do not regress versus baseline. | ⚠️ Partially unmet for BM25 | NFCorpus nDCG@5 -2.47%; SciFact nDCG@5 -9.27%. Classification/E2E unchanged. |

The first two criteria are complete. The third criterion needs follow-up ranking work if interpreted strictly for BM25 aggregate metrics.

---

## 13. Final conclusion

Phase 5 successfully adds the retrieval substrate needed for long-note search: section-aware chunks, chunk snippets, chunk embeddings, and chunk-aware CLI output. This is a major architectural step forward.

However, the BEIR comparison shows that **chunking changed BM25 scoring enough to cause a measurable regression**:

- NFCorpus: small top-rank regression, mostly under 2.5%.
- SciFact: larger relative regression, but on an already weak lexical benchmark.
- Classification and E2E behavior: unchanged.
- Unit tests and static checks: fully passing.

The recommendation is to keep Phase 5's chunk infrastructure and treat the next retrieval task as **ranking calibration**:

1. aggregate chunk scores at the note level,
2. add a note-level FTS fallback or shadow row,
3. tune chunk size/overlap,
4. run semantic/hybrid evals when API access is available,
5. add per-query regression diagnostics.

Until those ranking changes are made, Phase 5 should be described as a successful capability implementation with a known BM25 ranking regression, not as a measured retrieval-quality improvement.
