"""Section-aware chunk generation for bookmark retrieval.

Markdown notes remain canonical; chunks are derived records used by search,
embeddings, and the catalog.  The splitter is intentionally lightweight and
stdlib-only: it prefers Markdown sections, then splits oversized sections by a
character budget with small overlap.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .search_documents import SearchDocument

HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$", re.MULTILINE)
TOKEN_PATTERN = re.compile(r"[\w'-]+", re.UNICODE)
WHITESPACE_PATTERN = re.compile(r"\s+")

DEFAULT_CHUNK_MAX_CHARS = 1600
DEFAULT_CHUNK_OVERLAP_CHARS = 160
MIN_CHUNK_CHARS = 40


@dataclass(frozen=True)
class SearchChunk:
    """A derived section/chunk record for one bookmark note."""

    path: Path
    url: str
    title: str
    folder: str
    tags: str
    related: str
    parent_topic: str
    description: str
    section: str
    chunk_index: int
    chunk_text: str
    token_count: int
    text_hash: str


@dataclass(frozen=True)
class _Section:
    """Internal Markdown section representation."""

    name: str
    text: str


def _normalize_text(value: str) -> str:
    """Collapse whitespace while preserving readable text."""
    return WHITESPACE_PATTERN.sub(" ", value).strip()


def _section_name_from_heading(heading: str) -> str:
    """Map a Markdown heading to a stable retrieval section name."""
    normalized = re.sub(r"[^a-z0-9]+", "_", heading.lower()).strip("_")
    if not normalized:
        return "body"
    if normalized in {"executive_summary", "summary"}:
        return "summary"
    if normalized in {"key_ideas", "key_points", "highlights"}:
        return "key_ideas"
    if "archive" in normalized or "excerpt" in normalized:
        return "archive"
    if "note" in normalized:
        return "notes"
    if "relationship" in normalized:
        return "relationships"
    if "source" in normalized:
        return "source"
    return normalized


def _fallback_section_name(text: str) -> str:
    """Choose a section name for text before the first Markdown heading."""
    stripped = text.lstrip()
    if stripped.lower().startswith("summary:"):
        return "summary"
    return "body"


def split_markdown_sections(markdown_body: str) -> list[_Section]:
    """Split Markdown body text into heading-delimited sections.

    Text before the first heading is retained as a ``body`` or ``summary``
    section. Empty sections are skipped.
    """
    matches = list(HEADING_PATTERN.finditer(markdown_body))
    if not matches:
        text = _normalize_text(markdown_body)
        return [_Section(_fallback_section_name(text), text)] if text else []

    sections: list[_Section] = []
    prelude = _normalize_text(markdown_body[: matches[0].start()])
    if prelude:
        sections.append(_Section(_fallback_section_name(prelude), prelude))

    for index, match in enumerate(matches):
        heading = match.group(2).strip()
        content_start = match.end()
        content_end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown_body)
        section_text = _normalize_text(markdown_body[content_start:content_end])
        if section_text:
            sections.append(_Section(_section_name_from_heading(heading), section_text))
    return sections


def _split_large_text(
    text: str,
    *,
    max_chars: int = DEFAULT_CHUNK_MAX_CHARS,
    overlap_chars: int = DEFAULT_CHUNK_OVERLAP_CHARS,
) -> list[str]:
    """Split one section into character-budgeted chunks."""
    text = _normalize_text(text)
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        hard_end = min(start + max_chars, len(text))
        end = hard_end
        if hard_end < len(text):
            # Prefer sentence/word boundaries near the budget.
            boundary = max(text.rfind(". ", start, hard_end), text.rfind(" ", start, hard_end))
            if boundary > start + max(MIN_CHUNK_CHARS, max_chars // 2):
                end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap_chars, start + 1)
    return chunks


def _chunk_hash(text: str) -> str:
    """Return a stable hash for a normalized chunk text."""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _token_count(text: str) -> int:
    """Approximate token count with word-like tokens."""
    return len(TOKEN_PATTERN.findall(text))


def chunk_document(
    document: SearchDocument,
    *,
    max_chars: int = DEFAULT_CHUNK_MAX_CHARS,
    overlap_chars: int = DEFAULT_CHUNK_OVERLAP_CHARS,
) -> list[SearchChunk]:
    """Create retrieval chunks for one search document."""
    chunks: list[SearchChunk] = []
    chunk_index = 0
    sections = split_markdown_sections(document.body)
    if not sections:
        sections = [_Section("metadata", _normalize_text(document.description or document.title))]

    for section in sections:
        for chunk_text in _split_large_text(
            section.text,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        ):
            chunks.append(
                SearchChunk(
                    path=document.path,
                    url=document.url,
                    title=document.title,
                    folder=document.folder,
                    tags=document.tags,
                    related=document.related,
                    parent_topic=document.parent_topic,
                    description=document.description,
                    section=section.name,
                    chunk_index=chunk_index,
                    chunk_text=chunk_text,
                    token_count=_token_count(chunk_text),
                    text_hash=_chunk_hash(chunk_text),
                )
            )
            chunk_index += 1
    return chunks


def chunk_documents(
    documents: list[SearchDocument],
    *,
    max_chars: int = DEFAULT_CHUNK_MAX_CHARS,
    overlap_chars: int = DEFAULT_CHUNK_OVERLAP_CHARS,
) -> list[SearchChunk]:
    """Create retrieval chunks for a list of search documents."""
    chunks: list[SearchChunk] = []
    for document in documents:
        chunks.extend(
            chunk_document(
                document,
                max_chars=max_chars,
                overlap_chars=overlap_chars,
            )
        )
    return chunks
