# Bookmark Tools

CLI tools for fetching, classifying, summarizing, and searching bookmarks in an Obsidian vault.

## Features

- **Bookmark creation**: Fetch a web page, classify it with LLM (or heuristic fallback), generate a summary, and write a structured markdown note to your vault.
- **Batch import**: Import multiple URLs from a file or stdin with `--file`/`-f`.
- **Interactive mode**: Review and confirm classification before writing with `--interactive`/`-i`.
- **Content archiving**: Save a cleaned copy of page content alongside the bookmark with `--archive`.
- **Bookmark update**: Re-fetch and re-classify existing bookmarks with `bookmark-update`, preserving creation date.
- **Search**: BM25 keyword search, semantic vector search, or hybrid search with context snippets.
- **Link health checking**: Validate all bookmarked URLs with `bookmark-check` to find dead links.
- **Vault statistics**: View bookmark counts, tag distribution, and folder stats with `bookmark-stats`.
- **Folder reorganization**: Propose folder reclassifications with `bookmark-reorg`.
- **Tag normalization**: Consistent lowercase kebab-case tags with abbreviation alias resolution.
- **Bidirectional linking**: Update related fields of similar existing bookmarks when creating new ones.
- **Unified config file**: Consolidate settings in a `bookmark-tools.toml` config file.
- **Zero runtime dependencies** beyond Python stdlib (numpy is optional for faster cosine similarity).

## Installation

```bash
git clone <repo-url>
cd bookmark-tools
uv sync
```

## Configuration

Settings can be configured via environment variables (`.env` file) or a unified TOML config file.

### Config file (recommended)

Create a `bookmark-tools.toml` in your vault or working directory:

```toml
[llm]
api_key = "your-api-key"
model = "gpt-4.1-mini"
base_url = "https://api.openai.com/v1"
provider = ""  # or "openrouter"

[timeouts]
fetch = 20
llm_classify = 20
llm_summarize = 180
link_check = 15

[search]
similarity_threshold = 0.40
default_limit = 10
```

The file is auto-discovered in `$VAULT_PATH` or the current directory. Override with `BOOKMARK_CONFIG` env var.

### Environment variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

#### Required environment variables

| Variable | Description |
|---|---|
| `VAULT_PATH` | Path to your Obsidian vault root (containing `Bookmarks/` and `Meta/`) |
| `OPENROUTER_API_KEY` (or `OPENAI_API_KEY`) | API key for LLM classification and embeddings |
| `LLM_PROVIDER` | `openrouter` or `litellm` (default: `openrouter`) |
| `MODEL_ID` | Model identifier for classification (default: `gpt-4.1-mini`) |

#### Optional overrides

| Variable | Description |
|---|---|
| `BOOKMARKS_DIR` | Override the bookmarks directory (default: `$VAULT_PATH/Bookmarks`) |
| `BOOKMARK_SEARCH_INDEX` | Override the search database path (default: `$VAULT_PATH/Meta/bookmark-search.sqlite3`) |
| `BOOKMARK_CLASSIFICATION_GUIDE` | Override the classification guide path |
| `BOOKMARK_ENV_FILE` | Override the .env file path |

## Usage

### Add a bookmark

```bash
# Single URL
uv run bookmark <URL> [--dry-run] [--interactive] [--archive]

# Batch import from file
uv run bookmark --file urls.txt [--dry-run]

# Batch import from stdin
cat urls.txt | uv run bookmark --file -
```

| Argument | Description |
|---|---|
| `<URL>` | Web page URL to fetch and classify (required) |
| `--file`, `-f` | Read URLs from a file (one per line); use `-` for stdin |
| `--dry-run` | Print the proposed note without writing it to disk |
| `--interactive`, `-i` | Review and confirm classification before writing |
| `--archive` | Save a cleaned copy of the page content alongside the note |
| `--disallow-new-subfolder` | Restrict placement to existing folders only |
| `--verbose`, `-v` | Enable verbose (debug) logging output |
| `--quiet`, `-q` | Suppress all logging output except errors |

### Search bookmarks

```bash
# Keyword search (BM25)
uv run bookmark-search <QUERY> [--folder <FOLDER>] [--limit <N>] [--rebuild]

# Semantic search (embeddings)
uv run bookmark-search <QUERY> --semantic [--threshold <FLOAT>] [--limit <N>]

# Hybrid search (BM25 + semantic via Reciprocal Rank Fusion)
uv run bookmark-search <QUERY> --hybrid [--threshold <FLOAT>] [--limit <N>]
```

| Argument | Description |
|---|---|
| `<QUERY>` | Search query text (required) |
| `--folder` | Restrict to a folder and its subfolders (e.g., `ML-AI`) |
| `--limit` | Max results (default: 10) |
| `--rebuild` | Force a full FTS5 index rebuild |
| `--semantic` | Use embedding-based semantic search |
| `--hybrid` | Combine BM25 + semantic via Reciprocal Rank Fusion |
| `--threshold` | Min similarity for semantic/hybrid (default: 0.40) |

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
uv run bookmark-update <URL> [--dry-run] [--verbose] [--quiet]
```

Re-fetches and re-classifies an existing bookmark while preserving its file path and original creation date.

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

### Summary fallback chain

1. External `summarize` CLI (if available)
2. Classifier-provided summary from LLM
3. Direct LLM summarization
4. Heuristic fallback (description or first sentences)

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

Install the extra dependency and run the server:

```bash
uv pip install flask
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
uv run pytest tests/             # Run all tests (CLI + web)
uv run pytest tests/test_web_stats.py tests/test_web_bookmarks.py  # Web tests only
uv run ruff check bookmark_tools tests   # Lint
uv run ruff format bookmark_tools tests  # Format
```

## Project structure

- `AGENTS.md` — Detailed code structure and module documentation for coding agents
- `docs/plan.md` — Feature and improvement roadmap
- `bookmark_tools/` — Main package source code
- `tests/` — Unit tests
