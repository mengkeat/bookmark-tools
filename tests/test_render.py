from __future__ import annotations

import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from bookmark_tools.render import render_note, slugify_filename, yaml_scalar, yaml_list
from bookmark_tools.vault_profile import collect_existing_notes


def _make_profile(tmp: str):
    bookmarks_dir = Path(tmp) / "Bookmarks"
    bookmarks_dir.mkdir(parents=True)
    return collect_existing_notes(bookmarks_dir=bookmarks_dir)


def _sample_metadata():
    return {
        "folder": "Tech",
        "title": "Test Page",
        "type": "article",
        "tags": ["python", "testing"],
        "language": "en",
        "related": [],
        "parent_topic": "Tech",
        "description": "A test page",
        "summary": "Summary text",
        "visibility": "private",
    }


class RenderNoteCreatedOverrideTest(unittest.TestCase):
    def test_uses_today_when_no_override(self) -> None:
        """It renders a created date when no override is provided."""
        with TemporaryDirectory() as tmp:
            profile = _make_profile(tmp)
            result = render_note(_sample_metadata(), "https://example.com", profile)
        self.assertIn("created:", result)

    def test_created_override_is_used(self) -> None:
        """It preserves the original created date when created_override is given."""
        with TemporaryDirectory() as tmp:
            profile = _make_profile(tmp)
            result = render_note(
                _sample_metadata(),
                "https://example.com",
                profile,
                created_override="2023-06-15",
            )
        self.assertIn("created: 2023-06-15", result)

    def test_last_updated_is_not_affected_by_override(self) -> None:
        """last_updated always reflects today, even when created_override is given."""
        import datetime as dt

        with TemporaryDirectory() as tmp:
            profile = _make_profile(tmp)
            result = render_note(
                _sample_metadata(),
                "https://example.com",
                profile,
                created_override="2020-01-01",
            )
        today = dt.date.today().isoformat()
        self.assertIn(f"last_updated: {today}", result)
        self.assertIn("created: 2020-01-01", result)

    def test_created_override_none_uses_today(self) -> None:
        """Passing created_override=None falls back to today."""
        import datetime as dt

        with TemporaryDirectory() as tmp:
            profile = _make_profile(tmp)
            result = render_note(
                _sample_metadata(),
                "https://example.com",
                profile,
                created_override=None,
            )
        today = dt.date.today().isoformat()
        self.assertIn(f"created: {today}", result)


if __name__ == "__main__":
    unittest.main()
