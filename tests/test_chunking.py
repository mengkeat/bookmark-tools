from __future__ import annotations

from pathlib import Path
import unittest

from bookmark_tools.chunking import (
    chunk_document,
    chunk_documents,
    split_markdown_sections,
)
from bookmark_tools.search_documents import SearchDocument


def _document(body: str, *, title: str = "Chunk Test") -> SearchDocument:
    return SearchDocument(
        path=Path("/vault/Bookmarks/Test/chunk-test.md"),
        url="https://example.com/chunk-test",
        title=title,
        folder="Test",
        tags="search chunks",
        related="retrieval",
        parent_topic="Search",
        description="Chunking test document",
        body=body,
    )


class ChunkingTest(unittest.TestCase):
    def test_split_markdown_sections_uses_headings(self) -> None:
        sections = split_markdown_sections(
            "Summary: prelude text\n\n## Key ideas\n- alpha\n- beta\n\n## Notes\nHuman note."
        )

        self.assertEqual(
            [section.name for section in sections], ["summary", "key_ideas", "notes"]
        )
        self.assertIn("alpha", sections[1].text)

    def test_chunk_document_splits_large_sections(self) -> None:
        body = "## Archive\n" + " ".join(f"token{i}" for i in range(80))
        chunks = chunk_document(_document(body), max_chars=120, overlap_chars=20)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.section == "archive" for chunk in chunks))
        self.assertEqual(
            [chunk.chunk_index for chunk in chunks], list(range(len(chunks)))
        )
        self.assertTrue(all(chunk.text_hash.startswith("sha256:") for chunk in chunks))
        self.assertTrue(all(chunk.token_count > 0 for chunk in chunks))

    def test_chunk_documents_preserves_document_metadata(self) -> None:
        document = _document("## Notes\nA detailed note about sqlite chunk search.")
        chunks = chunk_documents([document])

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].path, document.path)
        self.assertEqual(chunks[0].title, document.title)
        self.assertEqual(chunks[0].tags, "search chunks")
        self.assertEqual(chunks[0].section, "notes")

    def test_chunk_empty_body_uses_metadata_fallback(self) -> None:
        chunks = chunk_document(_document("", title="Only Metadata"))

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].section, "metadata")
        self.assertIn("Chunking test document", chunks[0].chunk_text)


if __name__ == "__main__":
    unittest.main()
