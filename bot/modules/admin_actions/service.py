"""
bot/modules/admin_actions/service.py

Domain service for inspecting and modifying Quiz Space memberships,
payment activation requests, account suspension/badges, reward points,
and reward store orders from Telegram (OWNER-gated for mutations,
with explicit confirmation gates).
"""

from __future__ import annotations

import logging
from typing import Any

from bot.core.exceptions import ConfirmationRequiredError, QuizSpaceBotError
from bot.db.repositories import admin_actions_repo

logger = logging.getLogger("modules.admin_actions")

_VALID_BADGE_TIERS = ("none", "pro", "premium", "team", "enterprise", "lifetime", "founder")

_PLAN_PRESETS: dict[str, dict[str, Any]] = {
    "free": {
        "is_premium": False,
        "plan_name": "Free",
        "plan_id": None,
        "is_lifetime": False,
        "is_founder": False,
        "default_days": None,
    },
    "silver": {
        "is_premium": True,
        "plan_name": "Silver Plan",
        "plan_id": "silver",
        "is_lifetime": False,
        "is_founder": False,
        "default_days": 30,
    },
    "gold": {
        "is_premium": True,
        "plan_name": "Gold Plan",
        "plan_id": "gold",
        "is_lifetime": False,
        "is_founder": False,
        "default_days": 30,
    },
    "diamond": {
        "is_premium": True,
        "plan_name": "Diamond Plan",
        "plan_id": "diamond",
        "is_lifetime": False,
        "is_founder": True,
        "default_days": 365,
    },
    "lifetime": {
        "is_premium": True,
        "plan_name": "Lifetime",
        "plan_id": "diamond",
        "is_lifetime": True,
        "is_founder": False,
        "default_days": None,
    },
    "founder": {
        "is_premium": True,
        "plan_name": "Founder",
        "plan_id": "diamond",
        "is_lifetime": True,
        "is_founder": True,
        "default_days": None,
    },
}


async def get_user_full_profile(identifier: str) -> dict[str, Any] | None:
    return await admin_actions_repo.get_user_full_profile(identifier)


async def list_payment_requests_detailed(*, status_filter: str = "pending", limit: int = 15) -> list[dict[str, Any]]:
    return await admin_actions_repo.list_payment_requests_detailed(status_filter=status_filter, limit=limit)


async def get_points_overview(*, limit: int = 10) -> dict[str, Any]:
    return await admin_actions_repo.get_points_overview(limit=limit)


async def get_user_points_detail(identifier: str) -> dict[str, Any]:
    try:
        return await admin_actions_repo.get_user_points_detail(identifier)
    except ValueError as exc:
        raise QuizSpaceBotError(str(exc)) from exc


async def list_reward_orders(*, limit: int = 15) -> list[dict[str, Any]]:
    return await admin_actions_repo.list_reward_orders(limit=limit)


async def approve_payment(request_id: str, *, confirmed: bool = False) -> dict[str, Any]:
    if not confirmed:
        req = await admin_actions_repo.get_payment_request_by_id(request_id)
        if not req:
            raise QuizSpaceBotError(f"Payment request '{request_id}' not found.")
        raise ConfirmationRequiredError(
            "approve",
            f"Approve payment request #{req['id'][:8]} for {req.get('name') or req.get('user_id')} "
            f"({req.get('plan_name')})?",
            extra_args=[req["id"]],
        )
    try:
        return await admin_actions_repo.approve_payment_request(request_id)
    except ValueError as exc:
        raise QuizSpaceBotError(str(exc)) from exc


async def reject_payment(request_id: str, *, reason: str = "", confirmed: bool = False) -> dict[str, Any]:
    if not confirmed:
        req = await admin_actions_repo.get_payment_request_by_id(request_id)
        if not req:
            raise QuizSpaceBotError(f"Payment request '{request_id}' not found.")
        extra = [req["id"]] + ([reason] if reason else [])
        reason_note = f" Reason: {reason}" if reason else ""
        raise ConfirmationRequiredError(
            "reject",
            f"Reject payment request #{req['id'][:8]} for {req.get('name') or req.get('user_id')}?{reason_note}",
            extra_args=extra,
        )
    try:
        return await admin_actions_repo.reject_payment_request(request_id, reason=reason)
    except ValueError as exc:
        raise QuizSpaceBotError(str(exc)) from exc


async def set_membership(
    identifier: str,
    plan_key: str,
    *,
    days: int | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    normalized = plan_key.strip().lower()
    preset = _PLAN_PRESETS.get(normalized)
    if preset is None:
        raise QuizSpaceBotError(
            f"Unknown plan '{plan_key}'. Choose one of: {', '.join(_PLAN_PRESETS)}."
        )

    effective_days = days if days is not None else preset["default_days"]
    if not confirmed:
        user = await admin_actions_repo.resolve_user(identifier)
        if not user:
            raise QuizSpaceBotError(f"User '{identifier}' not found.")
        duration_txt = f" for {effective_days} days" if (preset["is_premium"] and effective_days) else ""
        extra = [user["uid"], normalized] + ([str(effective_days)] if effective_days else [])
        raise ConfirmationRequiredError(
            "membership",
            f"Set membership for {user.get('name') or user['uid']} ({user.get('email') or 'no email'}) "
            f"to {preset['plan_name']}{duration_txt}?",
            extra_args=extra,
        )

    try:
        return await admin_actions_repo.update_user_membership(
            identifier,
            is_premium=preset["is_premium"],
            plan_name=preset["plan_name"],
            plan_id=preset["plan_id"],
            is_lifetime=preset["is_lifetime"],
            is_founder=preset["is_founder"],
            days=effective_days,
        )
    except ValueError as exc:
        raise QuizSpaceBotError(str(exc)) from exc


async def set_suspension(identifier: str, *, suspended: bool, confirmed: bool = False) -> dict[str, Any]:
    state_word = "on" if suspended else "off"
    if not confirmed:
        user = await admin_actions_repo.resolve_user(identifier)
        if not user:
            raise QuizSpaceBotError(f"User '{identifier}' not found.")
        verb = "SUSPEND" if suspended else "UNSUSPEND"
        raise ConfirmationRequiredError(
            "suspend",
            f"{verb} account {user.get('name') or user['uid']} ({user.get('email') or 'no email'})?",
            extra_args=[user["uid"], state_word],
        )
    try:
        return await admin_actions_repo.set_user_suspension(identifier, suspended=suspended)
    except ValueError as exc:
        raise QuizSpaceBotError(str(exc)) from exc


async def set_badge_tier(identifier: str, badge_tier: str, *, confirmed: bool = False) -> dict[str, Any]:
    tier = badge_tier.strip().lower()
    if tier not in _VALID_BADGE_TIERS:
        raise QuizSpaceBotError(
            f"Invalid badge_tier '{badge_tier}'. Choose one of: {', '.join(_VALID_BADGE_TIERS)}."
        )
    if not confirmed:
        user = await admin_actions_repo.resolve_user(identifier)
        if not user:
            raise QuizSpaceBotError(f"User '{identifier}' not found.")
        raise ConfirmationRequiredError(
            "setbadge",
            f"Set badge_tier for {user.get('name') or user['uid']} to '{tier}'?",
            extra_args=[user["uid"], tier],
        )
    try:
        return await admin_actions_repo.set_user_badge_tier(identifier, badge_tier=tier)
    except ValueError as exc:
        raise QuizSpaceBotError(str(exc)) from exc


async def adjust_points(
    identifier: str,
    delta_points: int,
    *,
    note: str = "",
    admin_telegram_id: int | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    if delta_points == 0 or abs(delta_points) > 1_000_000:
        raise QuizSpaceBotError("Points amount must be non-zero and within ±1,000,000.")
    if not confirmed:
        user = await admin_actions_repo.resolve_user(identifier)
        if not user:
            raise QuizSpaceBotError(f"User '{identifier}' not found.")
        sign = "+" if delta_points > 0 else ""
        extra = [user["uid"], str(delta_points)] + ([note] if note else [])
        raise ConfirmationRequiredError(
            "grantpoints",
            f"Adjust points by {sign}{delta_points} for {user.get('name') or user['uid']}?",
            extra_args=extra,
        )
    try:
        return await admin_actions_repo.adjust_user_points(
            identifier,
            delta_points=delta_points,
            note=note,
            admin_telegram_id=admin_telegram_id,
        )
    except ValueError as exc:
        raise QuizSpaceBotError(str(exc)) from exc


async def review_order(
    order_id: str,
    status: str,
    *,
    note: str = "",
    admin_telegram_id: int | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    command_name = "approveorder" if status == "approved" else "rejectorder"
    if not confirmed:
        extra = [order_id] + ([note] if note else [])
        raise ConfirmationRequiredError(
            command_name,
            f"{status.capitalize()} reward store order #{order_id[:8]}?",
            extra_args=extra,
        )
    try:
        return await admin_actions_repo.review_reward_order(
            order_id,
            status=status,
            note=note,
            admin_telegram_id=admin_telegram_id,
        )
    except ValueError as exc:
        raise QuizSpaceBotError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Platform settings & trial offers
# ---------------------------------------------------------------------------

async def get_platform_settings() -> dict[str, Any]:
    from bot.db.repositories import platform_repo
    return await platform_repo.get_platform_settings()


async def get_trial_offers() -> list[dict[str, Any]]:
    from bot.db.repositories import platform_repo
    return await platform_repo.get_trial_offers()


async def toggle_platform_settings(
    *,
    maintenance_mode: bool,
    allow_registrations: bool,
    confirmed: bool = False,
) -> dict[str, Any]:
    if not confirmed:
        mm = "ON" if maintenance_mode else "OFF"
        reg = "ENABLED" if allow_registrations else "DISABLED"
        raise ConfirmationRequiredError(
            "platform",
            f"Set maintenance_mode={mm} and allow_registrations={reg}?",
            extra_args=["set", str(int(maintenance_mode)), str(int(allow_registrations))],
        )
    return await admin_actions_repo.update_platform_settings(
        maintenance_mode=maintenance_mode,
        allow_registrations=allow_registrations,
    )


async def toggle_trial_offer(
    *,
    duration_days: int,
    is_active: bool,
    confirmed: bool = False,
) -> dict[str, Any]:
    if duration_days not in (7, 14, 30):
        raise QuizSpaceBotError("duration_days must be 7, 14, or 30.")
    if not confirmed:
        verb = "ENABLE" if is_active else "DISABLE"
        raise ConfirmationRequiredError(
            "trial",
            f"{verb} the {duration_days}-day trial offer?",
            extra_args=[str(duration_days), "on" if is_active else "off"],
        )
    try:
        return await admin_actions_repo.set_trial_offer(duration_days=duration_days, is_active=is_active)
    except ValueError as exc:
        raise QuizSpaceBotError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Coupon management
# ---------------------------------------------------------------------------

async def list_coupons(*, limit: int = 20) -> list[dict[str, Any]]:
    return await admin_actions_repo.list_coupons(limit=limit)


async def create_coupon(
    *,
    coupon_id: str,
    code: str,
    discount_percent: int,
    max_uses: int = 0,
    expiry_date: str | None = None,
    applicable_plans: str = "silver,gold,diamond",
    confirmed: bool = False,
) -> dict[str, Any]:
    if not confirmed:
        raise ConfirmationRequiredError(
            "coupon",
            f"Create coupon '{code.upper()}' — {discount_percent}% off {applicable_plans}?",
            extra_args=["create", coupon_id, code, str(discount_percent), str(max_uses),
                        expiry_date or "-", applicable_plans],
        )
    try:
        return await admin_actions_repo.create_coupon(
            coupon_id=coupon_id,
            code=code,
            discount_percent=discount_percent,
            max_uses=max_uses,
            expiry_date=expiry_date,
            applicable_plans=applicable_plans,
        )
    except ValueError as exc:
        raise QuizSpaceBotError(str(exc)) from exc


async def toggle_coupon(coupon_id: str, *, is_active: bool, confirmed: bool = False) -> dict[str, Any]:
    verb = "ACTIVATE" if is_active else "DEACTIVATE"
    if not confirmed:
        raise ConfirmationRequiredError(
            "coupon",
            f"{verb} coupon '{coupon_id}'?",
            extra_args=["toggle", coupon_id, "on" if is_active else "off"],
        )
    return await admin_actions_repo.toggle_coupon_active(coupon_id, is_active=is_active)


async def delete_coupon(coupon_id: str, *, confirmed: bool = False) -> None:
    if not confirmed:
        raise ConfirmationRequiredError(
            "coupon",
            f"PERMANENTLY DELETE coupon '{coupon_id}'? This cannot be undone.",
            extra_args=["delete", coupon_id],
        )
    await admin_actions_repo.delete_coupon(coupon_id)
