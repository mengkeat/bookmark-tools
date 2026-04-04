from __future__ import annotations

import math
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from bookmark_tools.embeddings import (
    EMBEDDING_DIMENSIONS,
    EmbeddingMatch,
    build_embedding_text,
    refresh_embeddings,
    semantic_search,
    _normalize_vector,
    _serialize_vector,
    _deserialize_vector,
    _cosine_similarities,
)
from bookmark_tools.search import (
    search_bookmarks_hybrid,
    search_bookmarks_semantic,
    _reciprocal_rank_fusion,
)
from bookmark_tools.search_documents import SearchDocument
from bookmark_tools.search_index import SearchResult


def _make_document(
    bookmarks_dir: Path,
    relative_path: str,
    *,
    url: str = "",
    title: str = "",
    tags: str = "",
    parent_topic: str = "",
    description: str = "",
    body: str = "",
) -> SearchDocument:
    """Create a SearchDocument backed by a real file on disk."""
    note_path = bookmarks_dir / relative_path
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(
        "\n".join(
            [
                "---",
                f"url: {url}",
                f"title: {title}",
                f"tags: [{tags}]",
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
    folder = str(note_path.relative_to(bookmarks_dir).parent)
    return SearchDocument(
        path=note_path,
        url=url,
        title=title,
        folder="" if folder == "." else folder,
        tags=tags,
        related="",
        parent_topic=parent_topic,
        description=description,
        body=body,
    )


def _fake_embeddings(texts: list[str], _config: dict[str, str]) -> list[list[float]]:
    """Return deterministic fake embeddings based on text hash."""
    results: list[list[float]] = []
    for text in texts:
        h = hash(text) & 0xFFFFFFFF
        vector = [0.0] * EMBEDDING_DIMENSIONS
        for i in range(min(8, EMBEDDING_DIMENSIONS)):
            vector[(h + i * 37) % EMBEDDING_DIMENSIONS] = float((h >> i) & 1) or 0.1
        results.append(vector)
    return results


FAKE_CONFIG = {"api_key": "test-key", "model": "test", "base_url": "http://test"}


class EmbeddingHelpersTest(unittest.TestCase):
    def test_normalize_vector_produces_unit_length(self) -> None:
        """L2-normalized vector has magnitude 1."""
        vector = [3.0, 4.0, 0.0]
        normalized = _normalize_vector(vector)
        magnitude = math.sqrt(sum(x * x for x in normalized))
        self.assertAlmostEqual(magnitude, 1.0, places=6)

    def test_serialize_deserialize_roundtrips(self) -> None:
        """Serializing then deserializing recovers the original vector."""
        original = [1.0, -2.5, 3.14, 0.0]
        recovered = _deserialize_vector(_serialize_vector(original))
        for a, b in zip(original, recovered):
            self.assertAlmostEqual(a, b, places=5)

    def test_cosine_similarities_with_identical_vectors(self) -> None:
        """Identical normalized vectors have similarity 1.0."""
        vector = _normalize_vector([1.0, 2.0, 3.0])
        similarities = _cosine_similarities(vector, [vector, vector])
        for sim in similarities:
            self.assertAlmostEqual(sim, 1.0, places=5)

    def test_cosine_similarities_with_orthogonal_vectors(self) -> None:
        """Orthogonal vectors have similarity 0.0."""
        a = _normalize_vector([1.0, 0.0, 0.0])
        b = _normalize_vector([0.0, 1.0, 0.0])
        similarities = _cosine_similarities(a, [b])
        self.assertAlmostEqual(similarities[0], 0.0, places=5)

    def test_build_embedding_text_concatenates_nonempty_fields(self) -> None:
        """Document text joins only non-empty fields with pipe separators."""
        with TemporaryDirectory() as tmp:
            doc = _make_document(
                Path(tmp) / "Bookmarks",
                "ML-AI/test.md",
                title="Neural Networks",
                tags="ml deep-learning",
                description="Intro to NNs",
            )
        text = build_embedding_text(doc)
        self.assertIn("Neural Networks", text)
        self.assertIn("ml deep-learning", text)
        self.assertIn("Intro to NNs", text)
        self.assertNotIn("| |", text)


class EmbeddingIndexTest(unittest.TestCase):
    @patch("bookmark_tools.embeddings.embed_texts", side_effect=_fake_embeddings)
    def test_refresh_and_search_returns_ranked_matches(self, _mock: object) -> None:
        """Refresh stores embeddings and search returns ranked results."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            db_path = Path(tmp) / "test.sqlite3"

            doc_a = _make_document(
                bookmarks_dir,
                "ML-AI/transformers.md",
                title="Transformer Architecture",
                tags="ml transformers",
                description="Attention is all you need",
            )
            doc_b = _make_document(
                bookmarks_dir,
                "Development/Python/flask.md",
                title="Flask Web Framework",
                tags="python flask web",
                description="Lightweight web framework",
            )

            refresh_embeddings(
                [doc_a, doc_b], database_path=db_path, config=FAKE_CONFIG
            )
            results = semantic_search(
                "deep learning attention",
                database_path=db_path,
                config=FAKE_CONFIG,
                limit=2,
                threshold=0.0,
            )

        self.assertEqual(len(results), 2)
        self.assertIsInstance(results[0], EmbeddingMatch)
        self.assertGreaterEqual(results[0].similarity, results[1].similarity)

    @patch("bookmark_tools.embeddings.embed_texts", side_effect=_fake_embeddings)
    def test_refresh_skips_unchanged_documents(self, mock_embed: object) -> None:
        """Incremental refresh only embeds new or modified documents."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            db_path = Path(tmp) / "test.sqlite3"

            doc = _make_document(
                bookmarks_dir,
                "ML-AI/bert.md",
                title="BERT",
                tags="ml nlp",
                description="Bidirectional encoder",
            )

            refresh_embeddings([doc], database_path=db_path, config=FAKE_CONFIG)
            self.assertEqual(mock_embed.call_count, 1)

            refresh_embeddings([doc], database_path=db_path, config=FAKE_CONFIG)
            self.assertEqual(mock_embed.call_count, 1)

    @patch("bookmark_tools.embeddings.embed_texts", side_effect=_fake_embeddings)
    def test_refresh_removes_deleted_documents(self, _mock: object) -> None:
        """Deleted documents are removed from the embedding store."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            db_path = Path(tmp) / "test.sqlite3"

            doc_a = _make_document(
                bookmarks_dir, "ML-AI/a.md", title="Note A"
            )
            doc_b = _make_document(
                bookmarks_dir, "ML-AI/b.md", title="Note B"
            )

            refresh_embeddings(
                [doc_a, doc_b], database_path=db_path, config=FAKE_CONFIG
            )
            results = semantic_search(
                "test", database_path=db_path, config=FAKE_CONFIG,
                threshold=0.0,
            )
            self.assertEqual(len(results), 2)

            refresh_embeddings([doc_a], database_path=db_path, config=FAKE_CONFIG)
            results = semantic_search(
                "test", database_path=db_path, config=FAKE_CONFIG,
                threshold=0.0,
            )
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].title, "Note A")

    @patch("bookmark_tools.embeddings.embed_texts", side_effect=_fake_embeddings)
    def test_semantic_search_filters_by_folder(self, _mock: object) -> None:
        """Folder filtering restricts results to the specified subtree."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            db_path = Path(tmp) / "test.sqlite3"

            doc_a = _make_document(
                bookmarks_dir, "ML-AI/LLMs/gpt.md", title="GPT"
            )
            doc_b = _make_document(
                bookmarks_dir, "Development/Python/django.md", title="Django"
            )

            refresh_embeddings(
                [doc_a, doc_b], database_path=db_path, config=FAKE_CONFIG
            )
            results = semantic_search(
                "test",
                database_path=db_path,
                config=FAKE_CONFIG,
                folder="ML-AI",
                threshold=0.0,
            )

        titles = [r.title for r in results]
        self.assertIn("GPT", titles)
        self.assertNotIn("Django", titles)

    @patch("bookmark_tools.embeddings.embed_texts", side_effect=_fake_embeddings)
    def test_search_bookmarks_semantic_returns_search_results(
        self, _mock: object
    ) -> None:
        """The high-level semantic search returns SearchResult objects."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            db_path = Path(tmp) / "test.sqlite3"

            _make_document(
                bookmarks_dir,
                "ML-AI/attention.md",
                url="https://example.com/attention",
                title="Attention Mechanisms",
                tags="ml attention",
                description="Self-attention in transformers",
            )

            with patch(
                "bookmark_tools.embeddings.get_llm_config",
                return_value=FAKE_CONFIG,
            ):
                results = search_bookmarks_semantic(
                    "how does attention work",
                    bookmarks_dir=bookmarks_dir,
                    database_path=db_path,
                    threshold=0.0,
                )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "Attention Mechanisms")
        self.assertEqual(results[0].url, "https://example.com/attention")


class ReciprocalRankFusionTest(unittest.TestCase):
    def _result(self, name: str, score: float = 0.0) -> SearchResult:
        return SearchResult(
            path=Path(f"/tmp/{name}.md"),
            url=f"https://example.com/{name}",
            title=name,
            folder="Test",
            description="",
            score=score,
        )

    def test_duplicate_results_rank_higher(self) -> None:
        """A result appearing in both lists gets a higher fused score."""
        shared = self._result("shared")
        bm25_only = self._result("bm25-only")
        sem_only = self._result("sem-only")

        fused = _reciprocal_rank_fusion(
            [shared, bm25_only],
            [shared, sem_only],
            limit=10,
        )
        titles = [r.title for r in fused]
        self.assertEqual(titles[0], "shared")

    def test_limit_is_respected(self) -> None:
        """RRF returns at most ``limit`` results."""
        results_a = [self._result(f"a{i}") for i in range(5)]
        results_b = [self._result(f"b{i}") for i in range(5)]
        fused = _reciprocal_rank_fusion(results_a, results_b, limit=3)
        self.assertEqual(len(fused), 3)

    def test_disjoint_lists_interleave(self) -> None:
        """Results from two disjoint lists are both represented."""
        bm25 = [self._result("bm25")]
        sem = [self._result("sem")]
        fused = _reciprocal_rank_fusion(bm25, sem, limit=10)
        titles = {r.title for r in fused}
        self.assertEqual(titles, {"bm25", "sem"})


class HybridSearchTest(unittest.TestCase):
    @patch("bookmark_tools.embeddings.embed_texts", side_effect=_fake_embeddings)
    def test_hybrid_search_returns_fused_results(self, _mock: object) -> None:
        """Hybrid search returns results from both BM25 and semantic ranking."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            db_path = Path(tmp) / "test.sqlite3"

            _make_document(
                bookmarks_dir,
                "ML-AI/transformers.md",
                url="https://example.com/transformers",
                title="Transformer Architecture",
                tags="ml transformers attention",
                description="Attention is all you need",
                body="The transformer model uses self-attention.",
            )
            _make_document(
                bookmarks_dir,
                "ML-AI/rnn.md",
                url="https://example.com/rnn",
                title="Recurrent Neural Networks",
                tags="ml rnn",
                description="Sequence modeling with RNNs",
                body="RNNs process sequential data step by step.",
            )

            with patch(
                "bookmark_tools.embeddings.get_llm_config",
                return_value=FAKE_CONFIG,
            ):
                results = search_bookmarks_hybrid(
                    "transformer attention",
                    bookmarks_dir=bookmarks_dir,
                    database_path=db_path,
                    threshold=0.0,
                )

        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0].title, "Transformer Architecture")


if __name__ == "__main__":
    unittest.main()
