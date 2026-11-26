"""
tests/unit/test_admin_actions_and_errors.py

Unit tests for:
  - admin_actions_repo & admin_actions service (payment approval/rejection,
    membership updates, suspension, badge tier, points adjustment, reward
    store order review)
  - Full /errors, /user, /payments, /points, /orders handlers
  - Short-token confirmation buttons (>64-byte callback_data safety)
  - Long Telegram message splitting
  - OWNER-only RBAC for mutation commands
"""

from __future__ import annotations

import importlib
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from bot.core.exceptions import (
    ConfigurationError,
    ConfirmationRequiredError,
    ForbiddenError,
    QuizSpaceBotError,
)
from bot.core.router import CommandContext


class _TableStub:
    def __init__(self, rows_by_op: list[dict], *, store: list[dict] | None = None):
        self._rows = rows_by_op
        self._store = store if store is not None else rows_by_op
        self._op = "select"
        self._payload = None
        self._filters: list[tuple[str, str, object]] = []

    def select(self, *args, **kwargs):
        self._op = "select"
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def upsert(self, payload, **kwargs):
        self._op = "upsert"
        self._payload = payload
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def ilike(self, col, val):
        self._filters.append(("ilike", col, val))
        return self

    def in_(self, col, vals):
        self._filters.append(("in", col, vals))
        return self

    def or_(self, expr):
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, n):
        return self

    def _matches(self, row: dict) -> bool:
        for kind, col, val in self._filters:
            rv = row.get(col)
            if kind == "eq" and rv != val:
                return False
            if kind == "in" and rv not in val:
                return False
            if kind == "ilike":
                prefix = str(val).rstrip("%").lower()
                if not str(rv or "").lower().startswith(prefix):
                    return False
        return True

    def execute(self):
        if self._op == "select":
            matched = [r for r in self._store if self._matches(r)]
            return SimpleNamespace(data=matched, count=len(matched))
        if self._op == "insert":
            self._store.append(dict(self._payload))
            return SimpleNamespace(data=[self._payload])
        if self._op == "update":
            updated = []
            for r in self._store:
                if self._matches(r):
                    r.update(self._payload)
                    updated.append(r)
            return SimpleNamespace(data=updated)
        if self._op == "upsert":
            uid = self._payload.get("user_id")
            for r in self._store:
                if uid is not None and r.get("user_id") == uid:
                    r.update(self._payload)
                    return SimpleNamespace(data=[r])
            self._store.append(dict(self._payload))
            return SimpleNamespace(data=[self._payload])
        return SimpleNamespace(data=[])


class _FakeDb:
    def __init__(self, tables: dict[str, list[dict]]):
        self._tables = tables

    def table(self, name: str):
        store = self._tables.setdefault(name, [])
        return _TableStub(store, store=store)


@pytest.mark.asyncio
async def test_approve_payment_updates_request_and_user_plan(monkeypatch):
    from bot.db.repositories import admin_actions_repo
    from bot.modules.admin_actions import service as admin_actions

    tables = {
        "premium_requests": [
            {
                "id": "12345678-aaaa-bbbb-cccc-123456789012",
                "user_id": "user-uid-1",
                "name": "Ali",
                "email": "ali@example.com",
                "plan_name": "الباقة الذهبية",
                "payment_screenshot": "https://img.example/proof.png",
                "status": "pending",
            }
        ],
        "users": [
            {
                "uid": "user-uid-1",
                "name": "Ali",
                "email": "ali@example.com",
                "is_premium": False,
                "plan_name": "Free",
                "plan_id": None,
            }
        ],
    }
    monkeypatch.setattr(admin_actions_repo, "target_db", lambda: _FakeDb(tables))

    with pytest.raises(ConfirmationRequiredError) as exc:
        await admin_actions.approve_payment("12345678", confirmed=False)
    assert exc.value.command == "approve"

    res = await admin_actions.approve_payment("12345678", confirmed=True)
    assert res["plan_id"] == "gold"
    assert tables["premium_requests"][0]["status"] == "approved"
    assert tables["users"][0]["is_premium"] is True
    assert tables["users"][0]["plan_id"] == "gold"


@pytest.mark.asyncio
async def test_adjust_points_clamps_to_zero_and_writes_ledger(monkeypatch):
    from bot.db.repositories import admin_actions_repo
    from bot.modules.admin_actions import service as admin_actions

    tables = {
        "users": [{"uid": "u-1", "name": "Sara", "email": "sara@example.com"}],
        "user_reward_balances": [{"user_id": "u-1", "points": 120, "coins": 5, "level": 2}],
        "reward_points_ledger": [],
        "reward_levels": [
            {"level": 1, "min_points": 0},
            {"level": 2, "min_points": 100},
            {"level": 3, "min_points": 250},
            {"level": 4, "min_points": 500},
        ],
    }
    monkeypatch.setattr(admin_actions_repo, "target_db", lambda: _FakeDb(tables))

    added = await admin_actions.adjust_points(
        "sara@example.com", 200, note="Event bonus", admin_telegram_id=111, confirmed=True
    )
    assert added["previous_points"] == 120
    assert added["total_points"] == 320
    assert added["level"] == 3
    assert len(tables["reward_points_ledger"]) == 1
    assert tables["reward_points_ledger"][0]["event_type"] == "admin_grant"

    # Deducting more than current balance clamps at 0
    deducted = await admin_actions.adjust_points(
        "u-1", -1000, note="Correction", admin_telegram_id=111, confirmed=True
    )
    assert deducted["total_points"] == 0
    assert deducted["delta"] == -320
    assert deducted["level"] == 1


@pytest.mark.asyncio
async def test_review_reward_order_credits_points_on_approval(monkeypatch):
    from bot.db.repositories import admin_actions_repo
    from bot.modules.admin_actions import service as admin_actions

    tables = {
        "reward_store_orders": [
            {
                "id": "ord-9999-1111",
                "user_id": "u-2",
                "item_id": "pack_500",
                "status": "pending",
                "payment_method": "vodafone_cash",
                "amount_egp": 50,
            }
        ],
        "reward_store_items": [{"id": "pack_500", "name": "500 Points", "reward_points": 500}],
        "user_reward_balances": [{"user_id": "u-2", "points": 50, "level": 1}],
        "reward_points_ledger": [],
        "reward_levels": [{"level": 1, "min_points": 0}, {"level": 4, "min_points": 500}],
    }
    monkeypatch.setattr(admin_actions_repo, "target_db", lambda: _FakeDb(tables))

    res = await admin_actions.review_order("ord-9999", "approved", admin_telegram_id=111, confirmed=True)
    assert res["status"] == "approved"
    assert res["points_added"] == 500
    assert res["total_points"] == 550
    assert res["level"] == 4
    assert tables["reward_store_orders"][0]["status"] == "approved"


@pytest.mark.asyncio
async def test_set_membership_and_invalid_badge_validation(monkeypatch):
    from bot.db.repositories import admin_actions_repo
    from bot.modules.admin_actions import service as admin_actions

    tables = {
        "users": [{"uid": "u-3", "name": "Omar", "email": "omar@example.com", "is_premium": False}],
    }
    monkeypatch.setattr(admin_actions_repo, "target_db", lambda: _FakeDb(tables))

    res = await admin_actions.set_membership("u-3", "diamond", days=90, confirmed=True)
    assert res["is_premium"] is True
    assert res["is_founder"] is True
    assert tables["users"][0]["plan_id"] == "diamond"

    with pytest.raises(QuizSpaceBotError):
        await admin_actions.set_badge_tier("u-3", "invalid_tier", confirmed=True)


@pytest.mark.asyncio
async def test_detailed_errors_handler_shows_all_sources(monkeypatch):
    from bot.integrations import sentry_client
    from bot.modules.platform_insights import service as insights_service
    from bot.modules.telegram_commands import handlers

    async def _no_sentry(*args, **kwargs):
        raise ConfigurationError("Sentry not configured")

    async def _fake_errors(*, hours=24):
        now_iso = datetime.now(timezone.utc).isoformat()
        return {
            "hours": hours,
            "open_incidents": [{"service": "api", "details": "502 Upstream", "opened_at": now_iso}],
            "ai": {
                "error_count": 2,
                "recent_errors": [
                    {
                        "user_id": "user123456",
                        "provider": "openrouter",
                        "model": "gemma-4",
                        "operation": "extraction",
                        "latency_ms": 3400,
                        "error_category": "timeout",
                        "error_message": "Provider request timed out after 30s",
                        "created_at": now_iso,
                    }
                ],
            },
            "extraction": {
                "stuck_jobs": [{"id": "stuck-1234", "progress_percentage": 55, "provider": "inception", "updated_at": now_iso}],
                "recent_errors": [{"id": "fail-5678", "extraction_mode": "literal", "provider": "openrouter", "error_message": "Corrupt PDF header", "created_at": now_iso}],
            },
            "failed_checks": [{"service": "website", "latency_ms": 10000, "metadata": {"status_code": 503}, "checked_at": now_iso}],
            "failed_commands": [{"command": "deploy", "user_id": 111, "error": "GitHub 500", "created_at": now_iso}],
        }

    monkeypatch.setattr(sentry_client, "get_recent_issues", _no_sentry)
    monkeypatch.setattr(insights_service, "get_detailed_errors_report", _fake_errors)

    out = await handlers.handle_errors(CommandContext(1, 1, "errors", [], "/errors"))
    assert "502 Upstream" in out
    assert "Provider request timed out after 30s" in out
    assert "Corrupt PDF header" in out
    assert "HTTP 503" in out
    assert "GitHub 500" in out
    assert "STUCK" in out


@pytest.mark.asyncio
async def test_orders_handler_renders_arabic_cards_with_user_identity(monkeypatch):
    from bot.modules.admin_actions import service as admin_actions
    from bot.modules.telegram_commands import handlers

    async def _fake_orders(*, limit=15):
        return [
            {
                "id": "6aed9a9b-1234",
                "user_id": "user-very-long-id",
                "user_name": "أحمد",
                "user_custom_id": "ahmed_77",
                "item_id": "offer_double_pack",
                "amount_egp": 150,
                "amount_points": 2500,
                "payment_method": "vodafone_cash",
                "payment_reference": "01018995002",
                "status": "approved",
            }
        ]

    monkeypatch.setattr(admin_actions, "list_reward_orders", _fake_orders)
    out = await handlers.handle_orders(CommandContext(1, 1, "orders", [], "/orders"))

    assert "كل طلب في بطاقة مستقلة" in out
    assert "المنتج" in out and "offer_double_pack" in out
    assert "فودافون كاش" in out and "تمت الموافقة" in out
    assert "أحمد" in out and "المعرّف المخصص" in out and "ahmed_77" in out
    assert "UID: user-very-l" in out
    assert "01018995002" in out


@pytest.mark.asyncio
async def test_users_and_points_lists_expose_next_page_buttons(monkeypatch):
    from bot.db.repositories import platform_repo
    from bot.modules.admin_actions import service as admin_actions
    from bot.modules.telegram_commands import handlers
    from bot.utils import keyboards
    from bot.modules.users import service as users_service

    async def _fake_summary():
        return {"total_users": 13, "premium_users": 2, "recent_signups": []}

    async def _fake_users_table(*, filter_mode="all", limit=12, offset=0):
        return [
            {"uid": f"user-{offset + i}", "name": f"User {offset + i}", "is_premium": False}
            for i in range(limit)
        ]

    monkeypatch.setattr(users_service, "get_user_summary", _fake_summary)
    monkeypatch.setattr(platform_repo, "list_users_table", _fake_users_table)
    await handlers.handle_users(CommandContext(1, 1, "users", [], "/users"))
    user_buttons = keyboards._REPLY_EXTRA_BUTTONS.get()
    assert user_buttons[-1][0]["text"] == "التالي ▶️"
    assert "users|all,2" in user_buttons[-1][0]["callback_data"]

    async def _fake_points(*, limit=10, offset=0):
        return {
            "top_balances": [{"user_id": f"user-{i}", "points": i} for i in range(limit)],
            "recent_ledger": [],
        }

    monkeypatch.setattr(admin_actions, "get_points_overview", _fake_points)
    await handlers.handle_points(CommandContext(1, 1, "points", [], "/points"))
    points_buttons = keyboards._REPLY_EXTRA_BUTTONS.get()
    assert points_buttons[0][0]["text"] == "التالي ▶️"
    assert "points|page,2" in points_buttons[0][0]["callback_data"]


def test_long_confirmation_uses_short_token_within_64_bytes():
    from bot.utils.keyboards import confirmation_buttons, resolve_confirmation_token

    long_uid = "user-very-long-identifier-1234567890-abcdef"
    kb = confirmation_buttons(
        "grantpoints", [long_uid, "500", "reward for bug report"], user_id=111, chat_id=222
    )
    cb_data = kb[0][0]["callback_data"]
    assert len(cb_data.encode("utf-8")) <= 64
    assert cb_data.startswith("confirm_tok|")

    token = cb_data.split("|", 1)[1]
    resolved = resolve_confirmation_token(token, user_id=111, chat_id=222)
    assert resolved == ("grantpoints", [long_uid, "500", "reward for bug report"])
    assert resolve_confirmation_token(token, user_id=111, chat_id=222) is None  # one-time pop


def test_split_telegram_text_respects_limit():
    from bot.main import _split_telegram_text

    text = "\n".join(f"line-{i}-" + ("x" * 90) for i in range(60))
    chunks = _split_telegram_text(text, limit=1000)
    assert len(chunks) > 1
    assert all(len(c) <= 1000 for c in chunks)
    assert "".join(chunks) == text


@pytest.mark.asyncio
async def test_mutation_commands_require_owner(monkeypatch):
    monkeypatch.setenv("OWNER_USER_IDS", "111")
    monkeypatch.setenv("ADMIN_USER_IDS", "222")
    monkeypatch.setenv("VIEWER_USER_IDS", "333")

    import bot.config as config_module
    import bot.core.permissions as permissions_module
    import bot.db.repositories.users_repo as users_repo_module

    importlib.reload(config_module)
    importlib.reload(permissions_module)

    async def _no_db_user(uid):
        return None

    monkeypatch.setattr(users_repo_module, "get_bot_user", _no_db_user)

    assert await permissions_module.require_command_permission(222, "orders") == permissions_module.Role.ADMIN
    assert await permissions_module.require_command_permission(222, "points") == permissions_module.Role.ADMIN

    for owner_cmd in ("approve", "reject", "membership", "suspend", "setbadge", "grantpoints", "approveorder", "rejectorder"):
        with pytest.raises(ForbiddenError):
            await permissions_module.require_command_permission(222, owner_cmd)
        assert await permissions_module.require_command_permission(111, owner_cmd) == permissions_module.Role.OWNER
