"""
bot/core/rate_limiter.py

Simple in-memory, per-user sliding-window rate limiter protecting the
Bot from command spam (accidental double-taps or deliberate abuse).
Deliberately NOT persisted to the database — a Bot restart resetting
limits is an acceptable tradeoff against adding a DB round-trip to
every single command (see docs/08-free-infrastructure.md).

See: docs/07-security.md, bot/core/exceptions.py:RateLimitedError
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from bot.core.exceptions import RateLimitedError

_WINDOW_SECONDS = 10.0
_MAX_COMMANDS_PER_WINDOW = 8

_history: dict[int, deque[float]] = defaultdict(deque)


def check_rate_limit(user_id: int) -> None:
    """
    Raises RateLimitedError if `user_id` has sent more than
    _MAX_COMMANDS_PER_WINDOW commands/button-taps in the last
    _WINDOW_SECONDS. Called by bot/core/router.py:dispatch before the
    permission check (a rate-limited stranger shouldn't get a different
    signal than a rate-limited admin — both just get told to slow down).
    """
    now = time.monotonic()
    history = _history[user_id]

    while history and now - history[0] > _WINDOW_SECONDS:
        history.popleft()

    if len(history) >= _MAX_COMMANDS_PER_WINDOW:
        raise RateLimitedError("Too many commands — please wait a few seconds and try again.")

    history.append(now)


def reset(user_id: int | None = None) -> None:
    """Testing/admin utility — clears rate-limit history for one user,
    or everyone if user_id is None."""
    if user_id is None:
        _history.clear()
    else:
        _history.pop(user_id, None)
