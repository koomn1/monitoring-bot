"""
bot/main.py

Entry point for the Quiz Space Telegram DevOps Bot. Responsibilities:
  1. Validate configuration (fail fast)
  2. Configure logging
  3. Import telegram_commands.handlers to populate the command registry
  4. Wire python-telegram-bot's Application to bot/core/router.py, for
     BOTH text commands and inline-button taps (callback queries)
  5. Start the internal scheduler (bot/core/scheduler.py)
  6. Run the bot (polling by default; webhook if TELEGRAM_USE_WEBHOOK=true)

See: docs/03-system-architecture.md, docs/06-deployment.md
"""

from __future__ import annotations

import logging
import os
import re

from aiohttp import web
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from bot.api.server import build_app
from bot.config import settings
from bot.core import scheduler
from bot.core.middleware import with_audit_log
from bot.core.router import CommandContext, dispatch
from bot.utils.keyboards import Keyboard, resolve_confirmation_token

# Populates the command registry — must be imported before the bot starts
# receiving updates. See bot/modules/telegram_commands/handlers.py.
from bot.modules.telegram_commands import handlers  # noqa: F401

logger = logging.getLogger("bot.main")


class _TelegramTokenRedactionFilter(logging.Filter):
    _token_pattern = re.compile(r"(?i)(/bot)\d+:[A-Za-z0-9_-]+")

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = self._token_pattern.sub(r"\1[REDACTED]", message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    root_logger = logging.getLogger()
    if not any(isinstance(item, _TelegramTokenRedactionFilter) for item in root_logger.filters):
        root_logger.addFilter(_TelegramTokenRedactionFilter())
    for handler in root_logger.handlers:
        if not any(isinstance(item, _TelegramTokenRedactionFilter) for item in handler.filters):
            handler.addFilter(_TelegramTokenRedactionFilter())
    # httpx includes full request URLs in INFO logs; Telegram API URLs contain
    # the bot token, so keep transport logs at WARNING or above.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def _to_inline_markup(buttons: Keyboard | None) -> InlineKeyboardMarkup | None:
    """Converts the router's plain-data keyboard shape (see
    bot/utils/keyboards.py) into python-telegram-bot's InlineKeyboardMarkup.
    This is the ONLY place in the codebase that does this conversion —
    bot/core and bot/modules never import `telegram` directly."""
    if not buttons:
        return None
    rows = [
        [InlineKeyboardButton(b["text"], callback_data=b["callback_data"]) for b in row]
        for row in buttons
    ]
    return InlineKeyboardMarkup(rows)


def _split_telegram_text(text: str, limit: int = 3900) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in text.splitlines(keepends=True):
        if len(line) > limit:
            if current:
                chunks.append("".join(current))
                current, current_len = [], 0
            for start in range(0, len(line), limit):
                chunks.append(line[start : start + limit])
            continue
        if current_len + len(line) > limit and current:
            chunks.append("".join(current))
            current, current_len = [], 0
        current.append(line)
        current_len += len(line)
    if current:
        chunks.append("".join(current))
    return chunks


async def _telegram_command_entrypoint(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.effective_chat is None or update.message is None:
        return

    text = update.message.text or ""
    parts = text.strip().split()
    command_name = parts[0].lstrip("/").split("@")[0]
    args = parts[1:]

    ctx = CommandContext(
        user_id=update.effective_user.id,
        chat_id=update.effective_chat.id,
        command=command_name,
        args=args,
        raw_text=text,
    )

    reply_text, buttons = await with_audit_log(ctx, dispatch)
    chunks = _split_telegram_text(reply_text)
    markup = _to_inline_markup(buttons)
    for idx, chunk in enumerate(chunks):
        is_last = idx == len(chunks) - 1
        await update.message.reply_text(
            chunk, parse_mode="HTML", reply_markup=markup if is_last else None
        )


async def _telegram_callback_entrypoint(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles every inline-button tap: menu shortcuts ("cmd|status"),
    confirmations ("confirm|deploy|production" or "confirm_tok|<token>"),
    and cancellations ("cancel|deploy").
    """
    query = update.callback_query
    if query is None or query.data is None or query.from_user is None or query.message is None:
        return

    await query.answer()  # stop Telegram's loading spinner on the button immediately

    action, _, rest = query.data.partition("|")

    if action == "cancel":
        await query.edit_message_text("🚫 Cancelled — no changes were made.")
        return

    if action == "cmd":
        command_name = rest
        args: list[str] = []
    elif action == "confirm":
        command_name, _, args_csv = rest.partition("|")
        args = ([a for a in args_csv.split(",") if a] if args_csv else []) + ["confirm"]
    elif action == "confirm_tok":
        resolved = resolve_confirmation_token(rest)
        if resolved is None:
            await query.edit_message_text("⚠️ Confirmation expired — please re-run the command.")
            return
        command_name, stored_args = resolved
        args = list(stored_args) + ["confirm"]
    else:
        logger.warning("Unrecognized callback_data prefix: %s", action)
        return

    ctx = CommandContext(
        user_id=query.from_user.id,
        chat_id=query.message.chat_id,
        command=command_name,
        args=args,
        raw_text="",
        callback_data=query.data,
    )

    reply_text, buttons = await with_audit_log(ctx, dispatch)
    chunks = _split_telegram_text(reply_text)
    markup = _to_inline_markup(buttons)
    await query.edit_message_text(
        chunks[0], parse_mode="HTML", reply_markup=markup if len(chunks) == 1 else None
    )
    for idx, extra_chunk in enumerate(chunks[1:], start=1):
        is_last = idx == len(chunks) - 1
        await query.message.reply_text(
            extra_chunk, parse_mode="HTML", reply_markup=markup if is_last else None
        )


async def _post_init(application: Application) -> None:
    """
    Runs once, inside the same asyncio loop as Telegram polling, right
    before the Bot starts receiving updates. Starts the small aiohttp
    server from bot/api/server.py so that:
      - Railway (or any host) has an HTTP port to health-check
        (GET /health), which is what most PaaS free/hobby tiers use to
        decide whether the service is alive
      - GitHub Actions and Supabase can POST webhook events to this public URL
        (see docs/admin-notifications.md for the Supabase setup)

    This runs regardless of TELEGRAM_USE_WEBHOOK — Telegram delivery
    mode (polling vs. webhook) is independent of this receiver, which
    handles GitHub/Sentry/Supabase callbacks and the health check.
    """
    port = int(os.environ.get("PORT", str(settings.telegram_webhook_port)))
    runner = web.AppRunner(build_app())
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Webhook/health receiver listening on port %s", port)

    menu_commands = [
        BotCommand("start", "Open main operations menu"),
        BotCommand("status", "Service health, realtime & incidents"),
        BotCommand("dashboard", "Full executive platform snapshot"),
        BotCommand("pulse", "Live users, quizzes & activity"),
        BotCommand("errors", "Full diagnostics across Sentry, AI & jobs"),
        BotCommand("ai", "AI pipeline & extraction queue"),
        BotCommand("payments", "Review pending subscriptions"),
        BotCommand("orders", "Review reward store orders"),
        BotCommand("points", "Points leaderboard & user balances"),
        BotCommand("users", "User stats & newest signups"),
        BotCommand("user", "Full user profile, plan & points"),
        BotCommand("membership", "Edit user subscription (Owner)"),
        BotCommand("grantpoints", "Add/deduct user points (Owner)"),
        BotCommand("incidents", "Open/resolved incidents & uptime"),
        BotCommand("analytics", "Platform analytics & Web Vitals"),
        BotCommand("reports", "Daily/weekly/monthly/performance reports"),
        BotCommand("ask", "Ask AI assistant about live metrics"),
        BotCommand("help", "All commands & usage"),
    ]
    try:
        await application.bot.set_my_commands(menu_commands)
    except Exception:  # noqa: BLE001
        logger.warning("Could not sync Telegram command menu")


def build_application() -> Application:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to start the bot.")

    application = Application.builder().token(settings.telegram_bot_token).post_init(_post_init).build()

    from bot.core.router import registered_commands

    for command_name in registered_commands():
        application.add_handler(CommandHandler(command_name, _telegram_command_entrypoint))

    application.add_handler(CallbackQueryHandler(_telegram_callback_entrypoint))

    return application


def main() -> None:
    configure_logging()
    settings.validate()

    application = build_application()

    scheduler.register_all_jobs()
    scheduler.start()

    logger.info("Quiz Space DevOps Bot starting (environment=%s)", settings.environment)

    if settings.telegram_use_webhook:
        if not settings.telegram_webhook_url:
            raise RuntimeError("TELEGRAM_USE_WEBHOOK=true requires TELEGRAM_WEBHOOK_URL to be set.")
        # See api/02-webhooks.md for the webhook endpoint contract.
        application.run_webhook(
            listen="0.0.0.0",
            port=settings.telegram_webhook_port,
            webhook_url=settings.telegram_webhook_url,
        )
    else:
        application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
