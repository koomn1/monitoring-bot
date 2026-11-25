"""
bot/modules/api_monitor/service.py — API Monitor

Same pattern as website_monitor but targets API_BASE_URL and (optionally)
a configurable list of critical endpoints to spot-check.

See: modules/04-api-monitor.md
"""

from __future__ import annotations

import time

import httpx

from bot.config import settings
from bot.core.exceptions import ConfigurationError
from bot.db.repositories.incidents_repo import get_open_incident, open_incident, resolve_incident
from bot.db.repositories.logs_repo import record_monitoring_result
from bot.modules.notifications import service as notifications_service


async def check_api() -> dict:
    if not settings.api_base_url:
        raise ConfigurationError("API_BASE_URL is not configured")

    base_url = settings.api_base_url.rstrip("/")
    started = time.monotonic()
    status = "down"
    status_code = None
    health_payload: dict | None = None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{base_url}/health")
            status_code = resp.status_code
            status = "up" if resp.status_code < 400 else "down"
            try:
                data = resp.json()
                if isinstance(data, dict):
                    health_payload = data
            except Exception:  # noqa: BLE001
                health_payload = None
    except httpx.HTTPError:
        status = "down"

    latency_ms = int((time.monotonic() - started) * 1000)
    await record_monitoring_result(
        service="api",
        status=status,
        latency_ms=latency_ms,
        metadata={"status_code": status_code, "worker_status": (health_payload or {}).get("status")},
    )
    await _handle_state_transition(status, latency_ms)
    return {
        "status": status,
        "latency_ms": latency_ms,
        "status_code": status_code,
        "worker_status": (health_payload or {}).get("status"),
    }


async def _handle_state_transition(status: str, latency_ms: int) -> None:
    existing = await get_open_incident("api")
    if status == "down" and existing is None:
        await open_incident(service="api", details=f"API unreachable (latency={latency_ms}ms)")
        await notifications_service.notify_api_failure(latency_ms)
    elif status == "up" and existing is not None:
        await resolve_incident(existing["id"])
