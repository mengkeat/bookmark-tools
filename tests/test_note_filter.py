from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from bookmark_tools.note_filter import (
    ARCHIVE_SIDECAR_SUFFIX,
    is_archive_sidecar,
    iter_bookmark_note_paths,
)


class IsArchiveSidecarTest(unittest.TestCase):
    def test_content_md_suffix_detected(self) -> None:
        self.assertTrue(is_archive_sidecar(Path("note.content.md")))

    def test_regular_note_not_detected(self) -> None:
        self.assertFalse(is_archive_sidecar(Path("note.md")))

    def test_nested_path_detected(self) -> None:
        self.assertTrue(is_archive_sidecar(Path("Bookmarks/Dev/note.content.md")))

    def test_content_in_middle_not_detected(self) -> None:
        """Only the final suffix matters; 'content' in the stem is not a sidecar."""
        self.assertFalse(is_archive_sidecar(Path("content-overview.md")))

    def test_suffix_constant_matches(self) -> None:
        self.assertEqual(ARCHIVE_SIDECAR_SUFFIX, ".content.md")


class IterBookmarkNotePathsTest(unittest.TestCase):
    def test_yields_regular_notes(self) -> None:
        with TemporaryDirectory() as tmp:
            bm = Path(tmp)
            (bm / "a.md").write_text("---\nurl: x\n---\n", encoding="utf-8")
            (bm / "b.md").write_text("---\nurl: y\n---\n", encoding="utf-8")
            paths = list(iter_bookmark_note_paths(bm))
        self.assertEqual(len(paths), 2)

    def test_excludes_archive_sidecars(self) -> None:
        with TemporaryDirectory() as tmp:
            bm = Path(tmp)
            (bm / "note.md").write_text("---\nurl: x\n---\n", encoding="utf-8")
            (bm / "note.content.md").write_text("archived", encoding="utf-8")
            paths = list(iter_bookmark_note_paths(bm))
        self.assertEqual(len(paths), 1)
        self.assertTrue(paths[0].name, "note.md")

    def test_recursive_by_default(self) -> None:
        with TemporaryDirectory() as tmp:
            bm = Path(tmp)
            sub = bm / "Sub"
            sub.mkdir()
            (bm / "root.md").write_text("---\nurl: x\n---\n", encoding="utf-8")
            (sub / "nested.md").write_text("---\nurl: y\n---\n", encoding="utf-8")
            paths = list(iter_bookmark_note_paths(bm))
        self.assertEqual(len(paths), 2)

    def test_non_recursive_mode(self) -> None:
        with TemporaryDirectory() as tmp:
            bm = Path(tmp)
            sub = bm / "Sub"
            sub.mkdir()
            (bm / "root.md").write_text("---\nurl: x\n---\n", encoding="utf-8")
            (sub / "nested.md").write_text("---\nurl: y\n---\n", encoding="utf-8")
            paths = list(iter_bookmark_note_paths(bm, recursive=False))
        self.assertEqual(len(paths), 1)
        self.assertEqual(paths[0].name, "root.md")

    def test_empty_directory(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = list(iter_bookmark_note_paths(Path(tmp)))
        self.assertEqual(paths, [])

    def test_non_md_files_ignored(self) -> None:
        with TemporaryDirectory() as tmp:
            bm = Path(tmp)
            (bm / "data.json").write_text("{}", encoding="utf-8")
            (bm / "image.png").write_bytes(b"\x89PNG")
            paths = list(iter_bookmark_note_paths(bm))
        self.assertEqual(paths, [])

    def test_sidecar_excluded_in_recursive_mode(self) -> None:
        with TemporaryDirectory() as tmp:
            bm = Path(tmp)
            sub = bm / "Dev"
            sub.mkdir()
            (sub / "real.md").write_text("---\nurl: x\n---\n", encoding="utf-8")
            (sub / "real.content.md").write_text("archive", encoding="utf-8")
            paths = list(iter_bookmark_note_paths(bm))
        self.assertEqual(len(paths), 1)
        self.assertEqual(paths[0].name, "real.md")


if __name__ == "__main__":
    unittest.main()
