from __future__ import annotations

import os
from pathlib import Path

DEFAULT_TIMEOUT = 20
MAX_FETCH_BYTES = 1_000_000


def _resolve_path(value: str | Path | None, fallback: Path) -> Path:
    """Resolve a user-supplied path or fall back to the default."""
    if value is not None:
        return Path(value).expanduser().resolve()
    return fallback


def _default_bookmarks_dir() -> Path:
    """Return the default Bookmarks directory from VAULT_PATH env var."""
    vault = Path(os.environ.get("VAULT_PATH", "")).expanduser().resolve()
    return vault / "Bookmarks" if vault.is_dir() else Path()


def _default_search_index_path() -> Path:
    """Return the default search index path from VAULT_PATH env var."""
    vault = Path(os.environ.get("VAULT_PATH", "")).expanduser().resolve()
    return vault / "Meta" / "bookmark-search.sqlite3" if vault.is_dir() else Path()


def _default_guide_path() -> Path:
    """Return the default classification guide path from VAULT_PATH env var."""
    vault = Path(os.environ.get("VAULT_PATH", "")).expanduser().resolve()
    return (
        vault / "Meta" / "Bookmark-Classification-Guide.md"
        if vault.is_dir()
        else Path()
    )


def _default_env_paths() -> list[Path]:
    """Return default .env search paths.

    Checks multiple candidate locations so that a single .env file works
    regardless of whether VAULT_PATH is already set. Order matters: the
    first file found wins for each key (setdefault semantics).
    """
    cwd = Path.cwd()
    vault = Path(os.environ.get("VAULT_PATH", "")).expanduser()
    candidates: list[Path] = []

    # If VAULT_PATH is already set, prioritise it
    if vault.is_dir():
        candidates.append(vault / ".env")
        candidates.append(vault.parent / ".env")

    # Common layouts when VAULT_PATH is not yet known
    candidates.append(cwd / ".env")
    candidates.append(cwd / "Vault" / ".env")

    # Deduplicate while preserving order
    seen: set[Path] = set()
    result: list[Path] = []
    for p in candidates:
        resolved = p.resolve()
        if resolved not in seen:
            seen.add(resolved)
            result.append(p)
    return result


def get_bookmarks_dir() -> Path:
    """Return the configured bookmarks directory."""
    return _resolve_path(os.environ.get("BOOKMARKS_DIR"), _default_bookmarks_dir())


def get_search_index_path() -> Path:
    """Return the configured search index database path."""
    return _resolve_path(
        os.environ.get("BOOKMARK_SEARCH_INDEX"), _default_search_index_path()
    )


def get_guide_path() -> Path:
    """Return the configured classification guide path."""
    return _resolve_path(
        os.environ.get("BOOKMARK_CLASSIFICATION_GUIDE"), _default_guide_path()
    )


def get_env_paths() -> list[Path]:
    """Return the list of .env file paths to search."""
    env_override = os.environ.get("BOOKMARK_ENV_FILE")
    if env_override:
        return [Path(env_override).expanduser().resolve()]
    return _default_env_paths()


def load_env() -> None:
    """Load environment variables from configured .env files if present."""
    for env_path in get_env_paths():
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))
