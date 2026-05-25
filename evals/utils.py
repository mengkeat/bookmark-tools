from __future__ import annotations

import hashlib
import re


def folder_ancestors(folder: str) -> list[str]:
    """Return each ancestor path for a slash-delimited folder."""
    parts = [part for part in folder.strip("/").split("/") if part]
    return ["/".join(parts[: index + 1]) for index in range(len(parts))]


def safe_filename_stem(text: str, *, max_length: int = 120) -> str:
    """Convert arbitrary text to a conservative filename stem."""
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", text.strip()).strip("-").lower()
    if not stem:
        stem = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return stem[:max_length]
