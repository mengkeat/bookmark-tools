from __future__ import annotations

import json
import urllib.error
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
import unittest

from bookmark_tools.check import check_bookmarks, check_url, delete_broken, tag_broken


class CheckUrlTest(unittest.TestCase):
    def test_returns_200_for_healthy_url(self) -> None:
        """It returns (200, 'OK') for a reachable URL."""
        fake_response = MagicMock()
        fake_response.status = 200
        fake_response.__enter__ = lambda s: s
        fake_response.__exit__ = MagicMock(return_value=False)
        with patch(
            "bookmark_tools.check.urllib.request.urlopen", return_value=fake_response
        ):
            status, reason = check_url("https://example.com")
        self.assertEqual(status, 200)
        self.assertEqual(reason, "OK")

    def test_returns_404_for_not_found(self) -> None:
        """It returns (404, reason) for HTTP 404."""
        exc = urllib.error.HTTPError("https://example.com", 404, "Not Found", {}, None)
        with patch("bookmark_tools.check.urllib.request.urlopen", side_effect=exc):
            status, reason = check_url("https://example.com")
        self.assertEqual(status, 404)

    def test_returns_zero_for_connection_error(self) -> None:
        """It returns (0, error_message) for connection failures."""
        exc = urllib.error.URLError("Connection refused")
        with patch("bookmark_tools.check.urllib.request.urlopen", side_effect=exc):
            status, reason = check_url("https://example.com")
        self.assertEqual(status, 0)
        self.assertIn("Connection refused", reason)

    def test_falls_back_to_get_when_head_returns_405(self) -> None:
        """It retries with GET when HEAD returns 405 Method Not Allowed."""
        head_exc = urllib.error.HTTPError(
            "https://example.com", 405, "Method Not Allowed", {}, None
        )
        fake_response = MagicMock()
        fake_response.status = 200
        fake_response.__enter__ = lambda s: s
        fake_response.__exit__ = MagicMock(return_value=False)

        call_count = 0

        def side_effect(request, **kw):
            nonlocal call_count
            call_count += 1
            if request.get_method() == "HEAD":
                raise head_exc
            return fake_response

        with patch(
            "bookmark_tools.check.urllib.request.urlopen", side_effect=side_effect
        ):
            status, reason = check_url("https://example.com")

        self.assertEqual(status, 200)
        self.assertEqual(reason, "OK")
        self.assertEqual(call_count, 2)

    def test_returns_405_when_get_also_fails(self) -> None:
        """It reports the GET error code when both HEAD and GET fail."""
        head_exc = urllib.error.HTTPError(
            "https://example.com", 405, "Method Not Allowed", {}, None
        )
        get_exc = urllib.error.HTTPError(
            "https://example.com", 403, "Forbidden", {}, None
        )

        def side_effect(request, **kw):
            if request.get_method() == "HEAD":
                raise head_exc
            raise get_exc

        with patch(
            "bookmark_tools.check.urllib.request.urlopen", side_effect=side_effect
        ):
            status, reason = check_url("https://example.com")

        self.assertEqual(status, 403)

    def test_returns_zero_for_timeout(self) -> None:
        """It returns (0, ...) when the request times out."""
        with patch(
            "bookmark_tools.check.urllib.request.urlopen",
            side_effect=TimeoutError("timed out"),
        ):
            status, reason = check_url("https://example.com")
        self.assertEqual(status, 0)
        self.assertIn("timed out", reason)

    def test_returns_zero_for_ssl_error(self) -> None:
        """It returns (0, ...) for SSL/certificate errors (reported as URLError)."""
        import ssl

        ssl_exc = urllib.error.URLError(
            ssl.SSLCertVerificationError("cert verify failed")
        )
        with patch("bookmark_tools.check.urllib.request.urlopen", side_effect=ssl_exc):
            status, reason = check_url("https://example.com")
        self.assertEqual(status, 0)

    def test_returns_500_for_server_error(self) -> None:
        """It returns (500, reason) for HTTP 500 Internal Server Error."""
        exc = urllib.error.HTTPError(
            "https://example.com", 500, "Internal Server Error", {}, None
        )
        with patch("bookmark_tools.check.urllib.request.urlopen", side_effect=exc):
            status, reason = check_url("https://example.com")
        self.assertEqual(status, 500)


class CheckBookmarksTest(unittest.TestCase):
    def test_reports_broken_links(self) -> None:
        """It finds and reports broken bookmark URLs."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks" / "Test"
            bookmarks_dir.mkdir(parents=True)

            # Healthy note
            (bookmarks_dir / "good.md").write_text(
                "---\nurl: https://example.com/good\ntitle: Good Page\n---\n",
                encoding="utf-8",
            )
            # Broken note
            (bookmarks_dir / "broken.md").write_text(
                "---\nurl: https://example.com/broken\ntitle: Broken Page\n---\n",
                encoding="utf-8",
            )

            def fake_urlopen(req, **kw):
                url = req.full_url if hasattr(req, "full_url") else str(req)
                if "broken" in url:
                    raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
                resp = MagicMock()
                resp.status = 200
                resp.__enter__ = lambda s: s
                resp.__exit__ = MagicMock(return_value=False)
                return resp

            with patch(
                "bookmark_tools.check.urllib.request.urlopen", side_effect=fake_urlopen
            ):
                problems = check_bookmarks(bookmarks_dir=Path(tmp) / "Bookmarks")

        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]["title"], "Broken Page")
        self.assertEqual(problems[0]["status"], 404)

    def test_returns_empty_when_all_healthy(self) -> None:
        """It returns an empty list when all URLs are reachable."""
        with TemporaryDirectory() as tmp:
            bookmarks_dir = Path(tmp) / "Bookmarks" / "Test"
            bookmarks_dir.mkdir(parents=True)

            (bookmarks_dir / "good.md").write_text(
                "---\nurl: https://example.com/good\ntitle: Good\n---\n",
                encoding="utf-8",
            )

            fake_response = MagicMock()
            fake_response.status = 200
            fake_response.__enter__ = lambda s: s
            fake_response.__exit__ = MagicMock(return_value=False)
            with patch(
                "bookmark_tools.check.urllib.request.urlopen",
                return_value=fake_response,
            ):
                problems = check_bookmarks(bookmarks_dir=Path(tmp) / "Bookmarks")

        self.assertEqual(problems, [])


class DeleteBrokenTest(unittest.TestCase):
    def _make_problem(self, path: Path) -> dict:
        return {
            "path": path,
            "url": "https://example.com",
            "title": "Test",
            "status": 404,
            "reason": "Not Found",
        }

    def test_deletes_broken_file(self) -> None:
        """It deletes broken bookmark files."""
        with TemporaryDirectory() as tmp:
            note = Path(tmp) / "broken.md"
            note.write_text("---\nurl: https://example.com\n---\n", encoding="utf-8")
            deleted, errors = delete_broken([self._make_problem(note)])
            self.assertEqual(deleted, 1)
            self.assertEqual(errors, [])
            self.assertFalse(note.exists())

    def test_dry_run_does_not_delete(self) -> None:
        """It reports what would be deleted without removing files."""
        with TemporaryDirectory() as tmp:
            note = Path(tmp) / "broken.md"
            note.write_text("content", encoding="utf-8")
            deleted, errors = delete_broken([self._make_problem(note)], dry_run=True)
            self.assertEqual(deleted, 1)
            self.assertTrue(note.exists())

    def test_returns_zero_for_empty_list(self) -> None:
        """It handles an empty problem list."""
        deleted, errors = delete_broken([])
        self.assertEqual(deleted, 0)
        self.assertEqual(errors, [])


class TagBrokenTest(unittest.TestCase):
    def _make_problem(self, path: Path) -> dict:
        return {
            "path": path,
            "url": "https://example.com",
            "title": "Test",
            "status": 404,
            "reason": "Not Found",
        }

    def test_adds_broken_tag_to_existing_tags_list(self) -> None:
        """It appends 'broken' to an existing tags list."""
        with TemporaryDirectory() as tmp:
            note = Path(tmp) / "note.md"
            note.write_text(
                "---\ntags: [python]\nurl: https://example.com\n---\n", encoding="utf-8"
            )
            tagged = tag_broken([self._make_problem(note)])
            self.assertEqual(tagged, 1)
            content = note.read_text()
            self.assertIn("broken", content)

    def test_adds_tags_line_when_none_exists(self) -> None:
        """It creates a tags field when the note has none."""
        with TemporaryDirectory() as tmp:
            note = Path(tmp) / "note.md"
            note.write_text("---\nurl: https://example.com\n---\n", encoding="utf-8")
            tagged = tag_broken([self._make_problem(note)])
            self.assertEqual(tagged, 1)
            self.assertIn("broken", note.read_text())

    def test_does_not_double_tag(self) -> None:
        """It skips notes that already have the broken tag."""
        with TemporaryDirectory() as tmp:
            note = Path(tmp) / "note.md"
            note.write_text(
                "---\ntags: [broken]\nurl: https://example.com\n---\n", encoding="utf-8"
            )
            tagged = tag_broken([self._make_problem(note)])
            self.assertEqual(tagged, 0)

    def test_dry_run_does_not_write(self) -> None:
        """It reports would-be changes without modifying files."""
        with TemporaryDirectory() as tmp:
            note = Path(tmp) / "note.md"
            original = "---\ntags: [python]\nurl: https://example.com\n---\n"
            note.write_text(original, encoding="utf-8")
            tagged = tag_broken([self._make_problem(note)], dry_run=True)
            self.assertEqual(tagged, 1)
            self.assertEqual(note.read_text(), original)


class CheckFormatJsonTest(unittest.TestCase):
    def test_json_output_structure(self) -> None:
        """--format json produces a valid JSON array of problem entries."""
        from bookmark_tools.check import main as check_main
        import io

        fake_problems = [
            {
                "path": Path("/tmp/broken.md"),
                "url": "https://example.com/broken",
                "title": "Broken Page",
                "status": 404,
                "reason": "Not Found",
            }
        ]
        with (
            patch("bookmark_tools.check.check_bookmarks", return_value=fake_problems),
            patch("sys.stdout", new_callable=io.StringIO) as mock_stdout,
        ):
            check_main(["--format", "json"])

        output = json.loads(mock_stdout.getvalue())
        self.assertIsInstance(output, list)
        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]["url"], "https://example.com/broken")
        self.assertEqual(output[0]["status"], 404)
        self.assertIn("path", output[0])
        self.assertIn("reason", output[0])

    def test_json_empty_when_no_problems(self) -> None:
        """--format json outputs an empty array when all URLs are healthy."""
        from bookmark_tools.check import main as check_main
        import io

        with (
            patch("bookmark_tools.check.check_bookmarks", return_value=[]),
            patch("sys.stdout", new_callable=io.StringIO) as mock_stdout,
        ):
            result = check_main(["--format", "json"])

        output = json.loads(mock_stdout.getvalue())
        self.assertEqual(output, [])
        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
