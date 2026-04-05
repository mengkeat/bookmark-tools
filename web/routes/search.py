from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from bookmark_tools.search import (
    refresh_search_index,
    search_bookmarks,
    search_bookmarks_hybrid,
    search_bookmarks_semantic,
)
from web.app import serialize_search_result

search_bp = Blueprint("search", __name__)


@search_bp.route("/search")
def search_page():
    return render_template("search.html")


@search_bp.route("/api/search")
def api_search():
    query = request.args.get("q", "").strip()
    mode = request.args.get("mode", "keyword")
    folder = request.args.get("folder") or None
    limit = int(request.args.get("limit", 10))

    if not query:
        return jsonify({"results": []})

    if mode == "semantic":
        results = search_bookmarks_semantic(query, folder=folder, limit=limit)
    elif mode == "hybrid":
        results = search_bookmarks_hybrid(query, folder=folder, limit=limit)
    else:
        results = search_bookmarks(query, folder=folder, limit=limit)

    return jsonify({"results": [serialize_search_result(r) for r in results]})


@search_bp.route("/partials/search")
def partials_search():
    query = request.args.get("q", "").strip()
    mode = request.args.get("mode", "keyword")
    folder = request.args.get("folder") or None
    limit = int(request.args.get("limit", 10))

    results = []
    error = None
    if query:
        try:
            if mode == "semantic":
                results = search_bookmarks_semantic(query, folder=folder, limit=limit)
            elif mode == "hybrid":
                results = search_bookmarks_hybrid(query, folder=folder, limit=limit)
            else:
                results = search_bookmarks(query, folder=folder, limit=limit)
        except Exception as exc:
            error = str(exc)

    return render_template(
        "partials/search_results.html",
        results=results,
        query=query,
        error=error,
    )


@search_bp.route("/api/search/reindex", methods=["POST"])
def api_reindex():
    try:
        refresh_search_index()
        return jsonify({"status": "ok"})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500
