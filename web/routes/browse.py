from __future__ import annotations

from pathlib import Path

from flask import Blueprint, abort, jsonify, render_template, request

from bookmark_tools.paths import get_bookmarks_dir
from bookmark_tools.vault_profile import collect_existing_notes, parse_frontmatter

browse_bp = Blueprint("browse", __name__)


def _safe_note_path(note_path_str: str) -> Path:
    """Resolve a note path and verify it is under the bookmarks directory."""
    bookmarks_dir = get_bookmarks_dir()
    resolved = (bookmarks_dir / note_path_str).resolve()
    if not resolved.is_relative_to(bookmarks_dir.resolve()):
        abort(403)
    if not resolved.exists():
        abort(404)
    return resolved


@browse_bp.route("/")
def index():
    return render_template("index.html")


@browse_bp.route("/api/folders")
def api_folders():
    profile = collect_existing_notes()
    return jsonify({"folders": profile.folders})


@browse_bp.route("/api/bookmarks")
def api_bookmarks():
    folder = request.args.get("folder", "")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    bookmarks_dir = get_bookmarks_dir()
    profile = collect_existing_notes()

    notes = [n for n in profile.notes if n.folder == folder]
    total = len(notes)
    start = (page - 1) * per_page
    page_notes = notes[start : start + per_page]

    return jsonify({
        "folder": folder,
        "page": page,
        "per_page": per_page,
        "total": total,
        "bookmarks": [
            {
                "title": n.title,
                "folder": n.folder,
                "tags": n.tags,
                "description": n.description,
                "path": str(
                    next(
                        (
                            p
                            for p in bookmarks_dir.rglob("*.md")
                            if p.parent == bookmarks_dir / n.folder
                            and p.stem == n.title
                        ),
                        "",
                    )
                ),
            }
            for n in page_notes
        ],
    })


@browse_bp.route("/api/bookmarks/<path:note_path>")
def api_bookmark_detail(note_path: str):
    resolved = _safe_note_path(note_path)
    metadata = parse_frontmatter(resolved)
    bookmarks_dir = get_bookmarks_dir()
    rel = resolved.relative_to(bookmarks_dir)
    return jsonify({
        "path": str(rel),
        "title": str(metadata.get("title", resolved.stem)),
        "url": str(metadata.get("url", "")),
        "folder": str(rel.parent) if str(rel.parent) != "." else "",
        "tags": metadata.get("tags", []),
        "description": str(metadata.get("description", "")),
        "type": str(metadata.get("type", "")),
        "created": str(metadata.get("created", "")),
        "related": metadata.get("related", []),
        "parent_topic": str(metadata.get("parent_topic", "")),
    })


@browse_bp.route("/partials/folders")
def partials_folders():
    profile = collect_existing_notes()
    active = request.args.get("active", "")
    return render_template(
        "partials/folder_tree.html", folders=profile.folders, active=active
    )


@browse_bp.route("/partials/bookmarks")
def partials_bookmarks():
    folder = request.args.get("folder", "")
    bookmarks_dir = get_bookmarks_dir()
    folder_dir = bookmarks_dir / folder if folder else bookmarks_dir

    notes = []
    for md in sorted(folder_dir.glob("*.md")):
        metadata = parse_frontmatter(md)
        rel = str(md.relative_to(bookmarks_dir))
        notes.append({
            "path": rel,
            "title": str(metadata.get("title", md.stem)),
            "folder": folder,
            "tags": metadata.get("tags", []) if isinstance(metadata.get("tags"), list) else [],
            "description": str(metadata.get("description", "")),
        })

    return render_template(
        "partials/bookmark_list.html",
        notes=notes,
        folder=folder,
    )



@browse_bp.route("/partials/bookmark-detail/<path:note_path>")
def partials_bookmark_detail(note_path: str):
    resolved = _safe_note_path(note_path)
    metadata = parse_frontmatter(resolved)
    bookmarks_dir = get_bookmarks_dir()
    rel = resolved.relative_to(bookmarks_dir)
    detail = {
        "path": str(rel),
        "title": str(metadata.get("title", resolved.stem)),
        "url": str(metadata.get("url", "")),
        "folder": str(rel.parent) if str(rel.parent) != "." else "",
        "tags": metadata.get("tags", []) if isinstance(metadata.get("tags"), list) else [],
        "description": str(metadata.get("description", "")),
        "type": str(metadata.get("type", "")),
        "created": str(metadata.get("created", "")),
        "related": metadata.get("related", []) if isinstance(metadata.get("related"), list) else [],
        "parent_topic": str(metadata.get("parent_topic", "")),
    }
    return render_template("partials/bookmark_detail.html", bookmark=detail)
