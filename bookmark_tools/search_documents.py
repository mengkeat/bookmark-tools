from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .note_filter import iter_bookmark_note_paths
from .paths import require_bookmarks_dir
from .vault_profile import read_frontmatter

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


def _extract_body_text(note_path: Path) -> str:
    """Read a note body and remove frontmatter when present."""
    try:
        text = note_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""
    if text.startswith("---\n"):
        _, _, text = text[4:].partition("---\n")
    return WHITESPACE_PATTERN.sub(" ", text).strip()


def collect_search_documents(
    bookmarks_dir: Path | None = None,
) -> list[SearchDocument]:
    """Collect normalized bookmark documents for search indexing."""
    if bookmarks_dir is None:
        bookmarks_dir = require_bookmarks_dir()
    documents: list[SearchDocument] = []
    for note_path in iter_bookmark_note_paths(bookmarks_dir):
        metadata, _ = read_frontmatter(note_path)
        relative_folder = str(note_path.relative_to(bookmarks_dir).parent)
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
                body=_extract_body_text(note_path),
            )
        )
        # Also index final/canonical URL text for search matching
        doc = documents[-1]
        extra_url_text = " ".join(
            value
            for value in [
                _normalize_metadata_text(metadata.get("final_url")),
                _normalize_metadata_text(metadata.get("canonical_url")),
            ]
            if value
        )
        if extra_url_text:
            documents[-1] = SearchDocument(
                path=doc.path,
                url=doc.url,
                title=doc.title,
                folder=doc.folder,
                tags=doc.tags,
                related=doc.related,
                parent_topic=doc.parent_topic,
                description=doc.description,
                body=f"{doc.body} {extra_url_text}".strip(),
            )
    return documents
