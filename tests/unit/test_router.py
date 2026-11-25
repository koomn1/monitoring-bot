"""
tests/unit/test_router.py

Unit tests for bot/core/router.py — the central command dispatcher.
Covers: unknown-command handling, permission denial, rate limiting, the
confirmation-required flow (destructive actions get a Confirm/Cancel
keyboard instead of executing immediately), and the generic-exception
safety net. Registers throwaway test commands rather than importing
bot/modules/telegram_commands/handlers.py, so these tests don't depend
on the full module graph (Supabase/GitHub/etc. clients).
"""

from __future__ import annotations

import importlib

import pytest

pytestmark = pytest.mark.asyncio


def _fresh_router(monkeypatch, *, owners="111", admins="222", viewers="333"):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("OWNER_USER_IDS", owners)
    monkeypatch.setenv("ADMIN_USER_IDS", admins)
    monkeypatch.setenv("VIEWER_USER_IDS", viewers)

    import bot.config as config_module
    importlib.reload(config_module)
    import bot.core.permissions as permissions_module
    importlib.reload(permissions_module)
    import bot.core.rate_limiter as rate_limiter_module
    importlib.reload(rate_limiter_module)
    import bot.core.router as router_module
    importlib.reload(router_module)

    # get_role() now checks bot_users in the database first — stub it to
    # "no override" so these tests exercise the env-based roles above
    # deterministically, without a real Supabase connection.
    async def _fake_get_bot_user(user_id: int):
        return None

    import bot.db.repositories.users_repo as users_repo_module

    monkeypatch.setattr(users_repo_module, "get_bot_user", _fake_get_bot_user)

    return router_module, permissions_module


@pytest.fixture
def router_env(monkeypatch):
    router_module, permissions_module = _fresh_router(monkeypatch)

    permissions_module.COMMAND_MIN_ROLE["testcmd"] = permissions_module.Role.VIEWER
    permissions_module.COMMAND_MIN_ROLE["testdestructive"] = permissions_module.Role.ADMIN

    @router_module.command("testcmd")
    async def _handle_testcmd(ctx):
        return "ok"

    @router_module.command("testdestructive")
    async def _handle_testdestructive(ctx):
        from bot.core.exceptions import ConfirmationRequiredError

        if "confirm" not in ctx.args:
            raise ConfirmationRequiredError("testdestructive", "Are you sure?")
        return "done"

    @router_module.command("testboom")
    async def _handle_testboom(ctx):
        raise RuntimeError("boom")

    permissions_module.COMMAND_MIN_ROLE["testboom"] = permissions_module.Role.VIEWER

    return router_module


def _ctx(router_module, user_id, command, args=None):
    return router_module.CommandContext(
        user_id=user_id, chat_id=1, command=command, args=args or [], raw_text=""
    )


async def test_unknown_command_returns_helpful_message(router_env):
    text, buttons = await router_env.dispatch(_ctx(router_env, 111, "nope"))
    assert "أمر غير معروف" in text
    assert buttons is None


async def test_unauthorized_user_is_denied(router_env):
    text, buttons = await router_env.dispatch(_ctx(router_env, 999, "testcmd"))
    assert "غير مصرح" in text
    assert buttons is None


async def test_authorized_user_gets_handler_response(router_env):
    text, buttons = await router_env.dispatch(_ctx(router_env, 333, "testcmd"))
    assert text == "ok"


async def test_insufficient_role_is_forbidden(router_env):
    text, buttons = await router_env.dispatch(_ctx(router_env, 333, "testdestructive"))
    assert "صلاحية" in text


async def test_destructive_action_requires_confirmation_first(router_env):
    text, buttons = await router_env.dispatch(_ctx(router_env, 222, "testdestructive"))
    assert "Are you sure" in text
    assert buttons is not None
    assert buttons[0][0]["text"] == "✅ تأكيد"
    callback_data = buttons[0][0]["callback_data"]
    assert callback_data.startswith("confirm_tok|")
    from bot.utils.keyboards import resolve_confirmation_token
    token = callback_data.split("|", 1)[1]
    assert resolve_confirmation_token(token, user_id=222, chat_id=1) == ("testdestructive", [])


async def test_destructive_action_executes_when_confirmed(router_env):
    text, buttons = await router_env.dispatch(
        _ctx(router_env, 222, "testdestructive", args=["confirm"])
    )
    assert text == "done"


async def test_unhandled_exception_returns_generic_message(router_env):
    text, buttons = await router_env.dispatch(_ctx(router_env, 111, "testboom"))
    assert "خطأ غير متوقع" in text
    assert buttons is None


async def test_rate_limit_blocks_excessive_requests(router_env):
    ctx_factory = lambda: _ctx(router_env, 333, "testcmd")  # noqa: E731
    # default limit is 8 per 10s window (bot/core/rate_limiter.py)
    for _ in range(8):
        text, _ = await router_env.dispatch(ctx_factory())
        assert text == "ok"
    text, buttons = await router_env.dispatch(ctx_factory())
    assert "too many commands" in text.lower()
    assert buttons is None
