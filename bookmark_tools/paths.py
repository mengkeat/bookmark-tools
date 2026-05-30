from __future__ import annotations

import os
from pathlib import Path

DEFAULT_TIMEOUT = 20
MAX_FETCH_BYTES = 1_000_000


class BookmarkPathError(RuntimeError):
    """Raised when bookmark vault paths are missing or invalid."""


def _resolve_path(value: str | Path | None, fallback: Path) -> Path:
    """Resolve a user-supplied path or fall back to the default."""
    if value is not None:
        return Path(value).expanduser().resolve()
    return fallback


def _configured_vault_path() -> Path | None:
    """Return VAULT_PATH when configured, otherwise None."""
    value = os.environ.get("VAULT_PATH", "").strip()
    if not value:
        return None
    return Path(value).expanduser().resolve()


def _default_bookmarks_dir() -> Path:
    """Return the default Bookmarks directory from VAULT_PATH env var."""
    vault = _configured_vault_path()
    return vault / "Bookmarks" if vault is not None else Path()


def _default_search_index_path() -> Path:
    """Return the default search index path from configured vault-like paths."""
    vault = _configured_vault_path()
    if vault is not None:
        return vault / "Meta" / "bookmark-search.sqlite3"
    bookmarks_override = os.environ.get("BOOKMARKS_DIR", "").strip()
    if bookmarks_override:
        return (
            Path(bookmarks_override).expanduser().resolve().parent
            / "Meta"
            / "bookmark-search.sqlite3"
        )
    return Path()


def _default_hubs_dir() -> Path:
    """Return the default generated-hubs directory from configured paths."""
    vault = _configured_vault_path()
    if vault is not None:
        return vault / "Meta" / "bookmark-hubs"
    bookmarks_override = os.environ.get("BOOKMARKS_DIR", "").strip()
    if bookmarks_override:
        return (
            Path(bookmarks_override).expanduser().resolve().parent
            / "Meta"
            / "bookmark-hubs"
        )
    return Path()


def _default_guide_path() -> Path:
    """Return the default classification guide path from configured vault-like paths."""
    vault = _configured_vault_path()
    if vault is not None:
        return vault / "Meta" / "Bookmark-Classification-Guide.md"
    bookmarks_override = os.environ.get("BOOKMARKS_DIR", "").strip()
    if bookmarks_override:
        return (
            Path(bookmarks_override).expanduser().resolve().parent
            / "Meta"
            / "Bookmark-Classification-Guide.md"
        )
    return Path()


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


def require_bookmarks_dir() -> Path:
    """Return a usable bookmarks directory or raise a clear configuration error.

    The directory itself may be created later by write commands, but its
    configuration must be explicit. This prevents commands from silently using
    the current working directory when neither BOOKMARKS_DIR nor VAULT_PATH is
    set.
    """
    has_override = bool(os.environ.get("BOOKMARKS_DIR", "").strip())
    vault = _configured_vault_path()
    if not has_override and vault is None:
        raise BookmarkPathError(
            "Bookmark vault is not configured. Set BOOKMARKS_DIR or set "
            "VAULT_PATH to your Obsidian vault root."
        )
    if not has_override and vault is not None and not vault.is_dir():
        raise BookmarkPathError(
            f"VAULT_PATH does not exist or is not a directory: {vault}"
        )

    bookmarks_dir = get_bookmarks_dir()
    if bookmarks_dir.exists() and not bookmarks_dir.is_dir():
        raise BookmarkPathError(
            f"BOOKMARKS_DIR exists but is not a directory: {bookmarks_dir}"
        )
    return bookmarks_dir


def get_search_index_path() -> Path:
    """Return the configured search index database path."""
    return _resolve_path(
        os.environ.get("BOOKMARK_SEARCH_INDEX"), _default_search_index_path()
    )


def get_hubs_dir() -> Path:
    """Return the configured directory for generated hub pages."""
    return _resolve_path(os.environ.get("BOOKMARK_HUBS_DIR"), _default_hubs_dir())


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
