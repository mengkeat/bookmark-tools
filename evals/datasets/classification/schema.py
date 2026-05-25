from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bookmark_tools.tag_normalize import normalize_tags

from evals.datasets.schema_utils import (
    as_string_list,
    ensure_mapping,
    ensure_unique,
    load_yaml,
    optional_text,
    required_text,
    top_level_cases,
)


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


def _source_fields(entry: dict[str, Any], *, context: str) -> tuple[str, str, str]:
    """Return (url, content, html), supporting legacy `content_or_url`."""
    url = optional_text(entry, "url")
    content = optional_text(entry, "content")
    html = optional_text(entry, "html")
    content_or_url = optional_text(entry, "content_or_url")
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
    entry = ensure_mapping(raw, context=context)
    title = required_text(entry, "title", context=context)
    folder = optional_text(entry, "folder", "Development") or "Development"
    tags = tuple(
        normalize_tags(
            list(as_string_list(entry.get("tags", []), context=f"{context}.tags"))
        )
    )
    return ProfileNoteSeed(
        folder=folder.strip("/"),
        title=title,
        description=optional_text(entry, "description", title) or title,
        tags=tags,
        parent_topic=optional_text(entry, "parent_topic", folder) or folder,
        bookmark_type=optional_text(entry, "type", "article") or "article",
        url=optional_text(entry, "url", f"urn:classification-profile:{title}"),
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
    entry = ensure_mapping(raw, context=context)
    case_id = optional_text(entry, "id", f"case-{index + 1}")
    url, content, html = _source_fields(entry, context=context)
    title = optional_text(entry, "title")
    description = optional_text(entry, "description")
    expected_tags = frozenset(
        normalize_tags(
            list(
                as_string_list(
                    entry.get("expected_tags", []),
                    context=f"{context}.expected_tags",
                )
            )
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
        language=optional_text(entry, "language", "en") or "en",
        expected_folder=required_text(entry, "expected_folder", context=context).strip(
            "/"
        ),
        expected_type=required_text(entry, "expected_type", context=context).lower(),
        expected_tags=expected_tags,
        profile_folders=as_string_list(
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
    raw = load_yaml(fixtures_path)
    if raw is None:
        return ClassificationDataset(cases=[], profile_folders=(), profile_notes=())

    case_entries = top_level_cases(raw, path=fixtures_path)
    if isinstance(raw, dict):
        profile_folders = as_string_list(
            raw.get("profile_folders", []), context=f"{fixtures_path}.profile_folders"
        )
        profile_notes = _profile_notes_from_raw(
            raw.get("profile_notes"), context=f"{fixtures_path}.profile_notes"
        )
    else:
        profile_folders = ()
        profile_notes = ()

    cases = [
        _case_from_raw(entry, index=index) for index, entry in enumerate(case_entries)
    ]
    ensure_unique([case.case_id for case in cases], context=f"{fixtures_path}.cases")
    return ClassificationDataset(
        cases=cases,
        profile_folders=profile_folders,
        profile_notes=profile_notes,
    )
