from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from bookmark_tools.config import BookmarkConfigError, get_llm_config, load_config


class BookmarkConfigTest(unittest.TestCase):
    def test_load_config_reads_toml_provider_settings(self) -> None:
        """TOML config provides provider/model defaults."""
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "bookmark-tools.toml"
            config_path.write_text(
                "\n".join(
                    [
                        "[provider]",
                        'name = "openrouter"',
                        'base_url = "https://openrouter.example/api/v1"',
                        'api_key = "toml-token"',
                        "",
                        "[classification]",
                        'model = "openrouter/classifier"',
                        "",
                        "[summary]",
                        'model = "openrouter/summarizer"',
                        "",
                        "[embedding]",
                        'model = "embed-v2"',
                        "dimensions = 512",
                    ]
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                config = load_config(config_path=config_path)

        self.assertEqual(config.provider, "openrouter")
        self.assertEqual(config.api_key, "toml-token")
        self.assertEqual(config.base_url, "https://openrouter.example/api/v1")
        self.assertEqual(config.classification_model, "classifier")
        self.assertEqual(config.summary_model, "summarizer")
        self.assertEqual(config.embedding_model, "embed-v2")
        self.assertEqual(config.embedding_dimensions, 512)

    def test_env_overrides_toml(self) -> None:
        """Environment variables have higher precedence than TOML."""
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "bookmark-tools.toml"
            config_path.write_text(
                "\n".join(
                    [
                        "[provider]",
                        'api_key = "toml-token"',
                        'base_url = "https://toml.example/v1"',
                        "[classification]",
                        'model = "toml-model"',
                        "[embedding]",
                        'model = "toml-embed"',
                        "dimensions = 256",
                    ]
                ),
                encoding="utf-8",
            )
            env = {
                "OPENAI_API_KEY": "env-token",
                "OPENAI_BASE_URL": "https://env.example/v1",
                "BOOKMARK_CLASSIFICATION_MODEL": "env-model",
                "BOOKMARK_EMBEDDING_MODEL": "env-embed",
                "BOOKMARK_EMBEDDING_DIMENSIONS": "1024",
            }
            with patch.dict(os.environ, env, clear=True):
                config = load_config(config_path=config_path)

        self.assertEqual(config.api_key, "env-token")
        self.assertEqual(config.base_url, "https://env.example/v1")
        self.assertEqual(config.classification_model, "env-model")
        self.assertEqual(config.embedding_model, "env-embed")
        self.assertEqual(config.embedding_dimensions, 1024)

    def test_overrides_have_highest_precedence(self) -> None:
        """Explicit overrides support future CLI flags."""
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "bookmark-tools.toml"
            config_path.write_text(
                "[embedding]\ndimensions = 256\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"BOOKMARK_EMBEDDING_DIMENSIONS": "512"},
                clear=True,
            ):
                config = load_config(
                    config_path=config_path,
                    overrides={"embedding_dimensions": 768},
                )

        self.assertEqual(config.embedding_dimensions, 768)

    def test_get_llm_config_returns_none_without_api_key(self) -> None:
        """Provider config is optional; no API key means no LLM config."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("bookmark_tools.config.discover_config_paths", return_value=[]):
                self.assertIsNone(get_llm_config())

    def test_invalid_embedding_dimensions_raise_clear_error(self) -> None:
        """Embedding dimensions must be positive integers."""
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "bookmark-tools.toml"
            config_path.write_text(
                "[embedding]\ndimensions = 0\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(BookmarkConfigError, "positive"):
                    load_config(config_path=config_path)


if __name__ == "__main__":
    unittest.main()
