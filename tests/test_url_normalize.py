from __future__ import annotations

import unittest

from bookmark_tools.url_normalize import normalize_url


class NormalizeUrlTest(unittest.TestCase):
    """Comprehensive tests for URL normalization identity rules."""

    # --- Basic normalization ---

    def test_strips_whitespace(self) -> None:
        self.assertEqual(normalize_url("  https://example.com  "), "https://example.com")

    def test_empty_string_returns_empty(self) -> None:
        self.assertEqual(normalize_url(""), "")

    def test_none_like_empty(self) -> None:
        self.assertEqual(normalize_url("   "), "")

    # --- Scheme and host ---

    def test_lowercases_scheme(self) -> None:
        self.assertEqual(normalize_url("HTTPS://example.com"), "https://example.com")

    def test_lowercases_hostname(self) -> None:
        self.assertEqual(normalize_url("https://Example.COM/path"), "https://example.com/path")

    def test_mixed_case_scheme_and_host(self) -> None:
        self.assertEqual(
            normalize_url("HtTpS://WWW.Example.COM/Path"),
            "https://www.example.com/Path",
        )

    # --- Default ports ---

    def test_strips_http_port_80(self) -> None:
        self.assertEqual(
            normalize_url("http://example.com:80/path"),
            "http://example.com/path",
        )

    def test_strips_https_port_443(self) -> None:
        self.assertEqual(
            normalize_url("https://example.com:443/path"),
            "https://example.com/path",
        )

    def test_keeps_non_default_port(self) -> None:
        self.assertEqual(
            normalize_url("http://example.com:8080/path"),
            "http://example.com:8080/path",
        )

    def test_keeps_https_non_default_port(self) -> None:
        self.assertEqual(
            normalize_url("https://example.com:8443/path"),
            "https://example.com:8443/path",
        )

    # --- Path normalization ---

    def test_strips_trailing_slash(self) -> None:
        self.assertEqual(
            normalize_url("https://example.com/path/"),
            "https://example.com/path",
        )

    def test_bare_path_becomes_empty(self) -> None:
        """A path of just '/' is removed entirely."""
        self.assertEqual(normalize_url("https://example.com/"), "https://example.com")

    def test_preserves_multi_segment_path(self) -> None:
        self.assertEqual(
            normalize_url("https://example.com/a/b/c"),
            "https://example.com/a/b/c",
        )

    def test_strips_trailing_slash_from_multi_segment(self) -> None:
        self.assertEqual(
            normalize_url("https://example.com/a/b/c/"),
            "https://example.com/a/b/c",
        )

    # --- Query and fragment preservation ---

    def test_preserves_query_string(self) -> None:
        self.assertEqual(
            normalize_url("https://example.com/path?q=1"),
            "https://example.com/path?q=1",
        )

    def test_preserves_fragment(self) -> None:
        self.assertEqual(
            normalize_url("https://example.com/path#section"),
            "https://example.com/path#section",
        )

    def test_preserves_query_and_fragment(self) -> None:
        self.assertEqual(
            normalize_url("https://example.com/path?q=1#section"),
            "https://example.com/path?q=1#section",
        )

    def test_strips_trailing_slash_with_query(self) -> None:
        self.assertEqual(
            normalize_url("https://example.com/path/?q=1"),
            "https://example.com/path?q=1",
        )

    # --- Identity: same resource, different surface forms ---

    def test_identity_case_and_port(self) -> None:
        """Different surface forms of the same URL produce the same result."""
        urls = [
            "HTTPS://Example.COM:443/path",
            "https://example.com/path/",
            "https://example.com/path",
        ]
        results = [normalize_url(u) for u in urls]
        self.assertEqual(len(set(results)), 1)

    def test_identity_different_not_same_resource(self) -> None:
        """Different paths produce different normalized URLs."""
        self.assertNotEqual(
            normalize_url("https://example.com/a"),
            normalize_url("https://example.com/b"),
        )

    def test_identity_query_params_preserved(self) -> None:
        """Query parameters are NOT stripped (conservative policy)."""
        self.assertNotEqual(
            normalize_url("https://example.com/path?a=1"),
            normalize_url("https://example.com/path?a=2"),
        )

    # --- Edge cases ---

    def test_no_scheme_returns_stripped(self) -> None:
        """Without a scheme, only trailing slash removal is done."""
        self.assertEqual(normalize_url("example.com/path/"), "example.com/path")

    def test_user_info_preserved(self) -> None:
        self.assertEqual(
            normalize_url("https://user:pass@example.com/path"),
            "https://user:pass@example.com/path",
        )

    def test_user_without_password(self) -> None:
        self.assertEqual(
            normalize_url("https://user@example.com/path"),
            "https://user@example.com/path",
        )

    def test_ipv6_host_bracketed(self) -> None:
        """IPv6 addresses are bracketed in netloc."""
        result = normalize_url("https://[::1]/path")
        self.assertIn("[::1]", result)

    def test_url_encoded_path_normalized(self) -> None:
        """Percent-encoded characters are re-normalized."""
        self.assertEqual(
            normalize_url("https://example.com/hello%20world"),
            "https://example.com/hello%20world",
        )

    def test_bare_domain_no_path(self) -> None:
        self.assertEqual(normalize_url("https://example.com"), "https://example.com")


if __name__ == "__main__":
    unittest.main()
