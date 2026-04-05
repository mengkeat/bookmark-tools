from __future__ import annotations

import logging
import re
from pathlib import Path

from .vault_profile import parse_list

logger = logging.getLogger(__name__)

MAX_RELATED_ITEMS = 6


def _update_related_field(note_path: Path, new_topic: str) -> bool:
    """Add a related topic to a note's frontmatter if not already present.

    Returns True if the file was modified, False otherwise.
    """
    try:
        text = note_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return False

    if not text.startswith("---\n"):
        return False

    frontmatter_end = text.index("---\n", 4)
    frontmatter = text[4:frontmatter_end]
    rest = text[frontmatter_end:]

    # Find the related line
    related_match = re.search(r"^(related:\s*)(.*)$", frontmatter, re.MULTILINE)
    if related_match is None:
        # No related field — insert before the closing ---
        new_frontmatter = frontmatter.rstrip("\n") + f"\nrelated: [{new_topic}]\n"
        note_path.write_text(f"---\n{new_frontmatter}{rest}", encoding="utf-8")
        return True

    existing_value = related_match.group(2).strip()
    existing_items = (
        parse_list(existing_value) if existing_value.startswith("[") else []
    )

    normalized_existing = [item.lower().strip() for item in existing_items]
    if new_topic.lower() in normalized_existing:
        return False

    if len(existing_items) >= MAX_RELATED_ITEMS:
        return False

    updated_items = existing_items + [new_topic]
    updated_value = "[" + ", ".join(updated_items) + "]"

    new_line = f"{related_match.group(1)}{updated_value}"
    new_frontmatter = (
        frontmatter[: related_match.start()]
        + new_line
        + frontmatter[related_match.end() :]
    )
    note_path.write_text(f"---\n{new_frontmatter}{rest}", encoding="utf-8")
    return True


def update_related_backlinks(
    new_note_topic: str,
    similar_note_paths: list[Path],
    *,
    limit: int = 3,
) -> list[Path]:
    """Update the related field of the top-N similar notes with a backlink.

    Returns the list of paths that were actually modified.
    """
    modified: list[Path] = []
    for note_path in similar_note_paths[:limit]:
        if _update_related_field(note_path, new_note_topic):
            modified.append(note_path)
            logger.info("Added backlink '%s' to %s", new_note_topic, note_path)
    return modified
