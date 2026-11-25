"""
bot/modules/platform_insights/service.py

Domain service aggregating Quiz Space application telemetry (users,
quizzes, completions, AI pipeline health, extraction jobs, pending
payments, web vitals, uptime & incidents) for /pulse, /ai, /payments,
/incidents, /dashboard, /reports, and the AI assistant.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from bot.db.repositories import incidents_repo, logs_repo, platform_repo, users_repo

logger = logging.getLogger("modules.platform_insights")


async def _safe(coro: Any, default: Any) -> Any:
    try:
        return await coro
    except Exception as exc:  # noqa: BLE001
        logger.warning("Telemetry subtask degraded: %s", exc)
        return default


async def get_live_pulse(*, hours: int = 24) -> dict[str, Any]:
    cutoff_recent = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    (
        total_users,
        premium_users,
        signups_recent,
        sessions,
        quiz_activity,
        payments,
        ai_health,
        extraction_jobs,
        open_incidents,
    ) = await asyncio.gather(
        _safe(users_repo.get_quiz_space_user_count(), None),
        _safe(users_repo.get_premium_user_count(), None),
        _safe(users_repo.get_signups_count_since(cutoff_recent), None),
        _safe(platform_repo.get_active_sessions_summary(), {}),
        _safe(platform_repo.get_quiz_activity_summary(hours=hours), {}),
        _safe(platform_repo.get_payment_requests_summary(limit=5), {}),
        _safe(platform_repo.get_ai_health_summary(hours=hours, error_limit=3), {}),
        _safe(platform_repo.get_extraction_jobs_summary(hours=hours), {}),
        _safe(incidents_repo.get_all_open_incidents(), []),
    )

    return {
        "hours": hours,
        "users": {
            "total": total_users,
            "premium": premium_users,
            "signups_recent": signups_recent,
            "active_1h": sessions.get("active_1h"),
            "active_24h": sessions.get("active_24h"),
        },
        "activity": quiz_activity,
        "payments": payments,
        "ai": ai_health,
        "extraction": extraction_jobs,
        "open_incidents": open_incidents,
    }


async def get_ai_and_extraction_health(*, hours: int = 24) -> dict[str, Any]:
    ai_health, extraction_jobs = await asyncio.gather(
        _safe(platform_repo.get_ai_health_summary(hours=hours, error_limit=5), {"available": False}),
        _safe(platform_repo.get_extraction_jobs_summary(hours=hours), {"available": False}),
    )
    return {"hours": hours, "ai": ai_health, "extraction": extraction_jobs}


async def get_pending_payments(*, limit: int = 10) -> dict[str, Any]:
    return await _safe(platform_repo.get_payment_requests_summary(limit=limit), {})


async def get_uptime_and_incidents(*, hours: int = 24) -> dict[str, Any]:
    service_stats, open_incidents, recent_incidents = await asyncio.gather(
        _safe(logs_repo.get_service_stats(hours=hours), {}),
        _safe(incidents_repo.get_all_open_incidents(), []),
        _safe(incidents_repo.get_recent_incidents(limit=10), []),
    )
    return {
        "hours": hours,
        "services": service_stats,
        "open_incidents": open_incidents,
        "recent_incidents": recent_incidents,
    }


async def get_database_overview() -> dict[str, Any]:
    counts, db_stats = await asyncio.gather(
        _safe(platform_repo.get_core_table_counts(), {}),
        _safe(logs_repo.get_service_stats(hours=24), {}),
    )
    return {"table_counts": counts, "db_stats_24h": db_stats.get("database", {})}


async def get_web_vitals_overview(*, hours: int = 24) -> dict[str, Any]:
    return await _safe(platform_repo.get_web_vitals_summary(hours=hours), {})


async def get_detailed_errors_report(*, hours: int = 24) -> dict[str, Any]:
    ai_health, extraction, failed_checks, failed_commands, open_incidents = await asyncio.gather(
        _safe(platform_repo.get_ai_health_summary(hours=hours, error_limit=10), {}),
        _safe(platform_repo.get_extraction_jobs_summary(hours=hours), {}),
        _safe(logs_repo.get_recent_failed_checks(hours=hours, limit=10), []),
        _safe(logs_repo.get_recent_failed_commands(limit=10), []),
        _safe(incidents_repo.get_all_open_incidents(), []),
    )
    return {
        "hours": hours,
        "ai": ai_health,
        "extraction": extraction,
        "failed_checks": failed_checks,
        "failed_commands": failed_commands,
        "open_incidents": open_incidents,
    }
