"""
tests/unit/test_new_platform_features.py

Unit tests for:
  - platform_repo: get_platform_settings, get_trial_offers, list_coupon_codes,
    get_top_users_by_xp, get_top_users_by_points
  - admin_actions_repo: update_platform_settings, set_trial_offer,
    create_coupon, toggle_coupon_active, delete_coupon
  - admin_actions service: toggle_platform_settings, toggle_trial_offer,
    create_coupon, toggle_coupon, delete_coupon (confirmation gates)
  - handlers: /platform, /trial, /coupon, /vitals, /topusers
  - server: reward_store_orders webhook triggers notify_operational_alert
  - logs_repo: get_uptime_percentage fallback (uses monitoring_logs, no RPC)
  - users/service: _safe helper correctly handles dict coroutines
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.core.exceptions import ConfirmationRequiredError, QuizSpaceBotError
from bot.core.router import CommandContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(cmd: str, args: list[str] | None = None, user_id: int = 1) -> CommandContext:
    return CommandContext(user_id=user_id, chat_id=1, command=cmd, args=args or [], raw_text="")


def _supabase_result(data):
    return SimpleNamespace(data=data, count=len(data) if isinstance(data, list) else None)


# ---------------------------------------------------------------------------
# 1. platform_repo.get_platform_settings — returns dict or {} on error
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_platform_settings_returns_row():
    row = {"maintenance_mode": False, "allow_registrations": True, "updated_at": "2026-01-01T00:00:00Z", "updated_by": None}
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.limit.return_value.execute.return_value = _supabase_result([row])

    with patch("bot.db.repositories.platform_repo.target_db", return_value=mock_client):
        from bot.db.repositories import platform_repo
        result = await platform_repo.get_platform_settings()
    assert result["maintenance_mode"] is False
    assert result["allow_registrations"] is True


@pytest.mark.asyncio
async def test_get_platform_settings_empty_table_returns_empty_dict():
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.limit.return_value.execute.return_value = _supabase_result([])

    with patch("bot.db.repositories.platform_repo.target_db", return_value=mock_client):
        from bot.db.repositories import platform_repo
        result = await platform_repo.get_platform_settings()
    assert result == {}


# ---------------------------------------------------------------------------
# 2. platform_repo.get_trial_offers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_trial_offers_returns_sorted_rows():
    rows = [
        {"duration_days": 7, "is_active": False, "updated_at": "2026-01-01T00:00:00Z", "updated_by": None},
        {"duration_days": 14, "is_active": True, "updated_at": "2026-01-01T00:00:00Z", "updated_by": None},
        {"duration_days": 30, "is_active": False, "updated_at": "2026-01-01T00:00:00Z", "updated_by": None},
    ]
    mock_client = MagicMock()
    (mock_client.table.return_value.select.return_value
     .order.return_value.execute.return_value) = _supabase_result(rows)

    with patch("bot.db.repositories.platform_repo.target_db", return_value=mock_client):
        from bot.db.repositories import platform_repo
        result = await platform_repo.get_trial_offers()
    assert len(result) == 3
    assert result[1]["is_active"] is True  # 14d is active


# ---------------------------------------------------------------------------
# 3. platform_repo.list_coupon_codes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_coupon_codes_returns_list():
    rows = [
        {"id": "c1", "code": "SAVE20", "discount_percent": 20, "max_uses": 100, "used_count": 5,
         "is_active": True, "applicable_plans": "silver,gold", "created_at": "2026-01-01T00:00:00Z",
         "expiry_date": None},
    ]
    mock_client = MagicMock()
    q = mock_client.table.return_value.select.return_value.order.return_value.limit.return_value
    q.execute.return_value = _supabase_result(rows)

    with patch("bot.db.repositories.platform_repo.target_db", return_value=mock_client):
        from bot.db.repositories import platform_repo
        result = await platform_repo.list_coupon_codes()
    assert len(result) == 1
    assert result[0]["code"] == "SAVE20"


# ---------------------------------------------------------------------------
# 4. admin_actions_repo.update_platform_settings — writes to table
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_platform_settings_calls_update():
    mock_client = MagicMock()
    mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = _supabase_result([])

    with patch("bot.db.repositories.admin_actions_repo.target_db", return_value=mock_client):
        from bot.db.repositories import admin_actions_repo
        result = await admin_actions_repo.update_platform_settings(
            maintenance_mode=True, allow_registrations=False
        )
    assert result["maintenance_mode"] is True
    assert result["allow_registrations"] is False
    mock_client.table.assert_called_with("platform_settings")


# ---------------------------------------------------------------------------
# 5. admin_actions_repo.set_trial_offer — invalid duration raises ValueError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_trial_offer_invalid_duration():
    with patch("bot.db.repositories.admin_actions_repo.target_db", return_value=MagicMock()):
        from bot.db.repositories import admin_actions_repo
        with pytest.raises(ValueError, match="7, 14, or 30"):
            await admin_actions_repo.set_trial_offer(duration_days=99, is_active=True)


# ---------------------------------------------------------------------------
# 6. admin_actions_repo.create_coupon — upserts into coupon_codes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_coupon_upserts():
    inserted_row = {
        "id": "coupon1", "code": "SAVE20", "discount_percent": 20,
        "max_uses": 50, "used_count": 0, "is_active": True,
        "applicable_plans": "silver,gold,diamond", "created_at": "2026-01-01T00:00:00Z",
    }
    mock_client = MagicMock()
    (mock_client.table.return_value.upsert.return_value
     .execute.return_value) = _supabase_result([inserted_row])

    with patch("bot.db.repositories.admin_actions_repo.target_db", return_value=mock_client):
        from bot.db.repositories import admin_actions_repo
        result = await admin_actions_repo.create_coupon(
            coupon_id="coupon1", code="save20", discount_percent=20, max_uses=50
        )
    assert result["code"] == "SAVE20"


# ---------------------------------------------------------------------------
# 7. admin_actions service: toggle_platform_settings — confirmation gate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_toggle_platform_settings_requires_confirmation():
    from bot.modules.admin_actions import service as admin_actions
    with pytest.raises(ConfirmationRequiredError) as exc_info:
        await admin_actions.toggle_platform_settings(
            maintenance_mode=True, allow_registrations=False, confirmed=False
        )
    assert exc_info.value.command == "platform"


@pytest.mark.asyncio
async def test_toggle_platform_settings_executes_when_confirmed():
    expected = {"maintenance_mode": True, "allow_registrations": False, "updated_at": "now"}
    with patch(
        "bot.modules.admin_actions.service.admin_actions_repo.update_platform_settings",
        new_callable=AsyncMock,
        return_value=expected,
    ):
        from bot.modules.admin_actions import service as admin_actions
        result = await admin_actions.toggle_platform_settings(
            maintenance_mode=True, allow_registrations=False, confirmed=True
        )
    assert result["maintenance_mode"] is True


# ---------------------------------------------------------------------------
# 8. admin_actions service: toggle_trial_offer — confirmation gate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_toggle_trial_offer_requires_confirmation():
    from bot.modules.admin_actions import service as admin_actions
    with pytest.raises(ConfirmationRequiredError) as exc_info:
        await admin_actions.toggle_trial_offer(duration_days=7, is_active=True, confirmed=False)
    assert exc_info.value.command == "trial"


@pytest.mark.asyncio
async def test_toggle_trial_offer_invalid_days_raises():
    from bot.modules.admin_actions import service as admin_actions
    with pytest.raises(QuizSpaceBotError, match="7, 14, or 30"):
        await admin_actions.toggle_trial_offer(duration_days=99, is_active=True, confirmed=True)


# ---------------------------------------------------------------------------
# 9. admin_actions service: create_coupon — confirmation gate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_coupon_requires_confirmation():
    from bot.modules.admin_actions import service as admin_actions
    with pytest.raises(ConfirmationRequiredError) as exc_info:
        await admin_actions.create_coupon(
            coupon_id="x", code="SAVE", discount_percent=10, confirmed=False
        )
    assert exc_info.value.command == "coupon"


# ---------------------------------------------------------------------------
# 10. admin_actions service: delete_coupon — confirmation gate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_coupon_requires_confirmation():
    from bot.modules.admin_actions import service as admin_actions
    with pytest.raises(ConfirmationRequiredError):
        await admin_actions.delete_coupon("coupon1", confirmed=False)


@pytest.mark.asyncio
async def test_delete_coupon_executes_when_confirmed():
    with patch(
        "bot.modules.admin_actions.service.admin_actions_repo.delete_coupon",
        new_callable=AsyncMock,
        return_value=None,
    ):
        from bot.modules.admin_actions import service as admin_actions
        await admin_actions.delete_coupon("coupon1", confirmed=True)  # Should not raise


# ---------------------------------------------------------------------------
# 11. Handler /platform — shows current state when no args
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cmd_platform_no_args_shows_state():
    from bot.modules.admin_actions import service as admin_actions

    with patch.object(
        admin_actions, "get_platform_settings", new=AsyncMock(
            return_value={"maintenance_mode": False, "allow_registrations": True, "updated_at": "2026-01-01T00:00:00Z"}
        )
    ):
        from bot.modules.telegram_commands.handlers import handle_platform
        out = await handle_platform(_ctx("platform"))
    assert "وضع الصيانة" in out
    assert "فتح التسجيل" in out
    assert "🟢 متوقف" in out


# ---------------------------------------------------------------------------
# 12. Handler /trial — shows trial offers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cmd_trial_no_args_lists_offers():
    from bot.modules.admin_actions import service as admin_actions

    offers = [
        {"duration_days": 7, "is_active": True, "updated_at": "2026-01-01T00:00:00Z"},
        {"duration_days": 14, "is_active": False, "updated_at": "2026-01-01T00:00:00Z"},
        {"duration_days": 30, "is_active": False, "updated_at": "2026-01-01T00:00:00Z"},
    ]
    with patch.object(admin_actions, "get_trial_offers", new=AsyncMock(return_value=offers)):
        from bot.modules.telegram_commands.handlers import handle_trial
        out = await handle_trial(_ctx("trial"))
    assert "7 يوم" in out
    assert "✅ نشط" in out


# ---------------------------------------------------------------------------
# 13. Handler /coupon — lists coupons
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cmd_coupon_no_args_lists():
    from bot.modules.admin_actions import service as admin_actions

    coupons = [
        {
            "id": "c1", "code": "SAVE20", "discount_percent": 20,
            "max_uses": 100, "used_count": 5, "is_active": True,
            "applicable_plans": "silver,gold", "created_at": "2026-01-01T00:00:00Z",
            "expiry_date": None,
        }
    ]
    with patch.object(admin_actions, "list_coupons", new=AsyncMock(return_value=coupons)):
        from bot.modules.telegram_commands.handlers import handle_coupon
        out = await handle_coupon(_ctx("coupon"))
    assert "SAVE20" in out
    assert "20%" in out


# ---------------------------------------------------------------------------
# 14. Handler /vitals — renders web vitals with ratings
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cmd_vitals_renders_metrics():
    vitals = {
        "LCP": {"samples": 200, "avg": 1800, "p75": 2200},
        "CLS": {"samples": 200, "avg": 0.05, "p75": 0.08},
        "FCP": {"samples": 200, "avg": 1200, "p75": 1500},
    }
    import bot.db.repositories.platform_repo as _plat_repo
    with patch.object(_plat_repo, "get_web_vitals_summary", new=AsyncMock(return_value=vitals)):
        from bot.modules.telegram_commands.handlers import handle_vitals
        out = await handle_vitals(_ctx("vitals"))
    assert "LCP" in out
    assert "CLS" in out


# ---------------------------------------------------------------------------
# 15. Handler /topusers — XP leaderboard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cmd_topusers_xp():
    rows = [
        {"uid": "uid1", "name": "Alice", "xp": 5000, "level": 10,
         "is_premium": True, "plan_name": "Gold", "badge_tier": "pro", "custom_id": None},
        {"uid": "uid2", "name": "Bob", "xp": 3000, "level": 7,
         "is_premium": False, "plan_name": "Free", "badge_tier": "none", "custom_id": None},
    ]
    import bot.db.repositories.platform_repo as _plat_repo
    with patch.object(_plat_repo, "get_top_users_by_xp", new=AsyncMock(return_value=rows)):
        from bot.modules.telegram_commands.handlers import handle_topusers
        out = await handle_topusers(_ctx("topusers", ["xp"]))
    assert "Alice" in out
    assert "5,000" in out


# ---------------------------------------------------------------------------
# 16. Handler /topusers — points leaderboard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cmd_topusers_points():
    rows = [
        {"user_id": "uid1", "display_name": "Alice", "points": 8000, "coins": 100, "level": 5},
    ]
    import bot.db.repositories.platform_repo as _plat_repo
    with patch.object(_plat_repo, "get_top_users_by_points", new=AsyncMock(return_value=rows)):
        from bot.modules.telegram_commands.handlers import handle_topusers
        out = await handle_topusers(_ctx("topusers", ["points"]))
    assert "Alice" in out
    assert "8,000" in out


# ---------------------------------------------------------------------------
# 17. logs_repo.get_uptime_percentage — calculates from monitoring_logs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_uptime_percentage_from_logs():
    rows = [{"status": "up"}] * 90 + [{"status": "down"}] * 10
    mock_client = MagicMock()
    (mock_client.table.return_value.select.return_value
     .eq.return_value.gte.return_value.limit.return_value
     .execute.return_value) = SimpleNamespace(data=rows)

    with patch("bot.db.repositories.logs_repo.db", return_value=mock_client):
        from bot.db.repositories import logs_repo
        pct = await logs_repo.get_uptime_percentage("website", days=7)
    assert pct == 90.0


@pytest.mark.asyncio
async def test_get_uptime_percentage_empty_returns_none():
    mock_client = MagicMock()
    (mock_client.table.return_value.select.return_value
     .eq.return_value.gte.return_value.limit.return_value
     .execute.return_value) = SimpleNamespace(data=[])

    with patch("bot.db.repositories.logs_repo.db", return_value=mock_client):
        from bot.db.repositories import logs_repo
        pct = await logs_repo.get_uptime_percentage("website", days=7)
    assert pct is None


# ---------------------------------------------------------------------------
# 18. users/service: _safe handles dict-returning coroutines
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_users_service_safe_handles_dict_coro():
    """_safe() should return the dict, not None, when the coro returns a dict."""
    from bot.modules.users.service import _safe
    async def dict_coro():
        return {"active_1h": 5, "active_24h": 50}

    result = await _safe(dict_coro(), {})
    assert isinstance(result, dict)
    assert result["active_1h"] == 5


# ---------------------------------------------------------------------------
# 19. server.py webhook: reward_store_orders INSERT triggers alert
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_supabase_webhook_reward_order_insert_triggers_alert():
    import importlib

    notify_mock = AsyncMock()
    with patch("bot.modules.notifications.service.notify_operational_alert", notify_mock):
        from bot.api import server
        importlib.reload(server)

        payload = {
            "schema": "public",
            "table": "reward_store_orders",
            "type": "INSERT",
            "record": {
                "id": "order-uuid-1234",
                "user_id": "uid_test_user_1",
                "order_type": "points",
                "amount_points": 500,
                "amount_egp": 0,
                "status": "pending",
            },
            "old_record": {},
        }
        await server._process_supabase_event(payload)
    notify_mock.assert_awaited_once()
    title_arg: str = notify_mock.call_args[0][0]
    details_arg: str = notify_mock.call_args[0][1]
    assert "متجر المكافآت" in title_arg
    assert "/orders" in details_arg


# ---------------------------------------------------------------------------
# 20. admin_actions_repo.list_coupons — returns empty list on error
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_coupons_empty_on_error():
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.order.return_value.limit.return_value.execute.side_effect = RuntimeError("DB error")

    with patch("bot.db.repositories.admin_actions_repo.target_db", return_value=mock_client):
        from bot.db.repositories import admin_actions_repo
        result = await admin_actions_repo.list_coupons()
    assert result == []


# ---------------------------------------------------------------------------
# 21. Site management commands: /plans, /quizzes, edit_user_field, edit_plan, notify, delete_quiz
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cmd_plans_and_quizzes():
    import bot.db.repositories.platform_repo as _plat_repo

    plans = [
        {"id": "gold", "name": "Gold Plan", "name_ar": "الباقة الذهبية", "price": 99,
         "currency": "EGP", "duration_months": 1, "badge_style": "premium", "is_lifetime": False, "is_active": True}
    ]
    quizzes = [
        {"id": "quiz-1234", "title": "Arabic Grammar", "is_public": True, "total_plays": 42, "created_at": "2026-01-01T00:00:00Z"}
    ]
    with patch.object(_plat_repo, "list_subscription_plans", new=AsyncMock(return_value=plans)), \
         patch.object(_plat_repo, "list_recent_quizzes", new=AsyncMock(return_value=quizzes)):
        from bot.modules.telegram_commands.handlers import handle_plans, handle_quizzes
        plans_out = await handle_plans(_ctx("plans"))
        quizzes_out = await handle_quizzes(_ctx("quizzes"))
    assert "الباقة الذهبية" in plans_out
    assert "99 EGP" in plans_out
    assert "Arabic Grammar" in quizzes_out
    assert "42 تشغيل" in quizzes_out


@pytest.mark.asyncio
async def test_edit_user_plan_notify_delete_quiz_require_confirmation():
    from bot.modules.admin_actions import service as admin_actions

    with patch("bot.modules.admin_actions.service.admin_actions_repo.resolve_user", new=AsyncMock(return_value={"uid": "u1", "name": "Ali"})):
        with pytest.raises(ConfirmationRequiredError) as e1:
            await admin_actions.edit_user_field("u1", "name", "Ali Pro", confirmed=False)
        assert e1.value.command == "edituser"

    with pytest.raises(ConfirmationRequiredError) as e2:
        await admin_actions.edit_subscription_plan("gold", "price", "120", confirmed=False)
    assert e2.value.command == "editplan"

    with pytest.raises(ConfirmationRequiredError) as e3:
        await admin_actions.send_platform_notification("all", "إعلان", "تحديث جديد", confirmed=False)
    assert e3.value.command == "notify"

    with pytest.raises(ConfirmationRequiredError) as e4:
        await admin_actions.delete_quiz("quiz-123", confirmed=False)
    assert e4.value.command == "deletequiz"


# ---------------------------------------------------------------------------
# 22. Back button & cmd_button token handling & users table
# ---------------------------------------------------------------------------

def test_every_non_menu_screen_has_back_to_menu_button():
    from bot.utils import keyboards

    keyboards.clear_reply_buttons()
    kb = keyboards.buttons_for("status", [])
    flat = [btn for row in (kb or []) for btn in row]
    assert any(btn["callback_data"] == "cmd|start" and "القائمة الرئيسية" in btn["text"] for btn in flat)

    kb_mut = keyboards.buttons_for("user", ["u1"])
    flat_mut = [btn for row in (kb_mut or []) for btn in row]
    assert any(btn["callback_data"] == "cmd|start" for btn in flat_mut)


def test_cmd_button_uses_token_when_over_64_bytes():
    from bot.utils.keyboards import cmd_button, resolve_command_token

    long_uid = "user_" + "x" * 70
    btn = cmd_button("إيقاف", "suspend", [long_uid, "on"])
    assert len(btn["callback_data"].encode("utf-8")) <= 64
    assert btn["callback_data"].startswith("cmd_tok|")
    token = btn["callback_data"].split("|", 1)[1]
    assert resolve_command_token(token) == ("suspend", [long_uid, "on"])


@pytest.mark.asyncio
async def test_cmd_users_renders_table_with_points_and_status():
    import bot.db.repositories.platform_repo as _plat_repo
    from bot.modules.users import service as users_service

    summary = {"total_users": 2, "premium_users": 1, "recent_signups": [], "signups_24h": 1, "signups_7d": 2, "suspended_users": 1}
    table_rows = [
        {"uid": "uid_11112222", "name": "أحمد", "custom_id": None, "is_premium": True, "plan_name": "Gold", "is_suspended": False, "reward_points": 450},
        {"uid": "uid_33334444", "name": "سارة", "custom_id": None, "is_premium": False, "plan_name": None, "is_suspended": True, "reward_points": 20},
    ]
    with patch.object(users_service, "get_user_summary", new=AsyncMock(return_value=summary)), \
         patch.object(_plat_repo, "list_users_table", new=AsyncMock(return_value=table_rows)):
        from bot.modules.telegram_commands.handlers import handle_users
        out = await handle_users(_ctx("users"))
    assert "<pre>" in out
    assert "أحمد" in out
    assert "موقوف" in out
    assert "450" in out
