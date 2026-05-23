from __future__ import annotations

import urllib.parse


def normalize_url(url: str) -> str:
    """Return a conservative normalized URL for identity comparisons.

    The normalizer intentionally avoids aggressive rewrites that can merge
    distinct resources. It lowercases scheme/host, strips default ports, and
    removes redundant trailing slashes from the path while preserving query and
    fragment components.
    """
    text = str(url).strip()
    if not text:
        return ""

    parsed = urllib.parse.urlsplit(text)
    if not parsed.scheme or not parsed.netloc:
        return text.rstrip("/")

    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    try:
        hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError:
        pass

    try:
        port = parsed.port
    except ValueError:
        port = None
    default_port = (scheme == "http" and port == 80) or (
        scheme == "https" and port == 443
    )
    host = (
        f"[{hostname}]"
        if ":" in hostname and not hostname.startswith("[")
        else hostname
    )
    netloc = host
    if port is not None and not default_port:
        netloc = f"{netloc}:{port}"
    if parsed.username:
        userinfo = urllib.parse.quote(parsed.username, safe="")
        if parsed.password:
            userinfo = f"{userinfo}:{urllib.parse.quote(parsed.password, safe='')}"
        netloc = f"{userinfo}@{netloc}"

    path = urllib.parse.quote(
        urllib.parse.unquote(parsed.path or ""),
        safe="/%:@!$&'()*+,;=",
    )
    if path == "/":
        path = ""
    else:
        path = path.rstrip("/")

    return urllib.parse.urlunsplit(
        (scheme, netloc, path, parsed.query, parsed.fragment)
    )
