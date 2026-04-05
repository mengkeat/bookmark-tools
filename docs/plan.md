# Feature & Improvement Plan

Suggestions for making the Obsidian Bookmark Tools more feature-complete and robust, organized by priority and category.

---

## 1. Reliability & Error Handling

### 1.1 Retry with exponential backoff for network calls
All HTTP calls (page fetch, LLM classification, LLM summary, embedding API) are single-shot with a hard timeout. Add retry logic with exponential backoff and jitter to handle transient failures gracefully.
- **Scope**: `fetch.py`, `classify.py`, `summarize.py`, `embeddings.py`

### 1.2 Proper HTML parsing
`fetch.py` extracts `<title>`, `<meta>`, and `<html lang>` via regex. This is fragile for malformed HTML. Replace with a lightweight parser (e.g., `html.parser` from stdlib) for more reliable extraction.
- **Scope**: `fetch.py`

### 1.3 Graceful handling of rate limits
LLM and embedding APIs return 429 responses under load. Detect rate-limit headers (`Retry-After`, `x-ratelimit-*`) and wait accordingly rather than failing immediately.
- **Scope**: `classify.py`, `summarize.py`, `embeddings.py`

### 1.4 Timeout tuning and configurability
Timeouts are hard-coded (20s fetch, 20s LLM classify, 180s LLM summary). Make these configurable via environment variables or a config file so users can adapt to slow networks or providers.

---

## 2. Search Improvements

### 2.1 Incremental embedding updates
Semantic search currently recomputes all embeddings on every query (`refresh_embeddings` does a full pass). Switch to incremental embedding updates (like FTS5 already does via `bookmark_mtime`) to avoid redundant API calls and speed up queries.
- **Scope**: `embeddings.py`

### 2.2 Configurable BM25 weights
BM25 field weights are hard-coded `[0.0, 0.0, 8.0, 3.0, 4.0, 4.0, 3.0, 2.0, 1.0]`. Allow tuning via a config file or CLI flags so users can adjust ranking to their vault's content distribution.
- **Scope**: `search_index.py`, `search.py`

### 2.3 Search result snippets with highlighted matches
Currently search results show title/folder/description. Add context snippets around the matching text with highlighted query terms for faster scanning.
- **Scope**: `search.py`, `search_index.py`

### 2.4 Multi-language stemming support
The porter stemmer is English-only. Support additional languages via ICU tokenizer or language-specific stemmers for vaults with multilingual content.
- **Scope**: `search_index.py`

### 2.5 Embedding model configurability
The embedding model (`text-embedding-3-small`, 256 dims) and batch size (512) are hard-coded. Make these configurable to support different providers or higher-dimensional models.
- **Scope**: `embeddings.py`

---

## 3. Bookmark Creation Enhancements

### 3.1 Batch bookmark import
Support adding multiple URLs at once from a file, clipboard, or stdin (one URL per line). Useful for migrating from browser bookmark exports or Pocket/Raindrop.
- **Scope**: `cli.py` (new `--batch` or `--file` flag)

### 3.2 Bookmark update/refresh command
Add a command to re-fetch and re-classify an existing bookmark (e.g., when a page's content has changed or classification was wrong). Preserve manual edits while updating auto-generated fields.
- **Scope**: new CLI entry point or `--update` flag

### 3.3 Interactive classification review
Add an `--interactive` mode that shows the proposed classification (folder, tags, type, parent_topic) and lets the user confirm or override before writing the file.
- **Scope**: `cli.py`

### 3.4 Browser extension or bookmarklet integration
Provide a simple way to trigger `bookmark <URL>` from a browser, either via a bookmarklet that calls a local HTTP endpoint or a shell protocol handler.
- **Scope**: new module or companion script

### 3.5 Archive/snapshot page content
Optionally save a cleaned copy of the page content (or a Readability-parsed version) alongside the bookmark note, so content is preserved even if the original URL goes offline.
- **Scope**: `fetch.py`, `cli.py` (new `--archive` flag)

### 3.6 Link health checking
Periodically check all bookmarked URLs for dead links (404, timeouts, domain changes) and flag or tag broken bookmarks.
- **Scope**: new CLI entry point `bookmark-check`

---

## 4. Vault Organization & Metadata

### 4.1 Tag normalization and deduplication
Enforce consistent tag casing and merge near-duplicates (e.g., `machine-learning` vs `Machine Learning` vs `ml`). Maintain a tag alias map.
- **Scope**: `classify.py`, new config file for tag aliases

### 4.2 Folder reorganization tool
Provide a command to propose folder reclassifications for existing bookmarks based on the current classifier, useful after the classification guide evolves.
- **Scope**: new CLI entry point `bookmark-reorg`

### 4.3 Related bookmark linking
After creating a bookmark, update the `related` field of the top-N most similar existing bookmarks to include the new one, building a bidirectional link graph.
- **Scope**: `cli.py`, `classify.py`

### 4.4 Statistics and dashboard
Add a `bookmark-stats` command showing vault statistics: bookmarks per folder, tag distribution, most common parent topics, recent additions, broken links count, etc.
- **Scope**: new CLI entry point

---

## 5. Testing & Quality

### 5.1 Integration tests for the full pipeline
No tests cover the end-to-end `build_note()` flow. Add integration tests with mocked HTTP that exercise the complete bookmark creation pipeline.
- **Scope**: `tests/`

### 5.2 Branch-level coverage for `validate_folder()`
`validate_folder()` has complex branching logic for folder remapping. Add targeted tests for each branch to catch regressions.
- **Scope**: `tests/test_bookmarks.py`

### 5.3 Network behavior tests
Test handling of HTTP errors (404, 500, timeouts, SSL errors, rate limits) to verify fallback behavior is correct.
- **Scope**: `tests/`

### 5.4 Property-based testing for parsers
Use hypothesis to fuzz frontmatter parsing, URL normalization, and HTML extraction with random inputs.
- **Scope**: `tests/`

### 5.5 CI pipeline
Set up GitHub Actions to run `ruff check`, `ruff format --check`, and `pytest` on each push/PR.
- **Scope**: `.github/workflows/`

---

## 6. Developer Experience & Configuration

### 6.1 Unified configuration file
Consolidate settings (API keys, model IDs, timeouts, BM25 weights, embedding model, thresholds) into a single YAML/TOML config file with sensible defaults, reducing reliance on scattered environment variables.
- **Scope**: new `config.py` module, updates across all modules

### 6.2 Logging and verbosity levels
Replace `print()` with proper `logging` module usage. Support `--verbose` / `--quiet` flags and `LOG_LEVEL` env var for debugging and silent operation.
- **Scope**: all modules

### 6.3 Remove legacy entry point
`Vault/Meta/add_bookmark.py` uses `sys.path` manipulation. Remove it or convert it to a thin wrapper that calls the installed `bookmark` CLI.
- **Scope**: `Vault/Meta/add_bookmark.py`

### 6.4 Shell completions
Generate shell completions (bash, zsh, fish) for `bookmark` and `bookmark-search` commands.
- **Scope**: `cli.py`, `search.py`

---

## 7. Performance

### 7.1 Embedding caching with incremental updates
Store embeddings persistently (already done) but only recompute for new/modified documents, not all. This is the single biggest performance win for semantic search.
- **Scope**: `embeddings.py`

### 7.2 Lazy vault profile loading
`collect_existing_notes()` scans the entire vault on every invocation. Cache the profile and invalidate based on directory mtime for faster repeated runs.
- **Scope**: `vault_profile.py`

### 7.3 Parallel LLM and fetch calls
When doing batch imports, parallelize fetching and classification across URLs using `concurrent.futures`.
- **Scope**: `cli.py` (batch mode)

---

## Priority Order (suggested)

| Priority | Item | Impact | Effort |
|----------|------|--------|--------|
| P0 | 5.1 Integration tests | High | Medium | ✅ Done |
| P0 | 1.1 Retry with backoff | High | Low | ✅ Done |
| P0 | 7.1 Incremental embeddings | High | Low | ✅ Done (already implemented) |
| P1 | 1.2 Proper HTML parsing | Medium | Low | ✅ Done |
| P1 | 6.2 Logging | Medium | Medium | ✅ Done |
| P1 | 3.1 Batch import | High | Medium | ✅ Done |
| P1 | 3.6 Link health checking | Medium | Low | ✅ Done |
| P1 | 5.5 CI pipeline | Medium | Low | ✅ Done | ✅ Done |
| P2 | 3.2 Bookmark update/refresh | Medium | Medium | ✅ Done |
| P2 | 6.1 Unified config file | Medium | Medium |
| P2 | 2.3 Search snippets | Medium | Medium | ✅ Done |
| P2 | 4.4 Stats command | Low | Low | ✅ Done |
| P3 | 3.3 Interactive mode | Low | Low |
| P3 | 3.5 Archive content | Medium | Medium |
| P3 | 4.1 Tag normalization | Low | Medium |
| P3 | 4.2 Folder reorg tool | Low | High |
| P3 | 4.3 Bidirectional linking | Low | Medium |
