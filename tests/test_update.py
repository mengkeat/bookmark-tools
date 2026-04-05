from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from bookmark_tools.update import find_note_by_url, update_bookmark


SAMPLE_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Updated Page Title</title>
    <meta name="description" content="Updated description for the page.">
    <meta property="og:title" content="Updated OG Title">
</head>
<body>
<p>Updated body content about machine learning and neural networks.</p>
</body>
</html>"""


class _FakeHeaders:
    def get_content_charset(self):
        return "utf-8"


def _fake_urlopen(request, *, timeout=None):
    url = request.full_url if hasattr(request, "full_url") else str(request)
    body = SAMPLE_HTML.encode("utf-8")

    class FakeResponse:
        def __init__(self, data, url):
            self._data, self._url = data, url
            self.headers = _FakeHeaders()

        def read(self, n=-1):
            return self._data if n == -1 else self._data[:n]

        def geturl(self):
            return self._url

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    return FakeResponse(body, url)


def _setup_vault(tmp: str) -> tuple[Path, Path]:
    """Create a vault with one existing bookmark."""
    vault_dir = Path(tmp) / "Vault"
    bookmarks_dir = vault_dir / "Bookmarks"
    ml_dir = bookmarks_dir / "ML-AI"
    dev_dir = bookmarks_dir / "Development"
    ml_dir.mkdir(parents=True)
    dev_dir.mkdir(parents=True)

    existing_note = ml_dir / "sample-article.md"
    existing_note.write_text(
        "---\n"
        "title: Original Title\n"
        "url: https://example.com/sample\n"
        "type: article\n"
        "tags: [python]\n"
        "created: 2025-01-15\n"
        "last_updated: 2025-01-15\n"
        "language: en\n"
        "related: [ml]\n"
        "parent_topic: Machine Learning\n"
        "description: Original description\n"
        "visibility: private\n"
        "---\n\n"
        "Summary:\nOriginal summary.\n",
        encoding="utf-8",
    )
    return vault_dir, bookmarks_dir


class FindNoteByUrlTest(unittest.TestCase):
    def test_finds_existing_note(self) -> None:
        """It locates a note by its URL."""
        with TemporaryDirectory() as tmp:
            _, bookmarks_dir = _setup_vault(tmp)
            result = find_note_by_url(
                "https://example.com/sample", bookmarks_dir=bookmarks_dir
            )
        self.assertIsNotNone(result)
        self.assertEqual(result.name, "sample-article.md")

    def test_returns_none_for_unknown_url(self) -> None:
        """It returns None when the URL is not bookmarked."""
        with TemporaryDirectory() as tmp:
            _, bookmarks_dir = _setup_vault(tmp)
            result = find_note_by_url(
                "https://example.com/unknown", bookmarks_dir=bookmarks_dir
            )
        self.assertIsNone(result)


class UpdateBookmarkTest(unittest.TestCase):
    def test_update_refreshes_content(self) -> None:
        """It re-fetches and updates the bookmark note content."""
        with TemporaryDirectory() as tmp:
            vault_dir, bookmarks_dir = _setup_vault(tmp)
            env = {
                "VAULT_PATH": str(vault_dir),
                "BOOKMARKS_DIR": str(bookmarks_dir),
            }
            with (
                patch.dict(os.environ, env, clear=True),
                patch(
                    "bookmark_tools.fetch.urllib.request.urlopen",
                    side_effect=lambda req, **kw: _fake_urlopen(req, **kw),
                ),
                patch("bookmark_tools.summarize.shutil.which", return_value=None),
            ):
                result = update_bookmark(
                    "https://example.com/sample",
                    bookmarks_dir=bookmarks_dir,
                    dry_run=True,
                )

        self.assertIsNotNone(result)
        note_path, note_text = result
        self.assertEqual(note_path.name, "sample-article.md")
        # Should contain updated title from re-fetch
        self.assertIn("Updated", note_text)
        # Should preserve original created date
        self.assertIn("created: 2025-01-15", note_text)

    def test_update_returns_none_for_missing_url(self) -> None:
        """It returns None when the URL is not bookmarked."""
        with TemporaryDirectory() as tmp:
            vault_dir, bookmarks_dir = _setup_vault(tmp)
            env = {
                "VAULT_PATH": str(vault_dir),
                "BOOKMARKS_DIR": str(bookmarks_dir),
            }
            with patch.dict(os.environ, env, clear=True):
                result = update_bookmark(
                    "https://example.com/nonexistent",
                    bookmarks_dir=bookmarks_dir,
                )
        self.assertIsNone(result)

    def test_update_writes_to_disk_when_not_dry_run(self) -> None:
        """It writes the updated note to disk."""
        with TemporaryDirectory() as tmp:
            vault_dir, bookmarks_dir = _setup_vault(tmp)
            env = {
                "VAULT_PATH": str(vault_dir),
                "BOOKMARKS_DIR": str(bookmarks_dir),
            }
            with (
                patch.dict(os.environ, env, clear=True),
                patch(
                    "bookmark_tools.fetch.urllib.request.urlopen",
                    side_effect=lambda req, **kw: _fake_urlopen(req, **kw),
                ),
                patch("bookmark_tools.summarize.shutil.which", return_value=None),
            ):
                result = update_bookmark(
                    "https://example.com/sample",
                    bookmarks_dir=bookmarks_dir,
                    dry_run=False,
                )

            self.assertIsNotNone(result)
            note_path, _ = result
            content = note_path.read_text(encoding="utf-8")
            self.assertIn("Updated", content)
            self.assertIn("created: 2025-01-15", content)


class SingleVaultScanTest(unittest.TestCase):
    def test_update_bookmark_scans_vault_once(self) -> None:
        """update_bookmark performs only one vault scan (via collect_existing_notes)."""
        with TemporaryDirectory() as tmp:
            vault_dir, bookmarks_dir = _setup_vault(tmp)
            env = {
                "VAULT_PATH": str(vault_dir),
                "BOOKMARKS_DIR": str(bookmarks_dir),
            }
            with (
                patch.dict(os.environ, env, clear=True),
                patch(
                    "bookmark_tools.fetch.urllib.request.urlopen",
                    side_effect=lambda req, **kw: _fake_urlopen(req, **kw),
                ),
                patch("bookmark_tools.summarize.shutil.which", return_value=None),
                patch(
                    "bookmark_tools.update.collect_existing_notes",
                    wraps=__import__(
                        "bookmark_tools.vault_profile", fromlist=["collect_existing_notes"]
                    ).collect_existing_notes,
                ) as mock_collect,
            ):
                update_bookmark(
                    "https://example.com/sample",
                    bookmarks_dir=bookmarks_dir,
                    dry_run=True,
                )

        mock_collect.assert_called_once()


if __name__ == "__main__":
    unittest.main()
