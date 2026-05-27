from __future__ import annotations

import re
import sqlite3
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

from .chunking import SearchChunk, chunk_documents
from .paths import get_search_index_path
from .search_documents import SearchDocument

SEARCH_TABLE = "bookmark_search"
MTIME_TABLE = "bookmark_mtime"
CHUNKS_TABLE = "note_chunks"
BM25_WEIGHTS = (0.0, 0.0, 0.0, 0.0, 8.0, 3.0, 4.0, 4.0, 3.0, 2.0, 1.0)
QUERY_TERM_PATTERN = re.compile(r"[A-Za-z0-9]{2,}")
CHUNK_RESULT_MULTIPLIER = 20


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
    section: str = ""
    chunk_index: int = 0


def _connect(database_path: Path | None = None) -> sqlite3.Connection:
    """Open the search database with catalog schema ensured."""
    from .catalog import connect as catalog_connect, ensure_catalog_schema

    if database_path is None:
        database_path = get_search_index_path()
    connection = catalog_connect(database_path)
    ensure_catalog_schema(connection)
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
            section UNINDEXED,
            chunk_index UNINDEXED,
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
    if SEARCH_TABLE not in found or MTIME_TABLE not in found:
        return False
    columns = {
        row["name"] for row in connection.execute(f"PRAGMA table_info({SEARCH_TABLE})")
    }
    return {"section", "chunk_index", "body"}.issubset(columns)


def _build_match_query(query: str) -> str:
    """Convert a free-text query into an AND-based FTS query with prefix matching."""
    terms = QUERY_TERM_PATTERN.findall(query.lower())
    if not terms:
        raise ValueError("Search query must include at least one searchable term.")
    return " AND ".join(f"{term}*" for term in terms)


def _chunk_to_index_row(chunk: SearchChunk) -> tuple[object, ...]:
    """Return a tuple of column values for an FTS insert."""
    return (
        str(chunk.path),
        chunk.url,
        chunk.section,
        chunk.chunk_index,
        chunk.title,
        chunk.folder,
        chunk.tags,
        chunk.related,
        chunk.parent_topic,
        chunk.description,
        chunk.chunk_text,
    )


def _chunk_to_catalog_row(chunk: SearchChunk) -> tuple[object, ...]:
    """Return a tuple of values for the catalog note_chunks table."""
    from .note_schema import stable_bookmark_id

    bookmark_id = stable_bookmark_id(chunk.url) if chunk.url else str(chunk.path)
    return (
        bookmark_id,
        str(chunk.path),
        chunk.section,
        chunk.chunk_index,
        chunk.chunk_text,
        chunk.token_count,
        chunk.text_hash,
    )


def _insert_documents(
    connection: sqlite3.Connection,
    documents: list[SearchDocument],
) -> None:
    """Insert documents into the FTS and mtime tables."""
    if not documents:
        return
    chunks = chunk_documents(documents)
    if not chunks:
        return
    connection.executemany(
        f"""
        INSERT INTO {SEARCH_TABLE} (
            path, url, section, chunk_index, title, folder, tags,
            related, parent_topic, description, body
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [_chunk_to_index_row(chunk) for chunk in chunks],
    )
    connection.executemany(
        f"""
        INSERT INTO {CHUNKS_TABLE} (
            bookmark_id, note_path, section, chunk_index,
            chunk_text, token_count, text_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [_chunk_to_catalog_row(chunk) for chunk in chunks],
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
        connection.execute(f"DELETE FROM {CHUNKS_TABLE} WHERE note_path = ?", (path,))


def delete_from_search_index(
    path: Path,
    *,
    database_path: Path | None = None,
) -> None:
    """Remove a single note from the FTS5 search index and mtime table."""
    if database_path is None:
        database_path = get_search_index_path()
    if not database_path.exists():
        return
    connection = _connect(database_path)
    try:
        with connection:
            _delete_by_paths(connection, {str(path)})
    except sqlite3.OperationalError:
        pass
    finally:
        connection.close()


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
            connection.execute(f"DELETE FROM {CHUNKS_TABLE}")
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
    show_chunks: bool = False,
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

    candidate_limit = limit if show_chunks else limit * CHUNK_RESULT_MULTIPLIER
    parameters.append(candidate_limit)
    bm25_weight_sql = ", ".join(str(weight) for weight in BM25_WEIGHTS)
    # FTS5 snippet() on body column (index 10) for context excerpts.
    snippet_sql = (
        f"snippet({SEARCH_TABLE}, 10, "
        f"'{SNIPPET_MARKER_START}', '{SNIPPET_MARKER_END}', "
        f"'{SNIPPET_ELLIPSIS}', {SNIPPET_MAX_TOKENS})"
    )
    sql = f"""
        SELECT path, url, section, chunk_index, title, folder, tags, parent_topic, description,
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

    results = [
        SearchResult(
            path=Path(str(row["path"])),
            url=str(row["url"]),
            title=str(row["title"]),
            folder=str(row["folder"]),
            description=str(row["description"]),
            score=_boost_score(query, row, float(row["score"])),
            snippet=str(row["snippet"] or ""),
            section=str(row["section"] or ""),
            chunk_index=int(row["chunk_index"] or 0),
        )
        for row in rows
    ]
    results.sort(key=lambda result: (-result.score, result.title, result.chunk_index))
    if show_chunks:
        return results[:limit]
    deduped: list[SearchResult] = []
    seen_paths: set[Path] = set()
    for result in results:
        if result.path in seen_paths:
            continue
        seen_paths.add(result.path)
        deduped.append(result)
        if len(deduped) >= limit:
            break
    return deduped


def _boost_score(query: str, row: sqlite3.Row, base_score: float) -> float:
    """Apply small deterministic boosts for exact metadata matches."""
    query_text = query.strip().lower()
    if not query_text:
        return base_score

    boost = 0.0
    title = str(row["title"] or "").lower()
    tags = {
        part.strip().lower()
        for part in re.split(r"[\s,]+", str(row["tags"] or ""))
        if part.strip()
    }
    folder = str(row["folder"] or "").lower()
    topic = str(row["parent_topic"] or "").lower()
    domain = urllib.parse.urlparse(str(row["url"] or "")).netloc.lower()
    domain = re.sub(r"^www\.", "", domain)

    if query_text == title or query_text in title.split():
        boost += 2.0
    if query_text in tags:
        boost += 1.5
    if query_text and (query_text == folder or query_text in folder.split("/")):
        boost += 1.0
    if query_text == topic:
        boost += 1.0
    if domain and query_text == domain:
        boost += 1.0
    return base_score + boost
