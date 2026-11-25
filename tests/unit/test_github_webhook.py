from __future__ import annotations

import hashlib
import hmac
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


def _signature(body: bytes, secret: str = "test-secret") -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


async def test_github_webhook_accepts_github_hmac_signature(monkeypatch, api_client):
    monkeypatch.setattr(
        server, "settings", SimpleNamespace(github_webhook_secret="test-secret")
    )
    body = b'{"zen":"Keep it logically awesome."}'
    response = await api_client.post(
        "/webhooks/github",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "ping",
            "X-Hub-Signature-256": _signature(body),
        },
    )
    assert response.status == 200
    assert await response.text() == "pong"


async def test_github_webhook_rejects_invalid_or_missing_signature(monkeypatch, api_client):
    monkeypatch.setattr(
        server, "settings", SimpleNamespace(github_webhook_secret="test-secret")
    )
    body = b'{"zen":"test"}'
    for headers in (
        {"Content-Type": "application/json", "X-GitHub-Event": "ping"},
        {
            "Content-Type": "application/json",
            "X-GitHub-Event": "ping",
            "X-Hub-Signature-256": "sha256=" + ("0" * 64),
        },
    ):
        response = await api_client.post("/webhooks/github", data=body, headers=headers)
        assert response.status == 401


async def test_github_workflow_failure_notifies_deployment(monkeypatch, api_client):
    monkeypatch.setattr(
        server, "settings", SimpleNamespace(github_webhook_secret="test-secret")
    )
    notifications = []

    async def fake_failed(environment, details):
        notifications.append((environment, details))

    monkeypatch.setattr(
        notifications_service, "notify_deployment_failed", fake_failed
    )
    body = (
        b'{"workflow_run":{"name":"Deploy Worker","conclusion":"failure",'
        b'"html_url":"https://github.com/koomn1/monitoring-bot/actions/runs/42"}}'
    )
    response = await api_client.post(
        "/webhooks/github",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "workflow_run",
            "X-Hub-Signature-256": _signature(body),
        },
    )
    assert response.status == 200
    assert notifications == [
        (
            "Deploy Worker",
            "https://github.com/koomn1/monitoring-bot/actions/runs/42",
        )
    ]


async def test_legacy_internal_webhook_header_remains_supported(monkeypatch, api_client):
    monkeypatch.setattr(
        server, "settings", SimpleNamespace(github_webhook_secret="test-secret")
    )
    response = await api_client.post(
        "/webhooks/github",
        headers={"X-Webhook-Secret": "test-secret"},
        json={"event": "unknown"},
    )
    assert response.status == 200
