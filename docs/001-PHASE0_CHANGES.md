# Phase 0 — Correctness, Drift Cleanup, and System-of-Record Contract

This document describes the concrete changes delivered in Phase 0. The goal was to stop building on ambiguous or drifting behavior by establishing clear invariants about what is canonical, making commands fail fast on misconfiguration, and eliminating silent data corruption from archive sidecar pollution, weak URL identity, and batch duplicate races.

---

## Table of contents

- [Summary of deliverables](#summary-of-deliverables)
- [1. System-of-record contract](#1-system-of-record-contract)
- [2. Fail-fast vault path validation](#2-fail-fast-vault-path-validation)
- [3. Archive sidecar exclusion](#3-archive-sidecar-exclusion)
- [4. README and code reconciliation](#4-readme-and-code-reconciliation)
- [5. Shared URL normalization](#5-shared-url-normalization)
- [6. Batch duplicate prevention](#6-batch-duplicate-prevention)
- [7. Original vs. final URL separation](#7-original-vs-final-url-separation)
- [8. Test coverage](#8-test-coverage)
- [Files added](#files-added)
- [Files modified](#files-modified)

---

## Summary of deliverables

| # | Deliverable | Status |
|---|---|---|
| 1 | System-of-record document (`docs/000-SYSTEM_OF_RECORD.md`) | ✅ Done |
| 2 | Fail-fast validation when `VAULT_PATH`/`BOOKMARKS_DIR` is missing or invalid | ✅ Done |
| 3 | Archive sidecar (`*.content.md`) exclusion from all bookmark scans | ✅ Done |
| 4 | README reconciled with actual code behavior | ✅ Done |
| 5 | Shared URL normalization module | ✅ Done |
| 6 | Batch duplicate/race prevention | ✅ Done |
| 7 | Original URL preserved separately from final (redirect) URL | ✅ Done |
| 8 | Tests for all of the above | ✅ Done |

---

## 1. System-of-record contract

**New file:** `docs/000-SYSTEM_OF_RECORD.md`

Before Phase 0, Markdown notes appeared to be canonical, but this was never documented or enforced. This created ambiguity about whether the SQLite search database, embeddings, or archive files were authoritative when they diverged from notes.

The new document explicitly defines five data categories:

| Category | Examples | Rule |
|---|---|---|
| Canonical user knowledge | Bookmark notes (`$BOOKMARKS_DIR/**/*.md`), classification guide | Preserve and treat as authoritative |
| Derived from Markdown | SQLite FTS index, embedding rows, future catalog/edge tables | Rebuildable from canonical notes |
| Cache / raw fetch data | `*.content.md` archive sidecars, raw HTML/text snapshots | Safe to delete; recrawl may be lossy |
| Runtime-only state | Future jobs, checkpoints, progress rows | Not user knowledge; can be dropped |
| Local secrets/config | `.env`, API keys | Never committed; validated before commands run |

**Key invariants established:**

- A healthy vault is recoverable from Markdown notes + local config alone.
- Deleting the SQLite search database and rebuilding is always safe.
- Archive sidecars are cache, not canonical bookmarks.
- New user-knowledge features must define a Markdown representation and a rebuild path.

---

## 2. Fail-fast vault path validation

**Modified file:** `bookmark_tools/paths.py`

### The problem

When neither `VAULT_PATH` nor `BOOKMARKS_DIR` was configured, `_default_bookmarks_dir()` returned `Path()`, which resolves to the current working directory (`.`). Commands would silently scan the working directory tree for Markdown files, producing misleading counts, searches, and classifications.

### What changed

A new `require_bookmarks_dir()` function was added as the gatekeeper for all commands that need a valid vault:

```python
class BookmarkPathError(RuntimeError):
    """Raised when bookmark vault paths are missing or invalid."""

def require_bookmarks_dir() -> Path:
    ...
```

**Validation rules:**

1. If neither `BOOKMARKS_DIR` nor `VAULT_PATH` is set → raise `BookmarkPathError` with an actionable message telling the user to set one of them.
2. If `VAULT_PATH` is set but does not point to an existing directory → raise `BookmarkPathError`.
3. If `BOOKMARKS_DIR` exists but is a file (not a directory) → raise `BookmarkPathError`.

**Where it is used:**

- `cli.py` (`main()`): calls `require_bookmarks_dir()` before any bookmark processing.
- `check.py`, `stats.py`, `reorg.py`: each call `require_bookmarks_dir()` at entry.

The existing `get_bookmarks_dir()` function remains available for code that needs the path without validation (e.g., help text or dry-run output).

---

## 3. Archive sidecar exclusion

**New file:** `bookmark_tools/note_filter.py`

### The problem

The `--archive` flag writes cleaned page content beside each bookmark note as `<slug>.content.md`. However, all vault scans used glob patterns like `**/*.md`, which included these sidecars. This caused:

- **Inflated bookmark counts** in stats and doctor output.
- **Sidecar content appearing in search results** as if it were a standalone bookmark.
- **Sidecars used in classification similarity ranking**, biasing folder/tag decisions.
- **Sidecars checked for dead links** even though they are not bookmarks.
- **Sidecars appearing in update/reorg operations** that only make sense for real bookmarks.

### What changed

A new `note_filter` module provides two functions:

```python
ARCHIVE_SIDECAR_SUFFIX = ".content.md"

def is_archive_sidecar(path: Path) -> bool:
    """Return True when path is a cleaned-content archive sidecar."""
    return path.name.endswith(ARCHIVE_SIDECAR_SUFFIX)

def iter_bookmark_note_paths(
    bookmarks_dir: Path, *, recursive: bool = True
) -> Iterator[Path]:
    """Yield Markdown note paths that should be treated as bookmark records."""
    ...
```

`iter_bookmark_note_paths()` replaces bare `bookmarks_dir.glob("**/*.md")` calls throughout the codebase. It yields all `.md` files except those ending in `.content.md`.

**Modules updated to use `iter_bookmark_note_paths`:**

| Module | What it scans | Impact of the fix |
|---|---|---|
| `vault_profile.py` | `collect_existing_notes()` builds `BookmarkProfile` | Sidecars excluded from notes list, URL index, folder examples, similarity tokens |
| `search_documents.py` | `collect_search_documents()` builds `SearchDocument` records | Sidecars excluded from FTS index and embedding text |
| `classify.py` | `find_existing_url()` fallback scan | Sidecars excluded from duplicate URL detection |
| `classify.py` | `related_note_count()` scans a parent folder | Sidecars excluded from related-note counts |
| `check.py` | `check_bookmarks()` scans for URLs to health-check | Sidecars no longer checked for dead links |
| `update.py` | `update_bookmark()` scans for bookmarks to update | Sidecars excluded from update operations |

---

## 4. README and code reconciliation

**Modified file:** `README.md`

### What was fixed

1. **TOML config claims removed.** The README previously described a unified `bookmark-tools.toml` configuration file, but no TOML config loader was implemented. These claims were removed and deferred to Phase 3.

2. **Bidirectional backlink claims removed.** The README referenced automatic backlink updates, but `update_related_backlinks()` was never wired into the bookmark creation pipeline. These claims were removed.

3. **Dependency description corrected.** The README previously stated "zero runtime dependencies beyond stdlib." In reality, `pyproject.toml` requires `flask` (for the web UI) and `numpy` (for vector operations). The description was updated to "mostly stdlib; Flask powers the web UI and NumPy accelerates vectors."

4. **Project structure** was updated to reflect actual files after Phase 0 additions.

---

## 5. Shared URL normalization

**New file:** `bookmark_tools/url_normalize.py`

### The problem

Duplicate detection used `url.rstrip('/')` as its only normalization. This meant URLs that differed only in case (`HTTP://` vs `http://`), default ports (`http://example.com:80/` vs `http://example.com/`), or trailing slashes on query-bearing URLs were treated as different bookmarks, allowing duplicates to slip through.

### What changed

A new `normalize_url()` function provides conservative, deterministic URL normalization:

```python
def normalize_url(url: str) -> str:
    """Return a conservative normalized URL for identity comparisons."""
```

**Normalization rules (intentionally conservative):**

| Transformation | Example |
|---|---|
| Strip leading/trailing whitespace | `"  https://example.com  "` → `"https://example.com"` |
| Lowercase scheme | `"HTTPS://example.com"` → `"https://example.com"` |
| Lowercase hostname (with IDNA encoding) | `"https://EXAMPLE.COM"` → `"https://example.com"` |
| Strip default ports | `"http://example.com:80/path"` → `"http://example.com/path"` |
| Strip trailing slashes from path | `"https://example.com/path/"` → `"https://example.com/path"` |
| Preserve non-default ports | `"https://example.com:8443"` → `"https://example.com:8443"` |
| Preserve query strings | `"https://example.com?q=test"` unchanged |
| Preserve fragments | `"https://example.com#section"` unchanged |
| Preserve userinfo | `"https://user:pass@example.com"` unchanged |
| Normalize URL-encoded paths | `"/%7E/foo"` → `"/%7E/foo"` (safe characters re-encoded consistently) |
| Handle IPv6 hosts | `"https://[::1]:8443"` preserved with brackets |

**What it deliberately does NOT do:**

- Does not strip `www.` subdomain (may change resource identity).
- Does not remove tracking query parameters (too aggressive for identity comparison).
- Does not follow redirects or resolve canonical URLs (that is a network operation).
- Does not decode percent-encoded characters beyond safe-path normalization.

**Where it is used:**

| Module | Usage |
|---|---|
| `cli.py` | `_dedupe_batch_urls()`: deduplicates batch input URLs by normalized identity |
| `cli.py` | `_filter_existing_batch_urls()`: checks vault for existing bookmarks by normalized URL |
| `classify.py` | `find_existing_url()`: builds and queries `BookmarkProfile.url_index` with normalized keys |
| `vault_profile.py` | `collect_existing_notes()`: populates `url_index` using normalized `url` and `final_url` keys |
| `update.py` | `update_bookmark()` / `find_bookmark_path()`: locates bookmarks by normalized URL |
| `delete.py` | `find_bookmark_path()`: locates bookmarks by normalized URL |

---

## 6. Batch duplicate prevention

**Modified file:** `bookmark_tools/cli.py`

### The problem

When running `bookmark --file urls.txt` with many URLs, two issues caused duplicate notes:

1. **Input-level duplicates**: The same URL appearing multiple times in the input file would each go through the full pipeline and create separate notes.
2. **Vault-level races**: Each URL invocation scanned the full vault independently. With parallel workers, two identical URLs could both pass the duplicate check before either was written.

### What changed

Three fixes were applied:

#### 6a. Input deduplication: `_dedupe_batch_urls()`

```python
def _dedupe_batch_urls(urls: list[str]) -> list[str]:
    """Return URLs deduplicated by normalized identity while preserving order."""
```

Before any processing begins, the batch URL list is deduplicated using `normalize_url()`. The first occurrence of each URL identity wins; subsequent duplicates are logged as warnings and skipped.

#### 6b. Pre-flight vault check: `_filter_existing_batch_urls()`

```python
def _filter_existing_batch_urls(
    urls: list[str], *, force: bool, failures_list, profile: BookmarkProfile
) -> list[str]:
    """Skip URLs already present in the vault before starting batch workers."""
```

After deduplication but before spawning workers, each URL is checked against `profile.url_index` (built once from the vault). URLs already bookmarked are recorded as `BatchFailure` entries and excluded from processing. The `--force` flag bypasses this check.

#### 6c. Profile reuse across batch

Previously, each call to `build_note()` invoked `collect_existing_notes()` to scan the full vault. In batch mode, this meant scanning the vault N times (once per URL).

Now the batch flow builds the profile **once** and passes it to every worker:

```python
batch_profile = collect_existing_notes(bookmarks_dir=bookmarks_dir)
# ... passed to _filter_existing_batch_urls() and each _process_single_url() call
```

This eliminates redundant filesystem scans and ensures all workers share a consistent view of existing bookmarks at the start of the batch.

---

## 7. Original vs. final URL separation

**Modified files:** `fetch.py`, `types.py`, `classify.py`, `render.py`, `cli.py`, `vault_profile.py`

### The problem

When a URL redirected (e.g., `http://example.com` → `https://example.com/page`), the original URL was replaced by the final URL in the bookmark note. This meant:

- Re-importing the same original URL could create a duplicate (the vault now contains the final URL, not the original).
- The user's intended URL was lost.
- Duplicate detection could not catch both directions.

### What changed

#### `fetch.py:extract_page_data()`

Now returns **both** URLs in the `PageData` dict:

```python
return {
    "url": url,              # original URL as provided by the user
    "final_url": final_url,  # URL after following HTTP redirects
    ...
}
```

#### `types.py:PageData`

Added `final_url` as a required field:

```python
class PageData(TypedDict):
    url: str
    final_url: str  # URL after following HTTP redirects
    ...
```

#### `vault_profile.py:collect_existing_notes()`

The URL index now maps **both** normalized `url` and normalized `final_url` to the same note path, so duplicate detection catches a match from either direction:

```python
existing_url = normalize_url(str(metadata.get("url", "")))
existing_final_url = normalize_url(str(metadata.get("final_url", "")))
url_index[existing_url] = note_path
if existing_final_url and existing_final_url != existing_url:
    url_index[existing_final_url] = note_path
```

#### `classify.py:find_existing_url()`

Checks both the incoming URL and the final URL (if different) against the vault index:

```python
normalized = normalize_url(url)
if normalized in profile.url_index:
    return profile.url_index[normalized]
# Also check final_url if the page redirects
if not existing and page_data["final_url"] != page_data["url"]:
    existing_by_final = find_existing_url(page_data["final_url"], profile)
```

#### `render.py:render_note()`

Now accepts an optional `final_url` parameter and includes it in the frontmatter when it differs from the original URL:

```python
if final_url and final_url != url:
    values["final_url"] = final_url
```

---

## 8. Test coverage

**New test files:**

| Test file | Tests | What it covers |
|---|---|---|
| `tests/test_note_filter.py` | 12 | `is_archive_sidecar()` detection for various filename patterns; `iter_bookmark_note_paths()` yielding regular notes, excluding sidecars, recursive/non-recursive modes, empty directories, non-`.md` files |
| `tests/test_url_normalize.py` | 27 | Whitespace stripping, empty input, scheme/host case folding, default port stripping, non-default port preservation, trailing slash removal, query/fragment preservation, userinfo handling, IPv6, URL-encoded path normalization, identity comparisons |
| `tests/test_paths.py` | 9 | `require_bookmarks_dir()` raising on missing env, invalid `VAULT_PATH`, `BOOKMARKS_DIR` pointing to a file, succeeding with valid paths, `get_bookmarks_dir()` fallbacks and overrides |

**Total new tests: 48**

All tests use `unittest` with `unittest.mock` for environment variable isolation, consistent with the existing test suite.

---

## Files added

| File | Purpose |
|---|---|
| `docs/000-SYSTEM_OF_RECORD.md` | Defines canonical vs. derived vs. cache data categories and invariants |
| `docs/001-PHASE0_CHANGES.md` | This document |
| `bookmark_tools/note_filter.py` | `is_archive_sidecar()` and `iter_bookmark_note_paths()` for vault scan hygiene |
| `bookmark_tools/url_normalize.py` | `normalize_url()` for conservative URL identity comparison |
| `tests/test_note_filter.py` | 12 tests for archive sidecar detection and bookmark path iteration |
| `tests/test_url_normalize.py` | 27 tests for URL normalization rules and identity comparisons |
| `tests/test_paths.py` | 9 tests for fail-fast vault path validation |

## Files modified

| File | Change |
|---|---|
| `bookmark_tools/paths.py` | Added `BookmarkPathError` exception and `require_bookmarks_dir()` validator |
| `bookmark_tools/fetch.py` | `extract_page_data()` returns both `url` (original) and `final_url` (after redirects) |
| `bookmark_tools/types.py` | `PageData` TypedDict includes required `final_url` field |
| `bookmark_tools/vault_profile.py` | Uses `iter_bookmark_note_paths()` instead of raw glob; builds `url_index` with both `url` and `final_url` keys |
| `bookmark_tools/classify.py` | Uses `iter_bookmark_note_paths()` and `normalize_url()`; duplicate check covers both original and final URLs |
| `bookmark_tools/render.py` | `render_note()` accepts optional `final_url`; includes it in frontmatter when different from `url` |
| `bookmark_tools/cli.py` | Batch flow uses `_dedupe_batch_urls()`, `_filter_existing_batch_urls()`, and shared profile; uses `require_bookmarks_dir()` |
| `bookmark_tools/check.py` | Uses `iter_bookmark_note_paths()` instead of raw glob; uses `require_bookmarks_dir()` |
| `bookmark_tools/update.py` | Uses `iter_bookmark_note_paths()` and `normalize_url()` |
| `bookmark_tools/delete.py` | Uses `normalize_url()` for URL-based bookmark lookup |
| `bookmark_tools/search_documents.py` | Uses `iter_bookmark_note_paths()` instead of raw glob |
| `README.md` | Removed TOML config and backlink claims; corrected dependency description; updated project structure |
