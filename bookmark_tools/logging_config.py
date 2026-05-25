from __future__ import annotations

import logging
import os


def configure_logging(*, verbose: bool = False, quiet: bool = False) -> None:
    """Configure root logging based on CLI flags and LOG_LEVEL env var."""
    if verbose:
        level = logging.DEBUG
    elif quiet:
        level = logging.ERROR
    else:
        env_level = os.environ.get("LOG_LEVEL", "").upper()
        level = getattr(logging, env_level, logging.INFO)
    logging.basicConfig(
        format="%(levelname)s: %(message)s",
        level=level,
    )
