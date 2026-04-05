from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from bookmark_tools.search import search_bookmarks
from bookmark_tools.search_documents import collect_search_documents


class BookmarkSearchTest(unittest.TestCase):
    def _write_note(
        self,
        bookmarks_dir: Path,
        relative_path: str,
        *,
        url: str,
        title: str,
        tags: list[str],
        related: list[str],
        parent_topic: str,
        description: str,
        body: str,
    ) -> Path:
        note_path = bookmarks_dir / relative_path
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(
            "\n".join(
                [
                    "---",
                    f"url: {url}",
                    f"title: {title}",
                    f"tags: [{', '.join(tags)}]",
                    f"related: [{', '.join(related)}]",
                    f"parent_topic: {parent_topic}",
                    f"description: {description}",
                    "---",
                    "",
                    body,
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return note_path

    def _setup_two_notes(self, bookmarks_dir: Path) -> tuple[Path, Path]:
        """Create the standard python-sqlite and sqlite-overview test notes."""
        note_a = self._write_note(
            bookmarks_dir,
            "Development/Python/python-sqlite.md",
            url="https://example.com/python-sqlite",
            title="Python SQLite Guide",
            tags=["python", "sqlite"],
            related=["database"],
            parent_topic="Python",
            description="Guide to sqlite search from python",
            body="Summary: Build an FTS5 bookmark search tool with sqlite.",
        )
        note_b = self._write_note(
            bookmarks_dir,
            "Development/Databases/sqlite-overview.md",
            url="https://example.com/sqlite-overview",
            title="SQLite Overview",
            tags=["sqlite"],
            related=["database"],
            parent_topic="Databases",
            description="General sqlite notes",
            body="Summary: This note mentions python once in the body.",
        )
        return note_a, note_b

    def test_collect_search_documents_reads_frontmatter_and_body(self) -> None:
        """It turns bookmark markdown files into normalized search documents."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            note_path = self._write_note(
                bookmarks_dir,
                "Development/Python/python-sqlite.md",
                url="https://example.com/python-sqlite",
                title="Python SQLite Guide",
                tags=["python", "sqlite"],
                related=["database", "fts5"],
                parent_topic="Python",
                description="Guide to sqlite search from python",
                body="Summary: Build an FTS5 search index with sqlite.",
            )
            documents = collect_search_documents(bookmarks_dir=bookmarks_dir)

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].path, note_path)
        self.assertEqual(documents[0].tags, "python sqlite")
        self.assertEqual(documents[0].related, "database fts5")
        self.assertIn("FTS5 search index", documents[0].body)

    def test_search_bookmarks_returns_bm25_ranked_results(self) -> None:
        """It ranks stronger field matches ahead of weaker body-only matches."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            database_path = Path(tmp) / "bookmark-search.sqlite3"
            self._setup_two_notes(bookmarks_dir)

            results = search_bookmarks(
                "python sqlite",
                bookmarks_dir=bookmarks_dir,
                database_path=database_path,
            )

        self.assertEqual(
            [result.title for result in results[:2]],
            ["Python SQLite Guide", "SQLite Overview"],
        )

    def test_search_bookmarks_filters_by_folder_prefix(self) -> None:
        """It restricts matches to the selected folder subtree."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            database_path = Path(tmp) / "bookmark-search.sqlite3"
            self._setup_two_notes(bookmarks_dir)

            results = search_bookmarks(
                "sqlite",
                bookmarks_dir=bookmarks_dir,
                database_path=database_path,
                folder="Development/Databases",
            )

        self.assertEqual([result.title for result in results], ["SQLite Overview"])

    def test_incremental_update_adds_new_notes(self) -> None:
        """Incremental search picks up newly added notes without a full rebuild."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            database_path = Path(tmp) / "bookmark-search.sqlite3"
            self._setup_two_notes(bookmarks_dir)

            results = search_bookmarks(
                "sqlite",
                bookmarks_dir=bookmarks_dir,
                database_path=database_path,
            )
            self.assertEqual(len(results), 2)

            self._write_note(
                bookmarks_dir,
                "Development/Databases/sqlite-fts5.md",
                url="https://example.com/sqlite-fts5",
                title="SQLite FTS5 Deep Dive",
                tags=["sqlite", "fts5"],
                related=["search"],
                parent_topic="Databases",
                description="Advanced FTS5 usage with sqlite",
                body="Full-text search with FTS5.",
            )

            results = search_bookmarks(
                "sqlite",
                bookmarks_dir=bookmarks_dir,
                database_path=database_path,
            )
            self.assertEqual(len(results), 3)

    def test_incremental_update_removes_deleted_notes(self) -> None:
        """Incremental search drops notes that have been deleted from disk."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            database_path = Path(tmp) / "bookmark-search.sqlite3"
            _, note_b = self._setup_two_notes(bookmarks_dir)

            results = search_bookmarks(
                "sqlite",
                bookmarks_dir=bookmarks_dir,
                database_path=database_path,
            )
            self.assertEqual(len(results), 2)

            note_b.unlink()

            results = search_bookmarks(
                "sqlite",
                bookmarks_dir=bookmarks_dir,
                database_path=database_path,
            )
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].title, "Python SQLite Guide")

    def test_rebuild_flag_forces_full_rebuild(self) -> None:
        """Passing rebuild=True works and returns correct results."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            database_path = Path(tmp) / "bookmark-search.sqlite3"
            self._setup_two_notes(bookmarks_dir)

            results = search_bookmarks(
                "sqlite",
                bookmarks_dir=bookmarks_dir,
                database_path=database_path,
                rebuild=True,
            )
            self.assertEqual(len(results), 2)

    def test_prefix_matching(self) -> None:
        """A prefix query matches terms that share the prefix."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            database_path = Path(tmp) / "bookmark-search.sqlite3"
            self._write_note(
                bookmarks_dir,
                "Development/Python/pythonic-tips.md",
                url="https://example.com/pythonic-tips",
                title="Pythonic Tips",
                tags=["python"],
                related=["coding-style"],
                parent_topic="Python",
                description="Tips for writing pythonic code",
                body="Idiomatic Python patterns and best practices.",
            )

            results = search_bookmarks(
                "pyth",
                bookmarks_dir=bookmarks_dir,
                database_path=database_path,
            )
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].title, "Pythonic Tips")

    def test_search_results_include_snippets(self) -> None:
        """Search results include a context snippet from the matching body text."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            database_path = Path(tmp) / "bookmark-search.sqlite3"
            self._write_note(
                bookmarks_dir,
                "Development/Python/python-sqlite.md",
                url="https://example.com/python-sqlite",
                title="Python SQLite Guide",
                tags=["python", "sqlite"],
                related=["database"],
                parent_topic="Python",
                description="Guide to sqlite search from python",
                body="Summary: Build an FTS5 bookmark search tool with sqlite.",
            )

            results = search_bookmarks(
                "FTS5",
                bookmarks_dir=bookmarks_dir,
                database_path=database_path,
            )

        self.assertEqual(len(results), 1)
        self.assertIn("FTS5", results[0].snippet)

    def test_stemming_matches_word_variants(self) -> None:
        """Porter stemming matches inflected forms of words."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            database_path = Path(tmp) / "bookmark-search.sqlite3"
            self._write_note(
                bookmarks_dir,
                "Development/Testing/testing-guide.md",
                url="https://example.com/testing-guide",
                title="Testing Guide",
                tags=["testing"],
                related=["quality"],
                parent_topic="Testing",
                description="Comprehensive guide to automated tests",
                body="Unit tests, integration tests, and tested patterns.",
            )

            for query in ("test", "tests", "testing", "tested"):
                results = search_bookmarks(
                    query,
                    bookmarks_dir=bookmarks_dir,
                    database_path=database_path,
                )
                self.assertGreaterEqual(
                    len(results), 1, f"Expected match for query '{query}'"
                )


if __name__ == "__main__":
    unittest.main()
