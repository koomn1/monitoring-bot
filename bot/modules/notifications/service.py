"""
bot/modules/notifications/service.py — Notifications

Central fan-out for every notification type in docs/. Each notify_*
function formats a message and broadcasts it to the configured alert
channel (or all ADMIN+ users if no channel is set). Called from monitor
modules, deployment/backup modules, and automation.

See: modules/19-notifications.md
"""

from __future__ import annotations

from bot.config import settings
from bot.core.permissions import Role, list_env_authorized_users
from bot.integrations import telegram_client
from bot.utils.formatting import format_duration_ms


async def _broadcast(text: str) -> None:
    if settings.telegram_alert_channel_id:
        await telegram_client.send_message(settings.telegram_alert_channel_id, text)
        return
    admin_ids = [uid for uid, role in list_env_authorized_users() if role >= Role.ADMIN]
    await telegram_client.broadcast_to_role(admin_ids, text)


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
    await _broadcast(f"🚀 <b>Deployment Started</b>\nTarget: {environment}")


async def notify_deployment_success(environment: str) -> None:
    await _broadcast(f"✅ <b>Deployment Success</b>\nTarget: {environment}")


async def notify_deployment_failed(environment: str, reason: str) -> None:
    await _broadcast(f"❌ <b>Deployment Failed</b>\nTarget: {environment}\nReason: {reason}")


async def notify_rollback_started() -> None:
    await _broadcast("⏪ <b>Rollback Started</b>")


async def notify_rollback_completed() -> None:
    await _broadcast("✅ <b>Rollback Completed</b>")


async def notify_backup_started() -> None:
    await _broadcast("💾 <b>Backup Started</b>")


async def notify_backup_completed(size_note: str = "") -> None:
    await _broadcast(f"✅ <b>Backup Completed</b>{(' — ' + size_note) if size_note else ''}")


async def notify_backup_failed(reason: str) -> None:
    await _broadcast(f"❌ <b>Backup Failed</b>\nReason: {reason}")


async def notify_restore_started(backup_id: str) -> None:
    await _broadcast(f"♻️ <b>Restore Started</b>\nFrom backup: {backup_id}")


async def notify_restore_completed(backup_id: str) -> None:
    await _broadcast(f"✅ <b>Restore Completed</b>\nFrom backup: {backup_id}")


async def notify_security_alert(details: str) -> None:
    await _broadcast(f"🛡️ <b>Security Alert</b>\n{details}")


async def notify_new_user(identifier: str) -> None:
    await _broadcast(f"👋 <b>New User</b>\n{identifier}")


async def notify_new_premium_user(identifier: str) -> None:
    await _broadcast(f"⭐ <b>New Premium User</b>\n{identifier}")


async def notify_payment_received(amount: str, identifier: str) -> None:
    await _broadcast(f"💰 <b>Payment Received</b>\n{amount} from {identifier}")
