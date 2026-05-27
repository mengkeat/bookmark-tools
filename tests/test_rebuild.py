from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from bookmark_tools.rebuild import rebuild_derived_state, main as rebuild_main
from bookmark_tools.search_index import search_index


class BookmarkRebuildTest(unittest.TestCase):
    def _write_note(
        self,
        bookmarks_dir: Path,
        relative_path: str,
        *,
        title: str = "Python Search",
        url: str = "https://example.com/python-search",
        body: str = "Summary: Python full text search with sqlite.",
    ) -> Path:
        note_path = bookmarks_dir / relative_path
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(
            "\n".join(
                [
                    "---",
                    f"url: {url}",
                    f"title: {title}",
                    "tags: [python, search]",
                    "parent_topic: Python",
                    "description: Search notes",
                    "---",
                    "",
                    body,
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return note_path

    def test_rebuild_restores_search_index_after_database_delete(self) -> None:
        """Deleting the search DB then rebuilding restores keyword search."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            database_path = Path(tmp) / "Meta" / "bookmark-search.sqlite3"
            self._write_note(bookmarks_dir, "Development/python-search.md")

            result = rebuild_derived_state(
                bookmarks_dir=bookmarks_dir,
                database_path=database_path,
                include_embeddings=False,
            )
            self.assertTrue(database_path.exists())
            database_path.unlink()
            self.assertFalse(database_path.exists())

            result = rebuild_derived_state(
                bookmarks_dir=bookmarks_dir,
                database_path=database_path,
                include_embeddings=False,
            )
            results = search_index("python", database_path=database_path)

        self.assertTrue(result.search_rebuilt)
        self.assertFalse(result.embeddings_rebuilt)
        self.assertEqual(result.document_count, 1)
        self.assertEqual([r.title for r in results], ["Python Search"])

    @patch("bookmark_tools.rebuild.get_llm_config", return_value=None)
    def test_rebuild_skips_embeddings_without_api_config(self, _mock: object) -> None:
        """Embedding rebuild is skipped clearly when no API key is configured."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            database_path = Path(tmp) / "Meta" / "bookmark-search.sqlite3"
            self._write_note(bookmarks_dir, "Development/python-search.md")

            result = rebuild_derived_state(
                bookmarks_dir=bookmarks_dir,
                database_path=database_path,
            )

        self.assertTrue(result.search_rebuilt)
        self.assertFalse(result.embeddings_rebuilt)
        self.assertIn("No LLM API key", result.embeddings_skipped_reason)

    @patch("bookmark_tools.rebuild.get_llm_config", return_value=None)
    def test_rebuild_main_json_output(self, _mock: object) -> None:
        """The CLI can emit stable JSON for scripts."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            database_path = Path(tmp) / "Meta" / "bookmark-search.sqlite3"
            self._write_note(bookmarks_dir, "Development/python-search.md")
            env = {
                "BOOKMARKS_DIR": str(bookmarks_dir),
                "BOOKMARK_SEARCH_INDEX": str(database_path),
            }
            with patch.dict(os.environ, env, clear=False):
                with patch("builtins.print") as mock_print:
                    exit_code = rebuild_main(["--json"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(mock_print.call_args.args[0])
        self.assertEqual(payload["document_count"], 1)
        self.assertTrue(payload["search_rebuilt"])
        self.assertFalse(payload["embeddings_rebuilt"])

    @patch("bookmark_tools.classify.get_llm_config", return_value=None)
    def test_rebuild_catalog_flag_rebuilds_all_tables(self, _mock: object) -> None:
        """--catalog rebuilds the unified catalog with bookmarks table."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            database_path = Path(tmp) / "Meta" / "bookmark-search.sqlite3"
            self._write_note(bookmarks_dir, "Development/python-search.md")

            result = rebuild_derived_state(
                bookmarks_dir=bookmarks_dir,
                database_path=database_path,
                include_embeddings=False,
                include_catalog=True,
            )

            self.assertTrue(result.catalog_rebuilt)
            self.assertTrue(result.search_rebuilt)
            self.assertEqual(result.document_count, 1)

            # Verify bookmarks table is populated
            from bookmark_tools.catalog import (
                BOOKMARKS_TABLE,
                connect as catalog_connect,
            )

            conn = catalog_connect(database_path)
            try:
                row = conn.execute(
                    f"SELECT title FROM {BOOKMARKS_TABLE}"
                ).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row["title"], "Python Search")
            finally:
                conn.close()

    @patch("bookmark_tools.classify.get_llm_config", return_value=None)
    def test_rebuild_catalog_can_be_deleted_and_restored(self, _mock: object) -> None:
        """Full catalog can be deleted and rebuilt from Markdown."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            database_path = Path(tmp) / "Meta" / "bookmark-search.sqlite3"
            self._write_note(bookmarks_dir, "Development/python-search.md")

            # First build
            rebuild_derived_state(
                bookmarks_dir=bookmarks_dir,
                database_path=database_path,
                include_embeddings=False,
                include_catalog=True,
            )

            # Delete and rebuild
            database_path.unlink()
            result = rebuild_derived_state(
                bookmarks_dir=bookmarks_dir,
                database_path=database_path,
                include_embeddings=False,
                include_catalog=True,
            )

            results = search_index("python", database_path=database_path)
            self.assertTrue(result.catalog_rebuilt)
            self.assertEqual(len(results), 1)


if __name__ == "__main__":
    unittest.main()
