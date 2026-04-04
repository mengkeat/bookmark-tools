from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request

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


def search_meta(name: str, text: str) -> str:
    """Extract a meta tag value by property or name."""
    patterns = [
        rf'<meta[^>]+property=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+name=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{re.escape(name)}["\']',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']{re.escape(name)}["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return html.unescape(match.group(1)).strip()
    return ""


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
    title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw_text)
    title = search_meta("og:title", raw_text) or (
        html.unescape(title_match.group(1)).strip() if title_match else ""
    )
    description = search_meta("description", raw_text) or search_meta(
        "og:description", raw_text
    )
    language_match = re.search(
        r'<html[^>]+lang=["\']([a-zA-Z-]+)["\']', raw_text, flags=re.IGNORECASE
    )
    language = (
        language_match.group(1).split("-", 1)[0].lower() if language_match else ""
    ) or "en"
    return {
        "url": final_url,
        "title": title or urllib.parse.urlparse(final_url).netloc,
        "description": description,
        "language": language,
        "content": clean_html(raw_text)[:CONTENT_PREVIEW_LIMIT],
    }
