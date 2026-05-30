"""Generate topic/domain/tag hub pages from canonical bookmark notes.

Hub pages are derived Markdown indexes that group bookmarks by their
parent topic, domain, or tag.  Each page keeps its bookmark list inside a
protected ``bookmark-tools:hub`` generated block, so any human-authored
content outside the block is preserved across rebuilds.

Hubs live outside ``Bookmarks/`` (under ``Meta/bookmark-hubs`` by default)
so they are never scanned, profiled, or searched as bookmarks.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .note_schema import (
    domain_from_url,
    generated_block,
    parse_note_text,
    update_generated_block,
)
from .paths import BookmarkPathError, get_hubs_dir, load_env, require_bookmarks_dir
from .vault_profile import NoteProfile, collect_existing_notes

logger = logging.getLogger(__name__)

HUB_BLOCK_NAME = "hub"
HUB_KINDS = ("topic", "domain", "tag")

_KIND_HEADING = {"topic": "Topic", "domain": "Domain", "tag": "Tag"}
_KIND_SUBDIR = {"topic": "Topics", "domain": "Domains", "tag": "Tags"}


@dataclass(frozen=True)
class HubResult:
    """Summary of a hub generation run."""

    hubs_dir: Path
    written: list[Path]
    removed: list[Path]

    def to_dict(self) -> dict[str, object]:
        """Return a stable JSON-serializable representation."""
        return {
            "hubs_dir": str(self.hubs_dir),
            "written": [str(p) for p in self.written],
            "removed": [str(p) for p in self.removed],
        }


def _hub_filename(key: str) -> str:
    """Convert a hub key (tag/domain/topic) into a safe Markdown filename."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", key.strip()).strip("-.")
    return f"{safe or 'untitled'}.md"


def _note_link(note: NoteProfile) -> str:
    """Return an Obsidian wikilink list item for a note."""
    stem = note.path.stem
    title = note.title or stem
    if title == stem:
        return f"- [[{stem}]]"
    return f"- [[{stem}|{title}]]"


def _group_notes(
    notes: list[NoteProfile], kind: str
) -> dict[str, list[NoteProfile]]:
    """Group notes by the given hub kind, returning {key: [notes]}."""
    groups: dict[str, list[NoteProfile]] = defaultdict(list)
    for note in notes:
        if kind == "topic":
            if note.parent_topic:
                groups[note.parent_topic].append(note)
        elif kind == "domain":
            domain = domain_from_url(note.url)
            if domain:
                groups[domain].append(note)
        elif kind == "tag":
            for tag in note.tags:
                tag_key = tag.strip()
                if tag_key:
                    groups[tag_key].append(note)
    return groups


def _render_hub_body(notes: list[NoteProfile]) -> str:
    """Render the bookmark list block content for a hub page."""
    ordered = sorted(notes, key=lambda n: (n.title or n.path.stem).lower())
    lines = [_note_link(note) for note in ordered]
    return "\n".join(lines) or "- (none)"


def _hub_page_text(
    kind: str, key: str, notes: list[NoteProfile], existing_text: str | None
) -> str:
    """Build the full hub page text, preserving human content if present."""
    block_content = _render_hub_body(notes)
    if existing_text:
        note = parse_note_text(existing_text)
        new_body = update_generated_block(note.body, HUB_BLOCK_NAME, block_content)
        frontmatter, _ = _split(existing_text)
        if frontmatter:
            return f"{frontmatter}\n\n{new_body.strip()}\n"
        return f"{new_body.strip()}\n"

    heading = f"# {_KIND_HEADING[kind]}: {key}"
    frontmatter = "\n".join(
        [
            "---",
            "type: hub",
            f"hub_kind: {kind}",
            f"hub_key: {key}",
            "---",
        ]
    )
    block = generated_block(HUB_BLOCK_NAME, block_content)
    return f"{frontmatter}\n\n{heading}\n\n{block}\n"


def _split(text: str) -> tuple[str, str]:
    """Return (frontmatter-with-fences, body) for a note, fences included."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return "", text
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            frontmatter = "\n".join(lines[: index + 1])
            body = "\n".join(lines[index + 1 :]).lstrip("\n")
            return frontmatter, body
    return "", text


def build_hub_pages(
    *,
    bookmarks_dir: Path | None = None,
    hubs_dir: Path | None = None,
    kinds: tuple[str, ...] = HUB_KINDS,
    prune: bool = True,
) -> HubResult:
    """Generate (and optionally prune) topic/domain/tag hub pages.

    Returns the set of pages written and removed.  Pages are rebuildable:
    deleting them and re-running recreates them from canonical notes.
    """
    if bookmarks_dir is None:
        bookmarks_dir = require_bookmarks_dir()
    if hubs_dir is None:
        hubs_dir = get_hubs_dir()

    profile = collect_existing_notes(bookmarks_dir=bookmarks_dir)

    written: list[Path] = []
    expected_by_kind: dict[str, set[Path]] = {}
    for kind in kinds:
        groups = _group_notes(profile.notes, kind)
        kind_dir = hubs_dir / _KIND_SUBDIR[kind]
        expected: set[Path] = set()
        for key, notes in sorted(groups.items()):
            page_path = kind_dir / _hub_filename(key)
            expected.add(page_path)
            existing_text = (
                page_path.read_text(encoding="utf-8") if page_path.exists() else None
            )
            new_text = _hub_page_text(kind, key, notes, existing_text)
            if existing_text != new_text:
                page_path.parent.mkdir(parents=True, exist_ok=True)
                page_path.write_text(new_text, encoding="utf-8")
                written.append(page_path)
        expected_by_kind[kind] = expected

    removed: list[Path] = []
    if prune:
        for kind in kinds:
            kind_dir = hubs_dir / _KIND_SUBDIR[kind]
            if not kind_dir.is_dir():
                continue
            for page in kind_dir.glob("*.md"):
                if page not in expected_by_kind[kind]:
                    page.unlink()
                    removed.append(page)

    return HubResult(hubs_dir=hubs_dir, written=written, removed=removed)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for bookmark-topics."""
    parser = argparse.ArgumentParser(
        description="Generate topic/domain/tag hub pages from bookmark notes."
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="rebuild",
        choices=["rebuild"],
        help="Action to perform (default: rebuild)",
    )
    parser.add_argument(
        "--kind",
        default=",".join(HUB_KINDS),
        help=f"Comma-separated hub kinds to build (default: {','.join(HUB_KINDS)})",
    )
    parser.add_argument(
        "--no-prune",
        action="store_true",
        help="Do not remove hub pages with no matching bookmarks",
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_output", help="Emit JSON output"
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--quiet", "-q", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the bookmark-topics command."""
    load_env()
    args = parse_args(argv)
    from .logging_config import configure_logging

    configure_logging(verbose=args.verbose, quiet=args.quiet)

    kinds = tuple(k.strip() for k in args.kind.split(",") if k.strip())
    invalid = [k for k in kinds if k not in HUB_KINDS]
    if invalid:
        logger.error("Unknown hub kind(s): %s", ", ".join(invalid))
        return 1

    try:
        result = build_hub_pages(kinds=kinds, prune=not args.no_prune)
    except BookmarkPathError as exc:
        logger.error("%s", exc)
        return 1

    if args.json_output:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"Hubs directory: {result.hubs_dir}")
        print(f"Pages written: {len(result.written)}")
        print(f"Pages removed: {len(result.removed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
