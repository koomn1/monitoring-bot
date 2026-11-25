from __future__ import annotations

import pytest

from bot.core.exceptions import ConfigurationError
from bot.core.router import CommandContext
from bot.modules.api_monitor import service as api_monitor
from bot.modules.database_monitor import service as database_monitor
from bot.modules.storage_monitor import service as storage_monitor
from bot.modules.telegram_commands.handlers import handle_status
from bot.modules.website_monitor import service as website_monitor


def _context() -> CommandContext:
    return CommandContext(user_id=1, chat_id=1, command="status", args=[], raw_text="/status")


@pytest.mark.asyncio
async def test_status_continues_when_api_is_not_configured(monkeypatch):
    async def _website():
        return {"status": "up", "latency_ms": 23}

    async def _api():
        raise ConfigurationError("API_BASE_URL is not configured")

    async def _database():
        return {"status": "up", "latency_ms": 8}

    async def _storage():
        return {"status": "up", "bucket_count": 2}

    monkeypatch.setattr(website_monitor, "check_website", _website)
    monkeypatch.setattr(api_monitor, "check_api", _api)
    monkeypatch.setattr(database_monitor, "check_database", _database)
    monkeypatch.setattr(storage_monitor, "check_storage", _storage)

    response = await handle_status(_context())

    assert "الموقع: يعمل (23ms)" in response
    assert "الـ API: غير مهيأ" in response
    assert "قاعدة البيانات: يعمل" in response
    assert "التخزين: يعمل" in response


@pytest.mark.asyncio
async def test_status_continues_when_website_is_not_configured(monkeypatch):
    async def _website():
        raise ConfigurationError("WEBSITE_URL is not configured")

    async def _api():
        return {"status": "up", "latency_ms": 11}

    async def _database():
        return {"status": "up", "latency_ms": 8}

    async def _storage():
        return {"status": "up", "bucket_count": 2}

    monkeypatch.setattr(website_monitor, "check_website", _website)
    monkeypatch.setattr(api_monitor, "check_api", _api)
    monkeypatch.setattr(database_monitor, "check_database", _database)
    monkeypatch.setattr(storage_monitor, "check_storage", _storage)

    response = await handle_status(_context())

    assert "الموقع: غير مهيأ" in response
    assert "الـ API: يعمل (11ms)" in response
    assert "قاعدة البيانات: يعمل" in response
    assert "التخزين: يعمل" in response


def test_website_url_defaults_to_quiz_space(monkeypatch):
    monkeypatch.delenv("WEBSITE_URL", raising=False)

    from bot.config import Settings

    assert Settings().website_url == "https://quiz-space-app.pages.dev"
