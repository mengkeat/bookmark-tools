from __future__ import annotations

import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

from .classify import get_llm_config
from .http_retry import urlopen_with_retry
from .render import infer_summary
from .types import PageData

SUMMARIZE_TIMEOUT_SECONDS = 180
SUMMARY_CHAR_LIMIT = 900
SUMMARY_CONTENT_LIMIT = 12_000


def _trim_summary(text: str) -> str:
    """Trim summary output to vault-friendly length."""
    return text.strip()[:SUMMARY_CHAR_LIMIT].strip()


def summarize_with_tool(url: str) -> str | None:
    """Generate a summary using the external `summarize` CLI when available."""
    if shutil.which("summarize") is None:
        return None

    command = [
        "summarize",
        url,
        "--json",
        "--plain",
        "--no-color",
        "--metrics",
        "off",
        "--stream",
        "off",
        "--length",
        "short",
        "--force-summary",
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=SUMMARIZE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(
            f"summarize tool failed ({exc.__class__.__name__}); falling back.",
            file=sys.stderr,
        )
        return None

    summary = ""
    if completed.stdout.strip():
        try:
            payload = json.loads(completed.stdout)
            summary = _trim_summary(str(payload.get("summary", "")))
        except json.JSONDecodeError:
            summary = _trim_summary(completed.stdout)

    if completed.returncode == 0 and summary:
        return summary

    print(
        "summarize tool returned no summary; falling back.",
        file=sys.stderr,
    )
    return None


def summarize_with_llm(page_data: PageData) -> str | None:
    """Generate a summary directly with the configured LLM API."""
    config = get_llm_config()
    if not config:
        return None

    content = page_data["content"][:SUMMARY_CONTENT_LIMIT]
    payload = {
        "model": config["model"],
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": "Summarize bookmark content in 2-4 concise sentences. Return plain text only.",
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "title": page_data["title"],
                        "description": page_data["description"],
                        "language": page_data["language"],
                        "content": content,
                    },
                    ensure_ascii=False,
                ),
            },
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
        with urlopen_with_retry(request, timeout=SUMMARIZE_TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode("utf-8"))
        message = body["choices"][0]["message"]
        text = _trim_summary(str(message.get("content") or message.get("reasoning") or ""))
        return text or None
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        json.JSONDecodeError,
        KeyError,
        IndexError,
        TypeError,
    ) as exc:
        print(
            f"LLM summarization failed ({exc.__class__.__name__}); falling back.",
            file=sys.stderr,
        )
        return None


def generate_summary(
    url: str,
    page_data: PageData,
    classification_summary: str | None = None,
) -> str:
    """Generate summary with summarize tool, then classifier output, then fallbacks."""
    normalized_classification_summary = (classification_summary or "").strip()
    return (
        summarize_with_tool(url)
        or normalized_classification_summary
        or summarize_with_llm(page_data)
        or infer_summary(page_data["description"], page_data["content"])
    )
