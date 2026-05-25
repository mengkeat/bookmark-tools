from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from evals.datasets.schema_utils import (
    as_string_list,
    ensure_mapping,
    load_yaml,
    optional_text,
    required_text,
)


@dataclass(frozen=True)
class PersonalQuery:
    query: str
    relevant_ids: frozenset[str]
    mode_hint: str | None
    notes: str | None


def build_vault_id_map(bookmarks_dir: Path) -> dict[str, Path]:
    """Return {note_id → path} by scanning bookmark notes for their `id:` field."""
    from bookmark_tools.note_filter import iter_bookmark_note_paths
    from bookmark_tools.note_schema import parse_note_text

    id_map: dict[str, Path] = {}
    for path in iter_bookmark_note_paths(bookmarks_dir, bookmark_only=True):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        note = parse_note_text(text, path=path)
        note_id = str(note.frontmatter.get("id", "")).strip()
        if note_id:
            id_map[note_id] = path
    return id_map


def load_queries(queries_path: Path) -> list[dict]:
    """Load and lightly validate raw YAML entries from queries.yaml."""
    raw = load_yaml(queries_path)
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(
            f"{queries_path}: expected a YAML list at the top level, got {type(raw).__name__}"
        )
    return raw


def validate(
    queries_path: Path,
    bookmarks_dir: Path,
) -> tuple[list[PersonalQuery], dict[str, Path]]:
    """Load queries.yaml and validate every relevant_id exists in the vault.

    Returns (validated_queries, vault_id_map).
    Raises ValueError with a clear message for any schema error or stale ID.
    """
    raw_entries = load_queries(queries_path)
    if not raw_entries:
        return [], {}

    vault_id_map = build_vault_id_map(bookmarks_dir)

    queries: list[PersonalQuery] = []
    for i, entry in enumerate(raw_entries):
        context = f"{queries_path} entry {i}"
        entry = ensure_mapping(entry, context=context)
        query_text = required_text(entry, "query", context=context)
        raw_ids = as_string_list(
            entry.get("relevant_ids", []), context=f"{context}.relevant_ids"
        )

        relevant_ids: list[str] = []
        for j, rid_str in enumerate(raw_ids):
            if rid_str not in vault_id_map:
                raise ValueError(
                    f"{queries_path} entry {i}, relevant_ids[{j}]: "
                    f"ID {rid_str!r} not found in vault.\n"
                    f"  Run: grep -r 'id: {rid_str}' \"$BOOKMARKS_DIR\""
                )
            relevant_ids.append(rid_str)

        mode_hint = optional_text(entry, "mode_hint") or None
        notes = optional_text(entry, "notes") or None

        queries.append(
            PersonalQuery(
                query=query_text,
                relevant_ids=frozenset(relevant_ids),
                mode_hint=mode_hint,
                notes=notes,
            )
        )

    return queries, vault_id_map
