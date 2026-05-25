from __future__ import annotations

import hashlib
from pathlib import Path

from bookmark_tools.note_schema import yaml_scalar


def _safe_stem(doc_id: str) -> str:
    """Convert a doc_id to a safe filename stem (no extension)."""
    safe = doc_id.replace("/", "_").replace("\\", "_").replace(" ", "_")
    # Hash very long IDs to stay within filesystem limits
    if len(safe) > 180:
        safe = hashlib.sha256(doc_id.encode()).hexdigest()[:24]
    return safe


def write_note(
    vault_dir: Path,
    *,
    doc_id: str,
    title: str,
    body: str,
    url: str,
    description: str = "",
    tags: list[str] | None = None,
) -> Path:
    """Write a minimal bookmark note and return its path."""
    stem = _safe_stem(doc_id)
    note_path = vault_dir / f"{stem}.md"
    tag_str = "[" + ", ".join(tags or []) + "]"
    front_lines = [
        "---",
        f"url: {url}",
        f"title: {yaml_scalar(title)}",
        f"tags: {tag_str}",
        f"description: {yaml_scalar(description or title)}",
        "---",
    ]
    note_path.write_text("\n".join(front_lines) + f"\n\n{body}\n", encoding="utf-8")
    return note_path


def build_vault_from_docs(
    vault_dir: Path,
    docs: list[dict[str, str]],
    *,
    url_prefix: str = "urn:beir",
) -> dict[str, str]:
    """Write bookmark notes from a corpus doc list.

    Each doc must have keys: doc_id, title, text.
    Returns a mapping of doc_id → filename stem for reverse lookup.
    """
    vault_dir.mkdir(parents=True, exist_ok=True)
    doc_id_to_stem: dict[str, str] = {}
    for doc in docs:
        doc_id = doc["doc_id"]
        write_note(
            vault_dir,
            doc_id=doc_id,
            title=doc.get("title", "") or doc_id,
            body=doc.get("text", ""),
            url=f"{url_prefix}:{doc_id}",
            description=doc.get("title", "") or doc_id,
        )
        doc_id_to_stem[doc_id] = _safe_stem(doc_id)
    return doc_id_to_stem
