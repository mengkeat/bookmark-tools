from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .note_filter import iter_bookmark_note_paths
from .note_schema import parse_note_text
from .paths import require_bookmarks_dir

WHITESPACE_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True)
class SearchDocument:
    path: Path
    url: str
    title: str
    folder: str
    tags: str
    related: str
    parent_topic: str
    description: str
    body: str


def _normalize_metadata_text(value: object) -> str:
    """Normalize scalar and list values into whitespace-collapsed text."""
    if value is None:
        return ""
    if isinstance(value, list):
        parts = [str(item).strip() for item in value if str(item).strip()]
        return " ".join(parts)
    return WHITESPACE_PATTERN.sub(" ", str(value)).strip()


def _read_note_text(path: Path) -> str:
    """Read note text, returning empty string on decode errors."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def collect_search_documents(
    bookmarks_dir: Path | None = None,
) -> list[SearchDocument]:
    """Collect normalized bookmark documents for search indexing."""
    if bookmarks_dir is None:
        bookmarks_dir = require_bookmarks_dir()
    documents: list[SearchDocument] = []
    for note_path in iter_bookmark_note_paths(bookmarks_dir, bookmark_only=True):
        raw_text = _read_note_text(note_path)
        note = parse_note_text(raw_text, path=note_path)
        metadata = note.frontmatter
        # Preserve Markdown heading line structure so downstream chunking can
        # split by sections. Individual FTS/embedding chunk text is normalized
        # later by ``bookmark_tools.chunking``.
        body = note.body.strip()
        relative_folder = str(note_path.relative_to(bookmarks_dir).parent)

        # Append final/canonical URL text for search matching
        extra_url_text = " ".join(
            value
            for value in [
                _normalize_metadata_text(metadata.get("final_url")),
                _normalize_metadata_text(metadata.get("canonical_url")),
            ]
            if value
        )
        if extra_url_text:
            body = f"{body} {extra_url_text}".strip()

        documents.append(
            SearchDocument(
                path=note_path,
                url=_normalize_metadata_text(metadata.get("url")),
                title=_normalize_metadata_text(metadata.get("title")) or note_path.stem,
                folder="" if relative_folder == "." else relative_folder,
                tags=_normalize_metadata_text(metadata.get("tags")),
                related=_normalize_metadata_text(metadata.get("related")),
                parent_topic=_normalize_metadata_text(metadata.get("parent_topic")),
                description=_normalize_metadata_text(metadata.get("description")),
                body=body,
            )
        )
    return documents
