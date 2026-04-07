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
    """Find a bookmark note file by its URL.

    Performs a full vault scan.  Prefer passing a pre-built
    ``BookmarkProfile`` and using ``profile.url_index`` directly when a
    profile is already available, to avoid scanning the vault twice.
    """
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

    # Single vault scan — use the url_index from the profile instead of a
    # separate rglob pass in find_note_by_url.
    profile = collect_existing_notes(bookmarks_dir=bookmarks_dir)
    note_path = profile.url_index.get(url.rstrip("/"))
    if note_path is None:
        return None

    old_metadata, _ = read_frontmatter(note_path)
    old_created = str(old_metadata.get("created", "")).strip()
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


def bulk_update(
    *,
    bookmarks_dir: Path | None = None,
    folder: str | None = None,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Re-fetch and re-classify all bookmarks, or those in *folder*.

    Returns ``(success_count, failure_count)``.
    """
    if bookmarks_dir is None:
        bookmarks_dir = get_bookmarks_dir()

    profile = collect_existing_notes(bookmarks_dir=bookmarks_dir)

    notes = profile.notes
    if folder:
        normalized_folder = folder.strip().strip("/")
        notes = [
            n
            for n in notes
            if n.folder == normalized_folder
            or n.folder.startswith(f"{normalized_folder}/")
        ]

    successes = 0
    failures = 0
    for note in notes:
        if not note.url:
            logger.debug("Skipping %s (no URL)", note.path)
            continue
        logger.info("Updating %s …", note.url)
        try:
            result = update_bookmark(
                note.url, bookmarks_dir=bookmarks_dir, dry_run=dry_run
            )
            if result is None:
                logger.warning("Not found in vault: %s", note.url)
                failures += 1
            else:
                note_path, note_text = result
                if dry_run:
                    print(f"Target: {note_path}")
                    print()
                    print(note_text)
                    print("─" * 60)
                else:
                    print(f"Updated {note_path}")
                successes += 1
        except Exception as exc:
            logger.warning(
                "Failed to update %s (%s: %s)",
                note.url,
                exc.__class__.__name__,
                exc,
            )
            failures += 1

    return successes, failures


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for bookmark update."""
    parser = argparse.ArgumentParser(
        description="Re-fetch and re-classify an existing bookmark."
    )
    parser.add_argument(
        "url", nargs="?", default=None, help="URL of the bookmark to update"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="update_all",
        help="Re-process all bookmarks in the vault",
    )
    parser.add_argument(
        "--folder",
        type=str,
        default=None,
        help="Re-process all bookmarks in the given folder (and subfolders)",
    )
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

    if args.update_all or args.folder:
        if args.url:
            logger.error("Cannot specify a URL together with --all or --folder.")
            return 1
        successes, failures = bulk_update(
            folder=args.folder, dry_run=args.dry_run
        )
        total = successes + failures
        print(f"\nUpdated {successes}/{total} bookmarks successfully.")
        return 1 if successes == 0 and total > 0 else 0

    if not args.url:
        logger.error("Either a URL argument, --all, or --folder is required.")
        return 1

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
