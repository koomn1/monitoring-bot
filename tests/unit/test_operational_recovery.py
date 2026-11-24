from __future__ import annotations

import logging

import pytest

from bot.core.exceptions import ConfigurationError
from bot.core.router import CommandContext
from bot.modules.deployment import service as deployment_service
from bot.modules.analytics import service as analytics_service
from bot.modules.telegram_commands.handlers import handle_dashboard


def _context() -> CommandContext:
    return CommandContext(user_id=1, chat_id=1, command="dashboard", args=[], raw_text="/dashboard")


@pytest.mark.asyncio
async def test_dashboard_reports_missing_github_config_without_crashing(monkeypatch):
    async def _analytics():
        return {"period": "24h", "error_count": None}

    async def _deployment():
        raise ConfigurationError("GITHUB_REPO is not configured")

    monkeypatch.setattr(analytics_service, "get_analytics_summary", _analytics)
    monkeypatch.setattr(deployment_service, "get_deployment_status", _deployment)

    response = await handle_dashboard(_context())

    assert "Not configured" in response
    assert "GITHUB_REPO is not configured" in response
    assert "Errors (24h): N/A" in response


def test_configure_logging_suppresses_http_transport_urls():
    from bot.main import configure_logging

    httpx_logger = logging.getLogger("httpx")
    httpcore_logger = logging.getLogger("httpcore")
    original_levels = (httpx_logger.level, httpcore_logger.level)
    try:
        configure_logging()
        assert httpx_logger.level >= logging.WARNING
        assert httpcore_logger.level >= logging.WARNING
    finally:
        httpx_logger.setLevel(original_levels[0])
        httpcore_logger.setLevel(original_levels[1])


def test_telegram_token_redaction_filter_removes_url_credential():
    from bot.main import _TelegramTokenRedactionFilter

    record = logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname="test",
        lineno=1,
        msg="POST https://api.telegram.org/bot123456:TEST_TOKEN/getMe",
        args=(),
        exc_info=None,
    )

    assert _TelegramTokenRedactionFilter().filter(record)
    assert "TEST_TOKEN" not in record.getMessage()
    assert "/bot[REDACTED]/getMe" in record.getMessage()
