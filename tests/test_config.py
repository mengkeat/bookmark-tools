from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from bookmark_tools.config import load_config, _find_config_file


SAMPLE_CONFIG = """\
[llm]
api_key = "test-key"
model = "gpt-4o"
base_url = "https://custom.api/v1"
provider = "openai"

[timeouts]
fetch = 30
llm_classify = 25
llm_summarize = 200
link_check = 10

[search]
bm25_weights = [0.0, 0.0, 10.0, 5.0, 4.0, 4.0, 3.0, 2.0, 1.0]
similarity_threshold = 0.50
embedding_model = "text-embedding-3-large"
embedding_dimensions = 512
default_limit = 20
"""


class FindConfigFileTest(unittest.TestCase):
    def test_finds_config_in_vault_path(self) -> None:
        """It finds bookmark-tools.toml in VAULT_PATH."""
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "bookmark-tools.toml"
            config_path.write_text("[llm]\n", encoding="utf-8")
            with patch.dict(os.environ, {"VAULT_PATH": tmp}, clear=True):
                result = _find_config_file()
        self.assertEqual(result, config_path)

    def test_finds_dotfile_config(self) -> None:
        """It finds .bookmark-tools.toml in cwd."""
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / ".bookmark-tools.toml"
            config_path.write_text("[llm]\n", encoding="utf-8")
            with (
                patch.dict(os.environ, {}, clear=True),
                patch("bookmark_tools.config.Path.cwd", return_value=Path(tmp)),
            ):
                result = _find_config_file()
        self.assertEqual(result, config_path)

    def test_returns_none_when_no_config(self) -> None:
        """It returns None when no config file exists."""
        with TemporaryDirectory() as tmp:
            with (
                patch.dict(os.environ, {}, clear=True),
                patch("bookmark_tools.config.Path.cwd", return_value=Path(tmp)),
            ):
                result = _find_config_file()
        self.assertIsNone(result)

    def test_explicit_env_var_path(self) -> None:
        """It uses BOOKMARK_CONFIG env var when set."""
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "custom.toml"
            config_path.write_text("[llm]\n", encoding="utf-8")
            with patch.dict(
                os.environ, {"BOOKMARK_CONFIG": str(config_path)}, clear=True
            ):
                result = _find_config_file()
        self.assertEqual(result, config_path)


class LoadConfigTest(unittest.TestCase):
    def test_loads_defaults_without_config_file(self) -> None:
        """It returns default config when no config file is found."""
        with TemporaryDirectory() as tmp:
            with (
                patch.dict(os.environ, {}, clear=True),
                patch("bookmark_tools.config.Path.cwd", return_value=Path(tmp)),
            ):
                config = load_config()
        self.assertEqual(config.llm.model, "gpt-4.1-mini")
        self.assertEqual(config.timeouts.fetch, 20)
        self.assertEqual(config.search.default_limit, 10)

    def test_loads_full_config_from_toml(self) -> None:
        """It parses all sections from a TOML config file."""
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "bookmark-tools.toml"
            config_path.write_text(SAMPLE_CONFIG, encoding="utf-8")
            with patch.dict(
                os.environ, {"BOOKMARK_CONFIG": str(config_path)}, clear=True
            ):
                config = load_config()

        self.assertEqual(config.llm.api_key, "test-key")
        self.assertEqual(config.llm.model, "gpt-4o")
        self.assertEqual(config.llm.base_url, "https://custom.api/v1")
        self.assertEqual(config.timeouts.fetch, 30)
        self.assertEqual(config.timeouts.llm_classify, 25)
        self.assertEqual(config.timeouts.llm_summarize, 200)
        self.assertEqual(config.timeouts.link_check, 10)
        self.assertAlmostEqual(config.search.similarity_threshold, 0.50)
        self.assertEqual(config.search.embedding_model, "text-embedding-3-large")
        self.assertEqual(config.search.embedding_dimensions, 512)
        self.assertEqual(config.search.default_limit, 20)
        self.assertEqual(config.search.bm25_weights[2], 10.0)

    def test_partial_config_uses_defaults_for_missing(self) -> None:
        """It fills missing sections/keys with defaults."""
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "bookmark-tools.toml"
            config_path.write_text('[llm]\nmodel = "custom-model"\n', encoding="utf-8")
            with patch.dict(
                os.environ, {"BOOKMARK_CONFIG": str(config_path)}, clear=True
            ):
                config = load_config()

        self.assertEqual(config.llm.model, "custom-model")
        self.assertEqual(config.llm.base_url, "https://api.openai.com/v1")
        # Timeouts and search should be defaults
        self.assertEqual(config.timeouts.fetch, 20)
        self.assertEqual(config.search.default_limit, 10)


if __name__ == "__main__":
    unittest.main()
