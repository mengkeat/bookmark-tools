from __future__ import annotations

import argparse
import http.client
import json
import logging
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Sequence

from .paths import get_bookmarks_dir, load_env
from .vault_profile import parse_frontmatter

logger = logging.getLogger(__name__)

DEFAULT_CHECK_TIMEOUT = 15


def check_url(url: str, *, timeout: int = DEFAULT_CHECK_TIMEOUT) -> tuple[int, str]:
    """Check a URL and return (status_code, reason).

    Tries HEAD first; falls back to a minimal GET when HEAD returns 405
    (Method Not Allowed) to avoid false broken-link reports.
    Returns (0, error_message) for connection failures.
    """
    for method in ("HEAD", "GET"):
        request = urllib.request.Request(
            url,
            method=method,
            headers={"User-Agent": "bookmark-check/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, "OK"
        except urllib.error.HTTPError as exc:
            if exc.code == 405 and method == "HEAD":
                continue
            return exc.code, exc.reason
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            http.client.InvalidURL,
        ) as exc:
            reason = str(getattr(exc, "reason", exc))
            return 0, reason
    # Should not be reached, but satisfy the type checker
    return 0, "Unknown error"


def check_bookmarks(
    *,
    bookmarks_dir: Path | None = None,
    timeout: int = DEFAULT_CHECK_TIMEOUT,
) -> list[dict[str, object]]:
    """Check all bookmarked URLs and return a list of problem entries."""
    if bookmarks_dir is None:
        bookmarks_dir = get_bookmarks_dir()

    problems: list[dict[str, object]] = []
    for note_path in sorted(bookmarks_dir.rglob("*.md")):
        metadata = parse_frontmatter(note_path)
        url = str(metadata.get("url", "")).strip()
        if not url or not (url.startswith("http://") or url.startswith("https://")):
            continue
        title = str(metadata.get("title", note_path.stem))
        status, reason = check_url(url, timeout=timeout)
        if status == 0 or status >= 400:
            problems.append(
                {
                    "path": note_path,
                    "url": url,
                    "title": title,
                    "status": status,
                    "reason": reason,
                }
            )
            logger.info("✗ %s → %s (%s)", title, status, reason)
        else:
            logger.debug("✓ %s → %s", title, status)

    return problems


def delete_broken(
    problems: list[dict[str, object]],
    *,
    dry_run: bool = False,
) -> tuple[int, list[dict[str, object]]]:
    """Delete the note files for broken bookmarks.

    Returns (deleted_count, errors).  In dry-run mode, no files are
    removed; the returned count reflects what *would* be deleted.
    """
    deleted = 0
    errors: list[dict[str, object]] = []
    for entry in problems:
        path = Path(str(entry["path"]))
        if dry_run:
            logger.info("[dry-run] would delete %s", path)
            deleted += 1
            continue
        try:
            path.unlink()
            logger.info("Deleted %s", path)
            deleted += 1
        except OSError as exc:
            errors.append({"path": str(path), "error": str(exc)})
            logger.error("Failed to delete %s: %s", path, exc)
    return deleted, errors


def tag_broken(
    problems: list[dict[str, object]],
    *,
    dry_run: bool = False,
) -> int:
    """Add a ``broken`` tag to the frontmatter of each broken bookmark note.

    Returns the number of files updated (or that would be updated in dry-run).
    """
    tagged = 0
    for entry in problems:
        path = Path(str(entry["path"]))
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue

        # Avoid double-tagging
        if "broken" in text[:text.find("---", 1)]:
            continue

        # Inject "broken" into an existing tags list, or add a tags line
        if re.search(r"^tags:", text, re.MULTILINE):
            updated = re.sub(
                r"^(tags:\s*\[)(.*?)(\])",
                lambda m: (
                    f"{m.group(1)}{m.group(2) + ', ' if m.group(2).strip() else ''}broken{m.group(3)}"
                ),
                text,
                count=1,
                flags=re.MULTILINE,
            )
        else:
            # Insert tags line after the opening ---
            updated = text.replace("---\n", "---\ntags: [broken]\n", 1)

        if dry_run:
            logger.info("[dry-run] would tag %s as broken", path)
            tagged += 1
            continue

        try:
            path.write_text(updated, encoding="utf-8")
            tagged += 1
        except OSError as exc:
            logger.error("Failed to tag %s: %s", path, exc)

    return tagged


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for bookmark health checking."""
    parser = argparse.ArgumentParser(
        description="Check bookmarked URLs for dead links."
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_CHECK_TIMEOUT,
        help=f"Timeout in seconds for each URL check (default: {DEFAULT_CHECK_TIMEOUT})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what actions would be taken without making any changes",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete broken bookmark files (use --dry-run to preview)",
    )
    parser.add_argument(
        "--tag-broken",
        action="store_true",
        help="Add a 'broken' tag to the frontmatter of broken bookmark files",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
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


def main(argv: Sequence[str] | None = None) -> int:
    """Run link health checks and report broken bookmarks."""
    load_env()
    args = parse_args(argv)
    from .cli import configure_logging

    configure_logging(verbose=args.verbose, quiet=args.quiet)

    problems = check_bookmarks(timeout=args.timeout)

    if args.format == "json":
        output = [
            {
                "path": str(entry["path"]),
                "url": entry["url"],
                "title": entry["title"],
                "status": entry["status"],
                "reason": entry["reason"],
            }
            for entry in problems
        ]
        print(json.dumps(output, indent=2))
        return 1 if problems else 0

    if not problems:
        print("All bookmark URLs are reachable.")
        return 0

    print(f"Found {len(problems)} broken bookmark(s):\n")
    for entry in problems:
        status = entry["status"]
        label = f"HTTP {status}" if status else "Connection error"
        print(f"  ✗ {entry['title']}")
        print(f"    URL: {entry['url']}")
        print(f"    Status: {label} — {entry['reason']}")
        print(f"    Path: {entry['path']}")
        print()

    if args.delete:
        deleted, errors = delete_broken(problems, dry_run=args.dry_run)
        verb = "Would delete" if args.dry_run else "Deleted"
        print(f"{verb} {deleted} bookmark file(s).")
        if errors:
            for err in errors:
                logger.error("Delete failed for %s: %s", err["path"], err["error"])

    if args.tag_broken:
        tagged = tag_broken(problems, dry_run=args.dry_run)
        verb = "Would tag" if args.dry_run else "Tagged"
        print(f"{verb} {tagged} bookmark(s) as broken.")

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
