from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from bookmark_tools.paths import (
    BookmarkPathError,
    get_bookmarks_dir,
    require_bookmarks_dir,
)


class RequireBookmarksDirTest(unittest.TestCase):
    """Tests for fail-fast vault path validation."""

    def test_raises_when_no_env_set(self) -> None:
        """Without BOOKMARKS_DIR or VAULT_PATH, raises BookmarkPathError."""
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(BookmarkPathError) as ctx:
                require_bookmarks_dir()
        self.assertIn("not configured", str(ctx.exception))

    def test_raises_when_vault_path_is_not_a_directory(self) -> None:
        """VAULT_PATH pointing to a non-existent directory raises BookmarkPathError."""
        with TemporaryDirectory() as tmp:
            fake_vault = Path(tmp) / "nonexistent"
            with patch.dict(
                os.environ,
                {"VAULT_PATH": str(fake_vault)},
                clear=True,
            ):
                with self.assertRaises(BookmarkPathError) as ctx:
                    require_bookmarks_dir()
            self.assertIn("does not exist", str(ctx.exception))

    def test_raises_when_bookmarks_dir_is_a_file(self) -> None:
        """BOOKMARKS_DIR pointing to a file raises BookmarkPathError."""
        with TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "not_a_dir"
            file_path.write_text("I am a file", encoding="utf-8")
            with patch.dict(
                os.environ,
                {"BOOKMARKS_DIR": str(file_path)},
                clear=True,
            ):
                with self.assertRaises(BookmarkPathError) as ctx:
                    require_bookmarks_dir()
            self.assertIn("not a directory", str(ctx.exception))

    def test_succeeds_with_valid_vault_path(self) -> None:
        """A valid VAULT_PATH returns the expected Bookmarks directory."""
        with TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            with patch.dict(
                os.environ,
                {"VAULT_PATH": str(vault)},
                clear=True,
            ):
                result = require_bookmarks_dir()
        self.assertEqual(result, vault / "Bookmarks")

    def test_succeeds_with_explicit_bookmarks_dir(self) -> None:
        """An explicit BOOKMARKS_DIR override works without VAULT_PATH."""
        with TemporaryDirectory() as tmp:
            bm_dir = Path(tmp) / "MyBookmarks"
            with patch.dict(
                os.environ,
                {"BOOKMARKS_DIR": str(bm_dir)},
                clear=True,
            ):
                result = require_bookmarks_dir()
        self.assertEqual(result, bm_dir)

    def test_bookmarks_dir_overrides_vault_path(self) -> None:
        """BOOKMARKS_DIR takes precedence over VAULT_PATH."""
        with TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            override = Path(tmp) / "custom"
            with patch.dict(
                os.environ,
                {"VAULT_PATH": str(vault), "BOOKMARKS_DIR": str(override)},
                clear=True,
            ):
                result = require_bookmarks_dir()
        self.assertEqual(result, override)


class GetBookmarksDirTest(unittest.TestCase):
    """Tests for non-strict bookmarks directory resolution."""

    def test_returns_empty_path_when_no_env(self) -> None:
        """Without any configuration, returns an empty Path (not a valid dir)."""
        with patch.dict(os.environ, {}, clear=True):
            result = get_bookmarks_dir()
        self.assertEqual(result, Path())

    def test_returns_vault_bookmarks_when_vault_set(self) -> None:
        with TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            with patch.dict(
                os.environ,
                {"VAULT_PATH": str(vault)},
                clear=True,
            ):
                result = get_bookmarks_dir()
        self.assertEqual(result, vault / "Bookmarks")

    def test_returns_override_when_bookmarks_dir_set(self) -> None:
        with TemporaryDirectory() as tmp:
            custom = Path(tmp) / "custom-bm"
            with patch.dict(
                os.environ,
                {"BOOKMARKS_DIR": str(custom)},
                clear=True,
            ):
                result = get_bookmarks_dir()
        self.assertEqual(result, custom.resolve())


if __name__ == "__main__":
    unittest.main()
