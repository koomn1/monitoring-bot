"""
bot/modules/automation/service.py — Automation

Entry points invoked by bot/core/scheduler.py on a recurring basis.
Composes the monitor modules, backup module, and reports module into
scheduled jobs. Each function here MUST catch its own exceptions —
scheduled jobs must never crash the scheduler.

See: modules/20-automation.md
"""

from __future__ import annotations

import asyncio
import logging

from bot.modules.api_monitor import service as api_monitor
from bot.modules.backup import service as backup_service
from bot.modules.database_monitor import service as database_monitor
from bot.modules.reports import service as reports_service
from bot.modules.storage_monitor import service as storage_monitor
from bot.modules.website_monitor import service as website_monitor

logger = logging.getLogger("automation")


async def run_health_checks() -> None:
    """Automatic Health Checks — runs all monitors concurrently."""
    checks = [
        website_monitor.check_website(),
        api_monitor.check_api(),
        database_monitor.check_database(),
        storage_monitor.check_storage(),
    ]
    results = await asyncio.gather(*checks, return_exceptions=True)
    for check, result in zip(checks, results):
        if isinstance(result, Exception):
            logger.error("Health check failed: %s", result)


async def run_scheduled_backup() -> None:
    """Automatic Backup — daily (or as configured via BACKUP_CRON)."""
    try:
        await backup_service.trigger_backup(confirmed=True)
    except Exception:
        logger.exception("Scheduled backup failed to trigger")


async def run_daily_report() -> None:
    try:
        await reports_service.generate_daily_report()
    except Exception:
        logger.exception("Daily report generation failed")


async def run_weekly_report() -> None:
    try:
        await reports_service.generate_weekly_report()
    except Exception:
        logger.exception("Weekly report generation failed")


async def run_monthly_report() -> None:
    try:
        await reports_service.generate_monthly_report()
    except Exception:
        logger.exception("Monthly report generation failed")


async def run_cleanup() -> None:
    """Automatic Cleanup — prunes audit_logs/monitoring_logs rows older
    than the retention window via the cleanup_old_logs SQL function
    (bot/db/migrations/0003_functions.sql)."""
    from bot.db.repositories.logs_repo import cleanup_old_logs

    try:
        await cleanup_old_logs(retention_days=90)
    except Exception:
        logger.exception("Log cleanup failed")


async def run_security_scan() -> None:
    """Automatic Security Scan — re-checks Dependabot alerts and flags new
    high/critical severities via notifications."""
    from bot.modules.github import service as github_service
    from bot.modules.notifications import service as notifications_service

    summary = await github_service.get_security_alerts_summary()
    critical = summary["by_severity"].get("critical", 0)
    if critical:
        await notifications_service.notify_security_alert(f"{critical} critical Dependabot alert(s) open.")
