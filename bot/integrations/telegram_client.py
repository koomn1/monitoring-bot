"""
bot/integrations/telegram_client.py

Thin async client around the Telegram Bot API HTTP endpoints, used for
sending messages/notifications outside of the main update-handling loop
(e.g. from scheduled jobs). The main update loop itself is driven by
python-telegram-bot in bot/main.py; this client exists so that modules
(reports, notifications, automation) can push messages without depending
on the Application object directly.

See: docs/03-system-architecture.md, modules/19-notifications.md
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from bot.config import settings
from bot.core.exceptions import ExternalServiceError
from bot.utils.retry import async_retry, is_transient_service_error

logger = logging.getLogger("integrations.telegram")

_BASE_URL = "https://api.telegram.org/bot{token}"


def _url(method: str) -> str:
    if not settings.telegram_bot_token:
        raise ExternalServiceError("Telegram", "TELEGRAM_BOT_TOKEN is not configured")
    return f"{_BASE_URL.format(token=settings.telegram_bot_token)}/{method}"


def _raise_for_status(resp: httpx.Response) -> None:
    """Converts an httpx error into ExternalServiceError WITH a status
    code attached, so the retry predicate (is_transient_service_error)
    can tell a transient 5xx/network failure apart from a permanent 4xx
    (e.g. chat not found, bot blocked) that retrying would never fix."""
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ExternalServiceError(
            "Telegram", f"{exc.response.status_code}: {exc.response.text}",
            status_code=exc.response.status_code,
        ) from exc


@async_retry(attempts=3, base_delay=1.0, exceptions=(ExternalServiceError,), retry_if=is_transient_service_error)
async def send_message(
    chat_id: str | int,
    text: str,
    *,
    parse_mode: str = "HTML",
    reply_markup: dict[str, Any] | None = None,
    disable_notification: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_notification": disable_notification,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(_url("sendMessage"), json=payload)
            _raise_for_status(resp)
            return resp.json()
        except httpx.HTTPError as exc:
            logger.error("Telegram sendMessage failed: %s", exc)
            raise ExternalServiceError("Telegram", str(exc)) from exc


@async_retry(attempts=3, base_delay=1.0, exceptions=(ExternalServiceError,), retry_if=is_transient_service_error)
async def send_photo(chat_id: str | int, photo_url_or_bytes: Any, *, caption: str = "") -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(
                _url("sendPhoto"),
                data={"chat_id": chat_id, "caption": caption},
                files={"photo": photo_url_or_bytes} if not isinstance(photo_url_or_bytes, str) else None,
                params={"photo": photo_url_or_bytes} if isinstance(photo_url_or_bytes, str) else None,
            )
            _raise_for_status(resp)
            return resp.json()
        except httpx.HTTPError as exc:
            logger.error("Telegram sendPhoto failed: %s", exc)
            raise ExternalServiceError("Telegram", str(exc)) from exc


async def set_webhook(url: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(_url("setWebhook"), json={"url": url})
        _raise_for_status(resp)
        return resp.json()


async def broadcast_to_role(role_user_ids: list[int], text: str) -> None:
    """Sends `text` to every user_id in `role_user_ids`, best-effort (does not
    fail the whole broadcast if one user has blocked the bot)."""
    for uid in role_user_ids:
        try:
            await send_message(uid, text)
        except ExternalServiceError:
            logger.warning("Could not deliver message to user_id=%s (blocked bot?)", uid)
