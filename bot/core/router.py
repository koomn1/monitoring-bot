"""
bot/core/router.py

Central command router. Every Telegram command handler registers itself
here via the `@command` decorator. The router is responsible for:

  1. Resolving the incoming update to a command name
  2. Running it through the middleware chain (auth -> permissions -> logging)
  3. Invoking the registered handler
  4. Catching and translating known exceptions into user-facing messages
  5. Attaching the right inline keyboard to the reply (see
     bot/utils/keyboards.py) — confirmation buttons for destructive
     actions, refresh/menu buttons for read-only ones

See: docs/03-system-architecture.md, docs/07-security.md §8
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict

from bot.core.exceptions import (
    ConfirmationRequiredError,
    ExternalServiceError,
    ForbiddenError,
    QuizSpaceBotError,
    RateLimitedError,
    UnauthorizedError,
)
from bot.core import rate_limiter
from bot.core.permissions import require_command_permission
from bot.utils import keyboards
from bot.utils.keyboards import Keyboard

logger = logging.getLogger("bot.router")


@dataclass
class CommandContext:
    """Normalized representation of an inbound Telegram command or button
    tap, independent of whichever Telegram library implementation is
    used underneath (see bot/main.py for the python-telegram-bot
    adapter that constructs this)."""

    user_id: int
    chat_id: int
    command: str
    args: list[str]
    raw_text: str
    callback_data: str | None = None


HandlerFn = Callable[[CommandContext], Awaitable[str]]
DispatchResult = tuple[str, Keyboard | None]

_REGISTRY: Dict[str, HandlerFn] = {}


def command(name: str):
    """
    Decorator used by modules under bot/modules/telegram_commands/ to
    register a handler function for a given command name (without the
    leading slash), e.g.:

        @command("status")
        async def handle_status(ctx: CommandContext) -> str:
            ...

    Handlers return plain text only — the router attaches keyboards
    (see bot/utils/keyboards.py:buttons_for) so handlers don't need to
    know about Telegram-specific button plumbing.
    """

    def decorator(fn: HandlerFn) -> HandlerFn:
        if name in _REGISTRY:
            raise RuntimeError(f"Duplicate command registration: /{name}")
        _REGISTRY[name] = fn
        return fn

    return decorator


async def dispatch(ctx: CommandContext) -> DispatchResult:
    """
    Main entrypoint invoked by bot/main.py for every inbound command or
    button tap. Returns (text, keyboard) — keyboard is None when no
    buttons should be attached to the reply.
    """
    handler = _REGISTRY.get(ctx.command)
    if handler is None:
        return f"أمر غير معروف: /{ctx.command}. أرسل /help لعرض الأوامر المتاحة.", None

    try:
        rate_limiter.check_rate_limit(ctx.user_id)
    except RateLimitedError as e:
        logger.info("Rate limited user_id=%s on /%s", ctx.user_id, ctx.command)
        return f"⏳ {e}", None

    try:
        await require_command_permission(ctx.user_id, ctx.command)
    except UnauthorizedError:
        logger.warning("Unauthorized access attempt by user_id=%s command=/%s", ctx.user_id, ctx.command)
        return "🚫 غير مصرح لك باستخدام هذا البوت. تواصل مع مالك Quiz Space.", None
    except ForbiddenError:
        logger.warning("Forbidden: user_id=%s tried /%s without sufficient role", ctx.user_id, ctx.command)
        return "🚫 ليس لديك صلاحية لتنفيذ هذا الأمر.", None

    keyboards.clear_reply_buttons()
    try:
        text = await handler(ctx)
        return text, keyboards.buttons_for(ctx.command, ctx.args)
    except ConfirmationRequiredError as e:
        buttons = keyboards.confirmation_buttons(e.command, e.extra_args)
        return f"⚠️ {e}", buttons
    except ExternalServiceError as e:
        logger.error("External service error handling /%s: %s", ctx.command, e)
        return f"❌ تعذر الوصول إلى {e.service} حالياً. حاول مرة أخرى بعد قليل.", None
    except QuizSpaceBotError as e:
        logger.error("Bot error handling /%s: %s", ctx.command, e)
        return f"❌ {e}", None
    except Exception:  # noqa: BLE001 - top-level safety net, see docs/03
        logger.exception("Unhandled exception while handling /%s", ctx.command)
        return "❌ حدث خطأ غير متوقع. تم تسجيل الخطأ وإبلاغ الإدارة.", None


def registered_commands() -> list[str]:
    return sorted(_REGISTRY.keys())
