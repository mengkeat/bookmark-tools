from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from collections import Counter

from .http_retry import urlopen_with_retry
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

from .paths import DEFAULT_TIMEOUT, get_bookmarks_dir, get_guide_path
from .render import infer_summary
from .types import BookmarkMetadata, PageData
from .vault_profile import BookmarkProfile, parse_frontmatter, tokenize

TAG_STOP_WORDS = {"and", "for", "from", "into", "that", "the", "this", "with"}
ALLOWED_BOOKMARK_TYPES = ("article", "video", "course", "tool", "paper", "book")
DEFAULT_BOOKMARK_TYPE = "article"
STRONG_MATCH_SCORE_MIN = 0.08
STRONG_MATCH_OVERLAP_MIN = 2
SIMILAR_NOTES_LIMIT = 8
LLM_SIMILAR_NOTES_LIMIT = 5
INFERRED_TAG_LIMIT = 6
ENRICHED_TAG_LIMIT = 8
RELATED_TOPIC_LIMIT = 4


@dataclass(frozen=True)
class SimilarNote:
    folder: str
    tags: list[str]
    parent_topic: str
    score: float
    overlap: int


def find_existing_url(url: str, profile: BookmarkProfile | None = None) -> Path | None:
    """Return the existing note path for a URL if it is already bookmarked."""
    normalized = url.rstrip("/")
    if profile:
        return profile.url_index.get(normalized)
    bookmarks_dir = get_bookmarks_dir()
    for note_path in bookmarks_dir.rglob("*.md"):
        existing_url = str(parse_frontmatter(note_path).get("url", "")).rstrip("/")
        if existing_url == normalized:
            return note_path
    return None


def rank_similar_notes(
    page_data: PageData, profile: BookmarkProfile, limit: int = SIMILAR_NOTES_LIMIT
) -> list[SimilarNote]:
    """Rank existing notes by token overlap similarity to the current page."""
    query_tokens = tokenize(
        " ".join([page_data["title"], page_data["description"], page_data["content"]])
    )
    matches: list[SimilarNote] = []
    for note in profile.notes:
        overlap = len(query_tokens & note.tokens)
        if overlap == 0:
            continue
        score = overlap / max(len(query_tokens | note.tokens), 1)
        matches.append(
            SimilarNote(
                folder=note.folder,
                tags=note.tags,
                parent_topic=note.parent_topic,
                score=score,
                overlap=overlap,
            )
        )
    matches.sort(key=lambda match: match.score, reverse=True)
    return matches[:limit]


def strong_similar_notes(similar_notes: list[SimilarNote]) -> list[SimilarNote]:
    """Filter similar notes to high-confidence matches only."""
    return [
        note
        for note in similar_notes
        if note.score >= STRONG_MATCH_SCORE_MIN
        and note.overlap >= STRONG_MATCH_OVERLAP_MIN
    ]


def choose_folder_from_profile(
    similar_notes: list[SimilarNote], profile: BookmarkProfile
) -> str:
    """Infer the best destination folder from similar notes and existing folders."""
    strong_notes = strong_similar_notes(similar_notes)
    if strong_notes:
        folder_scores: Counter[str] = Counter()
        for note in strong_notes:
            folder_scores[note.folder] += note.score
        best_folder, _ = folder_scores.most_common(1)[0]
        if best_folder:
            return best_folder
    return (
        "Development"
        if "Development" in profile.folders
        else (profile.folders[0] if profile.folders else "Development")
    )


def derive_tags(title: str, description: str, folder: str) -> list[str]:
    """Generate initial tags from title/description with a folder hint."""
    tags: list[str] = []
    for word in re.findall(r"[A-Za-z0-9+#-]{3,}", f"{title} {description}"):
        lowered = word.lower()
        if lowered.isdigit() or lowered in TAG_STOP_WORDS or lowered in tags:
            continue
        tags.append(lowered)
        if len(tags) >= INFERRED_TAG_LIMIT:
            break
    folder_hint = folder.split("/")[-1].lower()
    if folder_hint and folder_hint not in tags:
        tags.insert(0, folder_hint)
    return tags[:INFERRED_TAG_LIMIT]


def enrich_tags_from_similar(
    base_tags: list[str], similar_notes: list[SimilarNote]
) -> list[str]:
    """Augment generated tags with tags observed in strong similar notes."""
    tags = list(base_tags)
    for note in strong_similar_notes(similar_notes):
        for tag in note.tags:
            lowered = tag.lower()
            if lowered not in tags:
                tags.append(lowered)
            if len(tags) >= ENRICHED_TAG_LIMIT:
                return tags
    return tags[:ENRICHED_TAG_LIMIT]


def derive_related_topics(folder: str, tags: list[str]) -> list[str]:
    """Infer related topics from folder hierarchy and selected tags."""
    related = [part.lower() for part in folder.split("/") if part]
    for tag in tags:
        if tag not in related:
            related.append(tag)
        if len(related) >= RELATED_TOPIC_LIMIT:
            break
    return related[:RELATED_TOPIC_LIMIT]


def derive_parent_topic(
    folder: str, profile: BookmarkProfile, similar_notes: list[SimilarNote]
) -> str:
    """Infer the parent topic using folder defaults and similar-note signals."""
    if folder in profile.folder_parent_topics:
        return profile.folder_parent_topics[folder]
    for note in strong_similar_notes(similar_notes):
        if note.parent_topic:
            return note.parent_topic
    return folder.split("/")[-1] if folder else "Bookmarks"


def get_llm_config() -> dict[str, str] | None:
    """Read LLM configuration from environment variables."""
    provider = os.environ.get("LLM_PROVIDER", "").strip().lower()
    api_key = (
        os.environ.get("BOOKMARK_LLM_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("OPENROUTER_API_KEY")
    )
    if not api_key:
        return None
    base_url = os.environ.get("BOOKMARK_LLM_BASE_URL") or os.environ.get(
        "OPENAI_BASE_URL"
    )
    if not base_url:
        base_url = (
            "https://openrouter.ai/api/v1"
            if provider == "openrouter"
            else "https://api.openai.com/v1"
        )
    model = (
        os.environ.get("BOOKMARK_LLM_MODEL")
        or os.environ.get("OPENAI_MODEL")
        or os.environ.get("MODEL_ID")
        or "gpt-4.1-mini"
    )
    if model.startswith("openrouter/"):
        model = model[len("openrouter/") :]
    return {
        "api_key": api_key,
        "model": model,
        "base_url": base_url.rstrip("/"),
    }


def call_llm(
    page_data: PageData,
    profile: BookmarkProfile,
    similar_notes: list[SimilarNote],
    allow_new_subfolder: bool,
) -> BookmarkMetadata | None:
    """Call the configured LLM for classification and return parsed JSON metadata."""
    config = get_llm_config()
    if not config:
        return None

    prompt = {
        "guide": get_guide_path().read_text(encoding="utf-8") if get_guide_path().exists() else "",
        "allow_new_subfolder": allow_new_subfolder,
        "existing_folders": profile.folders,
        "schema": profile.schema,
        "folder_examples": profile.folder_examples,
        "similar_notes": [
            {
                "folder": note.folder,
                "tags": note.tags,
                "parent_topic": note.parent_topic,
                "score": round(note.score, 3),
            }
            for note in similar_notes[:LLM_SIMILAR_NOTES_LIMIT]
        ],
        "bookmark": page_data,
        "allowed_types": list(ALLOWED_BOOKMARK_TYPES),
        "required_schema": {
            "title": "string",
            "type": "string (must be one of allowed_types)",
            "tags": ["string"],
            "language": "string",
            "related": [
                "string (lowercase single-word noun tag; no slashes or spaces)"
            ],
            "parent_topic": "string",
            "description": "string",
            "summary": "string",
            "folder": "string",
        },
    }
    payload = {
        "model": config["model"],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": "Classify the bookmark into the vault taxonomy and return strict JSON only. Infer `type`, `tags`, `related`, and `parent_topic` semantically from the bookmark content and context (not fixed keyword rules). Infer `type` as one value from `allowed_types`. `related` must contain lowercase single-word noun tags only (no slashes or spaces). Prefer existing folders and never create a new top-level folder.",
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
    }
    request = urllib.request.Request(
        f"{config['base_url']}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen_with_retry(request, timeout=DEFAULT_TIMEOUT) as response:
            body = json.loads(response.read().decode("utf-8"))
        message = body["choices"][0]["message"]
        content = message.get("content") or message.get("reasoning") or ""
        return json.loads(content)
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        json.JSONDecodeError,
        KeyError,
        IndexError,
        TypeError,
    ) as exc:
        logger.warning(
            "LLM classification failed (%s); falling back to heuristics.",
            exc.__class__.__name__,
        )
        return None


def heuristic_classification(
    page_data: PageData,
    profile: BookmarkProfile,
    similar_notes: list[SimilarNote],
) -> BookmarkMetadata:
    """Classify a bookmark using deterministic heuristics when LLM is unavailable."""
    folder = choose_folder_from_profile(similar_notes, profile)
    tags = enrich_tags_from_similar(
        derive_tags(page_data["title"], page_data["description"], folder),
        similar_notes,
    )
    return {
        "title": page_data["title"],
        "type": DEFAULT_BOOKMARK_TYPE,
        "tags": tags,
        "language": page_data["language"] or "en",
        "related": derive_related_topics(folder, tags),
        "parent_topic": derive_parent_topic(folder, profile, similar_notes),
        "description": page_data["description"] or page_data["title"],
        "summary": infer_summary(page_data["description"], page_data["content"]),
        "folder": folder,
    }


def related_note_count(parent_dir: Path, candidate_topic: str, bookmarks_dir: Path) -> int:
    """Count notes in a folder that are topically related to a candidate subtopic."""
    topic_tokens = [
        token.lower()
        for token in re.findall(r"[A-Za-z0-9]+", candidate_topic)
        if len(token) > 2
    ]
    if not topic_tokens or not parent_dir.exists():
        return 0
    count = 0
    for note_path in parent_dir.rglob("*.md"):
        metadata = parse_frontmatter(note_path)
        title_tokens = tokenize(
            " ".join(
                [
                    note_path.stem.replace("-", " "),
                    str(metadata.get("title", "")),
                    " ".join(metadata.get("tags", [])),
                ]
            )
        )
        if any(token in title_tokens for token in topic_tokens):
            count += 1
    return count


def validate_folder(raw_folder: str, allow_new_subfolder: bool, bookmarks_dir: Path | None = None) -> tuple[str, str]:
    """Validate or adjust folder choices according to vault constraints and support."""
    if bookmarks_dir is None:
        bookmarks_dir = get_bookmarks_dir()
    normalized = re.sub(r"/{2,}", "/", raw_folder.strip().strip("/").replace("\\", "/"))
    if not normalized or normalized.startswith(".") or ".." in normalized.split("/"):
        return (
            "Development",
            "Invalid folder from classifier; fell back to Development.",
        )
    if (bookmarks_dir / normalized).exists():
        return normalized, ""

    parts = normalized.split("/")
    top_level = bookmarks_dir / parts[0]
    if not allow_new_subfolder or not top_level.exists() or len(parts) < 2:
        fallback = parts[0] if top_level.exists() else "Development"
        return (
            fallback,
            f"Rejected new folder `{normalized}`; used `{fallback}` instead.",
        )

    parent_folder = "/".join(parts[:-1])
    parent_dir = bookmarks_dir / parent_folder
    if not parent_dir.exists():
        fallback = (
            parent_folder if (bookmarks_dir / parent_folder).exists() else parts[0]
        )
        return (
            fallback,
            f"Rejected nested folder `{normalized}`; used `{fallback}` instead.",
        )

    support = related_note_count(parent_dir, parts[-1], bookmarks_dir)
    if support >= 2:
        return (
            normalized,
            f"Creating new subfolder `{normalized}` based on {support} related existing notes.",
        )
    return (
        parent_folder,
        f"Needed 2 related notes before creating `{normalized}`; used `{parent_folder}` instead.",
    )
