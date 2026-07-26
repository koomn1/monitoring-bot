"""
bot/core/scheduler.py

Internal job scheduler, wrapping APScheduler. Responsible for running all
recurring automation: health checks, reports, backups, cleanup, security
scans. Complements (does not replace) the GitHub Actions-based scheduled
workflows described in workflows/ — this scheduler is for in-process jobs
when the Bot runs as a long-lived worker; GitHub Actions cron is preferred
for jobs that should run even if the Bot process is down (see
docs/08-free-infrastructure.md for the tradeoffs).

See: modules/20-automation.md
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger("bot.scheduler")

_scheduler = AsyncIOScheduler()

JobFn = Callable[[], Awaitable[None]]


def schedule_interval(job: JobFn, *, seconds: int, job_id: str) -> None:
    _scheduler.add_job(
        job,
        trigger=IntervalTrigger(seconds=seconds),
        id=job_id,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    logger.info("Scheduled interval job '%s' every %ss", job_id, seconds)


def schedule_cron(job: JobFn, *, cron_expression: str, job_id: str) -> None:
    """cron_expression uses standard 5-field cron syntax, e.g. '0 3 * * *'."""
    trigger = CronTrigger.from_crontab(cron_expression)
    _scheduler.add_job(
        job,
        trigger=trigger,
        id=job_id,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    logger.info("Scheduled cron job '%s' (%s)", job_id, cron_expression)


def start() -> None:
    if not _scheduler.running:
        _scheduler.start()
        logger.info("Scheduler started with %d jobs", len(_scheduler.get_jobs()))


def shutdown() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


def register_all_jobs() -> None:
    """
    Called once at startup (bot/main.py). Registers every recurring job
    from bot/modules/automation/service.py. Kept as a single function so
    startup order is explicit and easy to audit.
    """
    from bot.config import settings
    from bot.modules.automation import service as automation_service

    schedule_interval(
        automation_service.run_health_checks,
        seconds=settings.health_check_interval_seconds,
        job_id="automation.health_checks",
    )
    schedule_cron(
        automation_service.run_scheduled_backup,
        cron_expression=settings.backup_cron,
        job_id="automation.backup",
    )
    schedule_cron(
        automation_service.run_daily_report,
        cron_expression=settings.daily_report_cron,
        job_id="automation.daily_report",
    )
    schedule_cron(
        automation_service.run_weekly_report,
        cron_expression=settings.weekly_report_cron,
        job_id="automation.weekly_report",
    )
    schedule_cron(
        automation_service.run_monthly_report,
        cron_expression=settings.monthly_report_cron,
        job_id="automation.monthly_report",
    )
    schedule_cron(
        automation_service.run_cleanup,
        cron_expression="0 4 * * *",  # nightly, after the backup window
        job_id="automation.cleanup",
    )
