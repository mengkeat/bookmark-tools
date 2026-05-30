"""Lightweight deterministic graph for bookmark relationships.

Edges are extracted from Markdown notes (frontmatter + body) without any
LLM involvement and stored in the catalog ``edges`` table.  The graph is
entirely derived from canonical notes and can be rebuilt at any time.

Supported edge types (all deterministic):

| edge_type       | to_kind | extracted from                         |
|-----------------|---------|----------------------------------------|
| ``in_folder``   | folder  | note path relative to the vault root   |
| ``has_tag``     | tag     | frontmatter ``tags``                    |
| ``from_domain`` | domain  | frontmatter ``domain`` / URL host       |
| ``links_to_url``| url     | http(s) URLs in the note body           |
| ``related_to``  | topic   | frontmatter ``related``                 |

Author/entity/mention edges are intentionally deferred — they need author
metadata or LLM extraction and are out of scope for the deterministic core.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .catalog import BOOKMARKS_TABLE, EDGES_TABLE, connect
from .note_schema import BookmarkNote, domain_from_url, parse_note_file, stable_bookmark_id, utc_now
from .url_normalize import normalize_url

# Edge type / kind constants
EDGE_IN_FOLDER = "in_folder"
EDGE_HAS_TAG = "has_tag"
EDGE_FROM_DOMAIN = "from_domain"
EDGE_LINKS_TO_URL = "links_to_url"
EDGE_RELATED_TO = "related_to"

# Edge types that connect two bookmarks via a shared attribute. Used for
# related-bookmark suggestions and graph traversal.
SHARED_ATTR_EDGE_TYPES = (EDGE_HAS_TAG, EDGE_FROM_DOMAIN, EDGE_RELATED_TO)

# Bare/markdown URL extraction. Trailing punctuation is trimmed below.
_URL_RE = re.compile(r"https?://[^\s\)\]<>\"']+", re.IGNORECASE)
_URL_TRAILING = ".,;:!?)]}'\""


@dataclass(frozen=True)
class Edge:
    """A single deterministic graph edge from a bookmark."""

    from_id: str
    to_id: str
    to_kind: str
    edge_type: str
    context: str = ""
    source: str = "frontmatter"


@dataclass(frozen=True)
class Backlink:
    """A bookmark that references another bookmark."""

    bookmark_id: str
    url: str
    title: str
    note_path: str
    edge_type: str


@dataclass(frozen=True)
class RelatedBookmark:
    """A bookmark related to another via shared attributes."""

    bookmark_id: str
    url: str
    title: str
    note_path: str
    shared: int
    via: list[str]


# ---------------------------------------------------------------------------
# Edge extraction
# ---------------------------------------------------------------------------


def bookmark_id_for_note(note: BookmarkNote) -> str:
    """Return the stable bookmark id for a parsed note."""
    existing = str(note.frontmatter.get("id", "")).strip()
    if existing:
        return existing
    return stable_bookmark_id(str(note.frontmatter.get("url", "")).strip())


def _folder_for_note(note: BookmarkNote, bookmarks_dir: Path) -> str:
    """Return the note's folder relative to the vault root, or ''."""
    if note.path is None:
        return ""
    try:
        folder = str(note.path.relative_to(bookmarks_dir).parent)
    except ValueError:
        return ""
    return "" if folder == "." else folder


def _frontmatter_list(note: BookmarkNote, key: str) -> list[str]:
    """Return a frontmatter value coerced to a list of trimmed strings."""
    value = note.frontmatter.get(key)
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []


def extract_body_urls(body: str, *, exclude: set[str]) -> list[str]:
    """Extract normalized http(s) URLs from a note body.

    URLs whose normalized form is in *exclude* (typically the bookmark's own
    url/final/canonical) are dropped, as are exact duplicates.
    """
    seen: set[str] = set()
    urls: list[str] = []
    for match in _URL_RE.findall(body):
        cleaned = match.rstrip(_URL_TRAILING)
        if not cleaned:
            continue
        normalized = normalize_url(cleaned)
        if normalized in exclude or normalized in seen:
            continue
        seen.add(normalized)
        urls.append(normalized)
    return urls


def extract_edges(note: BookmarkNote, *, bookmarks_dir: Path) -> list[Edge]:
    """Extract all deterministic edges for a single bookmark note."""
    if not note.is_bookmark:
        return []

    from_id = bookmark_id_for_note(note)
    edges: list[Edge] = []

    folder = _folder_for_note(note, bookmarks_dir)
    if folder:
        edges.append(
            Edge(from_id, folder, "folder", EDGE_IN_FOLDER, context=folder, source="path")
        )

    for tag in _frontmatter_list(note, "tags"):
        edges.append(
            Edge(from_id, tag.lower(), "tag", EDGE_HAS_TAG, context=tag)
        )

    url = str(note.frontmatter.get("url", "")).strip()
    final_url = str(note.frontmatter.get("final_url", "")).strip()
    canonical_url = str(note.frontmatter.get("canonical_url", "")).strip()
    domain = str(note.frontmatter.get("domain", "")).strip() or domain_from_url(
        canonical_url or final_url or url
    )
    if domain:
        edges.append(
            Edge(from_id, domain.lower(), "domain", EDGE_FROM_DOMAIN, context=domain)
        )

    for topic in _frontmatter_list(note, "related"):
        edges.append(
            Edge(from_id, topic.lower(), "topic", EDGE_RELATED_TO, context=topic)
        )

    own_urls = {
        normalize_url(u) for u in (url, final_url, canonical_url) if u
    }
    for target in extract_body_urls(note.body, exclude=own_urls):
        edges.append(
            Edge(from_id, target, "url", EDGE_LINKS_TO_URL, context=target, source="body")
        )

    return edges


# ---------------------------------------------------------------------------
# Edge persistence
# ---------------------------------------------------------------------------


def _insert_edges(connection: sqlite3.Connection, edges: list[Edge]) -> None:
    """Insert edges, ignoring duplicates per the table's UNIQUE constraint."""
    if not edges:
        return
    now = utc_now()
    connection.executemany(
        f"""
        INSERT OR IGNORE INTO {EDGES_TABLE} (
            from_id, to_id, to_kind, edge_type, context, source, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (e.from_id, e.to_id, e.to_kind, e.edge_type, e.context, e.source, now)
            for e in edges
        ],
    )


def replace_edges_for_bookmark(
    connection: sqlite3.Connection, from_id: str, edges: list[Edge]
) -> None:
    """Replace all edges originating from *from_id* with a fresh set."""
    connection.execute(f"DELETE FROM {EDGES_TABLE} WHERE from_id = ?", (from_id,))
    _insert_edges(connection, edges)


def delete_edges_for_bookmark(connection: sqlite3.Connection, from_id: str) -> None:
    """Remove all edges originating from *from_id*."""
    connection.execute(f"DELETE FROM {EDGES_TABLE} WHERE from_id = ?", (from_id,))


def upsert_edges_for_note(
    connection: sqlite3.Connection, note_path: Path, bookmarks_dir: Path
) -> int:
    """Re-extract and store edges for a single note. Returns edge count."""
    note = parse_note_file(note_path)
    if not note.is_bookmark:
        return 0
    from_id = bookmark_id_for_note(note)
    edges = extract_edges(note, bookmarks_dir=bookmarks_dir)
    replace_edges_for_bookmark(connection, from_id, edges)
    return len(edges)


def rebuild_edges(connection: sqlite3.Connection, bookmarks_dir: Path) -> int:
    """Drop and rebuild every edge from the vault. Returns total edge count."""
    from .note_filter import iter_bookmark_note_paths

    connection.execute(f"DELETE FROM {EDGES_TABLE}")
    total = 0
    for note_path in iter_bookmark_note_paths(bookmarks_dir, bookmark_only=True):
        note = parse_note_file(note_path)
        if not note.is_bookmark:
            continue
        edges = extract_edges(note, bookmarks_dir=bookmarks_dir)
        _insert_edges(connection, edges)
        total += len(edges)
    return total


# ---------------------------------------------------------------------------
# Graph queries
# ---------------------------------------------------------------------------


def _bookmark_urls(connection: sqlite3.Connection, bookmark_id: str) -> list[str]:
    """Return the normalized url/final/canonical URLs for a bookmark."""
    row = connection.execute(
        f"SELECT url, final_url, canonical_url FROM {BOOKMARKS_TABLE} WHERE id = ?",
        (bookmark_id,),
    ).fetchone()
    if row is None:
        return []
    urls = {
        normalize_url(value)
        for value in (row["url"], row["final_url"], row["canonical_url"])
        if value
    }
    return [u for u in urls if u]


def get_backlinks(
    connection: sqlite3.Connection, bookmark_id: str
) -> list[Backlink]:
    """Return bookmarks whose body links to this bookmark's URL.

    A backlink exists when another bookmark has a ``links_to_url`` edge whose
    target matches any of this bookmark's url/final/canonical URLs.
    """
    urls = _bookmark_urls(connection, bookmark_id)
    if not urls:
        return []
    placeholders = ", ".join("?" for _ in urls)
    rows = connection.execute(
        f"""
        SELECT b.id, b.url, b.title, b.note_path, e.edge_type
        FROM {EDGES_TABLE} e
        JOIN {BOOKMARKS_TABLE} b ON b.id = e.from_id
        WHERE e.edge_type = ?
          AND e.to_id IN ({placeholders})
          AND e.from_id != ?
        ORDER BY b.title
        """,
        (EDGE_LINKS_TO_URL, *urls, bookmark_id),
    ).fetchall()
    return [
        Backlink(
            bookmark_id=row["id"],
            url=row["url"],
            title=row["title"] or row["url"],
            note_path=row["note_path"],
            edge_type=row["edge_type"],
        )
        for row in rows
    ]


def get_related(
    connection: sqlite3.Connection, bookmark_id: str, *, limit: int = 10
) -> list[RelatedBookmark]:
    """Return bookmarks sharing tags/domain/related-topics with this one.

    Ranked by the number of shared attributes, descending.
    """
    edge_placeholders = ", ".join("?" for _ in SHARED_ATTR_EDGE_TYPES)
    rows = connection.execute(
        f"""
        SELECT e2.from_id AS other_id,
               COUNT(*) AS shared,
               GROUP_CONCAT(DISTINCT e2.edge_type) AS edge_types,
               b.url AS url, b.title AS title, b.note_path AS note_path
        FROM {EDGES_TABLE} e1
        JOIN {EDGES_TABLE} e2
          ON e1.to_id = e2.to_id
         AND e1.edge_type = e2.edge_type
        JOIN {BOOKMARKS_TABLE} b ON b.id = e2.from_id
        WHERE e1.from_id = ?
          AND e2.from_id != ?
          AND e1.edge_type IN ({edge_placeholders})
        GROUP BY e2.from_id
        ORDER BY shared DESC, b.title
        LIMIT ?
        """,
        (bookmark_id, bookmark_id, *SHARED_ATTR_EDGE_TYPES, limit),
    ).fetchall()
    return [
        RelatedBookmark(
            bookmark_id=row["other_id"],
            url=row["url"],
            title=row["title"] or row["url"],
            note_path=row["note_path"],
            shared=int(row["shared"]),
            via=sorted((row["edge_types"] or "").split(",")),
        )
        for row in rows
    ]


def _neighbor_ids(connection: sqlite3.Connection, bookmark_id: str) -> set[str]:
    """Return bookmark ids directly adjacent via shared attrs or links."""
    neighbors = {
        related.bookmark_id
        for related in get_related(connection, bookmark_id, limit=1000)
    }
    # Outbound link targets that resolve to known bookmarks.
    rows = connection.execute(
        f"""
        SELECT b.id AS id
        FROM {EDGES_TABLE} e
        JOIN {BOOKMARKS_TABLE} b
          ON e.to_id IN (b.url, b.final_url, b.canonical_url)
        WHERE e.from_id = ? AND e.edge_type = ?
        """,
        (bookmark_id, EDGE_LINKS_TO_URL),
    ).fetchall()
    for row in rows:
        neighbors.add(row["id"])
    # Incoming backlinks are neighbors too.
    for backlink in get_backlinks(connection, bookmark_id):
        neighbors.add(backlink.bookmark_id)
    neighbors.discard(bookmark_id)
    return neighbors


def traverse(
    connection: sqlite3.Connection, bookmark_id: str, *, depth: int = 1
) -> dict[str, int]:
    """Breadth-first traversal from *bookmark_id* up to *depth* hops.

    Returns a mapping of reached bookmark id -> hop distance (excluding the
    start node).
    """
    distances: dict[str, int] = {}
    frontier = {bookmark_id}
    visited = {bookmark_id}
    for hop in range(1, max(depth, 0) + 1):
        next_frontier: set[str] = set()
        for node in frontier:
            for neighbor in _neighbor_ids(connection, node):
                if neighbor not in visited:
                    visited.add(neighbor)
                    distances[neighbor] = hop
                    next_frontier.add(neighbor)
        if not next_frontier:
            break
        frontier = next_frontier
    return distances


# ---------------------------------------------------------------------------
# Convenience: open a connection for read-only graph queries
# ---------------------------------------------------------------------------


def open_graph(database_path: Path | None = None) -> sqlite3.Connection:
    """Open a catalog connection for graph queries."""
    return connect(database_path)
