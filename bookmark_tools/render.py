from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from .types import NormalizedBookmarkMetadata
from .vault_profile import BookmarkProfile


def infer_summary(description: str, content: str) -> str:
    """Return description if available, otherwise derive a short summary from content."""
    if description:
        return description
    sentences = re.split(r"(?<=[.!?])\s+", content.strip())
    summary = " ".join(sentence for sentence in sentences[:2] if sentence)
    return summary[:900].strip() or "Summary unavailable."


def slugify_filename(title: str) -> str:
    """Convert a note title into a safe markdown filename."""
    title = re.sub(
        r"[^A-Za-z0-9+]+", "-", re.sub(r"[/:]", " ", title.strip() or "Untitled")
    )
    return f"{re.sub(r'-{2,}', '-', title).strip('-') or 'Untitled'}.md"


def yaml_scalar(value: str) -> str:
    """Serialize a scalar value for YAML frontmatter."""
    return " ".join(value.splitlines()).strip()


def yaml_list(values: list[str]) -> str:
    """Serialize a list of strings for inline YAML frontmatter."""
    return "[" + ", ".join(yaml_scalar(value) for value in values) + "]"


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
) -> str:
    """Render bookmark metadata into note content with ordered frontmatter."""
    today = dt.date.today().isoformat()
    values = {
        "title": str(metadata["title"]).strip(),
        "url": url,
        "type": str(metadata["type"]).strip(),
        "tags": [
            str(tag).strip() for tag in metadata.get("tags", []) if str(tag).strip()
        ],
        "created": created_override if created_override else today,
        "last_updated": today,
        "language": str(metadata.get("language", "en")).strip() or "en",
        "related": [
            str(item).strip()
            for item in metadata.get("related", [])
            if str(item).strip()
        ],
        "parent_topic": str(metadata.get("parent_topic", "")).strip()
        or str(metadata["folder"]).split("/")[-1],
        "description": str(metadata.get("description", metadata["title"])).strip(),
        "visibility": str(
            metadata.get("visibility", profile.default_visibility or "private")
        ),
    }
    frontmatter_lines = ["---"]
    for key in profile.schema:
        if key == "summary" or key not in values:
            continue
        value = values[key]
        if isinstance(value, list):
            frontmatter_lines.append(
                f"{key}: {yaml_list([str(item) for item in value if str(item).strip()])}"
            )
        elif key in {"created", "last_updated"}:
            frontmatter_lines.append(f"{key}: {value}")
        else:
            frontmatter_lines.append(f"{key}: {yaml_scalar(str(value))}")
    frontmatter_lines.extend(
        ["---", "", "Summary:", str(metadata.get("summary", "")).strip(), ""]
    )
    return "\n".join(frontmatter_lines)
