from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Sequence

from .paths import get_bookmarks_dir, get_search_index_path, load_env
from .search_index import MTIME_TABLE, SEARCH_TABLE
from .vault_profile import collect_existing_notes, read_frontmatter

logger = logging.getLogger(__name__)


def _remove_from_search_index(note_path: Path, database_path: Path) -> None:
    """Remove a note from the FTS5 search index and mtime table."""
    import sqlite3

    if not database_path.exists():
        return
    connection = sqlite3.connect(database_path)
    try:
        path_str = str(note_path)
        with connection:
            connection.execute(
                f"DELETE FROM {SEARCH_TABLE} WHERE path = ?", (path_str,)
            )
            connection.execute(
                f"DELETE FROM {MTIME_TABLE} WHERE path = ?", (path_str,)
            )
    except sqlite3.OperationalError:
        pass
    finally:
        connection.close()


def _remove_from_embedding_store(note_path: Path, database_path: Path) -> None:
    """Remove a note from the embedding store."""
    import sqlite3

    from .embeddings import EMBEDDING_TABLE

    if not database_path.exists():
        return
    connection = sqlite3.connect(database_path)
    try:
        with connection:
            connection.execute(
                f"DELETE FROM {EMBEDDING_TABLE} WHERE path = ?", (str(note_path),)
            )
    except sqlite3.OperationalError:
        pass
    finally:
        connection.close()


def find_note(
    target: str,
    *,
    bookmarks_dir: Path | None = None,
) -> Path | None:
    """Find a bookmark note by URL or file path.

    If *target* looks like a URL (contains ``://``), the vault is scanned
    to locate the note by its frontmatter ``url`` field.  Otherwise
    *target* is treated as a file path (absolute or relative to
    *bookmarks_dir*).
    """
    if bookmarks_dir is None:
        bookmarks_dir = get_bookmarks_dir()

    if "://" in target:
        profile = collect_existing_notes(bookmarks_dir=bookmarks_dir)
        return profile.url_index.get(target.rstrip("/"))

    candidate = Path(target)
    if candidate.is_absolute():
        return candidate if candidate.is_file() else None
    resolved = (bookmarks_dir / candidate).resolve()
    return resolved if resolved.is_file() else None


def delete_bookmark(
    target: str,
    *,
    bookmarks_dir: Path | None = None,
    database_path: Path | None = None,
    dry_run: bool = False,
) -> Path | None:
    """Delete a bookmark by URL or file path.

    Returns the deleted note path on success, or ``None`` if the
    bookmark was not found.
    """
    if bookmarks_dir is None:
        bookmarks_dir = get_bookmarks_dir()
    if database_path is None:
        database_path = get_search_index_path()

    note_path = find_note(target, bookmarks_dir=bookmarks_dir)
    if note_path is None:
        return None

    if dry_run:
        return note_path

    _remove_from_search_index(note_path, database_path)
    _remove_from_embedding_store(note_path, database_path)
    note_path.unlink()

    # Remove empty parent directories up to (but not including) bookmarks_dir
    parent = note_path.parent
    resolved_bookmarks = bookmarks_dir.resolve()
    while parent.resolve() != resolved_bookmarks and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent

    return note_path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for bookmark deletion."""
    parser = argparse.ArgumentParser(
        description="Delete a bookmark note by URL or file path."
    )
    parser.add_argument(
        "target",
        help="URL or file path of the bookmark to delete",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the note that would be deleted without removing it",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose (debug) logging output",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress all logging output except errors",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the bookmark deletion workflow."""
    load_env()
    args = parse_args(argv)
    from .cli import configure_logging

    configure_logging(verbose=args.verbose, quiet=args.quiet)

    note_path = delete_bookmark(args.target, dry_run=args.dry_run)
    if note_path is None:
        logger.error("No bookmark found for: %s", args.target)
        return 1

    if args.dry_run:
        print(f"Would delete: {note_path}")
    else:
        print(f"Deleted {note_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
