from __future__ import annotations

from flask import Blueprint, jsonify, render_template

from bookmark_tools.stats import collect_stats

stats_bp = Blueprint("stats", __name__)


@stats_bp.route("/stats")
def stats_page():
    return render_template("stats.html")


@stats_bp.route("/api/stats")
def api_stats():
    stats = collect_stats()
    return jsonify(stats)


@stats_bp.route("/partials/stats")
def partials_stats():
    stats = collect_stats()
    return render_template("partials/stats_cards.html", stats=stats)
