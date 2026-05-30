#!/usr/bin/env python3
"""One-time conversion script: upgrade legacy ML-AI bookmark notes to schema v1.

Reads from ~/code/obsidian-vault/Vault/Bookmarks/ML-AI/**/*.md
Writes to tests/data/bookmarks/ML-AI/**/*.md

This script is NOT imported by tests — only its output (the generated .md files)
and the derived fixtures.py module are committed.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import urllib.parse
from pathlib import Path

SOURCE_DIR = Path.home() / "code/obsidian-vault/Vault/Bookmarks/ML-AI"
OUTPUT_DIR = Path(__file__).parent / "bookmarks" / "ML-AI"

# Known URL fixes for notes with url: N/A
URL_FIXES = {
    "Stanford-CS230": "https://cs230.stanford.edu/",
    "JAX-ML-Github-Book": "https://github.com/jax-ml",
}

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


def normalize_url(url: str) -> str:
    """Normalize URL for stable ID generation."""
    parsed = urllib.parse.urlsplit(url.strip())
    scheme = parsed.scheme.lower() or "https"
    host = (parsed.hostname or "").lower()
    port = parsed.port
    path = parsed.path.rstrip("/")
    if port == {"http": 80, "https": 443}.get(scheme):
        port = None
    netloc = host if not port else f"{host}:{port}"
    return urllib.parse.urlunsplit((scheme, netloc, path, "", ""))


def stable_bookmark_id(url: str) -> str:
    normalized = normalize_url(url)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def domain_from_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(str(url).strip())
    hostname = parsed.hostname or ""
    try:
        return hostname.encode("idna").decode("ascii").lower()
    except UnicodeError:
        return hostname.lower()


def parse_frontmatter(text: str) -> tuple[dict[str, object], list[str], str]:
    """Parse legacy note into frontmatter dict, field order, and body."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, [], text
    end_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}, [], text

    data: dict[str, object] = {}
    order: list[str] = []
    for raw_line in lines[1:end_idx]:
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        if not key:
            continue
        order.append(key)
        val = raw_value.strip()
        # Parse inline list
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            if inner:
                data[key] = [item.strip().strip("'\"") for item in inner.split(",") if item.strip()]
            else:
                data[key] = []
        else:
            data[key] = val

    body = "\n".join(lines[end_idx + 1 :]).strip()
    return data, order, body


def parse_inline_list(value: str) -> list[str]:
    if not (value.startswith("[") and value.endswith("]")):
        return []
    inner = value[1:-1].strip()
    if not inner:
        return []
    return [item.strip().strip("'\"") for item in inner.split(",") if item.strip()]


def yaml_scalar(value: object) -> str:
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
    YAML_BOOLEAN_LIKE = {"true", "false", "yes", "no", "on", "off", "null", "none", "~"}
    UNSAFE_PLAIN_START = tuple("-?:{}[],&*#!|>@`%")
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


def yaml_list(values: list[object]) -> str:
    items = [yaml_scalar(item) for item in values if str(item).strip()]
    return "[" + ", ".join(items) + "]"


def wrap_summary_in_block(body: str) -> str:
    """Wrap a legacy 'Summary:' paragraph in a generated block."""
    if not body.startswith("Summary:"):
        return body
    # Find the summary text (everything after "Summary:")
    summary_text = body[len("Summary:"):].strip()
    # Check if there are sections after the summary
    heading_match = re.search(r"\n^#{1,6}\s+", summary_text, re.MULTILINE)
    if heading_match:
        summary_part = summary_text[:heading_match.start()].strip()
        rest = summary_text[heading_match.start():].strip()
        return (
            f"Summary:\n"
            f"<!-- bookmark-tools:summary:start -->\n"
            f"{summary_part}\n"
            f"<!-- bookmark-tools:summary:end -->\n\n"
            f"{rest}"
        )
    return (
        f"Summary:\n"
        f"<!-- bookmark-tools:summary:start -->\n"
        f"{summary_text}\n"
        f"<!-- bookmark-tools:summary:end -->"
    )


def convert_note(source_path: Path, dest_path: Path) -> None:
    text = source_path.read_text(encoding="utf-8")
    data, order, body = parse_frontmatter(text)

    stem = source_path.stem
    url = str(data.get("url", "")).strip()
    if url == "N/A" or not url:
        url = URL_FIXES.get(stem, "")
        if not url:
            raise ValueError(f"No URL for {source_path}")

    title = str(data.get("title", stem)).strip()
    bookmark_type = str(data.get("type", "article")).strip()
    tags = data.get("tags", [])
    if isinstance(tags, str):
        tags = parse_inline_list(tags)
    tags = [str(t).strip() for t in tags if str(t).strip()]

    created = str(data.get("created", "2026-03-28")).strip()
    last_updated = str(data.get("last_updated", created)).strip()
    language = str(data.get("language", "en")).strip()
    related = data.get("related", [])
    if isinstance(related, str):
        related = parse_inline_list(related)
    related = [str(r).strip() for r in related if str(r).strip()]
    parent_topic = str(data.get("parent_topic", "")).strip()
    visibility = str(data.get("visibility", "private")).strip()
    description = str(data.get("description", title)).strip()

    # Derive schema v1 fields
    bookmark_id = stable_bookmark_id(url)
    domain = domain_from_url(url)
    content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    timestamp = f"{created}T00:00:00Z"

    # Wrap summary body in generated block
    new_body = wrap_summary_in_block(body)

    # Build frontmatter
    values = {
        "schema_version": 1,
        "id": bookmark_id,
        "title": title,
        "url": url,
        "final_url": url,
        "canonical_url": url,
        "domain": domain,
        "type": bookmark_type,
        "tags": tags,
        "added_at": created,
        "last_fetched_at": timestamp,
        "last_success_at": timestamp,
        "created": created,
        "last_updated": last_updated,
        "language": language,
        "related": related,
        "parent_topic": parent_topic,
        "visibility": visibility,
        "status": "ok",
        "http_status": 200,
        "content_type": "text/html",
        "content_hash": content_hash,
        "archive_path": "",
        "classification_model": "",
        "classification_prompt_version": "v1",
        "summary_model": "",
        "source_kind": "url",
        "source_path": "",
        "source_line": "",
        "description": description,
    }

    fm_lines = ["---"]
    for key in SCHEMA_V1_FIELD_ORDER:
        if key not in values:
            continue
        value = values[key]
        if isinstance(value, list):
            fm_lines.append(f"{key}: {yaml_list(value)}")
        else:
            fm_lines.append(f"{key}: {yaml_scalar(value)}")
    fm_lines.append("---")

    output = "\n".join(fm_lines) + "\n\n" + new_body + "\n"
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(output, encoding="utf-8")
    print(f"  {source_path.relative_to(SOURCE_DIR.parent.parent)} → {dest_path.relative_to(OUTPUT_DIR.parent.parent)}")


def main():
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)

    source_files = sorted(SOURCE_DIR.rglob("*.md"))
    print(f"Converting {len(source_files)} notes...")

    for src in source_files:
        rel = src.relative_to(SOURCE_DIR)
        dest = OUTPUT_DIR / rel
        convert_note(src, dest)

    print(f"\nDone. {len(source_files)} notes written to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
