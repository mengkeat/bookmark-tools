from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class LLMConfig:
    api_key: str = ""
    model: str = "gpt-4.1-mini"
    base_url: str = "https://api.openai.com/v1"
    provider: str = ""


@dataclass(frozen=True)
class TimeoutConfig:
    fetch: int = 20
    llm_classify: int = 20
    llm_summarize: int = 180
    link_check: int = 15


@dataclass(frozen=True)
class SearchConfig:
    bm25_weights: tuple[float, ...] = (0.0, 0.0, 8.0, 3.0, 4.0, 4.0, 3.0, 2.0, 1.0)
    similarity_threshold: float = 0.40
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 256
    default_limit: int = 10


@dataclass(frozen=True)
class AppConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    timeouts: TimeoutConfig = field(default_factory=TimeoutConfig)
    search: SearchConfig = field(default_factory=SearchConfig)


_CONFIG_FILE_NAMES = ("bookmark-tools.toml", ".bookmark-tools.toml")


def _find_config_file() -> Path | None:
    """Locate a config file in standard locations."""
    explicit = os.environ.get("BOOKMARK_CONFIG")
    if explicit:
        path = Path(explicit).expanduser()
        return path if path.is_file() else None

    vault_path = os.environ.get("VAULT_PATH", "")
    search_dirs: list[Path] = []
    if vault_path:
        search_dirs.append(Path(vault_path).expanduser())
    search_dirs.append(Path.cwd())

    for directory in search_dirs:
        for name in _CONFIG_FILE_NAMES:
            candidate = directory / name
            if candidate.is_file():
                return candidate
    return None


def _parse_llm_section(data: dict[str, object]) -> LLMConfig:
    """Parse the [llm] section from config data."""
    section = data.get("llm", {})
    if not isinstance(section, dict):
        return LLMConfig()
    return LLMConfig(
        api_key=str(section.get("api_key", "")),
        model=str(section.get("model", "gpt-4.1-mini")),
        base_url=str(section.get("base_url", "https://api.openai.com/v1")),
        provider=str(section.get("provider", "")),
    )


def _parse_timeouts_section(data: dict[str, object]) -> TimeoutConfig:
    """Parse the [timeouts] section from config data."""
    section = data.get("timeouts", {})
    if not isinstance(section, dict):
        return TimeoutConfig()
    return TimeoutConfig(
        fetch=int(section.get("fetch", 20)),
        llm_classify=int(section.get("llm_classify", 20)),
        llm_summarize=int(section.get("llm_summarize", 180)),
        link_check=int(section.get("link_check", 15)),
    )


def _parse_search_section(data: dict[str, object]) -> SearchConfig:
    """Parse the [search] section from config data."""
    section = data.get("search", {})
    if not isinstance(section, dict):
        return SearchConfig()
    weights = section.get("bm25_weights")
    bm25 = (
        tuple(float(w) for w in weights)
        if isinstance(weights, list)
        else SearchConfig.bm25_weights
    )
    return SearchConfig(
        bm25_weights=bm25,
        similarity_threshold=float(section.get("similarity_threshold", 0.40)),
        embedding_model=str(section.get("embedding_model", "text-embedding-3-small")),
        embedding_dimensions=int(section.get("embedding_dimensions", 256)),
        default_limit=int(section.get("default_limit", 10)),
    )


def load_config() -> AppConfig:
    """Load configuration from a TOML file, falling back to defaults.

    Environment variables still take precedence over the config file
    for backward compatibility.
    """
    config_path = _find_config_file()
    if config_path is None:
        return AppConfig()

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    return AppConfig(
        llm=_parse_llm_section(data),
        timeouts=_parse_timeouts_section(data),
        search=_parse_search_section(data),
    )
