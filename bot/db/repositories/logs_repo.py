"""
bot/db/repositories/logs_repo.py

Data access layer for audit logs and monitoring logs (tables:
`audit_logs`, `monitoring_logs` — see database/02-tables.md).

See: modules/15-logging-module.md, database/02-tables.md
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from bot.db.client import db


async def record_command_execution(
    *,
    user_id: int,
    command: str,
    args: list[str],
    duration_ms: int,
    error: Optional[str],
) -> None:
    """Inserts one row into `audit_logs` for every command dispatch.
    Called by bot/core/middleware.py — must never raise (caller already
    wraps this in a try/except, but keep this function itself defensive)."""
    payload = {
        "user_id": user_id,
        "command": command,
        "args": args,
        "duration_ms": duration_ms,
        "error": error,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    db().table("audit_logs").insert(payload).execute()


async def record_monitoring_result(
    *,
    service: str,
    status: str,
    latency_ms: Optional[int],
    metadata: dict[str, Any] | None = None,
) -> None:
    """Inserts one row into `monitoring_logs` for every health check run
    by any *_monitor module (website, api, database, storage, realtime,
    github, cloudflare, firebase)."""
    payload = {
        "service": service,
        "status": status,
        "latency_ms": latency_ms,
        "metadata": metadata or {},
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    db().table("monitoring_logs").insert(payload).execute()


async def get_recent_logs(*, limit: int = 50, command: Optional[str] = None) -> list[dict[str, Any]]:
    query = db().table("audit_logs").select("*").order("created_at", desc=True).limit(limit)
    if command:
        query = query.eq("command", command)
    result = query.execute()
    return result.data


async def get_monitoring_history(service: str, *, hours: int = 24) -> list[dict[str, Any]]:
    result = (
        db()
        .table("monitoring_logs")
        .select("*")
        .eq("service", service)
        .order("checked_at", desc=True)
        .limit(500)
        .execute()
    )
    return result.data


async def cleanup_old_logs(retention_days: int = 90) -> None:
    """Calls the cleanup_old_logs SQL function (see
    bot/db/migrations/0003_functions.sql) which deletes audit_logs and
    monitoring_logs rows older than retention_days."""
    db().rpc("cleanup_old_logs", {"p_retention_days": retention_days}).execute()
