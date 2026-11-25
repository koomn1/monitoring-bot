from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from bot.core.exceptions import ConfirmationRequiredError
from bot.core.router import CommandContext
from bot.modules.telegram_commands import handlers


def _ctx(command: str, args: list[str] | None = None) -> CommandContext:
    return CommandContext(user_id=111, chat_id=222, command=command, args=args or [], raw_text="")


@pytest.mark.asyncio
async def test_restart_requires_confirmation_before_scheduling(monkeypatch):
    from bot.modules.runtime import service as runtime_service

    restart = AsyncMock()
    monkeypatch.setattr(runtime_service, "request_restart", restart)

    with pytest.raises(ConfirmationRequiredError) as exc_info:
        await handlers.handle_restart(_ctx("restart"))

    assert exc_info.value.command == "restart"
    restart.assert_not_awaited()


@pytest.mark.asyncio
async def test_restart_is_scheduled_only_after_confirmation(monkeypatch):
    from bot.modules.runtime import service as runtime_service

    restart = AsyncMock()
    monkeypatch.setattr(runtime_service, "request_restart", restart)

    result = await handlers.handle_restart(_ctx("restart", ["confirm"]))

    assert "إعادة تشغيل" in result
    restart.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_settings_requires_confirmation_before_write(monkeypatch):
    from bot.db.repositories import config_repo

    set_setting = AsyncMock()
    monkeypatch.setattr(config_repo, "set_setting", set_setting)

    with pytest.raises(ConfirmationRequiredError) as exc_info:
        await handlers.handle_settings(_ctx("settings", ["maintenance_mode", "true"]))

    assert exc_info.value.command == "settings"
    assert exc_info.value.extra_args == ["maintenance_mode", "true"]
    set_setting.assert_not_awaited()


@pytest.mark.asyncio
async def test_settings_writes_only_after_confirmation(monkeypatch):
    from bot.db.repositories import config_repo

    set_setting = AsyncMock()
    monkeypatch.setattr(config_repo, "set_setting", set_setting)

    result = await handlers.handle_settings(_ctx("settings", ["maintenance_mode", "true", "confirm"]))

    assert "maintenance_mode" in result
    set_setting.assert_awaited_once_with("maintenance_mode", True)


@pytest.mark.asyncio
async def test_setrole_requires_confirmation_before_write(monkeypatch):
    from bot.db.repositories import users_repo

    set_role = AsyncMock()
    monkeypatch.setattr(users_repo, "set_role", set_role)

    with pytest.raises(ConfirmationRequiredError) as exc_info:
        await handlers.handle_setrole(_ctx("setrole", ["987", "ADMIN"]))

    assert exc_info.value.command == "setrole"
    assert exc_info.value.extra_args == ["987", "ADMIN"]
    set_role.assert_not_awaited()


@pytest.mark.asyncio
async def test_setrole_writes_only_after_confirmation(monkeypatch):
    from bot.db.repositories import users_repo

    set_role = AsyncMock()
    monkeypatch.setattr(users_repo, "set_role", set_role)

    result = await handlers.handle_setrole(_ctx("setrole", ["987", "ADMIN", "confirm"]))

    assert "987" in result
    set_role.assert_awaited_once_with(987, "ADMIN")
