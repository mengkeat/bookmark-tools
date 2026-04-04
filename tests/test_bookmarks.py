from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from bookmark_tools.classify import (
    SimilarNote,
    find_existing_url,
    get_llm_config,
    strong_similar_notes,
)
from bookmark_tools.cli import normalize_metadata
from bookmark_tools.render import infer_summary, render_note, slugify_filename
from bookmark_tools.summarize import generate_summary, summarize_with_tool
from bookmark_tools.vault_profile import BookmarkProfile, collect_existing_notes


class BookmarkHelpersTest(unittest.TestCase):
    def test_normalize_metadata_defaults_type_to_article(self) -> None:
        """It falls back to the default type when LLM metadata omits type."""
        profile = BookmarkProfile(
            notes=[],
            folders=["Development"],
            schema=[],
            folder_examples={},
            folder_parent_topics={},
            default_visibility="private",
            url_index={},
        )
        normalized = normalize_metadata(
            metadata={"title": "Example title"},
            page_data={
                "url": "https://example.com",
                "title": "Example title",
                "description": "Example description",
                "language": "en",
                "content": "Example content.",
            },
            folder="Development",
            profile=profile,
            similar_notes=[],
            used_llm_classification=False,
        )
        self.assertEqual(normalized["type"], "article")

    def test_slugify_filename_normalizes_title(self) -> None:
        """It normalizes punctuation and separators in generated filenames."""
        self.assertEqual(
            slugify_filename("Intro to MPC (Model/Predictive Control)"),
            "Intro-to-MPC-Model-Predictive-Control.md",
        )

    def test_infer_summary_uses_description_first(self) -> None:
        """It prefers explicit descriptions over generated summaries."""
        self.assertEqual(
            infer_summary("Short description", "Longer body. Another sentence."),
            "Short description",
        )

    def test_strong_similar_notes_filters_weak_matches(self) -> None:
        """It keeps only high-confidence similar notes."""
        notes = [
            SimilarNote(folder="A", tags=[], parent_topic="", score=0.10, overlap=3),
            SimilarNote(folder="B", tags=[], parent_topic="", score=0.07, overlap=4),
            SimilarNote(folder="C", tags=[], parent_topic="", score=0.20, overlap=1),
        ]
        self.assertEqual(strong_similar_notes(notes), [notes[0]])

    def test_summarize_with_tool_uses_cli_output(self) -> None:
        """It returns summarize CLI output when the tool is available."""
        with patch("bookmark_tools.summarize.shutil.which", return_value="/usr/bin/summarize"), patch(
            "bookmark_tools.summarize.subprocess.run"
        ) as mocked_run:
            mocked_run.return_value.returncode = 0
            mocked_run.return_value.stdout = "Tool generated summary."
            mocked_run.return_value.stderr = ""
            summary = summarize_with_tool("https://example.com")
        self.assertEqual(summary, "Tool generated summary.")

    def test_generate_summary_prefers_classification_summary_before_second_llm_call(
        self,
    ) -> None:
        """It reuses classifier-provided summary to avoid an extra LLM summary call."""
        page_data = {
            "url": "https://example.com",
            "title": "Example",
            "description": "",
            "language": "en",
            "content": "Sentence one. Sentence two. Sentence three.",
        }
        with patch("bookmark_tools.summarize.summarize_with_tool", return_value=None), patch(
            "bookmark_tools.summarize.summarize_with_llm"
        ) as mocked_summary_llm:
            summary = generate_summary(
                "https://example.com",
                page_data,
                classification_summary="Classifier summary.",
            )
        self.assertEqual(summary, "Classifier summary.")
        mocked_summary_llm.assert_not_called()

    def test_generate_summary_falls_back_to_inferred_summary(self) -> None:
        """It falls back to deterministic summary generation when external paths fail."""
        page_data = {
            "url": "https://example.com",
            "title": "Example",
            "description": "",
            "language": "en",
            "content": "Sentence one. Sentence two. Sentence three.",
        }
        with patch("bookmark_tools.summarize.summarize_with_tool", return_value=None), patch(
            "bookmark_tools.summarize.summarize_with_llm", return_value=None
        ):
            summary = generate_summary("https://example.com", page_data)
        self.assertEqual(summary, "Sentence one. Sentence two.")

    def test_normalize_metadata_applies_defaults(self) -> None:
        """It fills required metadata fields and normalizes list values."""
        profile = BookmarkProfile(
            notes=[],
            folders=["Development"],
            schema=[
                "title",
                "url",
                "type",
                "tags",
                "language",
                "related",
                "parent_topic",
                "description",
                "visibility",
            ],
            folder_examples={},
            folder_parent_topics={},
            default_visibility="private",
            url_index={},
        )
        normalized = normalize_metadata(
            metadata={
                "title": "  ",
                "tags": [" Python ", " ", "AI"],
                "related": ["Docs", "  "],
            },
            page_data={
                "url": "https://example.com",
                "title": "Example title",
                "description": "Example description",
                "language": "en",
                "content": "Example content.",
            },
            folder="Development/Python",
            profile=profile,
            similar_notes=[],
            used_llm_classification=False,
            summary_override="Summary from summarize tool.",
        )
        self.assertEqual(normalized["title"], "Example title")
        self.assertEqual(normalized["tags"][:2], ["python", "ai"])
        self.assertEqual(normalized["related"], ["docs"])
        self.assertEqual(normalized["summary"], "Summary from summarize tool.")
        self.assertEqual(normalized["visibility"], "private")

    def test_normalize_metadata_related_are_single_word_terms(self) -> None:
        """It normalizes related values to single-word topic tags."""
        profile = BookmarkProfile(
            notes=[],
            folders=["Science"],
            schema=[],
            folder_examples={},
            folder_parent_topics={},
            default_visibility="private",
            url_index={},
        )
        normalized = normalize_metadata(
            metadata={
                "title": "Bee article",
                "related": [
                    "reading/book-sites/sci-hub",
                    "pollinator conservation",
                    "Wild-Bees",
                ],
            },
            page_data={
                "url": "https://example.com",
                "title": "Bee article",
                "description": "Example description",
                "language": "en",
                "content": "Example content.",
            },
            folder="Science",
            profile=profile,
            similar_notes=[],
            used_llm_classification=True,
        )
        self.assertEqual(
            normalized["related"],
            ["sci-hub", "pollinator-conservation", "wild-bees"],
        )

    def test_normalize_metadata_keeps_llm_tags_without_heuristic_enrichment(
        self,
    ) -> None:
        """It preserves LLM tags instead of appending heuristic similar-note tags."""
        profile = BookmarkProfile(
            notes=[],
            folders=["Development"],
            schema=[],
            folder_examples={},
            folder_parent_topics={},
            default_visibility="private",
            url_index={},
        )
        similar = [
            SimilarNote(
                folder="Development",
                tags=["heuristic-extra"],
                parent_topic="Development",
                score=0.2,
                overlap=3,
            )
        ]
        normalized = normalize_metadata(
            metadata={"title": "Example", "tags": ["llm-tag"]},
            page_data={
                "url": "https://example.com",
                "title": "Example title",
                "description": "Example description",
                "language": "en",
                "content": "Example content.",
            },
            folder="Development",
            profile=profile,
            similar_notes=similar,
            used_llm_classification=True,
        )
        self.assertEqual(normalized["tags"], ["llm-tag"])

    def test_get_llm_config_reads_openrouter_env(self) -> None:
        """It supports OpenRouter-style environment variables."""
        with patch.dict(
            os.environ,
            {
                "OPENROUTER_API_KEY": "token",
                "MODEL_ID": "openrouter/model",
                "LLM_PROVIDER": "openrouter",
            },
            clear=True,
        ):
            config = get_llm_config()
        self.assertIsNotNone(config)
        assert config is not None
        self.assertEqual(config["api_key"], "token")
        self.assertEqual(config["model"], "model")
        self.assertEqual(config["base_url"], "https://openrouter.ai/api/v1")

    def test_collect_existing_notes_indexes_urls(self) -> None:
        """It indexes normalized note URLs during vault scan."""
        with TemporaryDirectory() as tmp:
            bookmarks = Path(tmp) / "Bookmarks" / "Development"
            bookmarks.mkdir(parents=True)
            note_path = bookmarks / "sample.md"
            note_path.write_text(
                '---\nurl: "https://example.com/path/"\ntitle: "Sample"\n---\n',
                encoding="utf-8",
            )
            profile = collect_existing_notes(bookmarks_dir=Path(tmp) / "Bookmarks")
        self.assertEqual(profile.url_index["https://example.com/path"], note_path)

    def test_render_note_frontmatter_uses_unquoted_scalars(self) -> None:
        """It renders frontmatter string fields without double quotes."""
        profile = BookmarkProfile(
            notes=[],
            folders=["Development"],
            schema=[
                "title",
                "url",
                "type",
                "tags",
                "created",
                "last_updated",
                "language",
                "related",
                "parent_topic",
                "visibility",
                "description",
            ],
            folder_examples={},
            folder_parent_topics={},
            default_visibility="private",
            url_index={},
        )
        note = render_note(
            metadata={
                "folder": "Development",
                "title": "Example title",
                "type": "article",
                "tags": ["python", "ai"],
                "language": "en",
                "related": ["docs", "tutorial"],
                "parent_topic": "development",
                "description": "Simple description",
                "summary": "Simple summary.",
                "visibility": "private",
            },
            url="https://example.com",
            profile=profile,
        )
        self.assertIn("title: Example title", note)
        self.assertIn("tags: [python, ai]", note)
        self.assertIn("related: [docs, tutorial]", note)
        self.assertNotIn('"', note)

    def test_find_existing_url_uses_profile_index(self) -> None:
        """It skips filesystem scans when profile index is available."""
        expected_path = Path("/tmp/existing.md")
        profile = BookmarkProfile(
            notes=[],
            folders=[],
            schema=[],
            folder_examples={},
            folder_parent_topics={},
            default_visibility="private",
            url_index={"https://example.com": expected_path},
        )
        with patch("bookmark_tools.classify.get_bookmarks_dir") as mocked_bookmarks_dir:
            found = find_existing_url("https://example.com", profile=profile)
        self.assertEqual(found, expected_path)
        mocked_bookmarks_dir.assert_not_called()


if __name__ == "__main__":
    unittest.main()
