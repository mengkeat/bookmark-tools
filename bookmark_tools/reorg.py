from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Sequence

from .classify import (
    call_llm,
    heuristic_classification,
    rank_similar_notes,
)
from .fetch import extract_page_data
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
            result = call_llm(page_data, profile, similar_notes, allow_new_subfolder=False)
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
