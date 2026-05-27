"""Tests for the unified SQLite catalog module."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from bookmark_tools.catalog import (
    BOOKMARKS_TABLE,
    CATALOG_SCHEMA_VERSION,
    CHUNKS_TABLE,
    EDGES_TABLE,
    EMBEDDING_TABLE,
    FETCH_LOG_TABLE,
    JOBS_TABLE,
    META_TABLE,
    MTIME_TABLE,
    SEARCH_TABLE,
    CatalogInfo,
    CatalogResult,
    catalog_tables_exist,
    connect,
    delete_from_catalog,
    ensure_catalog_schema,
    get_catalog_info,
    get_catalog_version,
    populate_bookmarks,
    rebuild_catalog,
    rebuild_catalog_schema,
    table_names,
    upsert_bookmark,
)
from bookmark_tools.search_index import search_index


def _write_note(
    bookmarks_dir: Path,
    relative_path: str,
    *,
    title: str = "Test Page",
    url: str = "https://example.com/test",
    tags: str = "[test, catalog]",
    extra_frontmatter: str = "",
    body: str = "Summary: A test page.",
) -> Path:
    """Write a minimal bookmark note to the vault."""
    import hashlib

    from bookmark_tools.url_normalize import normalize_url

    note_path = bookmarks_dir / relative_path
    note_path.parent.mkdir(parents=True, exist_ok=True)
    bookmark_id = hashlib.sha256(normalize_url(url).encode()).hexdigest()
    frontmatter = "\n".join(
        line
        for line in [
            "---",
            "schema_version: 1",
            f"id: {bookmark_id}",
            f"url: {url}",
            f"title: {title}",
            f"tags: {tags}",
            "parent_topic: Testing",
            "description: Test description",
            extra_frontmatter,
            "---",
        ]
        if line
    )
    note_path.write_text(
        f"{frontmatter}\n\n{body}\n",
        encoding="utf-8",
    )
    return note_path


def _write_non_bookmark(
    bookmarks_dir: Path,
    relative_path: str,
    *,
    body: str = "Just a note.",
) -> Path:
    """Write a non-bookmark Markdown file (no url field)."""
    note_path = bookmarks_dir / relative_path
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(
        f"---\ntitle: Non-bookmark\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return note_path


class CatalogConnectionTest(unittest.TestCase):
    """Test catalog connection management."""

    def test_connect_creates_parent_directories(self) -> None:
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "sub" / "dir" / "catalog.sqlite3"
            conn = connect(db_path)
            conn.close()
            self.assertTrue(db_path.exists())

    def test_connect_enables_wal(self) -> None:
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "catalog.sqlite3"
            conn = connect(db_path)
            try:
                row = conn.execute("PRAGMA journal_mode").fetchone()
                self.assertEqual(str(row[0]), "wal")
            finally:
                conn.close()


class CatalogSchemaTest(unittest.TestCase):
    """Test catalog schema creation and versioning."""

    def test_ensure_schema_creates_all_tables(self) -> None:
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "catalog.sqlite3"
            conn = connect(db_path)
            try:
                ensure_catalog_schema(conn)
                tables = table_names(conn)
                self.assertIn(META_TABLE, tables)
                self.assertIn(BOOKMARKS_TABLE, tables)
                self.assertIn(FETCH_LOG_TABLE, tables)
                self.assertIn(CHUNKS_TABLE, tables)
                self.assertIn(EDGES_TABLE, tables)
                self.assertIn(JOBS_TABLE, tables)
                self.assertIn(SEARCH_TABLE, tables)
                self.assertIn(MTIME_TABLE, tables)
                self.assertIn(EMBEDDING_TABLE, tables)
            finally:
                conn.close()

    def test_ensure_schema_is_idempotent(self) -> None:
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "catalog.sqlite3"
            conn = connect(db_path)
            try:
                ensure_catalog_schema(conn)
                ensure_catalog_schema(conn)  # Should not raise
                version = get_catalog_version(conn)
                self.assertEqual(version, CATALOG_SCHEMA_VERSION)
            finally:
                conn.close()

    def test_rebuild_schema_drops_and_recreates(self) -> None:
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "catalog.sqlite3"
            conn = connect(db_path)
            try:
                ensure_catalog_schema(conn)
                # Insert a row
                conn.execute(
                    f"INSERT INTO {BOOKMARKS_TABLE} (id, note_path, url, metadata_json) "
                    f"VALUES ('test', '/fake.md', 'https://example.com', '{{}}')"
                )
                conn.commit()
                count = conn.execute(
                    f"SELECT COUNT(*) FROM {BOOKMARKS_TABLE}"
                ).fetchone()[0]
                self.assertEqual(count, 1)

                # Rebuild
                rebuild_catalog_schema(conn)
                count = conn.execute(
                    f"SELECT COUNT(*) FROM {BOOKMARKS_TABLE}"
                ).fetchone()[0]
                self.assertEqual(count, 0)
                version = get_catalog_version(conn)
                self.assertEqual(version, CATALOG_SCHEMA_VERSION)
            finally:
                conn.close()

    def test_get_version_returns_zero_for_empty_db(self) -> None:
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "catalog.sqlite3"
            conn = connect(db_path)
            try:
                self.assertEqual(get_catalog_version(conn), 0)
            finally:
                conn.close()

    def test_catalog_tables_exist_checks_core_tables(self) -> None:
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "catalog.sqlite3"
            conn = connect(db_path)
            try:
                self.assertFalse(catalog_tables_exist(conn))
                ensure_catalog_schema(conn)
                self.assertTrue(catalog_tables_exist(conn))
            finally:
                conn.close()

    def test_bookmarks_table_has_indexes(self) -> None:
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "catalog.sqlite3"
            conn = connect(db_path)
            try:
                ensure_catalog_schema(conn)
                indexes = {
                    str(row[0])
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='index'"
                    )
                }
                self.assertIn("idx_bookmarks_url", indexes)
                self.assertIn("idx_bookmarks_folder", indexes)
                self.assertIn("idx_bookmarks_domain", indexes)
            finally:
                conn.close()

    def test_edges_table_has_unique_constraint(self) -> None:
        """The UNIQUE constraint on (from_id, to_id, edge_type, source) is enforced."""
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "catalog.sqlite3"
            conn = connect(db_path)
            try:
                ensure_catalog_schema(conn)
                conn.execute(
                    f"INSERT INTO {EDGES_TABLE} (from_id, to_id, to_kind, edge_type, source, created_at) "
                    f"VALUES ('a', 'b', 'tag', 'has_tag', 'frontmatter', '2026-01-01')"
                )
                conn.commit()
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(
                        f"INSERT INTO {EDGES_TABLE} (from_id, to_id, to_kind, edge_type, source, created_at) "
                        f"VALUES ('a', 'b', 'tag', 'has_tag', 'frontmatter', '2026-01-02')"
                    )
            finally:
                conn.close()


class PopulateBookmarksTest(unittest.TestCase):
    """Test bookmark table population from vault notes."""

    def test_populate_inserts_bookmark_notes(self) -> None:
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            db_path = Path(tmp) / "catalog.sqlite3"
            _write_note(bookmarks_dir, "Testing/test.md")

            conn = connect(db_path)
            try:
                ensure_catalog_schema(conn)
                count = populate_bookmarks(conn, bookmarks_dir)
                self.assertEqual(count, 1)

                row = conn.execute(f"SELECT * FROM {BOOKMARKS_TABLE}").fetchone()
                self.assertEqual(row["title"], "Test Page")
                self.assertEqual(row["url"], "https://example.com/test")
                self.assertEqual(row["folder"], "Testing")
            finally:
                conn.close()

    def test_populate_skips_non_bookmark_notes(self) -> None:
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            db_path = Path(tmp) / "catalog.sqlite3"
            _write_note(bookmarks_dir, "Testing/bookmark.md")
            _write_non_bookmark(bookmarks_dir, "Testing/readme.md")

            conn = connect(db_path)
            try:
                ensure_catalog_schema(conn)
                count = populate_bookmarks(conn, bookmarks_dir)
                self.assertEqual(count, 1)
            finally:
                conn.close()

    def test_populate_stores_metadata_json(self) -> None:
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            db_path = Path(tmp) / "catalog.sqlite3"
            _write_note(
                bookmarks_dir,
                "Testing/test.md",
                extra_frontmatter="domain: example.com",
            )

            conn = connect(db_path)
            try:
                ensure_catalog_schema(conn)
                populate_bookmarks(conn, bookmarks_dir)
                row = conn.execute(
                    f"SELECT metadata_json FROM {BOOKMARKS_TABLE}"
                ).fetchone()
                metadata = json.loads(row["metadata_json"])
                self.assertEqual(metadata["domain"], "example.com")
            finally:
                conn.close()

    def test_populate_clears_existing_rows(self) -> None:
        """Each populate call clears old rows first."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            db_path = Path(tmp) / "catalog.sqlite3"
            _write_note(bookmarks_dir, "Testing/a.md", url="https://a.com")
            _write_note(bookmarks_dir, "Testing/b.md", url="https://b.com")

            conn = connect(db_path)
            try:
                ensure_catalog_schema(conn)
                populate_bookmarks(conn, bookmarks_dir)
                self.assertEqual(
                    conn.execute(f"SELECT COUNT(*) FROM {BOOKMARKS_TABLE}").fetchone()[
                        0
                    ],
                    2,
                )
                # Remove one note and re-populate
                (bookmarks_dir / "Testing" / "b.md").unlink()
                populate_bookmarks(conn, bookmarks_dir)
                self.assertEqual(
                    conn.execute(f"SELECT COUNT(*) FROM {BOOKMARKS_TABLE}").fetchone()[
                        0
                    ],
                    1,
                )
            finally:
                conn.close()


class UpsertBookmarkTest(unittest.TestCase):
    """Test single-bookmark upsert operations."""

    def test_upsert_inserts_new_row(self) -> None:
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            db_path = Path(tmp) / "catalog.sqlite3"
            note_path = _write_note(bookmarks_dir, "Testing/test.md")

            conn = connect(db_path)
            try:
                ensure_catalog_schema(conn)
                upsert_bookmark(conn, note_path, bookmarks_dir)
                count = conn.execute(
                    f"SELECT COUNT(*) FROM {BOOKMARKS_TABLE}"
                ).fetchone()[0]
                self.assertEqual(count, 1)
            finally:
                conn.close()

    def test_upsert_updates_existing_row(self) -> None:
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            db_path = Path(tmp) / "catalog.sqlite3"
            note_path = _write_note(bookmarks_dir, "Testing/test.md", title="Original")

            conn = connect(db_path)
            try:
                ensure_catalog_schema(conn)
                upsert_bookmark(conn, note_path, bookmarks_dir)
                row = conn.execute(f"SELECT title FROM {BOOKMARKS_TABLE}").fetchone()
                self.assertEqual(row["title"], "Original")

                # Update the note
                note_path.write_text(
                    note_path.read_text().replace("Original", "Updated"),
                    encoding="utf-8",
                )
                upsert_bookmark(conn, note_path, bookmarks_dir)
                row = conn.execute(f"SELECT title FROM {BOOKMARKS_TABLE}").fetchone()
                self.assertEqual(row["title"], "Updated")
                # Still only one row
                count = conn.execute(
                    f"SELECT COUNT(*) FROM {BOOKMARKS_TABLE}"
                ).fetchone()[0]
                self.assertEqual(count, 1)
            finally:
                conn.close()

    def test_upsert_skips_non_bookmark(self) -> None:
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            db_path = Path(tmp) / "catalog.sqlite3"
            note_path = _write_non_bookmark(bookmarks_dir, "Testing/readme.md")

            conn = connect(db_path)
            try:
                ensure_catalog_schema(conn)
                upsert_bookmark(conn, note_path, bookmarks_dir)
                count = conn.execute(
                    f"SELECT COUNT(*) FROM {BOOKMARKS_TABLE}"
                ).fetchone()[0]
                self.assertEqual(count, 0)
            finally:
                conn.close()


class DeleteFromCatalogTest(unittest.TestCase):
    """Test catalog row deletion."""

    def test_delete_removes_from_bookmarks_table(self) -> None:
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            db_path = Path(tmp) / "catalog.sqlite3"
            note_path = _write_note(bookmarks_dir, "Testing/test.md")

            conn = connect(db_path)
            try:
                ensure_catalog_schema(conn)
                populate_bookmarks(conn, bookmarks_dir)
                self.assertEqual(
                    conn.execute(f"SELECT COUNT(*) FROM {BOOKMARKS_TABLE}").fetchone()[
                        0
                    ],
                    1,
                )
            finally:
                conn.close()

            delete_from_catalog(note_path, database_path=db_path)

            conn = connect(db_path)
            try:
                self.assertEqual(
                    conn.execute(f"SELECT COUNT(*) FROM {BOOKMARKS_TABLE}").fetchone()[
                        0
                    ],
                    0,
                )
            finally:
                conn.close()

    def test_delete_noop_when_db_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "nonexistent.sqlite3"
            # Should not raise
            delete_from_catalog(Path("/fake.md"), database_path=db_path)


class RebuildCatalogTest(unittest.TestCase):
    """Test full catalog rebuild."""

    @patch("bookmark_tools.classify.get_llm_config", return_value=None)
    def test_rebuild_creates_catalog_and_fts(self, _mock: object) -> None:
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            db_path = Path(tmp) / "catalog.sqlite3"
            _write_note(bookmarks_dir, "Testing/test.md", title="SQLite Guide")

            result = rebuild_catalog(
                bookmarks_dir=bookmarks_dir,
                database_path=db_path,
                include_embeddings=False,
            )

            self.assertIsInstance(result, CatalogResult)
            self.assertTrue(result.fts_rebuilt)
            self.assertFalse(result.embeddings_rebuilt)
            self.assertEqual(result.bookmark_count, 1)

            # Verify bookmarks table
            conn = connect(db_path)
            try:
                row = conn.execute(f"SELECT title FROM {BOOKMARKS_TABLE}").fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row["title"], "SQLite Guide")
            finally:
                conn.close()

            # Verify FTS works
            results = search_index("sqlite", database_path=db_path)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].title, "SQLite Guide")

    @patch("bookmark_tools.classify.get_llm_config", return_value=None)
    def test_rebuild_can_be_deleted_and_restored(self, _mock: object) -> None:
        """The catalog can be deleted and fully rebuilt from Markdown."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            db_path = Path(tmp) / "catalog.sqlite3"
            _write_note(bookmarks_dir, "Testing/test.md", title="Python Search")

            # First rebuild
            rebuild_catalog(
                bookmarks_dir=bookmarks_dir,
                database_path=db_path,
                include_embeddings=False,
            )
            self.assertTrue(db_path.exists())

            # Delete and rebuild
            db_path.unlink()
            self.assertFalse(db_path.exists())

            result = rebuild_catalog(
                bookmarks_dir=bookmarks_dir,
                database_path=db_path,
                include_embeddings=False,
            )

            results = search_index("python", database_path=db_path)
            self.assertEqual(result.bookmark_count, 1)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].title, "Python Search")

    def test_rebuild_skips_embeddings_without_api_key(self) -> None:
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            db_path = Path(tmp) / "catalog.sqlite3"
            _write_note(bookmarks_dir, "Testing/test.md")

            result = rebuild_catalog(
                bookmarks_dir=bookmarks_dir,
                database_path=db_path,
                include_embeddings=True,
            )

            self.assertFalse(result.embeddings_rebuilt)
            self.assertIn("No LLM API key", result.embeddings_skipped_reason)


class GetCatalogInfoTest(unittest.TestCase):
    """Test catalog introspection."""

    def test_info_returns_zero_when_db_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "missing.sqlite3"
            info = get_catalog_info(db_path)
            self.assertFalse(info.exists)
            self.assertEqual(info.schema_version, 0)
            self.assertEqual(info.bookmark_count, 0)

    @patch("bookmark_tools.classify.get_llm_config", return_value=None)
    def test_info_returns_counts_after_rebuild(self, _mock: object) -> None:
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            db_path = Path(tmp) / "catalog.sqlite3"
            _write_note(bookmarks_dir, "Testing/a.md", url="https://a.com")
            _write_note(bookmarks_dir, "Testing/b.md", url="https://b.com")

            rebuild_catalog(
                bookmarks_dir=bookmarks_dir,
                database_path=db_path,
                include_embeddings=False,
            )

            info = get_catalog_info(db_path)
            self.assertTrue(info.exists)
            self.assertEqual(info.schema_version, CATALOG_SCHEMA_VERSION)
            self.assertEqual(info.bookmark_count, 2)
            self.assertEqual(info.fts_count, 2)
            self.assertEqual(info.embedding_count, 0)

    def test_info_to_dict(self) -> None:
        info = CatalogInfo(
            database_path=Path("/tmp/test.sqlite3"),
            exists=True,
            schema_version=1,
            bookmark_count=5,
            fts_count=5,
            embedding_count=3,
            fetch_log_count=0,
            chunk_count=0,
            edge_count=0,
            job_count=0,
        )
        d = info.to_dict()
        self.assertEqual(d["schema_version"], 1)
        self.assertEqual(d["bookmark_count"], 5)
        self.assertEqual(d["database_path"], "/tmp/test.sqlite3")


class CatalogResultTest(unittest.TestCase):
    """Test CatalogResult serialization."""

    def test_to_dict(self) -> None:
        result = CatalogResult(
            database_path=Path("/tmp/test.sqlite3"),
            bookmark_count=10,
            fts_rebuilt=True,
            embeddings_rebuilt=True,
            embeddings_skipped_reason="",
        )
        d = result.to_dict()
        self.assertTrue(d["fts_rebuilt"])
        self.assertTrue(d["embeddings_rebuilt"])
        self.assertEqual(d["bookmark_count"], 10)


class CatalogSchemaUpgradeTest(unittest.TestCase):
    """Test catalog schema upgrade paths."""

    def test_empty_db_upgrades_to_current_version(self) -> None:
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "catalog.sqlite3"
            conn = connect(db_path)
            try:
                self.assertEqual(get_catalog_version(conn), 0)
                ensure_catalog_schema(conn)
                self.assertEqual(get_catalog_version(conn), CATALOG_SCHEMA_VERSION)
            finally:
                conn.close()

    def test_existing_search_db_gets_catalog_tables(self) -> None:
        """A DB with only FTS tables gets catalog tables added."""
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "catalog.sqlite3"
            conn = connect(db_path)
            try:
                # Create only FTS tables (simulating pre-catalog DB)
                conn.execute(
                    f"CREATE TABLE {MTIME_TABLE} (path TEXT PRIMARY KEY, mtime REAL NOT NULL)"
                )
                conn.execute(
                    f"CREATE VIRTUAL TABLE {SEARCH_TABLE} USING fts5("
                    f"path UNINDEXED, url UNINDEXED, title, folder, tags, "
                    f"related, parent_topic, description, body, "
                    f"tokenize='porter unicode61')"
                )
                conn.commit()

                self.assertFalse(catalog_tables_exist(conn))
                ensure_catalog_schema(conn)
                self.assertTrue(catalog_tables_exist(conn))
                self.assertEqual(get_catalog_version(conn), CATALOG_SCHEMA_VERSION)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
