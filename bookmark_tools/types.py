from __future__ import annotations

from typing import TypedDict


class PageData(TypedDict):
    url: str  # Original URL as provided by the user
    final_url: str  # URL after following HTTP redirects
    canonical_url: str  # Canonical URL from <link rel="canonical"> or og:url
    title: str
    description: str
    language: str
    content: str  # Truncated preview (8 KB) for classification
    full_content: str  # Full cleaned text for hashing
    http_status: int
    content_type: str


class BookmarkMetadata(TypedDict, total=False):
    title: str
    type: str
    tags: list[str]
    language: str
    related: list[str]
    parent_topic: str
    description: str
    summary: str
    folder: str
    visibility: str


class NormalizedBookmarkMetadata(TypedDict):
    folder: str
    title: str
    type: str
    tags: list[str]
    language: str
    related: list[str]
    parent_topic: str
    description: str
    summary: str
    visibility: str
