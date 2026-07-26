"""
tests/unit/test_backup.py

Unit tests for bot/modules/backup/service.py — covers the confirmation
gate (backup and restore must never execute without explicit
confirmation, per docs/07-security.md §8) and the list_backups()
implementation added when NotImplementedError was removed.
"""

from __future__ import annotations

import pytest

from bot.core.exceptions import ConfirmationRequiredError

pytestmark = pytest.mark.asyncio


@pytest.fixture
def backup_service(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")

    import bot.modules.backup.service as service_module

    return service_module


async def test_trigger_backup_without_confirmation_raises(backup_service):
    with pytest.raises(ConfirmationRequiredError) as exc_info:
        await backup_service.trigger_backup(confirmed=False)
    assert exc_info.value.command == "backup"


async def test_trigger_backup_dispatches_workflow_when_confirmed(monkeypatch, backup_service):
    dispatched = []

    async def _fake_dispatch(workflow_file, ref="main", inputs=None):
        dispatched.append(workflow_file)

    async def _fake_notify():
        pass

    monkeypatch.setattr(backup_service.github_client, "dispatch_workflow", _fake_dispatch)
    monkeypatch.setattr(backup_service.notifications_service, "notify_backup_started", _fake_notify)

    result = await backup_service.trigger_backup(confirmed=True)
    assert dispatched == ["backup.yml"]
    assert "triggered" in result.lower()


async def test_trigger_restore_without_confirmation_raises_with_backup_id(backup_service):
    with pytest.raises(ConfirmationRequiredError) as exc_info:
        await backup_service.trigger_restore(confirmed=False, backup_id="12345")
    assert exc_info.value.command == "restore"
    assert exc_info.value.extra_args == ["12345"]


async def test_trigger_restore_dispatches_with_backup_id_when_confirmed(monkeypatch, backup_service):
    dispatched = []

    async def _fake_dispatch(workflow_file, ref="main", inputs=None):
        dispatched.append((workflow_file, inputs))

    async def _fake_notify(backup_id):
        pass

    monkeypatch.setattr(backup_service.github_client, "dispatch_workflow", _fake_dispatch)
    monkeypatch.setattr(backup_service.notifications_service, "notify_restore_started", _fake_notify)

    result = await backup_service.trigger_restore(confirmed=True, backup_id="99999")
    assert dispatched == [("restore.yml", {"backup_id": "99999"})]
    assert "99999" in result


async def test_list_backups_skips_failed_runs(monkeypatch, backup_service):
    async def _fake_list_runs(workflow_file, limit=10):
        return [
            {"id": 1, "conclusion": "success", "created_at": "2026-01-01"},
            {"id": 2, "conclusion": "failure", "created_at": "2026-01-02"},
        ]

    async def _fake_list_artifacts(run_id):
        assert run_id == 1  # the failed run (id=2) must never be queried for artifacts
        return [{"name": "backup-2026-01-01.sql", "size_in_bytes": 1024, "expired": False}]

    monkeypatch.setattr(backup_service.github_client, "list_workflow_runs", _fake_list_runs)
    monkeypatch.setattr(backup_service.github_client, "list_run_artifacts", _fake_list_artifacts)

    backups = await backup_service.list_backups()
    assert len(backups) == 1
    assert backups[0]["backup_id"] == "1"
    assert backups[0]["artifact_name"] == "backup-2026-01-01.sql"
