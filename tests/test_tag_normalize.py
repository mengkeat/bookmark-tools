from __future__ import annotations

import unittest

from bookmark_tools.tag_normalize import (
    load_aliases,
    normalize_tag,
    normalize_tags,
)


class NormalizeTagTest(unittest.TestCase):
    def test_lowercases_and_strips(self) -> None:
        """It lowercases and strips whitespace."""
        self.assertEqual(normalize_tag("  Python  "), "python")

    def test_converts_spaces_to_hyphens(self) -> None:
        """It converts spaces to hyphens."""
        self.assertEqual(normalize_tag("Machine Learning"), "machine-learning")

    def test_collapses_multiple_hyphens(self) -> None:
        """It collapses multiple hyphens into one."""
        self.assertEqual(normalize_tag("deep--learning"), "deep-learning")

    def test_applies_default_alias(self) -> None:
        """It resolves known abbreviations to their canonical form."""
        self.assertEqual(normalize_tag("ml"), "machine-learning")
        self.assertEqual(normalize_tag("js"), "javascript")
        self.assertEqual(normalize_tag("k8s"), "kubernetes")

    def test_custom_alias(self) -> None:
        """It uses custom aliases when provided."""
        aliases = {"react": "reactjs"}
        self.assertEqual(normalize_tag("react", aliases=aliases), "reactjs")

    def test_passthrough_unknown_tag(self) -> None:
        """It passes through tags not in the alias map."""
        self.assertEqual(normalize_tag("pytorch"), "pytorch")


class NormalizeTagsTest(unittest.TestCase):
    def test_deduplicates_after_normalization(self) -> None:
        """It removes duplicates that arise after normalization."""
        result = normalize_tags(["ML", "machine-learning", "Python"])
        self.assertEqual(result, ["machine-learning", "python"])

    def test_preserves_order(self) -> None:
        """It preserves the order of first occurrence."""
        result = normalize_tags(["python", "ai", "pytorch"])
        self.assertEqual(result, ["python", "artificial-intelligence", "pytorch"])

    def test_empty_list(self) -> None:
        """It returns an empty list for empty input."""
        self.assertEqual(normalize_tags([]), [])

    def test_filters_empty_tags(self) -> None:
        """It removes tags that normalize to empty strings."""
        result = normalize_tags(["python", "", "  ", "ai"])
        self.assertEqual(result, ["python", "artificial-intelligence"])


class LoadAliasesTest(unittest.TestCase):
    def test_loads_custom_aliases(self) -> None:
        """It parses alias definitions from text."""
        text = "react = reactjs\nvue = vuejs\n"
        aliases = load_aliases(text)
        self.assertEqual(aliases["react"], "reactjs")
        self.assertEqual(aliases["vue"], "vuejs")
        # Default aliases still present
        self.assertEqual(aliases["ml"], "machine-learning")

    def test_skips_comments_and_blanks(self) -> None:
        """It ignores comment lines and empty lines."""
        text = "# Comment\n\nreact = reactjs\n"
        aliases = load_aliases(text)
        self.assertIn("react", aliases)


if __name__ == "__main__":
    unittest.main()
