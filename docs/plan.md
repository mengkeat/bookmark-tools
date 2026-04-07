# Feature & Improvement Plan — Phase 2 (Revised)

Reorganized by dependency and impact. Bug fixes first, then completing existing features, then new capabilities, then polish.

---

## Phase 2A: Bug Fixes and Correctness ✅ DONE

All independent — can be done in any order or in parallel.

#### 2A.1 Fix duplicate logger/TYPE_CHECKING in `search.py` ✅
- **What**: Remove duplicate `if TYPE_CHECKING` block and `logger` at lines 17-25.
- **Files**: `search.py`
- **Effort**: Trivial
- **Resolved**: commit `abfdb76`

#### 2A.2 Fix fragile created-date preservation in `update.py` ✅
- **What**: `update_bookmark()` uses brittle string splitting (`split('created: ')`) to preserve the original created date after rendering. Add a `created_override` param to `render_note()` so the date is rendered correctly from the start. Remove the string-replacement hack.
- **Files**: `render.py`, `update.py`, `tests/test_render.py` (new)
- **Effort**: Low | **Impact**: High (data integrity)
- **Resolved**: commit `e7aff91`

#### 2A.3 HEAD→GET fallback in `check.py` ✅
- **What**: When a HEAD request returns 405, retry with GET (read minimal bytes) before marking the URL as broken. Eliminates false broken-link reports.
- **Files**: `check.py`, `tests/test_check.py`
- **Effort**: Low | **Impact**: High
- **Resolved**: commit `933c4ef`

#### 2A.4 Remove dead `config.py` ✅
- **What**: `AppConfig`/`load_config()` is never imported by any module — all use `os.environ.get()` directly. Remove the dead module and its test. TOML config system deferred to 2D.1 when it can be wired in properly.
- **Files**: `config.py` (deleted), `tests/test_config.py` (deleted)
- **Effort**: Trivial
- **Resolved**: commit `4061c26`

#### 2A.5 Eliminate double vault scan in `update.py` ✅
- **What**: `find_note_by_url()` does a full rglob scan, then `update_bookmark()` calls `collect_existing_notes()` for another full scan. Use `profile.url_index` for the lookup instead.
- **Files**: `update.py`, `tests/test_update.py`
- **Effort**: Low
- **Resolved**: commit `d9bd8cd`

---

## Phase 2B: Complete Existing Features ✅ DONE

Make half-built features actually useful. Depends on 2A being done.

#### 2B.1 Dry-run for destructive commands ✅
- **What**: Add `--dry-run` to `bookmark-reorg` (prerequisite for --apply) and prepare `check.py` for future `--delete` flag. Note: `bookmark-update` already has `--dry-run`.
- **Files**: `reorg.py`, `check.py`
- **Effort**: Low | **Impact**: High (safety net)
- **Resolved**: commit `2cc55b1`

#### 2B.2 `bookmark-reorg --apply` ✅
- **What**: Execute proposed folder moves via `shutil.move()`, update search index. Without this, reorg only prints suggestions users must act on manually.
- **Depends on**: 2B.1 (dry-run must exist alongside)
- **Files**: `reorg.py`, `tests/test_reorg.py`
- **Effort**: Medium | **Impact**: High
- **Resolved**: commit `093a954`

#### 2B.3 `bookmark-check` actionable output ✅
- **What**: Add `--delete` (remove broken bookmark files), `--tag-broken` (add tag to frontmatter), and `--format json` for scriptable output.
- **Depends on**: 2A.3 (GET fallback reduces false positives), 2B.1 (dry-run for safety)
- **Files**: `check.py`, `tests/test_check.py`
- **Effort**: Low | **Impact**: High
- **Resolved**: commit `733bf10`

#### 2B.4 `validate_folder()` branch-level tests ✅
- **What**: Cover every branch: invalid paths, existing folders, new subfolders with/without support, nested rejection.
- **Files**: `tests/test_bookmarks.py`
- **Effort**: Low | **Impact**: Medium (highest priority test gap)
- **Resolved**: commit `30f7709`

#### 2B.5 Network behavior tests ✅
- **What**: Mock HTTP 404, 500, timeouts, SSL errors, 405+GET fallback, rate-limit responses. Covers `check.py`, `fetch.py`, `http_retry.py`.
- **Depends on**: 2A.3 (tests should cover new GET fallback)
- **Files**: `tests/test_check.py`, `tests/test_fetch.py`, `tests/test_http_retry.py`
- **Effort**: Medium | **Impact**: Medium
- **Resolved**: commit `e3637b8`

---

## Phase 2C: New Capabilities (Do Third)

### Commands

#### 2C.1 Delete bookmark command (`bookmark-delete`) ✅
- **What**: Delete by URL or file path. Remove note file, clean up search index and embedding store. Basic CRUD is incomplete without this.
- **Files**: New `delete.py`, `pyproject.toml`
- **Effort**: Low | **Impact**: High
- **Resolved**: implemented `bookmark-delete` CLI with search index + embedding cleanup and empty dir removal

#### 2C.2 Bulk update command
- **What**: Extend `bookmark-update` with `--all` or `--folder <FOLDER>` to re-process bookmarks after changing the classification guide or LLM model.
- **Depends on**: 2A.5 (no double scan)
- **Files**: `update.py`
- **Effort**: Medium | **Impact**: Medium

#### 2C.3 Idempotent `bookmark --force`
- **What**: When a bookmark already exists, `--force` overwrites instead of erroring. Removes need to know about `bookmark-update` separately.
- **Files**: `cli.py`
- **Effort**: Low | **Impact**: Medium

### Batch Processing

#### 2C.4 Parallel batch processing
- **What**: Use `concurrent.futures.ThreadPoolExecutor` for `--file` batch mode. Add `--workers` flag (default 4). Call `collect_existing_notes()` once before pool starts.
- **Files**: `cli.py`
- **Effort**: Medium | **Impact**: High

#### 2C.5 Batch error recovery/reporting *(new)*
- **What**: After batch completion, output failed URLs with error reasons. Support `--retry-failed <file>` to re-process only failures.
- **Files**: `cli.py`
- **Effort**: Low | **Impact**: Medium

### Search Enhancements

#### 2C.6 Export search results (JSON, CSV)
- **What**: Add `--format json` and `--format csv` to `bookmark-search` for scripting.
- **Files**: `search.py`
- **Effort**: Low | **Impact**: Medium

#### 2C.7 Tag-based search filter
- **What**: Add `--tag` flag to restrict results, complementing existing `--folder`.
- **Files**: `search.py`, `search_index.py`
- **Effort**: Low | **Impact**: Medium

---

## Phase 2D: Polish and Quality of Life (When Convenient)

#### 2D.1 Wire TOML config system
- **What**: Reintroduce `config.py`, wire into classify/summarize/embeddings/paths/search_index/check. Env var overrides for backward compat. Do as a single focused PR.
- **Effort**: Medium

#### 2D.2 URL normalization consistency *(new)*
- **What**: Extract shared `normalize_url()` — strip trailing slash, remove `www.`, normalize scheme. Use in `vault_profile.py` url_index, `classify.py` `find_existing_url`, `update.py`. Prerequisite for future merge-duplicates.
- **Effort**: Low

#### 2D.3 Date-range search filter (`--after`, `--before`)
- **What**: Filter search results by `created` date. Add `created` as an indexed column.
- **Files**: `search.py`, `search_index.py`
- **Effort**: Medium

#### 2D.4 Browser bookmark HTML import
- **What**: Parse Netscape bookmark HTML format (Chrome/Firefox/Safari export).
- **Files**: New `import_html.py`, `cli.py`
- **Effort**: Medium

#### 2D.5 Progress indicators for long operations
- **What**: Add progress bars/spinners for batch import, check, reorg --llm, embedding refresh. Simple stderr output, no external dependency.
- **Effort**: Low

#### 2D.6 Property-based testing with hypothesis
- **What**: Fuzz frontmatter parsing, URL normalization, `slugify_filename()`, `clean_html()`.
- **Files**: `tests/`, `pyproject.toml` (add hypothesis dev dep)
- **Effort**: Medium

#### 2D.7 Lazy vault profile caching
- **What**: Cache `BookmarkProfile` by directory mtime. Defer until profiling shows it's needed — 2A.5 and 2C.4 address the main perf issues.
- **Effort**: Medium

---

## Backlog (Unscheduled)

| Item | Why deferred |
|------|-------------|
| Open in browser (`--open`) | Trivial; users can pipe to `xdg-open` |
| OPML import/export | Niche; HTML import covers primary use case |
| Structured JSON logging | Only useful for production monitoring |
| Shell completions | Nice-to-have, add anytime with argcomplete |
| Export vault to browser HTML | Lower demand than import |
| Merge duplicate bookmarks | Needs URL normalization (2D.2) first |

---

## Priority Summary

| ID | Item | Impact | Effort | Depends On |
|----|------|--------|--------|------------|
| ~~**2A.1**~~ | ~~Fix duplicate logger in search.py~~ | Low | Trivial | — | ✅ |
| ~~**2A.2**~~ | ~~Fix created-date preservation~~ | High | Low | — | ✅ |
| ~~**2A.3**~~ | ~~HEAD→GET fallback in check.py~~ | High | Low | — | ✅ |
| ~~**2A.4**~~ | ~~Remove dead config.py~~ | Low | Trivial | — | ✅ |
| ~~**2A.5**~~ | ~~Eliminate double vault scan~~ | Medium | Low | — | ✅ |
| ~~**2B.1**~~ | ~~Dry-run for destructive commands~~ | High | Low | — | ✅ |
| ~~**2B.2**~~ | ~~bookmark-reorg --apply~~ | High | Medium | 2B.1 | ✅ |
| ~~**2B.3**~~ | ~~bookmark-check actionable output~~ | High | Low | 2A.3, 2B.1 | ✅ |
| ~~**2B.4**~~ | ~~validate_folder() branch tests~~ | Medium | Low | — | ✅ |
| ~~**2B.5**~~ | ~~Network behavior tests~~ | Medium | Medium | 2A.3 | ✅ |
| **2C.1** | Delete bookmark command | High | Low | — |
| **2C.2** | Bulk update command | Medium | Medium | 2A.5 |
| **2C.3** | Idempotent bookmark --force | Medium | Low | — |
| **2C.4** | Parallel batch processing | High | Medium | — |
| **2C.5** | Batch error recovery/reporting | Medium | Low | — |
| **2C.6** | Export search results (JSON/CSV) | Medium | Low | — |
| **2C.7** | Tag-based search filter | Medium | Low | — |
| **2D.1** | Wire TOML config system | Medium | Medium | 2A.4 |
| **2D.2** | URL normalization consistency | Medium | Low | — |
| **2D.3** | Date-range search filter | Medium | Medium | — |
| **2D.4** | Browser HTML import | Medium | Medium | — |
| **2D.5** | Progress indicators | Low | Low | — |
| **2D.6** | Property-based testing | Medium | Medium | — |
| **2D.7** | Lazy vault profile caching | Low | Medium | 2A.5 |
