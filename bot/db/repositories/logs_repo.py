"""
bot/db/repositories/logs_repo.py

Data access layer for audit logs and monitoring logs (tables:
`audit_logs`, `monitoring_logs` — see database/02-tables.md).

See: modules/15-logging-module.md, database/02-tables.md
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


async def get_recent_failed_commands(*, limit: int = 10) -> list[dict[str, Any]]:
    result = (
        db()
        .table("audit_logs")
        .select("*")
        .not_.is_("error", "null")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data


async def get_recent_failed_checks(*, hours: int = 24, limit: int = 10) -> list[dict[str, Any]]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    result = (
        db()
        .table("monitoring_logs")
        .select("*")
        .eq("status", "down")
        .gte("checked_at", cutoff)
        .order("checked_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data


async def get_monitoring_history(service: str, *, hours: int = 24) -> list[dict[str, Any]]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    result = (
        db()
        .table("monitoring_logs")
        .select("*")
        .eq("service", service)
        .gte("checked_at", cutoff)
        .order("checked_at", desc=True)
        .limit(500)
        .execute()
    )
    return result.data


async def get_service_stats(*, hours: int = 24) -> dict[str, dict[str, Any]]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    result = (
        db()
        .table("monitoring_logs")
        .select("service,status,latency_ms,checked_at")
        .gte("checked_at", cutoff)
        .order("checked_at", desc=True)
        .limit(2000)
        .execute()
    )
    grouped: dict[str, dict[str, Any]] = {}
    for row in result.data or []:
        svc = str(row.get("service") or "unknown")
        entry = grouped.setdefault(
            svc,
            {
                "checks": 0,
                "up_count": 0,
                "down_count": 0,
                "latest_status": row.get("status", "unknown"),
                "latest_checked_at": row.get("checked_at"),
                "_latencies": [],
            },
        )
        entry["checks"] += 1
        if row.get("status") == "up":
            entry["up_count"] += 1
        elif row.get("status") == "down":
            entry["down_count"] += 1
        lat = row.get("latency_ms")
        if isinstance(lat, (int, float)) and lat >= 0:
            entry["_latencies"].append(int(lat))

    for entry in grouped.values():
        lats = entry.pop("_latencies")
        checks = entry["checks"]
        entry["uptime_pct"] = round((entry["up_count"] / checks) * 100.0, 2) if checks else None
        entry["avg_latency_ms"] = round(sum(lats) / len(lats)) if lats else None
    return grouped


async def get_uptime_percentage(service: str, *, days: int = 7) -> float | None:
    """Calculate uptime from bot's own monitoring_logs (no RPC required)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        result = (
            db()
            .table("monitoring_logs")
            .select("status")
            .eq("service", service)
            .gte("checked_at", cutoff)
            .limit(10000)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return None
        total = len(rows)
        up_count = sum(1 for r in rows if r.get("status") == "up")
        return round((up_count / total) * 100.0, 2)
    except Exception:  # noqa: BLE001
        return None


async def cleanup_old_logs(retention_days: int = 90) -> None:
    """Calls the cleanup_old_logs SQL function (see
    bot/db/migrations/0003_functions.sql) which deletes audit_logs and
    monitoring_logs rows older than retention_days."""
    db().rpc("cleanup_old_logs", {"p_retention_days": retention_days}).execute()
