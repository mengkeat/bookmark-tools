"""Tests for the web bookmarks routes (Phase 3)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from bookmark_tools.cli import BookmarkExistsError
from web.app import create_app


@pytest.fixture()
def client(tmp_path):
    env = {
        "BOOKMARKS_DIR": str(tmp_path / "Bookmarks"),
        "OBSIDIAN_VAULT": str(tmp_path),
    }
    with patch.dict("os.environ", env):
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


# ── /manage page ──────────────────────────────────────────────────────────────


def test_manage_page_returns_200(client):
    resp = client.get("/manage")
    assert resp.status_code == 200
    assert b"Manage" in resp.data


# ── POST /api/bookmarks ───────────────────────────────────────────────────────


def test_create_bookmark_missing_url(client):
    resp = client.post("/api/bookmarks", json={})
    assert resp.status_code == 400
    assert b"url is required" in resp.data


def test_create_bookmark_success(client, tmp_path):
    note_dir = tmp_path / "Bookmarks" / "Dev"
    note_dir.mkdir(parents=True)
    note_path = note_dir / "my-note.md"

    with (
        patch("web.routes.bookmarks.build_note") as mock_build,
        patch("web.routes.bookmarks.get_bookmarks_dir") as mock_dir,
    ):
        mock_dir.return_value = tmp_path / "Bookmarks"
        mock_build.return_value = (note_path, "# content", "placed in Dev")

        resp = client.post("/api/bookmarks", json={"url": "https://example.com"})

    assert resp.status_code == 201
    data = json.loads(resp.data)
    assert "Dev/my-note.md" in data["path"]
    assert data["folder_message"] == "placed in Dev"


def test_create_bookmark_duplicate(client):
    with patch("web.routes.bookmarks.build_note") as mock_build:
        mock_build.side_effect = BookmarkExistsError(
            "Bookmark already exists: Dev/note.md"
        )
        resp = client.post("/api/bookmarks", json={"url": "https://example.com"})

    assert resp.status_code == 409
    assert b"already exists" in resp.data


def test_create_bookmark_server_error(client):
    with patch("web.routes.bookmarks.build_note") as mock_build:
        mock_build.side_effect = RuntimeError("network failure")
        resp = client.post("/api/bookmarks", json={"url": "https://example.com"})

    assert resp.status_code == 500
    assert b"network failure" in resp.data


# ── PUT /api/bookmarks/update ─────────────────────────────────────────────────


def test_update_bookmark_missing_url(client):
    resp = client.put("/api/bookmarks/update", json={})
    assert resp.status_code == 400


def test_update_bookmark_not_found(client):
    with patch("web.routes.bookmarks.update_bookmark", return_value=None):
        resp = client.put("/api/bookmarks/update", json={"url": "https://example.com"})
    assert resp.status_code == 404
    assert b"No bookmark found" in resp.data


def test_update_bookmark_success(client, tmp_path):
    note_path = tmp_path / "Bookmarks" / "Dev" / "note.md"
    note_path.parent.mkdir(parents=True)
    note_path.write_text("# note", encoding="utf-8")

    with (
        patch("web.routes.bookmarks.update_bookmark") as mock_upd,
        patch("web.routes.bookmarks.get_bookmarks_dir") as mock_dir,
    ):
        mock_dir.return_value = tmp_path / "Bookmarks"
        mock_upd.return_value = (note_path, "# updated content")

        resp = client.put("/api/bookmarks/update", json={"url": "https://example.com"})

    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "Dev/note.md" in data["path"]


# ── POST /api/check (SSE) ─────────────────────────────────────────────────────


def _parse_sse(raw: bytes) -> list[dict]:
    events = []
    for chunk in raw.decode().split("\n\n"):
        chunk = chunk.strip()
        if chunk.startswith("data:"):
            events.append(json.loads(chunk[5:].strip()))
    return events


def test_check_empty_vault(client, tmp_path):
    bookmarks_dir = tmp_path / "Bookmarks"
    bookmarks_dir.mkdir(parents=True)

    with patch("web.routes.bookmarks.get_bookmarks_dir", return_value=bookmarks_dir):
        resp = client.post("/api/check", json={})

    assert resp.status_code == 200
    events = _parse_sse(resp.data)
    done = [e for e in events if e["type"] == "done"]
    assert len(done) == 1
    assert done[0]["checked"] == 0


def test_check_streams_broken_link(client, tmp_path):
    bookmarks_dir = tmp_path / "Bookmarks"
    bookmarks_dir.mkdir(parents=True)
    note = bookmarks_dir / "note.md"
    note.write_text(
        "---\nurl: https://broken.example.com\ntitle: Broken\n---\n",
        encoding="utf-8",
    )

    with (
        patch("web.routes.bookmarks.get_bookmarks_dir", return_value=bookmarks_dir),
        patch("web.routes.bookmarks.check_url", return_value=(0, "connection refused")),
    ):
        resp = client.post("/api/check", json={})

    events = _parse_sse(resp.data)
    results = [e for e in events if e["type"] == "result"]
    assert len(results) == 1
    assert results[0]["broken"] is True
    assert results[0]["status"] == 0


def test_check_streams_healthy_link(client, tmp_path):
    bookmarks_dir = tmp_path / "Bookmarks"
    bookmarks_dir.mkdir(parents=True)
    note = bookmarks_dir / "note.md"
    note.write_text(
        "---\nurl: https://ok.example.com\ntitle: OK\n---\n",
        encoding="utf-8",
    )

    with (
        patch("web.routes.bookmarks.get_bookmarks_dir", return_value=bookmarks_dir),
        patch("web.routes.bookmarks.check_url", return_value=(200, "OK")),
    ):
        resp = client.post("/api/check", json={})

    events = _parse_sse(resp.data)
    results = [e for e in events if e["type"] == "result"]
    assert results[0]["broken"] is False


def test_check_skips_notes_without_url(client, tmp_path):
    bookmarks_dir = tmp_path / "Bookmarks"
    bookmarks_dir.mkdir(parents=True)
    note = bookmarks_dir / "note.md"
    note.write_text("---\ntitle: No URL\n---\n", encoding="utf-8")

    with patch("web.routes.bookmarks.get_bookmarks_dir", return_value=bookmarks_dir):
        resp = client.post("/api/check", json={})

    events = _parse_sse(resp.data)
    skips = [e for e in events if e["type"] == "skip"]
    assert len(skips) == 1


# ── GET /api/reorg ────────────────────────────────────────────────────────────


def test_reorg_returns_proposals(client):
    proposals = [
        {
            "path": "/v/Dev/note.md",
            "title": "Note",
            "current_folder": "Dev",
            "proposed_folder": "ML",
        }
    ]
    with patch(
        "web.routes.bookmarks.propose_reclassifications", return_value=proposals
    ):
        resp = client.get("/api/reorg")

    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert len(data["proposals"]) == 1
    assert data["proposals"][0]["proposed_folder"] == "ML"


def test_reorg_empty(client):
    with patch("web.routes.bookmarks.propose_reclassifications", return_value=[]):
        resp = client.get("/api/reorg")

    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["proposals"] == []


def test_reorg_passes_llm_flag(client):
    with patch(
        "web.routes.bookmarks.propose_reclassifications", return_value=[]
    ) as mock_reorg:
        client.get("/api/reorg?llm=true")
    mock_reorg.assert_called_once_with(use_llm=True)
