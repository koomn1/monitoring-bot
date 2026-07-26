"""
bot/db/repositories/reports_repo.py

Data access layer for the `reports` table — stores generated report
payloads (daily/weekly/monthly/performance/security/etc.) so they can be
re-sent, compared over time, or reviewed via /reports.

See: modules/16-reports-module.md, database/02-tables.md
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bot.db.client import db


async def save_report(*, report_type: str, content: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "report_type": report_type,
        "content": content,
        "metadata": metadata or {},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    result = db().table("reports").insert(payload).execute()
    return result.data[0]


async def get_latest_report(report_type: str) -> dict[str, Any] | None:
    result = (
        db()
        .table("reports")
        .select("*")
        .eq("report_type", report_type)
        .order("generated_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


async def list_reports(report_type: str, *, limit: int = 10) -> list[dict[str, Any]]:
    result = (
        db()
        .table("reports")
        .select("*")
        .eq("report_type", report_type)
        .order("generated_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data
