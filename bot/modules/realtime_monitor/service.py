"""
bot/modules/realtime_monitor/service.py — Realtime Monitor

Verifies Supabase Realtime (websocket) connectivity with an actual
Phoenix-protocol handshake: connects, sends a heartbeat frame, and
requires a response within the timeout window.

See: modules/07-realtime-monitor.md
"""

from __future__ import annotations

import asyncio
import time

import aiohttp

from bot.config import settings
from bot.core.exceptions import ConfigurationError
from bot.db.repositories.incidents_repo import get_open_incident, open_incident, resolve_incident
from bot.db.repositories.logs_repo import record_monitoring_result
from bot.modules.notifications import service as notifications_service

_HANDSHAKE_TIMEOUT_SECONDS = 10.0


def _websocket_url() -> str:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise ConfigurationError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not configured")
    ws_base = settings.supabase_url.replace("https://", "wss://").replace("http://", "ws://")
    return f"{ws_base}/realtime/v1/websocket?apikey={settings.supabase_service_role_key}&vsn=1.0.0"


async def check_realtime() -> dict:
    started = time.monotonic()
    status = "down"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(_websocket_url(), timeout=_HANDSHAKE_TIMEOUT_SECONDS) as ws:
                # Phoenix channel heartbeat — the same handshake Supabase's
                # own client libraries use to keep a Realtime connection alive.
                await ws.send_json(
                    {"topic": "phoenix", "event": "heartbeat", "payload": {}, "ref": "1"}
                )
                msg = await asyncio.wait_for(ws.receive(), timeout=_HANDSHAKE_TIMEOUT_SECONDS)
                if msg.type in (aiohttp.WSMsgType.TEXT, aiohttp.WSMsgType.BINARY):
                    status = "up"
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
        status = "down"

    latency_ms = int((time.monotonic() - started) * 1000)
    await record_monitoring_result(service="realtime", status=status, latency_ms=latency_ms)
    await _handle_state_transition(status, latency_ms)
    return {"status": status, "latency_ms": latency_ms}


async def _handle_state_transition(status: str, latency_ms: int) -> None:
    existing = await get_open_incident("realtime")
    if status == "down" and existing is None:
        await open_incident(service="realtime", details=f"Realtime handshake failed (latency={latency_ms}ms)")
        await notifications_service.notify_security_alert("Realtime (websocket) is unreachable.")
    elif status == "up" and existing is not None:
        await resolve_incident(existing["id"])
