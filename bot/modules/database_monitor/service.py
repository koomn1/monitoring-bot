"""
bot/modules/database_monitor/service.py — Database Monitor

Checks Supabase Postgres health/latency via a lightweight query, records
history, manages incident lifecycle.

See: modules/05-database-monitor.md
"""

from __future__ import annotations

import time

from bot.db.repositories.health_repo import is_database_reachable
from bot.db.repositories.incidents_repo import get_open_incident, open_incident, resolve_incident
from bot.db.repositories.logs_repo import record_monitoring_result
from bot.modules.notifications import service as notifications_service


async def check_database() -> dict:
    started = time.monotonic()
    healthy = await is_database_reachable()
    latency_ms = int((time.monotonic() - started) * 1000)
    status = "up" if healthy else "down"

    await record_monitoring_result(service="database", status=status, latency_ms=latency_ms)
    await _handle_state_transition(status, latency_ms)
    return {"status": status, "latency_ms": latency_ms}


async def _handle_state_transition(status: str, latency_ms: int) -> None:
    existing = await get_open_incident("database")
    if status == "down" and existing is None:
        await open_incident(service="database", details="Supabase database unreachable")
        await notifications_service.notify_database_failure(latency_ms)
    elif status == "up" and existing is not None:
        await resolve_incident(existing["id"])
