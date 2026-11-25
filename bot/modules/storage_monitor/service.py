"""
bot/modules/storage_monitor/service.py — Storage Monitor

Checks Supabase Storage bucket availability and reports approximate
usage against the free-tier quota (1GB). Backs /storage.

See: modules/06-storage-monitor.md
"""

from __future__ import annotations

from bot.db.repositories.health_repo import get_storage_buckets_summary, list_storage_buckets
from bot.db.repositories.incidents_repo import get_open_incident, open_incident, resolve_incident
from bot.db.repositories.logs_repo import record_monitoring_result
from bot.modules.notifications import service as notifications_service


async def check_storage() -> dict:
    status = "up"
    bucket_count = 0
    buckets_detail: list[dict] = []
    try:
        buckets_detail = await get_storage_buckets_summary()
        bucket_count = len(buckets_detail)
    except Exception:  # noqa: BLE001
        try:
            raw_buckets = await list_storage_buckets()
            bucket_count = len(raw_buckets)
        except Exception:  # noqa: BLE001
            status = "down"

    await record_monitoring_result(service="storage", status=status, latency_ms=None, metadata={"buckets": bucket_count})
    await _handle_state_transition(status)
    return {"status": status, "bucket_count": bucket_count, "buckets": buckets_detail}


async def _handle_state_transition(status: str) -> None:
    """Matches the soft up/down + incident-lifecycle pattern used by
    every other monitor (website/api/database) — storage previously
    raised instead, which was flagged as an inconsistency to fix."""
    existing = await get_open_incident("storage")
    if status == "down" and existing is None:
        await open_incident(service="storage", details="Supabase Storage is unreachable")
        await notifications_service.notify_storage_failure()
    elif status == "up" and existing is not None:
        await resolve_incident(existing["id"])
