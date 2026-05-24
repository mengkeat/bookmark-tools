from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .paths import DEFAULT_TIMEOUT

DEFAULT_CLASSIFICATION_MODEL = "gpt-4.1-mini"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_EMBEDDING_DIMENSIONS = 256
DEFAULT_SUMMARY_TIMEOUT_SECONDS = 180
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
CONFIG_FILE_NAME = "bookmark-tools.toml"


class BookmarkConfigError(RuntimeError):
    """Raised when bookmark-tools configuration is invalid."""


@dataclass(frozen=True)
class ProviderConfig:
    """Resolved provider/model configuration.

    Values are resolved with this precedence: explicit overrides, environment
    variables, ``bookmark-tools.toml``, then defaults.
    """

    provider: str
    api_key: str
    base_url: str
    classification_model: str
    summary_model: str
    embedding_model: str
    embedding_dimensions: int
    request_timeout: int
    summary_timeout: int
    config_path: Path | None = None

    @property
    def has_api_key(self) -> bool:
        """Return True when a provider API key is configured."""
        return bool(self.api_key)

    def as_llm_dict(self) -> dict[str, str] | None:
        """Return the legacy LLM config mapping used by API callers."""
        if not self.has_api_key:
            return None
        return {
            "api_key": self.api_key,
            "model": self.classification_model,
            "summary_model": self.summary_model,
            "embedding_model": self.embedding_model,
            "embedding_dimensions": str(self.embedding_dimensions),
            "base_url": self.base_url.rstrip("/"),
            "provider": self.provider,
            "request_timeout": str(self.request_timeout),
            "summary_timeout": str(self.summary_timeout),
        }


def discover_config_paths() -> list[Path]:
    """Return config file candidates in discovery order."""
    override = os.environ.get("BOOKMARK_CONFIG_FILE", "").strip()
    if override:
        return [Path(override).expanduser().resolve()]

    candidates: list[Path] = []
    vault = os.environ.get("VAULT_PATH", "").strip()
    if vault:
        vault_path = Path(vault).expanduser().resolve()
        candidates.append(vault_path / "Meta" / CONFIG_FILE_NAME)
        candidates.append(vault_path / CONFIG_FILE_NAME)
    candidates.append(Path.cwd() / CONFIG_FILE_NAME)

    seen: set[Path] = set()
    result: list[Path] = []
    for path in candidates:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            result.append(path)
    return result


def read_config_file(path: Path | None = None) -> tuple[dict[str, Any], Path | None]:
    """Read the first available TOML config file.

    Returns ``({}, None)`` when no config file exists.
    """
    candidates = [path.expanduser().resolve()] if path else discover_config_paths()
    explicit = path is not None or bool(
        os.environ.get("BOOKMARK_CONFIG_FILE", "").strip()
    )
    for candidate in candidates:
        if not candidate.exists():
            if explicit:
                raise BookmarkConfigError(f"Config file does not exist: {candidate}")
            continue
        try:
            with candidate.open("rb") as handle:
                payload = tomllib.load(handle)
        except tomllib.TOMLDecodeError as exc:
            raise BookmarkConfigError(
                f"Invalid TOML config {candidate}: {exc}"
            ) from exc
        except OSError as exc:
            raise BookmarkConfigError(
                f"Could not read config {candidate}: {exc}"
            ) from exc
        return payload, candidate
    return {}, None


def _nested_value(data: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    """Return a nested TOML value or None when absent."""
    current: Any = data
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current


def _as_string(value: Any) -> str:
    """Normalize a config value to stripped text."""
    if value is None:
        return ""
    return str(value).strip()


def _resolve_text(
    *,
    name: str,
    data: Mapping[str, Any],
    env_names: tuple[str, ...] = (),
    toml_paths: tuple[tuple[str, ...], ...] = (),
    default: str = "",
    overrides: Mapping[str, Any] | None = None,
) -> str:
    """Resolve a text config value by precedence."""
    if overrides and _as_string(overrides.get(name)):
        return _as_string(overrides[name])
    for env_name in env_names:
        value = os.environ.get(env_name)
        if _as_string(value):
            return _as_string(value)
    for toml_path in toml_paths:
        value = _nested_value(data, toml_path)
        if _as_string(value):
            return _as_string(value)
    return default


def _resolve_int(
    *,
    name: str,
    data: Mapping[str, Any],
    env_names: tuple[str, ...] = (),
    toml_paths: tuple[tuple[str, ...], ...] = (),
    default: int,
    overrides: Mapping[str, Any] | None = None,
) -> int:
    """Resolve a positive integer config value by precedence."""
    text = _resolve_text(
        name=name,
        data=data,
        env_names=env_names,
        toml_paths=toml_paths,
        default=str(default),
        overrides=overrides,
    )
    try:
        value = int(text)
    except ValueError as exc:
        raise BookmarkConfigError(f"{name} must be an integer, got {text!r}") from exc
    if value <= 0:
        raise BookmarkConfigError(f"{name} must be positive, got {value}")
    return value


def _infer_provider(provider: str, api_key: str, data: Mapping[str, Any]) -> str:
    """Infer provider when only legacy API-key env vars are set."""
    if provider:
        return provider.lower()
    if os.environ.get("OPENROUTER_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        return "openrouter"
    toml_provider = _as_string(_nested_value(data, ("provider", "name")))
    return toml_provider.lower() if toml_provider else ("openai" if api_key else "")


def _default_base_url(provider: str) -> str:
    """Return the default OpenAI-compatible base URL for a provider."""
    return (
        DEFAULT_OPENROUTER_BASE_URL
        if provider == "openrouter"
        else DEFAULT_OPENAI_BASE_URL
    )


def _normalize_chat_model(model: str) -> str:
    """Normalize legacy OpenRouter model IDs used by this project."""
    if model.startswith("openrouter/"):
        return model[len("openrouter/") :]
    return model


def load_config(
    *,
    overrides: Mapping[str, Any] | None = None,
    config_path: Path | None = None,
) -> ProviderConfig:
    """Resolve bookmark-tools provider configuration.

    Precedence is explicit ``overrides`` (intended for CLI flags), then
    environment variables, then ``bookmark-tools.toml``, then defaults.
    """
    data, resolved_path = read_config_file(config_path)

    api_key = _resolve_text(
        name="api_key",
        data=data,
        env_names=(
            "BOOKMARK_LLM_API_KEY",
            "OPENAI_API_KEY",
            "OPENROUTER_API_KEY",
        ),
        toml_paths=(("provider", "api_key"), ("llm", "api_key")),
        overrides=overrides,
    )
    provider = _resolve_text(
        name="provider",
        data=data,
        env_names=("LLM_PROVIDER", "BOOKMARK_LLM_PROVIDER"),
        toml_paths=(("provider", "name"), ("llm", "provider")),
        overrides=overrides,
    )
    provider = _infer_provider(provider, api_key, data)

    base_url = _resolve_text(
        name="base_url",
        data=data,
        env_names=("BOOKMARK_LLM_BASE_URL", "OPENAI_BASE_URL"),
        toml_paths=(("provider", "base_url"), ("llm", "base_url")),
        default=_default_base_url(provider),
        overrides=overrides,
    ).rstrip("/")

    classification_model = _normalize_chat_model(
        _resolve_text(
            name="classification_model",
            data=data,
            env_names=(
                "BOOKMARK_CLASSIFICATION_MODEL",
                "BOOKMARK_LLM_MODEL",
                "OPENAI_MODEL",
                "MODEL_ID",
            ),
            toml_paths=(
                ("classification", "model"),
                ("llm", "classification_model"),
                ("llm", "model"),
            ),
            default=DEFAULT_CLASSIFICATION_MODEL,
            overrides=overrides,
        )
    )
    summary_model = _normalize_chat_model(
        _resolve_text(
            name="summary_model",
            data=data,
            env_names=("BOOKMARK_SUMMARY_MODEL",),
            toml_paths=(("summary", "model"), ("llm", "summary_model")),
            default=classification_model,
            overrides=overrides,
        )
    )
    embedding_model = _resolve_text(
        name="embedding_model",
        data=data,
        env_names=("BOOKMARK_EMBEDDING_MODEL",),
        toml_paths=(("embedding", "model"), ("llm", "embedding_model")),
        default=DEFAULT_EMBEDDING_MODEL,
        overrides=overrides,
    )
    embedding_dimensions = _resolve_int(
        name="embedding_dimensions",
        data=data,
        env_names=("BOOKMARK_EMBEDDING_DIMENSIONS",),
        toml_paths=(("embedding", "dimensions"), ("llm", "embedding_dimensions")),
        default=DEFAULT_EMBEDDING_DIMENSIONS,
        overrides=overrides,
    )
    request_timeout = _resolve_int(
        name="request_timeout",
        data=data,
        env_names=("BOOKMARK_REQUEST_TIMEOUT",),
        toml_paths=(("timeouts", "request_seconds"),),
        default=DEFAULT_TIMEOUT,
        overrides=overrides,
    )
    summary_timeout = _resolve_int(
        name="summary_timeout",
        data=data,
        env_names=("BOOKMARK_SUMMARY_TIMEOUT",),
        toml_paths=(("timeouts", "summary_seconds"),),
        default=DEFAULT_SUMMARY_TIMEOUT_SECONDS,
        overrides=overrides,
    )

    return ProviderConfig(
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        classification_model=classification_model,
        summary_model=summary_model,
        embedding_model=embedding_model,
        embedding_dimensions=embedding_dimensions,
        request_timeout=request_timeout,
        summary_timeout=summary_timeout,
        config_path=resolved_path,
    )


def get_llm_config(overrides: Mapping[str, Any] | None = None) -> dict[str, str] | None:
    """Return legacy API config mapping, or None when no API key is configured."""
    return load_config(overrides=overrides).as_llm_dict()
