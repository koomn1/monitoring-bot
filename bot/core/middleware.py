"""
bot/core/middleware.py

Audit logging middleware. Wraps command dispatch so that every single
command invocation (successful or not) is persisted via the Logging
Module. This is intentionally decoupled from bot/core/router.py so that
logging behavior can be changed without touching routing/auth logic.

See: modules/15-logging-module.md, docs/07-security.md
"""

from __future__ import annotations

import logging
import time
from typing import Awaitable, Callable

from bot.core.router import CommandContext, DispatchResult

logger = logging.getLogger("bot.middleware")

NextFn = Callable[[CommandContext], Awaitable[DispatchResult]]


async def with_audit_log(ctx: CommandContext, next_fn: NextFn) -> DispatchResult:
    """
    Wraps a dispatch call: records start time, invokes `next_fn`, then
    writes an audit log entry via the logs repository. Import of the
    repository is deferred (function-local) to avoid a hard dependency
    from core -> db at module load time, keeping bot/core importable in
    isolation for unit tests.
    """
    started = time.monotonic()
    error: str | None = None

    try:
        result = await next_fn(ctx)
        return result
    except Exception as exc:  # noqa: BLE001
        error = str(exc)
        raise
    finally:
        duration_ms = int((time.monotonic() - started) * 1000)
        try:
            from bot.db.repositories.logs_repo import record_command_execution

            await record_command_execution(
                user_id=ctx.user_id,
                command=ctx.command,
                args=ctx.args,
                duration_ms=duration_ms,
                error=error,
            )
        except Exception:  # noqa: BLE001
            # Logging must never break the user-facing response.
            logger.exception("Failed to persist audit log for /%s", ctx.command)
