from __future__ import annotations

from bot.core.permissions import COMMAND_MIN_ROLE, Role
from bot.utils.keyboards import buttons_for, main_menu_buttons


def _callbacks(keyboard):
    return [button["callback_data"] for row in keyboard for button in row]


def test_main_menu_uses_compact_section_navigation():
    callbacks = _callbacks(main_menu_buttons())

    assert callbacks == [
        "cmd|monitor",
        "cmd|status",
        "cmd|people",
        "cmd|commerce",
        "cmd|content",
        "cmd|platform_admin",
        "cmd|operations",
        "cmd|security_center",
        "cmd|dashboard",
        "cmd|help",
    ]
    assert all(len(callback.encode("utf-8")) <= 64 for callback in callbacks)


def test_section_result_keeps_navigation_home():
    keyboard = buttons_for("people", [])

    assert keyboard is not None
    assert keyboard[-1] == [{"text": "🏠 القائمة الرئيسية", "callback_data": "cmd|start"}]


def test_new_sections_fail_closed_with_explicit_roles():
    assert COMMAND_MIN_ROLE["monitor"] == Role.VIEWER
    assert COMMAND_MIN_ROLE["people"] == Role.ADMIN
    assert COMMAND_MIN_ROLE["platform_admin"] == Role.OWNER
    assert COMMAND_MIN_ROLE["secrets"] == Role.OWNER
