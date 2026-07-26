"""bot/utils/retry.py — small async retry/backoff decorator used by
integrations clients and monitor modules to avoid flooding free-tier
API quotas on transient failures.

By default retries on any exception in `exceptions`. Pass `retry_if` to
narrow that further — e.g. integrations clients use it to retry on
network errors and 5xx responses, but NOT on 4xx (a 404/401 will never
succeed on retry, so retrying just wastes the free-tier request budget
and adds latency to the user's command). See bot/integrations/*.py for
the concrete predicates used."""

from __future__ import annotations

import asyncio
import functools
import logging
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")
logger = logging.getLogger("utils.retry")


def is_transient_service_error(exc: Exception) -> bool:
    """
    Retry predicate for bot.core.exceptions.ExternalServiceError: retry
    on network-level failures (status_code is None) and server errors
    (5xx), but never on 4xx — a 401/403/404 will not succeed on retry,
    so retrying it only burns free-tier request quota and adds latency.
    """
    status_code = getattr(exc, "status_code", None)
    return status_code is None or status_code >= 500


def async_retry(
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    exceptions: tuple = (Exception,),
    retry_if: Callable[[Exception], bool] | None = None,
):
    def decorator(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs) -> T:
            last_exc: Exception | None = None
            for attempt in range(1, attempts + 1):
                try:
                    return await fn(*args, **kwargs)
                except exceptions as exc:  # noqa: BLE001
                    if retry_if is not None and not retry_if(exc):
                        raise
                    last_exc = exc
                    if attempt < attempts:
                        delay = base_delay * (2 ** (attempt - 1))
                        logger.warning(
                            "%s failed (attempt %d/%d): %s — retrying in %.1fs",
                            fn.__name__, attempt, attempts, exc, delay,
                        )
                        await asyncio.sleep(delay)
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator
