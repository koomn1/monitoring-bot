"""
bot/modules/website_monitor/service.py — Website Monitor

Checks Quiz Space's public website availability/latency on a schedule
(see bot/core/scheduler.py -> automation) and on-demand via /status.
Opens/resolves incidents and triggers notifications on state transitions.

See: modules/03-website-monitor.md
"""

from __future__ import annotations

import time

import httpx

from bot.config import settings
from bot.core.exceptions import ConfigurationError
from bot.db.repositories.incidents_repo import get_open_incident, open_incident, resolve_incident
from bot.db.repositories.logs_repo import record_monitoring_result
from bot.modules.notifications import service as notifications_service


async def check_website() -> dict:
    if not settings.website_url:
        raise ConfigurationError("WEBSITE_URL is not configured")

    started = time.monotonic()
    status = "down"
    status_code = None
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(settings.website_url)
            status_code = resp.status_code
            status = "up" if resp.status_code < 400 else "down"
    except httpx.HTTPError:
        status = "down"

    latency_ms = int((time.monotonic() - started) * 1000)
    await record_monitoring_result(
        service="website", status=status, latency_ms=latency_ms,
        metadata={"status_code": status_code},
    )
    await _handle_state_transition(status, latency_ms)
    return {"status": status, "latency_ms": latency_ms, "status_code": status_code}


async def _handle_state_transition(status: str, latency_ms: int) -> None:
    existing = await get_open_incident("website")
    if status == "down" and existing is None:
        await open_incident(service="website", details=f"Website unreachable (latency={latency_ms}ms)")
        await notifications_service.notify_website_down(latency_ms)
    elif status == "up" and existing is not None:
        await resolve_incident(existing["id"])
        await notifications_service.notify_website_online(latency_ms)
