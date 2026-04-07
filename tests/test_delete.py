from __future__ import annotations

import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from bookmark_tools.delete import delete_bookmark, find_note
from bookmark_tools.search_index import MTIME_TABLE, SEARCH_TABLE


NOTE_FRONTMATTER = """\
---
title: Sample Article
url: https://example.com/sample
type: article
tags: [python]
created: 2025-01-15
language: en
parent_topic: Python
description: A sample article
---

Summary:
Sample summary.
"""


def _setup_vault(tmp: str) -> tuple[Path, Path]:
    """Create a minimal vault with one bookmark note."""
    bookmarks_dir = Path(tmp) / "Bookmarks"
    folder = bookmarks_dir / "Development" / "Python"
    folder.mkdir(parents=True)
    note = folder / "sample-article.md"
    note.write_text(NOTE_FRONTMATTER, encoding="utf-8")
    return bookmarks_dir, note


def _setup_search_db(database_path: Path, note_path: Path) -> None:
    """Populate a search index and embedding store with one row."""
    conn = sqlite3.connect(database_path)
    conn.execute(
        f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS {SEARCH_TABLE} USING fts5(
            path UNINDEXED, url UNINDEXED, title, folder, tags,
            related, parent_topic, description, body,
            tokenize='porter unicode61'
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {MTIME_TABLE} (
            path TEXT PRIMARY KEY, mtime REAL NOT NULL
        )
        """
    )
    conn.execute(
        f"""
        INSERT INTO {SEARCH_TABLE}
            (path, url, title, folder, tags, related, parent_topic, description, body)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(note_path),
            "https://example.com/sample",
            "Sample Article",
            "Development/Python",
            "python",
            "",
            "Python",
            "A sample article",
            "Sample summary.",
        ),
    )
    conn.execute(
        f"INSERT INTO {MTIME_TABLE} (path, mtime) VALUES (?, ?)",
        (str(note_path), 0.0),
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS embedding_store (
            path TEXT PRIMARY KEY, url TEXT, title TEXT,
            folder TEXT, description TEXT, embedding BLOB, mtime REAL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO embedding_store (path, url, title, folder, description, embedding, mtime)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (str(note_path), "https://example.com/sample", "Sample Article",
         "Development/Python", "A sample article", b"\x00" * 16, 0.0),
    )
    conn.commit()
    conn.close()


class FindNoteTest(unittest.TestCase):
    def test_find_by_url(self) -> None:
        with TemporaryDirectory() as tmp:
            bookmarks_dir, note = _setup_vault(tmp)
            result = find_note(
                "https://example.com/sample", bookmarks_dir=bookmarks_dir
            )
        self.assertEqual(result, note)

    def test_find_by_url_not_found(self) -> None:
        with TemporaryDirectory() as tmp:
            bookmarks_dir, _ = _setup_vault(tmp)
            result = find_note(
                "https://example.com/missing", bookmarks_dir=bookmarks_dir
            )
        self.assertIsNone(result)

    def test_find_by_relative_path(self) -> None:
        with TemporaryDirectory() as tmp:
            bookmarks_dir, note = _setup_vault(tmp)
            result = find_note(
                "Development/Python/sample-article.md",
                bookmarks_dir=bookmarks_dir,
            )
        self.assertEqual(result, note)

    def test_find_by_absolute_path(self) -> None:
        with TemporaryDirectory() as tmp:
            bookmarks_dir, note = _setup_vault(tmp)
            result = find_note(str(note), bookmarks_dir=bookmarks_dir)
        self.assertEqual(result, note)

    def test_find_by_absolute_path_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            bookmarks_dir, _ = _setup_vault(tmp)
            result = find_note("/nonexistent/file.md", bookmarks_dir=bookmarks_dir)
        self.assertIsNone(result)


class DeleteBookmarkTest(unittest.TestCase):
    def test_delete_removes_file(self) -> None:
        with TemporaryDirectory() as tmp:
            bookmarks_dir, note = _setup_vault(tmp)
            db_path = Path(tmp) / "search.sqlite3"
            _setup_search_db(db_path, note)

            result = delete_bookmark(
                "https://example.com/sample",
                bookmarks_dir=bookmarks_dir,
                database_path=db_path,
            )

            self.assertEqual(result, note)
            self.assertFalse(note.exists())

    def test_delete_cleans_search_index(self) -> None:
        with TemporaryDirectory() as tmp:
            bookmarks_dir, note = _setup_vault(tmp)
            db_path = Path(tmp) / "search.sqlite3"
            _setup_search_db(db_path, note)

            delete_bookmark(
                "https://example.com/sample",
                bookmarks_dir=bookmarks_dir,
                database_path=db_path,
            )

            conn = sqlite3.connect(db_path)
            fts_count = conn.execute(
                f"SELECT COUNT(*) FROM {SEARCH_TABLE}"
            ).fetchone()[0]
            mtime_count = conn.execute(
                f"SELECT COUNT(*) FROM {MTIME_TABLE}"
            ).fetchone()[0]
            emb_count = conn.execute(
                "SELECT COUNT(*) FROM embedding_store"
            ).fetchone()[0]
            conn.close()

            self.assertEqual(fts_count, 0)
            self.assertEqual(mtime_count, 0)
            self.assertEqual(emb_count, 0)

    def test_delete_removes_empty_parent_dirs(self) -> None:
        with TemporaryDirectory() as tmp:
            bookmarks_dir, note = _setup_vault(tmp)
            db_path = Path(tmp) / "search.sqlite3"

            delete_bookmark(
                "https://example.com/sample",
                bookmarks_dir=bookmarks_dir,
                database_path=db_path,
            )

            # The Python subfolder should be removed since it's now empty
            self.assertFalse((bookmarks_dir / "Development" / "Python").exists())

    def test_delete_dry_run_preserves_file(self) -> None:
        with TemporaryDirectory() as tmp:
            bookmarks_dir, note = _setup_vault(tmp)
            db_path = Path(tmp) / "search.sqlite3"

            result = delete_bookmark(
                "https://example.com/sample",
                bookmarks_dir=bookmarks_dir,
                database_path=db_path,
                dry_run=True,
            )

            self.assertEqual(result, note)
            self.assertTrue(note.exists())

    def test_delete_returns_none_for_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            bookmarks_dir, _ = _setup_vault(tmp)
            db_path = Path(tmp) / "search.sqlite3"

            result = delete_bookmark(
                "https://example.com/missing",
                bookmarks_dir=bookmarks_dir,
                database_path=db_path,
            )

            self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
