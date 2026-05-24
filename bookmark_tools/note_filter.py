from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

ARCHIVE_SIDECAR_SUFFIX = ".content.md"


def _is_bookmark(path: Path) -> bool:
    """Check if a Markdown file has a url field in its frontmatter."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    # Fast check: look for "url:" in the first few lines (frontmatter)
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return False
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key = line.split(":", 1)[0].strip() if ":" in line else ""
        if key == "url":
            return True
    return False


def is_archive_sidecar(path: Path) -> bool:
    """Return True when *path* is a cleaned-content archive sidecar."""
    return path.name.endswith(ARCHIVE_SIDECAR_SUFFIX)


def iter_bookmark_note_paths(
    bookmarks_dir: Path,
    *,
    recursive: bool = True,
    bookmark_only: bool = False,
) -> Iterator[Path]:
    """Yield Markdown note paths that should be treated as bookmark records.

    When *bookmark_only* is True, only files with a ``url`` field in their
    frontmatter are yielded, skipping non-bookmark Markdown files.
    """
    pattern = "**/*.md" if recursive else "*.md"
    for note_path in sorted(bookmarks_dir.glob(pattern)):
        if is_archive_sidecar(note_path):
            continue
        if bookmark_only and not _is_bookmark(note_path):
            continue
        yield note_path
