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
from bot.utils.formatting import status_line
from bot.utils.style import title
from bot.utils.time_utils import humanize_delta


def _esc(value: Any, max_len: int = 80) -> str:
    if value is None:
        return "N/A"
    return html.escape(str(value).strip()[:max_len], quote=False)


def _fmt(value: Any, suffix: str = "") -> str:
    if value is None:
        return "N/A"
    return f"{value}{suffix}"


def _age(iso_value: Any) -> str:
    if not isinstance(iso_value, str) or not iso_value.strip():
        return "unknown"
    try:
        dt = datetime.fromisoformat(iso_value.strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return humanize_delta(dt)
    except ValueError:
        return "unknown"


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
        f"{title('Quiz Space Operations Bot', 'wave')}\n\n"
        "Live monitoring, platform pulse, AI pipeline telemetry, payment queue, "
        "and deployment control for Quiz Space.\n\n"
        "Use the buttons below or send /help for all commands."
    )


_HELP_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "Live Telemetry & Pulse",
        [
            ("status", "Service health, realtime & open incidents"),
            ("dashboard", "Full executive snapshot (users, quizzes, AI, ops)"),
            ("pulse", "Live platform activity (sessions, completions, top quizzes)"),
            ("ai", "AI pipeline logs & extraction job queue"),
            ("payments", "Pending premium activation requests"),
            ("incidents", "Open/recent incidents & 24h service uptime"),
        ],
    ),
    (
        "Users, Memberships & Points",
        [
            ("users", "User growth, premium conversion & newest signups"),
            ("user", "Full user details, plan, points & requests"),
            ("payments", "Pending & recent subscription payment requests"),
            ("approve", "Approve a pending payment request (Owner)"),
            ("reject", "Reject a pending payment request (Owner)"),
            ("membership", "Change user plan (free/silver/gold/diamond/lifetime/founder)"),
            ("suspend", "Suspend or unsuspend a user account (Owner)"),
            ("setbadge", "Update user badge_tier (Owner)"),
            ("points", "Points leaderboard or one user's balance & ledger"),
            ("grantpoints", "Add or deduct user reward points (Owner)"),
            ("orders", "Reward store orders queue"),
            ("approveorder", "Approve reward store order & credit points (Owner)"),
            ("rejectorder", "Reject reward store order (Owner)"),
        ],
    ),
    (
        "Platform Controls",
        [
            ("platform", "View/toggle maintenance mode & registration (Owner)"),
            ("trial", "View/toggle trial offer durations 7/14/30 days (Owner)"),
            ("coupon", "List, create, activate, deactivate, or delete coupons (Owner)"),
            ("vitals", "Web Vitals report: CLS, LCP, FCP, INP, TTFB — p75 & avg"),
            ("topusers", "Top users leaderboard by XP or reward points"),
        ],
    ),
    (
        "Analytics & AI Assistant",
        [
            ("analytics", "Platform analytics, Web Vitals & Umami traffic"),
            ("reports", "Periodic & performance reports (daily/weekly/monthly/performance)"),
            ("ask", "Ask the AI ops assistant about live metrics"),
        ],
    ),
    (
        "Infrastructure & Security",
        [
            ("database", "DB health, 24h uptime & table row counts"),
            ("storage", "Storage buckets & object counts"),
            ("system", "GitHub, Cloudflare Pages & Firebase status"),
            ("errors", "Sentry issues + recent AI/extraction errors"),
            ("security", "Dependabot alerts & unauthorized access attempts"),
            ("logs", "Recent bot command audit trail"),
        ],
    ),
    (
        "Deployment & Admin",
        [
            ("deploy", "Trigger production deployment"),
            ("build", "Trigger build workflow"),
            ("rollback", "Rollback production deployment (Owner)"),
            ("backup", "Trigger or list backups"),
            ("restore", "Restore from backup (Owner)"),
            ("settings", "View/update runtime settings (Owner)"),
            ("setrole", "Grant ADMIN/VIEWER role (Owner)"),
        ],
    ),
]


@command("help")
async def handle_help(ctx: CommandContext) -> str:
    known = set(registered_commands())
    lines = [title("Available Commands"), ""]
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
        lines.append("<b>Other</b>")
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
        title("Quiz Space — System Status", "dashboard"),
        status_line(
            "Website",
            website["status"],
            f"{website['latency_ms']}ms" if website.get("latency_ms") is not None else "",
        ),
        status_line(
            "API",
            api["status"],
            f"{api['latency_ms']}ms" if api.get("latency_ms") is not None else "",
        ),
        status_line("Database", database["status"], f"{database.get('latency_ms', '?')}ms"),
        status_line("Storage", storage["status"], f"{storage.get('bucket_count', 0)} buckets"),
    ]

    if realtime.get("status") != "not configured":
        rt_extra = f"{realtime['latency_ms']}ms" if realtime.get("latency_ms") is not None else ""
        lines.append(status_line("Realtime", realtime["status"], rt_extra))

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
                lines.append("<b>24h Uptime:</b> " + " | ".join(uptime_parts))
        lines.append(f"🚨 Open incidents: {len(open_inc)}")
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
        deployment_status = deployment.get("conclusion") or deployment.get("status") or "unknown"
    except ConfigurationError as exc:
        deployment_status = f"Not configured — {exc}"
    except Exception as exc:  # noqa: BLE001
        deployment_status = f"Unavailable ({_esc(exc, 60)})"

    error_count = analytics.get("error_count")
    lines = [
        title("Quiz Space — Dashboard", "reports"),
        f"Last deployment: {_esc(deployment_status)}",
        f"Errors (24h): {error_count if error_count is not None else 'N/A'}",
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
                "<b>Users &amp; Sessions</b>",
                f"• Total: {_fmt(users.get('total'))} | Premium: {_fmt(users.get('premium'))} | "
                f"New (24h): {_fmt(users.get('signups_recent'))}",
                f"• Active sessions: 1h={_fmt(users.get('active_1h'))} | 24h={_fmt(users.get('active_24h'))}",
                "",
                "<b>Quiz Activity (24h)</b>",
                f"• Quizzes: {_fmt(activity.get('total_quizzes'))} (+{_fmt(activity.get('quizzes_recent'))} new) | "
                f"Classrooms: {_fmt(activity.get('total_classrooms'))}",
                f"• Completions: {_fmt(activity.get('completions_recent'))} | "
                f"Guests: {_fmt(activity.get('guest_attempts_recent'))} | "
                f"Avg score: {_fmt(activity.get('avg_score_pct'), '%')}",
                f"• Cosmo chats (24h): {_fmt(activity.get('cosmo_conversations_recent'))}",
                "",
                "<b>AI &amp; Extraction (24h)</b>",
                f"• AI calls: {_fmt(ai.get('total_calls'))} | "
                f"Success: {_fmt(ai.get('success_rate_pct'), '%')} | "
                f"Avg/P95: {_fmt(ai.get('avg_latency_ms'), 'ms')} / {_fmt(ai.get('p95_latency_ms'), 'ms')}",
                f"• Extraction: active={_fmt((extraction.get('pending_count') or 0) + (extraction.get('processing_count') or 0))}, "
                f"done={_fmt(extraction.get('complete_recent'))}, err={_fmt(extraction.get('error_recent'))}, "
                f"stuck={len(extraction.get('stuck_jobs') or [])}",
                "",
                "<b>Operations</b>",
                f"• Pending payments: {_fmt(payments.get('pending_count'))} | "
                f"Needs info: {_fmt(payments.get('needs_info_count'))} | "
                f"Open incidents: {len(open_incidents)}",
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
        f"⚡ <b>Quiz Space Live Pulse ({label})</b>",
        "",
        "<b>Audience</b>",
        f"• Users: {_fmt(users.get('total'))} (Premium: {_fmt(users.get('premium'))})",
        f"• New signups ({label}): {_fmt(users.get('signups_recent'))}",
        f"• Active sessions: 1h={_fmt(users.get('active_1h'))} | 24h={_fmt(users.get('active_24h'))}",
        "",
        "<b>Learning &amp; Engagement</b>",
        f"• Quizzes created ({label}): {_fmt(activity.get('quizzes_recent'))} (total {_fmt(activity.get('total_quizzes'))})",
        f"• Completions ({label}): {_fmt(activity.get('completions_recent'))} | Avg score: {_fmt(activity.get('avg_score_pct'), '%')}",
        f"• Guest attempts ({label}): {_fmt(activity.get('guest_attempts_recent'))}",
        f"• Cosmo conversations ({label}): {_fmt(activity.get('cosmo_conversations_recent'))}",
    ]

    top_quizzes = activity.get("top_quizzes") or []
    if top_quizzes:
        lines.append("")
        lines.append("<b>Top Quizzes (All-time plays)</b>")
        for q in top_quizzes[:3]:
            lines.append(
                f"• {_esc(q.get('title'), 42)} — {q.get('total_plays', 0)} plays"
            )

    lines.extend(
        [
            "",
            "<b>Pipeline &amp; Ops</b>",
            f"• AI ({label}): {_fmt(ai.get('total_calls'))} calls, "
            f"{_fmt(ai.get('success_rate_pct'), '%')} ok, "
            f"{_fmt(ai.get('avg_latency_ms'), 'ms')} avg",
            f"• Extraction queue: pending={_fmt(extraction.get('pending_count'))}, "
            f"processing={_fmt(extraction.get('processing_count'))}, "
            f"stuck={len(extraction.get('stuck_jobs') or [])}",
            f"• Pending payments: {_fmt(payments.get('pending_count'))} | Open incidents: {len(open_incidents)}",
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

    lines = [f"🤖 <b>AI &amp; Extraction Health ({label})</b>", ""]

    if not ai.get("available", True):
        lines.append("• AI logs: unavailable")
    else:
        lines.extend(
            [
                "<b>AI Performance Logs</b>",
                f"• Total calls: {ai.get('total_calls', 0)} (✅ {ai.get('success_count', 0)} / ❌ {ai.get('error_count', 0)})",
                f"• Success rate: {_fmt(ai.get('success_rate_pct'), '%')}",
                f"• Latency: avg {_fmt(ai.get('avg_latency_ms'), 'ms')} | p95 {_fmt(ai.get('p95_latency_ms'), 'ms')}",
            ]
        )
        by_provider = ai.get("by_provider") or {}
        if by_provider:
            lines.append("• By provider:")
            for prov, stats in sorted(by_provider.items(), key=lambda item: -item[1]["calls"]):
                lines.append(
                    f"  - {_esc(prov)}: {stats['calls']} calls, {stats['errors']} err, "
                    f"avg {_fmt(stats.get('avg_latency_ms'), 'ms')}"
                )
        by_op = ai.get("by_operation") or {}
        if by_op:
            op_parts = [f"{_esc(op)}={st['calls']}({st['errors']} err)" for op, st in sorted(by_op.items())]
            lines.append("• By operation: " + ", ".join(op_parts))

        recent_errors = ai.get("recent_errors") or []
        if recent_errors:
            lines.append("")
            lines.append("<b>Recent AI Errors</b>")
            for err in recent_errors[:5]:
                cat = err.get("error_category") or "error"
                msg = err.get("error_message") or "no details"
                lines.append(
                    f"• [{_esc(err.get('provider'))}/{_esc(err.get('operation'))}] "
                    f"{_esc(cat)}: {_esc(msg, 70)} ({_age(err.get('created_at'))})"
                )

    lines.append("")
    if not ext.get("available", True):
        lines.append("• Extraction jobs: unavailable")
    else:
        stuck = ext.get("stuck_jobs") or []
        lines.extend(
            [
                "<b>Extraction Queue</b>",
                f"• Active: pending={ext.get('pending_count', 0)}, processing={ext.get('processing_count', 0)}, stuck={len(stuck)}",
                f"• Last {label}: complete={ext.get('complete_recent', 0)}, failed={ext.get('error_recent', 0)}",
            ]
        )
        if stuck:
            lines.append("• Stuck jobs:")
            for job in stuck[:3]:
                lines.append(
                    f"  - #{_esc(str(job.get('id', ''))[:8])} ({job.get('progress_percentage', 0)}%, "
                    f"updated {_age(job.get('updated_at'))})"
                )
        ext_errors = ext.get("recent_errors") or []
        if ext_errors:
            lines.append("• Recent extraction failures:")
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
        f"💳 <b>Subscription &amp; Payment Queue ({'All Recent' if show_all else 'Pending'})</b>",
        f"• Pending review: {_fmt(pending_count)} | Needs info: {_fmt(needs_info)}",
        f"• Last 7d decisions: ✅ {_fmt(approved_7d)} approved | ❌ {_fmt(rejected_7d)} rejected",
    ]
    if items:
        lines.append("")
        lines.append("<b>Requests</b>")
        for req in items:
            req_id = str(req.get("id") or "")
            short_id = req_id[:8]
            plan = _esc(req.get("plan_name") or "unknown", 40)
            req_status = _esc(req.get("status") or "pending", 20)
            who = _esc(req.get("name") or req.get("user_id") or "user", 32)
            email = req.get("email")
            email_txt = f" &lt;{_esc(email, 45)}&gt;" if email else ""
            shot = str(req.get("payment_screenshot") or "").strip()
            proof_tag = " [Trial]" if shot.startswith("TRIAL_OFFER_") else (" [Receipt]" if shot else "")
            lines.append(
                f"• <code>{_esc(short_id)}</code> — {who}{email_txt}\n"
                f"  Plan: {plan} | Status: {req_status}{proof_tag} ({_age(req.get('created_at'))})"
            )
            if req.get("reject_reason"):
                lines.append(f"  Reason: {_esc(req.get('reject_reason'), 80)}")
        lines.append("")
        lines.append("Actions: <code>/approve &lt;id&gt;</code> | <code>/reject &lt;id&gt; [reason]</code>")
    else:
        lines.append("\n✅ No pending payment requests.")

    return "\n".join(lines)


@command("approve")
async def handle_approve(ctx: CommandContext) -> str:
    from bot.modules.admin_actions import service as admin_actions

    if not ctx.args:
        return "Usage: /approve <request_id>"
    confirmed = "confirm" in ctx.args
    request_id = next((a for a in ctx.args if a != "confirm"), "")
    if not request_id:
        return "Usage: /approve <request_id>"

    result = await admin_actions.approve_payment(request_id, confirmed=confirmed)
    return (
        "✅ <b>Payment Approved &amp; Subscription Activated</b>\n"
        f"• Request: <code>{_esc(result['request_id'])}</code>\n"
        f"• User: {_esc(result.get('user_name') or result['user_id'])} (<code>{_esc(result['user_id'])}</code>)\n"
        f"• Plan: {_esc(result['plan_name'])} (<code>{_esc(result['plan_id'])}</code>)\n"
        f"• Renewal: {_esc(result.get('renewal_date'))}"
    )


@command("reject")
async def handle_reject(ctx: CommandContext) -> str:
    from bot.modules.admin_actions import service as admin_actions

    if not ctx.args:
        return "Usage: /reject <request_id> [reason]"
    confirmed = "confirm" in ctx.args
    args = [a for a in ctx.args if a != "confirm"]
    if not args:
        return "Usage: /reject <request_id> [reason]"
    request_id = args[0]
    reason = " ".join(args[1:]).strip()

    result = await admin_actions.reject_payment(request_id, reason=reason, confirmed=confirmed)
    return (
        "❌ <b>Payment Request Rejected</b>\n"
        f"• Request: <code>{_esc(result['request_id'])}</code>\n"
        f"• User: {_esc(result.get('user_name') or result['user_id'])}\n"
        f"• Reason: {_esc(result.get('reject_reason'))}"
    )


@command("membership")
async def handle_membership(ctx: CommandContext) -> str:
    from bot.modules.admin_actions import service as admin_actions

    args = [a for a in ctx.args if a != "confirm"]
    confirmed = "confirm" in ctx.args
    if len(args) < 2:
        return (
            "Usage: /membership <uid_or_email> <free|silver|gold|diamond|lifetime|founder> [days]\n"
            "Example: /membership user@example.com gold 30"
        )
    identifier, plan_key = args[0], args[1]
    days: int | None = None
    if len(args) >= 3:
        if not args[2].isdigit() or int(args[2]) <= 0:
            return "Days must be a positive whole number."
        days = int(args[2])

    result = await admin_actions.set_membership(identifier, plan_key, days=days, confirmed=confirmed)
    return (
        "⭐ <b>Membership Updated</b>\n"
        f"• User: {_esc(result.get('name') or result['uid'])} (<code>{_esc(result['uid'])}</code>)\n"
        f"• Premium: {result['is_premium']} | Plan: {_esc(result['plan_name'])}\n"
        f"• Lifetime: {result['is_lifetime']} | Founder: {result['is_founder']}\n"
        f"• Renewal: {_esc(result.get('renewal_date'))}"
    )


@command("suspend")
async def handle_suspend(ctx: CommandContext) -> str:
    from bot.modules.admin_actions import service as admin_actions

    args = [a for a in ctx.args if a != "confirm"]
    confirmed = "confirm" in ctx.args
    if len(args) < 2 or args[1].lower() not in ("on", "off", "true", "false"):
        return "Usage: /suspend <uid_or_email> <on|off>"
    identifier = args[0]
    suspended = args[1].lower() in ("on", "true")

    result = await admin_actions.set_suspension(identifier, suspended=suspended, confirmed=confirmed)
    state_label = "Suspended 🚫" if result["is_suspended"] else "Active ✅"
    return (
        "🛡️ <b>Account Status Updated</b>\n"
        f"• User: {_esc(result.get('name') or result['uid'])} (<code>{_esc(result['uid'])}</code>)\n"
        f"• Status: {state_label}"
    )


@command("setbadge")
async def handle_setbadge(ctx: CommandContext) -> str:
    from bot.modules.admin_actions import service as admin_actions

    args = [a for a in ctx.args if a != "confirm"]
    confirmed = "confirm" in ctx.args
    if len(args) < 2:
        return "Usage: /setbadge <uid_or_email> <none|pro|premium|team|enterprise|lifetime|founder>"
    result = await admin_actions.set_badge_tier(args[0], args[1], confirmed=confirmed)
    return (
        "🏅 <b>Badge Tier Updated</b>\n"
        f"• User: {_esc(result.get('name') or result['uid'])} (<code>{_esc(result['uid'])}</code>)\n"
        f"• badge_tier: <code>{_esc(result['badge_tier'])}</code>"
    )


@command("points")
async def handle_points(ctx: CommandContext) -> str:
    from bot.modules.admin_actions import service as admin_actions

    if ctx.args:
        detail = await admin_actions.get_user_points_detail(ctx.args[0])
        bal = detail.get("balance") or {}
        lines = [
            f"🏆 <b>Points &amp; Rewards — {_esc(detail.get('name') or detail['uid'])}</b>",
            f"• UID: <code>{_esc(detail['uid'])}</code>",
            f"• Points: <b>{bal.get('points', 0):,}</b> | Coins: {bal.get('coins', 0):,} | Reward Level: {bal.get('level', 1)}",
            f"• Quiz XP: {detail.get('xp', 0):,} | Profile Level: {detail.get('user_level', 1)}",
        ]
        ledger = detail.get("ledger") or []
        if ledger:
            lines.append("")
            lines.append("<b>Recent Points Ledger</b>")
            for entry in ledger[:10]:
                pts = int(entry.get("points") or 0)
                sign = "+" if pts >= 0 else ""
                note = ((entry.get("metadata") or {}).get("note") or "") if isinstance(entry.get("metadata"), dict) else ""
                note_txt = f" ({_esc(note, 45)})" if note else ""
                lines.append(
                    f"• {sign}{pts} pts — {_esc(entry.get('event_type'))}{note_txt} ({_age(entry.get('created_at'))})"
                )
        lines.append("\nAdjust: <code>/grantpoints &lt;uid_or_email&gt; &lt;+/-amount&gt; [note]</code>")
        return "\n".join(lines)

    overview = await admin_actions.get_points_overview(limit=10)
    top_bal = overview.get("top_balances") or []
    recent_led = overview.get("recent_ledger") or []
    lines = ["🏆 <b>Points &amp; Rewards Overview</b>", ""]
    if top_bal:
        lines.append("<b>Top Balances</b>")
        for idx, row in enumerate(top_bal, start=1):
            lines.append(
                f"{idx}. {_esc(row.get('display_name'), 28)} (<code>{_esc(str(row.get('user_id', ''))[:8])}</code>) — "
                f"{int(row.get('points') or 0):,} pts | {int(row.get('coins') or 0):,} coins | Lvl {row.get('level', 1)}"
            )
    else:
        lines.append("• No reward balances recorded yet.")

    if recent_led:
        lines.append("")
        lines.append("<b>Recent Points Transactions</b>")
        for entry in recent_led[:8]:
            pts = int(entry.get("points") or 0)
            sign = "+" if pts >= 0 else ""
            lines.append(
                f"• <code>{_esc(str(entry.get('user_id', ''))[:8])}</code>: {sign}{pts} pts "
                f"[{_esc(entry.get('event_type'))}] ({_age(entry.get('created_at'))})"
            )

    lines.append("\nUser lookup: <code>/points &lt;uid_or_email&gt;</code> | Adjust: <code>/grantpoints &lt;uid_or_email&gt; &lt;+/-amount&gt; [note]</code>")
    return "\n".join(lines)


@command("grantpoints")
async def handle_grantpoints(ctx: CommandContext) -> str:
    from bot.modules.admin_actions import service as admin_actions

    confirmed = "confirm" in ctx.args
    args = [a for a in ctx.args if a != "confirm"]
    if len(args) < 2:
        return "Usage: /grantpoints <uid_or_email> <+/-amount> [note]"
    identifier = args[0]
    try:
        delta = int(args[1])
    except ValueError:
        return "Amount must be a whole number (e.g. 500 or -100)."
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
        "🏆 <b>Points Updated</b>\n"
        f"• User: {_esc(result.get('name') or result['uid'])} (<code>{_esc(result['uid'])}</code>)\n"
        f"• Change: {sign}{result['delta']:,} pts\n"
        f"• Balance: {result['previous_points']:,} → <b>{result['total_points']:,}</b> pts (Level {result['level']})"
    )


@command("orders")
async def handle_orders(ctx: CommandContext) -> str:
    from bot.modules.admin_actions import service as admin_actions

    orders = await admin_actions.list_reward_orders(limit=15)
    lines = ["🎁 <b>Reward Store Orders</b>", ""]
    if not orders:
        lines.append("✅ No reward store orders found.")
        return "\n".join(lines)

    for order in orders:
        oid = str(order.get("id") or "")
        lines.append(
            f"• <code>{_esc(oid[:8])}</code> — item={_esc(order.get('item_id'))} | "
            f"status=<b>{_esc(order.get('status'))}</b> | "
            f"{order.get('amount_egp', 0)} EGP / {order.get('amount_points', 0)} pts "
            f"[{_esc(order.get('payment_method'))}] ({_age(order.get('created_at'))})"
        )
        if order.get("payment_reference"):
            lines.append(f"  Ref: <code>{_esc(order.get('payment_reference'), 60)}</code>")
    lines.append("\nActions: <code>/approveorder &lt;id&gt;</code> | <code>/rejectorder &lt;id&gt; [note]</code>")
    return "\n".join(lines)


@command("approveorder")
async def handle_approveorder(ctx: CommandContext) -> str:
    from bot.modules.admin_actions import service as admin_actions

    confirmed = "confirm" in ctx.args
    args = [a for a in ctx.args if a != "confirm"]
    if not args:
        return "Usage: /approveorder <order_id> [note]"
    result = await admin_actions.review_order(
        args[0],
        "approved",
        note=" ".join(args[1:]),
        admin_telegram_id=ctx.user_id,
        confirmed=confirmed,
    )
    return (
        "✅ <b>Reward Order Approved</b>\n"
        f"• Order: <code>{_esc(result['order_id'])}</code>\n"
        f"• User: <code>{_esc(result['user_id'])}</code>\n"
        f"• Points added: +{result.get('points_added', 0):,} (New total: {result.get('total_points', 0):,}, Level {result.get('level', 1)})"
    )


@command("rejectorder")
async def handle_rejectorder(ctx: CommandContext) -> str:
    from bot.modules.admin_actions import service as admin_actions

    confirmed = "confirm" in ctx.args
    args = [a for a in ctx.args if a != "confirm"]
    if not args:
        return "Usage: /rejectorder <order_id> [note]"
    result = await admin_actions.review_order(
        args[0],
        "rejected",
        note=" ".join(args[1:]),
        admin_telegram_id=ctx.user_id,
        confirmed=confirmed,
    )
    return (
        "❌ <b>Reward Order Rejected</b>\n"
        f"• Order: <code>{_esc(result['order_id'])}</code>\n"
        f"• User: <code>{_esc(result['user_id'])}</code>"
    )


@command("incidents")
async def handle_incidents(ctx: CommandContext) -> str:
    from bot.modules.platform_insights import service as insights_service

    hours, label = _parse_hours_arg(ctx.args, default_hours=24)
    data = await insights_service.get_uptime_and_incidents(hours=hours)
    open_incidents = data.get("open_incidents") or []
    recent_incidents = data.get("recent_incidents") or []
    services = data.get("services") or {}

    lines = [f"🚨 <b>Incidents &amp; Uptime ({label})</b>", ""]
    if open_incidents:
        lines.append(f"<b>Open Incidents ({len(open_incidents)})</b>")
        for inc in open_incidents:
            lines.append(
                f"• 🔴 <b>{_esc(inc.get('service'))}</b> — {_esc(inc.get('details'), 80)} "
                f"(opened {_age(inc.get('opened_at'))})"
            )
    else:
        lines.append("🟢 No open incidents.")

    if services:
        lines.append("")
        lines.append(f"<b>Service Uptime ({label})</b>")
        for svc, st in sorted(services.items()):
            lines.append(
                f"• {_esc(svc)}: {_fmt(st.get('uptime_pct'), '%')} "
                f"({st.get('checks', 0)} checks, avg {_fmt(st.get('avg_latency_ms'), 'ms')})"
            )

    resolved = [i for i in recent_incidents if i.get("resolved_at")]
    if resolved:
        lines.append("")
        lines.append("<b>Recent Resolved Incidents</b>")
        for inc in resolved[:5]:
            lines.append(
                f"• ✅ {_esc(inc.get('service'))}: {_esc(inc.get('details'), 60)} "
                f"(opened {_age(inc.get('opened_at'))})"
            )

    return "\n".join(lines)


# --- Users -----------------------------------------------------------------

@command("users")
async def handle_users(ctx: CommandContext) -> str:
    from bot.modules.users import service as users_service

    summary = await users_service.get_user_summary()
    total = summary.get("total_users", 0)
    premium = summary.get("premium_users", 0)
    pct = f"{(premium / total) * 100:.1f}%" if total else "0.0%"
    recent = summary.get("recent_signups") or []

    lines = [
        title("Users", "users"),
        f"Total: {total}",
        f"Premium: {premium} ({pct})",
        f"Recent signups: {len(recent)}",
    ]

    extra_parts = []
    if summary.get("signups_24h") is not None:
        extra_parts.append(f"24h: +{summary['signups_24h']}")
    if summary.get("signups_7d") is not None:
        extra_parts.append(f"7d: +{summary['signups_7d']}")
    if summary.get("active_sessions_24h") is not None:
        extra_parts.append(f"Active 24h: {summary['active_sessions_24h']}")
    if summary.get("suspended_users") is not None:
        extra_parts.append(f"Suspended: {summary['suspended_users']}")
    if summary.get("pending_payments") is not None:
        extra_parts.append(f"Pending payments: {summary['pending_payments']}")
    if extra_parts:
        lines.append(" | ".join(extra_parts))

    if recent:
        lines.append("")
        lines.append("<b>Newest Signups</b>")
        for u in recent[:5]:
            uid_short = str(u.get("uid") or "")[:8]
            display_name = _esc(u.get("name") or uid_short or "user", 32)
            tier = "⭐ Premium" if u.get("is_premium") else "Free"
            lines.append(f"• {display_name} ({_esc(uid_short)}) — {tier} ({_age(u.get('created_at'))})")

    return "\n".join(lines)


_UID_RE = re.compile(r"^[A-Za-z0-9._-]{3,64}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@command("user")
async def handle_user(ctx: CommandContext) -> str:
    from bot.modules.admin_actions import service as admin_actions
    from bot.modules.users import service as users_service

    if not ctx.args:
        return "Usage: /user <uid_or_email_or_custom_id>"
    identifier = ctx.args[0]
    if not (_UID_RE.match(identifier) or _EMAIL_RE.match(identifier)):
        return "Invalid identifier — expected a user uid, custom_id, or email address."

    full_profile = None
    try:
        full_profile = await admin_actions.get_user_full_profile(identifier)
    except Exception:  # noqa: BLE001
        full_profile = None

    if full_profile is None:
        detail = await users_service.get_user_detail(identifier)
        if detail is None:
            return f"No user found matching '{_esc(identifier)}'."
        preferred_keys = (
            "name", "email", "is_premium", "plan_name", "is_lifetime",
            "is_founder", "is_admin", "is_suspended", "badge_tier", "onboarded", "created_at",
        )
        lines = [f"{k}: {_esc(detail.get(k))}" for k in preferred_keys if k in detail]
        return f"{title('User', 'users')}\nuid: {_esc(detail.get('uid'))}\n" + "\n".join(lines)

    u = full_profile["user"]
    bal = full_profile.get("reward_balance") or {}
    ledger = full_profile.get("recent_ledger") or []
    reqs = full_profile.get("recent_requests") or []

    lines = [
        f"{title('User Full Profile', 'users')}",
        f"• UID: <code>{_esc(u.get('uid'))}</code>"
        + (f" | Custom ID: <code>{_esc(u.get('custom_id'))}</code>" if u.get("custom_id") else ""),
        f"• Name: {_esc(u.get('name'))} | Email: {_esc(u.get('email'))}",
        f"• Admin: {bool(u.get('is_admin'))} | Suspended: {bool(u.get('is_suspended'))} | Onboarded: {bool(u.get('onboarded'))}",
        f"• Created: {_age(u.get('created_at'))}",
        "",
        "<b>Membership &amp; Badges</b>",
        f"• Premium: {bool(u.get('is_premium'))} | Plan: {_esc(u.get('plan_name'))} (<code>{_esc(u.get('plan_id'))}</code>)",
        f"• Lifetime: {bool(u.get('is_lifetime'))} | Founder: {bool(u.get('is_founder'))}",
        f"• Renewal: {_esc(u.get('renewal_date') or u.get('premium_until'))}",
        f"• Badge tier: <code>{_esc(u.get('badge_tier'))}</code> | Name color: <code>{_esc(u.get('name_color'))}</code>",
        "",
        "<b>Points &amp; Progression</b>",
        f"• Reward Points: <b>{int(bal.get('points') or 0):,}</b> | Coins: {int(bal.get('coins') or 0):,} | Reward Level: {bal.get('level', 1)}",
        f"• XP: {int(u.get('xp') or 0):,} | Profile Level: {u.get('level', 1)}",
    ]

    if ledger:
        lines.append("")
        lines.append("<b>Recent Points Ledger</b>")
        for entry in ledger[:5]:
            pts = int(entry.get("points") or 0)
            sign = "+" if pts >= 0 else ""
            lines.append(f"• {sign}{pts} pts — {_esc(entry.get('event_type'))} ({_age(entry.get('created_at'))})")

    if reqs:
        lines.append("")
        lines.append("<b>Recent Subscription Requests</b>")
        for req in reqs[:5]:
            lines.append(
                f"• <code>{_esc(str(req.get('id', ''))[:8])}</code> — {_esc(req.get('plan_name'))} "
                f"[{_esc(req.get('status'))}] ({_age(req.get('created_at'))})"
            )

    lines.extend(
        [
            "",
            "<b>Quick Admin Actions</b>",
            f"• Plan: <code>/membership {_esc(u.get('uid'))} &lt;free|silver|gold|diamond|lifetime|founder&gt; [days]</code>",
            f"• Points: <code>/grantpoints {_esc(u.get('uid'))} &lt;+/-amount&gt; [note]</code>",
            f"• Suspend: <code>/suspend {_esc(u.get('uid'))} &lt;on|off&gt;</code>",
        ]
    )
    return "\n".join(lines)


# --- Infrastructure ----------------------------------------------------------

@command("database")
async def handle_database(ctx: CommandContext) -> str:
    from bot.modules.database_monitor import service as database_monitor
    from bot.modules.platform_insights import service as insights_service

    result = await database_monitor.check_database()
    lines = [status_line("Database", result["status"], f"{result['latency_ms']}ms")]

    try:
        overview = await insights_service.get_database_overview()
        db_stats = overview.get("db_stats_24h") or {}
        if db_stats.get("uptime_pct") is not None:
            lines.append(
                f"• 24h uptime: {db_stats['uptime_pct']}% "
                f"(avg {_fmt(db_stats.get('avg_latency_ms'), 'ms')}, {db_stats.get('checks', 0)} checks)"
            )
        counts = overview.get("table_counts") or {}
        valid_counts = [(tbl, cnt) for tbl, cnt in counts.items() if cnt is not None]
        if valid_counts:
            lines.append("")
            lines.append("<b>Table Row Counts</b>")
            for tbl, cnt in valid_counts:
                lines.append(f"• {html.escape(tbl)}: {cnt:,}")
    except Exception:  # noqa: BLE001
        pass

    return "\n".join(lines)


@command("storage")
async def handle_storage(ctx: CommandContext) -> str:
    from bot.modules.storage_monitor import service as storage_monitor

    result = await storage_monitor.check_storage()
    lines = [status_line("Storage", result["status"], f"{result['bucket_count']} buckets")]
    buckets = result.get("buckets") or []
    if buckets:
        lines.append("")
        lines.append("<b>Buckets</b>")
        for b in buckets:
            vis = "public" if b.get("public") else "private"
            entries = b.get("entries_sample")
            count_note = f", {entries}+ items" if entries is not None else ""
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
        gh_line = f"GitHub: Not configured ({_esc(exc, 60)})"
    except Exception as exc:  # noqa: BLE001
        gh_line = f"GitHub: Unavailable ({_esc(exc, 60)})"

    try:
        cf = await cloudflare_service.get_deployment_status()
        cf_line = f"Cloudflare Pages: {_esc(cf.get('status', 'unknown'))}"
        if cf.get("url"):
            cf_line += f" ({_esc(cf['url'], 60)})"
    except ConfigurationError as exc:
        cf_line = f"Cloudflare Pages: Not configured ({_esc(exc, 60)})"
    except Exception as exc:  # noqa: BLE001
        cf_line = f"Cloudflare Pages: Unavailable ({_esc(exc, 60)})"

    fb = await firebase_service.get_status()
    fb_line = f"Firebase: {_esc(fb.get('status', 'unknown'))}"

    return "\n".join(["🖥️ <b>System Overview</b>", gh_line, cf_line, fb_line])


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
        return "No recent activity."
    lines = []
    for log in logs:
        icon = "❌" if log.get("error") else "✅"
        lines.append(
            f"{icon} /{_esc(log.get('command'))} — {log.get('duration_ms', '?')}ms ({_age(log.get('created_at'))})"
        )
    return "📜 <b>Recent Activity</b>\n" + "\n".join(lines)


@command("errors")
async def handle_errors(ctx: CommandContext) -> str:
    from bot.integrations import sentry_client
    from bot.modules.platform_insights import service as insights_service

    hours, label = _parse_hours_arg(ctx.args, default_hours=24)
    lines = [f"🐛 <b>Full Error &amp; Diagnostics Report ({label})</b>", ""]

    try:
        issues = await sentry_client.get_recent_issues(limit=10)
        if not issues:
            lines.append("• Sentry: ✅ No unresolved issues.")
        else:
            lines.append(f"<b>Sentry Issues ({len(issues)})</b>")
            for issue in issues:
                culprit = issue.get("culprit")
                culprit_txt = f" [{_esc(culprit, 40)}]" if culprit else ""
                lines.append(
                    f"• {_esc(issue.get('title', 'Unknown error'), 90)}{culprit_txt} "
                    f"({issue.get('count', '?')}x, {_esc(issue.get('level', 'error'))})"
                )
    except ConfigurationError:
        lines.append("• Sentry: Not configured")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"• Sentry: Unavailable ({_esc(exc, 80)})")

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
            lines.append(f"<b>Open Incidents ({len(open_incidents)})</b>")
            for inc in open_incidents:
                lines.append(
                    f"• 🔴 <b>{_esc(inc.get('service'))}</b>: {_esc(inc.get('details'), 120)} "
                    f"(opened {_age(inc.get('opened_at'))})"
                )
        else:
            lines.append("• Open Incidents: ✅ None")

        lines.append("")
        if ai_errors:
            lines.append(
                f"<b>AI Pipeline Errors ({ai_data.get('error_count', len(ai_errors))} total in {label})</b>"
            )
            for err in ai_errors[:10]:
                uid_short = str(err.get("user_id") or "")[:8] or "anon"
                model_txt = f"/{_esc(err.get('model'), 28)}" if err.get("model") else ""
                lat_txt = f" {err['latency_ms']}ms" if err.get("latency_ms") is not None else ""
                lines.append(
                    f"• [{_esc(err.get('provider'))}{model_txt} | {_esc(err.get('operation'))}{lat_txt} | u:{_esc(uid_short)}] "
                    f"<b>{_esc(err.get('error_category') or 'error')}</b>: "
                    f"{_esc(err.get('error_message') or 'No message', 180)} ({_age(err.get('created_at'))})"
                )
        else:
            lines.append(f"• AI Errors ({label}): ✅ None")

        lines.append("")
        if ext_errors or stuck_jobs:
            lines.append(f"<b>Extraction Failures &amp; Stuck Jobs ({label})</b>")
            for job in stuck_jobs[:5]:
                lines.append(
                    f"• ⏳ STUCK <code>{_esc(str(job.get('id', ''))[:8])}</code> "
                    f"({job.get('progress_percentage', 0)}%, provider={_esc(job.get('provider'))}, "
                    f"updated {_age(job.get('updated_at'))})"
                )
            for err in ext_errors[:8]:
                lines.append(
                    f"• ❌ <code>{_esc(str(err.get('id', ''))[:8])}</code> "
                    f"[{_esc(err.get('extraction_mode'))}/{_esc(err.get('provider'))}]: "
                    f"{_esc(err.get('error_message') or 'No error message', 180)} ({_age(err.get('created_at'))})"
                )
        else:
            lines.append(f"• Extraction Failures ({label}): ✅ None")

        if failed_checks:
            lines.append("")
            lines.append(f"<b>Failed Health Probes ({label})</b>")
            for chk in failed_checks[:6]:
                meta = chk.get("metadata") if isinstance(chk.get("metadata"), dict) else {}
                code = meta.get("status_code")
                code_txt = f" HTTP {code}" if code is not None else ""
                lines.append(
                    f"• 🔴 {_esc(chk.get('service'))}{code_txt} "
                    f"({chk.get('latency_ms', '?')}ms, {_age(chk.get('checked_at'))})"
                )

        if failed_cmds:
            lines.append("")
            lines.append("<b>Failed Bot Commands</b>")
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

    lines = ["🛡️ <b>Security Overview</b>"]
    try:
        overview = await security_service.get_security_overview()
        dep = overview.get("dependabot") or {}
        by_sev = dep.get("by_severity") or {}
        sev_str = ", ".join(f"{k}={v}" for k, v in sorted(by_sev.items()))
        lines.append(f"• Open Dependabot alerts: {dep.get('total_open', 0)}" + (f" ({sev_str})" if sev_str else ""))
        lines.append(f"• Recent unauthorized attempts: {overview.get('recent_unauthorized_attempts', 0)}")
    except ConfigurationError as exc:
        lines.append(f"• Dependabot: Not configured ({_esc(exc, 60)})")

    try:
        uptime = await insights_service.get_uptime_and_incidents(hours=24)
        lines.append(f"• Open incidents: {len(uptime.get('open_incidents') or [])}")
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
            return "No backups found yet."
        lines = [
            f"• {b['backup_id']} — {b['artifact_name']} ({b['created_at']})"
            for b in backups[:10]
        ]
        return f"{title('Available Backups', 'backup')}\n" + "\n".join(lines)

    confirmed = "confirm" in ctx.args
    return await backup_service.trigger_backup(confirmed=confirmed)


@command("restore")
async def handle_restore(ctx: CommandContext) -> str:
    from bot.modules.backup import service as backup_service

    if not ctx.args:
        return "Usage: /restore <backup_id> [confirm]\nSee /backup list for available backup IDs."
    backup_id = ctx.args[0]
    if not backup_id.isdigit():
        return f"Invalid backup_id '{backup_id}' — expected a numeric ID from /backup list."
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
        f"📈 <b>Analytics ({html.escape(period_label)})</b>",
        f"Errors ({html.escape(period_label)}): {summary.get('error_count') if summary.get('error_count') is not None else 'N/A'}",
    ]

    if users or activity:
        lines.extend(
            [
                "",
                "<b>Platform Engagement</b>",
                f"• New signups: {_fmt(users.get('signups_recent'))} | Active 24h: {_fmt(users.get('active_24h'))}",
                f"• Quizzes created: {_fmt(activity.get('quizzes_recent'))} | Completions: {_fmt(activity.get('completions_recent'))}",
                f"• Guest attempts: {_fmt(activity.get('guest_attempts_recent'))} | Avg score: {_fmt(activity.get('avg_score_pct'), '%')}",
                f"• AI calls: {_fmt(ai.get('total_calls'))} ({_fmt(ai.get('success_rate_pct'), '%')} ok)",
            ]
        )

    if vitals:
        lines.append("")
        lines.append("<b>Web Vitals (p75)</b>")
        for metric, st in sorted(vitals.items()):
            unit = "" if metric == "CLS" else "ms"
            lines.append(f"• {html.escape(metric)}: {st['p75']}{unit} (n={st['samples']})")

    if isinstance(umami, dict) and umami:
        pv = umami.get("pageviews", {})
        vis = umami.get("visitors", {})
        pv_val = pv.get("value") if isinstance(pv, dict) else pv
        vis_val = vis.get("value") if isinstance(vis, dict) else vis
        lines.extend(
            [
                "",
                "<b>Umami Traffic</b>",
                f"• Pageviews: {_fmt(pv_val)} | Visitors: {_fmt(vis_val)}",
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
            f"Unknown or empty report type '{_esc(report_type)}'.\n"
            "Available: daily, weekly, monthly, performance (append 'refresh' to regenerate)."
        )
    return report["content"]


@command("ask")
async def handle_ask(ctx: CommandContext) -> str:
    from bot.modules.ai_assistant import service as ai_assistant

    if not ctx.args:
        return "Usage: /ask <question>\nExample: /ask What is the AI error rate and system status today?"
    question = " ".join(ctx.args).strip()
    answer = await ai_assistant.answer_question(question)
    return f"🤖 <b>AI Ops Assistant</b>\n\n{html.escape(answer)}"


# --- Access control (RBAC) ----------------------------------------------------------

@command("setrole")
async def handle_setrole(ctx: CommandContext) -> str:
    """Owner-only. Grants ADMIN or VIEWER to a Telegram user ID at runtime."""
    from bot.db.repositories.users_repo import set_role

    if len(ctx.args) < 2:
        return "Usage: /setrole <telegram_user_id> <ADMIN|VIEWER>"

    try:
        target_user_id = int(ctx.args[0])
    except ValueError:
        return "telegram_user_id must be a number."

    role_str = ctx.args[1].upper()
    if role_str not in ("ADMIN", "VIEWER"):
        return "Role must be ADMIN or VIEWER. Owner can only be set via the OWNER_USER_IDS environment variable."

    await set_role(target_user_id, role_str)
    return f"✅ User {target_user_id} is now {role_str}."


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
        raise ValueError("expected true/false")
    if kind == "int":
        try:
            return int(raw)
        except ValueError:
            raise ValueError("expected a whole number") from None
    if kind.startswith("enum:"):
        options = kind.split(":", 1)[1].split(",")
        if raw not in options:
            raise ValueError(f"expected one of: {', '.join(options)}")
        return raw
    raise ValueError("unsupported setting type")  # pragma: no cover


@command("settings")
async def handle_settings(ctx: CommandContext) -> str:
    from bot.db.repositories.config_repo import get_all_settings, set_setting

    known_keys_hint = ", ".join(_KNOWN_SETTINGS)

    if not ctx.args:
        settings_map = await get_all_settings()
        if not settings_map:
            return f"No runtime settings configured yet.\nUsage: /settings <key> <value>\nKnown keys: {known_keys_hint}"
        return "⚙️ <b>Settings</b>\n" + "\n".join(f"{k}: {v}" for k, v in settings_map.items())

    if len(ctx.args) < 2:
        return f"Usage: /settings <key> <value>\nKnown keys: {known_keys_hint}"

    key, raw_value = ctx.args[0], " ".join(ctx.args[1:])
    if key not in _KNOWN_SETTINGS:
        return f"Unknown setting '{_esc(key)}'.\nKnown keys: {known_keys_hint}"

    try:
        value = _parse_setting_value(_KNOWN_SETTINGS[key], raw_value)
    except ValueError as e:
        return f"Invalid value for '{_esc(key)}': {e}"

    await set_setting(key, value)
    return f"⚙️ {key} set to {value}."


# ---------------------------------------------------------------------------
# /platform — view & toggle maintenance mode / registration
# ---------------------------------------------------------------------------

@command("platform")
async def handle_platform(ctx: CommandContext) -> str:
    from bot.modules.admin_actions import service as admin_actions

    # Read current state
    if not ctx.args:
        cfg = await admin_actions.get_platform_settings()
        if not cfg:
            return "⚙️ <b>Platform Settings</b>\n• Unable to read platform_settings."
        mm = "🔴 ON" if cfg.get("maintenance_mode") else "🟢 OFF"
        reg = "✅ ENABLED" if cfg.get("allow_registrations") else "❌ DISABLED"
        updated = _age(cfg.get("updated_at"))
        return (
            "⚙️ <b>Platform Settings</b>\n"
            f"• Maintenance mode: <b>{mm}</b>\n"
            f"• Registrations: <b>{reg}</b>\n"
            f"• Last updated: {updated}\n\n"
            "Toggle: <code>/platform maintenance on|off</code>\n"
            "Toggle: <code>/platform registration on|off</code>"
        )

    confirmed = "confirm" in ctx.args
    args = [a for a in ctx.args if a != "confirm"]

    if len(args) == 3 and args[0].lower() == "set" and confirmed:
        mm = args[1] == "1"
        reg = args[2] == "1"
    else:
        if len(args) < 2 or args[1].lower() not in ("on", "off"):
            return "Usage: /platform &lt;maintenance|registration&gt; &lt;on|off&gt;"

        # Read current to preserve the other field
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
            return "Unknown field. Use 'maintenance' or 'registration'."

    result = await admin_actions.toggle_platform_settings(
        maintenance_mode=mm, allow_registrations=reg, confirmed=confirmed
    )
    return (
        "⚙️ <b>Platform Settings Updated</b>\n"
        f"• Maintenance mode: {'🔴 ON' if result['maintenance_mode'] else '🟢 OFF'}\n"
        f"• Registrations: {'✅ ENABLED' if result['allow_registrations'] else '❌ DISABLED'}"
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
            return "🎁 <b>Trial Offers</b>\n• No trial offers found."
        lines = ["🎁 <b>Trial Offers</b>", ""]
        for offer in offers:
            state = "✅ Active" if offer.get("is_active") else "❌ Inactive"
            updated = _age(offer.get("updated_at"))
            lines.append(f"• <b>{offer.get('duration_days')}d</b>: {state} (updated {updated})")
        lines.append("\nToggle: <code>/trial &lt;7|14|30&gt; &lt;on|off&gt;</code>")
        return "\n".join(lines)

    if len(ctx.args) < 2 or ctx.args[1].lower() not in ("on", "off"):
        return "Usage: /trial &lt;7|14|30&gt; &lt;on|off&gt;"

    confirmed = "confirm" in ctx.args
    args = [a for a in ctx.args if a != "confirm"]

    if not args[0].isdigit():
        return "Usage: /trial &lt;7|14|30&gt; &lt;on|off&gt;"
    duration = int(args[0])
    is_active = args[1].lower() == "on"

    result = await admin_actions.toggle_trial_offer(
        duration_days=duration, is_active=is_active, confirmed=confirmed
    )
    state = "✅ Activated" if result["is_active"] else "❌ Deactivated"
    return (
        f"🎁 <b>Trial Offer Updated</b>\n"
        f"• Duration: <b>{result['duration_days']} days</b>\n"
        f"• Status: {state}"
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
        # List coupons
        coupons = await admin_actions.list_coupons(limit=20)
        if not coupons:
            return "🎟️ <b>Coupon Codes</b>\n• No coupons found."
        lines = ["🎟️ <b>Coupon Codes</b>", ""]
        for c in coupons:
            active_icon = "✅" if c.get("is_active") else "❌"
            used = c.get("used_count", 0)
            max_u = c.get("max_uses", 0)
            uses_txt = f"{used}/{max_u}" if max_u else f"{used}/∞"
            exp = c.get("expiry_date")
            exp_txt = f" | exp {_age(exp)}" if exp else ""
            plans = c.get("applicable_plans") or "all"
            lines.append(
                f"{active_icon} <code>{_esc(c.get('code'))}</code> — "
                f"{c.get('discount_percent', 0)}% off | uses: {uses_txt}{exp_txt}\n"
                f"  ID: <code>{_esc(c.get('id'))}</code> | plans: {_esc(plans, 50)}"
            )
        lines.append(
            "\nCreate: <code>/coupon create &lt;id&gt; &lt;CODE&gt; &lt;discount%&gt; [max_uses] [expiry_iso] [plans]</code>\n"
            "Toggle: <code>/coupon toggle &lt;id&gt; on|off</code>\n"
            "Delete: <code>/coupon delete &lt;id&gt;</code>"
        )
        return "\n".join(lines)

    sub = args[0].lower()

    if sub == "create":
        # /coupon create <id> <CODE> <discount%> [max_uses] [expiry_iso] [plans]
        if len(args) < 4:
            return "Usage: /coupon create &lt;id&gt; &lt;CODE&gt; &lt;discount%&gt; [max_uses] [expiry_iso] [plans]"
        coupon_id = args[1]
        code = args[2]
        try:
            disc = int(args[3])
        except ValueError:
            return "discount_percent must be an integer 0-100."
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
            "🎟️ <b>Coupon Created/Updated</b>\n"
            f"• Code: <code>{_esc(result.get('code'))}</code>\n"
            f"• Discount: {result.get('discount_percent', 0)}% | Max uses: {result.get('max_uses', 0) or '∞'}\n"
            f"• Plans: {_esc(result.get('applicable_plans', 'all'), 60)}"
        )

    if sub == "toggle":
        if len(args) < 3 or args[2].lower() not in ("on", "off"):
            return "Usage: /coupon toggle &lt;id&gt; on|off"
        is_active = args[2].lower() == "on"
        result = await admin_actions.toggle_coupon(args[1], is_active=is_active, confirmed=confirmed)
        state = "✅ Activated" if result.get("is_active") else "❌ Deactivated"
        return f"🎟️ <b>Coupon {state}</b>\n• ID: <code>{_esc(args[1])}</code>"

    if sub == "delete":
        if len(args) < 2:
            return "Usage: /coupon delete &lt;id&gt;"
        await admin_actions.delete_coupon(args[1], confirmed=confirmed)
        return f"🗑️ <b>Coupon Deleted</b>\n• ID: <code>{_esc(args[1])}</code>"

    return "Unknown subcommand. Use: list (no args), create, toggle, delete."


# ---------------------------------------------------------------------------
# /vitals — dedicated Web Vitals report
# ---------------------------------------------------------------------------

@command("vitals")
async def handle_vitals(ctx: CommandContext) -> str:
    from bot.db.repositories import platform_repo

    summary = await platform_repo.get_web_vitals_summary()
    if not summary:
        return "📊 <b>Web Vitals</b>\n• No vitals data available."

    _THRESHOLDS = {
        "CLS": [(0.1, "🟢 Good"), (0.25, "🟡 Needs Improvement"), (999, "🔴 Poor")],
        "LCP": [(2500, "🟢 Good"), (4000, "🟡 Needs Improvement"), (99999, "🔴 Poor")],
        "FCP": [(1800, "🟢 Good"), (3000, "🟡 Needs Improvement"), (99999, "🔴 Poor")],
        "INP": [(200, "🟢 Good"), (500, "🟡 Needs Improvement"), (99999, "🔴 Poor")],
        "TTFB": [(800, "🟢 Good"), (1800, "🟡 Needs Improvement"), (99999, "🔴 Poor")],
    }

    def _rating(metric: str, value: float) -> str:
        for threshold, label in _THRESHOLDS.get(metric, []):
            if value <= threshold:
                return label
        return "⚪"

    lines = ["📊 <b>Web Vitals Report</b>", ""]
    for metric, stats in sorted(summary.items()):
        p75 = stats.get("p75")
        avg = stats.get("avg")
        samples = stats.get("samples", 0)
        rating = _rating(metric, p75) if p75 is not None else "⚪"
        unit = "" if metric == "CLS" else "ms"
        lines.append(
            f"• <b>{metric}</b>: p75={_fmt(p75, unit)} avg={_fmt(avg, unit)} "
            f"({samples} samples) {rating}"
        )

    lines.append(
        "\n<i>Good: CLS≤0.1 LCP≤2500ms FCP≤1800ms INP≤200ms TTFB≤800ms</i>"
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
        lines = ["🏆 <b>Top Users — Reward Points</b>", ""]
        if not rows:
            return lines[0] + "\n• No data available."
        for idx, row in enumerate(rows, 1):
            name = _esc(row.get("display_name", str(row.get("user_id", ""))[:8]), 30)
            pts = int(row.get("points") or 0)
            lvl = row.get("level", 1)
            lines.append(f"{idx}. {name} — <b>{pts:,}</b> pts | Level {lvl}")
        lines.append("\nFilter: <code>/topusers xp</code> | <code>/topusers points</code>")
        return "\n".join(lines)

    # Default: XP
    rows = await platform_repo.get_top_users_by_xp(limit=limit)
    lines = ["🏆 <b>Top Users — XP Leaderboard</b>", ""]
    if not rows:
        return lines[0] + "\n• No data available."
    for idx, row in enumerate(rows, 1):
        name = _esc(row.get("name") or row.get("custom_id") or str(row.get("uid", ""))[:8], 30)
        xp = int(row.get("xp") or 0)
        lvl = row.get("level", 1)
        tier = "⭐" if row.get("is_premium") else "·"
        lines.append(f"{idx}. {tier} {name} — <b>{xp:,}</b> XP | Level {lvl}")
    lines.append("\nFilter: <code>/topusers xp</code> | <code>/topusers points</code>")
    return "\n".join(lines)
