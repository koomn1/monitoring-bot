from __future__ import annotations

from types import SimpleNamespace

import pytest
from aiohttp.test_utils import TestClient, TestServer

from bot.api import server
from bot.modules.notifications import service as notifications_service

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def api_client():
    async with TestClient(TestServer(server.build_app())) as client:
        yield client


def _patch_supabase_secret(monkeypatch, secret: str = "test-secret") -> None:
    monkeypatch.setattr(server, "settings", SimpleNamespace(supabase_webhook_secret=secret))


async def test_supabase_webhook_rejects_missing_or_invalid_secret(monkeypatch, api_client):
    _patch_supabase_secret(monkeypatch)
    response = await api_client.post(
        "/webhooks/supabase",
        json={"type": "INSERT", "schema": "public", "table": "users", "record": {"uid": "123"}},
    )
    assert response.status == 401

    response = await api_client.post(
        "/webhooks/supabase",
        headers={"X-Webhook-Secret": "wrong"},
        json={"type": "INSERT", "schema": "public", "table": "users", "record": {"uid": "123"}},
    )
    assert response.status == 401


async def test_activation_insert_sends_only_allowlisted_fields(monkeypatch, api_client):
    _patch_supabase_secret(monkeypatch)
    captured = {}

    async def fake_notify(request_id, **kwargs):
        captured["request_id"] = request_id
        captured.update(kwargs)

    monkeypatch.setattr(notifications_service, "notify_activation_request", fake_notify)
    response = await api_client.post(
        "/webhooks/supabase",
        headers={"X-Webhook-Secret": "test-secret"},
        json={
            "type": "INSERT",
            "schema": "public",
            "table": "premium_requests",
            "record": {
                "id": "12345678-1234-1234-1234-123456789012",
                "plan_name": "Monthly",
                "amount": 120,
                "payment_method": "bank_transfer",
                "email": "private@example.com",
                "phone": "+15555550100",
                "receipt_url": "https://private.invalid/receipt.png",
            },
            "old_record": None,
        },
    )

    assert response.status == 200
    assert captured == {
        "request_id": "12345678-1234-1234-1234-123456789012",
        "plan": "Monthly",
        "amount": 120,
        "payment_method": "bank_transfer",
    }
    assert "email" not in captured and "phone" not in captured and "receipt_url" not in captured


async def test_trial_user_and_plan_events(monkeypatch, api_client):
    _patch_supabase_secret(monkeypatch)
    events = []

    async def fake_trial(request_id):
        events.append(("trial", request_id))

    async def fake_new_user(identifier):
        events.append(("user", identifier))

    async def fake_table(table, action, row_id):
        events.append(("table", table, action, row_id))

    monkeypatch.setattr(notifications_service, "notify_trial_activation_request", fake_trial)
    monkeypatch.setattr(notifications_service, "notify_new_user", fake_new_user)
    monkeypatch.setattr(notifications_service, "notify_admin_table_change", fake_table)

    for table, action, record, old_record in [
        ("premium_requests", "INSERT", {"id": "trial-123456", "is_trial": True}, None),
        ("users", "INSERT", {"uid": "user-123456", "id": "internal-uuid", "email": "hidden@example.com"}, None),
        ("subscription_plans", "DELETE", {}, {"id": "plan-123456", "name": "Gold"}),
    ]:
        response = await api_client.post(
            "/webhooks/supabase",
            headers={"X-Webhook-Secret": "test-secret"},
            json={
                "type": action,
                "schema": "public",
                "table": table,
                "record": record,
                "old_record": old_record,
            },
        )
        assert response.status == 200

    assert events == [
        ("trial", "trial-123456"),
        ("user", "user-123456"),
        ("table", "subscription_plans", "DELETE", "plan-123456"),
    ]


async def test_activation_status_transition_notifies_once(monkeypatch, api_client):
    _patch_supabase_secret(monkeypatch)
    decisions = []

    async def fake_decision(request_id, *, approved):
        decisions.append((request_id, approved))

    monkeypatch.setattr(notifications_service, "notify_activation_decision", fake_decision)
    base = {
        "schema": "public",
        "table": "premium_requests",
        "record": {"id": "request-123456", "status": "approved", "email": "hidden@example.com"},
        "old_record": {"id": "request-123456", "status": "pending"},
    }
    response = await api_client.post(
        "/webhooks/supabase",
        headers={"X-Webhook-Secret": "test-secret"},
        json={"type": "UPDATE", **base},
    )
    assert response.status == 200
    assert decisions == [("request-123456", True)]

    response = await api_client.post(
        "/webhooks/supabase",
        headers={"X-Webhook-Secret": "test-secret"},
        json={"type": "UPDATE", **{**base, "old_record": base["record"]}},
    )
    assert response.status == 200
    assert decisions == [("request-123456", True)]


async def test_notification_text_truncates_ids_and_omits_private_fields(monkeypatch):
    sent = []
    monkeypatch.setattr(
        notifications_service,
        "settings",
        SimpleNamespace(telegram_admin_chat_id="123456", telegram_alert_channel_id="-10099"),
    )

    async def fake_send_message(chat_id, text, **kwargs):
        sent.append((chat_id, text))
        return {}

    monkeypatch.setattr(notifications_service.telegram_client, "send_message", fake_send_message)
    await notifications_service.notify_activation_request(
        "12345678-abcdef",
        plan="<Gold>",
        amount=75,
        payment_method="card",
    )

    assert len(sent) == 1
    chat_id, text = sent[0]
    assert chat_id == "123456"
    assert "12345678" in text and "12345678-abcdef" not in text
    assert "&lt;Gold&gt;" in text and "<Gold>" not in text
    assert "@" not in text and "receipt" not in text.lower()
