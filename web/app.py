from __future__ import annotations

from flask import Flask

from bookmark_tools.paths import load_env


def serialize_search_result(r) -> dict:
    return {
        "path": str(r.path),
        "url": r.url,
        "title": r.title,
        "folder": r.folder,
        "description": r.description,
        "score": r.score,
        "snippet": r.snippet,
    }


def create_app() -> Flask:
    load_env()
    app = Flask(__name__, template_folder="templates", static_folder="static")

    from web.routes.browse import browse_bp
    from web.routes.search import search_bp
    from web.routes.stats import stats_bp

    app.register_blueprint(browse_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(stats_bp)

    return app
