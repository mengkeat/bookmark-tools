# Bookmark Tools

CLI tools for fetching, classifying, summarizing, and searching bookmarks in an Obsidian vault.

## Features

- **Bookmark creation**: Fetch a web page, classify it with LLM (or heuristic fallback), generate a summary, and write a structured markdown note to your vault.
- **Batch import**: Import multiple URLs from a file or stdin with `--file`/`-f`.
- **Search**: BM25 keyword search, semantic vector search, or hybrid search over your bookmark notes.
- **Link health checking**: Validate all bookmarked URLs with `bookmark-check` to find dead links.
- **Zero runtime dependencies** beyond Python stdlib (numpy is optional for faster cosine similarity).

## Installation

```bash
git clone <repo-url>
cd bookmark-tools
uv sync
```

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

### Required environment variables

| Variable | Description |
|---|---|
| `VAULT_PATH` | Path to your Obsidian vault root (containing `Bookmarks/` and `Meta/`) |
| `OPENROUTER_API_KEY` (or `OPENAI_API_KEY`) | API key for LLM classification and embeddings |
| `LLM_PROVIDER` | `openrouter` or `litellm` (default: `openrouter`) |
| `MODEL_ID` | Model identifier for classification (default: `gpt-4.1-mini`) |

### Optional overrides

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
uv run bookmark <URL> [--dry-run] [--disallow-new-subfolder]

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

## Development

```bash
uv run pytest                    # Run tests
uv run ruff check src tests      # Lint
uv run ruff format src tests     # Format
```

## Project structure

- `AGENTS.md` — Detailed code structure and module documentation for coding agents
- `docs/plan.md` — Feature and improvement roadmap
- `src/bookmark_tools/` — Main package source code
- `tests/` — Unit tests
