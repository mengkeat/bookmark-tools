from __future__ import annotations

import urllib.error
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
import unittest

from bookmark_tools.check import check_bookmarks, check_url


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


if __name__ == "__main__":
    unittest.main()
