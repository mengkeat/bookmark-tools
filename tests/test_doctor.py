from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from bookmark_tools.doctor import run_doctor, main as doctor_main
from bookmark_tools.embeddings import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_TABLE,
    _serialize_vector,
)
from bookmark_tools.note_schema import stable_bookmark_id
from bookmark_tools.search_index import search_index


class BookmarkDoctorTest(unittest.TestCase):
    def _write_note(
        self,
        bookmarks_dir: Path,
        relative_path: str,
        *,
        url: str = "https://example.com/page",
        title: str = "Example Page",
        archive_path: str = "",
        body: str = "Summary: Example page.",
    ) -> Path:
        note_path = bookmarks_dir / relative_path
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(
            "\n".join(
                [
                    "---",
                    "schema_version: 1",
                    f"id: {stable_bookmark_id(url)}",
                    f"title: {title}",
                    f"url: {url}",
                    f"final_url: {url}",
                    f"canonical_url: {url}",
                    "domain: example.com",
                    "created: 2026-05-24",
                    "last_updated: 2026-05-24",
                    "last_fetched_at: 2026-05-24T00:00:00Z",
                    "last_success_at: 2026-05-24T00:00:00Z",
                    f"archive_path: {archive_path}",
                    "---",
                    "",
                    body,
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return note_path

    def _codes(self, report: object) -> set[str]:
        return {issue.code for issue in report.issues}  # type: ignore[attr-defined]

    def test_doctor_reports_missing_bookmark_configuration(self) -> None:
        """Missing BOOKMARKS_DIR/VAULT_PATH is a config error."""
        with patch.dict(os.environ, {}, clear=True):
            report = run_doctor()

        self.assertEqual(report.status, "error")
        self.assertIn("config.bookmarks_dir", self._codes(report))

    @patch("bookmark_tools.doctor.get_llm_config", return_value=None)
    def test_doctor_detects_core_vault_issues(self, _mock: object) -> None:
        """Doctor catches duplicates, non-bookmarks, archives, links, and search."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            database_path = Path(tmp) / "Meta" / "bookmark-search.sqlite3"
            self._write_note(
                bookmarks_dir,
                "A/page.md",
                url="https://example.com/same",
                archive_path="A/page.content.md",
                body="Summary: Example.\n\nSee [[Missing Note]].",
            )
            self._write_note(
                bookmarks_dir,
                "B/page.md",
                url="https://example.com/same",
                title="Duplicate Page",
            )
            (bookmarks_dir / "README.md").write_text("Not a bookmark", encoding="utf-8")
            (bookmarks_dir / "orphan.content.md").write_text(
                "Orphan archive", encoding="utf-8"
            )

            report = run_doctor(
                bookmarks_dir=bookmarks_dir, database_path=database_path
            )

        codes = self._codes(report)
        self.assertIn("provider.api_key_missing", codes)
        self.assertIn("notes.non_bookmark_markdown", codes)
        self.assertIn("url.duplicate", codes)
        self.assertIn("archive.missing", codes)
        self.assertIn("archive.orphan_sidecar", codes)
        self.assertIn("links.broken_internal", codes)
        self.assertIn("search.missing", codes)

    @patch("bookmark_tools.doctor.get_llm_config", return_value=None)
    def test_doctor_fix_rebuilds_missing_search_index(self, _mock: object) -> None:
        """--fix safely rebuilds missing search state from Markdown."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            database_path = Path(tmp) / "Meta" / "bookmark-search.sqlite3"
            self._write_note(
                bookmarks_dir,
                "Development/python-search.md",
                title="Python Search",
                body="Summary: Python search with sqlite.",
            )

            report = run_doctor(
                bookmarks_dir=bookmarks_dir,
                database_path=database_path,
                fix=True,
            )
            results = search_index("python", database_path=database_path)

        fixed_search = [
            issue
            for issue in report.issues
            if issue.code == "search.missing" and issue.fixed
        ]
        self.assertTrue(fixed_search)
        self.assertIn("fix.search_rebuilt", self._codes(report))
        self.assertEqual([result.title for result in results], ["Python Search"])

    @patch("bookmark_tools.doctor.get_llm_config", return_value=None)
    def test_doctor_detects_embedding_model_mismatch(self, _mock: object) -> None:
        """Stored embedding rows with old model metadata are reported."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            database_path = Path(tmp) / "Meta" / "bookmark-search.sqlite3"
            note_path = self._write_note(bookmarks_dir, "ML-AI/embedding.md")
            database_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(database_path) as connection:
                connection.execute(
                    f"""
                    CREATE TABLE {EMBEDDING_TABLE} (
                        path TEXT PRIMARY KEY,
                        url TEXT NOT NULL DEFAULT '',
                        title TEXT NOT NULL DEFAULT '',
                        folder TEXT NOT NULL DEFAULT '',
                        description TEXT NOT NULL DEFAULT '',
                        embedding BLOB NOT NULL,
                        mtime REAL NOT NULL,
                        model TEXT NOT NULL DEFAULT '',
                        dimensions INTEGER NOT NULL DEFAULT 0
                    )
                    """
                )
                connection.execute(
                    f"""
                    INSERT INTO {EMBEDDING_TABLE}
                        (path, url, title, folder, description, embedding, mtime, model, dimensions)
                    VALUES (?, '', 'Embedding', '', '', ?, 0, 'old-model', ?)
                    """,
                    (
                        str(note_path),
                        _serialize_vector([1.0] * EMBEDDING_DIMENSIONS),
                        EMBEDDING_DIMENSIONS,
                    ),
                )

            report = run_doctor(
                bookmarks_dir=bookmarks_dir, database_path=database_path
            )

        self.assertIn("embedding.mismatch", self._codes(report))

    @patch("bookmark_tools.doctor.get_llm_config", return_value=None)
    def test_doctor_main_json_output(self, _mock: object) -> None:
        """bookmark-doctor --json emits a scriptable report."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            database_path = Path(tmp) / "Meta" / "bookmark-search.sqlite3"
            self._write_note(bookmarks_dir, "Development/page.md")
            env = {
                "BOOKMARKS_DIR": str(bookmarks_dir),
                "BOOKMARK_SEARCH_INDEX": str(database_path),
            }
            with patch.dict(os.environ, env, clear=False):
                with patch("builtins.print") as mock_print:
                    exit_code = doctor_main(["--json"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(mock_print.call_args.args[0])
        self.assertIn(payload["status"], {"ok", "warning"})
        self.assertIn("issues", payload)
        self.assertIn("summary", payload)


if __name__ == "__main__":
    unittest.main()
