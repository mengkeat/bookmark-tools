# Tests

Unit tests and manual smoke-check guidance for the `bookmark_tools` package.

## Quick navigation

- [Start here (quick path)](#start-here-quick-path)
- [Running tests](#running-tests)
- [Manual bookmark CLI smoke checks (no file writes)](#manual-bookmark-cli-smoke-checks-no-file-writes)
- [Summary generation order (progressive fallback)](#summary-generation-order-progressive-fallback)

## Start here (quick path)

```bash
uv sync
uv run pytest
```

For quick manual verification of bookmark generation behavior (without writing files):

```bash
uv run bookmark "https://example.com" --dry-run
```

## Running tests

```bash
uv run pytest                                  # all tests
uv run pytest -v                               # verbose output
uv run pytest tests/test_bookmarks.py          # single file
uv run pytest -k test_infer_summary_uses_description_first  # single test by name
```

## Manual bookmark CLI smoke checks (no file writes)

Use dry-run while iterating on classification/summary behavior so vault files are not written:

```bash
uv run bookmark "https://example.com" --dry-run
uv run python -m bookmark_tools "https://example.com" --dry-run
```

`--dry-run` prints the target path, optional folder decision message, and full rendered note content without writing to disk.

## Summary generation order (progressive fallback)

When adding a bookmark, summary generation follows this order:

1. `summarize` CLI output (`bookmark_tools/summarize.py:summarize_with_tool`)
2. Classifier-provided summary from `call_llm(...)` metadata
3. Direct summary LLM fallback (`summarize_with_llm(...)`)
4. Heuristic fallback (`render.py:infer_summary(...)`)

This means the system prefers the dedicated summarizer tool first, then reuses existing classifier output before making another LLM request.
