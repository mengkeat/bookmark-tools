# Phase 2 — Bookmark Doctor and Rebuildable Derived State

**Date**: 2026-05-24
**Commits**: Phase 2 implementation commits starting at `999c85d`
**Tests**: 300 → 312 (+12 tests)

---

## Goal

Phase 2 makes vault health visible and repairable. Markdown bookmark notes remain the system of record; search indexes and embeddings are derived state that can be diagnosed and rebuilt.

---

## Implemented commands

### `bookmark-rebuild`

Rebuilds derived state from canonical Markdown notes:

```bash
uv run bookmark-rebuild
uv run bookmark-rebuild --no-embeddings
uv run bookmark-rebuild --json
```

Behavior:

- Rebuilds the FTS5 search index from `collect_search_documents()`.
- Rebuilds embeddings when an LLM/embedding API configuration is available.
- Skips embeddings with an explicit reason when no API key is configured.
- Emits either human-readable text or a stable JSON result object.

Acceptance covered: deleting the search DB and running rebuild restores keyword search.

### `bookmark-doctor`

Diagnoses vault and derived-state health:

```bash
uv run bookmark-doctor
uv run bookmark-doctor --json
uv run bookmark-doctor --fix
```

Output includes:

- `status`: `ok`, `warning`, or `error`
- `score`: simple 0–100 health score
- `summary`: unresolved error/warning counts and fixed issue count
- `bookmarks_dir` and `database_path`
- `issues`: stable issue objects with `code`, `severity`, `message`, `path`, `field`, `fixable`, `fixed`, and optional `details`

`--fix` currently performs only safe derived-state repairs:

- rebuild missing/corrupt/stale/incomplete FTS search index,
- rebuild embeddings when embedding metadata is stale and provider config is available.

It does **not** delete notes, remove archives, or mutate user-authored Markdown.

---

## Health checks added

| Check | Code(s) | Severity | Fixable |
|---|---|---:|---:|
| Missing `BOOKMARKS_DIR`/`VAULT_PATH` | `config.bookmarks_dir` | error | no |
| Configured bookmarks path missing/not directory | `config.bookmarks_dir_missing`, `config.bookmarks_dir_not_directory` | error | no |
| Missing LLM/API key | `provider.api_key_missing` | warning | no |
| Schema v1 validation findings | `schema.invalid` | error/warning | no |
| Non-bookmark Markdown under `Bookmarks/` | `notes.non_bookmark_markdown` | warning | no |
| Duplicate normalized URL identities | `url.duplicate` | error | no |
| Missing referenced archive | `archive.missing` | warning | no |
| Orphan `*.content.md` sidecar | `archive.orphan_sidecar` | warning | no |
| Search DB missing | `search.missing` | warning | yes |
| Search DB corrupt/unreadable | `search.corrupt` | error | yes |
| Search schema missing tables | `search.schema_missing` | warning | yes |
| Notes missing from FTS/mtime table | `search.notes_missing` | warning | yes |
| Stale indexed mtimes | `search.stale` | warning | yes |
| Removed notes still indexed | `search.removed_notes` | warning | yes |
| Embedding table missing model/dim columns | `embedding.metadata_missing` | warning | yes when API available |
| Embedding model/dimension mismatch | `embedding.mismatch` | warning | yes when API available |
| Broken Obsidian links | `links.broken_internal` | warning | no |

---

## Embedding metadata hardening

Embedding rows now store:

- `model`
- `dimensions`

`refresh_embeddings()` re-embeds unchanged notes when the configured model or dimensions differ from the stored row metadata.

`semantic_search()` refuses direct searches against a mismatched embedding store and tells the user to run `bookmark-rebuild`.

`rebuild_embeddings()` drops and recreates the embedding table, removing stale rows and writing fresh model/dimension metadata.

---

## Files added

- `bookmark_tools/rebuild.py` — derived-state rebuild command and API
- `bookmark_tools/doctor.py` — health checks, JSON/text reports, safe fixes
- `tests/test_rebuild.py` — rebuild behavior and JSON output
- `tests/test_doctor.py` — doctor checks, JSON output, and safe fixes

## Files modified

- `bookmark_tools/embeddings.py` — model/dimension metadata, mismatch handling, full rebuild helper
- `pyproject.toml` — new scripts: `bookmark-rebuild`, `bookmark-doctor`
- `README.md` — usage docs for doctor/rebuild
- `docs/SYSTEM_OF_RECORD.md` — derived-state and doctor/rebuild contract

---

## Test coverage

| Test file | Tests added | Focus |
|---|---:|---|
| `tests/test_embeddings.py` | +4 | model/dimension storage, refresh on model change, mismatch refusal, full rebuild |
| `tests/test_rebuild.py` | +3 | DB deletion/rebuild, no-API skip reason, JSON output |
| `tests/test_doctor.py` | +5 | config error, core issue detection, search repair, embedding mismatch, JSON output |

Total suite: **312 tests** plus 7 subtests.

---

## Deferred / future expansion

- README/code feature drift check is listed as “if practical” in the plan and remains a future enhancement.
- Doctor repairs are intentionally conservative. Future safe fixes may include generated migrations, stale archive cleanup previews, and structured remediation plans.
- Catalog/graph/chunk derived state will be added to `bookmark-rebuild` in later phases.
