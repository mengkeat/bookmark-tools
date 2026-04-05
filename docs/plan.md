# Feature & Improvement Plan — Phase 2

---

### 1. Code Quality & Bug Fixes (P0)

#### 1.1 Fix duplicate logger and TYPE_CHECKING block in `search.py`
- **What**: Remove the duplicate `logger = logging.getLogger(__name__)` and `if TYPE_CHECKING` block.
- **Scope**: `search.py`
- **Effort**: Trivial

#### 1.2 Wire `config.py` into the application or remove it
- **What**: The `AppConfig`/`load_config()` module exists but nothing uses it. Either integrate it so modules read from `AppConfig` instead of raw env vars (eliminating the parallel config path), or remove the dead code.
- **Scope**: `config.py`, `classify.py`, `summarize.py`, `embeddings.py`, `paths.py`, `search_index.py`
- **Effort**: Medium

#### 1.3 Fix fragile created-date preservation in `update.py`
- **What**: Instead of string-replacing `created:` in rendered text, pass the original `created` date into `render_note()` (or `normalize_metadata()`) so it's rendered correctly from the start.
- **Scope**: `update.py`, `render.py`, `types.py`
- **Effort**: Low

#### 1.4 Fall back to GET on 405 in `check.py`
- **What**: When a HEAD request returns 405 Method Not Allowed, retry with a GET request (reading minimal bytes) before marking the URL as broken.
- **Scope**: `check.py`
- **Effort**: Low

#### 1.5 Add `validate_folder()` branch-level tests
- **What**: This was called out as high-priority remaining tech debt. Add targeted tests covering every branch (invalid paths, existing folders, new subfolders with/without support, nested rejection, etc.).
- **Scope**: `tests/test_bookmarks.py`
- **Effort**: Low

---

### 2. Performance (P1)

#### 2.1 Parallel batch processing with `concurrent.futures`
- **What**: Batch import (`--file`) currently processes URLs sequentially. Use a thread pool to parallelize fetching and classification across URLs.
- **Scope**: `cli.py`
- **Effort**: Medium

#### 2.2 Lazy vault profile caching
- **What**: `collect_existing_notes()` re-scans the entire vault directory tree on every invocation. Cache the profile in memory keyed by directory mtime, or persist a lightweight index, to speed up repeated runs (especially batch mode and search).
- **Scope**: `vault_profile.py`
- **Effort**: Medium

#### 2.3 Avoid double vault scan in `bookmark-update`
- **What**: `find_note_by_url()` in `update.py` does a full vault scan via `rglob("*.md")` + `read_frontmatter()`, then `update_bookmark()` calls `collect_existing_notes()` for another full scan. Use the profile's `url_index` for the lookup instead.
- **Scope**: `update.py`
- **Effort**: Low

---

### 3. Search & Discovery (P1)

#### 3.1 Export search results (JSON, CSV)
- **What**: Add `--format json` and `--format csv` output options to `bookmark-search` for scripting and integration with other tools.
- **Scope**: `search.py`
- **Effort**: Low

#### 3.2 "Open in browser" search action
- **What**: Add an `--open` flag that opens the top search result's URL in the default browser (`webbrowser.open()`).
- **Scope**: `search.py`
- **Effort**: Trivial

#### 3.3 Date-range search filter
- **What**: Add `--after` and `--before` flags to filter search results by `created` date, useful for finding recent or old bookmarks.
- **Scope**: `search.py`, `search_index.py` (add `created` as an indexed column)
- **Effort**: Medium

#### 3.4 Tag-based search filter
- **What**: Add a `--tag` flag to restrict results to bookmarks with a specific tag, complementing the existing `--folder` filter.
- **Scope**: `search.py`, `search_index.py`
- **Effort**: Low

---

### 4. Bookmark Management (P2)

#### 4.1 Delete bookmark command (`bookmark-delete`)
- **What**: Add a command to delete a bookmark by URL or file path, removing the note file and cleaning up the search index and embedding store.
- **Scope**: New module `delete.py`, `pyproject.toml`
- **Effort**: Low

#### 4.2 Bulk update command
- **What**: Extend `bookmark-update` with `--all` or `--folder <FOLDER>` to re-process all (or a subset of) bookmarks, useful after changing the classification guide or LLM model.
- **Scope**: `update.py`
- **Effort**: Medium

#### 4.3 Merge duplicate bookmarks
- **What**: Detect bookmarks pointing to the same URL (after normalization, e.g., trailing slash, www prefix, query params) and offer to merge them.
- **Scope**: `vault_profile.py`, new module or subcommand
- **Effort**: Medium

#### 4.4 `bookmark-check` actionable output
- **What**: Add `--delete` flag to auto-delete or `--tag-broken` to tag broken bookmarks instead of just reporting them. Add `--format json` for scriptable output.
- **Scope**: `check.py`
- **Effort**: Low

---

### 5. Import & Export (P2)

#### 5.1 Browser bookmark import (HTML format)
- **What**: Parse Netscape bookmark HTML format (exported from Chrome, Firefox, Safari) and import all URLs. This is the standard browser export format.
- **Scope**: New module `import_html.py`, `cli.py`
- **Effort**: Medium

#### 5.2 Export vault to browser bookmark HTML
- **What**: Export all bookmarks as a Netscape bookmark HTML file that can be imported into any browser, preserving folder structure.
- **Scope**: New module `export.py`, `pyproject.toml`
- **Effort**: Medium

#### 5.3 OPML import/export
- **What**: Support OPML format for interoperability with RSS readers and other bookmark tools.
- **Scope**: New module
- **Effort**: Low

---

### 6. Reliability & Observability (P2)

#### 6.1 Structured JSON logging
- **What**: Add `--log-format json` option for machine-readable log output, useful for monitoring batch jobs or piping into log aggregation.
- **Scope**: `cli.py`
- **Effort**: Low

#### 6.2 Dry-run for destructive commands
- **What**: Add `--dry-run` to `bookmark-reorg`, `bookmark-check --delete`, and `bookmark-update --all` so users can preview changes before applying them.
- **Scope**: `reorg.py`, `check.py`, `update.py`
- **Effort**: Low

#### 6.3 Network behavior tests
- **What**: Still missing per AGENTS.md tech debt. Test handling of HTTP 404, 500, timeouts, SSL errors, and rate-limit responses with mocked network to verify fallback behavior.
- **Scope**: `tests/`
- **Effort**: Medium

#### 6.4 Property-based testing for parsers
- **What**: Use hypothesis to fuzz frontmatter parsing, URL normalization, `slugify_filename()`, `clean_html()`, and `_MetadataParser` with random inputs to catch edge cases.
- **Scope**: `tests/`, `pyproject.toml` (add hypothesis dev dep)
- **Effort**: Medium

---

### 7. Developer Experience (P3)

#### 7.1 Shell completions
- **What**: Generate bash/zsh/fish completions for all CLI commands, either via argcomplete or static generation.
- **Scope**: All CLI modules
- **Effort**: Low

#### 7.2 `bookmark-reorg --apply` flag
- **What**: Currently `bookmark-reorg` only proposes moves. Add `--apply` to actually move files and update any internal references (related fields, search index).
- **Scope**: `reorg.py`
- **Effort**: Medium

#### 7.3 Idempotent `bookmark` command
- **What**: When a bookmark already exists, offer `--force` to overwrite/update it instead of just erroring out. Currently duplicates exit with an error, and `bookmark-update` is a separate command.
- **Scope**: `cli.py`
- **Effort**: Low

#### 7.4 Progress indicators for long operations
- **What**: Add progress bars or spinners for batch import, `bookmark-check`, `bookmark-reorg --llm`, and embedding refresh using simple stderr output (no external dependency).
- **Scope**: `cli.py`, `check.py`, `reorg.py`, `search.py`
- **Effort**: Low

---

## Priority Order

| Priority | Item | Impact | Effort |
|----------|------|--------|--------|
| P0 | 1.1 Fix duplicate logger in search.py | Low | Trivial |
| P0 | 1.2 Wire or remove config.py | Medium | Medium |
| P0 | 1.3 Fix created-date in update.py | Medium | Low |
| P0 | 1.4 HEAD→GET fallback in check.py | Low | Low |
| P0 | 1.5 validate_folder() branch tests | High | Low |
| P1 | 2.1 Parallel batch processing | High | Medium |
| P1 | 2.2 Lazy vault profile caching | Medium | Medium |
| P1 | 2.3 Avoid double scan in update.py | Low | Low |
| P1 | 3.1 Export search results (JSON/CSV) | Medium | Low |
| P1 | 3.2 Open in browser | Low | Trivial |
| P1 | 3.3 Date-range search filter | Medium | Medium |
| P1 | 3.4 Tag-based search filter | Medium | Low |
| P2 | 4.1 Delete bookmark command | Medium | Low |
| P2 | 4.2 Bulk update command | Medium | Medium |
| P2 | 4.3 Merge duplicate bookmarks | Low | Medium |
| P2 | 4.4 Actionable bookmark-check output | Medium | Low |
| P2 | 5.1 Browser bookmark HTML import | High | Medium |
| P2 | 5.2 Export to browser HTML | Medium | Medium |
| P2 | 5.3 OPML import/export | Low | Low |
| P2 | 6.1 Structured JSON logging | Low | Low |
| P2 | 6.2 Dry-run for destructive commands | Medium | Low |
| P2 | 6.3 Network behavior tests | Medium | Medium |
| P2 | 6.4 Property-based testing | Medium | Medium |
| P3 | 7.1 Shell completions | Low | Low |
| P3 | 7.2 bookmark-reorg --apply | Medium | Medium |
| P3 | 7.3 Idempotent bookmark --force | Low | Low |
| P3 | 7.4 Progress indicators | Low | Low |
