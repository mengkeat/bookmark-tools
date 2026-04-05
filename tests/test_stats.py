from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from bookmark_tools.stats import collect_stats, format_stats


class StatsTest(unittest.TestCase):
    def _write_note(
        self,
        bookmarks_dir: Path,
        relative_path: str,
        *,
        url: str = "https://example.com",
        title: str = "Example",
        tags: list[str] | None = None,
        btype: str = "article",
        parent_topic: str = "",
    ) -> Path:
        note_path = bookmarks_dir / relative_path
        note_path.parent.mkdir(parents=True, exist_ok=True)
        tag_list = tags or []
        note_path.write_text(
            "\n".join(
                [
                    "---",
                    f"url: {url}",
                    f"title: {title}",
                    f"type: {btype}",
                    f"tags: [{', '.join(tag_list)}]",
                    f"parent_topic: {parent_topic}",
                    "---",
                    "",
                    "Summary: test",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return note_path

    def test_collect_stats_counts_bookmarks(self) -> None:
        """It counts total bookmarks across all folders."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            self._write_note(
                bookmarks_dir,
                "Dev/note1.md",
                title="Note 1",
                tags=["python"],
                parent_topic="Dev",
            )
            self._write_note(
                bookmarks_dir,
                "Dev/note2.md",
                url="https://example.com/2",
                title="Note 2",
                tags=["python", "ai"],
                parent_topic="Dev",
            )
            self._write_note(
                bookmarks_dir,
                "Science/note3.md",
                url="https://example.com/3",
                title="Note 3",
                tags=["biology"],
                parent_topic="Science",
            )
            stats = collect_stats(bookmarks_dir=bookmarks_dir)

        self.assertEqual(stats["total_bookmarks"], 3)
        self.assertEqual(stats["total_folders"], 2)

        folder_counts = stats["bookmarks_per_folder"]
        assert isinstance(folder_counts, dict)
        self.assertEqual(folder_counts["Dev"], 2)
        self.assertEqual(folder_counts["Science"], 1)

    def test_collect_stats_counts_tags(self) -> None:
        """It aggregates tag frequencies across all notes."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            self._write_note(
                bookmarks_dir,
                "Dev/a.md",
                title="A",
                tags=["python", "ai"],
            )
            self._write_note(
                bookmarks_dir,
                "Dev/b.md",
                url="https://example.com/b",
                title="B",
                tags=["python"],
            )
            stats = collect_stats(bookmarks_dir=bookmarks_dir)

        top_tags = stats["top_tags"]
        assert isinstance(top_tags, dict)
        self.assertEqual(top_tags["python"], 2)
        self.assertEqual(top_tags["ai"], 1)

    def test_collect_stats_counts_types(self) -> None:
        """It counts bookmark types."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            self._write_note(
                bookmarks_dir, "Dev/a.md", title="A", btype="article"
            )
            self._write_note(
                bookmarks_dir,
                "Dev/b.md",
                url="https://example.com/b",
                title="B",
                btype="video",
            )
            stats = collect_stats(bookmarks_dir=bookmarks_dir)

        type_dist = stats["type_distribution"]
        assert isinstance(type_dist, dict)
        self.assertEqual(type_dist["article"], 1)
        self.assertEqual(type_dist["video"], 1)

    def test_collect_stats_empty_vault(self) -> None:
        """It handles an empty vault gracefully."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            bookmarks_dir.mkdir(parents=True)
            stats = collect_stats(bookmarks_dir=bookmarks_dir)

        self.assertEqual(stats["total_bookmarks"], 0)
        self.assertEqual(stats["total_folders"], 0)

    def test_format_stats_produces_readable_output(self) -> None:
        """It formats stats into a human-readable string."""
        stats = {
            "total_bookmarks": 5,
            "total_folders": 2,
            "bookmarks_per_folder": {"Dev": 3, "Science": 2},
            "type_distribution": {"article": 4, "video": 1},
            "top_tags": {"python": 3, "ai": 2},
            "top_parent_topics": {"Dev": 3},
        }
        output = format_stats(stats)
        self.assertIn("Total bookmarks: 5", output)
        self.assertIn("Total folders: 2", output)
        self.assertIn("Dev: 3", output)
        self.assertIn("article: 4", output)
        self.assertIn("python: 3", output)


if __name__ == "__main__":
    unittest.main()
