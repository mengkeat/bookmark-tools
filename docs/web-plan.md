# Web Frontend for Bookmark Tools

## Context

The bookmark-tools project is a CLI-based bookmark management system that stores bookmarks as markdown files with YAML frontmatter in an Obsidian vault. The web frontend makes it easier to browse, search, edit bookmarks, and visualize vault statistics.

**Key constraint**: All web code lives in `web/`, completely isolated. `bookmark_tools` gains no web dependencies and continues to work independently.

## Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Backend | **Flask** | Existing code is synchronous Python; Flask maps 1:1 with no ceremony. Single pip install. |
| Frontend interactivity | **htmx** | Server-rendered HTML fragments. No build step, no node_modules. One CDN script tag. |
| Styling | **Pico CSS** | Classless CSS — semantic HTML looks good immediately. One CDN link tag. |
| Charts | **Chart.js** | CDN script, ~10-20 lines of JS per chart. Only needed for stats page. |

No SPA framework, no bundler, no TypeScript, no npm.

## How to Run

```bash
pip install flask
python -m web          # starts dev server on localhost:5000
```

## Completed

All three implementation phases are done:

- **Phase 1 — Browse & Search**: Folder tree sidebar, paginated bookmark list, expandable bookmark detail cards, keyword/semantic/hybrid search with debounced input, htmx partial loading throughout.
- **Phase 2 — Stats & Visualization**: Summary cards (total bookmarks, folders, top type), Chart.js bar/doughnut/horizontal-bar charts for bookmarks per folder, type distribution, and top 20 tags.
- **Phase 3 — Create, Edit & Manage**: Bookmark creation from URL, re-fetch/re-classify, SSE-streaming link checker with progress bar, reclassification proposals.

### Routes Implemented

| Page | Path | Description |
|------|------|-------------|
| Browse | `/` | Folder tree + bookmark list with pagination |
| Search | `/search` | Multi-mode search (keyword, semantic, hybrid) |
| Stats | `/stats` | Charts and summary cards |
| Manage | `/manage` | Create, update, check, reorg |

Plus JSON APIs (`/api/*`) and htmx partials (`/partials/*`) backing each page.

## Features & Improvements

### UX

- [ ] Bookmark edit page — edit frontmatter fields (tags, folder, description) inline and save back to markdown
- [ ] Tag browsing page — browse/filter bookmarks by tag
- [ ] Recently added view — show newest bookmarks
- [ ] Folder bookmark counts — show count next to each folder in the sidebar
- [ ] In-folder search/filter — filter bookmarks within the current folder
- [ ] Advanced search filters — filter by date, type, tags, parent_topic
- [ ] Search result pagination
- [ ] Sortable/filterable broken link results
- [ ] Batch operations — add multiple URLs, bulk actions

### UI

- [ ] Error pages — custom 404 and 500 templates
- [ ] Loading skeletons — replace aria-busy spinners with skeleton loaders
- [ ] Keyboard shortcuts — quick navigation between pages, focus search
- [ ] Breadcrumbs for folder navigation
- [ ] Dark/light theme toggle
- [ ] Favicon display for bookmarks
- [ ] Mobile-responsive charts

### Performance

- [ ] API response caching — add cache headers and/or server-side caching for stats and folder data
- [ ] Efficient note lookup — avoid re-globbing the bookmark directory on every request
- [ ] Bookmark detail caching — cache expanded detail so re-clicking doesn't re-fetch

### Robustness

- [ ] Input validation — validate page/per_page range, folder parameter sanitization
- [ ] Link checker error categorization — distinguish timeout, DNS, SSL, HTTP errors
- [ ] Network error handling — htmx request failure feedback
- [ ] Export broken links report
