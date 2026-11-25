"""
bot/utils/keyboards.py

Generates Telegram inline keyboards as plain, Telegram-library-agnostic
data: list[list[{"text": str, "callback_data": str}]].

Callback data format (kept within Telegram's 64-byte cap):
  "cmd|<command>"                — re-run a read-only command
  "cmd|<command>|<a,b,c>"        — run a command with args (when <= 64 bytes)
  "cmd_tok|<token>"              — run a command with longer args
  "confirm|<command>|<a,b,c>"    — confirm pending action (when <= 64 bytes)
  "confirm_tok|<token>"          — confirm pending action with longer args
  "cancel|<command>"             — cancel a pending action
"""

from __future__ import annotations

import secrets
from collections import OrderedDict
from contextvars import ContextVar

Button = dict[str, str]
Keyboard = list[list[Button]]

_MAX_CALLBACK_BYTES = 64
_MAX_PENDING_TOKENS = 200
_PENDING_CONFIRMATIONS: OrderedDict[str, tuple[str, list[str]]] = OrderedDict()
_PENDING_COMMANDS: OrderedDict[str, tuple[str, list[str]]] = OrderedDict()
_REPLY_EXTRA_BUTTONS: ContextVar[Keyboard | None] = ContextVar("_REPLY_EXTRA_BUTTONS", default=None)


def clear_reply_buttons() -> None:
    _REPLY_EXTRA_BUTTONS.set(None)


def set_reply_buttons(buttons: Keyboard) -> None:
    _REPLY_EXTRA_BUTTONS.set(buttons)


def resolve_confirmation_token(token: str) -> tuple[str, list[str]] | None:
    """Pops and returns (command, extra_args) for a short confirmation token."""
    return _PENDING_CONFIRMATIONS.pop(token, None)


def resolve_command_token(token: str) -> tuple[str, list[str]] | None:
    """Returns (command, args) for a short command token (reusable within cache window)."""
    return _PENDING_COMMANDS.get(token)


def cmd_button(text: str, command: str, extra_args: list[str] | None = None) -> Button:
    args = list(extra_args or [])
    if not args:
        return {"text": text, "callback_data": f"cmd|{command}"}
    args_csv = ",".join(args)
    direct = f"cmd|{command}|{args_csv}"
    if len(direct.encode("utf-8")) <= _MAX_CALLBACK_BYTES:
        return {"text": text, "callback_data": direct}
    token = secrets.token_hex(6)
    _PENDING_COMMANDS[token] = (command, args)
    while len(_PENDING_COMMANDS) > _MAX_PENDING_TOKENS:
        _PENDING_COMMANDS.popitem(last=False)
    return {"text": text, "callback_data": f"cmd_tok|{token}"}


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
            {"text": "✅ تأكيد", "callback_data": confirm_cb},
            {"text": "❌ إلغاء", "callback_data": cancel_cb},
        ]
    ]


def main_menu_buttons() -> Keyboard:
    return [
        [
            {"text": "📡 الحالة", "callback_data": "cmd|status"},
            {"text": "📊 لوحة التحكم", "callback_data": "cmd|dashboard"},
        ],
        [
            {"text": "⚡ النبض الحي", "callback_data": "cmd|pulse"},
            {"text": "🐛 الأخطاء", "callback_data": "cmd|errors"},
        ],
        [
            {"text": "🤖 حالة الذكاء", "callback_data": "cmd|ai"},
            {"text": "🚨 الحوادث", "callback_data": "cmd|incidents"},
        ],
        [
            {"text": "💳 المدفوعات", "callback_data": "cmd|payments"},
            {"text": "🎁 طلبات المتجر", "callback_data": "cmd|orders"},
        ],
        [
            {"text": "👥 المستخدمون", "callback_data": "cmd|users"},
            {"text": "🏆 النقاط", "callback_data": "cmd|points"},
        ],
        [
            {"text": "💎 الباقات", "callback_data": "cmd|plans"},
            {"text": "📝 الاختبارات", "callback_data": "cmd|quizzes"},
        ],
        [
            {"text": "📈 التحليلات", "callback_data": "cmd|analytics"},
            {"text": "📋 التقارير", "callback_data": "cmd|reports"},
        ],
        [
            {"text": "🗄️ قاعدة البيانات", "callback_data": "cmd|database"},
            {"text": "🛡️ الأمان", "callback_data": "cmd|security"},
        ],
        [
            {"text": "🎟️ الكوبونات", "callback_data": "cmd|coupon"},
            {"text": "⚙️ المنصة", "callback_data": "cmd|platform"},
        ],
        [
            {"text": "🔑 فحص المفاتيح", "callback_data": "cmd|envcheck"},
        ],
    ]


def back_to_menu_buttons() -> Keyboard:
    return [[{"text": "🔙 القائمة الرئيسية", "callback_data": "cmd|start"}]]


def refresh_button(command: str, args: list[str] | None = None) -> Keyboard:
    return [
        [
            cmd_button("🔄 تحديث", command, args),
            {"text": "🔙 القائمة الرئيسية", "callback_data": "cmd|start"},
        ]
    ]


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
    "vitals",
    "topusers",
    "coupon",
    "platform",
    "trial",
    "plans",
    "quizzes",
    "envcheck",
}
_MENU_COMMANDS = {"start", "help"}


def _default_filter_rows(command: str) -> Keyboard:
    if command == "users":
        return [[
            cmd_button("👥 الكل", "users"),
            cmd_button("⭐ البريميوم", "users", ["premium"]),
            cmd_button("🚫 الموقوفون", "users", ["suspended"]),
        ]]
    if command == "payments":
        return [[
            cmd_button("⏳ المعلّقة", "payments"),
            cmd_button("📋 الكل", "payments", ["all"]),
        ]]
    if command == "topusers":
        return [[
            cmd_button("🏆 حسب XP", "topusers", ["xp"]),
            cmd_button("💰 حسب النقاط", "topusers", ["points"]),
        ]]
    return []


def buttons_for(command: str, args: list[str]) -> Keyboard | None:
    if command in _MENU_COMMANDS:
        return main_menu_buttons()
    rows: Keyboard = list(_REPLY_EXTRA_BUTTONS.get() or [])
    if not rows:
        rows.extend(_default_filter_rows(command))
    if command in _REFRESHABLE:
        rows.extend(refresh_button(command, args))
    else:
        rows.extend(back_to_menu_buttons())
    return rows
