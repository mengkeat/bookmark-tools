from __future__ import annotations

import urllib.error
import urllib.request
import unittest
from unittest.mock import MagicMock, patch

from bookmark_tools.http_retry import urlopen_with_retry


class HttpRetryTest(unittest.TestCase):
    @patch("bookmark_tools.http_retry.time.sleep")
    def test_retries_on_transient_url_error(self, mock_sleep: MagicMock) -> None:
        """It retries on URLError and succeeds on the third attempt."""
        fake_response = MagicMock()
        mock_urlopen = MagicMock(
            side_effect=[
                urllib.error.URLError("Connection refused"),
                urllib.error.URLError("Connection reset"),
                fake_response,
            ]
        )
        with patch("bookmark_tools.http_retry.urllib.request.urlopen", mock_urlopen):
            result = urlopen_with_retry(
                urllib.request.Request("https://example.com"),
                timeout=5,
                max_retries=3,
                base_delay=0.01,
            )
        self.assertIs(result, fake_response)
        self.assertEqual(mock_urlopen.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("bookmark_tools.http_retry.time.sleep")
    def test_retries_on_http_429(self, mock_sleep: MagicMock) -> None:
        """It retries on HTTP 429 rate limit responses."""
        fake_response = MagicMock()
        http_429 = urllib.error.HTTPError(
            "https://example.com", 429, "Too Many Requests", {}, None
        )
        mock_urlopen = MagicMock(side_effect=[http_429, fake_response])
        with patch("bookmark_tools.http_retry.urllib.request.urlopen", mock_urlopen):
            result = urlopen_with_retry(
                urllib.request.Request("https://example.com"),
                timeout=5,
                max_retries=2,
                base_delay=0.01,
            )
        self.assertIs(result, fake_response)

    @patch("bookmark_tools.http_retry.time.sleep")
    def test_retries_on_http_500(self, mock_sleep: MagicMock) -> None:
        """It retries on HTTP 500 server errors."""
        fake_response = MagicMock()
        http_500 = urllib.error.HTTPError(
            "https://example.com", 500, "Internal Server Error", {}, None
        )
        mock_urlopen = MagicMock(side_effect=[http_500, fake_response])
        with patch("bookmark_tools.http_retry.urllib.request.urlopen", mock_urlopen):
            result = urlopen_with_retry(
                urllib.request.Request("https://example.com"),
                timeout=5,
                max_retries=2,
                base_delay=0.01,
            )
        self.assertIs(result, fake_response)

    @patch("bookmark_tools.http_retry.time.sleep")
    def test_does_not_retry_on_http_404(self, mock_sleep: MagicMock) -> None:
        """It does not retry on non-retryable HTTP errors like 404."""
        http_404 = urllib.error.HTTPError(
            "https://example.com", 404, "Not Found", {}, None
        )
        mock_urlopen = MagicMock(side_effect=http_404)
        with patch("bookmark_tools.http_retry.urllib.request.urlopen", mock_urlopen):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urlopen_with_retry(
                    urllib.request.Request("https://example.com"),
                    timeout=5,
                    max_retries=3,
                    base_delay=0.01,
                )
        self.assertEqual(ctx.exception.code, 404)
        self.assertEqual(mock_urlopen.call_count, 1)
        mock_sleep.assert_not_called()

    @patch("bookmark_tools.http_retry.time.sleep")
    def test_raises_after_max_retries_exhausted(self, mock_sleep: MagicMock) -> None:
        """It raises the last exception after all retries are exhausted."""
        mock_urlopen = MagicMock(
            side_effect=urllib.error.URLError("Connection refused")
        )
        with patch("bookmark_tools.http_retry.urllib.request.urlopen", mock_urlopen):
            with self.assertRaises(urllib.error.URLError):
                urlopen_with_retry(
                    urllib.request.Request("https://example.com"),
                    timeout=5,
                    max_retries=2,
                    base_delay=0.01,
                )
        self.assertEqual(mock_urlopen.call_count, 3)  # initial + 2 retries

    def test_succeeds_on_first_attempt(self) -> None:
        """It returns immediately when the first attempt succeeds."""
        fake_response = MagicMock()
        mock_urlopen = MagicMock(return_value=fake_response)
        with patch("bookmark_tools.http_retry.urllib.request.urlopen", mock_urlopen):
            result = urlopen_with_retry(
                urllib.request.Request("https://example.com"),
                timeout=5,
            )
        self.assertIs(result, fake_response)
        self.assertEqual(mock_urlopen.call_count, 1)


if __name__ == "__main__":
    unittest.main()
