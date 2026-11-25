"""
bot/utils/keyboards.py

Generates Telegram inline keyboards as plain, Telegram-library-agnostic
data: list[list[{"text": str, "callback_data": str}]].

Callback data format (kept within Telegram's 64-byte cap):
  "cmd|<command>"                — re-run a read-only command
  "cmd|<command>|<a,b,c>"        — run a command with args (when <= 64 bytes)
  "cmdp|<parent>|<command>|..."  — run a command and remember its parent page
  "cmd_tok|<token>"              — run a command with longer args
  "cmdp_tok|<token>"             — run a command with longer args and a parent page
  "confirm|<command>|<a,b,c>"    — confirm pending action (when <= 64 bytes)
  "confirm_tok|<token>"          — confirm pending action with longer args
  "cancel_tok|<token>"            — cancel and invalidate a pending action
"""

from __future__ import annotations

import secrets
import threading
import time
from collections import OrderedDict
from contextvars import ContextVar

Button = dict[str, str]
Keyboard = list[list[Button]]

_MAX_CALLBACK_BYTES = 64
_MAX_PENDING_TOKENS = 200
_CONFIRMATION_TTL_SECONDS = 300
_PENDING_CONFIRMATIONS: OrderedDict[str, tuple[str, list[str], int, int, float]] = OrderedDict()
_CONFIRMATION_LOCK = threading.Lock()
_PENDING_COMMANDS: OrderedDict[str, tuple[str, list[str]]] = OrderedDict()
_PENDING_COMMAND_ORIGINS: OrderedDict[str, str] = OrderedDict()
_REPLY_EXTRA_BUTTONS: ContextVar[Keyboard | None] = ContextVar("_REPLY_EXTRA_BUTTONS", default=None)
_BUTTON_ORIGIN: ContextVar[str | None] = ContextVar("_BUTTON_ORIGIN", default=None)
_BUTTON_PARENT: ContextVar[str | None] = ContextVar("_BUTTON_PARENT", default=None)


def clear_reply_buttons() -> None:
    _REPLY_EXTRA_BUTTONS.set(None)


def set_reply_buttons(buttons: Keyboard) -> None:
    _REPLY_EXTRA_BUTTONS.set(buttons)


def set_button_origin(command: str | None) -> None:
    """Set the page that generated the current screen's inline buttons."""
    _BUTTON_ORIGIN.set(command or None)


def set_button_parent(command: str | None) -> None:
    """Set the page that the current screen's back button should open."""
    _BUTTON_PARENT.set(command or None)


def resolve_confirmation_token(
    token: str, *, user_id: int, chat_id: int
) -> tuple[str, list[str]] | None:
    """Atomically consume a confirmation for its initiating user and chat."""
    with _CONFIRMATION_LOCK:
        pending = _PENDING_CONFIRMATIONS.get(token)
        if pending is None:
            return None
        command, args, owner_user_id, owner_chat_id, expires_at = pending
        if time.monotonic() >= expires_at:
            _PENDING_CONFIRMATIONS.pop(token, None)
            return None
        if owner_user_id != user_id or owner_chat_id != chat_id:
            return None
        _PENDING_CONFIRMATIONS.pop(token, None)
        return command, args


def resolve_command_token(token: str) -> tuple[str, list[str]] | None:
    """Returns (command, args) for a short command token (reusable within cache window)."""
    return _PENDING_COMMANDS.get(token)


def resolve_command_origin(token: str) -> str | None:
    """Return the page that created a long command token, if any."""
    return _PENDING_COMMAND_ORIGINS.get(token)


def cmd_button(text: str, command: str, extra_args: list[str] | None = None) -> Button:
    args = list(extra_args or [])
    origin = _BUTTON_ORIGIN.get()
    prefix = f"cmdp|{origin}|{command}" if origin else f"cmd|{command}"
    if not args:
        return {"text": text, "callback_data": prefix}
    args_csv = ",".join(args)
    direct = f"{prefix}|{args_csv}"
    if len(direct.encode("utf-8")) <= _MAX_CALLBACK_BYTES:
        return {"text": text, "callback_data": direct}
    token = secrets.token_hex(6)
    _PENDING_COMMANDS[token] = (command, args)
    while len(_PENDING_COMMANDS) > _MAX_PENDING_TOKENS:
        _PENDING_COMMANDS.popitem(last=False)
    token_prefix = "cmdp_tok" if origin else "cmd_tok"
    if origin:
        _PENDING_COMMAND_ORIGINS[token] = origin
        while len(_PENDING_COMMAND_ORIGINS) > _MAX_PENDING_TOKENS:
            _PENDING_COMMAND_ORIGINS.popitem(last=False)
    return {"text": text, "callback_data": f"{token_prefix}|{token}"}


def confirmation_buttons(
    command: str,
    extra_args: list[str] | None = None,
    *,
    user_id: int,
    chat_id: int,
) -> Keyboard:
    """Create an opaque confirmation bound to its initiator and chat."""
    args = list(extra_args or [])
    token = secrets.token_urlsafe(18)
    with _CONFIRMATION_LOCK:
        _PENDING_CONFIRMATIONS[token] = (
            command,
            args,
            user_id,
            chat_id,
            time.monotonic() + _CONFIRMATION_TTL_SECONDS,
        )
        while len(_PENDING_CONFIRMATIONS) > _MAX_PENDING_TOKENS:
            _PENDING_CONFIRMATIONS.popitem(last=False)

    return [[
        {"text": "✅ تأكيد", "callback_data": f"confirm_tok|{token}"},
        {"text": "❌ إلغاء", "callback_data": f"cancel_tok|{token}"},
    ]]


def main_menu_buttons() -> Keyboard:
    return [
        [
            {"text": "📊 النظرة العامة", "callback_data": "cmd|monitor"},
            {"text": "🟢 حالة المنصة", "callback_data": "cmd|status"},
        ],
        [
            {"text": "👥 المستخدمون والنقاط", "callback_data": "cmd|people"},
            {"text": "💳 العضويات والمدفوعات", "callback_data": "cmd|commerce"},
        ],
        [
            {"text": "📝 المحتوى والاختبارات", "callback_data": "cmd|content"},
            {"text": "⚙️ إعدادات Quiz Space", "callback_data": "cmd|platform_admin"},
        ],
        [
            {"text": "🚀 النشر والنسخ الاحتياطي", "callback_data": "cmd|operations"},
            {"text": "🛡️ الأمان والسجلات", "callback_data": "cmd|security_center"},
        ],
        [
            {"text": "🔄 تحديث الحالة", "callback_data": "cmd|dashboard"},
            {"text": "❓ دليل الاستخدام", "callback_data": "cmd|help"},
        ],
    ]


def back_to_menu_buttons(parent: str | None = None) -> Keyboard:
    if parent:
        return [[{"text": "🔙 رجوع", "callback_data": f"cmd|{parent}"}]]
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
_SECTION_COMMANDS = {
    "monitor",
    "people",
    "commerce",
    "content",
    "platform_admin",
    "operations",
    "security_center",
}


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
    elif command in _SECTION_COMMANDS:
        rows.append([{"text": "🏠 القائمة الرئيسية", "callback_data": "cmd|start"}])
    else:
        rows.extend(back_to_menu_buttons(_BUTTON_PARENT.get()))
    return rows
