from __future__ import annotations

import unittest
from unittest.mock import patch

from bookmark_tools.fetch import _parse_metadata, search_meta, clean_html


class HTMLParserTest(unittest.TestCase):
    def test_extracts_title_tag(self) -> None:
        """It extracts the title from a <title> element."""
        html = "<html><head><title>Page Title</title></head></html>"
        parser = _parse_metadata(html)
        self.assertEqual(parser.title, "Page Title")

    def test_extracts_og_title_meta(self) -> None:
        """It extracts og:title from meta property tag."""
        html = '<html><head><meta property="og:title" content="OG Title"></head></html>'
        parser = _parse_metadata(html)
        self.assertEqual(parser.meta.get("og:title"), "OG Title")

    def test_extracts_description_meta(self) -> None:
        """It extracts description from meta name tag."""
        html = '<html><head><meta name="description" content="Page desc"></head></html>'
        parser = _parse_metadata(html)
        self.assertEqual(parser.meta.get("description"), "Page desc")

    def test_extracts_lang_attribute(self) -> None:
        """It extracts the lang attribute from the html tag."""
        html = '<html lang="fr-FR"><head><title>Test</title></head></html>'
        parser = _parse_metadata(html)
        self.assertEqual(parser.language, "fr")

    def test_defaults_language_to_empty(self) -> None:
        """It leaves language empty when html tag has no lang attribute."""
        html = "<html><head><title>Test</title></head></html>"
        parser = _parse_metadata(html)
        self.assertEqual(parser.language, "")

    def test_handles_malformed_html(self) -> None:
        """It handles malformed HTML without raising exceptions."""
        html = '<html><head><title>Broken<meta name="desc" content="hi">'
        parser = _parse_metadata(html)
        self.assertEqual(parser.title, "Broken")
        self.assertEqual(parser.meta.get("desc"), "hi")

    def test_handles_reversed_meta_attributes(self) -> None:
        """It handles meta tags with content before name/property."""
        html = '<html><head><meta content="Reversed" name="description"></head></html>'
        parser = _parse_metadata(html)
        self.assertEqual(parser.meta.get("description"), "Reversed")

    def test_search_meta_returns_value(self) -> None:
        """search_meta returns the correct meta tag value."""
        html = '<html><head><meta name="description" content="Test desc"></head></html>'
        self.assertEqual(search_meta("description", html), "Test desc")

    def test_search_meta_returns_empty_for_missing(self) -> None:
        """search_meta returns empty string for missing meta tags."""
        html = "<html><head><title>Test</title></head></html>"
        self.assertEqual(search_meta("description", html), "")

    def test_search_meta_unescapes_html_entities(self) -> None:
        """search_meta unescapes HTML entities in meta content."""
        html = '<html><head><meta name="description" content="A &amp; B"></head></html>'
        self.assertEqual(search_meta("description", html), "A & B")

    def test_clean_html_strips_tags(self) -> None:
        """clean_html removes tags and collapses whitespace."""
        html = "<p>Hello <b>world</b></p>  <p>test</p>"
        self.assertEqual(clean_html(html), "Hello world test")

    def test_clean_html_strips_scripts(self) -> None:
        """clean_html removes script blocks."""
        html = '<p>before</p><script>alert("xss")</script><p>after</p>'
        result = clean_html(html)
        self.assertNotIn("alert", result)
        self.assertIn("before", result)
        self.assertIn("after", result)

    def test_first_meta_wins_for_duplicate_names(self) -> None:
        """When multiple meta tags have the same name, the first one wins."""
        html = (
            "<html><head>"
            '<meta name="description" content="First">'
            '<meta name="description" content="Second">'
            "</head></html>"
        )
        parser = _parse_metadata(html)
        self.assertEqual(parser.meta.get("description"), "First")


class FetchNetworkErrorTest(unittest.TestCase):
    """Tests for network failure handling in fetch_text / extract_page_data."""

    def _fake_response(self, body: bytes, url: str = "https://example.com"):
        class FakeHeaders:
            def get_content_charset(self):
                return "utf-8"

        class FakeResponse:
            def __init__(self):
                self.headers = FakeHeaders()
                self._body = body
                self._url = url

            def read(self, n=-1):
                return self._body if n == -1 else self._body[:n]

            def geturl(self):
                return self._url

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        return FakeResponse()

    def test_fetch_raises_on_404(self) -> None:
        """fetch_text propagates HTTP 404 errors (not retried)."""
        import urllib.error
        from bookmark_tools.fetch import fetch_text

        exc = urllib.error.HTTPError("https://example.com", 404, "Not Found", {}, None)
        with patch("bookmark_tools.http_retry.urllib.request.urlopen", side_effect=exc):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                fetch_text("https://example.com")
        self.assertEqual(ctx.exception.code, 404)

    def test_fetch_raises_on_connection_error(self) -> None:
        """fetch_text propagates URLError after retries are exhausted."""
        import urllib.error
        from bookmark_tools.fetch import fetch_text

        exc = urllib.error.URLError("Connection refused")
        with patch(
            "bookmark_tools.http_retry.urllib.request.urlopen",
            side_effect=exc,
        ):
            with patch("bookmark_tools.http_retry.time.sleep"):
                with self.assertRaises(urllib.error.URLError):
                    fetch_text("https://example.com")

    def test_extract_page_data_uses_final_url_after_redirect(self) -> None:
        """extract_page_data captures the redirected URL."""
        from bookmark_tools.fetch import extract_page_data

        html = b"<html><head><title>Redirected Page</title></head><body></body></html>"
        fake = self._fake_response(html, url="https://redirected.example.com/final")
        with patch(
            "bookmark_tools.http_retry.urllib.request.urlopen", return_value=fake
        ):
            page = extract_page_data("https://example.com/original")
        self.assertEqual(page["url"], "https://redirected.example.com/final")
        self.assertEqual(page["title"], "Redirected Page")


if __name__ == "__main__":
    unittest.main()
