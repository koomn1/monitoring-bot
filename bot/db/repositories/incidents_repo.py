"""
bot/db/repositories/incidents_repo.py

Data access layer for the `incidents` table — tracks every state
transition detected by monitoring modules (e.g. website going DOWN then
UP again), used to avoid duplicate notifications and to power incident
history in reports.

See: modules/19-notifications.md, database/02-tables.md
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from bot.db.client import db


async def get_open_incident(service: str) -> Optional[dict[str, Any]]:
    result = (
        db()
        .table("incidents")
        .select("*")
        .eq("service", service)
        .is_("resolved_at", "null")
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


async def open_incident(*, service: str, details: str) -> dict[str, Any]:
    payload = {
        "service": service,
        "details": details,
        "opened_at": datetime.now(timezone.utc).isoformat(),
        "resolved_at": None,
    }
    result = db().table("incidents").insert(payload).execute()
    return result.data[0]


async def resolve_incident(incident_id: str) -> None:
    db().table("incidents").update(
        {"resolved_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", incident_id).execute()


async def get_incident_history(*, days: int = 30) -> list[dict[str, Any]]:
    result = (
        db().table("incidents").select("*").order("opened_at", desc=True).limit(200).execute()
    )
    return result.data


async def get_all_open_incidents() -> list[dict[str, Any]]:
    result = (
        db()
        .table("incidents")
        .select("*")
        .is_("resolved_at", "null")
        .order("opened_at", desc=True)
        .execute()
    )
    return result.data


async def get_recent_incidents(*, limit: int = 10) -> list[dict[str, Any]]:
    result = (
        db()
        .table("incidents")
        .select("*")
        .order("opened_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data
