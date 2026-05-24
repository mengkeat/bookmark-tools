# Phase 1B — Schema Hardening and Provenance Completion

**Date**: 2026-05-24
**Commits**: `4189768` .. `546312a` (8 commits)
**Tests**: 272 → 300 (+28 tests)
**Files changed**: 17 files, +851 / −71 lines

---

## Overview

Phase 1 established the schema v1 note format, tolerant parser, and stable IDs. Phase 1B closes the gaps that review identified: data loss on rewrite, ambiguous metadata semantics, missing provenance, and non-bookmark Markdown polluting vault scans.

The goal is that **every rewrite path preserves user data**, metadata has **precise tested semantics**, and the schema is ready for `bookmark-doctor` health checks in Phase 2.

---

## Commits

| Commit | Type | Summary |
|--------|------|---------|
| `4189768` | fix | Replace csv-based YAML list parser with proper flow sequence parser |
| `66af4f5` | feat | Preserve unknown frontmatter fields during re-renders |
| `c7d069d` | fix | Preserve human body sections during `--force` overwrite |
| `8ec9f7d` | feat | Extract canonical URL and hash full content |
| `e9c3ea3` | fix | Preserve original URL identity and refresh timestamps correctly |
| `7cb57f3` | feat | Return source provenance and track batch import source |
| `cbe0584` | feat | Skip non-bookmark Markdown in scans and fix archive ordering |
| `546312a` | feat | Add `validate_schema_v1` for frontmatter health checks |

---

## Detailed changes

### 1. YAML list parser rewrite (`4189768`)

**Problem**: The `_parse_inline_list()` function used Python's `csv.reader` to parse `[a, 'b', "c"]` syntax. `csv.reader` does not understand YAML single-quoted scalars, so a value like `'tag,with-comma'` was split at the comma, producing `["tag", "with-comma"]` instead of `["tag,with-comma"]`.

**Fix**: Replaced `csv.reader` with a hand-written parser that handles three YAML flow sequence scalar forms:
- **Plain scalars**: terminated by `,` or `]`
- **Single-quoted scalars**: `'value'` with `''` as escaped literal quote
- **Double-quoted scalars**: `"value"` with JSON-style escapes

**Files changed**: `bookmark_tools/note_schema.py`, `tests/test_note_schema.py`

**Tests added**: 10 round-trip tests covering commas, booleans, brackets, URLs, unicode, single-quote escaping, plain scalars with spaces, and full frontmatter parse cycles.

---

### 2. Unknown frontmatter field preservation (`66af4f5`)

**Problem**: `build_schema_v1_values()` built a fresh dict from schema v1 fields only. Any custom frontmatter keys (e.g., `rating: 5`, `custom_author: Jane`) were silently dropped during updates and forced overwrites.

**Fix**: 
- Added `OWNED_FIELDS = frozenset(SCHEMA_V1_FIELD_ORDER) | {"summary"}` to distinguish schema-managed keys from user/future keys.
- `build_schema_v1_values()` now merges unknown fields from `existing_metadata` into the output dict.
- `merge_field_order()` accepts `extra_keys` to place unknown fields after schema fields.
- `render_frontmatter()` accepts `existing_field_order` to preserve the original field position.
- `render_schema_v1()` accepts `existing_field_order` and passes it through.

**Files changed**: `bookmark_tools/note_schema.py`, `bookmark_tools/render.py`, `tests/test_note_schema.py`

**Tests added**: 3 tests for unknown field preservation in build, render, and full round-trip.

---

### 3. Human body preservation on `--force` (`c7d069d`)

**Problem**: `build_note(... force=True)` in `cli.py` did not read the existing note text, so `render_note()` received no `existing_note_text`. Human sections like `## Notes` were lost on forced overwrite. Only `bookmark-update` had this preservation.

**Fix**: When `force=True`, read the existing note file and pass `existing_note_text` through to `render_note()`. Also parse the existing note to preserve the original `url` field for stable identity.

**Files changed**: `bookmark_tools/cli.py`, `tests/test_integration.py`

**Tests added**: 1 integration test verifying `## Notes` sections survive forced overwrite.

---

### 4. Canonical URL extraction and full content hashing (`8ec9f7d`)

**Problem**: 
- `canonical_url` was always set to `final_url` — no actual canonical URL extraction from HTML.
- `content_hash` was computed from `page_data["content"]`, which is the 8 KB truncated classification preview. Long pages with changes beyond the first 8 KB would show the same hash.

**Fix**:
- Updated `_MetadataParser` in `fetch.py` to extract `<link rel="canonical">` from the HTML `<head>`.
- `extract_page_data()` resolves canonical URL in order: `<link rel="canonical">` → `og:url` → `final_url`.
- Added `full_content` to `PageData` TypedDict — the complete cleaned text without truncation.
- `render_note()` accepts `full_content` and uses it (falling back to `content`) for `content_hash` computation.
- `content_hash` semantics are now documented: SHA-256 of the full cleaned page text.

**Files changed**: `bookmark_tools/fetch.py`, `bookmark_tools/types.py`, `bookmark_tools/render.py`, `bookmark_tools/cli.py`, `bookmark_tools/update.py`, `tests/test_fetch.py`

**Tests added**: 5 fetch tests for canonical URL from `<link>`, `og:url` fallback, default to `final_url`, and `full_content` vs truncated `content`.

---

### 5. Original URL identity and timestamp semantics (`e9c3ea3`)

**Problem**:
- When updating a bookmark via `final_url` or `canonical_url`, `update_bookmark()` passed the lookup URL as `url` to `render_note()`, overwriting the original URL stored in the note.
- `last_success_at` had a fallback chain (`explicit → existing → computed`) that always preferred the existing value, so successful updates never refreshed it.

**Fix**:
- `update_bookmark()` now reads `original_url` from the existing note's frontmatter and passes it to `render_note()`.
- `build_note(... force=True)` also preserves the original URL from the existing note.
- Fixed `build_schema_v1_values()` timestamp logic:
  - If caller provides explicit `last_success_at`: use it
  - If `status == "ok"`: refresh to current `last_fetched_at`
  - If `status != "ok"`: preserve existing `last_success_at`
- `last_fetched_at` always refreshes (was already working correctly).

**Files changed**: `bookmark_tools/note_schema.py`, `bookmark_tools/cli.py`, `bookmark_tools/update.py`, `tests/test_note_schema.py`, `tests/test_update.py`

**Tests added**: 3 timestamp semantic tests, 1 original URL preservation test.

---

### 6. Summary and source provenance (`7cb57f3`)

**Problem**:
- `generate_summary()` returned only a string, losing information about which source produced it.
- `summary_model` was always the uninformative `"summary-pipeline-v1"`.
- Batch imports via `--file` did not record which file or line a URL came from.

**Fix**:
- `generate_summary()` now returns `tuple[str, str]` — `(summary_text, source_label)` where source_label is one of `"summarize"`, `"classifier"`, `"llm"`, or `"heuristic"`.
- The source label is recorded in the `summary_model` frontmatter field.
- `_read_urls_from_file()` returns `list[tuple[str, str, int]]` — `(url, source_path, line_number)`.
- `_dedupe_batch_urls()`, `_filter_existing_batch_urls()`, `_process_single_url()`, and `build_note()` propagate source provenance.
- `source_kind` is set to `"file"` for batch imports, `"url"` for single URL invocations.
- `source_path` records the file path or `"stdin"`.
- `source_line` records the 1-based line number.

**Files changed**: `bookmark_tools/summarize.py`, `bookmark_tools/cli.py`, `bookmark_tools/update.py`, `tests/test_bookmarks.py`, `tests/test_integration.py`

**Tests added**: Updated 2 existing summary tests to unpack tuples; enhanced URL file test to verify source provenance.

---

### 7. Bookmark-only vault scans and archive ordering (`cbe0584`)

**Problem**:
- `iter_bookmark_note_paths()` only excluded `*.content.md` sidecars. Any Markdown file under `Bookmarks/` (notes, templates, README files) entered the vault profile, search index, health checks, and update flows.
- Archive content was written *after* the bookmark note, so `archive_path` in the frontmatter could reference a file that didn't exist yet (or failed to write).

**Fix**:
- Added `bookmark_only=True` parameter to `iter_bookmark_note_paths()`.
- Added `_is_bookmark(path)` helper in `note_filter.py` that does a fast frontmatter scan for a `url:` key (avoids circular import with `note_schema.is_bookmark_note()`).
- Updated all scan consumers to use `bookmark_only=True`:
  - `vault_profile.collect_existing_notes()`
  - `search_documents.collect_search_documents()`
  - `check.check_bookmarks()`
  - `classify.find_existing_url()` (fallback path)
- `classify.related_note_count()` intentionally uses `bookmark_only=False` since it counts topic-similar notes in a folder, including non-bookmark Markdown.
- Restructured archive writing in `_process_single_url()`: archive is now written before the bookmark note, so `archive_path` metadata is accurate at write time.

**Files changed**: `bookmark_tools/note_filter.py`, `bookmark_tools/vault_profile.py`, `bookmark_tools/search_documents.py`, `bookmark_tools/check.py`, `bookmark_tools/classify.py`, `bookmark_tools/update.py`, `bookmark_tools/cli.py`, `tests/test_note_schema.py`

**Tests added**: 1 test for `iter_bookmark_note_paths(bookmark_only=True)` filtering.

---

### 8. Schema validation helper (`546312a`)

**Problem**: Phase 2 `bookmark-doctor` needs to validate note frontmatter without duplicating parser logic. No validation helper existed.

**Fix**: Added `validate_schema_v1(metadata)` that returns `list[SchemaIssue]`:

| Check | Severity | Description |
|-------|----------|-------------|
| Missing required field | error | `schema_version`, `id`, `url`, `title`, `created`, `last_updated` |
| Unsupported `schema_version` | error | Must be `1` |
| Invalid stable ID | warning | Must be 64-char hex SHA-256 |
| Malformed URL | warning | `url`, `final_url`, `canonical_url` must have scheme and netloc |
| Domain mismatch | warning | `domain` must match `canonical_url` hostname |
| Invalid date/timestamp | warning | `created`, `last_updated`, `added_at`, `last_fetched_at`, `last_success_at` must be ISO format |
| Invalid HTTP status | warning | `http_status` must be 3-digit code |
| Invalid content hash | warning | `content_hash` must be 64-char hex SHA-256 |

`SchemaIssue` is a frozen dataclass with `field`, `severity`, and `message`.

**Files changed**: `bookmark_tools/note_schema.py`, `tests/test_note_schema.py`

**Tests added**: 5 validation tests for valid metadata, missing fields, invalid ID, domain mismatch, and invalid HTTP status.

---

## Module changes summary

### `bookmark_tools/note_schema.py` (+255 lines)

The core schema module received the most changes:

- **New parser**: `_parse_inline_list()` rewritten from csv.reader to proper YAML flow sequence parser
- **Owned fields**: `OWNED_FIELDS` frozenset distinguishes schema-managed vs user keys
- **Unknown field preservation**: `build_schema_v1_values()` merges unknown fields from `existing_metadata`
- **Field order**: `merge_field_order()` accepts `extra_keys` for unknown field placement
- **Render chain**: `render_frontmatter()` and `render_schema_v1()` accept `existing_field_order` and `extra_keys`
- **Timestamp fix**: `last_success_at` correctly refreshes on success, preserves on failure
- **Validation**: `validate_schema_v1()` and `SchemaIssue` dataclass for doctor health checks

### `bookmark_tools/fetch.py` (+16 lines)

- `_MetadataParser` now extracts `<link rel="canonical">` into `canonical_url`
- `extract_page_data()` populates `canonical_url` with `<link>` → `og:url` → `final_url` fallback
- `extract_page_data()` populates `full_content` (complete cleaned text, not truncated)

### `bookmark_tools/cli.py` (+91 lines)

- `build_note()` reads existing note text on `force=True` for body preservation
- `build_note()` preserves original URL from existing note
- `build_note()` accepts and passes `source_kind`, `source_path`, `source_line`
- `_read_urls_from_file()` returns `(url, source_path, line_number)` tuples
- `_dedupe_batch_urls()`, `_filter_existing_batch_urls()` handle tuples
- `_process_single_url()` passes source provenance through
- Archive content is written before the bookmark note

### `bookmark_tools/summarize.py` (+22 lines)

- `generate_summary()` returns `(summary_text, source_label)` tuple
- Source labels: `"summarize"`, `"classifier"`, `"llm"`, `"heuristic"`

### `bookmark_tools/note_filter.py` (+32 lines)

- `_is_bookmark(path)` helper for fast frontmatter URL detection
- `iter_bookmark_note_paths(bookmark_only=True)` filters non-bookmark Markdown

### `bookmark_tools/render.py` (+4 lines)

- `render_note()` accepts `full_content` parameter, prefers it for content hashing
- Passes `existing_field_order` through to `render_schema_v1()`

### `bookmark_tools/types.py` (+4 lines)

- `PageData` gains `canonical_url` and `full_content` fields

### `bookmark_tools/update.py` (+14 lines)

- `update_bookmark()` preserves original `url` from existing note
- Passes `canonical_url` and `full_content` through to render
- Uses `summary_source` for provenance tracking

### `bookmark_tools/vault_profile.py`, `search_documents.py`, `check.py`, `classify.py` (minor)

- All scan consumers use `iter_bookmark_note_paths(bookmark_only=True)` (except `related_note_count`)

---

## Test coverage

| Test file | Tests added | Focus |
|-----------|------------|-------|
| `test_note_schema.py` | +22 | YAML round-trip, unknown fields, timestamps, validation, bookmark-only filtering |
| `test_fetch.py` | +5 | Canonical URL extraction, full content |
| `test_integration.py` | +1 | Force-overwrite body preservation |
| `test_update.py` | +1 | Original URL preservation |

**Total**: 272 → 300 tests (+28)

---

## Deferred items

Two deliverables from Phase 1B are intentionally deferred to later phases:

1. **Fetch timeline generated block** → Phase 7 (recrawl/snapshots) — the fetch timeline block helpers exist in `note_schema.py` but are not yet rendered into notes. Rendering them will be more valuable once recrawl history accumulates.

2. **Relationships generated block** → Phase 6 (graph/backlinks) — relationship block helpers exist but integrating them requires the graph edge model and backlink infrastructure from Phase 6.

Both helpers (`render_fetch_timeline_block()`, `render_relationships_block()`, `generated_block()`, `update_generated_block()`) are fully implemented and tested; they just need to be wired into the render pipeline at the right time.

---

## Breaking changes

None. All changes are backward-compatible:
- Existing notes without `schema_version` still parse via tolerant parsing
- New `PageData` fields (`canonical_url`, `full_content`) use `.get()` at call sites, defaulting gracefully
- `generate_summary()` return type changed from `str` to `tuple[str, str]` — internal API only, not CLI-facing
- `bookmark_only=True` may cause some previously-visible Markdown files to no longer appear in search/profile/stats — this is the intended behavior (they were never bookmarks)

---

## Next phase

Phase 2 (`bookmark-doctor` and rebuildable derived state) can now proceed with:
- `validate_schema_v1()` as the schema validation bridge
- `bookmark_only=True` filtering for accurate vault scans
- Precise metadata semantics for health checks
- Source provenance for audit trails
