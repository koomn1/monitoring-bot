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

from aiohttp import web
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from bot.api.server import build_app
from bot.config import settings
from bot.core import scheduler
from bot.core.middleware import with_audit_log
from bot.core.router import CommandContext, dispatch
from bot.utils.keyboards import Keyboard

# Populates the command registry — must be imported before the bot starts
# receiving updates. See bot/modules/telegram_commands/handlers.py.
from bot.modules.telegram_commands import handlers  # noqa: F401

logger = logging.getLogger("bot.main")


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


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
    await update.message.reply_text(
        reply_text, parse_mode="HTML", reply_markup=_to_inline_markup(buttons)
    )


async def _telegram_callback_entrypoint(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles every inline-button tap: menu shortcuts ("cmd|status"),
    confirmations ("confirm|deploy|production"), and cancellations
    ("cancel|deploy"). See bot/utils/keyboards.py for the callback_data
    format.
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
    else:
        logger.warning("Unrecognized callback_data prefix: %s", action)  # noqa: F821
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
    await query.edit_message_text(
        reply_text, parse_mode="HTML", reply_markup=_to_inline_markup(buttons)
    )


async def _post_init(application: Application) -> None:
    """
    Runs once, inside the same asyncio loop as Telegram polling, right
    before the Bot starts receiving updates. Starts the small aiohttp
    server from bot/api/server.py so that:
      - Railway (or any host) has an HTTP port to health-check
        (GET /health), which is what most PaaS free/hobby tiers use to
        decide whether the service is alive
      - GitHub Actions workflows can POST their deploy/backup/rollback
        callbacks to this same public URL (see .github/workflows/*.yml
        and BOT_WEBHOOK_URL in docs/04-environment-variables.md)

    This runs regardless of TELEGRAM_USE_WEBHOOK — Telegram delivery
    mode (polling vs. webhook) is independent of this receiver, which
    only ever handles GitHub/Sentry callbacks and the health check.
    """
    port = int(os.environ.get("PORT", 8081))
    runner = web.AppRunner(build_app())
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Webhook/health receiver listening on port %s", port)


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
            port=8080,
            webhook_url=settings.telegram_webhook_url,
        )
    else:
        application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
