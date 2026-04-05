from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from bookmark_tools.reorg import apply_reclassifications, propose_reclassifications


class ReorgTest(unittest.TestCase):
    def _write_note(
        self,
        bookmarks_dir: Path,
        relative_path: str,
        *,
        url: str,
        title: str,
        tags: list[str] | None = None,
        parent_topic: str = "",
        description: str = "",
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
                    f"tags: [{', '.join(tag_list)}]",
                    f"parent_topic: {parent_topic}",
                    f"description: {description}",
                    "---",
                    "",
                    "Summary: test",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return note_path

    def test_no_proposals_when_all_correct(self) -> None:
        """It returns empty when all bookmarks are in the right folder."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            # Create multiple notes in Development so heuristic picks Development
            self._write_note(
                bookmarks_dir,
                "Development/note1.md",
                url="https://example.com/1",
                title="Python Guide",
                tags=["python"],
                parent_topic="Development",
            )
            self._write_note(
                bookmarks_dir,
                "Development/note2.md",
                url="https://example.com/2",
                title="Python Tutorial",
                tags=["python"],
                parent_topic="Development",
            )
            proposals = propose_reclassifications(bookmarks_dir=bookmarks_dir)

        # Both notes are in Development, which is the strongest folder
        self.assertEqual(proposals, [])

    def test_proposes_move_for_misplaced_note(self) -> None:
        """It proposes a move when a note is in the wrong folder."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            # 3 notes in ML-AI about machine learning topics
            for i in range(3):
                self._write_note(
                    bookmarks_dir,
                    f"ML-AI/ml-note-{i}.md",
                    url=f"https://example.com/ml-{i}",
                    title=f"Machine Learning Guide {i}",
                    tags=["machine-learning", "neural-networks"],
                    parent_topic="Machine Learning",
                    description="Deep learning and neural networks",
                )
            # 1 ML-related note misplaced in Development
            self._write_note(
                bookmarks_dir,
                "Development/misplaced-ml.md",
                url="https://example.com/misplaced",
                title="Machine Learning Neural Networks",
                tags=["machine-learning", "neural-networks"],
                parent_topic="Machine Learning",
                description="Deep learning and neural networks",
            )
            proposals = propose_reclassifications(bookmarks_dir=bookmarks_dir)

        # The misplaced ML note should be proposed for move to ML-AI
        misplaced = [p for p in proposals if "misplaced" in p["path"]]
        self.assertEqual(len(misplaced), 1)
        self.assertEqual(misplaced[0]["current_folder"], "Development")
        self.assertEqual(misplaced[0]["proposed_folder"], "ML-AI")

    def test_skips_notes_without_url(self) -> None:
        """It skips notes that don't have a valid URL."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            note_path = bookmarks_dir / "Development" / "no-url.md"
            note_path.parent.mkdir(parents=True, exist_ok=True)
            note_path.write_text(
                "---\ntitle: No URL Note\n---\nSummary: test\n",
                encoding="utf-8",
            )
            proposals = propose_reclassifications(bookmarks_dir=bookmarks_dir)

        self.assertEqual(proposals, [])


class ApplyReclassificationsTest(unittest.TestCase):
    def test_moves_file_to_proposed_folder(self) -> None:
        """It moves the note file to the proposed destination folder."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            src_dir = bookmarks_dir / "Development"
            dest_dir = bookmarks_dir / "ML-AI"
            src_dir.mkdir(parents=True)
            dest_dir.mkdir(parents=True)
            note = src_dir / "misplaced.md"
            note.write_text("---\ntitle: Test\n---\n", encoding="utf-8")

            proposals = [
                {
                    "path": str(note),
                    "title": "Test",
                    "current_folder": "Development",
                    "proposed_folder": "ML-AI",
                }
            ]
            with patch("bookmark_tools.search.refresh_search_index"):
                moved, errors = apply_reclassifications(
                    proposals, bookmarks_dir=bookmarks_dir
                )

            self.assertEqual(moved, 1)
            self.assertEqual(errors, [])
            self.assertFalse(note.exists())
            self.assertTrue((dest_dir / "misplaced.md").exists())

    def test_creates_destination_folder_if_missing(self) -> None:
        """It creates the destination folder when it does not exist."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            src_dir = bookmarks_dir / "Development"
            src_dir.mkdir(parents=True)
            note = src_dir / "note.md"
            note.write_text("---\ntitle: Note\n---\n", encoding="utf-8")

            proposals = [
                {
                    "path": str(note),
                    "title": "Note",
                    "current_folder": "Development",
                    "proposed_folder": "NewFolder",
                }
            ]
            with patch("bookmark_tools.search.refresh_search_index"):
                moved, errors = apply_reclassifications(
                    proposals, bookmarks_dir=bookmarks_dir
                )

            self.assertEqual(moved, 1)
            self.assertTrue((bookmarks_dir / "NewFolder" / "note.md").exists())

    def test_renames_on_filename_conflict(self) -> None:
        """It appends a numeric suffix when the destination filename already exists."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            src_dir = bookmarks_dir / "Development"
            dest_dir = bookmarks_dir / "ML-AI"
            src_dir.mkdir(parents=True)
            dest_dir.mkdir(parents=True)
            # Existing file at destination
            (dest_dir / "note.md").write_text("existing", encoding="utf-8")
            # Source file with the same name
            src_note = src_dir / "note.md"
            src_note.write_text("new content", encoding="utf-8")

            proposals = [
                {
                    "path": str(src_note),
                    "title": "Note",
                    "current_folder": "Development",
                    "proposed_folder": "ML-AI",
                }
            ]
            with patch("bookmark_tools.search.refresh_search_index"):
                moved, errors = apply_reclassifications(
                    proposals, bookmarks_dir=bookmarks_dir
                )

            self.assertEqual(moved, 1)
            self.assertTrue((dest_dir / "note-2.md").exists())
            self.assertEqual((dest_dir / "note.md").read_text(), "existing")

    def test_returns_empty_on_no_proposals(self) -> None:
        """It returns (0, []) when no proposals are given."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            bookmarks_dir.mkdir()
            moved, errors = apply_reclassifications([], bookmarks_dir=bookmarks_dir)
        self.assertEqual(moved, 0)
        self.assertEqual(errors, [])

    def test_reports_error_for_missing_source(self) -> None:
        """It records an error when the source file does not exist."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks"
            bookmarks_dir.mkdir()
            proposals = [
                {
                    "path": str(bookmarks_dir / "missing.md"),
                    "title": "Missing",
                    "current_folder": "Development",
                    "proposed_folder": "ML-AI",
                }
            ]
            moved, errors = apply_reclassifications(
                proposals, bookmarks_dir=bookmarks_dir
            )
        self.assertEqual(moved, 0)
        self.assertEqual(len(errors), 1)
        self.assertIn("missing.md", errors[0]["path"])


if __name__ == "__main__":
    unittest.main()
