"""
Lightweight HTTP server for inbound GitHub, Sentry, and Supabase webhooks,
plus the Bot's own liveness endpoint.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

from aiohttp import web

from bot.config import settings
from bot.modules.notifications import service as notifications_service

logger = logging.getLogger("api.server")
routes = web.RouteTableDef()


_ALLOWED_SUPABASE_TABLES = {"premium_requests", "users", "profiles", "subscription_plans", "reward_store_orders"}
_PLAN_FIELDS = ("plan_name", "plan", "subscription_plan", "package_name", "package", "subscription_type")
_AMOUNT_FIELDS = ("amount", "payment_amount", "payable_amount", "total_amount", "price")
_PAYMENT_FIELDS = ("payment_method", "method", "payment_type")
_STATUS_FIELDS = ("status", "approval_status", "request_status", "state")
_APPROVED_STATUSES = {"approved", "approve", "accepted", "active", "مقبول", "تمت الموافقة", "موافق عليه"}
_REJECTED_STATUSES = {"rejected", "reject", "declined", "denied", "مرفوض", "تم الرفض"}


def _verify_webhook_secret(provided: str | None) -> bool:
    """Compare shared Supabase/GitHub secrets in constant time."""
    if not settings.github_webhook_secret:
        logger.warning("GITHUB_WEBHOOK_SECRET not configured — rejecting all GitHub webhooks")
        return False
    if not provided:
        return False
    return hmac.compare_digest(provided.encode(), settings.github_webhook_secret.encode())


def _verify_supabase_webhook_secret(provided: str | None) -> bool:
    expected = settings.supabase_webhook_secret
    if not expected:
        logger.warning("SUPABASE_WEBHOOK_SECRET not configured — rejecting Supabase webhooks")
        return False
    if not provided:
        return False
    return hmac.compare_digest(provided.encode(), expected.encode())


@routes.post("/webhooks/github")
async def github_webhook(request: web.Request) -> web.Response:
    raw_body = await request.read()
    provided_secret = request.headers.get("X-Webhook-Secret")
    if not _verify_webhook_secret(provided_secret):
        logger.warning("Rejected GitHub webhook: invalid or missing X-Webhook-Secret")
        return web.Response(status=401, text="invalid secret")

    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return web.Response(status=400, text="invalid JSON")
    if not isinstance(payload, dict):
        return web.Response(status=400, text="invalid payload")

    event = payload.get("event")
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


def _first_scalar(record: dict[str, Any], field_names: tuple[str, ...]) -> Any:
    for name in field_names:
        value = record.get(name)
        if isinstance(value, (str, int, float)) and not isinstance(value, bool) and str(value).strip():
            return value
    return None


def _row_id(record: dict[str, Any]) -> Any:
    return _first_scalar(record, ("uid", "id", "user_id", "profile_id", "request_id"))


def _is_trial_request(record: dict[str, Any]) -> bool:
    for key in ("is_trial", "trial", "is_trial_request", "trial_request"):
        if record.get(key) is True:
            return True
    for key in ("request_type", "type", "plan_type", "plan_name", "plan", "package_name", "package"):
        value = record.get(key)
        if isinstance(value, str) and any(token in value.casefold() for token in ("trial", "demo", "تجريبي", "تجربة")):
            return True
    return False


def _status(record: dict[str, Any]) -> str | None:
    value = _first_scalar(record, _STATUS_FIELDS)
    if value is not None:
        return str(value).strip().casefold()
    if record.get("approved") is True:
        return "approved"
    if record.get("approved") is False:
        return "rejected"
    return None


async def _process_supabase_event(payload: dict[str, Any]) -> None:
    schema = payload.get("schema", "public")
    table = payload.get("table")
    action = payload.get("type")
    if not isinstance(schema, str) or schema != "public":
        logger.info("Ignored Supabase webhook for unsupported schema")
        return
    if not isinstance(table, str) or table not in _ALLOWED_SUPABASE_TABLES:
        logger.info("Ignored Supabase webhook for unsupported table")
        return
    if not isinstance(action, str):
        logger.info("Ignored Supabase webhook without a valid event type")
        return
    action = action.upper()
    if action not in {"INSERT", "UPDATE", "DELETE"}:
        logger.info("Ignored unsupported Supabase event type")
        return

    record = payload.get("record")
    old_record = payload.get("old_record")
    record = record if isinstance(record, dict) else {}
    old_record = old_record if isinstance(old_record, dict) else {}
    identifier = _row_id(record) if record else _row_id(old_record)

    if table in {"users", "profiles"} and action == "INSERT":
        await notifications_service.notify_new_user(identifier)
        return

    if table == "subscription_plans":
        await notifications_service.notify_admin_table_change(table, action, identifier)
        return

    if table == "reward_store_orders":
        if action == "INSERT":
            order_type = record.get("order_type") or "points"
            amount_pts = record.get("amount_points") or 0
            amount_egp = record.get("amount_egp") or 0
            pay_method = record.get("payment_method") or "غير محدد"
            await notifications_service.notify_operational_alert(
                f"🎁 طلب جديد من متجر المكافآت #{str(identifier or '')[:8]}",
                f"النوع: {order_type} | {amount_pts} نقطة / {amount_egp} ج.م\n"
                f"طريقة الدفع: {pay_method}\n"
                f"المستخدم: {str(record.get('user_id', 'غير معروف'))[:16]}\n"
                f"للمراجعة: /orders أو /approveorder {str(identifier or '')[:8]}",
            )
        return

    if table == "premium_requests":
        if action == "INSERT":
            if _is_trial_request(record):
                await notifications_service.notify_trial_activation_request(identifier)
            else:
                await notifications_service.notify_activation_request(
                    identifier,
                    plan=_first_scalar(record, _PLAN_FIELDS),
                    amount=_first_scalar(record, _AMOUNT_FIELDS),
                    payment_method=_first_scalar(record, _PAYMENT_FIELDS),
                )
            return

        if action == "UPDATE":
            old_status = _status(old_record)
            new_status = _status(record)
            if new_status in _APPROVED_STATUSES and new_status != old_status:
                await notifications_service.notify_activation_decision(identifier, approved=True)
            elif new_status in _REJECTED_STATUSES and new_status != old_status:
                await notifications_service.notify_activation_decision(identifier, approved=False)


@routes.post("/webhooks/supabase")
async def supabase_webhook(request: web.Request) -> web.Response:
    if not _verify_supabase_webhook_secret(request.headers.get("X-Webhook-Secret")):
        logger.warning("Rejected Supabase webhook: invalid or missing X-Webhook-Secret")
        return web.Response(status=401, text="invalid secret")

    try:
        raw_body = await request.read()
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return web.Response(status=400, text="invalid JSON")
    if not isinstance(payload, dict):
        return web.Response(status=400, text="invalid payload")

    try:
        await _process_supabase_event(payload)
    except Exception:
        # Do not log payloads: they may contain personal or payment data.
        logger.exception("Supabase webhook notification dispatch failed")
        return web.Response(status=503, text="notification dispatch failed")
    return web.Response(status=200, text="ok")


def _verify_sentry_signature(raw_body: bytes, signature_header: str | None) -> bool:
    if not settings.sentry_webhook_secret or not signature_header:
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

    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return web.Response(status=400, text="invalid JSON")
    if not isinstance(payload, dict):
        return web.Response(status=400, text="invalid payload")

    action = payload.get("action")
    if action in ("created", "triggered"):
        data = payload.get("data")
        data = data if isinstance(data, dict) else {}
        issue = data.get("issue", data.get("event", {}))
        issue = issue if isinstance(issue, dict) else {}
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
    app = web.Application(client_max_size=1024 * 1024)
    app.add_routes(routes)
    return app


def main() -> None:
    logging.basicConfig(level=settings.log_level)
    web.run_app(build_app(), host="0.0.0.0", port=int(settings.telegram_webhook_port))


if __name__ == "__main__":
    main()
