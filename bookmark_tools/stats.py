from __future__ import annotations

import argparse
import logging
from collections import Counter
from pathlib import Path
from typing import Sequence

from .paths import get_bookmarks_dir, load_env
from .vault_profile import collect_existing_notes, parse_frontmatter

logger = logging.getLogger(__name__)


def collect_stats(bookmarks_dir: Path | None = None) -> dict[str, object]:
    """Collect vault statistics from existing bookmark notes."""
    if bookmarks_dir is None:
        bookmarks_dir = get_bookmarks_dir()

    profile = collect_existing_notes(bookmarks_dir=bookmarks_dir)
    folder_counts: Counter[str] = Counter()
    tag_counts: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()
    parent_topic_counts: Counter[str] = Counter()

    for note in profile.notes:
        folder_counts[note.folder or "(root)"] += 1
        for tag in note.tags:
            tag_counts[tag.lower()] += 1
        if note.parent_topic:
            parent_topic_counts[note.parent_topic] += 1

    for note_path in sorted(bookmarks_dir.rglob("*.md")):
        metadata = parse_frontmatter(note_path)
        btype = str(metadata.get("type", "")).strip().lower()
        if btype:
            type_counts[btype] += 1

    return {
        "total_bookmarks": len(profile.notes),
        "total_folders": len(profile.folders),
        "bookmarks_per_folder": dict(folder_counts.most_common()),
        "top_tags": dict(tag_counts.most_common(20)),
        "top_parent_topics": dict(parent_topic_counts.most_common(10)),
        "type_distribution": dict(type_counts.most_common()),
    }


def format_stats(stats: dict[str, object]) -> str:
    """Format collected stats into a human-readable report."""
    lines: list[str] = []
    lines.append(f"Total bookmarks: {stats['total_bookmarks']}")
    lines.append(f"Total folders: {stats['total_folders']}")

    lines.append("")
    lines.append("Bookmarks per folder:")
    folder_counts = stats["bookmarks_per_folder"]
    assert isinstance(folder_counts, dict)
    for folder, count in folder_counts.items():
        lines.append(f"  {folder}: {count}")

    lines.append("")
    lines.append("Type distribution:")
    type_dist = stats["type_distribution"]
    assert isinstance(type_dist, dict)
    for btype, count in type_dist.items():
        lines.append(f"  {btype}: {count}")

    lines.append("")
    lines.append("Top tags:")
    top_tags = stats["top_tags"]
    assert isinstance(top_tags, dict)
    for tag, count in top_tags.items():
        lines.append(f"  {tag}: {count}")

    lines.append("")
    lines.append("Top parent topics:")
    top_topics = stats["top_parent_topics"]
    assert isinstance(top_topics, dict)
    for topic, count in top_topics.items():
        lines.append(f"  {topic}: {count}")

    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for bookmark stats."""
    parser = argparse.ArgumentParser(
        description="Show bookmark vault statistics."
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
    """Run bookmark stats and print the report."""
    load_env()
    args = parse_args(argv)
    from .cli import configure_logging

    configure_logging(verbose=args.verbose, quiet=args.quiet)

    stats = collect_stats()
    print(format_stats(stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
