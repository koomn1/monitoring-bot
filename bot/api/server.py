"""
bot/api/server.py

Lightweight HTTP server (aiohttp) exposing:
  - POST /webhooks/github  — deployment/backup/rollback/restore callbacks
                              dispatched from .github/workflows/*.yml
  - POST /webhooks/sentry  — new-issue alerts from Sentry (optional)
  - GET  /health           — the Bot's OWN liveness endpoint (not Quiz
                              Space's — see modules/api monitor for that)

Runs as a small side-process alongside the Telegram polling loop (or,
in webhook mode, can share the same port as python-telegram-bot's
webhook server — see docs/06-deployment.md for the two deployment
shapes). Started explicitly from bot/main.py when
TELEGRAM_USE_WEBHOOK=true, or can be run standalone via
`python -m bot.api.server` if inbound webhooks are needed while the
Bot itself runs in polling mode on a separate process/host.

See: api/02-webhooks.md, api/03-health-endpoint.md, docs/07-security.md §11
"""

from __future__ import annotations

import hashlib
import hmac
import logging

from aiohttp import web

from bot.config import settings
from bot.modules.notifications import service as notifications_service

logger = logging.getLogger("api.server")

routes = web.RouteTableDef()


def _verify_webhook_secret(provided: str | None) -> bool:
    """
    Simple shared-secret check: the value in GITHUB_WEBHOOK_SECRET must
    match the X-Webhook-Secret header sent by .github/workflows/*.yml.
    This is intentionally a plain shared secret, not a computed HMAC
    signature — the workflows send the raw value directly (a `curl`
    step cannot easily compute HMAC-SHA256 without extra tooling), so
    keeping both sides plain avoids a mismatch between how the sender
    and receiver format the header. Still constant-time compared to
    avoid timing attacks. See docs/07-security.md §11.
    """
    if not settings.github_webhook_secret:
        logger.warning("GITHUB_WEBHOOK_SECRET not configured — rejecting all GitHub webhooks")
        return False
    if not provided:
        return False
    return hmac.compare_digest(provided.encode(), settings.github_webhook_secret.encode())


@routes.post("/webhooks/github")
async def github_webhook(request: web.Request) -> web.Response:
    raw_body = await request.read()
    provided_secret = request.headers.get("X-Webhook-Secret")

    if not _verify_webhook_secret(provided_secret):
        logger.warning("Rejected GitHub webhook: invalid or missing X-Webhook-Secret")
        return web.Response(status=401, text="invalid secret")

    payload = await request.json()
    event = payload.get("event")

    # Acknowledge immediately; notification dispatch is fire-and-forget
    # so GitHub Actions' `curl` step doesn't wait on Telegram delivery.
    if event == "deployment_success":
        await notifications_service.notify_deployment_success(payload.get("environment", "production"))
    elif event == "deployment_failed":
        await notifications_service.notify_deployment_failed(
            payload.get("environment", "production"), "See GitHub Actions run for details."
        )
    elif event == "rollback_completed":
        await notifications_service.notify_rollback_completed()
    elif event == "backup_completed":
        await notifications_service.notify_backup_completed(f"run {payload.get('run_id')}")
    elif event == "backup_failed":
        await notifications_service.notify_backup_failed(f"run {payload.get('run_id')} — see GitHub Actions logs")
    elif event == "restore_completed":
        await notifications_service.notify_restore_completed(payload.get("backup_id", "unknown"))
    elif event == "external_health_check_failed":
        await notifications_service.notify_security_alert(
            f"External health check failed — website={payload.get('website_code')} "
            f"api={payload.get('api_code')}"
        )
    else:
        logger.info("Unrecognized GitHub webhook event: %s", event)

    return web.Response(status=200, text="ok")


def _verify_sentry_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """
    Sentry's actual webhook signature scheme (distinct from GitHub's):
    Sentry computes HMAC-SHA256 over the raw request body using the
    integration's Client Secret, and sends the hex digest in the
    Sentry-Hook-Signature header — no "sha256=" prefix, unlike GitHub's
    convention. See: https://docs.sentry.io/product/integrations/integration-platform/webhooks/
    """
    if not settings.sentry_webhook_secret:
        logger.warning("SENTRY_WEBHOOK_SECRET not configured — rejecting all Sentry webhooks")
        return False
    if not signature_header:
        return False
    expected = hmac.new(settings.sentry_webhook_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


@routes.post("/webhooks/sentry")
async def sentry_webhook(request: web.Request) -> web.Response:
    raw_body = await request.read()
    signature = request.headers.get("Sentry-Hook-Signature")

    if not _verify_sentry_signature(raw_body, signature):
        logger.warning("Rejected Sentry webhook: invalid or missing Sentry-Hook-Signature")
        return web.Response(status=401, text="invalid signature")

    payload = await request.json()
    action = payload.get("action")

    if action in ("created", "triggered"):
        issue = payload.get("data", {}).get("issue", payload.get("data", {}).get("event", {}))
        title_text = issue.get("title") or issue.get("message") or "New Sentry issue"
        culprit = issue.get("culprit", "")
        await notifications_service.notify_security_alert(
            f"New Sentry issue: {title_text}" + (f" ({culprit})" if culprit else "")
        )
    else:
        logger.info("Unrecognized/ignored Sentry webhook action: %s", action)

    return web.Response(status=200, text="ok")


@routes.get("/health")
async def health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


def build_app() -> web.Application:
    app = web.Application()
    app.add_routes(routes)
    return app


def main() -> None:
    logging.basicConfig(level=settings.log_level)
    web.run_app(build_app(), host="0.0.0.0", port=8081)


if __name__ == "__main__":
    main()
