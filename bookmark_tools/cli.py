from __future__ import annotations

import argparse
import logging
import os
import re
import urllib.error
from pathlib import Path

from .classify import (
    ALLOWED_BOOKMARK_TYPES,
    DEFAULT_BOOKMARK_TYPE,
    SimilarNote,
    call_llm,
    derive_parent_topic,
    derive_related_topics,
    derive_tags,
    enrich_tags_from_similar,
    find_existing_url,
    heuristic_classification,
    rank_similar_notes,
    validate_folder,
)
from .fetch import extract_page_data
from .paths import get_bookmarks_dir, load_env
from .render import infer_summary, render_note, slugify_filename, uniquify_path
from .summarize import generate_summary
from .types import BookmarkMetadata, NormalizedBookmarkMetadata, PageData
from .vault_profile import BookmarkProfile, collect_existing_notes

logger = logging.getLogger(__name__)

MAX_RELATED_ITEMS = 6
DEFAULT_LANGUAGE = "en"
DEFAULT_PARENT_TOPIC = "Bookmarks"
RELATED_TOPIC_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _folder_leaf_topic(folder: str) -> str:
    """Return the leaf topic for a folder path."""
    return folder.split("/")[-1] if folder else DEFAULT_PARENT_TOPIC


def _normalize_text(value: object, fallback: str) -> str:
    """Return a trimmed string or fallback when empty."""
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _normalize_text_list(
    values: object, *, lower: bool = False, limit: int | None = None
) -> list[str]:
    """Normalize arbitrary list-like values into filtered strings."""
    if not isinstance(values, list):
        return []
    items: list[str] = []
    for item in values:
        text = str(item).strip()
        if not text:
            continue
        items.append(text.lower() if lower else text)
        if limit is not None and len(items) >= limit:
            break
    return items


def _normalize_related_topics(values: object, *, limit: int | None = None) -> list[str]:
    """Normalize related topics to lowercase single-word tags."""
    raw_items = _normalize_text_list(values, lower=True)
    items: list[str] = []
    for raw_item in raw_items:
        leaf = re.split(r"[\\/]", raw_item)[-1].strip()
        candidate = re.sub(r"\s+", "-", leaf)
        candidate = re.sub(r"-{2,}", "-", candidate).strip("-")
        if not candidate or not RELATED_TOPIC_PATTERN.fullmatch(candidate):
            continue
        if candidate not in items:
            items.append(candidate)
        if limit is not None and len(items) >= limit:
            break
    return items


def _normalize_bookmark_type(value: object) -> str:
    """Normalize bookmark type to a supported value."""
    bookmark_type = _normalize_text(value, DEFAULT_BOOKMARK_TYPE).lower()
    return (
        bookmark_type
        if bookmark_type in ALLOWED_BOOKMARK_TYPES
        else DEFAULT_BOOKMARK_TYPE
    )


def _resolve_tags(
    metadata: BookmarkMetadata,
    page_data: PageData,
    folder: str,
    similar_notes: list[SimilarNote],
    used_llm_classification: bool,
) -> list[str]:
    """Resolve tags using LLM metadata first, then heuristic fallbacks."""
    tags_from_metadata = _normalize_text_list(metadata.get("tags"), lower=True)
    if used_llm_classification:
        return tags_from_metadata or [_folder_leaf_topic(folder).lower()]
    base_tags = tags_from_metadata or derive_tags(
        page_data["title"], page_data["description"], folder
    )
    return enrich_tags_from_similar(base_tags, similar_notes)


def _resolve_related(
    metadata: BookmarkMetadata,
    folder: str,
    tags: list[str],
    used_llm_classification: bool,
) -> list[str]:
    """Resolve related topics using metadata first, then a single fallback source."""
    related_from_metadata = _normalize_related_topics(
        metadata.get("related"),
        limit=MAX_RELATED_ITEMS,
    )
    if related_from_metadata:
        return related_from_metadata

    related_candidates = (
        tags if used_llm_classification else derive_related_topics(folder, tags)
    )
    return _normalize_related_topics(
        related_candidates,
        limit=MAX_RELATED_ITEMS,
    )


def _resolve_parent_topic(
    metadata: BookmarkMetadata,
    folder: str,
    profile: BookmarkProfile,
    similar_notes: list[SimilarNote],
    used_llm_classification: bool,
) -> str:
    """Resolve parent topic using LLM metadata first, then fallbacks."""
    default_parent_topic = (
        _folder_leaf_topic(folder)
        if used_llm_classification
        else derive_parent_topic(folder, profile, similar_notes)
    )
    return _normalize_text(
        metadata.get("parent_topic", default_parent_topic), default_parent_topic
    )


def normalize_metadata(
    metadata: BookmarkMetadata,
    page_data: PageData,
    folder: str,
    profile: BookmarkProfile,
    similar_notes: list[SimilarNote],
    used_llm_classification: bool,
    summary_override: str | None = None,
) -> NormalizedBookmarkMetadata:
    """Normalize and complete classifier metadata before rendering a note."""
    title = _normalize_text(
        metadata.get("title", page_data["title"]), page_data["title"]
    )
    tags = _resolve_tags(
        metadata,
        page_data,
        folder,
        similar_notes,
        used_llm_classification,
    )
    related = _resolve_related(metadata, folder, tags, used_llm_classification)
    parent_topic = _resolve_parent_topic(
        metadata,
        folder,
        profile,
        similar_notes,
        used_llm_classification,
    )
    summary_fallback = summary_override or infer_summary(
        page_data["description"], page_data["content"]
    )
    return {
        "folder": folder,
        "title": title,
        "type": _normalize_bookmark_type(metadata.get("type")),
        "tags": tags,
        "language": _normalize_text(
            metadata.get("language", page_data["language"]),
            DEFAULT_LANGUAGE,
        ),
        "related": related,
        "parent_topic": parent_topic,
        "description": _normalize_text(
            metadata.get("description", page_data["description"] or title),
            page_data["description"] or title,
        ),
        "summary": _normalize_text(summary_fallback, summary_fallback)
        if summary_override
        else _normalize_text(
            metadata.get("summary", summary_fallback), summary_fallback
        ),
        "visibility": _normalize_text(
            metadata.get("visibility", profile.default_visibility),
            profile.default_visibility,
        ),
    }


class BookmarkExistsError(Exception):
    """Raised when a bookmark for the given URL already exists."""


def build_note(url: str, allow_new_subfolder: bool) -> tuple[Path, str, str]:
    """Build the target note path, rendered note text, and folder decision message."""
    logger.info("Scanning vault for existing bookmarks…")
    profile = collect_existing_notes()
    existing = find_existing_url(url, profile)
    if existing:
        raise BookmarkExistsError(f"Bookmark already exists: {existing}")
    logger.info("Fetching page content from %s…", url)
    page_data = extract_page_data(url)
    logger.info("Page fetched: %s", page_data["title"])
    similar_notes = rank_similar_notes(page_data, profile)
    logger.info("Classifying bookmark with LLM…")
    llm_metadata = call_llm(page_data, profile, similar_notes, allow_new_subfolder)
    if llm_metadata:
        logger.info("LLM classification succeeded.")
    else:
        logger.info("LLM unavailable; using heuristic classification.")
    metadata = llm_metadata or heuristic_classification(
        page_data, profile, similar_notes
    )
    classification_summary = (
        str(llm_metadata.get("summary", "")).strip() if llm_metadata else ""
    )
    logger.info("Generating summary…")
    summary_override = generate_summary(
        page_data["url"],
        page_data,
        classification_summary=classification_summary,
    )
    folder, folder_message = validate_folder(
        str(metadata.get("folder", "Development")), allow_new_subfolder
    )
    logger.info("Assigned folder: %s", folder)
    metadata = normalize_metadata(
        metadata,
        page_data,
        folder,
        profile,
        similar_notes,
        used_llm_classification=llm_metadata is not None,
        summary_override=summary_override,
    )
    bookmarks_dir = get_bookmarks_dir()
    target_path = uniquify_path(
        (bookmarks_dir / folder) / slugify_filename(str(metadata["title"]))
    )
    return target_path, render_note(metadata, page_data["url"], profile), folder_message


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for bookmark creation."""
    parser = argparse.ArgumentParser(
        description="Add a bookmark note to the Obsidian vault."
    )
    parser.add_argument("url", nargs="?", help="URL to fetch and classify")
    parser.add_argument(
        "--file",
        "-f",
        type=str,
        default=None,
        help="Read URLs from a file (one per line); use - for stdin",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the proposed note instead of writing it",
    )
    parser.add_argument(
        "--disallow-new-subfolder",
        action="store_true",
        help="Force placement into existing folders only",
    )
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Review and confirm classification before writing",
    )
    parser.add_argument(
        "--archive",
        action="store_true",
        help="Save a cleaned copy of the page content alongside the bookmark note",
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
    return parser.parse_args()


def configure_logging(*, verbose: bool = False, quiet: bool = False) -> None:
    """Configure root logging based on CLI flags and LOG_LEVEL env var."""
    if verbose:
        level = logging.DEBUG
    elif quiet:
        level = logging.ERROR
    else:
        env_level = os.environ.get("LOG_LEVEL", "").upper()
        level = getattr(logging, env_level, logging.INFO)
    logging.basicConfig(
        format="%(levelname)s: %(message)s",
        level=level,
    )


def _read_urls_from_file(file_path: str) -> list[str]:
    """Read URLs from a file (one per line) or stdin when path is '-'."""
    import sys

    if file_path == "-":
        lines = sys.stdin.read().splitlines()
    else:
        lines = Path(file_path).read_text(encoding="utf-8").splitlines()
    return [
        line.strip()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]


def _prompt_interactive_review(
    target_path: Path, note_text: str, folder_message: str
) -> bool:
    """Show proposed classification and prompt for confirmation.

    Returns True if the user accepts, False otherwise.
    """
    print("─" * 60)
    print(f"Target: {target_path}")
    if folder_message:
        print(f"Folder decision: {folder_message}")
    print()
    print(note_text)
    print("─" * 60)
    try:
        answer = input("Accept this classification? [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in ("", "y", "yes")


def _save_archive(target_path: Path, content: str) -> Path:
    """Save cleaned page content alongside the bookmark note."""
    archive_path = target_path.with_suffix(".content.md")
    archive_path.write_text(content, encoding="utf-8")
    return archive_path


def _process_single_url(
    url: str,
    *,
    allow_new_subfolder: bool,
    dry_run: bool,
    interactive: bool = False,
    archive: bool = False,
) -> int:
    """Process one URL through the bookmark pipeline. Returns 0 on success, 1 on error."""
    try:
        target_path, note_text, folder_message = build_note(url, allow_new_subfolder)
    except BookmarkExistsError as exc:
        logger.warning("%s — skipping %s", exc, url)
        return 1
    except Exception as exc:
        logger.warning(
            "Failed to process %s (%s: %s)", url, exc.__class__.__name__, exc
        )
        return 1
    if dry_run:
        print(f"Target: {target_path}")
        if folder_message:
            print(f"Folder decision: {folder_message}")
        print()
        print(note_text)
        return 0
    if interactive:
        if not _prompt_interactive_review(target_path, note_text, folder_message):
            print("Skipped.")
            return 1
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(note_text, encoding="utf-8")
    print(f"Created {target_path}")
    if folder_message:
        print(folder_message)
    if archive:
        from .fetch import clean_html, fetch_text

        try:
            _, raw_html = fetch_text(url)
            cleaned = clean_html(raw_html)
            archive_path = _save_archive(target_path, cleaned)
            print(f"Archived {archive_path}")
        except Exception as exc:
            logger.warning("Failed to archive content for %s: %s", url, exc)
    return 0


def main() -> int:
    """Run the bookmark creation workflow and write output unless dry-run is set."""
    load_env()
    args = parse_args()
    configure_logging(verbose=args.verbose, quiet=args.quiet)

    if args.file:
        urls = _read_urls_from_file(args.file)
        if not urls:
            logger.error("No URLs found in %s", args.file)
            return 1
        allow_new = not args.disallow_new_subfolder
        failures = sum(
            _process_single_url(
                url,
                allow_new_subfolder=allow_new,
                dry_run=args.dry_run,
                interactive=args.interactive,
                archive=args.archive,
            )
            for url in urls
        )
        total = len(urls)
        print(f"\nProcessed {total - failures}/{total} URLs successfully.")
        return 1 if failures == total else 0

    if not args.url:
        logger.error("Either a URL argument or --file is required.")
        return 1

    return _process_single_url(
        args.url,
        allow_new_subfolder=not args.disallow_new_subfolder,
        dry_run=args.dry_run,
        interactive=args.interactive,
        archive=args.archive,
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.URLError as exc:
        raise SystemExit(f"Failed to fetch URL: {exc}") from exc
