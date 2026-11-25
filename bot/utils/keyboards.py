"""
bot/utils/keyboards.py

Generates Telegram inline keyboards as plain, Telegram-library-agnostic
data: list[list[{"text": str, "callback_data": str}]].

Callback data format (kept within Telegram's 64-byte cap):
  "cmd|<command>"                — re-run a read-only command
  "confirm|<command>|<a,b,c>"    — confirm pending action (when <= 64 bytes)
  "confirm_tok|<token>"          — confirm pending action with longer args
  "cancel|<command>"             — cancel a pending action
"""

from __future__ import annotations

import secrets
from collections import OrderedDict

Button = dict[str, str]
Keyboard = list[list[Button]]

_MAX_CALLBACK_BYTES = 64
_MAX_PENDING_TOKENS = 200
_PENDING_CONFIRMATIONS: OrderedDict[str, tuple[str, list[str]]] = OrderedDict()


def resolve_confirmation_token(token: str) -> tuple[str, list[str]] | None:
    """Pops and returns (command, extra_args) for a short confirmation token."""
    return _PENDING_CONFIRMATIONS.pop(token, None)


def confirmation_buttons(command: str, extra_args: list[str] | None = None) -> Keyboard:
    args = list(extra_args or [])
    args_csv = ",".join(args)
    direct_data = f"confirm|{command}|{args_csv}"
    if len(direct_data.encode("utf-8")) <= _MAX_CALLBACK_BYTES:
        confirm_cb = direct_data
    else:
        token = secrets.token_hex(6)
        _PENDING_CONFIRMATIONS[token] = (command, args)
        while len(_PENDING_CONFIRMATIONS) > _MAX_PENDING_TOKENS:
            _PENDING_CONFIRMATIONS.popitem(last=False)
        confirm_cb = f"confirm_tok|{token}"

    cancel_cb = f"cancel|{command}"
    if len(cancel_cb.encode("utf-8")) > _MAX_CALLBACK_BYTES:
        cancel_cb = "cancel|action"

    return [
        [
            {"text": "✅ Confirm", "callback_data": confirm_cb},
            {"text": "❌ Cancel", "callback_data": cancel_cb},
        ]
    ]


def main_menu_buttons() -> Keyboard:
    return [
        [
            {"text": "📡 Status", "callback_data": "cmd|status"},
            {"text": "📊 Dashboard", "callback_data": "cmd|dashboard"},
        ],
        [
            {"text": "⚡ Pulse", "callback_data": "cmd|pulse"},
            {"text": "🐛 Errors", "callback_data": "cmd|errors"},
        ],
        [
            {"text": "🤖 AI Health", "callback_data": "cmd|ai"},
            {"text": "🚨 Incidents", "callback_data": "cmd|incidents"},
        ],
        [
            {"text": "💳 Payments", "callback_data": "cmd|payments"},
            {"text": "🎁 Store Orders", "callback_data": "cmd|orders"},
        ],
        [
            {"text": "👥 Users", "callback_data": "cmd|users"},
            {"text": "🏆 Points", "callback_data": "cmd|points"},
        ],
        [
            {"text": "📈 Analytics", "callback_data": "cmd|analytics"},
            {"text": "📋 Reports", "callback_data": "cmd|reports"},
        ],
        [
            {"text": "🗄️ Database", "callback_data": "cmd|database"},
            {"text": "🛡️ Security", "callback_data": "cmd|security"},
        ],
    ]


def refresh_button(command: str) -> Keyboard:
    return [[{"text": "🔄 Refresh", "callback_data": f"cmd|{command}"}]]


_REFRESHABLE = {
    "status",
    "dashboard",
    "pulse",
    "ai",
    "payments",
    "orders",
    "points",
    "incidents",
    "users",
    "database",
    "storage",
    "system",
    "security",
    "analytics",
    "reports",
    "errors",
    "logs",
}
_MENU_COMMANDS = {"start", "help"}


def buttons_for(command: str, args: list[str]) -> Keyboard | None:
    if command in _MENU_COMMANDS:
        return main_menu_buttons()
    if command in _REFRESHABLE:
        return refresh_button(command)
    return None
