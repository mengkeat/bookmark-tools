"""CLI commands for querying the bookmark graph.

Provides ``bookmark-backlinks`` and ``bookmark-graph``.  Both resolve a
URL or note path to a bookmark id and query the catalog edges table, which
must already exist (run ``bookmark-rebuild --catalog`` to build it).
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
from pathlib import Path
from typing import Sequence

from .catalog import BOOKMARKS_TABLE
from .delete import find_note
from .graph import (
    bookmark_id_for_note,
    get_backlinks,
    get_related,
    open_graph,
    traverse,
)
from .note_schema import parse_note_file
from .paths import (
    BookmarkPathError,
    get_search_index_path,
    load_env,
    require_bookmarks_dir,
)

logger = logging.getLogger(__name__)


def _resolve_bookmark(target: str, bookmarks_dir: Path) -> tuple[str, Path] | None:
    """Resolve a URL or note path to (bookmark_id, note_path)."""
    note_path = find_note(target, bookmarks_dir=bookmarks_dir)
    if note_path is None:
        return None
    note = parse_note_file(note_path)
    if not note.is_bookmark:
        return None
    return bookmark_id_for_note(note), note_path


def _label(connection: sqlite3.Connection, bookmark_id: str) -> dict[str, str]:
    """Return {id,title,url,note_path} for a bookmark id."""
    row = connection.execute(
        f"SELECT id, title, url, note_path FROM {BOOKMARKS_TABLE} WHERE id = ?",
        (bookmark_id,),
    ).fetchone()
    if row is None:
        return {"id": bookmark_id, "title": bookmark_id, "url": "", "note_path": ""}
    return {
        "id": row["id"],
        "title": row["title"] or row["url"] or row["id"],
        "url": row["url"] or "",
        "note_path": row["note_path"] or "",
    }


# ---------------------------------------------------------------------------
# bookmark-backlinks
# ---------------------------------------------------------------------------


def _backlinks_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Show bookmarks that link to a given bookmark."
    )
    parser.add_argument("target", help="URL or note path of the bookmark")
    parser.add_argument(
        "--related",
        action="store_true",
        help="Also show bookmarks sharing tags/domain/related topics",
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_output", help="Emit JSON output"
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--quiet", "-q", action="store_true")
    return parser.parse_args(argv)


def backlinks_main(argv: Sequence[str] | None = None) -> int:
    """Run the bookmark-backlinks command."""
    load_env()
    args = _backlinks_args(argv)
    from .logging_config import configure_logging

    configure_logging(verbose=args.verbose, quiet=args.quiet)

    try:
        bookmarks_dir = require_bookmarks_dir()
    except BookmarkPathError as exc:
        logger.error("%s", exc)
        return 1

    database_path = get_search_index_path()
    if not database_path.exists():
        logger.error(
            "Catalog database not found. Run `bookmark-rebuild --catalog` first."
        )
        return 1

    resolved = _resolve_bookmark(args.target, bookmarks_dir)
    if resolved is None:
        logger.error("No bookmark found for: %s", args.target)
        return 1
    bookmark_id, _ = resolved

    connection = open_graph(database_path)
    try:
        backlinks = get_backlinks(connection, bookmark_id)
        related = (
            get_related(connection, bookmark_id) if args.related else []
        )
        target = _label(connection, bookmark_id)
    finally:
        connection.close()

    if args.json_output:
        print(
            json.dumps(
                {
                    "target": target,
                    "backlinks": [
                        {
                            "id": b.bookmark_id,
                            "title": b.title,
                            "url": b.url,
                            "note_path": b.note_path,
                        }
                        for b in backlinks
                    ],
                    "related": [
                        {
                            "id": r.bookmark_id,
                            "title": r.title,
                            "url": r.url,
                            "shared": r.shared,
                            "via": r.via,
                        }
                        for r in related
                    ],
                },
                indent=2,
            )
        )
        return 0

    print(f"Backlinks to {target['title']} ({target['url']}): {len(backlinks)}")
    for b in backlinks:
        print(f"  - {b.title}  {b.url}  [{b.note_path}]")
    if args.related:
        print(f"\nRelated ({len(related)}):")
        for r in related:
            print(f"  - {r.title}  (shared {r.shared} via {', '.join(r.via)})")
    return 0


# ---------------------------------------------------------------------------
# bookmark-graph
# ---------------------------------------------------------------------------


def _graph_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Traverse the bookmark graph from a starting bookmark."
    )
    parser.add_argument("target", help="URL or note path of the bookmark")
    parser.add_argument(
        "--depth",
        type=int,
        default=1,
        help="Maximum number of hops to traverse (default: 1)",
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_output", help="Emit JSON output"
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--quiet", "-q", action="store_true")
    return parser.parse_args(argv)


def graph_main(argv: Sequence[str] | None = None) -> int:
    """Run the bookmark-graph command."""
    load_env()
    args = _graph_args(argv)
    from .logging_config import configure_logging

    configure_logging(verbose=args.verbose, quiet=args.quiet)

    if args.depth < 1:
        logger.error("--depth must be at least 1.")
        return 1

    try:
        bookmarks_dir = require_bookmarks_dir()
    except BookmarkPathError as exc:
        logger.error("%s", exc)
        return 1

    database_path = get_search_index_path()
    if not database_path.exists():
        logger.error(
            "Catalog database not found. Run `bookmark-rebuild --catalog` first."
        )
        return 1

    resolved = _resolve_bookmark(args.target, bookmarks_dir)
    if resolved is None:
        logger.error("No bookmark found for: %s", args.target)
        return 1
    bookmark_id, _ = resolved

    connection = open_graph(database_path)
    try:
        distances = traverse(connection, bookmark_id, depth=args.depth)
        target = _label(connection, bookmark_id)
        nodes = [
            {**_label(connection, node_id), "depth": hop}
            for node_id, hop in sorted(distances.items(), key=lambda kv: (kv[1],))
        ]
    finally:
        connection.close()

    if args.json_output:
        print(json.dumps({"target": target, "nodes": nodes}, indent=2))
        return 0

    print(f"Graph for {target['title']} ({target['url']}), depth {args.depth}:")
    if not nodes:
        print("  (no connected bookmarks)")
        return 0
    for hop in range(1, args.depth + 1):
        at_depth = [n for n in nodes if n["depth"] == hop]
        if not at_depth:
            continue
        print(f"\nDepth {hop} ({len(at_depth)}):")
        for node in at_depth:
            print(f"  - {node['title']}  {node['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(backlinks_main())
