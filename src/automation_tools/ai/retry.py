"""Retry/backoff loop shared by every provider family.

Extracted from what used to be Gemini-only retry logic, so every provider gets
the same treatment Gemini already had.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Optional

from automation_tools.core.logger import print_error, print_warning, get_logger

logger = get_logger()

MAX_RETRIES = 4
BASE_BACKOFF = 2.0  # seconds; doubled each retry

# Substrings that mean "busy, try again" rather than "you asked for something
# impossible". Providers phrase these differently, so match on text.
RATE_LIMIT_MARKERS = (
    "429", "503", "resource_exhausted", "unavailable",
    "overloaded", "rate_limit", "rate limit",
)


def is_rate_limit(err: Exception) -> bool:
    """True when the error is transient and worth retrying."""
    msg = str(err).lower()
    return any(marker in msg for marker in RATE_LIMIT_MARKERS)


def with_retry(
    call: Callable[[], Any],
    *,
    label: str,
    max_retries: int = MAX_RETRIES,
    base_backoff: float = BASE_BACKOFF,
    sleep: Callable[[float], None] = time.sleep,
) -> Optional[Any]:
    """Runs `call()`, retrying transient failures with exponential backoff.

    Returns the call's result, or None once every attempt failed, having
    already printed the error. `sleep` is injected so tests never wait.
    """
    backoff = base_backoff
    last_err: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            return call()
        except Exception as e:
            last_err = e
            if is_rate_limit(e) and attempt < max_retries:
                print_warning(
                    f"{label} busy. Retrying {attempt}/{max_retries - 1} in {backoff:.1f}s…"
                )
                logger.warning(f"Retry {attempt} on {label}: {e}")
                sleep(backoff)
                backoff *= 2
                continue
            break  # permanent error, or retries exhausted

    print_error(f"{label} API error: {last_err}")
    return None
