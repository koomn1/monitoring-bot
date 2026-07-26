"""
tests/unit/test_automation.py

Unit tests for bot/modules/automation/service.py — the scheduled-job
layer. The core guarantee under test: every job function must swallow
its own exceptions and never raise, since there is no caller to handle
an error for an unattended scheduled job (see
docs/03-system-architecture.md §9). A job that raises would otherwise
deregister itself from APScheduler silently.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
def automation(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")

    import bot.modules.automation.service as automation_module

    return automation_module


async def test_run_health_checks_survives_one_monitor_failing(monkeypatch, automation):
    """If the website monitor throws (e.g. WEBSITE_URL misconfigured),
    the other monitors must still run — asyncio.gather(..., return_exceptions=True)
    is what makes this true; this test would fail if that flag were
    ever accidentally removed."""

    calls = {"api": False, "database": False, "storage": False}

    async def _boom():
        raise RuntimeError("website monitor exploded")

    async def _ok_api():
        calls["api"] = True
        return {"status": "up"}

    async def _ok_db():
        calls["database"] = True
        return {"status": "up"}

    async def _ok_storage():
        calls["storage"] = True
        return {"status": "up"}

    monkeypatch.setattr(automation.website_monitor, "check_website", _boom)
    monkeypatch.setattr(automation.api_monitor, "check_api", _ok_api)
    monkeypatch.setattr(automation.database_monitor, "check_database", _ok_db)
    monkeypatch.setattr(automation.storage_monitor, "check_storage", _ok_storage)

    await automation.run_health_checks()  # must not raise

    assert calls == {"api": True, "database": True, "storage": True}


async def test_run_scheduled_backup_swallows_errors(monkeypatch, automation):
    async def _boom(confirmed=False):
        raise RuntimeError("GitHub is down")

    monkeypatch.setattr(automation.backup_service, "trigger_backup", _boom)
    await automation.run_scheduled_backup()  # must not raise


async def test_run_scheduled_backup_bypasses_confirmation_gate(monkeypatch, automation):
    """Scheduled backups are the one legitimate case where confirmed=True
    is passed automatically — see modules/12-backup-module.md §7."""
    received = {}

    async def _capture(confirmed=False):
        received["confirmed"] = confirmed
        return "ok"

    monkeypatch.setattr(automation.backup_service, "trigger_backup", _capture)
    await automation.run_scheduled_backup()
    assert received["confirmed"] is True


async def test_run_daily_report_swallows_errors(monkeypatch, automation):
    async def _boom():
        raise RuntimeError("analytics unreachable")

    monkeypatch.setattr(automation.reports_service, "generate_daily_report", _boom)
    await automation.run_daily_report()  # must not raise


async def test_run_security_scan_notifies_on_critical_alerts(monkeypatch, automation):
    import bot.modules.github.service as github_service
    import bot.modules.notifications.service as notifications_service

    async def _fake_summary():
        return {"total_open": 3, "by_severity": {"critical": 2, "low": 1}}

    notified = []

    async def _fake_notify(details):
        notified.append(details)

    monkeypatch.setattr(github_service, "get_security_alerts_summary", _fake_summary)
    monkeypatch.setattr(notifications_service, "notify_security_alert", _fake_notify)

    await automation.run_security_scan()
    assert len(notified) == 1
    assert "2" in notified[0]
