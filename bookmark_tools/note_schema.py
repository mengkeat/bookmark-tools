from __future__ import annotations

import datetime as dt
import hashlib
import json
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

# Fields explicitly owned/managed by schema v1. These may be overwritten
# during render. Any frontmatter key NOT in this set is treated as
# user/future-owned and preserved verbatim during re-renders.
OWNED_FIELDS = frozenset(SCHEMA_V1_FIELD_ORDER) | {"summary"}
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
    """Parse a YAML flow sequence (``[a, 'b', "c"]``) into a list of strings.

    Supports three scalar forms:
    - plain (unquoted): terminated by ``,`` or ``]``
    - single-quoted: ``'value'`` with ``''`` as escaped literal quote
    - double-quoted: ``"value"`` with JSON-style escapes
    """
    if not (value.startswith("[") and value.endswith("]")):
        return []
    inner = value[1:-1].strip()
    if not inner:
        return []
    items: list[str] = []
    pos = 0
    length = len(inner)
    while pos < length:
        # skip leading whitespace
        while pos < length and inner[pos] in " \t":
            pos += 1
        if pos >= length:
            break
        ch = inner[pos]
        if ch == "'":
            # single-quoted scalar
            pos += 1
            parts: list[str] = []
            while pos < length:
                if inner[pos] == "'":
                    if pos + 1 < length and inner[pos + 1] == "'":
                        parts.append("'")
                        pos += 2
                    else:
                        pos += 1
                        break
                else:
                    parts.append(inner[pos])
                    pos += 1
            items.append("".join(parts))
        elif ch == '"':
            # double-quoted scalar — use JSON semantics
            pos += 1
            start = pos
            while pos < length and inner[pos] != '"':
                if inner[pos] == "\\":
                    pos += 1  # skip escaped char
                pos += 1
            raw = inner[start:pos]
            if pos < length:
                pos += 1  # skip closing quote
            try:
                items.append(json.loads('"' + raw + '"'))
            except json.JSONDecodeError:
                items.append(raw.replace('\\"', '"').replace("\\\\", "\\"))
        else:
            # plain scalar — read until comma or end
            start = pos
            while pos < length and inner[pos] != ",":
                pos += 1
            text = inner[start:pos].strip()
            if text:
                items.append(text)
        # skip trailing whitespace and comma
        while pos < length and inner[pos] in " \t":
            pos += 1
        if pos < length and inner[pos] == ",":
            pos += 1
    return items


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
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return inner.replace('\\"', '"').replace("\\\\", "\\")
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
        or "," in text
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


def merge_field_order(
    *orders: Sequence[str], extra_keys: Sequence[str] = ()
) -> list[str]:
    """Merge schema v1 fields with observed field orders, preserving first use."""
    merged: list[str] = []
    for field in SCHEMA_V1_FIELD_ORDER:
        if field not in merged:
            merged.append(field)
    for order in orders:
        for field in order:
            if field not in merged and field != "summary":
                merged.append(field)
    for key in extra_keys:
        if key not in merged:
            merged.append(key)
    return merged


def render_frontmatter(
    values: Mapping[str, object],
    *,
    field_order: Sequence[str] | None = None,
    extra_keys: Sequence[str] = (),
    existing_field_order: Sequence[str] | None = None,
) -> str:
    """Render frontmatter values using schema-aware field ordering."""
    orders: list[Sequence[str]] = []
    if field_order:
        orders.append(field_order)
    if existing_field_order:
        orders.append(existing_field_order)
    order = merge_field_order(*orders, extra_keys=extra_keys)
    lines = ["---"]
    for key in order:
        if key not in values or key == "summary":
            continue
        value = values[key]
        if isinstance(value, list):
            lines.append(f"{key}: {yaml_list(value)}")
        else:
            lines.append(f"{key}: {yaml_scalar(value)}")
    # Append any values not yet rendered (safety net)
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
    existing_field_order: Sequence[str] | None = None,
) -> str:
    """Render a complete schema v1 bookmark note."""
    # Determine which keys are unknown (not in owned schema) for ordering
    unknown_keys = [k for k in values if k not in OWNED_FIELDS]
    frontmatter = render_frontmatter(
        values,
        field_order=field_order,
        extra_keys=unknown_keys,
        existing_field_order=existing_field_order,
    )
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
    # Determine last_success_at:
    # - If caller provides an explicit value, use it
    # - Otherwise, refresh to now on success, or preserve existing on failure
    existing_success_at = str(existing_metadata.get("last_success_at", "")).strip()
    if last_success_at:
        resolved_success_at = last_success_at
    elif status == "ok":
        resolved_success_at = fetched_at
    else:
        resolved_success_at = existing_success_at
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
        "last_success_at": resolved_success_at,
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
    # Preserve unknown/future frontmatter fields from the existing note.
    # These are fields not owned by schema v1 and should pass through
    # unchanged during re-renders and updates.
    for key, val in existing_metadata.items():
        if key not in OWNED_FIELDS and key not in values:
            values[key] = val
    return values


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS = ("schema_version", "id", "url", "title", "created", "last_updated")

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?(Z|[+-]\d{2}:\d{2})?)?$"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_HTTP_STATUS_RE = re.compile(r"^\d{3}$")


@dataclass(frozen=True)
class SchemaIssue:
    """A single schema validation finding."""

    field: str
    severity: str  # "error" or "warning"
    message: str


def validate_schema_v1(metadata: Mapping[str, object]) -> list[SchemaIssue]:
    """Validate frontmatter metadata against schema v1 expectations.

    Returns a list of issues ordered by field. An empty list means the
    metadata passes all checks.
    """
    issues: list[SchemaIssue] = []

    # Required fields
    for field in _REQUIRED_FIELDS:
        value = metadata.get(field)
        if value is None or str(value).strip() == "":
            issues.append(
                SchemaIssue(field, "error", f"Missing required field: {field}")
            )

    # schema_version must be 1
    sv = metadata.get("schema_version")
    if sv is not None and str(sv).strip() not in ("1", ""):
        issues.append(
            SchemaIssue(
                "schema_version",
                "error",
                f"Unsupported schema_version: {sv!r} (expected 1)",
            )
        )

    # Stable ID should be a 64-char hex string
    id_val = str(metadata.get("id", "")).strip()
    if id_val and not _SHA256_RE.fullmatch(id_val):
        issues.append(
            SchemaIssue("id", "warning", "ID is not a valid SHA-256 hex digest")
        )

    # URL fields should be parseable
    for url_field in ("url", "final_url", "canonical_url"):
        url_val = str(metadata.get(url_field, "")).strip()
        if url_val:
            parsed = urllib.parse.urlsplit(url_val)
            if not parsed.scheme or not parsed.netloc:
                issues.append(
                    SchemaIssue(url_field, "warning", f"Not a valid URL: {url_val!r}")
                )

    # Domain should match canonical_url hostname
    domain = str(metadata.get("domain", "")).strip()
    canonical = str(metadata.get("canonical_url", "")).strip()
    if domain and canonical:
        expected_domain = domain_from_url(canonical)
        if domain.lower() != expected_domain:
            issues.append(
                SchemaIssue(
                    "domain",
                    "warning",
                    f"Domain {domain!r} does not match canonical_url host {expected_domain!r}",
                )
            )

    # Date/timestamp formats
    for date_field in ("created", "last_updated", "added_at"):
        val = str(metadata.get(date_field, "")).strip()
        if (
            val
            and not _ISO_DATE_RE.fullmatch(val)
            and not _ISO_TIMESTAMP_RE.fullmatch(val)
        ):
            issues.append(
                SchemaIssue(
                    date_field, "warning", f"Not a valid date/timestamp: {val!r}"
                )
            )

    for ts_field in ("last_fetched_at", "last_success_at"):
        val = str(metadata.get(ts_field, "")).strip()
        if val and not _ISO_TIMESTAMP_RE.fullmatch(val):
            issues.append(
                SchemaIssue(ts_field, "warning", f"Not a valid ISO timestamp: {val!r}")
            )

    # http_status should be a 3-digit code when present
    http_status = str(metadata.get("http_status", "")).strip()
    if http_status and not _HTTP_STATUS_RE.fullmatch(http_status):
        issues.append(
            SchemaIssue(
                "http_status", "warning", f"Not a valid HTTP status: {http_status!r}"
            )
        )

    # content_hash should be a SHA-256 hex when present
    ch = str(metadata.get("content_hash", "")).strip()
    if ch and not _SHA256_RE.fullmatch(ch):
        issues.append(
            SchemaIssue(
                "content_hash",
                "warning",
                f"Not a valid SHA-256 hex digest: {ch!r}",
            )
        )

    return issues
