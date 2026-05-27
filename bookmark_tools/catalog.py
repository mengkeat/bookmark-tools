"""Unified SQLite catalog for bookmark-tools derived state.

The catalog consolidates FTS5 search, embeddings, bookmark metadata,
fetch logs, and stubs for future chunk/edge/job tables into a single
managed database with schema versioning and migrations.

Markdown notes remain the canonical system of record.  The catalog is
entirely derived and can be rebuilt from ``Bookmarks/**/*.md``.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .paths import get_search_index_path

# ---------------------------------------------------------------------------
# Schema constants
# ---------------------------------------------------------------------------

CATALOG_SCHEMA_VERSION = 1

META_TABLE = "catalog_meta"
BOOKMARKS_TABLE = "bookmarks"
FETCH_LOG_TABLE = "fetch_log"
CHUNKS_TABLE = "note_chunks"
EDGES_TABLE = "edges"
JOBS_TABLE = "jobs"

# Tables owned by other modules but managed by the catalog schema.
SEARCH_TABLE = "bookmark_search"
MTIME_TABLE = "bookmark_mtime"
EMBEDDING_TABLE = "embedding_store"

# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------


def connect(database_path: Path | None = None) -> sqlite3.Connection:
    """Open the catalog database with row factory enabled.

    Creates parent directories if needed.  Callers should close the
    connection when finished or use it as a context manager.
    """
    if database_path is None:
        database_path = get_search_index_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------


def _create_meta_table(connection: sqlite3.Connection) -> None:
    """Create the catalog metadata table."""
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {META_TABLE} (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )


def _create_bookmarks_table(connection: sqlite3.Connection) -> None:
    """Create the bookmarks derived metadata table."""
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {BOOKMARKS_TABLE} (
            id TEXT PRIMARY KEY,
            note_path TEXT NOT NULL UNIQUE,
            url TEXT NOT NULL,
            final_url TEXT,
            canonical_url TEXT,
            domain TEXT,
            title TEXT,
            folder TEXT,
            status TEXT,
            created_at TEXT,
            last_fetched_at TEXT,
            last_success_at TEXT,
            content_hash TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{{}}'
        )
        """
    )
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_bookmarks_url ON {BOOKMARKS_TABLE} (url)"
    )
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_bookmarks_folder ON {BOOKMARKS_TABLE} (folder)"
    )
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_bookmarks_domain ON {BOOKMARKS_TABLE} (domain)"
    )


def _create_fetch_log_table(connection: sqlite3.Connection) -> None:
    """Create the fetch log table."""
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {FETCH_LOG_TABLE} (
            id INTEGER PRIMARY KEY,
            bookmark_id TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            url TEXT NOT NULL,
            final_url TEXT,
            http_status INTEGER,
            content_type TEXT,
            content_hash TEXT,
            archive_path TEXT,
            error_stage TEXT,
            error_message TEXT
        )
        """
    )
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_fetch_log_bookmark ON {FETCH_LOG_TABLE} (bookmark_id)"
    )


def _create_chunks_table(connection: sqlite3.Connection) -> None:
    """Create the note chunks table (stub for future chunked retrieval)."""
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {CHUNKS_TABLE} (
            id INTEGER PRIMARY KEY,
            bookmark_id TEXT NOT NULL,
            note_path TEXT NOT NULL,
            section TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            chunk_text TEXT NOT NULL,
            token_count INTEGER,
            text_hash TEXT NOT NULL
        )
        """
    )
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_chunks_bookmark ON {CHUNKS_TABLE} (bookmark_id)"
    )


def _create_edges_table(connection: sqlite3.Connection) -> None:
    """Create the edges table (stub for future graph support)."""
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {EDGES_TABLE} (
            id INTEGER PRIMARY KEY,
            from_id TEXT NOT NULL,
            to_id TEXT NOT NULL,
            to_kind TEXT NOT NULL,
            edge_type TEXT NOT NULL,
            context TEXT,
            source TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(from_id, to_id, edge_type, source)
        )
        """
    )
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_edges_from ON {EDGES_TABLE} (from_id)"
    )
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_edges_to ON {EDGES_TABLE} (to_id)"
    )


def _create_jobs_table(connection: sqlite3.Connection) -> None:
    """Create the jobs/checkpoints table (stub for future automation)."""
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {JOBS_TABLE} (
            id INTEGER PRIMARY KEY,
            kind TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            progress_json TEXT NOT NULL DEFAULT '{{}}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def _create_fts_table(connection: sqlite3.Connection) -> None:
    """Create the FTS5 full-text search table."""
    connection.execute(
        f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS {SEARCH_TABLE} USING fts5(
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


def _create_mtime_table(connection: sqlite3.Connection) -> None:
    """Create the file mtime tracking table."""
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {MTIME_TABLE} (
            path TEXT PRIMARY KEY,
            mtime REAL NOT NULL
        )
        """
    )


def _create_embedding_table(connection: sqlite3.Connection) -> None:
    """Create the embedding storage table."""
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {EMBEDDING_TABLE} (
            path TEXT NOT NULL,
            chunk_index INTEGER NOT NULL DEFAULT 0,
            url TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            folder TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            section TEXT NOT NULL DEFAULT '',
            chunk_text TEXT NOT NULL DEFAULT '',
            embedding BLOB NOT NULL,
            mtime REAL NOT NULL,
            model TEXT NOT NULL DEFAULT '',
            dimensions INTEGER NOT NULL DEFAULT 0,
            text_hash TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (path, chunk_index)
        )
        """
    )


def _set_version(connection: sqlite3.Connection, version: int) -> None:
    """Record the catalog schema version."""
    connection.execute(
        f"INSERT OR REPLACE INTO {META_TABLE} (key, value) VALUES (?, ?)",
        ("schema_version", str(version)),
    )


# ---------------------------------------------------------------------------
# Public schema operations
# ---------------------------------------------------------------------------


def get_catalog_version(
    connection: sqlite3.Connection,
) -> int:
    """Return the catalog schema version, or 0 if not initialized."""
    try:
        row = connection.execute(
            f"SELECT value FROM {META_TABLE} WHERE key = ?",
            ("schema_version",),
        ).fetchone()
        return int(row["value"]) if row else 0
    except sqlite3.OperationalError:
        return 0


def ensure_catalog_schema(
    connection: sqlite3.Connection,
) -> None:
    """Create all catalog tables if they do not exist.

    Idempotent — safe to call on every connection.  Creates the meta,
    bookmarks, fetch_log, chunks, edges, jobs, FTS, mtime, and embedding
    tables, then records the current schema version.
    """
    _create_meta_table(connection)
    _create_bookmarks_table(connection)
    _create_fetch_log_table(connection)
    _create_chunks_table(connection)
    _create_edges_table(connection)
    _create_jobs_table(connection)
    _create_fts_table(connection)
    _create_mtime_table(connection)
    _create_embedding_table(connection)
    _set_version(connection, CATALOG_SCHEMA_VERSION)


def rebuild_catalog_schema(connection: sqlite3.Connection) -> None:
    """Drop and recreate all catalog tables.

    Used for full rebuilds.  Clears all derived state so it can be
    repopulated from Markdown notes.
    """
    # Drop in dependency order (dependent tables first)
    for table in (
        FETCH_LOG_TABLE,
        CHUNKS_TABLE,
        EDGES_TABLE,
        JOBS_TABLE,
        BOOKMARKS_TABLE,
        EMBEDDING_TABLE,
        MTIME_TABLE,
        SEARCH_TABLE,
        META_TABLE,
    ):
        connection.execute(f"DROP TABLE IF EXISTS {table}")
    ensure_catalog_schema(connection)


def table_names(connection: sqlite3.Connection) -> set[str]:
    """Return all user table names in the catalog database."""
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {str(row[0]) for row in rows}


def catalog_tables_exist(connection: sqlite3.Connection) -> bool:
    """Return True if the core catalog tables are present."""
    tables = table_names(connection)
    required = {META_TABLE, BOOKMARKS_TABLE, SEARCH_TABLE, MTIME_TABLE}
    return required.issubset(tables)


# ---------------------------------------------------------------------------
# Bookmark metadata population
# ---------------------------------------------------------------------------


def _row_from_note_metadata(
    note_path: Path,
    metadata: dict[str, object],
    bookmarks_dir: Path,
) -> tuple[str, ...]:
    """Build a bookmarks row from parsed note metadata."""
    from .note_schema import domain_from_url, stable_bookmark_id
    from .url_normalize import normalize_url

    url = str(metadata.get("url", "")).strip()
    bookmark_id = str(metadata.get("id", "")).strip() or stable_bookmark_id(url)
    final_url = str(metadata.get("final_url", "")).strip()
    canonical_url = str(metadata.get("canonical_url", "")).strip()
    domain = str(metadata.get("domain", "")).strip() or domain_from_url(
        canonical_url or final_url or url
    )
    folder = str(note_path.relative_to(bookmarks_dir).parent)
    if folder == ".":
        folder = ""

    return (
        bookmark_id,
        str(note_path),
        normalize_url(url),
        normalize_url(final_url) if final_url else "",
        normalize_url(canonical_url) if canonical_url else "",
        domain,
        str(metadata.get("title", "")).strip(),
        folder,
        str(metadata.get("status", "")).strip(),
        str(metadata.get("added_at", metadata.get("created", ""))).strip(),
        str(metadata.get("last_fetched_at", "")).strip(),
        str(metadata.get("last_success_at", "")).strip(),
        str(metadata.get("content_hash", "")).strip(),
        json.dumps(
            {k: v for k, v in metadata.items()}, default=str, ensure_ascii=False
        ),
    )


def populate_bookmarks(
    connection: sqlite3.Connection,
    bookmarks_dir: Path,
) -> int:
    """Populate the bookmarks table from vault Markdown notes.

    Returns the number of bookmarks inserted.
    """
    from .note_filter import iter_bookmark_note_paths
    from .note_schema import parse_note_file

    connection.execute(f"DELETE FROM {BOOKMARKS_TABLE}")

    rows: list[tuple[str, ...]] = []
    for note_path in iter_bookmark_note_paths(bookmarks_dir, bookmark_only=True):
        note = parse_note_file(note_path)
        if not note.is_bookmark:
            continue
        rows.append(_row_from_note_metadata(note_path, note.frontmatter, bookmarks_dir))

    if rows:
        connection.executemany(
            f"""
            INSERT OR REPLACE INTO {BOOKMARKS_TABLE} (
                id, note_path, url, final_url, canonical_url, domain,
                title, folder, status, created_at, last_fetched_at,
                last_success_at, content_hash, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    return len(rows)


# ---------------------------------------------------------------------------
# Catalog rebuild
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CatalogResult:
    """Result summary for a catalog rebuild operation."""

    database_path: Path
    bookmark_count: int
    fts_rebuilt: bool
    embeddings_rebuilt: bool
    embeddings_skipped_reason: str = ""

    def to_dict(self) -> dict[str, object]:
        """Return a stable JSON-serializable representation."""
        return {
            "database_path": str(self.database_path),
            "bookmark_count": self.bookmark_count,
            "fts_rebuilt": self.fts_rebuilt,
            "embeddings_rebuilt": self.embeddings_rebuilt,
            "embeddings_skipped_reason": self.embeddings_skipped_reason,
        }


def rebuild_catalog(
    *,
    bookmarks_dir: Path | None = None,
    database_path: Path | None = None,
    include_embeddings: bool = True,
    embedding_config: dict[str, str] | None = None,
) -> CatalogResult:
    """Rebuild all catalog tables from Markdown notes.

    This drops and recreates all derived tables (bookmarks, FTS, embeddings,
    fetch_log, etc.) and repopulates them from the vault.
    """
    from .classify import get_llm_config
    from .paths import require_bookmarks_dir
    from .search_documents import collect_search_documents
    from .search_index import rebuild_search_index

    if bookmarks_dir is None:
        bookmarks_dir = require_bookmarks_dir()
    if database_path is None:
        database_path = get_search_index_path()

    documents = collect_search_documents(bookmarks_dir=bookmarks_dir)

    connection = connect(database_path)
    try:
        with connection:
            rebuild_catalog_schema(connection)
            populate_bookmarks(connection, bookmarks_dir)
            # Rebuild FTS via the search_index module (it creates its own
            # connection but the tables already exist, so we insert directly).
            _populate_fts(connection, documents)
    finally:
        connection.close()

    # Also use the search_index module for its standard rebuild path
    # (this re-does the FTS but ensures consistency with the existing API).
    rebuild_search_index(documents, database_path=database_path)

    embeddings_rebuilt = False
    embeddings_skipped_reason = ""
    if include_embeddings:
        config = embedding_config if embedding_config is not None else get_llm_config()
        if config:
            from .embeddings import rebuild_embeddings

            rebuild_embeddings(documents, database_path=database_path, config=config)
            embeddings_rebuilt = True
        else:
            embeddings_skipped_reason = (
                "No LLM API key configured; skipped embedding rebuild."
            )
    else:
        embeddings_skipped_reason = "Embedding rebuild disabled."

    return CatalogResult(
        database_path=database_path,
        bookmark_count=len(documents),
        fts_rebuilt=True,
        embeddings_rebuilt=embeddings_rebuilt,
        embeddings_skipped_reason=embeddings_skipped_reason,
    )


def _populate_fts(
    connection: sqlite3.Connection,
    documents: list,
) -> None:
    """Insert documents into the FTS and mtime tables directly.

    Uses the catalog's existing connection rather than opening a new one.
    """
    from .chunking import chunk_documents
    from .note_schema import stable_bookmark_id

    if not documents:
        return
    chunks = chunk_documents(documents)
    connection.executemany(
        f"""
        INSERT INTO {SEARCH_TABLE} (
            path, url, section, chunk_index, title, folder, tags,
            related, parent_topic, description, body
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
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
            for chunk in chunks
        ],
    )
    connection.executemany(
        f"""
        INSERT INTO {CHUNKS_TABLE} (
            bookmark_id, note_path, section, chunk_index,
            chunk_text, token_count, text_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                stable_bookmark_id(chunk.url) if chunk.url else str(chunk.path),
                str(chunk.path),
                chunk.section,
                chunk.chunk_index,
                chunk.chunk_text,
                chunk.token_count,
                chunk.text_hash,
            )
            for chunk in chunks
        ],
    )
    connection.executemany(
        f"INSERT OR REPLACE INTO {MTIME_TABLE} (path, mtime) VALUES (?, ?)",
        [(str(doc.path), doc.path.stat().st_mtime) for doc in documents],
    )


# ---------------------------------------------------------------------------
# Catalog row maintenance
# ---------------------------------------------------------------------------


def upsert_bookmark(
    connection: sqlite3.Connection,
    note_path: Path,
    bookmarks_dir: Path,
) -> None:
    """Insert or update a single bookmark row in the catalog.

    Called after creating or updating a bookmark note.
    """
    from .note_schema import parse_note_file

    note = parse_note_file(note_path)
    if not note.is_bookmark:
        return
    row = _row_from_note_metadata(note_path, note.frontmatter, bookmarks_dir)
    connection.execute(
        f"""
        INSERT OR REPLACE INTO {BOOKMARKS_TABLE} (
            id, note_path, url, final_url, canonical_url, domain,
            title, folder, status, created_at, last_fetched_at,
            last_success_at, content_hash, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        row,
    )


def delete_from_catalog(
    path: Path,
    *,
    database_path: Path | None = None,
) -> None:
    """Remove a bookmark from all catalog tables.

    Delegates to existing module functions for FTS and embeddings, and
    removes the bookmarks row by note_path.
    """
    from .embeddings import delete_from_embedding_store
    from .search_index import delete_from_search_index

    if database_path is None:
        database_path = get_search_index_path()
    if not database_path.exists():
        return

    path_str = str(path)

    # Remove from FTS and embeddings via existing module functions.
    delete_from_search_index(path, database_path=database_path)
    delete_from_embedding_store(path, database_path=database_path)

    # Remove from bookmarks table.
    connection = connect(database_path)
    try:
        with connection:
            connection.execute(
                f"DELETE FROM {BOOKMARKS_TABLE} WHERE note_path = ?",
                (path_str,),
            )
            connection.execute(
                f"DELETE FROM {FETCH_LOG_TABLE} WHERE bookmark_id IN "
                f"(SELECT id FROM {BOOKMARKS_TABLE} WHERE note_path = ?)",
                (path_str,),
            )
            connection.execute(
                f"DELETE FROM {CHUNKS_TABLE} WHERE note_path = ?",
                (path_str,),
            )
    except sqlite3.OperationalError:
        pass
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# Catalog info / introspection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CatalogInfo:
    """Summary of catalog state for display and doctor checks."""

    database_path: Path
    exists: bool
    schema_version: int
    bookmark_count: int
    fts_count: int
    embedding_count: int
    fetch_log_count: int
    chunk_count: int
    edge_count: int
    job_count: int

    def to_dict(self) -> dict[str, object]:
        """Return a stable JSON-serializable representation."""
        return {
            "database_path": str(self.database_path),
            "exists": self.exists,
            "schema_version": self.schema_version,
            "bookmark_count": self.bookmark_count,
            "fts_count": self.fts_count,
            "embedding_count": self.embedding_count,
            "fetch_log_count": self.fetch_log_count,
            "chunk_count": self.chunk_count,
            "edge_count": self.edge_count,
            "job_count": self.job_count,
        }


def _count_rows(connection: sqlite3.Connection, table: str) -> int:
    """Count rows in a table, returning 0 if the table doesn't exist."""
    try:
        row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        return int(row[0]) if row else 0
    except sqlite3.OperationalError:
        return 0


def get_catalog_info(
    database_path: Path | None = None,
) -> CatalogInfo:
    """Return catalog metadata and row counts."""
    if database_path is None:
        database_path = get_search_index_path()

    if not database_path.exists():
        return CatalogInfo(
            database_path=database_path,
            exists=False,
            schema_version=0,
            bookmark_count=0,
            fts_count=0,
            embedding_count=0,
            fetch_log_count=0,
            chunk_count=0,
            edge_count=0,
            job_count=0,
        )

    connection = connect(database_path)
    try:
        version = get_catalog_version(connection)
        return CatalogInfo(
            database_path=database_path,
            exists=True,
            schema_version=version,
            bookmark_count=_count_rows(connection, BOOKMARKS_TABLE),
            fts_count=_count_rows(connection, SEARCH_TABLE),
            embedding_count=_count_rows(connection, EMBEDDING_TABLE),
            fetch_log_count=_count_rows(connection, FETCH_LOG_TABLE),
            chunk_count=_count_rows(connection, CHUNKS_TABLE),
            edge_count=_count_rows(connection, EDGES_TABLE),
            job_count=_count_rows(connection, JOBS_TABLE),
        )
    except sqlite3.DatabaseError:
        return CatalogInfo(
            database_path=database_path,
            exists=True,
            schema_version=0,
            bookmark_count=0,
            fts_count=0,
            embedding_count=0,
            fetch_log_count=0,
            chunk_count=0,
            edge_count=0,
            job_count=0,
        )
    finally:
        connection.close()
