"""
tests/unit/test_users.py

Unit tests for bot/modules/users/service.py — covers the user lookup
path added when NotImplementedError was removed (see modules/02-users-module.md).
Stubs the repository layer directly rather than a real Supabase
connection, matching the pattern in test_permissions.py.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
def users_service(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")

    import bot.modules.users.service as service_module

    return service_module


async def test_get_user_detail_by_uid(monkeypatch, users_service):
    async def _fake_lookup(identifier):
        assert identifier == "abc123"
        return {"uid": "abc123", "email": "a@example.com"}

    monkeypatch.setattr(users_service, "get_user_by_identifier", _fake_lookup)
    result = await users_service.get_user_detail("abc123")
    assert result == {"uid": "abc123", "email": "a@example.com"}


async def test_get_user_detail_not_found_returns_none(monkeypatch, users_service):
    async def _fake_lookup(identifier):
        return None

    monkeypatch.setattr(users_service, "get_user_by_identifier", _fake_lookup)
    result = await users_service.get_user_detail("nonexistent")
    assert result is None


async def test_get_user_summary_combines_count_premium_and_recent(monkeypatch, users_service):
    async def _fake_count():
        return 42

    async def _fake_premium():
        return 7

    async def _fake_recent(limit):
        assert limit == 5
        return [{"uid": "1"}, {"uid": "2"}]

    monkeypatch.setattr(users_service, "get_quiz_space_user_count", _fake_count)
    monkeypatch.setattr(users_service, "get_premium_user_count", _fake_premium)
    monkeypatch.setattr(users_service, "get_recent_signups", _fake_recent)

    summary = await users_service.get_user_summary()
    assert summary["total_users"] == 42
    assert summary["premium_users"] == 7
    assert len(summary["recent_signups"]) == 2
