"""Bounded retries.

Only failures that can plausibly succeed on a second attempt are retried
(network errors, 5xx, Meta's temporary rate-limit codes). An expired token, a
validation error, a duplicate or a denied approval is raised immediately: a
retry would repeat the same mistake, and for a publisher that means posting
twice or hammering an API that is already refusing.

The loop is bounded three ways - attempt count, per-attempt delay cap and a
total deadline - so a stuck call cannot hold a client's calendar hostage.
"""
from __future__ import annotations

import random
import time
from collections.abc import Callable, Sequence
from typing import TypeVar

from .errors import RateLimitedError, RetryExhaustedError, TransientError

T = TypeVar("T")

RETRYABLE: tuple[type[BaseException], ...] = (TransientError, RateLimitedError)


def retry_call(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 4.0,
    deadline_seconds: float = 30.0,
    retry_on: Sequence[type[BaseException]] = RETRYABLE,
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[], float] = random.random,
) -> T:
    """Call ``fn``, retrying transient failures with exponential backoff."""
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    started = time.monotonic()
    last: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except tuple(retry_on) as exc:
            last = exc
            if attempt == attempts:
                break
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            delay += delay * 0.25 * jitter()
            if time.monotonic() - started + delay > deadline_seconds:
                break
            sleep(delay)
    raise RetryExhaustedError(
        f"{attempts} attempt(s) failed; last error: {type(last).__name__}: {last}"
    ) from last
