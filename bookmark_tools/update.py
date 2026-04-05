from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Sequence

from .classify import (
    call_llm,
    heuristic_classification,
    rank_similar_notes,
    validate_folder,
)
from .cli import configure_logging, normalize_metadata
from .fetch import extract_page_data
from .paths import get_bookmarks_dir, load_env
from .render import render_note
from .summarize import generate_summary
from .vault_profile import collect_existing_notes, read_frontmatter

logger = logging.getLogger(__name__)


def find_note_by_url(url: str, bookmarks_dir: Path | None = None) -> Path | None:
    """Find a bookmark note file by its URL."""
    if bookmarks_dir is None:
        bookmarks_dir = get_bookmarks_dir()
    normalized = url.rstrip("/")
    for note_path in bookmarks_dir.rglob("*.md"):
        metadata, _ = read_frontmatter(note_path)
        existing_url = str(metadata.get("url", "")).strip().rstrip("/")
        if existing_url == normalized:
            return note_path
    return None


def update_bookmark(
    url: str,
    *,
    bookmarks_dir: Path | None = None,
    dry_run: bool = False,
) -> tuple[Path, str] | None:
    """Re-fetch and re-classify an existing bookmark, preserving its path.

    Returns (note_path, rendered_note) on success, or None if the URL
    is not found in the vault.
    """
    if bookmarks_dir is None:
        bookmarks_dir = get_bookmarks_dir()

    note_path = find_note_by_url(url, bookmarks_dir=bookmarks_dir)
    if note_path is None:
        return None

    old_metadata, _ = read_frontmatter(note_path)
    old_created = str(old_metadata.get("created", "")).strip()

    profile = collect_existing_notes(bookmarks_dir=bookmarks_dir)
    page_data = extract_page_data(url)
    similar_notes = rank_similar_notes(page_data, profile)
    llm_metadata = call_llm(page_data, profile, similar_notes, allow_new_subfolder=True)
    metadata = llm_metadata or heuristic_classification(
        page_data, profile, similar_notes
    )

    classification_summary = (
        str(llm_metadata.get("summary", "")).strip() if llm_metadata else ""
    )
    summary_override = generate_summary(
        page_data["url"],
        page_data,
        classification_summary=classification_summary,
    )

    folder, _ = validate_folder(
        str(metadata.get("folder", note_path.relative_to(bookmarks_dir).parent)),
        allow_new_subfolder=True,
        bookmarks_dir=bookmarks_dir,
    )

    normalized = normalize_metadata(
        metadata,
        page_data,
        folder,
        profile,
        similar_notes,
        used_llm_classification=llm_metadata is not None,
        summary_override=summary_override,
    )

    note_text = render_note(
        normalized,
        page_data["url"],
        profile,
        created_override=old_created or None,
    )

    if not dry_run:
        note_path.write_text(note_text, encoding="utf-8")

    return note_path, note_text


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for bookmark update."""
    parser = argparse.ArgumentParser(
        description="Re-fetch and re-classify an existing bookmark."
    )
    parser.add_argument("url", help="URL of the bookmark to update")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the updated note instead of writing it",
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
    """Run the bookmark update workflow."""
    load_env()
    args = parse_args(argv)
    configure_logging(verbose=args.verbose, quiet=args.quiet)

    result = update_bookmark(args.url, dry_run=args.dry_run)
    if result is None:
        logger.error("No bookmark found for URL: %s", args.url)
        return 1

    note_path, note_text = result
    if args.dry_run:
        print(f"Target: {note_path}")
        print()
        print(note_text)
    else:
        print(f"Updated {note_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
