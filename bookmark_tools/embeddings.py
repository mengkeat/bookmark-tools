from __future__ import annotations

import json
import sqlite3
import struct
import urllib.error
import urllib.request
from dataclasses import dataclass

from .config import DEFAULT_EMBEDDING_DIMENSIONS, DEFAULT_EMBEDDING_MODEL
from .http_retry import urlopen_with_retry
from pathlib import Path

from .chunking import SearchChunk, chunk_documents
from .classify import get_llm_config
from .paths import DEFAULT_TIMEOUT, get_search_index_path
from .search_documents import SearchDocument

EMBEDDING_TABLE = "embedding_store"
EMBEDDING_MODEL = DEFAULT_EMBEDDING_MODEL
EMBEDDING_DIMENSIONS = DEFAULT_EMBEDDING_DIMENSIONS
EMBEDDING_BATCH_SIZE = 512
EMBEDDING_BODY_CHARACTER_LIMIT = 500
MIN_SIMILARITY_THRESHOLD = 0.40


@dataclass(frozen=True)
class EmbeddingMatch:
    path: Path
    url: str
    title: str
    folder: str
    description: str
    similarity: float
    snippet: str = ""
    section: str = ""
    chunk_index: int = 0


# ---------------------------------------------------------------------------
# Embedding API
# ---------------------------------------------------------------------------


def _call_embedding_api(
    texts: list[str],
    config: dict[str, str],
) -> list[list[float]]:
    """Call the OpenAI-compatible embeddings endpoint and return vectors."""
    payload = {
        "model": embedding_model(config),
        "input": texts,
        "dimensions": embedding_dimensions(config),
    }
    request = urllib.request.Request(
        f"{config['base_url']}/embeddings",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    timeout = int(config.get("request_timeout") or DEFAULT_TIMEOUT)
    with urlopen_with_retry(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    body["data"].sort(key=lambda item: item["index"])
    return [item["embedding"] for item in body["data"]]


def embed_texts(
    texts: list[str],
    config: dict[str, str],
) -> list[list[float]]:
    """Embed a list of texts, batching to stay within API limits."""
    all_embeddings: list[list[float]] = []
    for start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        batch = texts[start : start + EMBEDDING_BATCH_SIZE]
        all_embeddings.extend(_call_embedding_api(batch, config))
    return all_embeddings


def embedding_model(config: dict[str, str] | None = None) -> str:
    """Return the configured embedding model name."""
    config = config or {}
    return config.get("embedding_model") or EMBEDDING_MODEL


def embedding_dimensions(config: dict[str, str] | None = None) -> int:
    """Return the configured embedding dimensions."""
    config = config or {}
    value = config.get("embedding_dimensions") or EMBEDDING_DIMENSIONS
    return int(value)


# ---------------------------------------------------------------------------
# Document text construction
# ---------------------------------------------------------------------------


def build_embedding_text(document: SearchDocument) -> str:
    """Concatenate document fields into a single string for embedding."""
    parts = [
        document.title,
        document.folder,
        document.tags,
        document.parent_topic,
        document.description,
        document.body[:EMBEDDING_BODY_CHARACTER_LIMIT],
    ]
    return " | ".join(part for part in parts if part)


def build_embedding_chunk_text(chunk: SearchChunk) -> str:
    """Concatenate chunk fields into a single string for embedding."""
    parts = [
        chunk.title,
        chunk.folder,
        chunk.tags,
        chunk.parent_topic,
        chunk.description,
        chunk.section,
        chunk.chunk_text,
    ]
    return " | ".join(part for part in parts if part)


# ---------------------------------------------------------------------------
# Vector serialization
# ---------------------------------------------------------------------------


def _normalize_vector(vector: list[float]) -> list[float]:
    """L2-normalize a vector so cosine similarity becomes a dot product."""
    magnitude = sum(x * x for x in vector) ** 0.5
    if magnitude == 0:
        return vector
    return [x / magnitude for x in vector]


def _serialize_vector(vector: list[float]) -> bytes:
    """Pack a float vector into compact bytes (little-endian float32)."""
    return struct.pack(f"<{len(vector)}f", *vector)


def _deserialize_vector(data: bytes) -> list[float]:
    """Unpack bytes back into a float vector."""
    count = len(data) // 4
    return list(struct.unpack(f"<{count}f", data))


# ---------------------------------------------------------------------------
# SQLite storage
# ---------------------------------------------------------------------------


def _connect(database_path: Path) -> sqlite3.Connection:
    """Open the database with catalog schema ensured."""
    from .catalog import connect as catalog_connect, ensure_catalog_schema

    connection = catalog_connect(database_path)
    ensure_catalog_schema(connection)
    return connection


def _create_embedding_table(connection: sqlite3.Connection) -> None:
    """Create the embedding storage table if it does not exist."""
    if _embedding_table_is_legacy(connection):
        connection.execute(f"DROP TABLE IF EXISTS {EMBEDDING_TABLE}")
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
    _ensure_embedding_metadata_columns(connection)


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    """Return column names for an existing SQLite table."""
    return {
        row["name"] for row in connection.execute(f"PRAGMA table_info({table_name})")
    }


def _ensure_embedding_metadata_columns(connection: sqlite3.Connection) -> None:
    """Add model/dimension columns to legacy embedding tables."""
    columns = _table_columns(connection, EMBEDDING_TABLE)
    if not columns:
        return
    if "model" not in columns:
        connection.execute(
            f"ALTER TABLE {EMBEDDING_TABLE} ADD COLUMN model TEXT NOT NULL DEFAULT ''"
        )
    if "dimensions" not in columns:
        connection.execute(
            f"ALTER TABLE {EMBEDDING_TABLE} ADD COLUMN dimensions INTEGER NOT NULL DEFAULT 0"
        )


def _embedding_table_is_legacy(connection: sqlite3.Connection) -> bool:
    """Return True when the derived embedding table predates chunk columns."""
    columns = _table_columns(connection, EMBEDDING_TABLE)
    if not columns:
        return False
    required = {"chunk_index", "tags", "section", "chunk_text", "text_hash"}
    return not required.issubset(columns)


def _load_stored_metadata(
    connection: sqlite3.Connection,
) -> dict[tuple[str, int], tuple[float, str, int, str]]:
    """Load chunk key → (mtime, model, dimensions, text_hash)."""
    try:
        _ensure_embedding_metadata_columns(connection)
        rows = connection.execute(
            f"SELECT path, chunk_index, mtime, model, dimensions, text_hash FROM {EMBEDDING_TABLE}"
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {
        (row["path"], int(row["chunk_index"])): (
            float(row["mtime"]),
            str(row["model"]),
            int(row["dimensions"]),
            str(row["text_hash"]),
        )
        for row in rows
    }


def _delete_by_paths(connection: sqlite3.Connection, paths: set[str]) -> None:
    """Remove embedding rows by path."""
    if not paths:
        return
    path_list = list(paths)
    placeholders = ",".join("?" * len(path_list))
    connection.execute(
        f"DELETE FROM {EMBEDDING_TABLE} WHERE path IN ({placeholders})", path_list
    )


def _delete_by_chunk_keys(
    connection: sqlite3.Connection,
    keys: set[tuple[str, int]],
) -> None:
    """Remove embedding rows by (path, chunk_index)."""
    if not keys:
        return
    key_list = list(keys)
    placeholders = ",".join("(?, ?)" for _ in key_list)
    params = [field for key in key_list for field in key]
    connection.execute(
        f"DELETE FROM {EMBEDDING_TABLE} WHERE (path, chunk_index) IN ({placeholders})",
        params,
    )


def delete_from_embedding_store(
    path: Path,
    *,
    database_path: Path | None = None,
) -> None:
    """Remove a single note from the embedding store."""
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


def _insert_embeddings(
    connection: sqlite3.Connection,
    chunks: list[SearchChunk],
    embeddings: list[list[float]],
    *,
    model: str,
    dimensions: int,
) -> None:
    """Insert pre-normalized embeddings into the store."""
    connection.executemany(
        f"""
        INSERT OR REPLACE INTO {EMBEDDING_TABLE}
            (path, chunk_index, url, title, folder, tags, description, section,
             chunk_text, embedding, mtime, model, dimensions, text_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                str(chunk.path),
                chunk.chunk_index,
                chunk.url,
                chunk.title,
                chunk.folder,
                chunk.tags,
                chunk.description,
                chunk.section,
                chunk.chunk_text,
                _serialize_vector(_normalize_vector(emb)),
                chunk.path.stat().st_mtime,
                model,
                dimensions,
                chunk.text_hash,
            )
            for chunk, emb in zip(chunks, embeddings)
        ],
    )


# ---------------------------------------------------------------------------
# Index refresh (incremental)
# ---------------------------------------------------------------------------


def refresh_embeddings(
    documents: list[SearchDocument],
    *,
    database_path: Path | None = None,
    config: dict[str, str] | None = None,
) -> None:
    """Incrementally update stored embeddings for new/modified/deleted documents.

    Skips unchanged documents to avoid unnecessary API calls.
    """
    if database_path is None:
        database_path = get_search_index_path()
    if config is None:
        config = get_llm_config()
    if not config:
        raise ValueError(
            "No LLM API key configured. Semantic search requires an embedding API."
        )
    model = embedding_model(config)
    dimensions = embedding_dimensions(config)

    connection = _connect(database_path)
    try:
        with connection:
            _create_embedding_table(connection)

        chunks = chunk_documents(documents)
        stored_metadata = _load_stored_metadata(connection)
        current_keys = {(str(chunk.path), chunk.chunk_index) for chunk in chunks}

        removed_keys = stored_metadata.keys() - current_keys
        changed_chunks: list[SearchChunk] = []
        for chunk in chunks:
            key = (str(chunk.path), chunk.chunk_index)
            if key not in stored_metadata:
                changed_chunks.append(chunk)
                continue
            stored_mtime, stored_model, stored_dimensions, stored_hash = (
                stored_metadata[key]
            )
            if (
                chunk.path.stat().st_mtime != stored_mtime
                or stored_model != model
                or stored_dimensions != dimensions
                or stored_hash != chunk.text_hash
            ):
                changed_chunks.append(chunk)

        if not removed_keys and not changed_chunks:
            return

        with connection:
            if removed_keys:
                _delete_by_chunk_keys(connection, removed_keys)

            if changed_chunks:
                texts = [build_embedding_chunk_text(chunk) for chunk in changed_chunks]
                embeddings = embed_texts(texts, config)
                _insert_embeddings(
                    connection,
                    changed_chunks,
                    embeddings,
                    model=model,
                    dimensions=dimensions,
                )
    finally:
        connection.close()


def rebuild_embeddings(
    documents: list[SearchDocument],
    *,
    database_path: Path | None = None,
    config: dict[str, str] | None = None,
) -> None:
    """Rebuild stored embeddings for all documents from scratch."""
    if database_path is None:
        database_path = get_search_index_path()
    if config is None:
        config = get_llm_config()
    if not config:
        raise ValueError(
            "No LLM API key configured. Semantic search requires an embedding API."
        )

    model = embedding_model(config)
    dimensions = embedding_dimensions(config)
    connection = _connect(database_path)
    try:
        with connection:
            connection.execute(f"DROP TABLE IF EXISTS {EMBEDDING_TABLE}")
            _create_embedding_table(connection)
            if documents:
                chunks = chunk_documents(documents)
                texts = [build_embedding_chunk_text(chunk) for chunk in chunks]
                embeddings = embed_texts(texts, config)
                _insert_embeddings(
                    connection,
                    chunks,
                    embeddings,
                    model=model,
                    dimensions=dimensions,
                )
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# Semantic search
# ---------------------------------------------------------------------------


def _cosine_similarities(
    query_vector: list[float],
    stored_vectors: list[list[float]],
) -> list[float]:
    """Compute cosine similarity via dot product (vectors are pre-normalized)."""
    try:
        import numpy as np

        query_array = np.array(query_vector, dtype=np.float32)
        stored_matrix = np.array(stored_vectors, dtype=np.float32)
        return (stored_matrix @ query_array).tolist()
    except ImportError:
        return [
            sum(
                query_value * stored_value
                for query_value, stored_value in zip(query_vector, stored_vector)
            )
            for stored_vector in stored_vectors
        ]


def semantic_search(
    query: str,
    *,
    database_path: Path | None = None,
    config: dict[str, str] | None = None,
    folder: str | None = None,
    tag: str | None = None,
    limit: int = 10,
    threshold: float = MIN_SIMILARITY_THRESHOLD,
    show_chunks: bool = False,
) -> list[EmbeddingMatch]:
    """Embed a query and return the most similar bookmark chunks."""
    if database_path is None:
        database_path = get_search_index_path()
    if config is None:
        config = get_llm_config()
    if not config:
        raise ValueError(
            "No LLM API key configured. Semantic search requires an embedding API."
        )
    model = embedding_model(config)
    dimensions = embedding_dimensions(config)

    query_embedding = _normalize_vector(embed_texts([query], config)[0])

    normalized_folder = folder.strip().strip("/") if folder else ""

    connection = _connect(database_path)
    try:
        with connection:
            _create_embedding_table(connection)
        where_clauses: list[str] = []
        params: list[str] = []
        if normalized_folder:
            where_clauses.append("(folder = ? OR folder LIKE ?)")
            params.extend([normalized_folder, f"{normalized_folder}/%"])
        if tag:
            where_clauses.append("tags LIKE ?")
            params.append(f"%{tag.strip().lower()}%")
        where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        rows = connection.execute(
            f"""
            SELECT path, chunk_index, url, title, folder, description, section,
                   chunk_text, embedding, model, dimensions
            FROM {EMBEDDING_TABLE}
            {where}
            """,
            params,
        ).fetchall()
    finally:
        connection.close()

    if not rows:
        return []

    mismatched = [
        row
        for row in rows
        if str(row["model"]) != model or int(row["dimensions"]) != dimensions
    ]
    if mismatched:
        stored_models = sorted({str(row["model"]) or "<unknown>" for row in mismatched})
        stored_dimensions = sorted({int(row["dimensions"]) for row in mismatched})
        raise ValueError(
            "Embedding store was built with a different model or dimensions "
            f"(stored model(s): {', '.join(stored_models)}; "
            f"stored dimension(s): {', '.join(str(d) for d in stored_dimensions)}; "
            f"expected: {model}/{dimensions}). Run bookmark-rebuild."
        )

    stored_vectors = [_deserialize_vector(row["embedding"]) for row in rows]
    similarities = _cosine_similarities(query_embedding, stored_vectors)

    scored = sorted(
        zip(rows, similarities),
        key=lambda pair: pair[1],
        reverse=True,
    )

    matches: list[EmbeddingMatch] = []
    seen_paths: set[Path] = set()
    for row, similarity in scored:
        if similarity < threshold:
            continue
        path = Path(str(row["path"]))
        if not show_chunks and path in seen_paths:
            continue
        seen_paths.add(path)
        chunk_text = str(row["chunk_text"] or "")
        matches.append(
            EmbeddingMatch(
                path=path,
                url=str(row["url"]),
                title=str(row["title"]),
                folder=str(row["folder"]),
                description=str(row["description"]),
                similarity=round(similarity, 4),
                snippet=chunk_text[:240],
                section=str(row["section"] or ""),
                chunk_index=int(row["chunk_index"] or 0),
            )
        )
        if len(matches) >= limit:
            break
    return matches
