from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
