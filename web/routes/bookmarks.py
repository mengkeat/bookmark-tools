from __future__ import annotations

import json
from pathlib import Path

from flask import Blueprint, Response, jsonify, render_template, request, stream_with_context

from bookmark_tools.check import check_url
from bookmark_tools.cli import BookmarkExistsError, build_note
from bookmark_tools.paths import get_bookmarks_dir
from bookmark_tools.reorg import propose_reclassifications
from bookmark_tools.update import update_bookmark
from bookmark_tools.vault_profile import parse_frontmatter

bookmarks_bp = Blueprint("bookmarks", __name__)


@bookmarks_bp.route("/manage")
def manage_page():
    return render_template("manage.html")


@bookmarks_bp.route("/api/bookmarks", methods=["POST"])
def api_create_bookmark():
    data = request.get_json(silent=True) or {}
    url = str(data.get("url", "")).strip()
    if not url:
        return jsonify({"error": "url is required"}), 400

    allow_new = bool(data.get("allow_new_subfolder", True))

    try:
        target_path, note_text, folder_message = build_note(url, allow_new)
        bookmarks_dir = get_bookmarks_dir()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(note_text, encoding="utf-8")
        return jsonify({
            "path": str(target_path.relative_to(bookmarks_dir)),
            "folder_message": folder_message,
        }), 201
    except BookmarkExistsError as exc:
        return jsonify({"error": str(exc)}), 409
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bookmarks_bp.route("/api/bookmarks/update", methods=["PUT"])
def api_update_bookmark():
    data = request.get_json(silent=True) or {}
    url = str(data.get("url", "")).strip()
    if not url:
        return jsonify({"error": "url is required"}), 400

    try:
        result = update_bookmark(url)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    if result is None:
        return jsonify({"error": f"No bookmark found for URL: {url}"}), 404

    note_path, _ = result
    bookmarks_dir = get_bookmarks_dir()
    return jsonify({"path": str(note_path.relative_to(bookmarks_dir))})


@bookmarks_bp.route("/api/check", methods=["POST"])
def api_check():
    """Stream link-check progress as Server-Sent Events."""
    bookmarks_dir = get_bookmarks_dir()
    timeout = int((request.get_json(silent=True) or {}).get("timeout", 15))

    def generate():
        note_paths = sorted(bookmarks_dir.rglob("*.md"))
        total = len(note_paths)
        checked = 0

        for note_path in note_paths:
            metadata = parse_frontmatter(note_path)
            url = str(metadata.get("url", "")).strip()
            title = str(metadata.get("title", note_path.stem))
            rel = str(note_path.relative_to(bookmarks_dir))
            checked += 1

            if not url or not (url.startswith("http://") or url.startswith("https://")):
                event = {"type": "skip", "path": rel, "title": title,
                         "checked": checked, "total": total}
            else:
                status, reason = check_url(url, timeout=timeout)
                broken = status == 0 or status >= 400
                event = {"type": "result", "path": rel, "title": title, "url": url,
                         "status": status, "reason": reason, "broken": broken,
                         "checked": checked, "total": total}

            yield f"data: {json.dumps(event)}\n\n"

        yield f"data: {json.dumps({'type': 'done', 'checked': checked, 'total': total})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@bookmarks_bp.route("/api/reorg")
def api_reorg():
    use_llm = request.args.get("llm", "false").lower() == "true"
    try:
        proposals = propose_reclassifications(use_llm=use_llm)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"proposals": proposals})
