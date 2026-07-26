"""
bot/utils/keyboards.py

Generates Telegram inline keyboards as plain, Telegram-library-agnostic
data: list[list[{"text": str, "callback_data": str}]]. This matches
CommandContext's design goal (bot/core/router.py) — nothing in
bot/core or bot/modules imports the `telegram` package directly.
bot/main.py is the only place that converts this shape into
python-telegram-bot's InlineKeyboardMarkup.

Callback data format (kept short — Telegram caps callback_data at 64
bytes):
  "cmd|<command>"                — re-run a read-only command (e.g. refresh)
  "confirm|<command>|<a,b,c>"    — confirm a pending destructive action,
                                    extra_args joined by comma
  "cancel|<command>"             — cancel a pending destructive action

See: modules/17-telegram-commands.md, docs/07-security.md §8
"""

from __future__ import annotations

Button = dict[str, str]
Keyboard = list[list[Button]]


def confirmation_buttons(command: str, extra_args: list[str] | None = None) -> Keyboard:
    args_csv = ",".join(extra_args or [])
    return [
        [
            {"text": "✅ Confirm", "callback_data": f"confirm|{command}|{args_csv}"},
            {"text": "❌ Cancel", "callback_data": f"cancel|{command}"},
        ]
    ]


def main_menu_buttons() -> Keyboard:
    return [
        [
            {"text": "📡 Status", "callback_data": "cmd|status"},
            {"text": "📊 Dashboard", "callback_data": "cmd|dashboard"},
        ],
        [
            {"text": "🖥️ System", "callback_data": "cmd|system"},
            {"text": "🛡️ Security", "callback_data": "cmd|security"},
        ],
        [
            {"text": "📈 Analytics", "callback_data": "cmd|analytics"},
            {"text": "📜 Logs", "callback_data": "cmd|logs"},
        ],
    ]


def refresh_button(command: str) -> Keyboard:
    return [[{"text": "🔄 Refresh", "callback_data": f"cmd|{command}"}]]


# Commands that get an automatic "🔄 Refresh" button on their reply.
_REFRESHABLE = {"status", "dashboard", "system", "security", "analytics"}
# Commands that get the main menu attached on their reply.
_MENU_COMMANDS = {"start", "help"}


def buttons_for(command: str, args: list[str]) -> Keyboard | None:
    """
    Called automatically by bot/core/router.py after a successful reply
    to attach the right keyboard for that command — individual command
    handlers in bot/modules/telegram_commands/handlers.py do not need
    to build keyboards themselves for these standard cases.
    """
    if command in _MENU_COMMANDS:
        return main_menu_buttons()
    if command in _REFRESHABLE:
        return refresh_button(command)
    return None
