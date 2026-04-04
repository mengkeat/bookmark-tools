from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from .embeddings import EmbeddingMatch

logger = logging.getLogger(__name__)

from .paths import get_bookmarks_dir, get_search_index_path, load_env
from .search_documents import collect_search_documents
from .search_index import (
    SearchResult,
    rebuild_search_index,
    search_index,
    update_search_index,
)

DEFAULT_SEARCH_LIMIT = 10
DEFAULT_SIMILARITY_THRESHOLD = 0.40


def _positive_int(value: str) -> int:
    """Parse a positive integer argument value."""
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("limit must be at least 1")
    return parsed


def refresh_search_index(
    *,
    bookmarks_dir: Path | None = None,
    database_path: Path | None = None,
    rebuild: bool = False,
) -> None:
    """Refresh the bookmark search index.

    Performs an incremental update by default.  Pass ``rebuild=True``
    to drop and recreate the index from scratch.
    """
    if bookmarks_dir is None:
        bookmarks_dir = get_bookmarks_dir()
    if database_path is None:
        database_path = get_search_index_path()
    documents = collect_search_documents(bookmarks_dir=bookmarks_dir)
    if rebuild:
        rebuild_search_index(documents, database_path=database_path)
    else:
        update_search_index(documents, database_path=database_path)


def search_bookmarks(
    query: str,
    *,
    bookmarks_dir: Path | None = None,
    database_path: Path | None = None,
    folder: str | None = None,
    limit: int = DEFAULT_SEARCH_LIMIT,
    rebuild: bool = False,
) -> list[SearchResult]:
    """Refresh the index and return BM25-ranked search results.

    Uses incremental indexing by default.  Pass ``rebuild=True`` to
    force a full index rebuild.
    """
    if bookmarks_dir is None:
        bookmarks_dir = get_bookmarks_dir()
    if database_path is None:
        database_path = get_search_index_path()
    refresh_search_index(
        bookmarks_dir=bookmarks_dir,
        database_path=database_path,
        rebuild=rebuild,
    )
    return search_index(
        query,
        database_path=database_path,
        folder=folder,
        limit=limit,
    )


def search_bookmarks_semantic(
    query: str,
    *,
    bookmarks_dir: Path | None = None,
    database_path: Path | None = None,
    folder: str | None = None,
    limit: int = DEFAULT_SEARCH_LIMIT,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> list[SearchResult]:
    """Refresh embeddings and return cosine-similarity-ranked search results."""
    from .embeddings import refresh_embeddings, semantic_search

    if bookmarks_dir is None:
        bookmarks_dir = get_bookmarks_dir()
    if database_path is None:
        database_path = get_search_index_path()
    documents = collect_search_documents(bookmarks_dir=bookmarks_dir)
    refresh_embeddings(documents, database_path=database_path)
    matches = semantic_search(
        query,
        database_path=database_path,
        folder=folder,
        limit=limit,
        threshold=threshold,
    )
    return [_embedding_match_to_result(match) for match in matches]


def _embedding_match_to_result(match: EmbeddingMatch) -> SearchResult:
    """Convert an EmbeddingMatch to a SearchResult for uniform output."""
    return SearchResult(
        path=match.path,
        url=match.url,
        title=match.title,
        folder=match.folder,
        description=match.description,
        score=match.similarity,
    )


RRF_RANK_CONSTANT = 60
HYBRID_CANDIDATE_MULTIPLIER = 3


def _reciprocal_rank_fusion(
    bm25_results: list[SearchResult],
    semantic_results: list[SearchResult],
    limit: int,
) -> list[SearchResult]:
    """Merge two ranked lists using Reciprocal Rank Fusion (RRF).

    Each result receives score = sum(1 / (k + rank)) across the lists
    it appears in.  Results are keyed by path so duplicates are merged.
    The combined ``SearchResult.score`` is the fused RRF score.
    """
    scores: dict[Path, float] = {}
    result_map: dict[Path, SearchResult] = {}

    for rank, result in enumerate(bm25_results, start=1):
        scores[result.path] = scores.get(result.path, 0.0) + 1.0 / (RRF_RANK_CONSTANT + rank)
        result_map.setdefault(result.path, result)

    for rank, result in enumerate(semantic_results, start=1):
        scores[result.path] = scores.get(result.path, 0.0) + 1.0 / (RRF_RANK_CONSTANT + rank)
        result_map.setdefault(result.path, result)

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [
        SearchResult(
            path=path,
            url=result_map[path].url,
            title=result_map[path].title,
            folder=result_map[path].folder,
            description=result_map[path].description,
            score=round(score, 6),
        )
        for path, score in ranked[:limit]
    ]


def search_bookmarks_hybrid(
    query: str,
    *,
    bookmarks_dir: Path | None = None,
    database_path: Path | None = None,
    folder: str | None = None,
    limit: int = DEFAULT_SEARCH_LIMIT,
    rebuild: bool = False,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> list[SearchResult]:
    """Combine BM25 and semantic search via Reciprocal Rank Fusion."""
    from .embeddings import refresh_embeddings, semantic_search

    if bookmarks_dir is None:
        bookmarks_dir = get_bookmarks_dir()
    if database_path is None:
        database_path = get_search_index_path()
    documents = collect_search_documents(bookmarks_dir=bookmarks_dir)

    # Build / refresh both indexes
    if rebuild:
        rebuild_search_index(documents, database_path=database_path)
    else:
        update_search_index(documents, database_path=database_path)
    refresh_embeddings(documents, database_path=database_path)

    candidate_limit = limit * HYBRID_CANDIDATE_MULTIPLIER

    bm25_results = search_index(
        query,
        database_path=database_path,
        folder=folder,
        limit=candidate_limit,
    )

    semantic_results = [
        _embedding_match_to_result(match)
        for match in semantic_search(
            query,
            database_path=database_path,
            folder=folder,
            limit=candidate_limit,
            threshold=threshold,
        )
    ]

    return _reciprocal_rank_fusion(bm25_results, semantic_results, limit)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for bookmark search."""
    parser = argparse.ArgumentParser(
        description="Search bookmark notes with FTS5 BM25 or semantic vector search."
    )
    parser.add_argument("query", help="Search query")
    parser.add_argument(
        "--folder",
        help="Restrict results to a folder and its subfolders",
    )
    parser.add_argument(
        "--limit",
        type=_positive_int,
        default=DEFAULT_SEARCH_LIMIT,
        help=f"Maximum number of results to return (default: {DEFAULT_SEARCH_LIMIT})",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Force a full index rebuild instead of incremental update",
    )
    parser.add_argument(
        "--semantic",
        action="store_true",
        help="Use embedding-based semantic search instead of keyword FTS5 search",
    )
    parser.add_argument(
        "--hybrid",
        action="store_true",
        help="Combine BM25 and semantic search via Reciprocal Rank Fusion",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_SIMILARITY_THRESHOLD,
        help=f"Minimum similarity score for semantic/hybrid results (default: {DEFAULT_SIMILARITY_THRESHOLD})",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose (debug) logging output",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress all logging output except errors",
    )
    return parser.parse_args(argv)


def _format_description(description: str, *, limit: int = 160) -> str:
    """Trim result descriptions for terminal output."""
    if len(description) <= limit:
        return description
    return f"{description[: limit - 3].rstrip()}..."


def _display_folder(folder: str) -> str:
    """Display a root folder with a readable fallback label."""
    return folder or "(root)"


def _print_result(position: int, result: SearchResult) -> None:
    """Render a single search result in a readable CLI format."""
    print(f"{position}. {result.title}  (score: {result.score:.4f})")
    print(f"   Folder: {_display_folder(result.folder)}")
    print(f"   URL: {result.url}")
    print(f"   Path: {result.path}")
    if result.description:
        print(f"   Description: {_format_description(result.description)}")
    print()


def main(argv: Sequence[str] | None = None) -> int:
    """Run bookmark search and print ranked results."""
    load_env()
    args = parse_args(argv)
    from .cli import configure_logging
    configure_logging(verbose=args.verbose, quiet=args.quiet)
    try:
        if args.hybrid:
            results = search_bookmarks_hybrid(
                args.query,
                folder=args.folder,
                limit=args.limit,
                rebuild=args.rebuild,
                threshold=args.threshold,
            )
        elif args.semantic:
            results = search_bookmarks_semantic(
                args.query,
                folder=args.folder,
                limit=args.limit,
                threshold=args.threshold,
            )
        else:
            results = search_bookmarks(
                args.query,
                folder=args.folder,
                limit=args.limit,
                rebuild=args.rebuild,
            )
    except ValueError as exc:
        logger.error("%s", exc)
        return 1
    if not results:
        print("No bookmarks found.")
        return 0
    for position, result in enumerate(results, start=1):
        _print_result(position, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
