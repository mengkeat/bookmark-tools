# Web Frontend for Bookmark Tools

## Context

The bookmark-tools project is a CLI-based bookmark management system that stores bookmarks as markdown files with YAML frontmatter in an Obsidian vault. It has rich features (search, stats, classification, link checking) but no visual interface. Adding a web frontend will make it easier to browse, search, and eventually edit bookmarks, plus visualize vault statistics.

**Key constraint**: All web code lives in `web/`, completely isolated. `bookmark_tools` gains no web dependencies and continues to work independently.

## Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Backend | **Flask** | Existing code is synchronous Python; Flask maps 1:1 with no ceremony. Single pip install. |
| Frontend interactivity | **htmx** | Server-rendered HTML fragments. No build step, no node_modules. One CDN script tag. |
| Styling | **Pico CSS** | Classless CSS — semantic HTML looks good immediately. One CDN link tag. |
| Charts | **Chart.js** | CDN script, ~10-20 lines of JS per chart. Only needed for stats page. |

No SPA framework, no bundler, no TypeScript, no npm.

## Directory Structure

```
web/
  __init__.py
  __main__.py              # Entry: python -m web
  app.py                   # Flask app factory, blueprint registration
  routes/
    __init__.py
    browse.py              # Folder listing + bookmark browsing
    search.py              # Search with mode toggle
    stats.py               # Stats + charts
    bookmarks.py           # Create/update/edit (Phase 3)
  templates/
    base.html              # Layout: nav, Pico CSS, htmx
    index.html             # Browse page (folder tree + bookmark list)
    search.html            # Search page
    stats.html             # Stats + visualization page
    partials/
      folder_tree.html     # htmx fragment: folder sidebar
      bookmark_list.html   # htmx fragment: bookmark cards for a folder
      bookmark_detail.html # htmx fragment: single bookmark expanded view
      search_results.html  # htmx fragment: search result list
      stats_cards.html     # htmx fragment: stats summary
  static/
    style.css              # Minimal overrides on Pico
  requirements.txt         # flask
```

## How to Run

```bash
pip install flask
python -m web          # starts dev server on localhost:5000
```

`web/__main__.py` calls `create_app()` from `web/app.py` and runs `app.run(debug=True, port=5000)`. Since the repo root is on `sys.path`, `from bookmark_tools.search import search_bookmarks` works in route handlers. The app calls `load_env()` once at startup.

## Implementation Phases

### Phase 1: Browse & Search (starter MVP)

**Step 1 — Scaffold** ✅
- Create `web/__init__.py`, `web/__main__.py`, `web/app.py`
- `create_app()`: calls `load_env()`, registers blueprints, returns Flask app
- Create `web/requirements.txt` with `flask`

**Step 2 — Base template** ✅
- `templates/base.html`: Pico CSS CDN, htmx CDN, nav bar (Browse / Search / Stats)

**Step 3 — Browse routes** (`web/routes/browse.py`) ✅

| Method | Endpoint | Description | Wraps |
|--------|----------|-------------|-------|
| GET | `/` | Full browse page with folder tree + bookmark list | `collect_existing_notes()` |
| GET | `/api/folders` | JSON list of folders | `collect_existing_notes().folders` |
| GET | `/api/bookmarks` | JSON bookmarks, `?folder=X&page=1&per_page=20` | `collect_existing_notes().notes` filtered |
| GET | `/api/bookmarks/<path:note_path>` | JSON single bookmark detail | `parse_frontmatter()` |
| GET | `/partials/folders` | htmx fragment: folder tree | |
| GET | `/partials/bookmarks` | htmx fragment: bookmark cards, `?folder=X` | |

- Clicking a folder in the sidebar loads bookmarks via htmx
- Bookmark cards show title, folder, tags, description
- Clicking a card expands to show full detail (URL link, related, etc.)

**Path security**: Validate that any resolved note path is under `get_bookmarks_dir()` using `Path.resolve().is_relative_to()`.

**Step 4 — Search routes** (`web/routes/search.py`) ✅

| Method | Endpoint | Description | Wraps |
|--------|----------|-------------|-------|
| GET | `/search` | Full search page | |
| GET | `/api/search` | JSON results, `?q=X&mode=keyword|semantic|hybrid&folder=X&limit=10` | `search_bookmarks[_semantic|_hybrid]()` |
| GET | `/partials/search` | htmx fragment: search results | |
| POST | `/api/search/reindex` | Trigger index refresh | `refresh_search_index()` |

- Search form with text input, mode radio buttons (keyword/semantic/hybrid), optional folder filter
- Results load via htmx as user types (debounced) or on submit
- Each result shows title, folder, score, description, snippet, link to URL

**Serialization helper** in `web/app.py`:
```python
def serialize_search_result(r):
    return {"path": str(r.path), "url": r.url, "title": r.title,
            "folder": r.folder, "description": r.description,
            "score": r.score, "snippet": r.snippet}
```

### Phase 2: Stats & Visualization ✅

**Step 5 — Stats routes** (`web/routes/stats.py`) ✅

| Method | Endpoint | Description | Wraps |
|--------|----------|-------------|-------|
| GET | `/stats` | Full stats page with charts | |
| GET | `/api/stats` | JSON stats | `collect_stats()` |
| GET | `/partials/stats` | htmx fragment: stats cards | |

- Summary cards: total bookmarks, total folders, top type
- Bar chart: bookmarks per folder (`bookmarks_per_folder` from `collect_stats()`)
- Pie/doughnut chart: type distribution (`type_distribution`)
- Horizontal bar: top 20 tags (`top_tags`)
- Chart.js renders from `/api/stats` JSON — ~15 lines of JS per chart

### Phase 3: Create, Edit & Manage (future)

**Step 6 — Bookmark CRUD** (`web/routes/bookmarks.py`)

| Method | Endpoint | Description | Wraps |
|--------|----------|-------------|-------|
| POST | `/api/bookmarks` | Create bookmark from URL | `build_note()` |
| PUT | `/api/bookmarks/update` | Re-fetch/re-classify | `update_bookmark()` |
| POST | `/api/check` | Check for broken links (SSE stream) | `check_bookmarks()` |
| GET | `/api/reorg` | Get reclassification proposals | `propose_reclassifications()` |

- Create form: paste URL, submit, see result
- Link checker uses SSE (`text/event-stream`) for progress — htmx supports this via `hx-ext="sse"`
- Edit frontmatter fields inline (tags, folder, description) — write back to markdown file

## Key Files to Consume from bookmark_tools

| File | Functions used |
|------|---------------|
| `bookmark_tools/search.py` | `search_bookmarks`, `search_bookmarks_semantic`, `search_bookmarks_hybrid`, `refresh_search_index` |
| `bookmark_tools/search_index.py` | `SearchResult` dataclass (for serialization) |
| `bookmark_tools/vault_profile.py` | `collect_existing_notes`, `parse_frontmatter`, `BookmarkProfile`, `NoteProfile` |
| `bookmark_tools/stats.py` | `collect_stats` |
| `bookmark_tools/paths.py` | `load_env`, `get_bookmarks_dir` |
| `bookmark_tools/cli.py` | `build_note` (Phase 3) |
| `bookmark_tools/update.py` | `update_bookmark` (Phase 3) |
| `bookmark_tools/check.py` | `check_bookmarks` (Phase 3) |

## Verification

After each phase:
1. `python -m web` starts without errors
2. Browse `/` — folder tree loads, clicking folder shows bookmarks
3. Browse `/search` — searching returns results for all three modes
4. Browse `/stats` — charts render with real vault data
5. JSON endpoints return valid JSON (`curl localhost:5000/api/stats | python -m json.tool`)
6. Run `ruff check web/` — no lint errors
