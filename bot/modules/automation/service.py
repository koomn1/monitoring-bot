"""
bot/modules/automation/service.py — Automation

Entry points invoked by bot/core/scheduler.py on a recurring basis.
Composes the monitor modules, backup module, reports module, and
operational anomaly detection into scheduled jobs. Each function here
MUST catch its own exceptions — scheduled jobs must never crash the
scheduler.

See: modules/20-automation.md
"""

from __future__ import annotations

import asyncio
import logging
import time

from bot.core.exceptions import ConfigurationError
from bot.modules.api_monitor import service as api_monitor
from bot.modules.backup import service as backup_service
from bot.modules.database_monitor import service as database_monitor
from bot.modules.notifications import service as notifications_service
from bot.modules.realtime_monitor import service as realtime_monitor
from bot.modules.reports import service as reports_service
from bot.modules.storage_monitor import service as storage_monitor
from bot.modules.website_monitor import service as website_monitor

logger = logging.getLogger("automation")

_ALERT_COOLDOWN_SECONDS = 3600.0
_last_alert_sent: dict[str, float] = {}


def _can_send_alert(key: str, *, cooldown_seconds: float = _ALERT_COOLDOWN_SECONDS) -> bool:
    now = time.monotonic()
    prev = _last_alert_sent.get(key)
    if prev is not None and (now - prev) < cooldown_seconds:
        return False
    _last_alert_sent[key] = now
    return True


async def _get_threshold_ms(key: str) -> int | None:
    from bot.db.repositories.config_repo import get_setting

    try:
        val = await get_setting(key)
        if isinstance(val, int) and val > 0:
            return val
    except Exception:  # noqa: BLE001
        return None
    return None


async def _check_latency_warnings(website_res: object, api_res: object) -> None:
    checks = [
        ("website", website_res, "website_latency_warn_ms"),
        ("api", api_res, "api_latency_warn_ms"),
    ]
    for service_name, res, setting_key in checks:
        if not isinstance(res, dict) or res.get("status") != "up":
            continue
        latency_ms = res.get("latency_ms")
        if not isinstance(latency_ms, int):
            continue
        threshold = await _get_threshold_ms(setting_key)
        if threshold and latency_ms > threshold and _can_send_alert(f"latency:{service_name}"):
            try:
                await notifications_service.notify_latency_warning(service_name, latency_ms, threshold)
            except Exception:  # noqa: BLE001
                logger.exception("Failed sending latency warning for %s", service_name)


async def run_health_checks() -> None:
    """Automatic Health Checks — runs all monitors concurrently."""
    checks = [
        website_monitor.check_website(),
        api_monitor.check_api(),
        database_monitor.check_database(),
        storage_monitor.check_storage(),
        realtime_monitor.check_realtime(),
    ]
    results = await asyncio.gather(*checks, return_exceptions=True)
    for idx, result in enumerate(results):
        if isinstance(result, ConfigurationError):
            logger.debug("Optional monitor skipped: %s", result)
        elif isinstance(result, Exception):
            logger.error("Health check #%d failed: %s", idx, result)

    await _check_latency_warnings(results[0], results[1])


async def run_operational_alerts() -> None:
    """Detects AI error spikes and stuck extraction jobs without spamming."""
    from bot.modules.platform_insights import service as insights_service

    try:
        health = await insights_service.get_ai_and_extraction_health(hours=1)
        ai = health.get("ai") or {}
        total_calls = ai.get("total_calls") or 0
        error_count = ai.get("error_count") or 0
        if total_calls >= 5:
            error_rate = (error_count / total_calls) * 100.0
            if error_rate >= 30.0 and _can_send_alert("ai_error_spike"):
                await notifications_service.notify_operational_alert(
                    "AI Error Rate Spike (1h)",
                    f"{error_count}/{total_calls} AI calls failed ({error_rate:.1f}% errors).",
                )

        extraction = health.get("extraction") or {}
        stuck_jobs = extraction.get("stuck_jobs") or []
        if stuck_jobs and _can_send_alert("stuck_extraction_jobs"):
            await notifications_service.notify_operational_alert(
                "Stuck Extraction Jobs Detected",
                f"{len(stuck_jobs)} extraction job(s) have been processing for >20m.",
            )
    except Exception:  # noqa: BLE001
        logger.exception("Operational alert scan failed")


async def run_scheduled_backup() -> None:
    """Automatic Backup — daily (or as configured via BACKUP_CRON)."""
    try:
        await backup_service.trigger_backup(confirmed=True)
    except Exception:
        logger.exception("Scheduled backup failed to trigger")


async def run_daily_report() -> None:
    try:
        content = await reports_service.generate_daily_report()
        try:
            await notifications_service.notify_scheduled_report(content)
        except Exception:  # noqa: BLE001
            logger.exception("Failed delivering daily report notification")
    except Exception:
        logger.exception("Daily report generation failed")


async def run_weekly_report() -> None:
    try:
        content = await reports_service.generate_weekly_report()
        try:
            await notifications_service.notify_scheduled_report(content)
        except Exception:  # noqa: BLE001
            logger.exception("Failed delivering weekly report notification")
    except Exception:
        logger.exception("Weekly report generation failed")


async def run_monthly_report() -> None:
    try:
        content = await reports_service.generate_monthly_report()
        try:
            await notifications_service.notify_scheduled_report(content)
        except Exception:  # noqa: BLE001
            logger.exception("Failed delivering monthly report notification")
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

    try:
        summary = await github_service.get_security_alerts_summary()
        critical = summary["by_severity"].get("critical", 0)
        if critical:
            await notifications_service.notify_security_alert(
                f"{critical} critical Dependabot alert(s) open."
            )
    except ConfigurationError:
        logger.debug("Security scan skipped: GitHub not configured")
    except Exception:  # noqa: BLE001
        logger.exception("Security scan failed")
