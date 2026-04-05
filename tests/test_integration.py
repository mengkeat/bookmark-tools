from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from bookmark_tools.cli import BookmarkExistsError, build_note, main, _read_urls_from_file


SAMPLE_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Sample Page Title</title>
    <meta name="description" content="A sample page for integration testing.">
    <meta property="og:title" content="Sample OG Title">
</head>
<body>
<p>This is the body content of the sample page. It contains enough text for
classification and summary generation. Machine learning and neural networks
are discussed here for topic inference.</p>
</body>
</html>"""


SAMPLE_LLM_RESPONSE = {
    "choices": [
        {
            "message": {
                "content": json.dumps(
                    {
                        "title": "Sample OG Title",
                        "type": "article",
                        "tags": ["machine-learning", "neural-networks"],
                        "language": "en",
                        "related": ["ml", "deep-learning"],
                        "parent_topic": "Machine Learning",
                        "description": "A sample page for integration testing.",
                        "summary": "LLM generated summary of the sample page.",
                        "folder": "ML-AI",
                    }
                )
            }
        }
    ]
}


def _fake_urlopen(request, *, timeout=None):
    """Simulate urlopen for both page fetch and LLM API calls."""
    url = request.full_url if hasattr(request, "full_url") else str(request)

    if "/chat/completions" in url:
        body = json.dumps(SAMPLE_LLM_RESPONSE).encode("utf-8")
    else:
        body = SAMPLE_HTML.encode("utf-8")

    class FakeResponse:
        def __init__(self, data, url):
            self._data = data
            self._url = url
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


class _FakeHeaders:
    def get_content_charset(self):
        return "utf-8"


def _setup_vault(tmp: str) -> tuple[Path, Path]:
    """Create a minimal vault structure for testing."""
    vault_dir = Path(tmp) / "Vault"
    bookmarks_dir = vault_dir / "Bookmarks"
    ml_dir = bookmarks_dir / "ML-AI"
    dev_dir = bookmarks_dir / "Development"
    ml_dir.mkdir(parents=True)
    dev_dir.mkdir(parents=True)

    # Write an existing note for similarity matching
    existing_note = ml_dir / "intro-to-ml.md"
    existing_note.write_text(
        "---\n"
        "title: Intro to Machine Learning\n"
        "url: https://example.com/intro-ml\n"
        "type: article\n"
        "tags: [machine-learning, intro]\n"
        "language: en\n"
        "related: [ml]\n"
        "parent_topic: Machine Learning\n"
        "description: Introduction to ML concepts\n"
        "visibility: private\n"
        "---\n\n"
        "Summary:\nA beginner guide to machine learning concepts.\n",
        encoding="utf-8",
    )
    return vault_dir, bookmarks_dir


class IntegrationBuildNoteTest(unittest.TestCase):
    """Integration tests for the full build_note pipeline with mocked HTTP."""

    def test_build_note_with_llm_classification(self) -> None:
        """Full pipeline with LLM produces a well-formed note at the right path."""
        with TemporaryDirectory() as tmp:
            vault_dir, bookmarks_dir = _setup_vault(tmp)
            env = {
                "VAULT_PATH": str(vault_dir),
                "BOOKMARKS_DIR": str(bookmarks_dir),
                "BOOKMARK_LLM_API_KEY": "test-key",
                "BOOKMARK_LLM_MODEL": "test-model",
                "BOOKMARK_LLM_BASE_URL": "https://fake-llm.test/v1",
            }
            with (
                patch.dict(os.environ, env, clear=True),
                patch(
                    "bookmark_tools.fetch.urllib.request.urlopen",
                    side_effect=lambda req, **kw: _fake_urlopen(req, **kw),
                ),
                patch(
                    "bookmark_tools.classify.urllib.request.urlopen",
                    side_effect=lambda req, **kw: _fake_urlopen(req, **kw),
                ),
                patch("bookmark_tools.summarize.shutil.which", return_value=None),
                patch("bookmark_tools.summarize.summarize_with_llm", return_value=None),
            ):
                target_path, note_text, folder_message = build_note(
                    "https://example.com/sample-page", allow_new_subfolder=True
                )

            # Verify target path is under the ML-AI folder
            self.assertTrue(
                str(target_path).startswith(str(bookmarks_dir / "ML-AI")),
                f"Expected path under ML-AI, got {target_path}",
            )
            self.assertTrue(str(target_path).endswith(".md"))

            # Verify the rendered note has correct frontmatter
            self.assertIn("title: Sample OG Title", note_text)
            self.assertIn("type: article", note_text)
            self.assertIn("tags: [machine-learning, neural-networks]", note_text)
            self.assertIn("language: en", note_text)
            self.assertIn("parent_topic: Machine Learning", note_text)
            self.assertIn("---", note_text)
            self.assertIn("Summary:", note_text)

    def test_build_note_with_heuristic_fallback(self) -> None:
        """Full pipeline without LLM falls back to heuristic classification."""
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
                target_path, note_text, folder_message = build_note(
                    "https://example.com/sample-page", allow_new_subfolder=True
                )

            # Should still produce valid output with heuristic fallback
            self.assertTrue(str(target_path).endswith(".md"))
            self.assertIn("---", note_text)
            self.assertIn("type: article", note_text)
            self.assertIn("Summary:", note_text)

    def test_build_note_rejects_duplicate_url(self) -> None:
        """Pipeline exits when the URL is already bookmarked."""
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
            ):
                with self.assertRaises(BookmarkExistsError) as ctx:
                    build_note("https://example.com/intro-ml", allow_new_subfolder=True)
                self.assertIn("already exists", str(ctx.exception))

    def test_build_note_disallow_new_subfolder(self) -> None:
        """Pipeline falls back to existing folder when new subfolder is disallowed."""
        llm_response_new_folder = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "title": "Sample OG Title",
                                "type": "article",
                                "tags": ["sample"],
                                "language": "en",
                                "related": ["test"],
                                "parent_topic": "New Topic",
                                "description": "Test page.",
                                "summary": "Summary.",
                                "folder": "ML-AI/NewSubfolder",
                            }
                        )
                    }
                }
            ]
        }

        def urlopen_new_folder(request, **kw):
            url = request.full_url if hasattr(request, "full_url") else str(request)
            if "/chat/completions" in url:
                body = json.dumps(llm_response_new_folder).encode("utf-8")
            else:
                body = SAMPLE_HTML.encode("utf-8")

            class FakeResp:
                def __init__(self, d, u):
                    self._data, self._url = d, u
                    self.headers = _FakeHeaders()

                def read(self, n=-1):
                    return self._data if n == -1 else self._data[:n]

                def geturl(self):
                    return self._url

                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    pass

            return FakeResp(body, url)

        with TemporaryDirectory() as tmp:
            vault_dir, bookmarks_dir = _setup_vault(tmp)
            env = {
                "VAULT_PATH": str(vault_dir),
                "BOOKMARKS_DIR": str(bookmarks_dir),
                "BOOKMARK_LLM_API_KEY": "test-key",
                "BOOKMARK_LLM_BASE_URL": "https://fake-llm.test/v1",
            }
            with (
                patch.dict(os.environ, env, clear=True),
                patch(
                    "bookmark_tools.fetch.urllib.request.urlopen",
                    side_effect=urlopen_new_folder,
                ),
                patch(
                    "bookmark_tools.classify.urllib.request.urlopen",
                    side_effect=urlopen_new_folder,
                ),
                patch("bookmark_tools.summarize.shutil.which", return_value=None),
                patch("bookmark_tools.summarize.summarize_with_llm", return_value=None),
            ):
                target_path, note_text, folder_message = build_note(
                    "https://example.com/new-page", allow_new_subfolder=False
                )

            # Should fall back to ML-AI, not ML-AI/NewSubfolder
            self.assertIn("ML-AI", str(target_path))
            self.assertNotIn("NewSubfolder", str(target_path))


class IntegrationCLIMainTest(unittest.TestCase):
    """Integration tests for the CLI main() function."""

    def test_dry_run_prints_note_without_writing(self) -> None:
        """--dry-run prints the note to stdout but does not create a file."""
        with TemporaryDirectory() as tmp:
            vault_dir, bookmarks_dir = _setup_vault(tmp)
            env = {
                "VAULT_PATH": str(vault_dir),
                "BOOKMARKS_DIR": str(bookmarks_dir),
            }
            with (
                patch.dict(os.environ, env, clear=True),
                patch(
                    "sys.argv",
                    ["bookmark", "https://example.com/dry-run-test", "--dry-run"],
                ),
                patch(
                    "bookmark_tools.fetch.urllib.request.urlopen",
                    side_effect=lambda req, **kw: _fake_urlopen(req, **kw),
                ),
                patch("bookmark_tools.summarize.shutil.which", return_value=None),
                patch("builtins.print") as mock_print,
            ):
                exit_code = main()

            self.assertEqual(exit_code, 0)
            printed = " ".join(str(c) for c in mock_print.call_args_list)
            self.assertIn("Target:", printed)

            # Verify no new files were created
            new_notes = list(bookmarks_dir.rglob("*dry-run*"))
            self.assertEqual(new_notes, [])

    def test_main_writes_note_to_disk(self) -> None:
        """Normal invocation creates a markdown file in the vault."""
        with TemporaryDirectory() as tmp:
            vault_dir, bookmarks_dir = _setup_vault(tmp)
            env = {
                "VAULT_PATH": str(vault_dir),
                "BOOKMARKS_DIR": str(bookmarks_dir),
            }
            with (
                patch.dict(os.environ, env, clear=True),
                patch(
                    "sys.argv",
                    ["bookmark", "https://example.com/write-test"],
                ),
                patch(
                    "bookmark_tools.fetch.urllib.request.urlopen",
                    side_effect=lambda req, **kw: _fake_urlopen(req, **kw),
                ),
                patch("bookmark_tools.summarize.shutil.which", return_value=None),
            ):
                exit_code = main()

            self.assertEqual(exit_code, 0)
            all_notes = list(bookmarks_dir.rglob("*.md"))
            # Should have the existing note + the new one
            self.assertGreaterEqual(len(all_notes), 2)
            new_notes = [n for n in all_notes if n.name != "intro-to-ml.md"]
            self.assertTrue(len(new_notes) >= 1)
            content = new_notes[0].read_text(encoding="utf-8")
            self.assertIn("---", content)
            self.assertIn("Summary:", content)


class InteractiveModeTest(unittest.TestCase):
    """Tests for interactive classification review."""

    def test_interactive_accepts_on_yes(self) -> None:
        """--interactive writes the note when user confirms with 'y'."""
        with TemporaryDirectory() as tmp:
            vault_dir, bookmarks_dir = _setup_vault(tmp)
            env = {
                "VAULT_PATH": str(vault_dir),
                "BOOKMARKS_DIR": str(bookmarks_dir),
            }
            with (
                patch.dict(os.environ, env, clear=True),
                patch(
                    "sys.argv",
                    [
                        "bookmark",
                        "https://example.com/interactive-test",
                        "--interactive",
                    ],
                ),
                patch(
                    "bookmark_tools.fetch.urllib.request.urlopen",
                    side_effect=lambda req, **kw: _fake_urlopen(req, **kw),
                ),
                patch("bookmark_tools.summarize.shutil.which", return_value=None),
                patch("builtins.input", return_value="y"),
            ):
                exit_code = main()

            self.assertEqual(exit_code, 0)
            all_notes = list(bookmarks_dir.rglob("*.md"))
            self.assertGreaterEqual(len(all_notes), 2)

    def test_interactive_skips_on_no(self) -> None:
        """--interactive skips writing when user declines."""
        with TemporaryDirectory() as tmp:
            vault_dir, bookmarks_dir = _setup_vault(tmp)
            env = {
                "VAULT_PATH": str(vault_dir),
                "BOOKMARKS_DIR": str(bookmarks_dir),
            }
            with (
                patch.dict(os.environ, env, clear=True),
                patch(
                    "sys.argv",
                    [
                        "bookmark",
                        "https://example.com/interactive-skip",
                        "--interactive",
                    ],
                ),
                patch(
                    "bookmark_tools.fetch.urllib.request.urlopen",
                    side_effect=lambda req, **kw: _fake_urlopen(req, **kw),
                ),
                patch("bookmark_tools.summarize.shutil.which", return_value=None),
                patch("builtins.input", return_value="n"),
                patch("builtins.print"),
            ):
                exit_code = main()

            self.assertEqual(exit_code, 1)
            # Only the original note should exist
            all_notes = [
                n for n in bookmarks_dir.rglob("*.md") if n.name != "intro-to-ml.md"
            ]
            self.assertEqual(len(all_notes), 0)

    def test_interactive_accepts_on_empty_input(self) -> None:
        """--interactive defaults to accept on empty input (pressing Enter)."""
        with TemporaryDirectory() as tmp:
            vault_dir, bookmarks_dir = _setup_vault(tmp)
            env = {
                "VAULT_PATH": str(vault_dir),
                "BOOKMARKS_DIR": str(bookmarks_dir),
            }
            with (
                patch.dict(os.environ, env, clear=True),
                patch(
                    "sys.argv",
                    ["bookmark", "https://example.com/enter-test", "--interactive"],
                ),
                patch(
                    "bookmark_tools.fetch.urllib.request.urlopen",
                    side_effect=lambda req, **kw: _fake_urlopen(req, **kw),
                ),
                patch("bookmark_tools.summarize.shutil.which", return_value=None),
                patch("builtins.input", return_value=""),
            ):
                exit_code = main()

            self.assertEqual(exit_code, 0)


class ArchiveContentTest(unittest.TestCase):
    """Tests for page content archiving."""

    def test_archive_saves_cleaned_content(self) -> None:
        """--archive saves a .content.md file alongside the bookmark note."""
        with TemporaryDirectory() as tmp:
            vault_dir, bookmarks_dir = _setup_vault(tmp)
            env = {
                "VAULT_PATH": str(vault_dir),
                "BOOKMARKS_DIR": str(bookmarks_dir),
            }
            with (
                patch.dict(os.environ, env, clear=True),
                patch(
                    "sys.argv",
                    ["bookmark", "https://example.com/archive-test", "--archive"],
                ),
                patch(
                    "bookmark_tools.fetch.urllib.request.urlopen",
                    side_effect=lambda req, **kw: _fake_urlopen(req, **kw),
                ),
                patch("bookmark_tools.summarize.shutil.which", return_value=None),
            ):
                exit_code = main()

            self.assertEqual(exit_code, 0)
            archive_files = list(bookmarks_dir.rglob("*.content.md"))
            self.assertEqual(len(archive_files), 1)
            content = archive_files[0].read_text(encoding="utf-8")
            self.assertIn("body content", content)

    def test_archive_not_created_without_flag(self) -> None:
        """No archive file is created when --archive is not set."""
        with TemporaryDirectory() as tmp:
            vault_dir, bookmarks_dir = _setup_vault(tmp)
            env = {
                "VAULT_PATH": str(vault_dir),
                "BOOKMARKS_DIR": str(bookmarks_dir),
            }
            with (
                patch.dict(os.environ, env, clear=True),
                patch(
                    "sys.argv",
                    ["bookmark", "https://example.com/no-archive-test"],
                ),
                patch(
                    "bookmark_tools.fetch.urllib.request.urlopen",
                    side_effect=lambda req, **kw: _fake_urlopen(req, **kw),
                ),
                patch("bookmark_tools.summarize.shutil.which", return_value=None),
            ):
                exit_code = main()

            self.assertEqual(exit_code, 0)
            archive_files = list(bookmarks_dir.rglob("*.content.md"))
            self.assertEqual(len(archive_files), 0)


class BatchImportTest(unittest.TestCase):
    """Tests for batch URL import functionality."""

    def test_read_urls_from_file_skips_comments_and_blanks(self) -> None:
        """It reads URLs, skipping comments and blank lines."""
        with TemporaryDirectory() as tmp:
            url_file = Path(tmp) / "urls.txt"
            url_file.write_text(
                "# Comment\n"
                "https://example.com/page1\n"
                "\n"
                "https://example.com/page2\n"
                "# Another comment\n"
                "https://example.com/page3\n",
                encoding="utf-8",
            )
            urls = _read_urls_from_file(str(url_file))
        self.assertEqual(
            urls,
            [
                "https://example.com/page1",
                "https://example.com/page2",
                "https://example.com/page3",
            ],
        )

    def test_batch_import_processes_multiple_urls(self) -> None:
        """--file flag processes multiple URLs from a file."""
        with TemporaryDirectory() as tmp:
            vault_dir, bookmarks_dir = _setup_vault(tmp)
            url_file = Path(tmp) / "urls.txt"
            url_file.write_text(
                "https://example.com/batch-page1\nhttps://example.com/batch-page2\n",
                encoding="utf-8",
            )
            env = {
                "VAULT_PATH": str(vault_dir),
                "BOOKMARKS_DIR": str(bookmarks_dir),
            }
            with (
                patch.dict(os.environ, env, clear=True),
                patch(
                    "sys.argv",
                    ["bookmark", "--file", str(url_file), "--dry-run"],
                ),
                patch(
                    "bookmark_tools.fetch.urllib.request.urlopen",
                    side_effect=lambda req, **kw: _fake_urlopen(req, **kw),
                ),
                patch("bookmark_tools.summarize.shutil.which", return_value=None),
            ):
                exit_code = main()

            self.assertEqual(exit_code, 0)

    def test_batch_import_skips_duplicate_urls(self) -> None:
        """Batch import skips URLs that already exist as bookmarks."""
        with TemporaryDirectory() as tmp:
            vault_dir, bookmarks_dir = _setup_vault(tmp)
            url_file = Path(tmp) / "urls.txt"
            url_file.write_text(
                "https://example.com/intro-ml\nhttps://example.com/new-page\n",
                encoding="utf-8",
            )
            env = {
                "VAULT_PATH": str(vault_dir),
                "BOOKMARKS_DIR": str(bookmarks_dir),
            }
            with (
                patch.dict(os.environ, env, clear=True),
                patch(
                    "sys.argv",
                    ["bookmark", "--file", str(url_file)],
                ),
                patch(
                    "bookmark_tools.fetch.urllib.request.urlopen",
                    side_effect=lambda req, **kw: _fake_urlopen(req, **kw),
                ),
                patch("bookmark_tools.summarize.shutil.which", return_value=None),
            ):
                exit_code = main()

            # Should succeed (not all failed)
            self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
