"""Tests for the bookmark-graph and bookmark-backlinks CLIs."""

from __future__ import annotations

import hashlib
import json
import unittest
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from bookmark_tools.catalog import connect, ensure_catalog_schema, populate_bookmarks
from bookmark_tools.graph import rebuild_edges
from bookmark_tools.graph_cli import backlinks_main, graph_main
from bookmark_tools.url_normalize import normalize_url


def _bid(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode()).hexdigest()


def _write_note(
    bookmarks_dir: Path,
    relative_path: str,
    *,
    url: str,
    title: str = "A Page",
    tags: str = "[alpha, beta]",
    body: str = "Summary: A page.",
) -> Path:
    note_path = bookmarks_dir / relative_path
    note_path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = "\n".join(
        [
            "---",
            "schema_version: 1",
            f"id: {_bid(url)}",
            f"url: {url}",
            f"final_url: {url}",
            f"canonical_url: {url}",
            f"title: {title}",
            f"tags: {tags}",
            "description: Test",
            "---",
        ]
    )
    note_path.write_text(f"{frontmatter}\n\n{body}\n", encoding="utf-8")
    return note_path


class GraphCliTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self.bookmarks_dir = tmp / "Bookmarks"
        self.bookmarks_dir.mkdir(parents=True)
        self.db_path = tmp / "Meta" / "catalog.sqlite3"
        self.db_path.parent.mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _build(self) -> None:
        connection = connect(self.db_path)
        try:
            with connection:
                ensure_catalog_schema(connection)
                populate_bookmarks(connection, self.bookmarks_dir)
                rebuild_edges(connection, self.bookmarks_dir)
        finally:
            connection.close()

    def _env(self):
        return patch.multiple(
            "bookmark_tools.graph_cli",
            require_bookmarks_dir=lambda: self.bookmarks_dir,
            get_search_index_path=lambda: self.db_path,
        )


class BacklinksCliTest(GraphCliTestBase):
    def test_reports_backlinks_json(self) -> None:
        _write_note(self.bookmarks_dir, "target.md", url="https://target.com/")
        _write_note(
            self.bookmarks_dir,
            "source.md",
            url="https://source.com/",
            title="Source",
            body="Summary: x\n\nSee https://target.com/ here.",
        )
        self._build()

        with self._env(), patch("sys.stdout", new_callable=StringIO) as out:
            rc = backlinks_main(["https://target.com/", "--json"])
        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(len(payload["backlinks"]), 1)
        self.assertEqual(payload["backlinks"][0]["title"], "Source")

    def test_missing_db_errors(self) -> None:
        _write_note(self.bookmarks_dir, "t.md", url="https://t.com/")
        with self._env():
            rc = backlinks_main(["https://t.com/"])
        self.assertEqual(rc, 1)

    def test_unknown_target_errors(self) -> None:
        _write_note(self.bookmarks_dir, "t.md", url="https://t.com/")
        self._build()
        with self._env():
            rc = backlinks_main(["https://missing.com/"])
        self.assertEqual(rc, 1)


class GraphCliTest(GraphCliTestBase):
    def test_traverse_json(self) -> None:
        _write_note(self.bookmarks_dir, "a.md", url="https://a.com/", tags="[python]")
        _write_note(
            self.bookmarks_dir, "b.md", url="https://b.com/", tags="[python, db]"
        )
        _write_note(self.bookmarks_dir, "c.md", url="https://c.com/", tags="[db]")
        self._build()

        with self._env(), patch("sys.stdout", new_callable=StringIO) as out:
            rc = graph_main(["https://a.com/", "--depth", "2", "--json"])
        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        depths = {n["url"]: n["depth"] for n in payload["nodes"]}
        self.assertEqual(depths[normalize_url("https://b.com/")], 1)
        self.assertEqual(depths[normalize_url("https://c.com/")], 2)

    def test_depth_must_be_positive(self) -> None:
        _write_note(self.bookmarks_dir, "a.md", url="https://a.com/")
        self._build()
        with self._env():
            rc = graph_main(["https://a.com/", "--depth", "0"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
