from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from bookmark_tools.link import _update_related_field, update_related_backlinks


class UpdateRelatedFieldTest(unittest.TestCase):
    def _write_note(self, tmp: str, content: str) -> Path:
        note_path = Path(tmp) / "test.md"
        note_path.write_text(content, encoding="utf-8")
        return note_path

    def test_adds_topic_to_existing_related(self) -> None:
        """It appends a topic to an existing related list."""
        with TemporaryDirectory() as tmp:
            note = self._write_note(
                tmp,
                "---\ntitle: Test\nrelated: [ml, python]\n---\n\nBody\n",
            )
            modified = _update_related_field(note, "pytorch")
            self.assertTrue(modified)
            content = note.read_text(encoding="utf-8")
            self.assertIn("pytorch", content)
            self.assertIn("ml", content)

    def test_skips_duplicate_topic(self) -> None:
        """It does not add a topic that already exists."""
        with TemporaryDirectory() as tmp:
            note = self._write_note(
                tmp,
                "---\ntitle: Test\nrelated: [ml, python]\n---\n\nBody\n",
            )
            modified = _update_related_field(note, "ml")
            self.assertFalse(modified)

    def test_creates_related_field_when_missing(self) -> None:
        """It adds a related field when none exists."""
        with TemporaryDirectory() as tmp:
            note = self._write_note(
                tmp,
                "---\ntitle: Test\ntags: [python]\n---\n\nBody\n",
            )
            modified = _update_related_field(note, "pytorch")
            self.assertTrue(modified)
            content = note.read_text(encoding="utf-8")
            self.assertIn("related: [pytorch]", content)

    def test_respects_max_related_limit(self) -> None:
        """It does not exceed the maximum related items."""
        with TemporaryDirectory() as tmp:
            items = ", ".join(f"topic{i}" for i in range(6))
            note = self._write_note(
                tmp,
                f"---\ntitle: Test\nrelated: [{items}]\n---\n\nBody\n",
            )
            modified = _update_related_field(note, "extra")
            self.assertFalse(modified)

    def test_skips_non_frontmatter_file(self) -> None:
        """It returns False for files without frontmatter."""
        with TemporaryDirectory() as tmp:
            note = self._write_note(tmp, "Just plain text.\n")
            modified = _update_related_field(note, "test")
            self.assertFalse(modified)


class UpdateRelatedBacklinksTest(unittest.TestCase):
    def test_updates_multiple_notes(self) -> None:
        """It adds backlinks to multiple similar notes."""
        with TemporaryDirectory() as tmp:
            paths: list[Path] = []
            for i in range(3):
                note = Path(tmp) / f"note{i}.md"
                note.write_text(
                    f"---\ntitle: Note {i}\nrelated: [existing]\n---\n\nBody\n",
                    encoding="utf-8",
                )
                paths.append(note)

            modified = update_related_backlinks("new-topic", paths)
            self.assertEqual(len(modified), 3)
            for path in paths:
                content = path.read_text(encoding="utf-8")
                self.assertIn("new-topic", content)

    def test_respects_limit(self) -> None:
        """It only modifies up to `limit` notes."""
        with TemporaryDirectory() as tmp:
            paths: list[Path] = []
            for i in range(5):
                note = Path(tmp) / f"note{i}.md"
                note.write_text(
                    f"---\ntitle: Note {i}\nrelated: [existing]\n---\n\nBody\n",
                    encoding="utf-8",
                )
                paths.append(note)

            modified = update_related_backlinks("new-topic", paths, limit=2)
            self.assertEqual(len(modified), 2)


if __name__ == "__main__":
    unittest.main()
