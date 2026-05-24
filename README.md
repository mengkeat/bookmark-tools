# Bookmark Tools

CLI tools for fetching, classifying, summarizing, and searching bookmarks in an Obsidian vault.

## Features

- **Schema v1 bookmark notes**: Self-describing notes with stable IDs, fetch metadata, content hashes, canonical URLs, and source provenance. See `docs/SYSTEM_OF_RECORD.md` for the full schema.
- **Bookmark creation**: Fetch a web page, classify it with LLM (or heuristic fallback), generate a summary, and write a structured markdown note to your vault.
- **Batch import**: Import multiple URLs from a file or stdin with `--file`/`-f`. Source file and line number are recorded for provenance.
- **Interactive mode**: Review and confirm classification before writing with `--interactive`/`-i`.
- **Content archiving**: Save a cleaned copy of page content alongside the bookmark with `--archive`; archive sidecars are ignored by bookmark scans and search indexing.
- **Bookmark update**: Re-fetch and re-classify existing bookmarks with `bookmark-update`, preserving creation date, original URL, human notes, and unknown frontmatter. Supports `--all` and `--folder` for bulk updates.
- **Bookmark deletion**: Delete bookmarks by URL or file path with `bookmark-delete`, cleaning up search index and embeddings.
- **Search**: BM25 keyword search, semantic vector search, or hybrid search with context snippets. Filter by `--tag`, export as JSON/CSV.
- **Derived-state rebuilds**: Rebuild FTS search and embedding state from Markdown with `bookmark-rebuild`.
- **Vault doctor**: Diagnose config, schema, duplicate URLs, archive references, search index state, embedding metadata, non-bookmark Markdown, and broken Obsidian links with `bookmark-doctor`.
- **Link health checking**: Validate all bookmarked URLs with `bookmark-check` to find dead links.
- **Vault statistics**: View bookmark counts, tag distribution, and folder stats with `bookmark-stats`.
- **Folder reorganization**: Propose folder reclassifications with `bookmark-reorg`.
- **Tag normalization**: Consistent lowercase kebab-case tags with abbreviation alias resolution.
- **Related-topic metadata**: Populate `related` and `parent_topic` fields from LLM or heuristic signals.
- **Schema validation**: `validate_schema_v1()` checks required fields, stable ID format, URL validity, domain consistency, and timestamp formats — ready for `bookmark-doctor` health checks.
- **Small dependency set**: Core tooling is mostly stdlib; Flask powers the web UI and NumPy accelerates vector similarity.

## Installation

```bash
git clone <repo-url>
cd bookmark-tools
uv sync
```

## Configuration

Settings are currently configured with environment variables. `load_env()` reads `.env` files from the configured vault, the vault parent, the current directory, or the path specified by `BOOKMARK_ENV_FILE`.

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

#### Required environment variables

| Variable | Description |
|---|---|
| `VAULT_PATH` | Path to your Obsidian vault root. Used to derive `Bookmarks/` and `Meta/` defaults unless overridden. |

Alternatively, set `BOOKMARKS_DIR` directly for commands that operate on a bookmark directory.

#### Optional overrides and provider settings

| Variable | Description |
|---|---|
| `BOOKMARKS_DIR` | Override the bookmarks directory (default: `$VAULT_PATH/Bookmarks`) |
| `BOOKMARK_SEARCH_INDEX` | Override the search database path (default: `$VAULT_PATH/Meta/bookmark-search.sqlite3`) |
| `BOOKMARK_CLASSIFICATION_GUIDE` | Override the classification guide path |
| `BOOKMARK_ENV_FILE` | Override the .env file path |
| `BOOKMARK_LLM_API_KEY`, `OPENAI_API_KEY`, or `OPENROUTER_API_KEY` | Optional API key for LLM classification, LLM summaries, and semantic search embeddings. Without one, bookmark creation falls back to heuristics and semantic search is unavailable. |
| `BOOKMARK_LLM_MODEL`, `OPENAI_MODEL`, or `MODEL_ID` | Model identifier for classification and LLM summary fallback (default: `gpt-4.1-mini`) |
| `BOOKMARK_LLM_BASE_URL` or `OPENAI_BASE_URL` | OpenAI-compatible API base URL |
| `LLM_PROVIDER` | Set to `openrouter` to default the base URL to OpenRouter when no explicit base URL is configured |
| `BOOKMARK_EMBEDDING_MODEL` | Override the embedding model label stored with embedding rows (default: `text-embedding-3-small`) |

## Usage

### Add a bookmark

```bash
# Single URL
uv run bookmark <URL> [--dry-run] [--interactive] [--archive]

# Overwrite an existing bookmark
uv run bookmark <URL> --force

# Batch import from file (parallel by default, 4 workers)
uv run bookmark --file urls.txt [--dry-run] [--workers <N>]

# Batch import from stdin
cat urls.txt | uv run bookmark --file -

# Retry only the URLs that failed in a previous batch
uv run bookmark --retry-failed failed-urls.txt
```

| Argument | Description |
|---|---|
| `<URL>` | Web page URL to fetch and classify (required) |
| `--file`, `-f` | Read URLs from a file (one per line); use `-` for stdin |
| `--force` | Overwrite if a bookmark for the URL already exists |
| `--dry-run` | Print the proposed note without writing it to disk |
| `--interactive`, `-i` | Review and confirm classification before writing |
| `--archive` | Save a cleaned copy of the page content alongside the note |
| `--disallow-new-subfolder` | Restrict placement to existing folders only |
| `--workers` | Number of parallel workers for batch mode (default: 4) |
| `--retry-failed` | Re-process only the URLs listed in a previous failures file |
| `--verbose`, `-v` | Enable verbose (debug) logging output |
| `--quiet`, `-q` | Suppress all logging output except errors |

After a batch run, any failed URLs are printed with their error reasons so you can save them to a file and retry with `--retry-failed`.

### Search bookmarks

```bash
# Keyword search (BM25)
uv run bookmark-search <QUERY> [--folder <FOLDER>] [--tag <TAG>] [--limit <N>]

# Semantic search (embeddings)
uv run bookmark-search <QUERY> --semantic [--threshold <FLOAT>] [--limit <N>]

# Hybrid search (BM25 + semantic via Reciprocal Rank Fusion)
uv run bookmark-search <QUERY> --hybrid [--threshold <FLOAT>] [--limit <N>]

# Export results as JSON or CSV for scripting
uv run bookmark-search <QUERY> --format json
uv run bookmark-search <QUERY> --format csv
```

| Argument | Description |
|---|---|
| `<QUERY>` | Search query text (required) |
| `--folder` | Restrict to a folder and its subfolders (e.g., `ML-AI`) |
| `--tag` | Restrict results to bookmarks with the given tag |
| `--limit` | Max results (default: 10) |
| `--rebuild` | Force a full FTS5 index rebuild |
| `--semantic` | Use embedding-based semantic search |
| `--hybrid` | Combine BM25 + semantic via Reciprocal Rank Fusion |
| `--threshold` | Min similarity for semantic/hybrid (default: 0.40) |
| `--format` | Output format: `text` (default), `json`, or `csv` |

### Rebuild derived state

```bash
# Rebuild FTS search and embeddings if an API key is configured
uv run bookmark-rebuild

# Rebuild only the FTS search index
uv run bookmark-rebuild --no-embeddings

# Scriptable output
uv run bookmark-rebuild --json
```

`bookmark-rebuild` reconstructs derived state from canonical Markdown bookmark notes. Deleting `BOOKMARK_SEARCH_INDEX` and running this command restores keyword search. Embeddings are rebuilt when an LLM/embedding API key is configured; otherwise they are skipped with a clear reason.

### Diagnose vault health

```bash
# Human-readable report with health score
uv run bookmark-doctor

# JSON report for scripts/CI
uv run bookmark-doctor --json

# Apply safe repairs such as rebuilding missing/stale search indexes
uv run bookmark-doctor --fix
```

`bookmark-doctor` checks configuration, provider availability, schema v1 frontmatter, non-bookmark Markdown under `Bookmarks/`, duplicate URL identities, missing/orphan archives, search DB health/staleness, embedding model/dimension mismatch, and broken Obsidian links. `--fix` only performs safe derived-state repairs; it does not delete notes or mutate user-authored Markdown.

### Check bookmark health

```bash
uv run bookmark-check [--timeout <N>] [--verbose] [--quiet]
```

| Argument | Description |
|---|---|
| `--timeout` | Timeout in seconds for each URL check (default: 15) |
| `--verbose`, `-v` | Enable verbose (debug) logging output |
| `--quiet`, `-q` | Suppress all logging output except errors |

### Update an existing bookmark

```bash
# Update a single bookmark
uv run bookmark-update <URL> [--dry-run] [--verbose] [--quiet]

# Bulk update all bookmarks
uv run bookmark-update --all [--dry-run]

# Bulk update a specific folder
uv run bookmark-update --folder ML-AI [--dry-run]
```

Re-fetches and re-classifies existing bookmarks while preserving file paths and original creation dates. Use `--all` or `--folder` to re-process bookmarks in bulk after changing your classification guide or LLM model.

### Delete a bookmark

```bash
uv run bookmark-delete <URL-or-PATH> [--dry-run] [--verbose] [--quiet]
```

Deletes a bookmark by URL or file path. Removes the note file, cleans up the search index and embedding store, and removes empty parent directories.

| Argument | Description |
|---|---|
| `<URL-or-PATH>` | URL or file path of the bookmark to delete (required) |
| `--dry-run` | Print what would be deleted without removing it |

### Vault statistics

```bash
uv run bookmark-stats [--verbose] [--quiet]
```

Shows vault statistics: total bookmarks, bookmarks per folder, type distribution, top tags, and top parent topics.

### Folder reorganization

```bash
uv run bookmark-reorg [--llm] [--verbose] [--quiet]
```

Proposes folder reclassifications for existing bookmarks based on the current classifier. Uses heuristics by default; pass `--llm` to use LLM-based classification.

## How it works

When you run `uv run bookmark <URL>`, the tool:

1. Fetches the web page and extracts title, description, and content
2. Checks for duplicate URLs in your vault
3. Classifies the page (folder, type, tags, parent topic) using an LLM with heuristic fallback
4. Generates a summary via the `summarize` CLI, classifier output, LLM, or heuristic fallback
5. Writes a structured markdown note with YAML frontmatter to your vault

Bookmark Markdown notes are the canonical system of record; search indexes, embeddings, and archive sidecars are derived/cache data. Use `bookmark-rebuild` to recreate derived search/embedding state and `bookmark-doctor` to detect drift. See `docs/SYSTEM_OF_RECORD.md`.

### Summary fallback chain

Each source is recorded in the `summary_model` frontmatter field for provenance:

1. External `summarize` CLI (if available) → `"summarize"`
2. Classifier-provided summary from LLM → `"classifier"`
3. Direct LLM summarization → `"llm"`
4. Heuristic fallback (description or first sentences) → `"heuristic"`

### Data preservation on update

When updating or force-overwriting an existing bookmark:

- The original `url` field is always preserved (updates via `final_url` or `canonical_url` do not change it)
- Human-authored sections like `## Notes` are preserved
- Unknown frontmatter fields (not owned by schema v1) are carried forward
- `last_success_at` refreshes on successful fetch; preserved on failure
- `content_hash` uses the full fetched content (not the truncated preview)

### Canonical URL resolution

`canonical_url` is resolved in order: `<link rel="canonical">` → `og:url` → `final_url`. The three URL fields (`url`, `final_url`, `canonical_url`) serve distinct purposes: identity, redirect tracking, and canonical reference.

## Web interface

A Flask-based web UI is included in the `web/` directory. It exposes the same functionality as the CLI through a browser interface.

### Pages

| Route | Description |
|---|---|
| `/` | Browse bookmarks by folder |
| `/search` | Keyword, semantic, or hybrid search |
| `/stats` | Vault statistics and charts |
| `/manage` | Create, update, check links, and reorganize bookmarks |

### Launch

`uv sync` installs the Flask dependency declared by the project. Run:

```bash
uv run python -m web
```

The server starts on `http://localhost:5000` in debug mode.

### REST API

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/folders` | List all folders |
| `GET` | `/api/bookmarks?folder=&page=&per_page=` | Paginated bookmark list |
| `GET` | `/api/bookmarks/<path>` | Bookmark detail |
| `POST` | `/api/bookmarks` | Create bookmark (`{"url": "..."}`) |
| `PUT` | `/api/bookmarks/update` | Re-fetch and re-classify (`{"url": "..."}`) |
| `POST` | `/api/check` | Stream link-check progress as SSE |
| `GET` | `/api/reorg?llm=false` | Propose folder reclassifications |
| `GET` | `/api/search?q=&mode=keyword\|semantic\|hybrid&folder=&limit=` | Search bookmarks |
| `POST` | `/api/search/reindex` | Rebuild the search index |
| `GET` | `/api/stats` | Vault statistics |

## Development

```bash
uv run pytest tests/             # Run all tests (312 tests)
uv run pytest tests/test_web_stats.py tests/test_web_bookmarks.py  # Web tests only
uv run ruff check bookmark_tools tests   # Lint
uv run ruff format bookmark_tools tests  # Format
```

## Project structure

- `AGENTS.md` — Detailed code structure and module documentation for coding agents
- `docs/SYSTEM_OF_RECORD.md` — Defines canonical vs derived data categories
- `docs/PHASE0_CHANGES.md` — Phase 0 implementation details
- `docs/PHASE1B_CHANGES.md` — Phase 1B schema hardening details
- `docs/PHASE2_CHANGES.md` — Phase 2 doctor/rebuild implementation details
- `bookmark_tools/` — Main package source code
- `bookmark_tools/doctor.py` — Vault health checks, JSON reports, and safe derived-state fixes
- `bookmark_tools/rebuild.py` — Rebuild derived search/embedding state from Markdown
- `bookmark_tools/note_schema.py` — Schema v1 parser, renderer, validation, and identity helpers
- `bookmark_tools/note_filter.py` — Bookmark vs sidecar/non-bookmark filtering for vault scans
- `bookmark_tools/url_normalize.py` — URL identity and canonicalization
- `tests/` — Unit and integration tests (312 tests across 22 files)
