from __future__ import annotations

import random
import time
import urllib.error
import urllib.request

DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 1.0
DEFAULT_MAX_DELAY = 30.0

RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}


def urlopen_with_retry(
    request: urllib.request.Request,
    *,
    timeout: int | float = 20,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
) -> urllib.response.addinfourl:
    """Open a URL with exponential backoff retry on transient failures.

    Retries on connection errors, timeouts, and HTTP 429/5xx responses.
    Uses full jitter: delay = random(0, min(max_delay, base_delay * 2^attempt)).
    """
    last_exception: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            if exc.code not in RETRYABLE_HTTP_CODES or attempt == max_retries:
                raise
            last_exception = exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt == max_retries:
                raise
            last_exception = exc

        delay = min(max_delay, base_delay * (2**attempt))
        jittered_delay = random.uniform(0, delay)  # noqa: S311
        time.sleep(jittered_delay)

    raise last_exception  # type: ignore[misc]
