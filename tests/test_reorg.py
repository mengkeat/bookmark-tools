from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from bookmark_tools.reorg import propose_reclassifications


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


if __name__ == "__main__":
    unittest.main()
