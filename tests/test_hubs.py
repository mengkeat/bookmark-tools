"""Tests for topic/domain/tag hub generation."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from bookmark_tools.hubs import build_hub_pages, main


def _write_note(
    bookmarks_dir: Path,
    relative_path: str,
    *,
    url: str,
    title: str,
    tags: str = "[python]",
    parent_topic: str = "Programming",
) -> Path:
    note_path = bookmarks_dir / relative_path
    note_path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = "\n".join(
        [
            "---",
            "schema_version: 1",
            f"url: {url}",
            f"title: {title}",
            f"tags: {tags}",
            f"parent_topic: {parent_topic}",
            "description: Test",
            "---",
        ]
    )
    note_path.write_text(f"{frontmatter}\n\nSummary: x\n", encoding="utf-8")
    return note_path


class BuildHubPagesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        root = Path(self._tmp.name)
        self.bookmarks_dir = root / "Bookmarks"
        self.bookmarks_dir.mkdir(parents=True)
        self.hubs_dir = root / "Meta" / "hubs"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_generates_tag_domain_topic_pages(self) -> None:
        _write_note(
            self.bookmarks_dir,
            "a.md",
            url="https://example.com/a",
            title="Alpha",
            tags="[python, web]",
            parent_topic="Programming",
        )
        _write_note(
            self.bookmarks_dir,
            "b.md",
            url="https://example.com/b",
            title="Beta",
            tags="[python]",
            parent_topic="Programming",
        )
        result = build_hub_pages(
            bookmarks_dir=self.bookmarks_dir, hubs_dir=self.hubs_dir
        )
        self.assertTrue(result.written)

        tag_page = self.hubs_dir / "Tags" / "python.md"
        self.assertTrue(tag_page.exists())
        text = tag_page.read_text()
        self.assertIn("[[a|Alpha]]", text)
        self.assertIn("[[b|Beta]]", text)

        domain_page = self.hubs_dir / "Domains" / "example.com.md"
        self.assertTrue(domain_page.exists())

        topic_page = self.hubs_dir / "Topics" / "Programming.md"
        self.assertTrue(topic_page.exists())

    def test_rebuild_recreates_deleted_pages(self) -> None:
        _write_note(
            self.bookmarks_dir, "a.md", url="https://x.com/a", title="Alpha"
        )
        build_hub_pages(bookmarks_dir=self.bookmarks_dir, hubs_dir=self.hubs_dir)
        tag_page = self.hubs_dir / "Tags" / "python.md"
        self.assertTrue(tag_page.exists())

        tag_page.unlink()
        build_hub_pages(bookmarks_dir=self.bookmarks_dir, hubs_dir=self.hubs_dir)
        self.assertTrue(tag_page.exists())

    def test_preserves_human_content_outside_block(self) -> None:
        _write_note(
            self.bookmarks_dir, "a.md", url="https://x.com/a", title="Alpha"
        )
        build_hub_pages(bookmarks_dir=self.bookmarks_dir, hubs_dir=self.hubs_dir)
        topic_page = self.hubs_dir / "Topics" / "Programming.md"
        original = topic_page.read_text()
        topic_page.write_text(
            original.rstrip() + "\n\n## My notes\nHand-written.\n", encoding="utf-8"
        )

        # Add another note and rebuild.
        _write_note(
            self.bookmarks_dir, "b.md", url="https://x.com/b", title="Beta"
        )
        build_hub_pages(bookmarks_dir=self.bookmarks_dir, hubs_dir=self.hubs_dir)

        text = topic_page.read_text()
        self.assertIn("## My notes\nHand-written.", text)
        self.assertIn("[[b|Beta]]", text)
        self.assertEqual(text.count("bookmark-tools:hub:start"), 1)

    def test_prune_removes_orphan_pages(self) -> None:
        _write_note(
            self.bookmarks_dir,
            "a.md",
            url="https://x.com/a",
            title="Alpha",
            tags="[python]",
        )
        build_hub_pages(bookmarks_dir=self.bookmarks_dir, hubs_dir=self.hubs_dir)
        self.assertTrue((self.hubs_dir / "Tags" / "python.md").exists())

        # Retag the only note; the python tag page becomes an orphan.
        _write_note(
            self.bookmarks_dir,
            "a.md",
            url="https://x.com/a",
            title="Alpha",
            tags="[rust]",
        )
        result = build_hub_pages(
            bookmarks_dir=self.bookmarks_dir, hubs_dir=self.hubs_dir
        )
        self.assertFalse((self.hubs_dir / "Tags" / "python.md").exists())
        self.assertTrue((self.hubs_dir / "Tags" / "rust.md").exists())
        self.assertTrue(result.removed)


class HubsCliTest(unittest.TestCase):
    def test_main_rejects_unknown_kind(self) -> None:
        # Patch load_env so the repo .env does not leak into os.environ.
        with patch("bookmark_tools.hubs.load_env", lambda: None):
            rc = main(["rebuild", "--kind", "bogus"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
