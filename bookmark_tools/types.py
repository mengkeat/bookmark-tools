from __future__ import annotations

from typing import TypedDict


class PageData(TypedDict):
    url: str
    title: str
    description: str
    language: str
    content: str


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
