"""Tests for the web stats routes (Phase 2)."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from web.app import create_app


SAMPLE_STATS = {
    "total_bookmarks": 5,
    "total_folders": 2,
    "bookmarks_per_folder": {"Dev": 3, "Science": 2},
    "top_tags": {"python": 3, "ai": 2},
    "top_parent_topics": {"Dev": 3},
    "type_distribution": {"article": 4, "video": 1},
}


@pytest.fixture()
def client(tmp_path):
    """Flask test client with a temporary bookmark vault."""
    env = {
        "BOOKMARKS_DIR": str(tmp_path / "Bookmarks"),
        "OBSIDIAN_VAULT": str(tmp_path),
    }
    with patch.dict("os.environ", env):
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


def test_stats_page_returns_200(client):
    resp = client.get("/stats")
    assert resp.status_code == 200
    assert b"Stats" in resp.data


def test_api_stats_returns_json(client):
    with patch("web.routes.stats.collect_stats", return_value=SAMPLE_STATS):
        resp = client.get("/api/stats")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["total_bookmarks"] == 5
    assert data["total_folders"] == 2
    assert data["bookmarks_per_folder"]["Dev"] == 3
    assert data["type_distribution"]["article"] == 4
    assert data["top_tags"]["python"] == 3


def test_api_stats_keys_present(client):
    with patch("web.routes.stats.collect_stats", return_value=SAMPLE_STATS):
        resp = client.get("/api/stats")
    data = json.loads(resp.data)
    for key in ("total_bookmarks", "total_folders", "bookmarks_per_folder",
                "top_tags", "type_distribution"):
        assert key in data, f"Missing key: {key}"


def test_partials_stats_returns_html(client):
    with patch("web.routes.stats.collect_stats", return_value=SAMPLE_STATS):
        resp = client.get("/partials/stats")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "5" in html   # total_bookmarks
    assert "2" in html   # total_folders


def test_partials_stats_shows_top_type(client):
    with patch("web.routes.stats.collect_stats", return_value=SAMPLE_STATS):
        resp = client.get("/partials/stats")
    html = resp.data.decode()
    # First key in type_distribution is the top type
    assert "article" in html


def test_api_stats_empty_vault(client):
    empty_stats = {
        "total_bookmarks": 0,
        "total_folders": 0,
        "bookmarks_per_folder": {},
        "top_tags": {},
        "top_parent_topics": {},
        "type_distribution": {},
    }
    with patch("web.routes.stats.collect_stats", return_value=empty_stats):
        resp = client.get("/api/stats")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["total_bookmarks"] == 0
