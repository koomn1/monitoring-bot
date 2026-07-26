"""
bot/modules/logging/service.py — Logging Module

Read-side of the audit/monitoring log system (write-side lives directly
in bot/db/repositories/logs_repo.py, called from middleware and monitor
modules). This service formats log data for /logs and /errors.

See: modules/15-logging-module.md
"""

from __future__ import annotations

from typing import Any

from bot.db.repositories.logs_repo import get_monitoring_history, get_recent_logs


async def get_recent_command_logs(limit: int = 20) -> list[dict[str, Any]]:
    return await get_recent_logs(limit=limit)


async def get_service_history(service: str, hours: int = 24) -> list[dict[str, Any]]:
    return await get_monitoring_history(service, hours=hours)
