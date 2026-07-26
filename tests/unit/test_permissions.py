"""
tests/unit/test_permissions.py

Unit tests for bot/core/permissions.py — the Bot's RBAC enforcement.
This is the single most security-critical module in the codebase (see
docs/07-security.md), so it was the first to get real test coverage
after the initial skeleton audit found tests/ was empty.

get_role() now consults the bot_users table (for /setrole-granted
Admin/Viewer roles) before falling back to environment variables — see
bot/core/permissions.py's module docstring. These tests stub out the
database lookup (bot.db.repositories.users_repo.get_bot_user) so they
stay fast and don't require a real Supabase connection; DB-backed role
resolution itself is covered by test_setrole_grants_db_role below,
which stubs a specific return value instead of None.
"""

from __future__ import annotations

import importlib

import pytest

pytestmark = pytest.mark.asyncio


def _reload_permissions(monkeypatch, *, owners="", admins="", viewers=""):
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
    return permissions_module


def _stub_db_role(monkeypatch, permissions_module, row: dict | None):
    """Replaces the DB lookup get_role() makes with a fixed return value,
    so tests exercise the env-fallback path deterministically without a
    real database."""

    async def _fake_get_bot_user(user_id: int):
        return row

    import bot.db.repositories.users_repo as users_repo_module

    monkeypatch.setattr(users_repo_module, "get_bot_user", _fake_get_bot_user)
    # permissions.py imports get_bot_user via a deferred (function-local)
    # import, so patching the source module is sufficient — no need to
    # also patch a name inside permissions_module.


@pytest.fixture
def perms(monkeypatch):
    module = _reload_permissions(monkeypatch, owners="111", admins="222", viewers="333")
    _stub_db_role(monkeypatch, module, row=None)  # no DB override by default
    return module


async def test_owner_role_resolved(perms):
    assert await perms.get_role(111) == perms.Role.OWNER


async def test_admin_role_resolved(perms):
    assert await perms.get_role(222) == perms.Role.ADMIN


async def test_viewer_role_resolved(perms):
    assert await perms.get_role(333) == perms.Role.VIEWER


async def test_unknown_user_has_no_role(perms):
    assert await perms.get_role(999) is None


async def test_require_known_user_raises_for_stranger(perms):
    with pytest.raises(perms.UnauthorizedError):
        await perms.require_known_user(999)


async def test_viewer_cannot_run_admin_command(perms):
    with pytest.raises(perms.ForbiddenError):
        await perms.require_role(333, perms.Role.ADMIN)


async def test_admin_can_run_admin_command(perms):
    await perms.require_role(222, perms.Role.ADMIN)  # must not raise


async def test_owner_satisfies_lower_role_requirements(perms):
    await perms.require_role(111, perms.Role.VIEWER)  # must not raise


async def test_unlisted_command_defaults_to_owner_only(perms):
    with pytest.raises(perms.ForbiddenError):
        await perms.require_command_permission(222, "some_future_unlisted_command")
    await perms.require_command_permission(111, "some_future_unlisted_command")  # must not raise


async def test_status_is_viewer_accessible(perms):
    await perms.require_command_permission(333, "status")  # must not raise


async def test_rollback_requires_owner(perms):
    with pytest.raises(perms.ForbiddenError):
        await perms.require_command_permission(222, "rollback")
    await perms.require_command_permission(111, "rollback")  # must not raise


async def test_restore_requires_owner(perms):
    with pytest.raises(perms.ForbiddenError):
        await perms.require_command_permission(222, "restore")


async def test_deploy_allows_admin(perms):
    await perms.require_command_permission(222, "deploy")  # must not raise


async def test_list_env_authorized_users_includes_every_role(perms):
    users = dict(perms.list_env_authorized_users())
    assert users[111] == perms.Role.OWNER
    assert users[222] == perms.Role.ADMIN
    assert users[333] == perms.Role.VIEWER


async def test_no_owners_configured_still_resolves_admin(monkeypatch):
    module = _reload_permissions(monkeypatch, owners="", admins="222", viewers="")
    _stub_db_role(monkeypatch, module, row=None)
    assert await module.get_role(222) == module.Role.ADMIN
    assert await module.get_role(111) is None


async def test_setrole_grants_db_role_over_no_env_role(monkeypatch):
    # A user with NO env-based role at all should still resolve to ADMIN
    # if /setrole granted it in the database — this is the whole point
    # of the DB-backed RBAC upgrade.
    module = _reload_permissions(monkeypatch, owners="111", admins="", viewers="")
    _stub_db_role(monkeypatch, module, row={"telegram_user_id": 555, "role": "ADMIN"})
    assert await module.get_role(555) == module.Role.ADMIN


async def test_db_role_of_owner_is_never_honored(monkeypatch):
    # Defense in depth: even if a bot_users row somehow says role=OWNER
    # (e.g. from the audit-log upsert in auth/service.py, which writes
    # whatever role was resolved — including "OWNER" for env-based
    # owners), get_role() must NEVER grant Owner from the database.
    module = _reload_permissions(monkeypatch, owners="111", admins="", viewers="")
    _stub_db_role(monkeypatch, module, row={"telegram_user_id": 555, "role": "OWNER"})
    assert await module.get_role(555) is None
