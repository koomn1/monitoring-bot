"""
bot/modules/telegram_commands/handlers.py — Telegram Commands

Registers every /command with bot/core/router.py via the @command
decorator. This file contains NO direct DB/integration HTTP logic itself —
every handler is a thin adapter calling module services and formatting
rich, scannable Telegram HTML output.

See: modules/17-telegram-commands.md
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from typing import Any

from bot.core.exceptions import ConfigurationError
from bot.core.router import CommandContext, command, registered_commands
from bot.utils.formatting import format_table, status_line
from bot.utils.keyboards import cmd_button, set_reply_buttons
from bot.utils.style import title
from bot.utils.time_utils import humanize_delta


def _esc(value: Any, max_len: int = 80) -> str:
    if value is None:
        return "غير متاح"
    return html.escape(str(value).strip()[:max_len], quote=False)


def _fmt(value: Any, suffix: str = "") -> str:
    if value is None:
        return "غير متاح"
    return f"{value}{suffix}"


def _age(iso_value: Any) -> str:
    if not isinstance(iso_value, str) or not iso_value.strip():
        return "غير معروف"
    try:
        dt = datetime.fromisoformat(iso_value.strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return humanize_delta(dt)
    except ValueError:
        return "غير معروف"


def _parse_hours_arg(args: list[str], default_hours: int = 24) -> tuple[int, str]:
    if not args:
        return default_hours, f"{default_hours}h"
    raw = args[0].strip().lower()
    if raw.endswith("d") and raw[:-1].isdigit():
        days = max(1, min(90, int(raw[:-1])))
        return days * 24, f"{days}d"
    if raw.endswith("h") and raw[:-1].isdigit():
        hours = max(1, min(720, int(raw[:-1])))
        return hours, f"{hours}h"
    return default_hours, f"{default_hours}h"


# --- General ------------------------------------------------------------

@command("start")
async def handle_start(ctx: CommandContext) -> str:
    from bot.modules.auth import service as auth_service

    await auth_service.authenticate(ctx.user_id, username=None)
    return (
        f"{title('لوحة إدارة ومراقبة Quiz Space', 'wave')}\n\n"
        "مراقبة حية، إدارة المستخدمين والعضويات، مراجعة المدفوعات والنقاط، "
        "تعديل الباقات والكوبونات، وتشخيص أخطاء الذكاء الاصطناعي بالكامل.\n\n"
        "استخدم الأزرار بالأسفل أو أرسل /help لعرض جميع الأوامر."
    )


_HELP_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "المراقبة الحية والنبض",
        [
            ("status", "حالة الخدمات، الاتصال اللحظي والحوادث المفتوحة"),
            ("dashboard", "الملخص التنفيذي الشامل للمنصة"),
            ("pulse", "النشاط الحي (الجلسات، الإكمالات، أشهر الاختبارات)"),
            ("ai", "أداء الذكاء الاصطناعي وطابور مهام الاستخراج"),
            ("payments", "طلبات تفعيل الاشتراك والمدفوعات المعلّقة"),
            ("incidents", "الحوادث المفتوحة والسابقة ونسب التشغيل 24س"),
        ],
    ),
    (
        "إدارة المستخدمين والعضويات والنقاط",
        [
            ("users", "نمو المستخدمين، نسبة البريميوم وأحدث المسجلين"),
            ("user", "ملف المستخدم الكامل: الباقة، النقاط، السجل والطلبات"),
            ("edituser", "تعديل بيانات المستخدم (الاسم، اللون، الصلاحية، XP) — المالك"),
            ("approve", "الموافقة على طلب دفع وتفعيل الاشتراك (المالك)"),
            ("reject", "رفض طلب دفع مع ذكر السبب (المالك)"),
            ("membership", "تغيير باقة المستخدم (free/silver/gold/diamond/lifetime/founder)"),
            ("suspend", "إيقاف أو تفعيل حساب مستخدم (المالك)"),
            ("setbadge", "تغيير شارة المستخدم badge_tier (المالك)"),
            ("points", "متصدرو النقاط أو تفاصيل رصيد وسجل مستخدم"),
            ("grantpoints", "إضافة أو خصم نقاط لمستخدم (المالك)"),
            ("orders", "طابور طلبات متجر المكافآت"),
            ("approveorder", "الموافقة على طلب متجر وإضافة النقاط (المالك)"),
            ("rejectorder", "رفض طلب متجر المكافآت (المالك)"),
        ],
    ),
    (
        "إدارة الموقع والباقات والكوبونات",
        [
            ("plans", "عرض جميع باقات الاشتراك وأسعارها"),
            ("editplan", "تعديل سعر أو اسم أو حالة باقة اشتراك (المالك)"),
            ("platform", "عرض/تعديل وضع الصيانة وفتح التسجيل (المالك)"),
            ("trial", "عرض/تفعيل عروض التجربة المجانية 7/14/30 يوم (المالك)"),
            ("coupon", "عرض/إنشاء/تفعيل/حذف كوبونات الخصم (المالك)"),
            ("notify", "إرسال إشعار داخل الموقع لمستخدم أو للجميع (المالك)"),
            ("quizzes", "عرض أحدث الاختبارات في المنصة"),
            ("deletequiz", "حذف اختبار من المنصة (المالك)"),
            ("vitals", "تقرير مؤشرات الأداء Web Vitals"),
            ("topusers", "قائمة المتصدرين حسب XP أو النقاط"),
        ],
    ),
    (
        "التحليلات والمساعد الذكي",
        [
            ("analytics", "تحليلات المنصة ومؤشرات الأداء والزيارات"),
            ("reports", "التقارير الدورية والأداء (daily/weekly/monthly/performance)"),
            ("ask", "اسأل المساعد الذكي عن حالة المنصة والأرقام الحالية"),
        ],
    ),
    (
        "البنية التحتية والأمان",
        [
            ("database", "صحة قاعدة البيانات، نسبة التشغيل وعدد الصفوف"),
            ("storage", "حاويات التخزين وعدد الملفات"),
            ("system", "حالة GitHub و Cloudflare Pages و Firebase"),
            ("errors", "تقرير الأخطاء الشامل (Sentry + AI + الاستخراج + الفحوصات)"),
            ("security", "تنبيهات Dependabot ومحاولات الوصول غير المصرح بها"),
            ("logs", "سجل تنفيذ أوامر البوت"),
        ],
    ),
    (
        "النشر والإعدادات",
        [
            ("deploy", "تشغيل نشر الإنتاج"),
            ("build", "تشغيل بناء المشروع"),
            ("rollback", "التراجع عن آخر نشر (المالك)"),
            ("backup", "إنشاء أو عرض النسخ الاحتياطية"),
            ("restore", "استعادة نسخة احتياطية (المالك)"),
            ("settings", "عرض/تعديل إعدادات البوت (المالك)"),
            ("envcheck", "فحص المفاتيح السرية والتكاملات (المالك)"),
            ("setrole", "منح صلاحية ADMIN أو VIEWER لمستخدم تليجرام (المالك)"),
        ],
    ),
]


@command("help")
async def handle_help(ctx: CommandContext) -> str:
    known = set(registered_commands())
    lines = [title("الأوامر المتاحة"), ""]
    seen: set[str] = set()
    for group_name, items in _HELP_GROUPS:
        present = [(cmd, desc) for cmd, desc in items if cmd in known]
        if not present:
            continue
        lines.append(f"<b>{group_name}</b>")
        for cmd, desc in present:
            lines.append(f"/{cmd} — {html.escape(desc)}")
            seen.add(cmd)
        lines.append("")
    leftover = sorted(known - seen - {"start", "help"})
    if leftover:
        lines.append("<b>أوامر أخرى</b>")
        lines.extend(f"/{c}" for c in leftover)
    return "\n".join(lines).strip()


# --- Monitoring -----------------------------------------------------------

@command("status")
async def handle_status(ctx: CommandContext) -> str:
    from bot.modules.api_monitor import service as api_monitor
    from bot.modules.database_monitor import service as database_monitor
    from bot.modules.platform_insights import service as insights_service
    from bot.modules.realtime_monitor import service as realtime_monitor
    from bot.modules.storage_monitor import service as storage_monitor
    from bot.modules.website_monitor import service as website_monitor

    async def check_optional_monitor(check):
        try:
            return await check()
        except ConfigurationError:
            return {"status": "not configured"}
        except Exception:  # noqa: BLE001
            return {"status": "unknown"}

    website = await check_optional_monitor(website_monitor.check_website)
    api = await check_optional_monitor(api_monitor.check_api)
    database = await database_monitor.check_database()
    storage = await storage_monitor.check_storage()
    realtime = await check_optional_monitor(realtime_monitor.check_realtime)

    lines = [
        title("Quiz Space — حالة النظام", "dashboard"),
        status_line(
            "الموقع",
            website["status"],
            f"{website['latency_ms']}ms" if website.get("latency_ms") is not None else "",
        ),
        status_line(
            "الـ API",
            api["status"],
            f"{api['latency_ms']}ms" if api.get("latency_ms") is not None else "",
        ),
        status_line("قاعدة البيانات", database["status"], f"{database.get('latency_ms', '?')}ms"),
        status_line("التخزين", storage["status"], f"{storage.get('bucket_count', 0)} حاوية"),
    ]

    if realtime.get("status") != "not configured":
        rt_extra = f"{realtime['latency_ms']}ms" if realtime.get("latency_ms") is not None else ""
        lines.append(status_line("الاتصال اللحظي", realtime["status"], rt_extra))

    try:
        uptime = await insights_service.get_uptime_and_incidents(hours=24)
        open_inc = uptime.get("open_incidents") or []
        services = uptime.get("services") or {}
        if services:
            uptime_parts = [
                f"{name}: {stats['uptime_pct']}%"
                for name, stats in sorted(services.items())
                if stats.get("uptime_pct") is not None
            ]
            if uptime_parts:
                lines.append("")
                lines.append("<b>نسبة التشغيل (24س):</b> " + " | ".join(uptime_parts))
        lines.append(f"🚨 الحوادث المفتوحة: {len(open_inc)}")
    except Exception:  # noqa: BLE001
        pass

    return "\n".join(lines)


@command("dashboard")
async def handle_dashboard(ctx: CommandContext) -> str:
    from bot.modules.analytics import service as analytics_service
    from bot.modules.deployment import service as deployment_service

    analytics = await analytics_service.get_analytics_summary()
    try:
        deployment = await deployment_service.get_deployment_status()
        deployment_status = deployment.get("conclusion") or deployment.get("status") or "غير معروف"
    except ConfigurationError as exc:
        deployment_status = f"غير مهيأ — {exc}"
    except Exception as exc:  # noqa: BLE001
        deployment_status = f"غير متاح ({_esc(exc, 60)})"

    error_count = analytics.get("error_count")
    lines = [
        title("Quiz Space — لوحة التحكم", "reports"),
        f"آخر نشر: {_esc(deployment_status)}",
        f"الأخطاء (24س): {error_count if error_count is not None else 'غير متاح'}",
    ]

    pulse = analytics.get("pulse") or {}
    users = pulse.get("users") or {}
    activity = pulse.get("activity") or {}
    ai = pulse.get("ai") or {}
    extraction = pulse.get("extraction") or {}
    payments = pulse.get("payments") or {}
    open_incidents = pulse.get("open_incidents") or []

    if users or activity or ai:
        lines.extend(
            [
                "",
                "<b>المستخدمون والجلسات</b>",
                f"• الإجمالي: {_fmt(users.get('total'))} | بريميوم: {_fmt(users.get('premium'))} | "
                f"جدد (24س): {_fmt(users.get('signups_recent'))}",
                f"• الجلسات النشطة: 1س={_fmt(users.get('active_1h'))} | 24س={_fmt(users.get('active_24h'))}",
                "",
                "<b>نشاط الاختبارات (24س)</b>",
                f"• الاختبارات: {_fmt(activity.get('total_quizzes'))} (+{_fmt(activity.get('quizzes_recent'))} جديد) | "
                f"الفصول: {_fmt(activity.get('total_classrooms'))}",
                f"• الإكمالات: {_fmt(activity.get('completions_recent'))} | "
                f"الضيوف: {_fmt(activity.get('guest_attempts_recent'))} | "
                f"متوسط الدرجة: {_fmt(activity.get('avg_score_pct'), '%')}",
                f"• محادثات Cosmo (24س): {_fmt(activity.get('cosmo_conversations_recent'))}",
                "",
                "<b>الذكاء الاصطناعي والاستخراج (24س)</b>",
                f"• طلبات الذكاء: {_fmt(ai.get('total_calls'))} | "
                f"النجاح: {_fmt(ai.get('success_rate_pct'), '%')} | "
                f"المتوسط/P95: {_fmt(ai.get('avg_latency_ms'), 'ms')} / {_fmt(ai.get('p95_latency_ms'), 'ms')}",
                f"• مهام الاستخراج: نشطة={_fmt((extraction.get('pending_count') or 0) + (extraction.get('processing_count') or 0))}, "
                f"مكتملة={_fmt(extraction.get('complete_recent'))}, أخطاء={_fmt(extraction.get('error_recent'))}, "
                f"عالقة={len(extraction.get('stuck_jobs') or [])}",
                "",
                "<b>العمليات</b>",
                f"• مدفوعات معلّقة: {_fmt(payments.get('pending_count'))} | "
                f"تحتاج بيانات: {_fmt(payments.get('needs_info_count'))} | "
                f"حوادث مفتوحة: {len(open_incidents)}",
            ]
        )

    return "\n".join(lines)


@command("pulse")
async def handle_pulse(ctx: CommandContext) -> str:
    from bot.modules.platform_insights import service as insights_service

    hours, label = _parse_hours_arg(ctx.args, default_hours=24)
    pulse = await insights_service.get_live_pulse(hours=hours)
    users = pulse.get("users") or {}
    activity = pulse.get("activity") or {}
    payments = pulse.get("payments") or {}
    ai = pulse.get("ai") or {}
    extraction = pulse.get("extraction") or {}
    open_incidents = pulse.get("open_incidents") or []

    lines = [
        f"⚡ <b>النبض الحي لـ Quiz Space ({label})</b>",
        "",
        "<b>الجمهور</b>",
        f"• المستخدمون: {_fmt(users.get('total'))} (بريميوم: {_fmt(users.get('premium'))})",
        f"• تسجيلات جديدة ({label}): {_fmt(users.get('signups_recent'))}",
        f"• الجلسات النشطة: 1س={_fmt(users.get('active_1h'))} | 24س={_fmt(users.get('active_24h'))}",
        "",
        "<b>التعلم والتفاعل</b>",
        f"• اختبارات منشأة ({label}): {_fmt(activity.get('quizzes_recent'))} (الإجمالي {_fmt(activity.get('total_quizzes'))})",
        f"• الإكمالات ({label}): {_fmt(activity.get('completions_recent'))} | متوسط الدرجة: {_fmt(activity.get('avg_score_pct'), '%')}",
        f"• محاولات الضيوف ({label}): {_fmt(activity.get('guest_attempts_recent'))}",
        f"• محادثات Cosmo ({label}): {_fmt(activity.get('cosmo_conversations_recent'))}",
    ]

    top_quizzes = activity.get("top_quizzes") or []
    if top_quizzes:
        lines.append("")
        lines.append("<b>أشهر الاختبارات (إجمالي التشغيل)</b>")
        for q in top_quizzes[:3]:
            lines.append(
                f"• {_esc(q.get('title'), 42)} — {q.get('total_plays', 0)} تشغيل"
            )

    lines.extend(
        [
            "",
            "<b>خط الذكاء والعمليات</b>",
            f"• الذكاء ({label}): {_fmt(ai.get('total_calls'))} طلب، "
            f"{_fmt(ai.get('success_rate_pct'), '%')} نجاح، "
            f"متوسط {_fmt(ai.get('avg_latency_ms'), 'ms')}",
            f"• طابور الاستخراج: قيد الانتظار={_fmt(extraction.get('pending_count'))}، "
            f"قيد المعالجة={_fmt(extraction.get('processing_count'))}، "
            f"عالقة={len(extraction.get('stuck_jobs') or [])}",
            f"• مدفوعات معلّقة: {_fmt(payments.get('pending_count'))} | حوادث مفتوحة: {len(open_incidents)}",
        ]
    )
    return "\n".join(lines)


@command("ai")
async def handle_ai(ctx: CommandContext) -> str:
    from bot.modules.platform_insights import service as insights_service

    hours, label = _parse_hours_arg(ctx.args, default_hours=24)
    data = await insights_service.get_ai_and_extraction_health(hours=hours)
    ai = data.get("ai") or {}
    ext = data.get("extraction") or {}

    lines = [f"🤖 <b>صحة الذكاء الاصطناعي والاستخراج ({label})</b>", ""]

    if not ai.get("available", True):
        lines.append("• سجلات الذكاء: غير متاحة")
    else:
        lines.extend(
            [
                "<b>سجلات أداء الذكاء الاصطناعي</b>",
                f"• إجمالي الطلبات: {ai.get('total_calls', 0)} (✅ {ai.get('success_count', 0)} / ❌ {ai.get('error_count', 0)})",
                f"• نسبة النجاح: {_fmt(ai.get('success_rate_pct'), '%')}",
                f"• زمن الاستجابة: متوسط {_fmt(ai.get('avg_latency_ms'), 'ms')} | P95 {_fmt(ai.get('p95_latency_ms'), 'ms')}",
            ]
        )
        by_provider = ai.get("by_provider") or {}
        if by_provider:
            lines.append("• حسب المزود:")
            for prov, stats in sorted(by_provider.items(), key=lambda item: -item[1]["calls"]):
                lines.append(
                    f"  - {_esc(prov)}: {stats['calls']} طلب، {stats['errors']} خطأ، "
                    f"متوسط {_fmt(stats.get('avg_latency_ms'), 'ms')}"
                )
        by_op = ai.get("by_operation") or {}
        if by_op:
            op_parts = [f"{_esc(op)}={st['calls']}({st['errors']} خطأ)" for op, st in sorted(by_op.items())]
            lines.append("• حسب العملية: " + "، ".join(op_parts))

        recent_errors = ai.get("recent_errors") or []
        if recent_errors:
            lines.append("")
            lines.append("<b>أحدث أخطاء الذكاء الاصطناعي</b>")
            for err in recent_errors[:5]:
                cat = err.get("error_category") or "error"
                msg = err.get("error_message") or "بدون تفاصيل"
                lines.append(
                    f"• [{_esc(err.get('provider'))}/{_esc(err.get('operation'))}] "
                    f"{_esc(cat)}: {_esc(msg, 70)} ({_age(err.get('created_at'))})"
                )

    lines.append("")
    if not ext.get("available", True):
        lines.append("• مهام الاستخراج: غير متاحة")
    else:
        stuck = ext.get("stuck_jobs") or []
        lines.extend(
            [
                "<b>طابور الاستخراج</b>",
                f"• النشط: انتظار={ext.get('pending_count', 0)}، معالجة={ext.get('processing_count', 0)}، عالقة={len(stuck)}",
                f"• آخر {label}: مكتملة={ext.get('complete_recent', 0)}، فاشلة={ext.get('error_recent', 0)}",
            ]
        )
        if stuck:
            lines.append("• مهام عالقة:")
            for job in stuck[:3]:
                lines.append(
                    f"  - #{_esc(str(job.get('id', ''))[:8])} ({job.get('progress_percentage', 0)}%، "
                    f"آخر تحديث {_age(job.get('updated_at'))})"
                )
        ext_errors = ext.get("recent_errors") or []
        if ext_errors:
            lines.append("• أحدث فشل في الاستخراج:")
            for err in ext_errors[:3]:
                lines.append(
                    f"  - #{_esc(str(err.get('id', ''))[:8])} [{_esc(err.get('extraction_mode'))}]: "
                    f"{_esc(err.get('error_message'), 70)} ({_age(err.get('created_at'))})"
                )

    return "\n".join(lines)


@command("payments")
async def handle_payments(ctx: CommandContext) -> str:
    from bot.modules.admin_actions import service as admin_actions
    from bot.modules.platform_insights import service as insights_service

    show_all = bool(ctx.args and ctx.args[0].lower() == "all")
    summary = await insights_service.get_pending_payments(limit=15)
    try:
        detailed = await admin_actions.list_payment_requests_detailed(
            status_filter="all" if show_all else "pending", limit=15
        )
    except Exception:  # noqa: BLE001
        detailed = []

    pending_count = summary.get("pending_count")
    needs_info = summary.get("needs_info_count")
    approved_7d = summary.get("approved_7d")
    rejected_7d = summary.get("rejected_7d")
    items = detailed if detailed else (summary.get("pending_items") or [])

    lines = [
        f"💳 <b>طابور الاشتراكات وطرق الدفع ({'الكل حديثاً' if show_all else 'المعلّقة'})</b>",
        f"• قيد المراجعة: {_fmt(pending_count)} | تحتاج بيانات: {_fmt(needs_info)}",
        f"• قرارات آخر 7 أيام: ✅ {_fmt(approved_7d)} مقبول | ❌ {_fmt(rejected_7d)} مرفوض",
    ]
    if items:
        table_rows = []
        action_rows = []
        notes: list[str] = []
        for req in items:
            req_id = str(req.get("id") or "")
            short_id = req_id[:8]
            plan = str(req.get("plan_name") or "غير محدد")
            req_status = str(req.get("status") or "pending")
            who = str(req.get("name") or req.get("user_id") or "مستخدم")
            shot = str(req.get("payment_screenshot") or "").strip()
            pay_label = "تجريبي" if shot.startswith("TRIAL_OFFER_") else ("إيصال" if shot else "تحويل")
            table_rows.append(
                {
                    "المعرف": short_id,
                    "المستخدم": who,
                    "الباقة": plan,
                    "الدفع": pay_label,
                    "الحالة": req_status,
                }
            )
            if req.get("reject_reason"):
                notes.append(f"• <code>{_esc(short_id)}</code>: {_esc(req.get('reject_reason'), 80)}")
            if req_status in ("pending", "needs_info") and len(action_rows) < 3:
                action_rows.append(
                    [
                        cmd_button(f"✅ قبول #{short_id}", "approve", [req_id]),
                        cmd_button(f"❌ رفض #{short_id}", "reject", [req_id]),
                    ]
                )

        lines.append("")
        lines.append(format_table(table_rows, ["المعرف", "المستخدم", "الباقة", "الدفع", "الحالة"], max_col_width=14))
        if notes:
            lines.append("<b>أسباب الرفض:</b>")
            lines.extend(notes[:5])
        lines.append("الإجراءات: <code>/approve &lt;id&gt;</code> | <code>/reject &lt;id&gt; [السبب]</code>")

        action_rows.append(
            [
                cmd_button("⏳ المعلّقة", "payments"),
                cmd_button("📋 الكل", "payments", ["all"]),
            ]
        )
        set_reply_buttons(action_rows)
    else:
        lines.append("\n✅ لا توجد طلبات دفع معلّقة.")

    return "\n".join(lines)


@command("approve")
async def handle_approve(ctx: CommandContext) -> str:
    from bot.modules.admin_actions import service as admin_actions

    if not ctx.args:
        return "الاستخدام: /approve <request_id>"
    confirmed = "confirm" in ctx.args
    request_id = next((a for a in ctx.args if a != "confirm"), "")
    if not request_id:
        return "الاستخدام: /approve <request_id>"

    result = await admin_actions.approve_payment(request_id, confirmed=confirmed)
    return (
        "✅ <b>تمت الموافقة على الدفع وتفعيل الاشتراك</b>\n"
        f"• الطلب: <code>{_esc(result['request_id'])}</code>\n"
        f"• المستخدم: {_esc(result.get('user_name') or result['user_id'])} (<code>{_esc(result['user_id'])}</code>)\n"
        f"• الباقة: {_esc(result['plan_name'])} (<code>{_esc(result['plan_id'])}</code>)\n"
        f"• التجديد: {_esc(result.get('renewal_date'))}"
    )


@command("reject")
async def handle_reject(ctx: CommandContext) -> str:
    from bot.modules.admin_actions import service as admin_actions

    if not ctx.args:
        return "الاستخدام: /reject <request_id> [السبب]"
    confirmed = "confirm" in ctx.args
    args = [a for a in ctx.args if a != "confirm"]
    if not args:
        return "الاستخدام: /reject <request_id> [السبب]"
    request_id = args[0]
    reason = " ".join(args[1:]).strip()

    result = await admin_actions.reject_payment(request_id, reason=reason, confirmed=confirmed)
    return (
        "❌ <b>تم رفض طلب الدفع</b>\n"
        f"• الطلب: <code>{_esc(result['request_id'])}</code>\n"
        f"• المستخدم: {_esc(result.get('user_name') or result['user_id'])}\n"
        f"• السبب: {_esc(result.get('reject_reason'))}"
    )


@command("membership")
async def handle_membership(ctx: CommandContext) -> str:
    from bot.modules.admin_actions import service as admin_actions

    args = [a for a in ctx.args if a != "confirm"]
    confirmed = "confirm" in ctx.args
    if len(args) < 2:
        return (
            "الاستخدام: /membership <uid_or_email> <free|silver|gold|diamond|lifetime|founder> [days]\n"
            "مثال: /membership user@example.com gold 30"
        )
    identifier, plan_key = args[0], args[1]
    days: int | None = None
    if len(args) >= 3:
        if not args[2].isdigit() or int(args[2]) <= 0:
            return "عدد الأيام يجب أن يكون رقماً موجباً صحيحاً."
        days = int(args[2])

    result = await admin_actions.set_membership(identifier, plan_key, days=days, confirmed=confirmed)
    return (
        "⭐ <b>تم تحديث العضوية</b>\n"
        f"• المستخدم: {_esc(result.get('name') or result['uid'])} (<code>{_esc(result['uid'])}</code>)\n"
        f"• بريميوم: {result['is_premium']} | الباقة: {_esc(result['plan_name'])}\n"
        f"• مدى الحياة: {result['is_lifetime']} | مؤسس: {result['is_founder']}\n"
        f"• التجديد: {_esc(result.get('renewal_date'))}"
    )


@command("suspend")
async def handle_suspend(ctx: CommandContext) -> str:
    from bot.modules.admin_actions import service as admin_actions

    args = [a for a in ctx.args if a != "confirm"]
    confirmed = "confirm" in ctx.args
    if len(args) < 2 or args[1].lower() not in ("on", "off", "true", "false"):
        return "الاستخدام: /suspend <uid_or_email> <on|off>"
    identifier = args[0]
    suspended = args[1].lower() in ("on", "true")

    result = await admin_actions.set_suspension(identifier, suspended=suspended, confirmed=confirmed)
    state_label = "موقوف 🚫" if result["is_suspended"] else "نشط ✅"
    return (
        "🛡️ <b>تم تحديث حالة الحساب</b>\n"
        f"• المستخدم: {_esc(result.get('name') or result['uid'])} (<code>{_esc(result['uid'])}</code>)\n"
        f"• الحالة: {state_label}"
    )


@command("setbadge")
async def handle_setbadge(ctx: CommandContext) -> str:
    from bot.modules.admin_actions import service as admin_actions

    args = [a for a in ctx.args if a != "confirm"]
    confirmed = "confirm" in ctx.args
    if len(args) < 2:
        return "الاستخدام: /setbadge <uid_or_email> <none|pro|premium|team|enterprise|lifetime|founder>"
    result = await admin_actions.set_badge_tier(args[0], args[1], confirmed=confirmed)
    return (
        "🏅 <b>تم تحديث الشارة</b>\n"
        f"• المستخدم: {_esc(result.get('name') or result['uid'])} (<code>{_esc(result['uid'])}</code>)\n"
        f"• badge_tier: <code>{_esc(result['badge_tier'])}</code>"
    )


@command("points")
async def handle_points(ctx: CommandContext) -> str:
    from bot.modules.admin_actions import service as admin_actions

    if ctx.args:
        detail = await admin_actions.get_user_points_detail(ctx.args[0])
        bal = detail.get("balance") or {}
        lines = [
            f"🏆 <b>النقاط والمكافآت — {_esc(detail.get('name') or detail['uid'])}</b>",
            f"• المعرّف: <code>{_esc(detail['uid'])}</code>",
            f"• النقاط: <b>{bal.get('points', 0):,}</b> | العملات: {bal.get('coins', 0):,} | مستوى المكافآت: {bal.get('level', 1)}",
            f"• نقاط الخبرة XP: {detail.get('xp', 0):,} | مستوى الملف: {detail.get('user_level', 1)}",
        ]
        ledger = detail.get("ledger") or []
        if ledger:
            lines.append("")
            lines.append("<b>أحدث حركات النقاط</b>")
            for entry in ledger[:10]:
                pts = int(entry.get("points") or 0)
                sign = "+" if pts >= 0 else ""
                note = ((entry.get("metadata") or {}).get("note") or "") if isinstance(entry.get("metadata"), dict) else ""
                note_txt = f" ({_esc(note, 45)})" if note else ""
                lines.append(
                    f"• {sign}{pts} نقطة — {_esc(entry.get('event_type'))}{note_txt} ({_age(entry.get('created_at'))})"
                )
        lines.append("\nللتعديل: <code>/grantpoints &lt;uid_or_email&gt; &lt;+/-amount&gt; [ملاحظة]</code>")
        return "\n".join(lines)

    overview = await admin_actions.get_points_overview(limit=10)
    top_bal = overview.get("top_balances") or []
    recent_led = overview.get("recent_ledger") or []
    lines = ["🏆 <b>جدول النقاط والمكافآت</b>", ""]
    if top_bal:
        bal_rows = [
            {
                "#": idx,
                "الاسم": row.get("display_name") or str(row.get("user_id", ""))[:8],
                "النقاط": f"{int(row.get('points') or 0):,}",
                "العملات": f"{int(row.get('coins') or 0):,}",
                "المستوى": row.get("level", 1),
            }
            for idx, row in enumerate(top_bal, start=1)
        ]
        lines.append(format_table(bal_rows, ["#", "الاسم", "النقاط", "العملات", "المستوى"], max_col_width=14))
    else:
        lines.append("• لا توجد أرصدة نقاط مسجلة بعد.")

    if recent_led:
        lines.append("")
        lines.append("<b>أحدث معاملات النقاط</b>")
        for entry in recent_led[:6]:
            pts = int(entry.get("points") or 0)
            sign = "+" if pts >= 0 else ""
            lines.append(
                f"• <code>{_esc(str(entry.get('user_id', ''))[:8])}</code>: {sign}{pts} نقطة "
                f"[{_esc(entry.get('event_type'))}] ({_age(entry.get('created_at'))})"
            )

    lines.append("\nبحث مستخدم: <code>/points &lt;uid_or_email&gt;</code> | تعديل: <code>/grantpoints &lt;uid_or_email&gt; &lt;+/-amount&gt; [ملاحظة]</code>")
    return "\n".join(lines)


@command("grantpoints")
async def handle_grantpoints(ctx: CommandContext) -> str:
    from bot.modules.admin_actions import service as admin_actions

    confirmed = "confirm" in ctx.args
    args = [a for a in ctx.args if a != "confirm"]
    if len(args) < 2:
        return "الاستخدام: /grantpoints <uid_or_email> <+/-amount> [ملاحظة]"
    identifier = args[0]
    try:
        delta = int(args[1])
    except ValueError:
        return "الكمية يجب أن تكون رقماً صحيحاً (مثال: 500 أو -100)."
    note = " ".join(args[2:]).strip()

    result = await admin_actions.adjust_points(
        identifier,
        delta,
        note=note,
        admin_telegram_id=ctx.user_id,
        confirmed=confirmed,
    )
    sign = "+" if result["delta"] >= 0 else ""
    return (
        "🏆 <b>تم تحديث النقاط</b>\n"
        f"• المستخدم: {_esc(result.get('name') or result['uid'])} (<code>{_esc(result['uid'])}</code>)\n"
        f"• التغيير: {sign}{result['delta']:,} نقطة\n"
        f"• الرصيد: {result['previous_points']:,} ← <b>{result['total_points']:,}</b> نقطة (المستوى {result['level']})"
    )


@command("orders")
async def handle_orders(ctx: CommandContext) -> str:
    from bot.modules.admin_actions import service as admin_actions

    orders = await admin_actions.list_reward_orders(limit=15)
    lines = ["🎁 <b>جدول طلبات متجر المكافآت</b>", ""]
    if not orders:
        lines.append("✅ لا توجد طلبات في متجر المكافآت.")
        return "\n".join(lines)

    table_rows = []
    action_rows = []
    refs: list[str] = []
    for order in orders:
        oid = str(order.get("id") or "")
        short_id = oid[:8]
        status_val = str(order.get("status") or "pending")
        amt = f"{order.get('amount_egp', 0)}ج/{order.get('amount_points', 0)}ن"
        table_rows.append(
            {
                "الطلب": short_id,
                "الصنف": order.get("item_id") or "-",
                "القيمة": amt,
                "الدفع": order.get("payment_method") or "-",
                "الحالة": status_val,
            }
        )
        if order.get("payment_reference"):
            refs.append(f"• <code>{_esc(short_id)}</code>: <code>{_esc(order.get('payment_reference'), 60)}</code>")
        if status_val == "pending" and len(action_rows) < 3:
            action_rows.append(
                [
                    cmd_button(f"✅ قبول #{short_id}", "approveorder", [oid]),
                    cmd_button(f"❌ رفض #{short_id}", "rejectorder", [oid]),
                ]
            )

    lines.append(format_table(table_rows, ["الطلب", "الصنف", "القيمة", "الدفع", "الحالة"], max_col_width=13))
    if refs:
        lines.append("<b>مراجع الدفع:</b>")
        lines.extend(refs[:5])
    if action_rows:
        set_reply_buttons(action_rows)
    lines.append("\nالإجراءات: <code>/approveorder &lt;id&gt;</code> | <code>/rejectorder &lt;id&gt; [ملاحظة]</code>")
    return "\n".join(lines)


@command("approveorder")
async def handle_approveorder(ctx: CommandContext) -> str:
    from bot.modules.admin_actions import service as admin_actions

    confirmed = "confirm" in ctx.args
    args = [a for a in ctx.args if a != "confirm"]
    if not args:
        return "الاستخدام: /approveorder <order_id> [ملاحظة]"
    result = await admin_actions.review_order(
        args[0],
        "approved",
        note=" ".join(args[1:]),
        admin_telegram_id=ctx.user_id,
        confirmed=confirmed,
    )
    return (
        "✅ <b>تمت الموافقة على طلب المتجر</b>\n"
        f"• الطلب: <code>{_esc(result['order_id'])}</code>\n"
        f"• المستخدم: <code>{_esc(result['user_id'])}</code>\n"
        f"• النقاط المضافة: +{result.get('points_added', 0):,} (الإجمالي الجديد: {result.get('total_points', 0):,}، المستوى {result.get('level', 1)})"
    )


@command("rejectorder")
async def handle_rejectorder(ctx: CommandContext) -> str:
    from bot.modules.admin_actions import service as admin_actions

    confirmed = "confirm" in ctx.args
    args = [a for a in ctx.args if a != "confirm"]
    if not args:
        return "الاستخدام: /rejectorder <order_id> [ملاحظة]"
    result = await admin_actions.review_order(
        args[0],
        "rejected",
        note=" ".join(args[1:]),
        admin_telegram_id=ctx.user_id,
        confirmed=confirmed,
    )
    return (
        "❌ <b>تم رفض طلب المتجر</b>\n"
        f"• الطلب: <code>{_esc(result['order_id'])}</code>\n"
        f"• المستخدم: <code>{_esc(result['user_id'])}</code>"
    )


@command("incidents")
async def handle_incidents(ctx: CommandContext) -> str:
    from bot.modules.platform_insights import service as insights_service

    hours, label = _parse_hours_arg(ctx.args, default_hours=24)
    data = await insights_service.get_uptime_and_incidents(hours=hours)
    open_incidents = data.get("open_incidents") or []
    recent_incidents = data.get("recent_incidents") or []
    services = data.get("services") or {}

    lines = [f"🚨 <b>الحوادث ونسبة التشغيل ({label})</b>", ""]
    if open_incidents:
        lines.append(f"<b>الحوادث المفتوحة ({len(open_incidents)})</b>")
        for inc in open_incidents:
            lines.append(
                f"• 🔴 <b>{_esc(inc.get('service'))}</b> — {_esc(inc.get('details'), 80)} "
                f"(فُتحت {_age(inc.get('opened_at'))})"
            )
    else:
        lines.append("🟢 لا توجد حوادث مفتوحة.")

    if services:
        lines.append("")
        lines.append(f"<b>نسبة تشغيل الخدمات ({label})</b>")
        for svc, st in sorted(services.items()):
            lines.append(
                f"• {_esc(svc)}: {_fmt(st.get('uptime_pct'), '%')} "
                f"({st.get('checks', 0)} فحص، متوسط {_fmt(st.get('avg_latency_ms'), 'ms')})"
            )

    resolved = [i for i in recent_incidents if i.get("resolved_at")]
    if resolved:
        lines.append("")
        lines.append("<b>أحدث الحوادث المحلولة</b>")
        for inc in resolved[:5]:
            lines.append(
                f"• ✅ {_esc(inc.get('service'))}: {_esc(inc.get('details'), 60)} "
                f"(فُتحت {_age(inc.get('opened_at'))})"
            )

    return "\n".join(lines)


# --- Users -----------------------------------------------------------------

@command("users")
async def handle_users(ctx: CommandContext) -> str:
    from bot.db.repositories import platform_repo
    from bot.modules.users import service as users_service

    filter_mode = "all"
    if ctx.args and ctx.args[0].lower() in ("premium", "suspended", "all"):
        filter_mode = ctx.args[0].lower()

    summary = await users_service.get_user_summary()
    total = summary.get("total_users", 0)
    premium = summary.get("premium_users", 0)
    pct = f"{(premium / total) * 100:.1f}%" if total else "0.0%"
    recent = summary.get("recent_signups") or []

    filter_labels = {"all": "الكل", "premium": "البريميوم", "suspended": "الموقوفون"}
    lines = [
        title(f"جدول المستخدمين ({filter_labels[filter_mode]})", "users"),
        f"الإجمالي: {total} | البريميوم: {premium} ({pct}) | أحدث المسجلين: {len(recent)}",
    ]

    extra_parts = []
    if summary.get("signups_24h") is not None:
        extra_parts.append(f"24س: +{summary['signups_24h']}")
    if summary.get("signups_7d") is not None:
        extra_parts.append(f"7أ: +{summary['signups_7d']}")
    if summary.get("active_sessions_24h") is not None:
        extra_parts.append(f"نشط 24س: {summary['active_sessions_24h']}")
    if summary.get("suspended_users") is not None:
        extra_parts.append(f"موقوف: {summary['suspended_users']}")
    if summary.get("pending_payments") is not None:
        extra_parts.append(f"مدفوعات معلّقة: {summary['pending_payments']}")
    if extra_parts:
        lines.append(" | ".join(extra_parts))

    table_source = await platform_repo.list_users_table(filter_mode=filter_mode, limit=12)
    if not table_source and recent:
        table_source = recent[:10]

    if table_source:
        table_rows = []
        for u in table_source:
            uid_full = str(u.get("uid") or "")
            plan_txt = str(u.get("plan_name") or ("بريميوم" if u.get("is_premium") else "مجاني"))
            status_txt = "موقوف" if u.get("is_suspended") else "نشط"
            pts_val = u.get("reward_points", u.get("xp", 0))
            table_rows.append(
                {
                    "ID": uid_full[:8],
                    "الاسم": u.get("name") or u.get("custom_id") or uid_full[:8],
                    "الباقة": plan_txt,
                    "الحالة": status_txt,
                    "النقاط": f"{int(pts_val or 0):,}",
                }
            )
        lines.append("")
        lines.append(format_table(table_rows, ["ID", "الاسم", "الباقة", "الحالة", "النقاط"], max_col_width=13))
        lines.append("لعرض وتعديل مستخدم: <code>/user &lt;uid_or_email&gt;</code>")

    return "\n".join(lines)


_UID_RE = re.compile(r"^[A-Za-z0-9._-]{3,64}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@command("user")
async def handle_user(ctx: CommandContext) -> str:
    from bot.modules.admin_actions import service as admin_actions
    from bot.modules.users import service as users_service

    if not ctx.args:
        return "الاستخدام: /user <uid_or_email_or_custom_id>"
    identifier = ctx.args[0]
    if not (_UID_RE.match(identifier) or _EMAIL_RE.match(identifier)):
        return "معرّف غير صالح — أدخل uid أو custom_id أو البريد الإلكتروني."

    full_profile = None
    try:
        full_profile = await admin_actions.get_user_full_profile(identifier)
    except Exception:  # noqa: BLE001
        full_profile = None

    if full_profile is None:
        detail = await users_service.get_user_detail(identifier)
        if detail is None:
            return f"لم يتم العثور على مستخدم مطابق لـ '{_esc(identifier)}'."
        preferred_keys = (
            "name", "email", "is_premium", "plan_name", "is_lifetime",
            "is_founder", "is_admin", "is_suspended", "badge_tier", "onboarded", "created_at",
        )
        lines = [f"{k}: {_esc(detail.get(k))}" for k in preferred_keys if k in detail]
        return f"{title('المستخدم', 'users')}\nuid: {_esc(detail.get('uid'))}\n" + "\n".join(lines)

    u = full_profile["user"]
    bal = full_profile.get("reward_balance") or {}
    ledger = full_profile.get("recent_ledger") or []
    reqs = full_profile.get("recent_requests") or []

    lines = [
        f"{title('الملف الكامل للمستخدم', 'users')}",
        f"• المعرّف UID: <code>{_esc(u.get('uid'))}</code>"
        + (f" | المعرّف المخصص: <code>{_esc(u.get('custom_id'))}</code>" if u.get("custom_id") else ""),
        f"• الاسم: {_esc(u.get('name'))} | البريد: {_esc(u.get('email'))}",
        f"• أدمن: {bool(u.get('is_admin'))} | موقوف: {bool(u.get('is_suspended'))} | مكتمل: {bool(u.get('onboarded'))}",
        f"• تاريخ التسجيل: {_age(u.get('created_at'))}",
        "",
        "<b>العضوية والشارات</b>",
        f"• بريميوم: {bool(u.get('is_premium'))} | الباقة: {_esc(u.get('plan_name'))} (<code>{_esc(u.get('plan_id'))}</code>)",
        f"• مدى الحياة: {bool(u.get('is_lifetime'))} | مؤسس: {bool(u.get('is_founder'))}",
        f"• التجديد: {_esc(u.get('renewal_date') or u.get('premium_until'))}",
        f"• الشارة: <code>{_esc(u.get('badge_tier'))}</code> | لون الاسم: <code>{_esc(u.get('name_color'))}</code>",
        "",
        "<b>النقاط والتقدم</b>",
        f"• نقاط المكافآت: <b>{int(bal.get('points') or 0):,}</b> | العملات: {int(bal.get('coins') or 0):,} | مستوى المكافآت: {bal.get('level', 1)}",
        f"• نقاط الخبرة XP: {int(u.get('xp') or 0):,} | مستوى الملف: {u.get('level', 1)}",
    ]

    if ledger:
        lines.append("")
        lines.append("<b>أحدث حركات النقاط</b>")
        for entry in ledger[:5]:
            pts = int(entry.get("points") or 0)
            sign = "+" if pts >= 0 else ""
            lines.append(f"• {sign}{pts} نقطة — {_esc(entry.get('event_type'))} ({_age(entry.get('created_at'))})")

    if reqs:
        lines.append("")
        lines.append("<b>أحدث طلبات الاشتراك</b>")
        for req in reqs[:5]:
            lines.append(
                f"• <code>{_esc(str(req.get('id', ''))[:8])}</code> — {_esc(req.get('plan_name'))} "
                f"[{_esc(req.get('status'))}] ({_age(req.get('created_at'))})"
            )

    lines.extend(
        [
            "",
            "<b>إجراءات سريعة للأدمن</b>",
            f"• الباقة: <code>/membership {_esc(u.get('uid'))} &lt;free|silver|gold|diamond|lifetime|founder&gt; [days]</code>",
            f"• النقاط: <code>/grantpoints {_esc(u.get('uid'))} &lt;+/-amount&gt; [ملاحظة]</code>",
            f"• تعديل بيانات: <code>/edituser {_esc(u.get('uid'))} &lt;name|custom_id|name_color|is_admin|xp|level&gt; &lt;value&gt;</code>",
            f"• إيقاف: <code>/suspend {_esc(u.get('uid'))} &lt;on|off&gt;</code>",
        ]
    )

    uid_val = str(u.get("uid") or "")
    if uid_val:
        is_susp = bool(u.get("is_suspended"))
        susp_btn = (
            cmd_button("✅ تفعيل الحساب", "suspend", [uid_val, "off"])
            if is_susp
            else cmd_button("🚫 إيقاف الحساب", "suspend", [uid_val, "on"])
        )
        set_reply_buttons(
            [
                [
                    susp_btn,
                    cmd_button("⭐ باقة Gold", "membership", [uid_val, "gold", "30"]),
                    cmd_button("💎 باقة Diamond", "membership", [uid_val, "diamond", "365"]),
                ],
                [
                    cmd_button("🏆 +100 نقطة", "grantpoints", [uid_val, "100"]),
                    cmd_button("🏆 +500 نقطة", "grantpoints", [uid_val, "500"]),
                    cmd_button("➖ -100 نقطة", "grantpoints", [uid_val, "-100"]),
                ],
            ]
        )

    return "\n".join(lines)


# --- Infrastructure ----------------------------------------------------------

@command("database")
async def handle_database(ctx: CommandContext) -> str:
    from bot.modules.database_monitor import service as database_monitor
    from bot.modules.platform_insights import service as insights_service

    result = await database_monitor.check_database()
    lines = [status_line("قاعدة البيانات", result["status"], f"{result['latency_ms']}ms")]

    try:
        overview = await insights_service.get_database_overview()
        db_stats = overview.get("db_stats_24h") or {}
        if db_stats.get("uptime_pct") is not None:
            lines.append(
                f"• التشغيل (24س): {db_stats['uptime_pct']}% "
                f"(متوسط {_fmt(db_stats.get('avg_latency_ms'), 'ms')}، {db_stats.get('checks', 0)} فحص)"
            )
        counts = overview.get("table_counts") or {}
        valid_counts = [(tbl, cnt) for tbl, cnt in counts.items() if cnt is not None]
        if valid_counts:
            lines.append("")
            lines.append("<b>عدد الصفوف في الجداول</b>")
            for tbl, cnt in valid_counts:
                lines.append(f"• {html.escape(tbl)}: {cnt:,}")
    except Exception:  # noqa: BLE001
        pass

    return "\n".join(lines)


@command("storage")
async def handle_storage(ctx: CommandContext) -> str:
    from bot.modules.storage_monitor import service as storage_monitor

    result = await storage_monitor.check_storage()
    lines = [status_line("التخزين", result["status"], f"{result['bucket_count']} حاوية")]
    buckets = result.get("buckets") or []
    if buckets:
        lines.append("")
        lines.append("<b>الحاويات</b>")
        for b in buckets:
            vis = "عام" if b.get("public") else "خاص"
            entries = b.get("entries_sample")
            count_note = f"، {entries}+ ملف" if entries is not None else ""
            lines.append(f"• {_esc(b.get('name'))} ({vis}{count_note})")
    return "\n".join(lines)


@command("system")
async def handle_system(ctx: CommandContext) -> str:
    from bot.modules.cloudflare import service as cloudflare_service
    from bot.modules.firebase import service as firebase_service
    from bot.modules.github import service as github_service

    try:
        repo = await github_service.get_repo_status()
        gh_line = f"GitHub: {_esc(repo.get('latest_commit_sha'))} — {_esc(repo.get('latest_commit_message'), 70)}"
    except ConfigurationError as exc:
        gh_line = f"GitHub: غير مهيأ ({_esc(exc, 60)})"
    except Exception as exc:  # noqa: BLE001
        gh_line = f"GitHub: غير متاح ({_esc(exc, 60)})"

    try:
        cf = await cloudflare_service.get_deployment_status()
        cf_line = f"Cloudflare Pages: {_esc(cf.get('status', 'غير معروف'))}"
        if cf.get("url"):
            cf_line += f" ({_esc(cf['url'], 60)})"
    except ConfigurationError as exc:
        cf_line = f"Cloudflare Pages: غير مهيأ ({_esc(exc, 60)})"
    except Exception as exc:  # noqa: BLE001
        cf_line = f"Cloudflare Pages: غير متاح ({_esc(exc, 60)})"

    fb = await firebase_service.get_status()
    fb_line = f"Firebase: {_esc(fb.get('status', 'غير معروف'))}"

    return "\n".join(["🖥️ <b>نظرة عامة على النظام</b>", gh_line, cf_line, fb_line])


# --- Deployment ----------------------------------------------------------------

@command("deploy")
async def handle_deploy(ctx: CommandContext) -> str:
    from bot.modules.deployment import service as deployment_service

    confirmed = "confirm" in ctx.args
    return await deployment_service.trigger_deploy(confirmed=confirmed)


@command("build")
async def handle_build(ctx: CommandContext) -> str:
    from bot.modules.deployment import service as deployment_service

    confirmed = "confirm" in ctx.args
    return await deployment_service.trigger_build(confirmed=confirmed)


@command("rollback")
async def handle_rollback(ctx: CommandContext) -> str:
    from bot.modules.deployment import service as deployment_service

    confirmed = "confirm" in ctx.args
    target_sha = next((a for a in ctx.args if a != "confirm"), None)
    return await deployment_service.trigger_rollback(confirmed=confirmed, target_sha=target_sha)


# --- Observability -----------------------------------------------------------

@command("logs")
async def handle_logs(ctx: CommandContext) -> str:
    from bot.modules.logging import service as logging_service

    limit = 10
    if ctx.args and ctx.args[0].isdigit():
        limit = max(1, min(30, int(ctx.args[0])))
    logs = await logging_service.get_recent_command_logs(limit=limit)
    if not logs:
        return "لا يوجد نشاط حديث."
    lines = []
    for log in logs:
        icon = "❌" if log.get("error") else "✅"
        lines.append(
            f"{icon} /{_esc(log.get('command'))} — {log.get('duration_ms', '?')}ms ({_age(log.get('created_at'))})"
        )
    return "📜 <b>أحدث الأوامر المنفذة</b>\n" + "\n".join(lines)


@command("errors")
async def handle_errors(ctx: CommandContext) -> str:
    from bot.integrations import sentry_client
    from bot.modules.platform_insights import service as insights_service

    hours, label = _parse_hours_arg(ctx.args, default_hours=24)
    lines = [f"🐛 <b>تقرير الأخطاء والتشخيص الشامل ({label})</b>", ""]

    try:
        issues = await sentry_client.get_recent_issues(limit=10)
        if not issues:
            lines.append("• Sentry: ✅ لا توجد مشاكل غير محلولة.")
        else:
            lines.append(f"<b>مشاكل Sentry ({len(issues)})</b>")
            for issue in issues:
                culprit = issue.get("culprit")
                culprit_txt = f" [{_esc(culprit, 40)}]" if culprit else ""
                lines.append(
                    f"• {_esc(issue.get('title', 'خطأ غير معروف'), 90)}{culprit_txt} "
                    f"({issue.get('count', '?')}x، {_esc(issue.get('level', 'error'))})"
                )
    except ConfigurationError:
        lines.append("• Sentry: غير مهيأ")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"• Sentry: غير متاح ({_esc(exc, 80)})")

    try:
        report = await insights_service.get_detailed_errors_report(hours=hours)
        ai_data = report.get("ai") or {}
        ext_data = report.get("extraction") or {}
        ai_errors = ai_data.get("recent_errors") or []
        ext_errors = ext_data.get("recent_errors") or []
        stuck_jobs = ext_data.get("stuck_jobs") or []
        failed_checks = report.get("failed_checks") or []
        failed_cmds = report.get("failed_commands") or []
        open_incidents = report.get("open_incidents") or []

        lines.append("")
        if open_incidents:
            lines.append(f"<b>الحوادث المفتوحة ({len(open_incidents)})</b>")
            for inc in open_incidents:
                lines.append(
                    f"• 🔴 <b>{_esc(inc.get('service'))}</b>: {_esc(inc.get('details'), 120)} "
                    f"(فُتحت {_age(inc.get('opened_at'))})"
                )
        else:
            lines.append("• الحوادث المفتوحة: ✅ لا يوجد")

        lines.append("")
        if ai_errors:
            lines.append(
                f"<b>أخطاء الذكاء الاصطناعي ({ai_data.get('error_count', len(ai_errors))} إجمالي في {label})</b>"
            )
            for err in ai_errors[:10]:
                uid_short = str(err.get("user_id") or "")[:8] or "anon"
                model_txt = f"/{_esc(err.get('model'), 28)}" if err.get("model") else ""
                lat_txt = f" {err['latency_ms']}ms" if err.get("latency_ms") is not None else ""
                lines.append(
                    f"• [{_esc(err.get('provider'))}{model_txt} | {_esc(err.get('operation'))}{lat_txt} | u:{_esc(uid_short)}] "
                    f"<b>{_esc(err.get('error_category') or 'error')}</b>: "
                    f"{_esc(err.get('error_message') or 'بدون رسالة', 180)} ({_age(err.get('created_at'))})"
                )
        else:
            lines.append(f"• أخطاء الذكاء ({label}): ✅ لا يوجد")

        lines.append("")
        if ext_errors or stuck_jobs:
            lines.append(f"<b>أخطاء الاستخراج والمهام العالقة ({label})</b>")
            for job in stuck_jobs[:5]:
                lines.append(
                    f"• ⏳ عالق (STUCK) <code>{_esc(str(job.get('id', ''))[:8])}</code> "
                    f"({job.get('progress_percentage', 0)}%، المزود={_esc(job.get('provider'))}، "
                    f"آخر تحديث {_age(job.get('updated_at'))})"
                )
            for err in ext_errors[:8]:
                lines.append(
                    f"• ❌ <code>{_esc(str(err.get('id', ''))[:8])}</code> "
                    f"[{_esc(err.get('extraction_mode'))}/{_esc(err.get('provider'))}]: "
                    f"{_esc(err.get('error_message') or 'بدون رسالة خطأ', 180)} ({_age(err.get('created_at'))})"
                )
        else:
            lines.append(f"• أخطاء الاستخراج ({label}): ✅ لا يوجد")

        if failed_checks:
            lines.append("")
            lines.append(f"<b>فحوصات الصحة الفاشلة ({label})</b>")
            for chk in failed_checks[:6]:
                meta = chk.get("metadata") if isinstance(chk.get("metadata"), dict) else {}
                code = meta.get("status_code")
                code_txt = f" HTTP {code}" if code is not None else ""
                lines.append(
                    f"• 🔴 {_esc(chk.get('service'))}{code_txt} "
                    f"({chk.get('latency_ms', '?')}ms، {_age(chk.get('checked_at'))})"
                )

        if failed_cmds:
            lines.append("")
            lines.append("<b>أوامر البوت الفاشلة</b>")
            for cmd in failed_cmds[:6]:
                lines.append(
                    f"• /{_esc(cmd.get('command'))} (u:{cmd.get('user_id')}): "
                    f"{_esc(cmd.get('error'), 140)} ({_age(cmd.get('created_at'))})"
                )
    except Exception:  # noqa: BLE001
        pass

    return "\n".join(lines)


@command("security")
async def handle_security(ctx: CommandContext) -> str:
    from bot.modules.platform_insights import service as insights_service
    from bot.modules.security import service as security_service

    lines = ["🛡️ <b>نظرة عامة على الأمان</b>"]
    try:
        overview = await security_service.get_security_overview()
        dep = overview.get("dependabot") or {}
        by_sev = dep.get("by_severity") or {}
        sev_str = "، ".join(f"{k}={v}" for k, v in sorted(by_sev.items()))
        lines.append(f"• تنبيهات Dependabot المفتوحة: {dep.get('total_open', 0)}" + (f" ({sev_str})" if sev_str else ""))
        lines.append(f"• محاولات الوصول غير المصرح بها: {overview.get('recent_unauthorized_attempts', 0)}")
    except ConfigurationError as exc:
        lines.append(f"• Dependabot: غير مهيأ ({_esc(exc, 60)})")

    try:
        uptime = await insights_service.get_uptime_and_incidents(hours=24)
        lines.append(f"• الحوادث المفتوحة: {len(uptime.get('open_incidents') or [])}")
    except Exception:  # noqa: BLE001
        pass

    return "\n".join(lines)


# --- Backup / Restore --------------------------------------------------------------

@command("backup")
async def handle_backup(ctx: CommandContext) -> str:
    from bot.modules.backup import service as backup_service

    if ctx.args and ctx.args[0] == "list":
        backups = await backup_service.list_backups()
        if not backups:
            return "لا توجد نسخ احتياطية حتى الآن."
        lines = [
            f"• {b['backup_id']} — {b['artifact_name']} ({b['created_at']})"
            for b in backups[:10]
        ]
        return f"{title('النسخ الاحتياطية المتاحة', 'backup')}\n" + "\n".join(lines)

    confirmed = "confirm" in ctx.args
    return await backup_service.trigger_backup(confirmed=confirmed)


@command("restore")
async def handle_restore(ctx: CommandContext) -> str:
    from bot.modules.backup import service as backup_service

    if not ctx.args:
        return "الاستخدام: /restore <backup_id> [confirm]\nاستخدم /backup list لعرض النسخ المتاحة."
    backup_id = ctx.args[0]
    if not backup_id.isdigit():
        return f"معرّف نسخة غير صالح '{backup_id}' — يجب أن يكون رقماً من /backup list."
    confirmed = "confirm" in ctx.args
    return await backup_service.trigger_restore(confirmed=confirmed, backup_id=backup_id)


# --- Analytics / Reports / AI Assistant ---------------------------------------------

@command("analytics")
async def handle_analytics(ctx: CommandContext) -> str:
    from bot.modules.analytics import service as analytics_service

    _, period_label = _parse_hours_arg(ctx.args, default_hours=24)
    summary = await analytics_service.get_analytics_summary(period=period_label)
    pulse = summary.get("pulse") or {}
    users = pulse.get("users") or {}
    activity = pulse.get("activity") or {}
    ai = pulse.get("ai") or {}
    vitals = summary.get("web_vitals") or {}
    umami = summary.get("umami")

    lines = [
        f"📈 <b>التحليلات ({html.escape(period_label)})</b>",
        f"الأخطاء ({html.escape(period_label)}): {summary.get('error_count') if summary.get('error_count') is not None else 'غير متاح'}",
    ]

    if users or activity:
        lines.extend(
            [
                "",
                "<b>تفاعل المنصة</b>",
                f"• مسجلون جدد: {_fmt(users.get('signups_recent'))} | نشط 24س: {_fmt(users.get('active_24h'))}",
                f"• اختبارات منشأة: {_fmt(activity.get('quizzes_recent'))} | الإكمالات: {_fmt(activity.get('completions_recent'))}",
                f"• محاولات الضيوف: {_fmt(activity.get('guest_attempts_recent'))} | متوسط الدرجة: {_fmt(activity.get('avg_score_pct'), '%')}",
                f"• طلبات الذكاء: {_fmt(ai.get('total_calls'))} ({_fmt(ai.get('success_rate_pct'), '%')} نجاح)",
            ]
        )

    if vitals:
        lines.append("")
        lines.append("<b>مؤشرات Web Vitals (p75)</b>")
        for metric, st in sorted(vitals.items()):
            unit = "" if metric == "CLS" else "ms"
            lines.append(f"• {html.escape(metric)}: {st['p75']}{unit} (عينة={st['samples']})")

    if isinstance(umami, dict) and umami:
        pv = umami.get("pageviews", {})
        vis = umami.get("visitors", {})
        pv_val = pv.get("value") if isinstance(pv, dict) else pv
        vis_val = vis.get("value") if isinstance(vis, dict) else vis
        lines.extend(
            [
                "",
                "<b>زيارات Umami</b>",
                f"• المشاهدات: {_fmt(pv_val)} | الزوار: {_fmt(vis_val)}",
            ]
        )

    return "\n".join(lines)


@command("reports")
async def handle_reports(ctx: CommandContext) -> str:
    from bot.modules.reports import service as reports_service

    args = [a.lower() for a in ctx.args]
    refresh = "refresh" in args or "now" in args
    report_type = next((a for a in args if a not in {"refresh", "now"}), "daily")

    report = await reports_service.get_report(report_type, refresh=refresh)
    if report is None:
        return (
            f"نوع التقرير غير معروف أو فارغ '{_esc(report_type)}'.\n"
            "المتاح: daily, weekly, monthly, performance (أضف 'refresh' لإعادة التوليد)."
        )
    return report["content"]


@command("ask")
async def handle_ask(ctx: CommandContext) -> str:
    from bot.modules.ai_assistant import service as ai_assistant

    if not ctx.args:
        return "الاستخدام: /ask <سؤالك>\nمثال: /ask ما هي نسبة أخطاء الذكاء وحالة النظام اليوم؟"
    question = " ".join(ctx.args).strip()
    answer = await ai_assistant.answer_question(question)
    return f"🤖 <b>مساعد العمليات الذكي</b>\n\n{html.escape(answer)}"


# --- Access control (RBAC) ----------------------------------------------------------

@command("setrole")
async def handle_setrole(ctx: CommandContext) -> str:
    """Owner-only. Grants ADMIN or VIEWER to a Telegram user ID at runtime."""
    from bot.db.repositories.users_repo import set_role

    if len(ctx.args) < 2:
        return "الاستخدام: /setrole <telegram_user_id> <ADMIN|VIEWER>"

    try:
        target_user_id = int(ctx.args[0])
    except ValueError:
        return "معرّف تليجرام يجب أن يكون رقماً."

    role_str = ctx.args[1].upper()
    if role_str not in ("ADMIN", "VIEWER"):
        return "الدور يجب أن يكون ADMIN أو VIEWER. المالك يحدد عبر متغير البيئة OWNER_USER_IDS فقط."

    await set_role(target_user_id, role_str)
    return f"✅ المستخدم {target_user_id} أصبح الآن {role_str}."


# --- Runtime settings ----------------------------------------------------------------

_KNOWN_SETTINGS: dict[str, str] = {
    "maintenance_mode": "bool",
    "website_latency_warn_ms": "int",
    "api_latency_warn_ms": "int",
    "notify_on_new_user": "bool",
    "report_verbosity": "enum:brief,full",
}


def _parse_setting_value(kind: str, raw: str):
    if kind == "bool":
        if raw.lower() in ("true", "1", "yes", "on"):
            return True
        if raw.lower() in ("false", "0", "no", "off"):
            return False
        raise ValueError("متوقع true أو false")
    if kind == "int":
        try:
            return int(raw)
        except ValueError:
            raise ValueError("متوقع رقم صحيح") from None
    if kind.startswith("enum:"):
        options = kind.split(":", 1)[1].split(",")
        if raw not in options:
            raise ValueError(f"متوقع إحدى القيم: {', '.join(options)}")
        return raw
    raise ValueError("نوع إعداد غير مدعوم")  # pragma: no cover


@command("settings")
async def handle_settings(ctx: CommandContext) -> str:
    from bot.db.repositories.config_repo import get_all_settings, set_setting

    known_keys_hint = ", ".join(_KNOWN_SETTINGS)

    if not ctx.args:
        settings_map = await get_all_settings()
        if not settings_map:
            return f"لا توجد إعدادات وقت تشغيل مهيأة بعد.\nالاستخدام: /settings <key> <value>\nالمفاتيح المتاحة: {known_keys_hint}"
        return "⚙️ <b>إعدادات البوت</b>\n" + "\n".join(f"{k}: {v}" for k, v in settings_map.items())

    if len(ctx.args) < 2:
        return f"الاستخدام: /settings <key> <value>\nالمفاتيح المتاحة: {known_keys_hint}"

    key, raw_value = ctx.args[0], " ".join(ctx.args[1:])
    if key not in _KNOWN_SETTINGS:
        return f"إعداد غير معروف '{_esc(key)}'.\nالمفاتيح المتاحة: {known_keys_hint}"

    try:
        value = _parse_setting_value(_KNOWN_SETTINGS[key], raw_value)
    except ValueError as e:
        return f"قيمة غير صالحة لـ '{_esc(key)}': {e}"

    await set_setting(key, value)
    return f"⚙️ تم ضبط {key} إلى {value}."


# ---------------------------------------------------------------------------
# /platform — view & toggle maintenance mode / registration
# ---------------------------------------------------------------------------

@command("platform")
async def handle_platform(ctx: CommandContext) -> str:
    from bot.modules.admin_actions import service as admin_actions

    if not ctx.args:
        cfg = await admin_actions.get_platform_settings()
        if not cfg:
            return "⚙️ <b>إعدادات المنصة</b>\n• تعذر قراءة إعدادات platform_settings."
        mm = "🔴 مفعّل" if cfg.get("maintenance_mode") else "🟢 متوقف"
        reg = "✅ مفتوح" if cfg.get("allow_registrations") else "❌ مغلق"
        updated = _age(cfg.get("updated_at"))
        return (
            "⚙️ <b>إعدادات المنصة</b>\n"
            f"• وضع الصيانة: <b>{mm}</b>\n"
            f"• فتح التسجيل: <b>{reg}</b>\n"
            f"• آخر تحديث: {updated}\n\n"
            "تبديل الصيانة: <code>/platform maintenance on|off</code>\n"
            "تبديل التسجيل: <code>/platform registration on|off</code>"
        )

    confirmed = "confirm" in ctx.args
    args = [a for a in ctx.args if a != "confirm"]

    if len(args) == 3 and args[0].lower() == "set" and confirmed:
        mm = args[1] == "1"
        reg = args[2] == "1"
    else:
        if len(args) < 2 or args[1].lower() not in ("on", "off"):
            return "الاستخدام: /platform &lt;maintenance|registration&gt; &lt;on|off&gt;"

        cfg = await admin_actions.get_platform_settings()
        mm = bool(cfg.get("maintenance_mode", False))
        reg = bool(cfg.get("allow_registrations", True))

        field = args[0].lower()
        value = args[1].lower() == "on"
        if field == "maintenance":
            mm = value
        elif field == "registration":
            reg = value
        else:
            return "حقل غير معروف. استخدم 'maintenance' أو 'registration'."

    result = await admin_actions.toggle_platform_settings(
        maintenance_mode=mm, allow_registrations=reg, confirmed=confirmed
    )
    return (
        "⚙️ <b>تم تحديث إعدادات المنصة</b>\n"
        f"• وضع الصيانة: {'🔴 مفعّل' if result['maintenance_mode'] else '🟢 متوقف'}\n"
        f"• التسجيل: {'✅ مفتوح' if result['allow_registrations'] else '❌ مغلق'}"
    )


# ---------------------------------------------------------------------------
# /trial — view & toggle trial offer durations
# ---------------------------------------------------------------------------

@command("trial")
async def handle_trial(ctx: CommandContext) -> str:
    from bot.modules.admin_actions import service as admin_actions

    if not ctx.args or (len(ctx.args) == 1 and ctx.args[0].isdigit() is False):
        offers = await admin_actions.get_trial_offers()
        if not offers:
            return "🎁 <b>عروض التجربة المجانية</b>\n• لا توجد عروض مسجلة."
        lines = ["🎁 <b>عروض التجربة المجانية</b>", ""]
        for offer in offers:
            state = "✅ نشط" if offer.get("is_active") else "❌ غير نشط"
            updated = _age(offer.get("updated_at"))
            lines.append(f"• <b>{offer.get('duration_days')} يوم</b>: {state} (آخر تحديث {updated})")
        lines.append("\nللتعديل: <code>/trial &lt;7|14|30&gt; &lt;on|off&gt;</code>")
        return "\n".join(lines)

    if len(ctx.args) < 2 or ctx.args[1].lower() not in ("on", "off"):
        return "الاستخدام: /trial &lt;7|14|30&gt; &lt;on|off&gt;"

    confirmed = "confirm" in ctx.args
    args = [a for a in ctx.args if a != "confirm"]

    if not args[0].isdigit():
        return "الاستخدام: /trial &lt;7|14|30&gt; &lt;on|off&gt;"
    duration = int(args[0])
    is_active = args[1].lower() == "on"

    result = await admin_actions.toggle_trial_offer(
        duration_days=duration, is_active=is_active, confirmed=confirmed
    )
    state = "✅ تم التفعيل" if result["is_active"] else "❌ تم الإيقاف"
    return (
        f"🎁 <b>تم تحديث عرض التجربة المجانية</b>\n"
        f"• المدة: <b>{result['duration_days']} يوم</b>\n"
        f"• الحالة: {state}"
    )


# ---------------------------------------------------------------------------
# /coupon — list, create, toggle, delete coupons
# ---------------------------------------------------------------------------

@command("coupon")
async def handle_coupon(ctx: CommandContext) -> str:
    from bot.modules.admin_actions import service as admin_actions

    confirmed = "confirm" in ctx.args
    args = [a for a in ctx.args if a != "confirm"]

    if not args:
        coupons = await admin_actions.list_coupons(limit=20)
        if not coupons:
            return "🎟️ <b>كوبونات الخصم</b>\n• لا توجد كوبونات."
        lines = ["🎟️ <b>جدول كوبونات الخصم</b>", ""]
        c_rows = []
        for c in coupons:
            used = c.get("used_count", 0)
            max_u = c.get("max_uses", 0)
            c_rows.append(
                {
                    "ID": str(c.get("id") or ""),
                    "الكود": str(c.get("code") or ""),
                    "الخصم": f"{c.get('discount_percent', 0)}%",
                    "الاستخدام": f"{used}/{max_u}" if max_u else f"{used}/∞",
                    "الحالة": "نشط" if c.get("is_active") else "متوقف",
                }
            )
        lines.append(format_table(c_rows, ["ID", "الكود", "الخصم", "الاستخدام", "الحالة"], max_col_width=13))
        lines.append(
            "\nإنشاء: <code>/coupon create &lt;id&gt; &lt;CODE&gt; &lt;discount%&gt; [max_uses] [expiry_iso] [plans]</code>\n"
            "تبديل: <code>/coupon toggle &lt;id&gt; on|off</code>\n"
            "حذف: <code>/coupon delete &lt;id&gt;</code>"
        )
        return "\n".join(lines)

    sub = args[0].lower()

    if sub == "create":
        if len(args) < 4:
            return "الاستخدام: /coupon create &lt;id&gt; &lt;CODE&gt; &lt;discount%&gt; [max_uses] [expiry_iso] [plans]"
        coupon_id = args[1]
        code = args[2]
        try:
            disc = int(args[3])
        except ValueError:
            return "نسبة الخصم يجب أن تكون رقماً صحيحاً بين 0 و 100."
        max_uses = int(args[4]) if len(args) > 4 and args[4].isdigit() else 0
        expiry_arg = args[5] if len(args) > 5 else None
        expiry = expiry_arg if (expiry_arg and expiry_arg != "-" and "T" in expiry_arg) else None
        plans = args[6] if len(args) > 6 else "silver,gold,diamond"

        result = await admin_actions.create_coupon(
            coupon_id=coupon_id, code=code, discount_percent=disc,
            max_uses=max_uses, expiry_date=expiry, applicable_plans=plans,
            confirmed=confirmed,
        )
        return (
            "🎟️ <b>تم إنشاء/تحديث الكوبون</b>\n"
            f"• الكود: <code>{_esc(result.get('code'))}</code>\n"
            f"• الخصم: {result.get('discount_percent', 0)}% | الحد الأقصى: {result.get('max_uses', 0) or '∞'}\n"
            f"• الباقات: {_esc(result.get('applicable_plans', 'الكل'), 60)}"
        )

    if sub == "toggle":
        if len(args) < 3 or args[2].lower() not in ("on", "off"):
            return "الاستخدام: /coupon toggle &lt;id&gt; on|off"
        is_active = args[2].lower() == "on"
        result = await admin_actions.toggle_coupon(args[1], is_active=is_active, confirmed=confirmed)
        state = "✅ تم التفعيل" if result.get("is_active") else "❌ تم الإيقاف"
        return f"🎟️ <b>حالة الكوبون: {state}</b>\n• ID: <code>{_esc(args[1])}</code>"

    if sub == "delete":
        if len(args) < 2:
            return "الاستخدام: /coupon delete &lt;id&gt;"
        await admin_actions.delete_coupon(args[1], confirmed=confirmed)
        return f"🗑️ <b>تم حذف الكوبون</b>\n• ID: <code>{_esc(args[1])}</code>"

    return "أمر فرعي غير معروف. استخدم: بدون معاملات للعرض، أو create, toggle, delete."


# ---------------------------------------------------------------------------
# /vitals — dedicated Web Vitals report
# ---------------------------------------------------------------------------

@command("vitals")
async def handle_vitals(ctx: CommandContext) -> str:
    from bot.db.repositories import platform_repo

    summary = await platform_repo.get_web_vitals_summary()
    if not summary:
        return "📊 <b>مؤشرات الأداء Web Vitals</b>\n• لا توجد بيانات متاحة حالياً."

    _THRESHOLDS = {
        "CLS": [(0.1, "🟢 ممتاز"), (0.25, "🟡 يحتاج تحسين"), (999, "🔴 بطيء")],
        "LCP": [(2500, "🟢 ممتاز"), (4000, "🟡 يحتاج تحسين"), (99999, "🔴 بطيء")],
        "FCP": [(1800, "🟢 ممتاز"), (3000, "🟡 يحتاج تحسين"), (99999, "🔴 بطيء")],
        "INP": [(200, "🟢 ممتاز"), (500, "🟡 يحتاج تحسين"), (99999, "🔴 بطيء")],
        "TTFB": [(800, "🟢 ممتاز"), (1800, "🟡 يحتاج تحسين"), (99999, "🔴 بطيء")],
    }

    def _rating(metric: str, value: float) -> str:
        for threshold, label in _THRESHOLDS.get(metric, []):
            if value <= threshold:
                return label
        return "⚪"

    lines = ["📊 <b>تقرير مؤشرات الأداء Web Vitals</b>", ""]
    for metric, stats in sorted(summary.items()):
        p75 = stats.get("p75")
        avg = stats.get("avg")
        samples = stats.get("samples", 0)
        rating = _rating(metric, p75) if p75 is not None else "⚪"
        unit = "" if metric == "CLS" else "ms"
        lines.append(
            f"• <b>{metric}</b>: p75={_fmt(p75, unit)} متوسط={_fmt(avg, unit)} "
            f"({samples} عينة) {rating}"
        )

    lines.append(
        "\n<i>الحدود الجيدة: CLS≤0.1 LCP≤2500ms FCP≤1800ms INP≤200ms TTFB≤800ms</i>"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# /topusers — leaderboard by XP or reward points
# ---------------------------------------------------------------------------

@command("topusers")
async def handle_topusers(ctx: CommandContext) -> str:
    from bot.db.repositories import platform_repo

    mode = (ctx.args[0].lower() if ctx.args else "xp")
    limit = 10

    if mode in ("points", "pts", "rewards"):
        rows = await platform_repo.get_top_users_by_points(limit=limit)
        lines = ["🏆 <b>جدول المتصدرين — نقاط المكافآت</b>", ""]
        if not rows:
            return lines[0] + "\n• لا توجد بيانات متاحة."
        t_rows = [
            {
                "#": idx,
                "الاسم": row.get("display_name", str(row.get("user_id", ""))[:8]),
                "النقاط": f"{int(row.get('points') or 0):,}",
                "المستوى": row.get("level", 1),
            }
            for idx, row in enumerate(rows, 1)
        ]
        lines.append(format_table(t_rows, ["#", "الاسم", "النقاط", "المستوى"], max_col_width=16))
        lines.append("\nالترتيب: <code>/topusers xp</code> | <code>/topusers points</code>")
        return "\n".join(lines)

    rows = await platform_repo.get_top_users_by_xp(limit=limit)
    lines = ["🏆 <b>جدول المتصدرين — نقاط الخبرة XP</b>", ""]
    if not rows:
        return lines[0] + "\n• لا توجد بيانات متاحة."
    t_rows = [
        {
            "#": idx,
            "الاسم": ("⭐ " if row.get("is_premium") else "") + str(row.get("name") or row.get("custom_id") or str(row.get("uid", ""))[:8]),
            "XP": f"{int(row.get('xp') or 0):,}",
            "المستوى": row.get("level", 1),
        }
        for idx, row in enumerate(rows, 1)
    ]
    lines.append(format_table(t_rows, ["#", "الاسم", "XP", "المستوى"], max_col_width=16))
    lines.append("\nالترتيب: <code>/topusers xp</code> | <code>/topusers points</code>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# /edituser, /plans, /editplan, /notify, /quizzes, /deletequiz
# ---------------------------------------------------------------------------

@command("edituser")
async def handle_edituser(ctx: CommandContext) -> str:
    from bot.modules.admin_actions import service as admin_actions

    confirmed = "confirm" in ctx.args
    args = [a for a in ctx.args if a != "confirm"]
    if len(args) < 3:
        return (
            "الاستخدام: /edituser &lt;uid_or_email&gt; &lt;field&gt; &lt;value&gt;\n"
            "الحقول المتاحة: <code>name, custom_id, name_color, badge_color, is_admin, xp, level</code>"
        )
    identifier = args[0]
    field = args[1]
    raw_value = " ".join(args[2:])
    result = await admin_actions.edit_user_field(identifier, field, raw_value, confirmed=confirmed)
    return (
        "✏️ <b>تم تعديل بيانات المستخدم</b>\n"
        f"• المستخدم: {_esc(result.get('name') or result['uid'])} (<code>{_esc(result['uid'])}</code>)\n"
        f"• الحقل: <code>{_esc(result['field'])}</code> ← <b>{_esc(result['value'])}</b>"
    )


@command("plans")
async def handle_plans(ctx: CommandContext) -> str:
    from bot.db.repositories import platform_repo

    plans = await platform_repo.list_subscription_plans()
    if not plans:
        return "💎 <b>باقات الاشتراك</b>\n• لا توجد باقات مسجلة."
    lines = ["💎 <b>جدول باقات الاشتراك في الموقع</b>", ""]
    p_rows = []
    for p in plans:
        dur = "مدى الحياة" if p.get("is_lifetime") else f"{p.get('duration_months', 1)}ش"
        p_rows.append(
            {
                "ID": str(p.get("id") or ""),
                "الباقة": p.get("name_ar") or p.get("name") or "-",
                "السعر": f"{p.get('price', 0)} {p.get('currency', 'EGP')}",
                "المدة": dur,
                "الحالة": "نشط" if p.get("is_active") else "متوقف",
            }
        )
    lines.append(format_table(p_rows, ["ID", "الباقة", "السعر", "المدة", "الحالة"], max_col_width=14))
    lines.append("\nلتعديل باقة: <code>/editplan &lt;plan_id&gt; &lt;price|name|name_ar|duration_months|is_active&gt; &lt;value&gt;</code>")
    return "\n".join(lines)


@command("editplan")
async def handle_editplan(ctx: CommandContext) -> str:
    from bot.modules.admin_actions import service as admin_actions

    confirmed = "confirm" in ctx.args
    args = [a for a in ctx.args if a != "confirm"]
    if len(args) < 3:
        return (
            "الاستخدام: /editplan &lt;plan_id&gt; &lt;field&gt; &lt;value&gt;\n"
            "الحقول المتاحة: <code>price, name, name_ar, duration_months, is_active, is_lifetime, badge_style, badge_color, priority_level</code>"
        )
    plan_id = args[0]
    field = args[1]
    raw_value = " ".join(args[2:])
    result = await admin_actions.edit_subscription_plan(plan_id, field, raw_value, confirmed=confirmed)
    return (
        "💎 <b>تم تحديث باقة الاشتراك</b>\n"
        f"• الباقة: <code>{_esc(result['plan_id'])}</code>\n"
        f"• الحقل: <code>{_esc(result['field'])}</code> ← <b>{_esc(result['value'])}</b>"
    )


@command("notify")
async def handle_notify(ctx: CommandContext) -> str:
    from bot.modules.admin_actions import service as admin_actions

    confirmed = "confirm" in ctx.args
    args = [a for a in ctx.args if a != "confirm"]
    if len(args) < 2:
        return (
            "الاستخدام: /notify &lt;uid_or_email_or_all&gt; &lt;العنوان&gt; | &lt;نص الإشعار&gt;\n"
            "مثال: /notify all صيانة سريعة | سيتم تحديث السيرفر خلال 10 دقائق"
        )
    target = args[0]
    rest = " ".join(args[1:]).strip()
    if "|" in rest:
        notif_title, notif_body = (part.strip() for part in rest.split("|", 1))
    else:
        notif_title = "إشعار من الإدارة"
        notif_body = rest

    result = await admin_actions.send_platform_notification(
        target, notif_title, notif_body, confirmed=confirmed
    )
    return (
        "📢 <b>تم إرسال الإشعار داخل الموقع</b>\n"
        f"• المستهدف: {_esc(result['target_label'])}\n"
        f"• العنوان: <b>{_esc(result['title'])}</b>\n"
        f"• النص: {_esc(result['body'], 200)}"
    )


@command("quizzes")
async def handle_quizzes(ctx: CommandContext) -> str:
    from bot.db.repositories import platform_repo

    limit = 15
    if ctx.args and ctx.args[0].isdigit():
        limit = max(1, min(30, int(ctx.args[0])))
    quizzes = await platform_repo.list_recent_quizzes(limit=limit)
    if not quizzes:
        return "📝 <b>أحدث الاختبارات</b>\n• لا توجد اختبارات مسجلة."
    lines = [f"📝 <b>أحدث الاختبارات ({len(quizzes)})</b>", ""]
    for q in quizzes:
        vis = "🌐 عام" if q.get("is_public") else "🔒 خاص"
        lines.append(
            f"• <code>{_esc(str(q.get('id', ''))[:8])}</code> — <b>{_esc(q.get('title'), 45)}</b>\n"
            f"  {vis} | {q.get('total_plays', 0)} تشغيل | {_age(q.get('created_at'))}"
        )
    lines.append("\nلحذف اختبار: <code>/deletequiz &lt;quiz_id&gt;</code>")
    return "\n".join(lines)


@command("deletequiz")
async def handle_deletequiz(ctx: CommandContext) -> str:
    from bot.modules.admin_actions import service as admin_actions

    confirmed = "confirm" in ctx.args
    args = [a for a in ctx.args if a != "confirm"]
    if not args:
        return "الاستخدام: /deletequiz &lt;quiz_id&gt;"
    result = await admin_actions.delete_quiz(args[0], confirmed=confirmed)
    return (
        "🗑️ <b>تم حذف الاختبار</b>\n"
        f"• المعرّف: <code>{_esc(result['id'])}</code>\n"
        f"• العنوان: {_esc(result.get('title'))}"
    )


@command("envcheck")
async def handle_envcheck(ctx: CommandContext) -> str:
    from bot.config import settings

    checks = [
        ("TELEGRAM_BOT_TOKEN", bool(settings.telegram_bot_token), "إلزامي"),
        ("SUPABASE_URL", bool(settings.supabase_url), "إلزامي"),
        ("SUPABASE_SERVICE_ROLE_KEY", bool(settings.supabase_service_role_key), "إلزامي"),
        ("OWNER_USER_IDS", bool(settings.owner_user_ids), "إلزامي"),
        ("SUPABASE_WEBHOOK_SECRET", bool(settings.supabase_webhook_secret), "إشعارات الدفع"),
        ("TELEGRAM_ADMIN_CHAT_ID", bool(settings.telegram_admin_chat_id), "قناة الإدارة"),
        ("TELEGRAM_ALERT_CHANNEL_ID", bool(settings.telegram_alert_channel_id), "قناة التنبيهات"),
        ("AI_API_KEY", bool(settings.ai_api_key), f"الذكاء ({settings.ai_provider})"),
        ("GITHUB_TOKEN", bool(settings.github_token), "النشر والنسخ"),
        ("GITHUB_REPO", bool(settings.github_repo), "النشر والنسخ"),
        ("GITHUB_WEBHOOK_SECRET", bool(settings.github_webhook_secret), "Webhook النشر"),
        ("CLOUDFLARE_API_TOKEN", bool(settings.cloudflare_api_token), "Cloudflare"),
        ("CLOUDFLARE_ACCOUNT_ID", bool(settings.cloudflare_account_id), "Cloudflare"),
        ("SENTRY_AUTH_TOKEN", bool(settings.sentry_auth_token), "أخطاء Sentry"),
        ("SENTRY_WEBHOOK_SECRET", bool(settings.sentry_webhook_secret), "Webhook Sentry"),
        ("API_BASE_URL", bool(settings.api_base_url), "فحص الـ API"),
        ("UMAMI_API_KEY", bool(settings.umami_api_key), "إحصائيات Umami"),
        ("FIREBASE_PROJECT_ID", bool(settings.firebase_project_id), "Firebase"),
    ]

    rows = [
        {
            "المفتاح": name,
            "الحالة": "✅ مضبوط" if is_set else "❌ ناقص",
            "الوظيفة": purpose,
        }
        for name, is_set, purpose in checks
    ]
    configured_count = sum(1 for _, ok, _ in checks if ok)
    missing_required = [name for name, ok, purpose in checks if not ok and purpose == "إلزامي"]

    lines = [
        "🔑 <b>فحص المفاتيح السرية وإعدادات البيئة</b>",
        f"• الجاهزية: <b>{configured_count}/{len(checks)}</b> مضبوط (بدون عرض أي قيم سرية)",
        "",
        format_table(rows, ["المفتاح", "الحالة", "الوظيفة"], max_col_width=25),
    ]
    if missing_required:
        lines.append(f"⚠️ <b>مفاتيح إلزامية ناقصة:</b> {', '.join(missing_required)}")
    else:
        lines.append("✅ جميع المفاتيح الإلزامية مضبوطة.")
    return "\n".join(lines)
