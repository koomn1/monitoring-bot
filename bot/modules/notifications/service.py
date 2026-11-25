"""
bot/modules/notifications/service.py — Notifications

Central fan-out for Bot notifications. Supabase webhook notifications use
an explicit admin destination and only include allow-listed, non-sensitive
fields; user identifiers are shortened before they are sent.
"""

from __future__ import annotations

import html
from typing import Any

from bot.config import settings
from bot.core.permissions import Role, list_env_authorized_users
from bot.integrations import telegram_client
from bot.utils.formatting import format_duration_ms


def _escape(value: Any, max_length: int = 100) -> str:
    """Render a scalar safely for Telegram HTML without exposing arbitrary objects."""
    if value is None or isinstance(value, (dict, list, tuple, set, bool)):
        return "غير محدد"
    text = str(value).strip()
    if not text:
        return "غير محدد"
    return html.escape(text[:max_length], quote=False)


def _short_id(value: Any) -> str:
    if value is None or isinstance(value, (dict, list, tuple, set, bool)):
        return "غير متاح"
    identifier = str(value).strip()
    return html.escape(identifier[:8] if identifier else "غير متاح", quote=False)


async def _broadcast(text: str) -> None:
    if settings.telegram_alert_channel_id:
        await telegram_client.send_message(settings.telegram_alert_channel_id, text)
        return
    admin_ids = [uid for uid, role in list_env_authorized_users() if role >= Role.ADMIN]
    await telegram_client.broadcast_to_role(admin_ids, text)


async def _broadcast_admin(text: str) -> None:
    """Send admin-only notifications to the dedicated chat, then legacy targets."""
    if settings.telegram_admin_chat_id:
        await telegram_client.send_message(settings.telegram_admin_chat_id, text)
        return
    await _broadcast(text)


async def notify_website_down(latency_ms: int) -> None:
    await _broadcast(f"🔴 <b>Website Down</b>\nNo response after {format_duration_ms(latency_ms)}.")


async def notify_website_online(latency_ms: int) -> None:
    await _broadcast(f"🟢 <b>Website Online</b>\nResponding in {format_duration_ms(latency_ms)}.")


async def notify_api_failure(latency_ms: int) -> None:
    await _broadcast(f"🔴 <b>API Failure</b>\nNo healthy response after {format_duration_ms(latency_ms)}.")


async def notify_database_failure(latency_ms: int) -> None:
    await _broadcast("🔴 <b>Database Failure</b>\nSupabase database is unreachable.")


async def notify_storage_failure() -> None:
    await _broadcast("🔴 <b>Storage Failure</b>\nSupabase Storage is unreachable.")


async def notify_deployment_started(environment: str) -> None:
    await _broadcast(f"🚀 <b>Deployment Started</b>\nTarget: {_escape(environment)}")


async def notify_deployment_success(environment: str) -> None:
    await _broadcast(f"✅ <b>Deployment Success</b>\nTarget: {_escape(environment)}")


async def notify_deployment_failed(environment: str, reason: str) -> None:
    await _broadcast(f"❌ <b>Deployment Failed</b>\nTarget: {_escape(environment)}\nReason: {_escape(reason)}")


async def notify_rollback_started() -> None:
    await _broadcast("⏪ <b>Rollback Started</b>")


async def notify_rollback_completed() -> None:
    await _broadcast("✅ <b>Rollback Completed</b>")


async def notify_backup_started() -> None:
    await _broadcast("💾 <b>Backup Started</b>")


async def notify_backup_completed(size_note: str = "") -> None:
    await _broadcast(f"✅ <b>Backup Completed</b>{(' — ' + _escape(size_note)) if size_note else ''}")


async def notify_backup_failed(reason: str) -> None:
    await _broadcast(f"❌ <b>Backup Failed</b>\nReason: {_escape(reason)}")


async def notify_restore_started(backup_id: str) -> None:
    await _broadcast(f"♻️ <b>Restore Started</b>\nFrom backup: {_short_id(backup_id)}")


async def notify_restore_completed(backup_id: str) -> None:
    await _broadcast(f"✅ <b>Restore Completed</b>\nFrom backup: {_short_id(backup_id)}")


async def notify_security_alert(details: str) -> None:
    await _broadcast(f"🛡️ <b>Security Alert</b>\n{_escape(details)}")


async def notify_new_user(identifier: str) -> None:
    await _broadcast_admin(f"👋 <b>مستخدم جديد</b>\nالمعرّف: {_short_id(identifier)}")


async def notify_activation_request(
    request_id: Any, *, plan: Any = None, amount: Any = None, payment_method: Any = None
) -> None:
    lines = ["💳 <b>طلب تفعيل جديد</b>", f"المعرّف: {_short_id(request_id)}"]
    if plan is not None:
        lines.append(f"الباقة: {_escape(plan)}")
    if amount is not None:
        lines.append(f"المبلغ: {_escape(amount)}")
    if payment_method is not None:
        lines.append(f"طريقة الدفع: {_escape(payment_method)}")
    await _broadcast_admin("\n".join(lines))


async def notify_trial_activation_request(request_id: Any) -> None:
    await _broadcast_admin(f"🎁 <b>طلب تفعيل تجريبي</b>\nالمعرّف: {_short_id(request_id)}")


async def notify_activation_decision(request_id: Any, *, approved: bool) -> None:
    icon, decision = ("✅", "تمت الموافقة") if approved else ("❌", "تم الرفض")
    await _broadcast_admin(f"{icon} <b>{decision} على طلب التفعيل</b>\nالمعرّف: {_short_id(request_id)}")


async def notify_admin_table_change(table: str, action: str, row_id: Any) -> None:
    labels = {"INSERT": "إضافة", "UPDATE": "تعديل", "DELETE": "حذف"}
    action_label = labels.get(action.upper(), "تغيير")
    await _broadcast_admin(
        f"🛠️ <b>تغيير في جدول إداري</b>\nالجدول: {_escape(table)}\n"
        f"العملية: {_escape(action_label)}\nالمعرّف: {_short_id(row_id)}"
    )


async def notify_latency_warning(service: str, latency_ms: int, threshold_ms: int) -> None:
    await _broadcast(
        f"🟡 <b>High Latency Warning</b>\n"
        f"Service: {_escape(service)}\n"
        f"Latency: {format_duration_ms(latency_ms)} (threshold: {format_duration_ms(threshold_ms)})"
    )


async def notify_operational_alert(title_text: str, details: str) -> None:
    await _broadcast(f"⚠️ <b>{_escape(title_text)}</b>\n{_escape(details, max_length=400)}")


async def notify_scheduled_report(content: str) -> None:
    await _broadcast_admin(content)


async def notify_new_premium_user(identifier: str) -> None:
    await _broadcast(f"⭐ <b>New Premium User</b>\n{_short_id(identifier)}")


async def notify_payment_received(amount: str, identifier: str) -> None:
    await _broadcast(f"💰 <b>Payment Received</b>\n{_escape(amount)} from {_short_id(identifier)}")
