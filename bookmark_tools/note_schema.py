from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import re
import urllib.parse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from .note_filter import is_archive_sidecar
from .url_normalize import normalize_url

SCHEMA_VERSION = 1
CLASSIFICATION_PROMPT_VERSION = "v1"
GENERATED_BLOCK_PREFIX = "bookmark-tools"

SCHEMA_V1_FIELD_ORDER = [
    "schema_version",
    "id",
    "title",
    "url",
    "final_url",
    "canonical_url",
    "domain",
    "type",
    "tags",
    "added_at",
    "last_fetched_at",
    "last_success_at",
    "created",
    "last_updated",
    "language",
    "related",
    "parent_topic",
    "visibility",
    "status",
    "http_status",
    "content_type",
    "content_hash",
    "archive_path",
    "classification_model",
    "classification_prompt_version",
    "summary_model",
    "source_kind",
    "source_path",
    "source_line",
    "description",
]

INTEGER_FIELDS = {"schema_version", "http_status", "source_line"}
YAML_BOOLEAN_LIKE = {
    "true",
    "false",
    "yes",
    "no",
    "on",
    "off",
    "null",
    "none",
    "~",
}
UNSAFE_PLAIN_START = tuple("-?:{}[],&*#!|>@`%")
GENERATED_BLOCK_RE = re.compile(
    r"<!--\s*bookmark-tools:(?P<name>[a-z0-9_-]+):start\s*-->.*?"
    r"<!--\s*bookmark-tools:(?P=name):end\s*-->",
    re.IGNORECASE | re.DOTALL,
)
MARKDOWN_HEADING_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)


@dataclass(frozen=True)
class BookmarkNote:
    """Parsed representation of a Markdown bookmark note."""

    path: Path | None
    frontmatter: dict[str, object]
    field_order: list[str]
    body: str
    text: str
    is_sidecar: bool = False

    @property
    def is_bookmark(self) -> bool:
        """Return True when this note has enough metadata to be a bookmark."""
        return not self.is_sidecar and bool(
            str(self.frontmatter.get("url", "")).strip()
        )


def utc_now() -> str:
    """Return a second-precision UTC timestamp for schema metadata."""
    return (
        dt.datetime.now(dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def stable_bookmark_id(url: str) -> str:
    """Return the stable bookmark id for an original URL."""
    normalized = normalize_url(url)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def content_sha256(content: str) -> str:
    """Return the SHA-256 hex digest for fetched text content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def domain_from_url(url: str) -> str:
    """Return a normalized hostname for URL-derived domain metadata."""
    parsed = urllib.parse.urlsplit(str(url).strip())
    hostname = parsed.hostname or ""
    try:
        return hostname.encode("idna").decode("ascii").lower()
    except UnicodeError:
        return hostname.lower()


def split_frontmatter(text: str) -> tuple[str, str]:
    """Split Markdown text into frontmatter text and body text.

    Returns (frontmatter, body). If the document has no leading frontmatter
    fence, frontmatter is an empty string and body is the whole document.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return "", text
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "\n".join(lines[1:index]), "\n".join(lines[index + 1 :])
    return "", text


def _parse_inline_list(value: str) -> list[str]:
    """Parse a simple YAML-style inline string list."""
    if not (value.startswith("[") and value.endswith("]")):
        return []
    inner = value[1:-1].strip()
    if not inner:
        return []
    reader = csv.reader(io.StringIO(inner), skipinitialspace=True)
    try:
        row = next(reader)
    except csv.Error:
        return [item.strip().strip("'").strip('"') for item in inner.split(",")]
    return [
        str(item).strip().strip("'").strip('"') for item in row if str(item).strip()
    ]


def _parse_scalar(key: str, value: str) -> object:
    """Parse the subset of YAML scalars used by bookmark frontmatter."""
    if value == "":
        return ""
    if value.startswith("[") and value.endswith("]"):
        return _parse_inline_list(value)
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        quote = value[0]
        inner = value[1:-1]
        if quote == "'":
            return inner.replace("''", "'")
        return bytes(inner, "utf-8").decode("unicode_escape")
    if key in INTEGER_FIELDS and value.isdigit():
        return int(value)
    return value


def parse_frontmatter_text(frontmatter: str) -> tuple[dict[str, object], list[str]]:
    """Parse YAML-like frontmatter into data and original field order."""
    data: dict[str, object] = {}
    order: list[str] = []
    for raw_line in frontmatter.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        if not key:
            continue
        order.append(key)
        data[key] = _parse_scalar(key, raw_value.strip())
    return data, order


def parse_note_text(text: str, path: Path | None = None) -> BookmarkNote:
    """Parse a Markdown note into frontmatter and body components."""
    frontmatter, body = split_frontmatter(text)
    metadata, order = parse_frontmatter_text(frontmatter)
    return BookmarkNote(
        path=path,
        frontmatter=metadata,
        field_order=order,
        body=body,
        text=text,
        is_sidecar=is_archive_sidecar(path) if path is not None else False,
    )


def parse_note_file(path: Path) -> BookmarkNote:
    """Read and parse a Markdown note file."""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = ""
    return parse_note_text(text, path=path)


def is_bookmark_note(path: Path) -> bool:
    """Return True if *path* is a canonical bookmark note."""
    if path.suffix != ".md" or is_archive_sidecar(path):
        return False
    return parse_note_file(path).is_bookmark


def yaml_scalar(value: object) -> str:
    """Serialize a scalar value for conservative YAML frontmatter.

    Plain scalars are used when safe and readable; values that YAML is likely
    to coerce or misread are single-quoted.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    text = " ".join(str(value).splitlines()).strip()
    if text == "":
        return ""
    lower = text.lower()
    needs_quote = (
        lower in YAML_BOOLEAN_LIKE
        or text.startswith(UNSAFE_PLAIN_START)
        or ": " in text
        or " #" in text
        or "[" in text
        or "]" in text
        or "{" in text
        or "}" in text
    )
    if needs_quote:
        return "'" + text.replace("'", "''") + "'"
    return text


def yaml_list(values: Sequence[object]) -> str:
    """Serialize a list of scalar values for inline YAML frontmatter."""
    items = [yaml_scalar(item) for item in values if str(item).strip()]
    return "[" + ", ".join(items) + "]"


def merge_field_order(*orders: Sequence[str]) -> list[str]:
    """Merge schema v1 fields with observed field orders, preserving first use."""
    merged: list[str] = []
    for field in SCHEMA_V1_FIELD_ORDER:
        if field not in merged:
            merged.append(field)
    for order in orders:
        for field in order:
            if field not in merged and field != "summary":
                merged.append(field)
    return merged


def render_frontmatter(
    values: Mapping[str, object], *, field_order: Sequence[str] | None = None
) -> str:
    """Render frontmatter values using schema-aware field ordering."""
    order = merge_field_order(field_order or [])
    lines = ["---"]
    for key in order:
        if key not in values or key == "summary":
            continue
        value = values[key]
        if isinstance(value, list):
            lines.append(f"{key}: {yaml_list(value)}")
        else:
            lines.append(f"{key}: {yaml_scalar(value)}")
    for key, value in values.items():
        if key in order or key == "summary":
            continue
        if isinstance(value, list):
            lines.append(f"{key}: {yaml_list(value)}")
        else:
            lines.append(f"{key}: {yaml_scalar(value)}")
    lines.append("---")
    return "\n".join(lines)


def generated_block(name: str, content: str) -> str:
    """Return a managed generated Markdown block."""
    safe_name = re.sub(r"[^a-z0-9_-]+", "-", name.lower()).strip("-")
    body = str(content).strip()
    return (
        f"<!-- {GENERATED_BLOCK_PREFIX}:{safe_name}:start -->\n"
        f"{body}\n"
        f"<!-- {GENERATED_BLOCK_PREFIX}:{safe_name}:end -->"
    )


def update_generated_block(body: str, name: str, content: str) -> str:
    """Replace or append one generated block in an existing Markdown body."""
    safe_name = re.sub(r"[^a-z0-9_-]+", "-", name.lower()).strip("-")
    block = generated_block(safe_name, content)
    pattern = re.compile(
        rf"<!--\s*{GENERATED_BLOCK_PREFIX}:{re.escape(safe_name)}:start\s*-->.*?"
        rf"<!--\s*{GENERATED_BLOCK_PREFIX}:{re.escape(safe_name)}:end\s*-->",
        re.IGNORECASE | re.DOTALL,
    )
    if pattern.search(body):
        return pattern.sub(block, body, count=1)
    return f"{body.rstrip()}\n\n{block}".strip()


def render_relationships_block(
    *, tags: Sequence[str], related: Sequence[str], domain: str
) -> str:
    """Render deterministic relationship metadata as a generated block body."""
    lines: list[str] = []
    if domain:
        lines.append(f"- domain: {domain}")
    if tags:
        lines.append("- tags: " + ", ".join(str(tag) for tag in tags))
    if related:
        lines.append("- related: " + ", ".join(str(item) for item in related))
    return "\n".join(lines) or "- none"


def render_fetch_timeline_block(
    *, last_fetched_at: str, status: str, http_status: object = ""
) -> str:
    """Render the current fetch event as a generated block body."""
    status_text = str(status).strip() or "unknown"
    http_text = str(http_status).strip()
    suffix = f" (HTTP {http_text})" if http_text else ""
    return f"- {last_fetched_at}: {status_text}{suffix}"


def strip_generated_blocks(body: str) -> str:
    """Remove bookmark-tools generated blocks from a Markdown body."""
    return GENERATED_BLOCK_RE.sub("", body).strip()


def extract_human_body(body: str) -> str:
    """Return human-authored body content outside generated summary blocks.

    Legacy notes often start with a plain ``Summary:`` paragraph. That section
    is treated as generated content and removed until the first Markdown
    heading, preserving sections such as ``## Notes``.
    """
    without_blocks = strip_generated_blocks(body)
    text = without_blocks.strip()
    if not text:
        return ""
    if text.startswith("Summary:"):
        heading = MARKDOWN_HEADING_RE.search(text)
        if heading:
            return text[heading.start() :].strip()
        return ""
    return text


def render_schema_v1(
    values: Mapping[str, object],
    *,
    summary: str,
    field_order: Sequence[str] | None = None,
    existing_body: str | None = None,
) -> str:
    """Render a complete schema v1 bookmark note."""
    frontmatter = render_frontmatter(values, field_order=field_order)
    summary_body = "Summary:\n" + generated_block("summary", summary)
    human_body = extract_human_body(existing_body or "")
    body = summary_body if not human_body else f"{summary_body}\n\n{human_body}"
    return f"{frontmatter}\n\n{body}\n"


def build_schema_v1_values(
    *,
    title: str,
    url: str,
    final_url: str | None = None,
    canonical_url: str | None = None,
    bookmark_type: str,
    tags: Sequence[str],
    created: str,
    last_updated: str,
    language: str,
    related: Sequence[str],
    parent_topic: str,
    visibility: str,
    description: str,
    status: str = "ok",
    http_status: object = "",
    content_type: str = "",
    content: str = "",
    archive_path: str = "",
    classification_model: str = "",
    classification_prompt_version: str = CLASSIFICATION_PROMPT_VERSION,
    summary_model: str = "",
    source_kind: str = "url",
    source_path: str = "",
    source_line: object = "",
    added_at: str | None = None,
    last_fetched_at: str | None = None,
    last_success_at: str | None = None,
    existing_metadata: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build frontmatter values for a schema v1 bookmark note."""
    existing_metadata = existing_metadata or {}
    final = final_url or url
    canonical = canonical_url or final
    fetched_at = last_fetched_at or utc_now()
    success_at = last_success_at or (fetched_at if status == "ok" else "")
    bookmark_id = str(existing_metadata.get("id", "")).strip() or stable_bookmark_id(
        url
    )
    preserved_added_at = str(existing_metadata.get("added_at", "")).strip()
    values: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "id": bookmark_id,
        "title": title,
        "url": url,
        "final_url": final,
        "canonical_url": canonical,
        "domain": domain_from_url(canonical),
        "type": bookmark_type,
        "tags": list(tags),
        "added_at": added_at or preserved_added_at or created,
        "last_fetched_at": fetched_at,
        "last_success_at": last_success_at
        or str(existing_metadata.get("last_success_at", "")).strip()
        or success_at,
        "created": created,
        "last_updated": last_updated,
        "language": language,
        "related": list(related),
        "parent_topic": parent_topic,
        "visibility": visibility,
        "status": status,
        "http_status": http_status,
        "content_type": content_type,
        "content_hash": content_sha256(content)
        if content
        else str(existing_metadata.get("content_hash", "")).strip(),
        "archive_path": archive_path
        or str(existing_metadata.get("archive_path", "")).strip(),
        "classification_model": classification_model
        or str(existing_metadata.get("classification_model", "")).strip(),
        "classification_prompt_version": classification_prompt_version
        or str(existing_metadata.get("classification_prompt_version", "")).strip(),
        "summary_model": summary_model
        or str(existing_metadata.get("summary_model", "")).strip(),
        "source_kind": source_kind
        or str(existing_metadata.get("source_kind", "")).strip()
        or "url",
        "source_path": source_path
        or str(existing_metadata.get("source_path", "")).strip(),
        "source_line": source_line
        or str(existing_metadata.get("source_line", "")).strip(),
        "description": description,
    }
    return values
