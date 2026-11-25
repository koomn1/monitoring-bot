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

    lines.append("<b>المستخدمون والاشتراكات</b>")
    lines.append(
        f"• الإجمالي: {_fmt(users.get('total'))} | بريميوم: {_fmt(users.get('premium'))} | "
        f"جدد ({period}): {_fmt(users.get('signups_recent'))}"
    )
    lines.append(
        f"• الجلسات النشطة (24س): {_fmt(users.get('active_24h'))} | "
        f"مدفوعات معلّقة: {_fmt(payments.get('pending_count'))}"
    )

    lines.append("")
    lines.append("<b>نشاط الاختبارات</b>")
    lines.append(
        f"• الاختبارات: {_fmt(activity.get('total_quizzes'))} (+{_fmt(activity.get('quizzes_recent'))} جديد) | "
        f"الفصول: {_fmt(activity.get('total_classrooms'))}"
    )
    lines.append(
        f"• الإكمالات ({period}): {_fmt(activity.get('completions_recent'))} | "
        f"محاولات الضيوف: {_fmt(activity.get('guest_attempts_recent'))} | "
        f"متوسط الدرجات: {_fmt(activity.get('avg_score_pct'), '%')}"
    )

    lines.append("")
    lines.append("<b>الذكاء الاصطناعي والاستخراج</b>")
    lines.append(
        f"• طلبات الذكاء ({period}): {_fmt(ai.get('total_calls'))} | "
        f"النجاح: {_fmt(ai.get('success_rate_pct'), '%')} | "
        f"المتوسط/P95: {_fmt(ai.get('avg_latency_ms'), 'ms')} / {_fmt(ai.get('p95_latency_ms'), 'ms')}"
    )
    lines.append(
        f"• مهام الاستخراج: مكتملة={_fmt(extraction.get('complete_recent'))}, "
        f"أخطاء={_fmt(extraction.get('error_recent'))}, "
        f"نشطة={(_fmt((extraction.get('pending_count') or 0) + (extraction.get('processing_count') or 0)))}, "
        f"عالقة={len(extraction.get('stuck_jobs') or [])}"
    )

    if services:
        lines.append("")
        lines.append("<b>توفر الخدمات</b>")
        for svc_name, stats in sorted(services.items()):
            lines.append(
                f"• {html.escape(svc_name)}: {_fmt(stats.get('uptime_pct'), '%')} "
                f"({stats.get('checks', 0)} فحص، متوسط {_fmt(stats.get('avg_latency_ms'), 'ms')})"
            )

    lines.append("")
    lines.append("<b>الأخطاء والأمان</b>")
    lines.append(f"• الحوادث المفتوحة: {len(open_incidents)}")
    lines.append(f"• الأخطاء ({period}): {_fmt(analytics.get('error_count'))}")
    lines.append(
        f"• تنبيهات الأمان المفتوحة: {_fmt((security.get('dependabot') or {}).get('total_open'))} | "
        f"محاولات غير مصرح بها: {security.get('recent_unauthorized_attempts', 0)}"
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
    lines = ["⚡ <b>تقرير الأداء — Quiz Space (24س)</b>", ""]

    if services:
        lines.append("<b>سرعة الاستجابة للخادم والخدمات</b>")
        for svc_name, stats in sorted(services.items()):
            lines.append(
                f"• {html.escape(svc_name)}: متوسط {_fmt(stats.get('avg_latency_ms'), 'ms')} | "
                f"التوفر {_fmt(stats.get('uptime_pct'), '%')}"
            )
        lines.append("")

    lines.append("<b>أداء خط الذكاء الاصطناعي</b>")
    lines.append(
        f"• الطلبات: {_fmt(ai.get('total_calls'))} | النجاح: {_fmt(ai.get('success_rate_pct'), '%')} | "
        f"المتوسط: {_fmt(ai.get('avg_latency_ms'), 'ms')} | P95: {_fmt(ai.get('p95_latency_ms'), 'ms')}"
    )

    if vitals:
        lines.append("")
        lines.append("<b>مؤشرات الواجهة الأمامية Web Vitals (p75)</b>")
        for metric, stats in sorted(vitals.items()):
            unit = "" if metric == "CLS" else "ms"
            lines.append(f"• {html.escape(metric)}: p75={stats['p75']}{unit} (متوسط={stats['avg']}{unit}, عينة={stats['samples']})")
    else:
        lines.append("\n• مؤشرات الأداء: لا توجد عينات خلال آخر 24 ساعة.")

    content = "\n".join(lines)
    await save_report(
        report_type="performance",
        content=content,
        metadata={"vitals": vitals, "ai": ai_ext, "uptime": uptime},
    )
    return content


async def generate_daily_report() -> str:
    return await _generate_period_report(report_type="daily", period="24h", title="التقرير اليومي")


async def generate_weekly_report() -> str:
    return await _generate_period_report(report_type="weekly", period="7d", title="التقرير الأسبوعي")


async def generate_monthly_report() -> str:
    return await _generate_period_report(report_type="monthly", period="30d", title="التقرير الشهري")


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
