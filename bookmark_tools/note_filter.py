from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

ARCHIVE_SIDECAR_SUFFIX = ".content.md"


def is_archive_sidecar(path: Path) -> bool:
    """Return True when *path* is a cleaned-content archive sidecar."""
    return path.name.endswith(ARCHIVE_SIDECAR_SUFFIX)


def iter_bookmark_note_paths(
    bookmarks_dir: Path, *, recursive: bool = True
) -> Iterator[Path]:
    """Yield Markdown note paths that should be treated as bookmark records."""
    pattern = "**/*.md" if recursive else "*.md"
    for note_path in sorted(bookmarks_dir.glob(pattern)):
        if is_archive_sidecar(note_path):
            continue
        yield note_path
