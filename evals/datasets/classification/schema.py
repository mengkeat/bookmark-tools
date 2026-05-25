from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ProfileNoteSeed:
    """Synthetic note used to build classification context in temp profiles."""

    folder: str
    title: str
    description: str
    tags: tuple[str, ...]
    parent_topic: str
    bookmark_type: str
    url: str


@dataclass(frozen=True)
class ClassificationCase:
    """One labeled classification fixture."""

    case_id: str
    title: str
    url: str
    content: str
    html: str
    description: str
    language: str
    expected_folder: str
    expected_type: str
    expected_tags: frozenset[str]
    profile_folders: tuple[str, ...]
    profile_notes: tuple[ProfileNoteSeed, ...]
    allow_new_subfolder: bool


@dataclass(frozen=True)
class ClassificationDataset:
    """Loaded classification fixture dataset."""

    cases: list[ClassificationCase]
    profile_folders: tuple[str, ...]
    profile_notes: tuple[ProfileNoteSeed, ...]


def _as_mapping(value: Any, *, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context}: expected a mapping, got {type(value).__name__}")
    return value


def _as_string_list(value: Any, *, context: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{context}: expected a list, got {type(value).__name__}")
    items: list[str] = []
    for index, item in enumerate(value):
        text = str(item).strip()
        if not text:
            raise ValueError(f"{context}[{index}]: empty value")
        items.append(text)
    return tuple(items)


def _required_text(entry: dict[str, Any], key: str, *, context: str) -> str:
    text = str(entry.get(key, "")).strip()
    if not text:
        raise ValueError(f"{context}: missing required {key!r} field")
    return text


def _optional_text(entry: dict[str, Any], key: str, default: str = "") -> str:
    value = entry.get(key, default)
    if value is None:
        return default
    return str(value).strip()


def _source_fields(entry: dict[str, Any], *, context: str) -> tuple[str, str, str]:
    """Return (url, content, html), supporting legacy `content_or_url`."""
    url = _optional_text(entry, "url")
    content = _optional_text(entry, "content")
    html = _optional_text(entry, "html")
    content_or_url = _optional_text(entry, "content_or_url")
    if content_or_url and not (url or content or html):
        if content_or_url.startswith(("http://", "https://", "file://")):
            url = content_or_url
        else:
            content = content_or_url
    if not (url or content or html):
        raise ValueError(
            f"{context}: one of 'url', 'content', 'html', or 'content_or_url' is required"
        )
    return url, content, html


def _profile_note_from_raw(raw: Any, *, context: str) -> ProfileNoteSeed:
    entry = _as_mapping(raw, context=context)
    title = _required_text(entry, "title", context=context)
    folder = _optional_text(entry, "folder", "Development") or "Development"
    tags = _as_string_list(entry.get("tags", []), context=f"{context}.tags")
    return ProfileNoteSeed(
        folder=folder.strip("/"),
        title=title,
        description=_optional_text(entry, "description", title) or title,
        tags=tags,
        parent_topic=_optional_text(entry, "parent_topic", folder) or folder,
        bookmark_type=_optional_text(entry, "type", "article") or "article",
        url=_optional_text(entry, "url", f"urn:classification-profile:{title}"),
    )


def _profile_notes_from_raw(value: Any, *, context: str) -> tuple[ProfileNoteSeed, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{context}: expected a list, got {type(value).__name__}")
    return tuple(
        _profile_note_from_raw(item, context=f"{context}[{index}]")
        for index, item in enumerate(value)
    )


def _case_from_raw(raw: Any, *, index: int) -> ClassificationCase:
    context = f"classification fixture {index}"
    entry = _as_mapping(raw, context=context)
    case_id = _optional_text(entry, "id", f"case-{index + 1}")
    url, content, html = _source_fields(entry, context=context)
    title = _optional_text(entry, "title")
    description = _optional_text(entry, "description")
    expected_tags = frozenset(
        tag.lower()
        for tag in _as_string_list(
            entry.get("expected_tags", []), context=f"{context}.expected_tags"
        )
    )
    if not expected_tags:
        raise ValueError(f"{context}: expected_tags must contain at least one tag")
    return ClassificationCase(
        case_id=case_id,
        title=title,
        url=url,
        content=content,
        html=html,
        description=description,
        language=_optional_text(entry, "language", "en") or "en",
        expected_folder=_required_text(entry, "expected_folder", context=context).strip(
            "/"
        ),
        expected_type=_required_text(entry, "expected_type", context=context).lower(),
        expected_tags=expected_tags,
        profile_folders=_as_string_list(
            entry.get("profile_folders", []), context=f"{context}.profile_folders"
        ),
        profile_notes=_profile_notes_from_raw(
            entry.get("profile_notes"), context=f"{context}.profile_notes"
        ),
        allow_new_subfolder=bool(entry.get("allow_new_subfolder", False)),
    )


def load_dataset(fixtures_path: Path) -> ClassificationDataset:
    """Load classification fixtures from YAML.

    Supports either a top-level list of cases or a mapping with optional
    `profile_folders`, `profile_notes`, and required `cases` list.
    """
    raw = yaml.safe_load(fixtures_path.read_text(encoding="utf-8"))
    if raw is None:
        return ClassificationDataset(cases=[], profile_folders=(), profile_notes=())

    if isinstance(raw, list):
        case_entries = raw
        profile_folders: tuple[str, ...] = ()
        profile_notes: tuple[ProfileNoteSeed, ...] = ()
    elif isinstance(raw, dict):
        case_entries = raw.get("cases", [])
        if not isinstance(case_entries, list):
            raise ValueError(
                f"{fixtures_path}: 'cases' must be a list, got {type(case_entries).__name__}"
            )
        profile_folders = _as_string_list(
            raw.get("profile_folders", []), context=f"{fixtures_path}.profile_folders"
        )
        profile_notes = _profile_notes_from_raw(
            raw.get("profile_notes"), context=f"{fixtures_path}.profile_notes"
        )
    else:
        raise ValueError(
            f"{fixtures_path}: expected a YAML list or mapping, got {type(raw).__name__}"
        )

    return ClassificationDataset(
        cases=[
            _case_from_raw(entry, index=index)
            for index, entry in enumerate(case_entries)
        ],
        profile_folders=profile_folders,
        profile_notes=profile_notes,
    )
