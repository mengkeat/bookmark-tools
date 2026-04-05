from __future__ import annotations

import argparse
import logging
import shutil
from pathlib import Path
from typing import Sequence

from .classify import (
    call_llm,
    heuristic_classification,
    rank_similar_notes,
)
from .paths import get_bookmarks_dir, load_env
from .vault_profile import collect_existing_notes, parse_frontmatter

logger = logging.getLogger(__name__)


def propose_reclassifications(
    bookmarks_dir: Path | None = None,
    *,
    use_llm: bool = False,
) -> list[dict[str, str]]:
    """Propose folder reclassifications for existing bookmarks.

    Returns a list of dicts with keys: path, title, current_folder,
    proposed_folder.  Only includes entries where the proposed folder
    differs from the current one.
    """
    if bookmarks_dir is None:
        bookmarks_dir = get_bookmarks_dir()

    profile = collect_existing_notes(bookmarks_dir=bookmarks_dir)
    proposals: list[dict[str, str]] = []

    for note_path in sorted(bookmarks_dir.rglob("*.md")):
        metadata = parse_frontmatter(note_path)
        url = str(metadata.get("url", "")).strip()
        title = str(metadata.get("title", note_path.stem))
        current_folder = str(note_path.relative_to(bookmarks_dir).parent)
        if current_folder == ".":
            current_folder = ""

        if not url or not (url.startswith("http://") or url.startswith("https://")):
            continue

        page_data = {
            "url": url,
            "title": title,
            "description": str(metadata.get("description", "")),
            "language": str(metadata.get("language", "en")),
            "content": title,
        }

        similar_notes = rank_similar_notes(page_data, profile)

        if use_llm:
            result = call_llm(
                page_data, profile, similar_notes, allow_new_subfolder=False
            )
            if result is None:
                result = heuristic_classification(page_data, profile, similar_notes)
        else:
            result = heuristic_classification(page_data, profile, similar_notes)

        proposed_folder = str(result.get("folder", current_folder))

        if proposed_folder != current_folder:
            proposals.append(
                {
                    "path": str(note_path),
                    "title": title,
                    "current_folder": current_folder or "(root)",
                    "proposed_folder": proposed_folder or "(root)",
                }
            )

    return proposals


def apply_reclassifications(
    proposals: list[dict[str, str]],
    bookmarks_dir: Path | None = None,
) -> tuple[int, list[dict[str, str]]]:
    """Execute the proposed folder moves by renaming files on disk.

    Returns (moved_count, errors) where errors is a list of dicts with
    ``path`` and ``error`` keys for any moves that failed.
    """
    if bookmarks_dir is None:
        bookmarks_dir = get_bookmarks_dir()

    moved = 0
    errors: list[dict[str, str]] = []

    for entry in proposals:
        src = Path(entry["path"])
        proposed_folder = entry["proposed_folder"].strip("()")
        if proposed_folder == "root":
            proposed_folder = ""
        dest_dir = bookmarks_dir / proposed_folder if proposed_folder else bookmarks_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name

        # Avoid overwriting an existing file at the destination
        if dest.exists() and dest != src:
            stem = src.stem
            suffix = src.suffix
            index = 2
            while dest.exists():
                dest = dest_dir / f"{stem}-{index}{suffix}"
                index += 1

        try:
            shutil.move(str(src), str(dest))
            logger.info("Moved %s → %s", src, dest)
            moved += 1
        except OSError as exc:
            errors.append({"path": str(src), "error": str(exc)})
            logger.error("Failed to move %s: %s", src, exc)

    if moved:
        try:
            from .search import refresh_search_index

            refresh_search_index(bookmarks_dir=bookmarks_dir)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Search index refresh failed after moves: %s", exc)

    return moved, errors


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for folder reorganization."""
    parser = argparse.ArgumentParser(
        description="Propose folder reclassifications for existing bookmarks."
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Use LLM for classification (default: heuristic only)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print proposed moves without applying them (default behavior without --apply)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute the proposed folder moves (moves files on disk)",
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
    """Run folder reorganization analysis and print proposals."""
    load_env()
    args = parse_args(argv)
    from .cli import configure_logging

    configure_logging(verbose=args.verbose, quiet=args.quiet)

    proposals = propose_reclassifications(use_llm=args.llm)
    if not proposals:
        print("No reclassifications proposed. All bookmarks are well-placed.")
        return 0

    print(f"Found {len(proposals)} proposed reclassification(s):\n")
    for entry in proposals:
        print(f"  {entry['title']}")
        print(f"    Current: {entry['current_folder']}")
        print(f"    Proposed: {entry['proposed_folder']}")
        print(f"    Path: {entry['path']}")
        print()

    if args.apply and not args.dry_run:
        moved, errors = apply_reclassifications(proposals)
        print(f"Applied {moved} move(s).")
        if errors:
            for err in errors:
                logger.error("Failed to move %s: %s", err["path"], err["error"])
            return 1
    else:
        print("Run with --apply to execute these moves.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
