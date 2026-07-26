"""
bot/modules/reports/service.py — Reports Module

Generates and persists periodic reports (daily/weekly/monthly) plus
on-demand category reports (performance, database, infrastructure,
deployment, analytics, security). Invoked by bot/modules/automation for
schedules, and directly by /reports for on-demand generation.

See: modules/16-reports-module.md
"""

from __future__ import annotations

from typing import Any

from bot.db.repositories.reports_repo import get_latest_report, save_report
from bot.modules.analytics import service as analytics_service
from bot.modules.security import service as security_service


async def _generate_period_report(*, report_type: str, period: str, title: str) -> str:
    """Shared aggregation logic for daily/weekly/monthly reports — they
    differ only in the analytics period and label, not in structure."""
    analytics = await analytics_service.get_analytics_summary(period)
    security = await security_service.get_security_overview()

    content = (
        f"📊 <b>{title} — Quiz Space</b>\n"
        f"Errors ({period}): {analytics.get('error_count', 'N/A')}\n"
        f"Open security alerts: {security['dependabot'].get('total_open', 'N/A')}\n"
    )
    await save_report(
        report_type=report_type, content=content, metadata={"analytics": analytics, "security": security}
    )
    return content


async def generate_daily_report() -> str:
    return await _generate_period_report(report_type="daily", period="24h", title="Daily Report")


async def generate_weekly_report() -> str:
    return await _generate_period_report(report_type="weekly", period="7d", title="Weekly Report")


async def generate_monthly_report() -> str:
    return await _generate_period_report(report_type="monthly", period="30d", title="Monthly Report")


async def get_report(report_type: str) -> dict[str, Any] | None:
    return await get_latest_report(report_type)
