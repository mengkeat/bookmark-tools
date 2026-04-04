from __future__ import annotations

import json
import sqlite3
import struct
import urllib.error
import urllib.request
from dataclasses import dataclass

from .http_retry import urlopen_with_retry
from pathlib import Path

from .classify import get_llm_config
from .paths import DEFAULT_TIMEOUT, get_search_index_path
from .search_documents import SearchDocument

EMBEDDING_TABLE = "embedding_store"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 256
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


# ---------------------------------------------------------------------------
# Embedding API
# ---------------------------------------------------------------------------


def _call_embedding_api(
    texts: list[str],
    config: dict[str, str],
) -> list[list[float]]:
    """Call the OpenAI-compatible embeddings endpoint and return vectors."""
    payload = {
        "model": config.get("embedding_model", EMBEDDING_MODEL),
        "input": texts,
        "dimensions": EMBEDDING_DIMENSIONS,
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
    with urlopen_with_retry(request, timeout=DEFAULT_TIMEOUT) as response:
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
    """Open the database with row access enabled."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def _create_embedding_table(connection: sqlite3.Connection) -> None:
    """Create the embedding storage table if it does not exist."""
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {EMBEDDING_TABLE} (
            path TEXT PRIMARY KEY,
            url TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            folder TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            embedding BLOB NOT NULL,
            mtime REAL NOT NULL
        )
        """
    )


def _load_stored_mtimes(connection: sqlite3.Connection) -> dict[str, float]:
    """Load path → mtime from the embedding table."""
    try:
        rows = connection.execute(
            f"SELECT path, mtime FROM {EMBEDDING_TABLE}"
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {row["path"]: float(row["mtime"]) for row in rows}


def _delete_by_paths(connection: sqlite3.Connection, paths: set[str]) -> None:
    """Remove embedding rows by path."""
    for path in paths:
        connection.execute(
            f"DELETE FROM {EMBEDDING_TABLE} WHERE path = ?", (path,)
        )


def _insert_embeddings(
    connection: sqlite3.Connection,
    documents: list[SearchDocument],
    embeddings: list[list[float]],
) -> None:
    """Insert pre-normalized embeddings into the store."""
    connection.executemany(
        f"""
        INSERT OR REPLACE INTO {EMBEDDING_TABLE}
            (path, url, title, folder, description, embedding, mtime)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                str(doc.path),
                doc.url,
                doc.title,
                doc.folder,
                doc.description,
                _serialize_vector(_normalize_vector(emb)),
                doc.path.stat().st_mtime,
            )
            for doc, emb in zip(documents, embeddings)
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

    connection = _connect(database_path)
    try:
        with connection:
            _create_embedding_table(connection)

        stored_mtimes = _load_stored_mtimes(connection)
        current_paths = {str(doc.path) for doc in documents}

        removed_paths = stored_mtimes.keys() - current_paths
        changed_documents: list[SearchDocument] = []
        for document in documents:
            path_str = str(document.path)
            if path_str not in stored_mtimes:
                changed_documents.append(document)
            elif document.path.stat().st_mtime != stored_mtimes[path_str]:
                changed_documents.append(document)

        if not removed_paths and not changed_documents:
            return

        with connection:
            if removed_paths:
                _delete_by_paths(connection, removed_paths)

            if changed_documents:
                texts = [build_embedding_text(doc) for doc in changed_documents]
                embeddings = embed_texts(texts, config)
                _insert_embeddings(connection, changed_documents, embeddings)
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
            sum(query_value * stored_value for query_value, stored_value in zip(query_vector, stored_vector))
            for stored_vector in stored_vectors
        ]


def semantic_search(
    query: str,
    *,
    database_path: Path | None = None,
    config: dict[str, str] | None = None,
    folder: str | None = None,
    limit: int = 10,
    threshold: float = MIN_SIMILARITY_THRESHOLD,
) -> list[EmbeddingMatch]:
    """Embed a query and return the most similar bookmarks by cosine similarity."""
    if database_path is None:
        database_path = get_search_index_path()
    if config is None:
        config = get_llm_config()
    if not config:
        raise ValueError(
            "No LLM API key configured. Semantic search requires an embedding API."
        )

    query_embedding = _normalize_vector(embed_texts([query], config)[0])

    normalized_folder = folder.strip().strip("/") if folder else ""

    connection = _connect(database_path)
    try:
        where = ""
        params: list[str] = []
        if normalized_folder:
            where = "WHERE folder = ? OR folder LIKE ?"
            params = [normalized_folder, f"{normalized_folder}/%"]

        rows = connection.execute(
            f"""
            SELECT path, url, title, folder, description, embedding
            FROM {EMBEDDING_TABLE}
            {where}
            """,
            params,
        ).fetchall()
    finally:
        connection.close()

    if not rows:
        return []

    stored_vectors = [_deserialize_vector(row["embedding"]) for row in rows]
    similarities = _cosine_similarities(query_embedding, stored_vectors)

    scored = sorted(
        zip(rows, similarities),
        key=lambda pair: pair[1],
        reverse=True,
    )

    return [
        EmbeddingMatch(
            path=Path(str(row["path"])),
            url=str(row["url"]),
            title=str(row["title"]),
            folder=str(row["folder"]),
            description=str(row["description"]),
            similarity=round(similarity, 4),
        )
        for row, similarity in scored[:limit]
        if similarity >= threshold
    ]
