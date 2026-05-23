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

A bookmark note is a Markdown file in `BOOKMARKS_DIR` with YAML-like frontmatter containing at least a `url` field. The current default frontmatter fields are:

```yaml
---
title: Example
url: https://example.com
type: article
tags: [example]
created: 2026-05-23
last_updated: 2026-05-23
language: en
related: [example]
parent_topic: Bookmarks
visibility: private
description: Example description
---
```

The body currently contains a `Summary:` section. Future schema versions may add stable IDs, fetch metadata, content hashes, generated relationship blocks, and fetch timelines, but existing notes must remain readable.

## Archive sidecars

`bookmark --archive` may create cleaned content sidecars named `*.content.md`. These files are **not bookmark records** and must not be counted as bookmarks, classified, checked as links, or indexed as standalone bookmark notes.

Sidecars are cache/raw data. They can support search or future recrawl/change workflows, but only when explicitly referenced from a canonical bookmark note or derived catalog.

## Derived search state

The SQLite search database (`BOOKMARK_SEARCH_INDEX`, defaulting under `$VAULT_PATH/Meta/`) is derived state. It contains FTS rows and embeddings generated from bookmark notes. It is safe to delete and rebuild.

Commands that update, delete, or reorganize bookmarks should update the derived index when practical, but Markdown remains authoritative if the two diverge.

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
