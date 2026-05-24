from __future__ import annotations

import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from bookmark_tools.note_schema import (
    SCHEMA_VERSION,
    build_schema_v1_values,
    content_sha256,
    domain_from_url,
    extract_human_body,
    generated_block,
    is_bookmark_note,
    parse_note_file,
    parse_note_text,
    render_fetch_timeline_block,
    render_frontmatter,
    render_relationships_block,
    render_schema_v1,
    stable_bookmark_id,
    update_generated_block,
    yaml_scalar,
)


class NoteSchemaParseTest(unittest.TestCase):
    def test_parse_existing_note_frontmatter_and_body(self) -> None:
        note = parse_note_text(
            "---\n"
            "schema_version: 1\n"
            "url: https://example.com\n"
            "tags: [python, 'ai']\n"
            "title: 'Example: title'\n"
            "---\n\n"
            "Summary:\nBody text.\n"
        )

        self.assertTrue(note.is_bookmark)
        self.assertEqual(note.frontmatter["schema_version"], 1)
        self.assertEqual(note.frontmatter["url"], "https://example.com")
        self.assertEqual(note.frontmatter["tags"], ["python", "ai"])
        self.assertEqual(note.frontmatter["title"], "Example: title")
        self.assertEqual(note.field_order[:2], ["schema_version", "url"])
        self.assertIn("Summary:", note.body)

    def test_parse_double_quoted_unicode_scalar(self) -> None:
        note = parse_note_text('---\ntitle: "Café"\nurl: https://example.com\n---\n')
        self.assertEqual(note.frontmatter["title"], "Café")

    def test_identifies_sidecar_as_non_bookmark(self) -> None:
        with TemporaryDirectory() as tmp:
            sidecar = Path(tmp) / "sample.content.md"
            sidecar.write_text("---\nurl: https://example.com\n---\n", encoding="utf-8")
            note = parse_note_file(sidecar)

        self.assertTrue(note.is_sidecar)
        self.assertFalse(note.is_bookmark)

    def test_is_bookmark_note_requires_md_url_and_non_sidecar(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            bookmark = root / "bookmark.md"
            bookmark.write_text(
                "---\nurl: https://example.com\n---\n", encoding="utf-8"
            )
            no_url = root / "note.md"
            no_url.write_text("---\ntitle: Note\n---\n", encoding="utf-8")
            sidecar = root / "bookmark.content.md"
            sidecar.write_text("---\nurl: https://example.com\n---\n", encoding="utf-8")

            self.assertTrue(is_bookmark_note(bookmark))
            self.assertFalse(is_bookmark_note(no_url))
            self.assertFalse(is_bookmark_note(sidecar))


class NoteSchemaIdentityTest(unittest.TestCase):
    def test_stable_id_uses_normalized_original_url(self) -> None:
        expected = hashlib.sha256(b"https://example.com/path").hexdigest()
        self.assertEqual(
            stable_bookmark_id(" HTTPS://Example.com:443/path/ "),
            expected,
        )

    def test_domain_from_url_normalizes_hostname(self) -> None:
        self.assertEqual(domain_from_url("https://Example.COM/path"), "example.com")

    def test_content_hash_uses_sha256(self) -> None:
        self.assertEqual(content_sha256("hello"), hashlib.sha256(b"hello").hexdigest())


class NoteSchemaRenderTest(unittest.TestCase):
    def test_yaml_scalar_quotes_ambiguous_values_only(self) -> None:
        self.assertEqual(
            yaml_scalar("https://example.com/path"), "https://example.com/path"
        )
        self.assertEqual(yaml_scalar("Example: with colon"), "'Example: with colon'")
        self.assertEqual(yaml_scalar("tag,with-comma"), "'tag,with-comma'")
        self.assertEqual(yaml_scalar("true"), "'true'")

    def test_render_frontmatter_uses_schema_order(self) -> None:
        rendered = render_frontmatter(
            {
                "title": "Example",
                "url": "https://example.com",
                "schema_version": SCHEMA_VERSION,
                "id": "abc",
            }
        )
        lines = rendered.splitlines()
        self.assertEqual(lines[0], "---")
        self.assertEqual(lines[1], "schema_version: 1")
        self.assertEqual(lines[2], "id: abc")
        self.assertEqual(lines[3], "title: Example")

    def test_build_schema_v1_values_populates_stable_fields(self) -> None:
        values = build_schema_v1_values(
            title="Example",
            url="https://example.com/short",
            final_url="https://example.com/full",
            bookmark_type="article",
            tags=["python"],
            created="2026-05-24",
            last_updated="2026-05-24",
            language="en",
            related=["docs"],
            parent_topic="Development",
            visibility="private",
            description="Description",
            content="Fetched content",
            last_fetched_at="2026-05-24T00:00:00Z",
        )

        self.assertEqual(values["schema_version"], 1)
        self.assertEqual(values["id"], stable_bookmark_id("https://example.com/short"))
        self.assertEqual(values["final_url"], "https://example.com/full")
        self.assertEqual(values["canonical_url"], "https://example.com/full")
        self.assertEqual(values["domain"], "example.com")
        self.assertEqual(values["content_hash"], content_sha256("Fetched content"))
        self.assertEqual(values["classification_prompt_version"], "v1")

    def test_render_schema_v1_preserves_human_notes_section(self) -> None:
        existing_body = "Summary:\nOld summary.\n\n## Notes\nKeep this.\n"
        rendered = render_schema_v1(
            {
                "schema_version": 1,
                "id": "abc",
                "title": "Example",
                "url": "https://example.com",
            },
            summary="New summary.",
            existing_body=existing_body,
        )

        self.assertIn("bookmark-tools:summary:start", rendered)
        self.assertIn("New summary.", rendered)
        self.assertNotIn("Old summary.", rendered)
        self.assertIn("## Notes\nKeep this.", rendered)

    def test_extract_human_body_removes_generated_summary(self) -> None:
        body = (
            "Summary:\n"
            + generated_block("summary", "Generated")
            + "\n\n## Notes\nMine"
        )
        self.assertEqual(extract_human_body(body), "## Notes\nMine")

    def test_update_generated_block_replaces_existing_block(self) -> None:
        body = "Intro\n\n" + generated_block("relationships", "old")
        updated = update_generated_block(body, "relationships", "new")
        self.assertIn("new", updated)
        self.assertNotIn("old", updated)
        self.assertEqual(updated.count("bookmark-tools:relationships:start"), 1)

    def test_generated_relationship_and_fetch_helpers(self) -> None:
        relationships = render_relationships_block(
            tags=["python"], related=["docs"], domain="example.com"
        )
        timeline = render_fetch_timeline_block(
            last_fetched_at="2026-05-24T00:00:00Z",
            status="ok",
            http_status=200,
        )
        self.assertIn("domain: example.com", relationships)
        self.assertIn("tags: python", relationships)
        self.assertEqual(timeline, "- 2026-05-24T00:00:00Z: ok (HTTP 200)")


class YamlListRoundTripTest(unittest.TestCase):
    """Tests that inline YAML lists survive render → parse round-trips."""

    def _round_trip(self, tags: list[str]) -> list[str]:
        from bookmark_tools.note_schema import _parse_inline_list, yaml_list

        rendered = yaml_list(tags)
        return _parse_inline_list(rendered)

    def test_comma_in_value(self) -> None:
        self.assertEqual(
            self._round_trip(["tag,with-comma", "other"]),
            ["tag,with-comma", "other"],
        )

    def test_boolean_like_values(self) -> None:
        for val in ("true", "false", "yes", "no", "on", "off", "null"):
            with self.subTest(val=val):
                self.assertEqual(self._round_trip([val]), [val])

    def test_brackets_in_value(self) -> None:
        self.assertEqual(
            self._round_trip(["val[0]", "val[1]"]),
            ["val[0]", "val[1]"],
        )

    def test_urls(self) -> None:
        self.assertEqual(
            self._round_trip(["https://example.com/path"]),
            ["https://example.com/path"],
        )

    def test_empty_list(self) -> None:
        self.assertEqual(self._round_trip([]), [])

    def test_single_quoted_scalar_round_trips(self) -> None:
        """Values that need quoting in YAML render correctly."""
        from bookmark_tools.note_schema import _parse_inline_list, yaml_list

        rendered = yaml_list(["Example: with colon", "tag,with-comma"])
        self.assertIn("'", rendered)
        parsed = _parse_inline_list(rendered)
        self.assertEqual(parsed, ["Example: with colon", "tag,with-comma"])

    def test_double_quoted_scalar_round_trips(self) -> None:
        """Double-quoted scalars with unicode parse correctly."""
        from bookmark_tools.note_schema import parse_frontmatter_text

        data, _ = parse_frontmatter_text('tags: ["Café", "Test"]')
        self.assertEqual(data["tags"], ["Café", "Test"])

    def test_single_quote_escape_in_list(self) -> None:
        from bookmark_tools.note_schema import _parse_inline_list

        parsed = _parse_inline_list("['it''s', 'rock ''n'' roll']")
        self.assertEqual(parsed, ["it's", "rock 'n' roll"])

    def test_frontmatter_tags_round_trip(self) -> None:
        """Tags rendered in frontmatter survive a full parse cycle."""
        from bookmark_tools.note_schema import parse_frontmatter_text, yaml_list

        original = ["python", "ai/ml", "tag,with-comma", "true"]
        rendered = yaml_list(original)
        data, _ = parse_frontmatter_text(f"tags: {rendered}")
        self.assertEqual(data["tags"], original)

    def test_plain_scalars_with_spaces(self) -> None:
        from bookmark_tools.note_schema import _parse_inline_list

        parsed = _parse_inline_list("[machine learning, data science]")
        self.assertEqual(parsed, ["machine learning", "data science"])


if __name__ == "__main__":
    unittest.main()
