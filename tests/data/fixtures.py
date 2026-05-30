"""Test data fixtures derived from the ML-AI bookmark vault.

This module provides programmatic access to the 47 real-world bookmark notes
stored in ``tests/data/bookmarks/ML-AI/``.  All notes are in schema v1 format.

Usage in tests::

    from tests.data.fixtures import BOOKMARKS_DIR, copy_bookmarks

    def test_something(tmp_path):
        vault = copy_bookmarks(tmp_path / "Bookmarks")
        profile = collect_existing_notes(bookmarks_dir=vault)
        assert len(profile.notes) == NOTE_COUNT
"""

from __future__ import annotations

import shutil
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent
"""``tests/data/`` — root of the test data directory."""

BOOKMARKS_DIR = DATA_DIR / "bookmarks"
"""``tests/data/bookmarks/`` — vault-compatible bookmark directory."""

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NOTE_COUNT: int = 47
"""Total number of bookmark notes in the test dataset."""

FOLDERS: list[str] = [
    "ML-AI",
    "ML-AI/Agents",
    "ML-AI/Computer-Vision",
    "ML-AI/Diffusion",
    "ML-AI/General",
    "ML-AI/LLMs",
    "ML-AI/Reinforcement-Learning",
]
"""All subfolder paths present in the test data."""

# ---------------------------------------------------------------------------
# Derived collections (loaded lazily)
# ---------------------------------------------------------------------------

_all_note_paths: list[Path] | None = None


def all_note_paths() -> list[Path]:
    """Return sorted list of all ``.md`` paths in the test dataset."""
    global _all_note_paths
    if _all_note_paths is None:
        _all_note_paths = sorted(BOOKMARKS_DIR.rglob("*.md"))
    return _all_note_paths


def all_note_texts() -> dict[str, str]:
    """Return ``{stem: full_text}`` for every note in the dataset."""
    return {p.stem: p.read_text(encoding="utf-8") for p in all_note_paths()}


def all_note_metadata() -> dict[str, dict]:
    """Return ``{stem: frontmatter_dict}`` for every note.

    Uses the project's own ``parse_note_file`` for robust parsing.
    """
    from bookmark_tools.note_schema import parse_note_file

    return {
        p.stem: dict(parse_note_file(p).frontmatter)
        for p in all_note_paths()
    }


def tag_universe() -> set[str]:
    """Return the union of all tags across all notes."""
    meta = all_note_metadata()
    tags: set[str] = set()
    for m in meta.values():
        raw = m.get("tags", [])
        if isinstance(raw, list):
            tags.update(str(t) for t in raw)
    return tags


def type_distribution() -> dict[str, int]:
    """Return ``{type: count}`` across all notes."""
    from collections import Counter

    meta = all_note_metadata()
    return dict(Counter(str(m.get("type", "unknown")) for m in meta.values()))


def notes_by_folder() -> dict[str, list[Path]]:
    """Return ``{folder: [path, ...]}`` mapping."""
    result: dict[str, list[Path]] = {}
    for p in all_note_paths():
        folder = str(p.relative_to(BOOKMARKS_DIR).parent)
        result.setdefault(folder, []).append(p)
    return result


# ---------------------------------------------------------------------------
# Vault setup helpers
# ---------------------------------------------------------------------------


def copy_bookmarks(dest: Path) -> Path:
    """Copy the entire test bookmark tree into *dest*.

    Returns the destination path (``dest``), which can be used directly
    as ``bookmarks_dir`` for vault functions.

    Example::

        tmp = Path(tmp_path) / "Bookmarks"
        vault = copy_bookmarks(tmp)
        profile = collect_existing_notes(bookmarks_dir=vault)
    """
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(BOOKMARKS_DIR, dest)
    return dest


def setup_vault(tmp_dir: Path) -> tuple[Path, Path]:
    """Create a minimal vault structure with the full test dataset.

    Returns ``(vault_dir, bookmarks_dir)``.
    """
    vault_dir = tmp_dir / "Vault"
    bookmarks_dir = vault_dir / "Bookmarks"
    copy_bookmarks(bookmarks_dir)
    return vault_dir, bookmarks_dir
