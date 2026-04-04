from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from .paths import get_bookmarks_dir

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "for",
    "from",
    "how",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "this",
    "to",
    "using",
    "with",
    "you",
}

DEFAULT_FIELD_ORDER = [
    "title",
    "url",
    "type",
    "tags",
    "created",
    "last_updated",
    "language",
    "related",
    "parent_topic",
    "visibility",
    "description",
]


@dataclass(frozen=True)
class NoteProfile:
    folder: str
    title: str
    description: str
    tags: list[str]
    parent_topic: str
    tokens: set[str]


@dataclass(frozen=True)
class BookmarkProfile:
    notes: list[NoteProfile]
    folders: list[str]
    schema: list[str]
    folder_examples: dict[str, list[str]]
    folder_parent_topics: dict[str, str]
    default_visibility: str
    url_index: dict[str, Path]


def list_existing_folders(bookmarks_dir: Path) -> list[str]:
    """Return all existing bookmark folder paths relative to the bookmarks root."""
    return sorted(
        str(path.relative_to(bookmarks_dir))
        for path in bookmarks_dir.rglob("*")
        if path.is_dir()
    )


def parse_list(value: str) -> list[str]:
    """Parse a simple bracketed list string into a list of trimmed values."""
    if not (value.startswith("[") and value.endswith("]")):
        return []
    inner = value[1:-1].strip()
    if not inner:
        return []
    return [
        item.strip().strip("'").strip('"') for item in inner.split(",") if item.strip()
    ]


def read_frontmatter(note_path: Path) -> tuple[dict[str, object], list[str]]:
    """Read YAML-like frontmatter key/value pairs and preserve their field order."""
    try:
        text = note_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {}, []
    if not text.startswith("---\n"):
        return {}, []
    frontmatter, _, _ = text[4:].partition("---\n")
    data: dict[str, object] = {}
    order: list[str] = []
    for line in frontmatter.splitlines():
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        order.append(key)
        data[key] = parse_list(value) if value.startswith("[") else value.strip('"')
    return data, order


def parse_frontmatter(note_path: Path) -> dict[str, object]:
    """Read frontmatter metadata from a note file."""
    return read_frontmatter(note_path)[0]


def tokenize(text: str) -> set[str]:
    """Tokenize text into normalized searchable terms."""
    return {
        token
        for token in re.findall(r"[A-Za-z0-9+#-]{3,}", text.lower())
        if token not in STOPWORDS and not token.isdigit()
    }


def choose_schema(field_orders: list[list[str]]) -> list[str]:
    """Build a stable schema using defaults plus observed fields by frequency."""
    counter: Counter[str] = Counter()
    for order in field_orders:
        counter.update(order)
    schema = list(DEFAULT_FIELD_ORDER)
    for field, _ in counter.most_common():
        if field not in schema:
            schema.append(field)
    return schema


def choose_default_visibility(visibility_values: list[str]) -> str:
    """Pick the most common non-empty visibility, defaulting to private."""
    values = [value for value in visibility_values if value]
    if not values:
        return "private"
    return Counter(values).most_common(1)[0][0]


def choose_folder_parent_topics(
    folder_topics: dict[str, Counter[str]],
) -> dict[str, str]:
    """Pick the most common parent topic per folder."""
    chosen: dict[str, str] = {}
    for folder, topics in folder_topics.items():
        if topics:
            chosen[folder] = topics.most_common(1)[0][0]
    return chosen


def collect_existing_notes(
    bookmarks_dir: Path | None = None,
) -> BookmarkProfile:
    """Collect existing bookmark notes and derive profile data used for classification."""
    if bookmarks_dir is None:
        bookmarks_dir = get_bookmarks_dir()
    notes: list[NoteProfile] = []
    field_orders: list[list[str]] = []
    folder_examples: dict[str, list[str]] = defaultdict(list)
    folder_topics: dict[str, Counter[str]] = defaultdict(Counter)
    visibility_values: list[str] = []
    url_index: dict[str, Path] = {}

    for note_path in bookmarks_dir.rglob("*.md"):
        metadata, order = read_frontmatter(note_path)
        field_orders.append(order)
        existing_url = str(metadata.get("url", "")).strip().rstrip("/")
        if existing_url and existing_url not in url_index:
            url_index[existing_url] = note_path
        folder = str(note_path.relative_to(bookmarks_dir).parent)
        folder = "" if folder == "." else folder
        title = str(metadata.get("title", note_path.stem))
        description = str(metadata.get("description", ""))
        tags = (
            [str(tag) for tag in metadata.get("tags", [])]
            if isinstance(metadata.get("tags"), list)
            else []
        )
        parent_topic = str(metadata.get("parent_topic", ""))
        if folder and len(folder_examples[folder]) < 3:
            folder_examples[folder].append(title)
        if parent_topic:
            folder_topics[folder][parent_topic] += 1
        visibility_values.append(str(metadata.get("visibility", "")))
        notes.append(
            NoteProfile(
                folder=folder,
                title=title,
                description=description,
                tags=tags,
                parent_topic=parent_topic,
                tokens=tokenize(
                    " ".join([folder, title, description, " ".join(tags), parent_topic])
                ),
            )
        )

    return BookmarkProfile(
        notes=notes,
        folders=list_existing_folders(bookmarks_dir),
        schema=choose_schema(field_orders),
        folder_examples=dict(folder_examples),
        folder_parent_topics=choose_folder_parent_topics(folder_topics),
        default_visibility=choose_default_visibility(visibility_values),
        url_index=url_index,
    )
