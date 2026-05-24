from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .classify import get_llm_config
from .paths import (
    BookmarkPathError,
    get_search_index_path,
    load_env,
    require_bookmarks_dir,
)
from .search_documents import collect_search_documents
from .search_index import rebuild_search_index

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RebuildResult:
    """Result summary for a derived-state rebuild."""

    bookmarks_dir: Path
    database_path: Path
    document_count: int
    search_rebuilt: bool
    embeddings_rebuilt: bool
    embeddings_skipped_reason: str = ""

    def to_dict(self) -> dict[str, object]:
        """Return a stable JSON-serializable representation."""
        return {
            "bookmarks_dir": str(self.bookmarks_dir),
            "database_path": str(self.database_path),
            "document_count": self.document_count,
            "search_rebuilt": self.search_rebuilt,
            "embeddings_rebuilt": self.embeddings_rebuilt,
            "embeddings_skipped_reason": self.embeddings_skipped_reason,
        }


def rebuild_derived_state(
    *,
    bookmarks_dir: Path | None = None,
    database_path: Path | None = None,
    include_embeddings: bool = True,
    embedding_config: dict[str, str] | None = None,
) -> RebuildResult:
    """Rebuild all currently supported derived state from bookmark Markdown."""
    if bookmarks_dir is None:
        bookmarks_dir = require_bookmarks_dir()
    if database_path is None:
        database_path = get_search_index_path()

    documents = collect_search_documents(bookmarks_dir=bookmarks_dir)
    rebuild_search_index(documents, database_path=database_path)

    embeddings_rebuilt = False
    embeddings_skipped_reason = ""
    if include_embeddings:
        config = embedding_config if embedding_config is not None else get_llm_config()
        if config:
            from .embeddings import rebuild_embeddings

            rebuild_embeddings(documents, database_path=database_path, config=config)
            embeddings_rebuilt = True
        else:
            embeddings_skipped_reason = (
                "No LLM API key configured; skipped embedding rebuild."
            )
    else:
        embeddings_skipped_reason = "Embedding rebuild disabled."

    return RebuildResult(
        bookmarks_dir=bookmarks_dir,
        database_path=database_path,
        document_count=len(documents),
        search_rebuilt=True,
        embeddings_rebuilt=embeddings_rebuilt,
        embeddings_skipped_reason=embeddings_skipped_reason,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for bookmark rebuild."""
    parser = argparse.ArgumentParser(
        description="Rebuild derived bookmark state from Markdown notes."
    )
    parser.add_argument(
        "--no-embeddings",
        action="store_true",
        help="Rebuild only the FTS search index and skip embeddings",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print a JSON result object",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging output",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress all logging output except errors",
    )
    return parser.parse_args(argv)


def _format_text(result: RebuildResult) -> str:
    """Format a human-readable rebuild result."""
    lines = [
        "Rebuilt derived bookmark state.",
        f"Bookmarks: {result.document_count}",
        f"Search index: rebuilt at {result.database_path}",
    ]
    if result.embeddings_rebuilt:
        lines.append("Embeddings: rebuilt")
    else:
        lines.append(f"Embeddings: skipped ({result.embeddings_skipped_reason})")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the rebuild command."""
    load_env()
    args = parse_args(argv)
    from .cli import configure_logging

    configure_logging(verbose=args.verbose, quiet=args.quiet)
    try:
        result = rebuild_derived_state(include_embeddings=not args.no_embeddings)
    except (BookmarkPathError, ValueError) as exc:
        logger.error("%s", exc)
        return 1

    if args.json_output:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(_format_text(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
