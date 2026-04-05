from __future__ import annotations

import re

DEFAULT_TAG_ALIASES: dict[str, str] = {
    "ml": "machine-learning",
    "ai": "artificial-intelligence",
    "dl": "deep-learning",
    "nlp": "natural-language-processing",
    "cv": "computer-vision",
    "rl": "reinforcement-learning",
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "db": "database",
    "k8s": "kubernetes",
    "tf": "tensorflow",
    "gcp": "google-cloud",
    "aws": "amazon-web-services",
}


def normalize_tag(tag: str, aliases: dict[str, str] | None = None) -> str:
    """Normalize a single tag to lowercase kebab-case, applying aliases."""
    cleaned = tag.strip().lower()
    cleaned = re.sub(r"\s+", "-", cleaned)
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    if aliases is None:
        aliases = DEFAULT_TAG_ALIASES
    return aliases.get(cleaned, cleaned)


def normalize_tags(tags: list[str], aliases: dict[str, str] | None = None) -> list[str]:
    """Normalize and deduplicate a list of tags."""
    seen: set[str] = set()
    result: list[str] = []
    for tag in tags:
        normalized = normalize_tag(tag, aliases)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def load_aliases(alias_text: str) -> dict[str, str]:
    """Parse a tag alias mapping from text (one 'alias = canonical' per line)."""
    aliases = dict(DEFAULT_TAG_ALIASES)
    for line in alias_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lower()
        value = value.strip().lower()
        if key and value:
            aliases[key] = value
    return aliases
