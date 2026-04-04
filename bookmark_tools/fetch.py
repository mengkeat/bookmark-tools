from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from .http_retry import urlopen_with_retry
from .paths import DEFAULT_TIMEOUT, MAX_FETCH_BYTES
from .types import PageData

CONTENT_PREVIEW_LIMIT = 8_000


def fetch_text(url: str) -> tuple[str, str]:
    """Fetch URL content and return the final URL with decoded text."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "bookmark-bot/1.0 (+https://example.com)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.5",
        },
    )
    with urlopen_with_retry(request, timeout=DEFAULT_TIMEOUT) as response:
        final_url = response.geturl()
        charset = response.headers.get_content_charset() or "utf-8"
        raw = response.read(MAX_FETCH_BYTES)
    return final_url, raw.decode(charset, errors="replace")


class _MetadataParser(HTMLParser):
    """Extract title, meta tags, and lang attribute from HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.meta: dict[str, str] = {}
        self.language = ""
        self._in_title = False
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = {k.lower(): (v or "") for k, v in attrs}
        if tag == "html" and "lang" in attr_dict:
            self.language = attr_dict["lang"].split("-", 1)[0].lower()
        elif tag == "title":
            self._in_title = True
            self._title_parts = []
        elif self._in_title and tag != "title":
            self._finalize_title()
        if tag == "meta":
            content = attr_dict.get("content", "")
            name = attr_dict.get("property", "") or attr_dict.get("name", "")
            if name and content:
                self.meta.setdefault(name.lower(), content)

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)

    def _finalize_title(self) -> None:
        if self._in_title:
            self._in_title = False
            self.title = " ".join(self._title_parts).strip()

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._finalize_title()


def _parse_metadata(text: str) -> _MetadataParser:
    """Parse HTML and return extracted metadata."""
    parser = _MetadataParser()
    parser.feed(text)
    return parser


def search_meta(name: str, text: str) -> str:
    """Extract a meta tag value by property or name using the HTML parser."""
    parser = _parse_metadata(text)
    value = parser.meta.get(name.lower(), "")
    return html.unescape(value).strip() if value else ""


def clean_html(text: str) -> str:
    """Strip scripts/styles/tags and collapse whitespace into plain text."""
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?is)<noscript.*?>.*?</noscript>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def extract_page_data(url: str) -> PageData:
    """Fetch and extract normalized page fields used for bookmark classification."""
    final_url, raw_text = fetch_text(url)
    parser = _parse_metadata(raw_text)
    title = parser.meta.get("og:title", "") or parser.title
    description = parser.meta.get("description", "") or parser.meta.get(
        "og:description", ""
    )
    language = parser.language or "en"
    return {
        "url": final_url,
        "title": title or urllib.parse.urlparse(final_url).netloc,
        "description": description,
        "language": language,
        "content": clean_html(raw_text)[:CONTENT_PREVIEW_LIMIT],
    }
