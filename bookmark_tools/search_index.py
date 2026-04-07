from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .paths import get_search_index_path
from .search_documents import SearchDocument

SEARCH_TABLE = "bookmark_search"
MTIME_TABLE = "bookmark_mtime"
BM25_WEIGHTS = (0.0, 0.0, 8.0, 3.0, 4.0, 4.0, 3.0, 2.0, 1.0)
QUERY_TERM_PATTERN = re.compile(r"[A-Za-z0-9+#-]{2,}")


SNIPPET_MAX_TOKENS = 10
SNIPPET_MARKER_START = "»"
SNIPPET_MARKER_END = "«"
SNIPPET_ELLIPSIS = "…"


@dataclass(frozen=True)
class SearchResult:
    path: Path
    url: str
    title: str
    folder: str
    description: str
    score: float
    snippet: str = ""


def _connect(database_path: Path | None = None) -> sqlite3.Connection:
    """Open the search database with row access enabled."""
    if database_path is None:
        database_path = get_search_index_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def _create_schema(connection: sqlite3.Connection) -> None:
    """Drop and recreate the FTS5 search table and mtime tracking table."""
    connection.execute(f"DROP TABLE IF EXISTS {SEARCH_TABLE}")
    connection.execute(f"DROP TABLE IF EXISTS {MTIME_TABLE}")
    connection.execute(
        f"""
        CREATE VIRTUAL TABLE {SEARCH_TABLE} USING fts5(
            path UNINDEXED,
            url UNINDEXED,
            title,
            folder,
            tags,
            related,
            parent_topic,
            description,
            body,
            tokenize='porter unicode61'
        )
        """
    )
    connection.execute(
        f"""
        CREATE TABLE {MTIME_TABLE} (
            path TEXT PRIMARY KEY,
            mtime REAL NOT NULL
        )
        """
    )


def _schema_exists(connection: sqlite3.Connection) -> bool:
    """Return True if both the search and mtime tables exist."""
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE name IN (?, ?)",
        (SEARCH_TABLE, MTIME_TABLE),
    ).fetchall()
    found = {row["name"] for row in rows}
    return SEARCH_TABLE in found and MTIME_TABLE in found


def _build_match_query(query: str) -> str:
    """Convert a free-text query into an AND-based FTS query with prefix matching."""
    terms = QUERY_TERM_PATTERN.findall(query.lower())
    if not terms:
        raise ValueError("Search query must include at least one searchable term.")
    return " AND ".join(f"{term}*" for term in terms)


def _document_to_index_row(document: SearchDocument) -> tuple[str, ...]:
    """Return a tuple of column values for an FTS insert."""
    return (
        str(document.path),
        document.url,
        document.title,
        document.folder,
        document.tags,
        document.related,
        document.parent_topic,
        document.description,
        document.body,
    )


def _insert_documents(
    connection: sqlite3.Connection,
    documents: list[SearchDocument],
) -> None:
    """Insert documents into the FTS and mtime tables."""
    if not documents:
        return
    connection.executemany(
        f"""
        INSERT INTO {SEARCH_TABLE} (
            path, url, title, folder, tags,
            related, parent_topic, description, body
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [_document_to_index_row(document) for document in documents],
    )
    connection.executemany(
        f"INSERT OR REPLACE INTO {MTIME_TABLE} (path, mtime) VALUES (?, ?)",
        [(str(document.path), document.path.stat().st_mtime) for document in documents],
    )


def _delete_by_paths(
    connection: sqlite3.Connection,
    paths: set[str],
) -> None:
    """Remove entries from both the FTS and mtime tables by path."""
    for path in paths:
        connection.execute(f"DELETE FROM {SEARCH_TABLE} WHERE path = ?", (path,))
        connection.execute(f"DELETE FROM {MTIME_TABLE} WHERE path = ?", (path,))


def _load_stored_mtimes(connection: sqlite3.Connection) -> dict[str, float]:
    """Load the path-to-mtime mapping from the database."""
    rows = connection.execute(f"SELECT path, mtime FROM {MTIME_TABLE}").fetchall()
    return {row["path"]: float(row["mtime"]) for row in rows}


def rebuild_search_index(
    documents: list[SearchDocument],
    database_path: Path | None = None,
) -> None:
    """Rebuild the search index from scratch."""
    connection = _connect(database_path)
    try:
        with connection:
            _create_schema(connection)
            _insert_documents(connection, documents)
    finally:
        connection.close()


def update_search_index(
    documents: list[SearchDocument],
    database_path: Path | None = None,
) -> None:
    """Incrementally update the index, only touching new, modified, or deleted files."""
    connection = _connect(database_path)
    try:
        if not _schema_exists(connection):
            with connection:
                _create_schema(connection)
                _insert_documents(connection, documents)
            return

        stored_mtimes = _load_stored_mtimes(connection)
        current_paths = {str(document.path) for document in documents}

        removed_paths = stored_mtimes.keys() - current_paths
        new_documents: list[SearchDocument] = []
        modified_documents: list[SearchDocument] = []
        for document in documents:
            document_path = str(document.path)
            if document_path not in stored_mtimes:
                new_documents.append(document)
            elif document.path.stat().st_mtime != stored_mtimes[document_path]:
                modified_documents.append(document)

        if not removed_paths and not new_documents and not modified_documents:
            return

        modified_paths = {str(document.path) for document in modified_documents}
        with connection:
            _delete_by_paths(connection, removed_paths | modified_paths)
            _insert_documents(connection, new_documents + modified_documents)
    finally:
        connection.close()


def search_index(
    query: str,
    *,
    database_path: Path | None = None,
    folder: str | None = None,
    tag: str | None = None,
    limit: int = 10,
) -> list[SearchResult]:
    """Query the FTS5 index and return BM25-ranked bookmark matches."""
    match_query = _build_match_query(query)

    where_clauses = [f"{SEARCH_TABLE} MATCH ?"]
    parameters: list[object] = [match_query]

    normalized_folder = folder.strip().strip("/") if folder else ""
    if normalized_folder:
        where_clauses.append("(folder = ? OR folder LIKE ?)")
        parameters.extend([normalized_folder, f"{normalized_folder}/%"])

    if tag:
        normalized_tag = tag.strip().lower()
        where_clauses.append("tags LIKE ?")
        parameters.append(f"%{normalized_tag}%")

    parameters.append(limit)
    bm25_weight_sql = ", ".join(str(weight) for weight in BM25_WEIGHTS)
    # FTS5 snippet() on body column (index 8) for context excerpts
    snippet_sql = (
        f"snippet({SEARCH_TABLE}, 8, "
        f"'{SNIPPET_MARKER_START}', '{SNIPPET_MARKER_END}', "
        f"'{SNIPPET_ELLIPSIS}', {SNIPPET_MAX_TOKENS})"
    )
    sql = f"""
        SELECT path, url, title, folder, description,
               -bm25({SEARCH_TABLE}, {bm25_weight_sql}) AS score,
               {snippet_sql} AS snippet
        FROM {SEARCH_TABLE}
        WHERE {" AND ".join(where_clauses)}
        ORDER BY score DESC, title ASC
        LIMIT ?
    """

    connection = _connect(database_path)
    try:
        rows = connection.execute(sql, parameters).fetchall()
    finally:
        connection.close()

    return [
        SearchResult(
            path=Path(str(row["path"])),
            url=str(row["url"]),
            title=str(row["title"]),
            folder=str(row["folder"]),
            description=str(row["description"]),
            score=float(row["score"]),
            snippet=str(row["snippet"] or ""),
        )
        for row in rows
    ]
