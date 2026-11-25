"""
bot/modules/reports/service.py — Reports Module

Generates and persists periodic reports (daily/weekly/monthly) plus
on-demand category reports (performance, database, infrastructure,
deployment, analytics, security). Invoked by bot/modules/automation for
schedules, and directly by /reports for on-demand generation.

See: modules/16-reports-module.md
"""

from __future__ import annotations

import html
import logging
from typing import Any

from bot.core.exceptions import ConfigurationError
from bot.db.repositories.reports_repo import get_latest_report, save_report
from bot.modules.analytics import service as analytics_service
from bot.modules.platform_insights import service as insights_service
from bot.modules.security import service as security_service

logger = logging.getLogger("modules.reports")


def _fmt(val: Any, suffix: str = "") -> str:
    if val is None:
        return "N/A"
    return f"{val}{suffix}"


async def _safe_security_overview() -> dict[str, Any]:
    try:
        return await security_service.get_security_overview()
    except ConfigurationError as exc:
        return {"dependabot": {"total_open": None, "note": str(exc)}, "recent_unauthorized_attempts": 0}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Security overview degraded in report: %s", exc)
        return {"dependabot": {"total_open": None}, "recent_unauthorized_attempts": 0}


async def _generate_period_report(*, report_type: str, period: str, title: str) -> str:
    """Shared aggregation logic for daily/weekly/monthly reports."""
    hours = analytics_service._period_to_hours(period)  # noqa: SLF001
    analytics = await analytics_service.get_analytics_summary(period)
    uptime_data = await insights_service.get_uptime_and_incidents(hours=hours)
    security = await _safe_security_overview()

    pulse = analytics.get("pulse") or {}
    users = pulse.get("users") or {}
    activity = pulse.get("activity") or {}
    ai = pulse.get("ai") or {}
    extraction = pulse.get("extraction") or {}
    payments = pulse.get("payments") or {}
    services = uptime_data.get("services") or {}
    open_incidents = uptime_data.get("open_incidents") or []

    lines = [f"📊 <b>{html.escape(title)} — Quiz Space ({html.escape(period)})</b>", ""]

    lines.append("<b>Users &amp; Subscriptions</b>")
    lines.append(
        f"• Total: {_fmt(users.get('total'))} | Premium: {_fmt(users.get('premium'))} | "
        f"New ({period}): {_fmt(users.get('signups_recent'))}"
    )
    lines.append(
        f"• Active sessions (24h): {_fmt(users.get('active_24h'))} | "
        f"Pending payments: {_fmt(payments.get('pending_count'))}"
    )

    lines.append("")
    lines.append("<b>Quiz Activity</b>")
    lines.append(
        f"• Quizzes: {_fmt(activity.get('total_quizzes'))} (+{_fmt(activity.get('quizzes_recent'))} new) | "
        f"Classrooms: {_fmt(activity.get('total_classrooms'))}"
    )
    lines.append(
        f"• Completions ({period}): {_fmt(activity.get('completions_recent'))} | "
        f"Guest attempts: {_fmt(activity.get('guest_attempts_recent'))} | "
        f"Avg score: {_fmt(activity.get('avg_score_pct'), '%')}"
    )

    lines.append("")
    lines.append("<b>AI &amp; Extraction</b>")
    lines.append(
        f"• AI calls ({period}): {_fmt(ai.get('total_calls'))} | "
        f"Success: {_fmt(ai.get('success_rate_pct'), '%')} | "
        f"Avg/P95: {_fmt(ai.get('avg_latency_ms'), 'ms')} / {_fmt(ai.get('p95_latency_ms'), 'ms')}"
    )
    lines.append(
        f"• Extraction jobs: complete={_fmt(extraction.get('complete_recent'))}, "
        f"errors={_fmt(extraction.get('error_recent'))}, "
        f"active={(_fmt((extraction.get('pending_count') or 0) + (extraction.get('processing_count') or 0)))}, "
        f"stuck={len(extraction.get('stuck_jobs') or [])}"
    )

    if services:
        lines.append("")
        lines.append("<b>Service Uptime</b>")
        for svc_name, stats in sorted(services.items()):
            lines.append(
                f"• {html.escape(svc_name)}: {_fmt(stats.get('uptime_pct'), '%')} "
                f"({stats.get('checks', 0)} checks, avg {_fmt(stats.get('avg_latency_ms'), 'ms')})"
            )

    lines.append("")
    lines.append("<b>Errors &amp; Security</b>")
    lines.append(f"• Open incidents: {len(open_incidents)}")
    lines.append(f"• Errors ({period}): {_fmt(analytics.get('error_count'))}")
    lines.append(
        f"• Open security alerts: {_fmt((security.get('dependabot') or {}).get('total_open'))} | "
        f"Unauthorized attempts: {security.get('recent_unauthorized_attempts', 0)}"
    )

    content = "\n".join(lines)
    await save_report(
        report_type=report_type,
        content=content,
        metadata={"analytics": analytics, "uptime": uptime_data, "security": security},
    )
    return content


async def generate_performance_report() -> str:
    vitals = await insights_service.get_web_vitals_overview(hours=24)
    ai_ext = await insights_service.get_ai_and_extraction_health(hours=24)
    uptime = await insights_service.get_uptime_and_incidents(hours=24)

    ai = ai_ext.get("ai") or {}
    services = uptime.get("services") or {}
    lines = ["⚡ <b>Performance Report — Quiz Space (24h)</b>", ""]

    if services:
        lines.append("<b>Backend &amp; Endpoint Latency</b>")
        for svc_name, stats in sorted(services.items()):
            lines.append(
                f"• {html.escape(svc_name)}: avg {_fmt(stats.get('avg_latency_ms'), 'ms')} | "
                f"uptime {_fmt(stats.get('uptime_pct'), '%')}"
            )
        lines.append("")

    lines.append("<b>AI Pipeline Latency</b>")
    lines.append(
        f"• Calls: {_fmt(ai.get('total_calls'))} | Success: {_fmt(ai.get('success_rate_pct'), '%')} | "
        f"Avg: {_fmt(ai.get('avg_latency_ms'), 'ms')} | P95: {_fmt(ai.get('p95_latency_ms'), 'ms')}"
    )

    if vitals:
        lines.append("")
        lines.append("<b>Frontend Web Vitals (p75)</b>")
        for metric, stats in sorted(vitals.items()):
            unit = "" if metric == "CLS" else "ms"
            lines.append(f"• {html.escape(metric)}: p75={stats['p75']}{unit} (avg={stats['avg']}{unit}, n={stats['samples']})")
    else:
        lines.append("\n• Web Vitals: No samples in last 24h.")

    content = "\n".join(lines)
    await save_report(
        report_type="performance",
        content=content,
        metadata={"vitals": vitals, "ai": ai_ext, "uptime": uptime},
    )
    return content


async def generate_daily_report() -> str:
    return await _generate_period_report(report_type="daily", period="24h", title="Daily Report")


async def generate_weekly_report() -> str:
    return await _generate_period_report(report_type="weekly", period="7d", title="Weekly Report")


async def generate_monthly_report() -> str:
    return await _generate_period_report(report_type="monthly", period="30d", title="Monthly Report")


_GENERATORS = {
    "daily": generate_daily_report,
    "weekly": generate_weekly_report,
    "monthly": generate_monthly_report,
    "performance": generate_performance_report,
}


async def get_report(report_type: str, *, refresh: bool = False) -> dict[str, Any] | None:
    if not refresh:
        existing = await get_latest_report(report_type)
        if existing is not None:
            return existing
    generator = _GENERATORS.get(report_type)
    if generator is None:
        return None
    content = await generator()
    return {"report_type": report_type, "content": content}
