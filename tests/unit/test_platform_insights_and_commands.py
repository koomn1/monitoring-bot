"""
tests/unit/test_platform_insights_and_commands.py

Unit tests covering the enriched telemetry repository, insights service,
new & upgraded Telegram commands (/pulse, /ai, /payments, /incidents,
/dashboard, /users, /analytics, /reports, /ask, /errors), RBAC for new
commands, and operational anomaly alerts in automation/service.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from bot.core.exceptions import ConfigurationError
from bot.core.router import CommandContext

pytestmark = pytest.mark.asyncio


class _FakeQuery:
    def __init__(self, data, count=None, *, raise_exc=None):
        self._data = data
        self._count = count
        self._raise_exc = raise_exc

    def select(self, *args, **kwargs):
        return self

    def gte(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def in_(self, *args, **kwargs):
        return self

    def is_(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def execute(self):
        if self._raise_exc is not None:
            raise self._raise_exc
        return SimpleNamespace(data=self._data, count=self._count)


class _FakeTargetDb:
    def __init__(self, handlers: dict[str, _FakeQuery]):
        self._handlers = handlers

    def table(self, name: str):
        return self._handlers.get(name, _FakeQuery([], count=0))


async def test_ai_health_and_stuck_extraction_aggregation(monkeypatch):
    from bot.db.repositories import platform_repo

    now = datetime.now(timezone.utc)
    stale = (now - timedelta(minutes=45)).isoformat()
    recent = (now - timedelta(minutes=2)).isoformat()

    ai_rows = [
        {"operation": "generation", "provider": "inception", "model": "m1", "status": "success", "latency_ms": 800, "created_at": recent},
        {"operation": "generation", "provider": "inception", "model": "m1", "status": "success", "latency_ms": 1200, "created_at": recent},
        {
            "operation": "extraction",
            "provider": "openrouter",
            "model": "gemma",
            "status": "error",
            "latency_ms": 4000,
            "error_category": "timeout",
            "error_message": "Upstream timed out <script>",
            "created_at": recent,
        },
    ]
    ext_rows = [
        {
            "id": "job-stuck-1234",
            "extraction_mode": "literal",
            "status": "processing",
            "progress_percentage": 40,
            "provider": "openrouter",
            "processing_started_at": stale,
            "updated_at": stale,
            "created_at": stale,
        },
        {
            "id": "job-err-5678",
            "extraction_mode": "generate",
            "status": "error",
            "provider": "openrouter",
            "error_message": "PDF parse failed",
            "created_at": recent,
        },
    ]

    fake_db = _FakeTargetDb(
        {
            "ai_performance_logs": _FakeQuery(ai_rows),
            "extraction_jobs": _FakeQuery(ext_rows),
        }
    )
    monkeypatch.setattr(platform_repo, "target_db", lambda: fake_db)

    ai_summary = await platform_repo.get_ai_health_summary(hours=24)
    assert ai_summary["total_calls"] == 3
    assert ai_summary["success_count"] == 2
    assert ai_summary["error_count"] == 1
    assert ai_summary["success_rate_pct"] == 66.7
    assert ai_summary["by_provider"]["inception"]["calls"] == 2
    assert ai_summary["by_provider"]["openrouter"]["errors"] == 1
    assert len(ai_summary["recent_errors"]) == 1

    ext_summary = await platform_repo.get_extraction_jobs_summary(hours=24, stuck_minutes=20)
    assert ext_summary["processing_count"] == 1
    assert ext_summary["error_recent"] == 1
    assert len(ext_summary["stuck_jobs"]) == 1
    assert ext_summary["stuck_jobs"][0]["id"] == "job-stuck-1234"


async def test_platform_repo_degrades_gracefully_on_missing_table(monkeypatch):
    from bot.db.repositories import platform_repo

    fake_db = _FakeTargetDb(
        {"ai_performance_logs": _FakeQuery([], raise_exc=RuntimeError("relation does not exist"))}
    )
    monkeypatch.setattr(platform_repo, "target_db", lambda: fake_db)

    ai_summary = await platform_repo.get_ai_health_summary(hours=24)
    assert ai_summary["available"] is False
    assert ai_summary["total_calls"] == 0


async def test_new_command_handlers_render_useful_telemetry(monkeypatch):
    from bot.modules.ai_assistant import service as ai_assistant
    from bot.modules.platform_insights import service as insights_service
    from bot.modules.telegram_commands import handlers

    async def _fake_pulse(*, hours=24):
        return {
            "hours": hours,
            "users": {"total": 250, "premium": 35, "signups_recent": 12, "active_1h": 9, "active_24h": 64},
            "activity": {
                "total_quizzes": 420,
                "quizzes_recent": 18,
                "completions_recent": 140,
                "guest_attempts_recent": 30,
                "avg_score_pct": 78.5,
                "total_classrooms": 14,
                "cosmo_conversations_recent": 22,
                "top_quizzes": [{"id": "q1", "title": "Biology <101>", "total_plays": 95}],
            },
            "payments": {"pending_count": 3, "needs_info_count": 1},
            "ai": {"total_calls": 50, "success_rate_pct": 94.0, "avg_latency_ms": 920, "p95_latency_ms": 2100},
            "extraction": {"pending_count": 1, "processing_count": 1, "complete_recent": 8, "error_recent": 1, "stuck_jobs": []},
            "open_incidents": [],
        }

    async def _fake_ai_ext(*, hours=24):
        return {
            "hours": hours,
            "ai": {
                "available": True,
                "total_calls": 50,
                "success_count": 47,
                "error_count": 3,
                "success_rate_pct": 94.0,
                "avg_latency_ms": 920,
                "p95_latency_ms": 2100,
                "by_provider": {"openrouter": {"calls": 50, "errors": 3, "avg_latency_ms": 920}},
                "by_operation": {"generation": {"calls": 40, "errors": 2}},
                "recent_errors": [{"provider": "openrouter", "operation": "generation", "error_category": "timeout", "error_message": "timed out", "created_at": None}],
            },
            "extraction": {
                "available": True,
                "pending_count": 1,
                "processing_count": 0,
                "complete_recent": 8,
                "error_recent": 1,
                "stuck_jobs": [],
                "recent_errors": [],
            },
        }

    async def _fake_payments(*, limit=10):
        return {
            "pending_count": 2,
            "needs_info_count": 1,
            "approved_7d": 15,
            "rejected_7d": 2,
            "pending_items": [
                {"id": "req-12345678", "plan_name": "Pro Monthly", "status": "pending", "created_at": datetime.now(timezone.utc).isoformat()}
            ],
        }

    async def _fake_incidents(*, hours=24):
        return {
            "hours": hours,
            "services": {"website": {"uptime_pct": 99.8, "checks": 200, "avg_latency_ms": 110}},
            "open_incidents": [{"service": "api", "details": "502 Bad Gateway", "opened_at": datetime.now(timezone.utc).isoformat()}],
            "recent_incidents": [],
        }

    async def _fake_ask(question: str):
        return f"Status looks healthy for: {question}"

    monkeypatch.setattr(insights_service, "get_live_pulse", _fake_pulse)
    monkeypatch.setattr(insights_service, "get_ai_and_extraction_health", _fake_ai_ext)
    monkeypatch.setattr(insights_service, "get_pending_payments", _fake_payments)
    monkeypatch.setattr(insights_service, "get_uptime_and_incidents", _fake_incidents)
    monkeypatch.setattr(ai_assistant, "answer_question", _fake_ask)

    pulse_out = await handlers.handle_pulse(CommandContext(1, 1, "pulse", [], "/pulse"))
    assert "250" in pulse_out
    assert "Biology &lt;101&gt;" in pulse_out
    assert "Pending payments: 3" in pulse_out

    ai_out = await handlers.handle_ai(CommandContext(1, 1, "ai", [], "/ai"))
    assert "Success rate: 94.0%" in ai_out
    assert "openrouter" in ai_out

    pay_out = await handlers.handle_payments(CommandContext(1, 1, "payments", [], "/payments"))
    assert "Pending review: 2" in pay_out
    assert "req-1234" in pay_out
    assert "Pro Monthly" in pay_out

    inc_out = await handlers.handle_incidents(CommandContext(1, 1, "incidents", [], "/incidents"))
    assert "Open Incidents (1)" in inc_out
    assert "99.8%" in inc_out

    ask_out = await handlers.handle_ask(CommandContext(1, 1, "ask", ["how", "is", "ai?"], "/ask how is ai?"))
    assert "Status looks healthy for: how is ai?" in ask_out


async def test_reports_autogenerates_when_missing(monkeypatch):
    from bot.db.repositories import reports_repo
    from bot.modules.analytics import service as analytics_service
    from bot.modules.platform_insights import service as insights_service
    from bot.modules.reports import service as reports_service
    from bot.modules.security import service as security_service

    async def _none_report(report_type):
        return None

    saved = []

    async def _fake_save(*, report_type, content, metadata=None):
        saved.append((report_type, content))
        return {"report_type": report_type, "content": content}

    async def _fake_analytics(period="24h"):
        return {
            "period": period,
            "error_count": 0,
            "pulse": {
                "users": {"total": 100, "premium": 10, "signups_recent": 4, "active_24h": 30},
                "activity": {"total_quizzes": 50, "quizzes_recent": 3, "completions_recent": 20, "guest_attempts_recent": 5, "avg_score_pct": 80.0, "total_classrooms": 4},
                "ai": {"total_calls": 12, "success_rate_pct": 100.0, "avg_latency_ms": 500, "p95_latency_ms": 900},
                "extraction": {"complete_recent": 2, "error_recent": 0, "pending_count": 0, "processing_count": 0, "stuck_jobs": []},
                "payments": {"pending_count": 1},
            },
        }

    async def _fake_uptime(*, hours=24):
        return {"services": {"website": {"uptime_pct": 100.0, "checks": 12, "avg_latency_ms": 95}}, "open_incidents": []}

    async def _no_github():
        raise ConfigurationError("GITHUB_REPO is not configured")

    monkeypatch.setattr(reports_repo, "get_latest_report", _none_report)
    monkeypatch.setattr(reports_service, "get_latest_report", _none_report)
    monkeypatch.setattr(reports_service, "save_report", _fake_save)
    monkeypatch.setattr(analytics_service, "get_analytics_summary", _fake_analytics)
    monkeypatch.setattr(insights_service, "get_uptime_and_incidents", _fake_uptime)
    monkeypatch.setattr(security_service, "get_security_overview", _no_github)

    report = await reports_service.get_report("daily")
    assert report is not None
    assert "Daily Report" in report["content"]
    assert "Pending payments: 1" in report["content"]
    assert len(saved) == 1


async def test_operational_alerts_detects_ai_spike_and_deduplicates(monkeypatch):
    from bot.modules.automation import service as automation_service
    from bot.modules.notifications import service as notifications_service
    from bot.modules.platform_insights import service as insights_service

    automation_service._last_alert_sent.clear()
    alerts = []

    async def _fake_health(*, hours=1):
        return {
            "ai": {"total_calls": 10, "error_count": 5},
            "extraction": {"stuck_jobs": [{"id": "job-1"}]},
        }

    async def _fake_notify(title_text, details):
        alerts.append((title_text, details))

    monkeypatch.setattr(insights_service, "get_ai_and_extraction_health", _fake_health)
    monkeypatch.setattr(notifications_service, "notify_operational_alert", _fake_notify)

    await automation_service.run_operational_alerts()
    await automation_service.run_operational_alerts()  # second run within cooldown must not duplicate

    assert len(alerts) == 2
    assert alerts[0][0] == "AI Error Rate Spike (1h)"
    assert alerts[1][0] == "Stuck Extraction Jobs Detected"


async def test_rbac_for_new_commands(monkeypatch):
    monkeypatch.setenv("OWNER_USER_IDS", "111")
    monkeypatch.setenv("ADMIN_USER_IDS", "222")
    monkeypatch.setenv("VIEWER_USER_IDS", "333")

    import importlib
    import bot.config as config_module
    import bot.core.permissions as permissions_module
    import bot.db.repositories.users_repo as users_repo_module

    importlib.reload(config_module)
    importlib.reload(permissions_module)

    async def _no_db_user(uid):
        return None

    monkeypatch.setattr(users_repo_module, "get_bot_user", _no_db_user)

    assert await permissions_module.require_command_permission(333, "pulse") == permissions_module.Role.VIEWER
    assert await permissions_module.require_command_permission(333, "incidents") == permissions_module.Role.VIEWER
    with pytest.raises(permissions_module.ForbiddenError):
        await permissions_module.require_command_permission(333, "ai")
    with pytest.raises(permissions_module.ForbiddenError):
        await permissions_module.require_command_permission(333, "payments")
    assert await permissions_module.require_command_permission(222, "ai") == permissions_module.Role.ADMIN
    assert await permissions_module.require_command_permission(222, "payments") == permissions_module.Role.ADMIN
    assert await permissions_module.require_command_permission(222, "ask") == permissions_module.Role.ADMIN
