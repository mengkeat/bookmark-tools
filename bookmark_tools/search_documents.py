from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .paths import get_bookmarks_dir
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
        bookmarks_dir = get_bookmarks_dir()
    documents: list[SearchDocument] = []
    for note_path in sorted(bookmarks_dir.rglob("*.md")):
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
    return documents
