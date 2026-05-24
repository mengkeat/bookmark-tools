from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from .note_schema import (
    build_schema_v1_values,
    parse_note_text,
    render_schema_v1,
    yaml_list as _yaml_list,
    yaml_scalar as _yaml_scalar,
)
from .types import NormalizedBookmarkMetadata
from .vault_profile import BookmarkProfile


def infer_summary(description: str, content: str) -> str:
    """Return description if available, otherwise derive a short summary from content."""
    if description:
        return description
    sentences = re.split(r"(?<=[.!?])\s+", content.strip())
    summary = " ".join(sentence for sentence in sentences[:2] if sentence)
    return summary[:900].strip() or "Summary unavailable."


def yaml_scalar(value: object) -> str:
    """Serialize a scalar value for YAML frontmatter."""
    return _yaml_scalar(value)


def yaml_list(values: list[str]) -> str:
    """Serialize a list of strings for inline YAML frontmatter."""
    return _yaml_list(values)


def slugify_filename(title: str) -> str:
    """Convert a note title into a safe markdown filename."""
    title = re.sub(
        r"[^A-Za-z0-9+]+", "-", re.sub(r"[/:]", " ", title.strip() or "Untitled")
    )
    return f"{re.sub(r'-{2,}', '-', title).strip('-') or 'Untitled'}.md"


def uniquify_path(path: Path) -> Path:
    """Return a non-conflicting path by appending a numeric suffix when needed."""
    if not path.exists():
        return path
    index = 2
    while True:
        candidate = path.parent / f"{path.stem}-{index}{path.suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def render_note(
    metadata: NormalizedBookmarkMetadata,
    url: str,
    profile: BookmarkProfile,
    *,
    created_override: str | None = None,
    final_url: str | None = None,
    canonical_url: str | None = None,
    content: str = "",
    full_content: str = "",
    http_status: object = "",
    content_type: str = "",
    archive_path: str = "",
    classification_model: str = "",
    summary_model: str = "",
    source_kind: str = "url",
    source_path: str = "",
    source_line: object = "",
    existing_note_text: str | None = None,
) -> str:
    """Render bookmark metadata into a schema v1 Markdown note."""
    today = dt.date.today().isoformat()
    existing_note = (
        parse_note_text(existing_note_text or "") if existing_note_text else None
    )
    existing_metadata = existing_note.frontmatter if existing_note else {}
    existing_body = existing_note.body if existing_note else ""
    created = (
        created_override or str(existing_metadata.get("created", "")).strip() or today
    )
    values = build_schema_v1_values(
        title=str(metadata["title"]).strip(),
        url=url,
        final_url=final_url or url,
        canonical_url=canonical_url,
        bookmark_type=str(metadata["type"]).strip(),
        tags=[str(tag).strip() for tag in metadata.get("tags", []) if str(tag).strip()],
        created=created,
        last_updated=today,
        language=str(metadata.get("language", "en")).strip() or "en",
        related=[
            str(item).strip()
            for item in metadata.get("related", [])
            if str(item).strip()
        ],
        parent_topic=str(metadata.get("parent_topic", "")).strip()
        or str(metadata["folder"]).split("/")[-1],
        visibility=str(
            metadata.get("visibility", profile.default_visibility or "private")
        ),
        description=str(metadata.get("description", metadata["title"])).strip(),
        content=full_content or content,
        http_status=http_status,
        content_type=content_type,
        archive_path=archive_path,
        classification_model=classification_model,
        summary_model=summary_model,
        source_kind=source_kind,
        source_path=source_path,
        source_line=source_line,
        existing_metadata=existing_metadata,
    )
    return render_schema_v1(
        values,
        summary=str(metadata.get("summary", "")).strip(),
        field_order=[
            *profile.schema,
            *(existing_note.field_order if existing_note else []),
        ],
        existing_body=existing_body,
        existing_field_order=existing_note.field_order if existing_note else None,
    )
