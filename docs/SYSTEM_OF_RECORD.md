# Bookmark Tools System of Record

This document defines which project data is canonical and which data is derived or runtime-only.

## Core rule

**Bookmark Markdown notes are the system of record. Search indexes, embeddings, generated views, and caches are derived.**

A healthy vault should be recoverable from the Markdown notes under `BOOKMARKS_DIR` plus local configuration. If a derived database is deleted, the tool should be able to rebuild it from the notes.

## Data categories

| Category | Examples | Rule |
|---|---|---|
| Canonical user knowledge | Bookmark notes under `BOOKMARKS_DIR/**/*.md`; user-written summaries/notes; classification guide. | Preserve and treat as authoritative. |
| Derived from Markdown | SQLite FTS index, embedding rows, future chunk/edge/catalog tables, generated topic/domain/tag pages. | Rebuild from canonical notes. Do not require backup. |
| Cache / raw fetch data | `*.content.md` archive sidecars, future raw HTML/text/PDF snapshots, HTTP headers. | May be deleted, although recrawl can be lossy if the source URL changes or disappears. |
| Runtime-only state | Future jobs, checkpoints, progress rows, transient failure records. | Not user knowledge; may be dropped or retried. |
| Local secrets/config | `.env`, API keys, local path/provider settings. | Never commit secrets. Validate before commands run. |

## Current canonical bookmark shape

A bookmark note is a Markdown file in `BOOKMARKS_DIR` with YAML-like frontmatter containing at least a `url` field. New notes are rendered as schema v1 records:

```yaml
---
schema_version: 1
id: <sha256(normalized original url)>
title: Example
url: https://example.com          # Original URL from user input
final_url: https://example.com    # URL after HTTP redirects
canonical_url: https://example.com  # From <link rel="canonical"> or og:url
domain: example.com
type: article
tags: [example]
added_at: 2026-05-24
last_fetched_at: 2026-05-24T00:00:00Z
last_success_at: 2026-05-24T00:00:00Z
created: 2026-05-24
last_updated: 2026-05-24
language: en
related: [example]
parent_topic: Bookmarks
visibility: private
status: ok
http_status: 200
content_type: text/html
content_hash: <sha256(full cleaned text)>
archive_path:
classification_model: heuristic
classification_prompt_version: v1
summary_model: heuristic
source_kind: url
source_path:
source_line:
description: Example description
---
```

The body starts with a generated `Summary:` block using explicit `bookmark-tools` markers. Human-authored sections such as `## Notes` live outside generated blocks and are preserved by update/migration flows. Existing legacy notes without `schema_version` remain readable through tolerant parsing.

## Data preservation guarantees

Schema v1 notes are designed for safe round-trips through update and forced overwrite:

- **Unknown fields preserved**: Frontmatter keys not owned by schema v1 (e.g., user-added `rating` or future `custom_field`) are carried forward unchanged during re-renders. Only `OWNED_FIELDS` (the 30 schema v1 keys) are overwritten.
- **Human body preserved**: Sections like `## Notes` outside generated blocks survive updates and force-overwrites. The `extract_human_body()` helper strips generated blocks and legacy `Summary:` paragraphs but keeps user content.
- **Original URL preserved**: On update or `--force`, the `url` field is kept from the existing note. Updates triggered via `final_url` or `canonical_url` do not change the original URL or stable ID.
- **Timestamp semantics**: `last_fetched_at` refreshes on every fetch attempt. `last_success_at` refreshes on successful fetches and is preserved on failures. `added_at` and `created` are never overwritten.
- **Content hash**: `content_hash` is the SHA-256 of the full cleaned page text (not the 8 KB classification preview), enabling accurate change detection.
- **Canonical URL**: Resolved from `<link rel="canonical">`, then `og:url`, then `final_url`. Stored as a separate identity hint.

## Schema validation

`validate_schema_v1(metadata)` checks frontmatter for:

- Missing required fields (`schema_version`, `id`, `url`, `title`, `created`, `last_updated`)
- Invalid stable ID format (must be 64-char hex SHA-256)
- Unsupported `schema_version`
- Malformed URL fields
- Domain / canonical_url hostname mismatch
- Invalid date/timestamp formats
- Invalid HTTP status codes
- Invalid content_hash format

Returns a list of `SchemaIssue` records with severity (`"error"` or `"warning"`). Designed for consumption by `bookmark-doctor` (Phase 2).

## Archive sidecars

`bookmark --archive` may create cleaned content sidecars named `*.content.md`. These files are **not bookmark records** and must not be counted as bookmarks, classified, checked as links, or indexed as standalone bookmark notes.

Sidecars are cache/raw data. They can support search or future recrawl/change workflows, but only when explicitly referenced from a canonical bookmark note or derived catalog.

## Derived search state

The SQLite search database (`BOOKMARK_SEARCH_INDEX`, defaulting under `$VAULT_PATH/Meta/`) is derived state. It contains FTS rows and embeddings generated from bookmark notes. It is safe to delete and rebuild with `bookmark-rebuild`.

Commands that update, delete, or reorganize bookmarks should update the derived index when practical, but Markdown remains authoritative if the two diverge. `bookmark-doctor` reports missing, corrupt, stale, or incomplete search state and `bookmark-doctor --fix` can safely rebuild the search index from Markdown.

Embedding rows record the configured embedding model and vector dimensions used to create them. Semantic search refuses mismatched embedding stores, and `bookmark-doctor` reports model/dimension drift so the store can be rebuilt. Provider/model settings are resolved by `bookmark_tools/config.py` from CLI overrides, environment variables, `bookmark-tools.toml`, and defaults.

## Doctor and rebuild contract

`bookmark-doctor` is the health surface for the Markdown system of record and its derived state. It reports:

- missing/invalid bookmark path configuration,
- missing provider/API configuration,
- schema v1 frontmatter issues via `validate_schema_v1()`,
- non-bookmark Markdown under `Bookmarks/`,
- duplicate original/final/canonical URL identities,
- missing archive paths and orphan `*.content.md` sidecars,
- missing/corrupt/stale search indexes and notes missing from FTS,
- embedding model/dimension mismatch,
- broken Obsidian `[[internal links]]`.

`bookmark-doctor --json` emits a stable report object with `status`, `score`, `summary`, path fields, and issue records. `bookmark-doctor --fix` only performs safe derived-state repairs (currently search rebuilds and embedding rebuilds when API configuration is available). It must not delete notes or alter human-authored Markdown.

`bookmark-rebuild` reconstructs current derived state from Markdown: FTS search is always rebuilt; embeddings are rebuilt only when API configuration is available or skipped with an explicit reason.

## Path validation

Commands must fail fast with an actionable error when neither `BOOKMARKS_DIR` nor a valid `VAULT_PATH` is configured. They must not silently scan the current working directory as a fallback vault.

## Rule for new user-knowledge features

When adding a new user-visible knowledge category:

1. Define its Markdown/frontmatter/generated-block representation.
2. Make parsing tolerant of older notes.
3. Keep machine-generated edits inside explicit generated blocks.
4. Add a rebuild path for any derived DB/index tables.
5. Add doctor checks for divergence or corruption.

If the data is not recoverable from Markdown, document why it is cache/runtime-only.
