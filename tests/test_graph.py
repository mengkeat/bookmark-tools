"""Tests for the deterministic bookmark graph module."""

from __future__ import annotations

import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from bookmark_tools.catalog import (
    EDGES_TABLE,
    connect,
    ensure_catalog_schema,
    populate_bookmarks,
)
from bookmark_tools.graph import (
    EDGE_FROM_DOMAIN,
    EDGE_HAS_TAG,
    EDGE_IN_FOLDER,
    EDGE_LINKS_TO_URL,
    EDGE_RELATED_TO,
    extract_body_urls,
    extract_edges,
    get_backlinks,
    get_related,
    rebuild_edges,
    traverse,
    upsert_edges_for_note,
)
from bookmark_tools.note_schema import parse_note_file
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
    related: str = "",
    domain: str = "",
    body: str = "Summary: A page.",
) -> Path:
    note_path = bookmarks_dir / relative_path
    note_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        "schema_version: 1",
        f"id: {_bid(url)}",
        f"url: {url}",
        f"final_url: {url}",
        f"canonical_url: {url}",
        f"title: {title}",
        f"tags: {tags}",
        "parent_topic: Testing",
    ]
    if domain:
        lines.append(f"domain: {domain}")
    if related:
        lines.append(f"related: {related}")
    lines.append("description: Test")
    lines.append("---")
    frontmatter = "\n".join(lines)
    note_path.write_text(f"{frontmatter}\n\n{body}\n", encoding="utf-8")
    return note_path


class ExtractEdgesTests(unittest.TestCase):
    def test_extracts_folder_tag_domain_edges(self) -> None:
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp)
            note_path = _write_note(
                bookmarks_dir,
                "Tech/page.md",
                url="https://example.com/a",
                tags="[search, rag]",
            )
            note = parse_note_file(note_path)
            edges = extract_edges(note, bookmarks_dir=bookmarks_dir)
            by_type: dict[str, list[str]] = {}
            for edge in edges:
                by_type.setdefault(edge.edge_type, []).append(edge.to_id)

            self.assertEqual(by_type[EDGE_IN_FOLDER], ["Tech"])
            self.assertEqual(sorted(by_type[EDGE_HAS_TAG]), ["rag", "search"])
            self.assertEqual(by_type[EDGE_FROM_DOMAIN], ["example.com"])

    def test_related_edges(self) -> None:
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp)
            note_path = _write_note(
                bookmarks_dir,
                "page.md",
                url="https://example.com/a",
                related="[Semantic Search, Retrieval]",
            )
            note = parse_note_file(note_path)
            edges = extract_edges(note, bookmarks_dir=bookmarks_dir)
            related = [e.to_id for e in edges if e.edge_type == EDGE_RELATED_TO]
            self.assertEqual(sorted(related), ["retrieval", "semantic search"])

    def test_body_links_excludes_own_url(self) -> None:
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp)
            body = (
                "Summary: A page.\n\n"
                "See https://other.com/x and [link](https://third.com/y).\n"
                "Self ref https://example.com/a should be skipped."
            )
            note_path = _write_note(
                bookmarks_dir,
                "page.md",
                url="https://example.com/a",
                body=body,
            )
            note = parse_note_file(note_path)
            edges = extract_edges(note, bookmarks_dir=bookmarks_dir)
            links = sorted(e.to_id for e in edges if e.edge_type == EDGE_LINKS_TO_URL)
            self.assertEqual(links, ["https://other.com/x", "https://third.com/y"])

    def test_non_bookmark_yields_no_edges(self) -> None:
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp)
            note_path = bookmarks_dir / "note.md"
            note_path.write_text("---\ntitle: x\n---\n\nNo url.\n", encoding="utf-8")
            note = parse_note_file(note_path)
            self.assertEqual(extract_edges(note, bookmarks_dir=bookmarks_dir), [])


class ExtractBodyUrlsTests(unittest.TestCase):
    def test_trims_trailing_punctuation(self) -> None:
        urls = extract_body_urls(
            "Visit https://example.com/path. Also (https://x.com/y).",
            exclude=set(),
        )
        self.assertEqual(urls, ["https://example.com/path", "https://x.com/y"])

    def test_dedupes(self) -> None:
        urls = extract_body_urls(
            "https://a.com/1 https://a.com/1 https://a.com/1/", exclude=set()
        )
        # Trailing-slash normalization makes the third a duplicate.
        self.assertEqual(urls, ["https://a.com/1"])


class GraphPersistenceTests(unittest.TestCase):
    def _setup_vault(self, tmp: str) -> Path:
        bookmarks_dir = Path(tmp) / "Bookmarks"
        bookmarks_dir.mkdir(parents=True)
        return bookmarks_dir

    def test_rebuild_and_get_related_by_shared_tag(self) -> None:
        with TemporaryDirectory() as tmp:
            bookmarks_dir = self._setup_vault(tmp)
            db = Path(tmp) / "catalog.sqlite3"
            _write_note(
                bookmarks_dir, "a.md", url="https://a.com/", tags="[python, web]"
            )
            _write_note(
                bookmarks_dir, "b.md", url="https://b.com/", tags="[python, db]"
            )
            connection = connect(db)
            try:
                with connection:
                    ensure_catalog_schema(connection)
                    populate_bookmarks(connection, bookmarks_dir)
                    total = rebuild_edges(connection, bookmarks_dir)
                self.assertGreater(total, 0)
                related = get_related(connection, _bid("https://a.com/"))
                self.assertEqual(len(related), 1)
                self.assertEqual(related[0].bookmark_id, _bid("https://b.com/"))
                self.assertIn(EDGE_HAS_TAG, related[0].via)
            finally:
                connection.close()

    def test_get_backlinks(self) -> None:
        with TemporaryDirectory() as tmp:
            bookmarks_dir = self._setup_vault(tmp)
            db = Path(tmp) / "catalog.sqlite3"
            _write_note(bookmarks_dir, "target.md", url="https://target.com/")
            _write_note(
                bookmarks_dir,
                "source.md",
                url="https://source.com/",
                body="Summary: x\n\nSee https://target.com/ for details.",
            )
            connection = connect(db)
            try:
                with connection:
                    ensure_catalog_schema(connection)
                    populate_bookmarks(connection, bookmarks_dir)
                    rebuild_edges(connection, bookmarks_dir)
                backlinks = get_backlinks(connection, _bid("https://target.com/"))
                self.assertEqual(len(backlinks), 1)
                self.assertEqual(backlinks[0].bookmark_id, _bid("https://source.com/"))
            finally:
                connection.close()

    def test_upsert_replaces_edges(self) -> None:
        with TemporaryDirectory() as tmp:
            bookmarks_dir = self._setup_vault(tmp)
            db = Path(tmp) / "catalog.sqlite3"
            note_path = _write_note(
                bookmarks_dir, "a.md", url="https://a.com/", tags="[one, two]"
            )
            connection = connect(db)
            try:
                with connection:
                    ensure_catalog_schema(connection)
                    populate_bookmarks(connection, bookmarks_dir)
                    upsert_edges_for_note(connection, note_path, bookmarks_dir)
                first = connection.execute(
                    f"SELECT COUNT(*) FROM {EDGES_TABLE} WHERE edge_type = ?",
                    (EDGE_HAS_TAG,),
                ).fetchone()[0]
                self.assertEqual(first, 2)

                _write_note(
                    bookmarks_dir, "a.md", url="https://a.com/", tags="[only]"
                )
                with connection:
                    upsert_edges_for_note(connection, note_path, bookmarks_dir)
                second = connection.execute(
                    f"SELECT COUNT(*) FROM {EDGES_TABLE} WHERE edge_type = ?",
                    (EDGE_HAS_TAG,),
                ).fetchone()[0]
                self.assertEqual(second, 1)
            finally:
                connection.close()

    def test_traverse_depth(self) -> None:
        with TemporaryDirectory() as tmp:
            bookmarks_dir = self._setup_vault(tmp)
            db = Path(tmp) / "catalog.sqlite3"
            # a -> b share tag python; b -> c share tag db; a and c share nothing.
            _write_note(bookmarks_dir, "a.md", url="https://a.com/", tags="[python]")
            _write_note(
                bookmarks_dir, "b.md", url="https://b.com/", tags="[python, db]"
            )
            _write_note(bookmarks_dir, "c.md", url="https://c.com/", tags="[db]")
            connection = connect(db)
            try:
                with connection:
                    ensure_catalog_schema(connection)
                    populate_bookmarks(connection, bookmarks_dir)
                    rebuild_edges(connection, bookmarks_dir)
                depth1 = traverse(connection, _bid("https://a.com/"), depth=1)
                self.assertEqual(set(depth1), {_bid("https://b.com/")})
                depth2 = traverse(connection, _bid("https://a.com/"), depth=2)
                self.assertEqual(
                    set(depth2), {_bid("https://b.com/"), _bid("https://c.com/")}
                )
                self.assertEqual(depth2[_bid("https://c.com/")], 2)
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
