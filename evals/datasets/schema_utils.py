from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: Path) -> Any:
    """Load a YAML file using the project's safe parser."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def ensure_mapping(value: Any, *, context: str) -> dict[str, Any]:
    """Return a YAML mapping or raise a schema error."""
    if not isinstance(value, dict):
        raise ValueError(f"{context}: expected a mapping, got {type(value).__name__}")
    return value


def as_string_list(value: Any, *, context: str) -> tuple[str, ...]:
    """Return a non-empty-string tuple from a YAML list-like field."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{context}: expected a list, got {type(value).__name__}")
    items: list[str] = []
    for index, item in enumerate(value):
        text = str(item).strip()
        if not text:
            raise ValueError(f"{context}[{index}]: empty value")
        items.append(text)
    return tuple(items)


def optional_text(entry: dict[str, Any], key: str, default: str = "") -> str:
    """Return a trimmed optional text field."""
    value = entry.get(key, default)
    if value is None:
        return default
    return str(value).strip()


def required_text(entry: dict[str, Any], key: str, *, context: str) -> str:
    """Return a trimmed required text field or raise a schema error."""
    text = optional_text(entry, key)
    if not text:
        raise ValueError(f"{context}: missing required {key!r} field")
    return text


def top_level_cases(raw: Any, *, path: Path) -> list[Any]:
    """Return cases from either a top-level list or a mapping with `cases`."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        cases = raw.get("cases", [])
        if not isinstance(cases, list):
            raise ValueError(
                f"{path}: 'cases' must be a list, got {type(cases).__name__}"
            )
        return cases
    raise ValueError(
        f"{path}: expected a YAML list or mapping, got {type(raw).__name__}"
    )


def ensure_unique(values: list[str], *, context: str) -> None:
    """Raise when a list contains duplicate identifiers."""
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"{context}: duplicate id {value!r}")
        seen.add(value)
