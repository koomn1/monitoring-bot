"""
bot/db/repositories/admin_actions_repo.py

Supabase data-access layer (via `target_db()`, service-role client) for
Quiz Space's administrative views & mutations:
  - Inspecting & approving/rejecting `premium_requests`
  - Updating user memberships (`users` subscription & suspension & badge_tier)
  - Inspecting & adjusting user reward points (`user_reward_balances`,
    `reward_points_ledger`, `reward_levels`)
  - Reviewing/approving/rejecting `reward_store_orders`
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from bot.integrations.supabase_client import target_db

logger = logging.getLogger("repositories.admin_actions")

_DEFAULT_LEVEL_THRESHOLDS: list[tuple[int, int]] = [
    (6, 2000),
    (5, 1000),
    (4, 500),
    (3, 250),
    (2, 100),
    (1, 0),
]

_TRIAL_DAYS_BY_MARKER = {
    "TRIAL_OFFER_7_DAYS": 7,
    "TRIAL_OFFER_14_DAYS": 14,
    "TRIAL_OFFER_30_DAYS": 30,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _infer_plan_id(plan_name: str, fallback: str | None = None) -> str:
    low = (plan_name or "").lower()
    if "diamond" in low or "ماسي" in low or "ماس" in low:
        return "diamond"
    if "gold" in low or "ذهبي" in low or "ذهب" in low:
        return "gold"
    if "silver" in low or "فضي" in low or "فض" in low:
        return "silver"
    return fallback or "gold"


def _compute_reward_level(points: int) -> int:
    safe_pts = max(0, points)
    try:
        res = (
            target_db()
            .table("reward_levels")
            .select("level,min_points")
            .order("min_points", desc=True)
            .execute()
        )
        rows = sorted(
            res.data or [],
            key=lambda r: int(r.get("min_points", 0)),
            reverse=True,
        )
        for row in rows:
            if safe_pts >= int(row.get("min_points", 0)):
                return int(row.get("level", 1))
    except Exception:  # noqa: BLE001
        pass
    for lvl, min_pts in _DEFAULT_LEVEL_THRESHOLDS:
        if safe_pts >= min_pts:
            return lvl
    return 1


async def resolve_user(identifier: str) -> dict[str, Any] | None:
    query = target_db().table("users").select("*")
    ident = identifier.strip()
    if "@" in ident:
        query = query.eq("email", ident)
    else:
        query = query.or_(f"uid.eq.{ident},custom_id.eq.{ident}")
    res = query.limit(1).execute()
    return res.data[0] if res.data else None


async def get_user_full_profile(identifier: str) -> dict[str, Any] | None:
    user = await resolve_user(identifier)
    if not user:
        return None
    uid = user["uid"]

    reward_balance: dict[str, Any] | None = None
    ledger: list[dict[str, Any]] = []
    requests: list[dict[str, Any]] = []

    try:
        bal_res = (
            target_db()
            .table("user_reward_balances")
            .select("points,coins,level,updated_at")
            .eq("user_id", uid)
            .limit(1)
            .execute()
        )
        reward_balance = bal_res.data[0] if bal_res.data else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed fetching reward balance for %s: %s", uid, exc)

    try:
        led_res = (
            target_db()
            .table("reward_points_ledger")
            .select("points,event_type,metadata,created_at")
            .eq("user_id", uid)
            .order("created_at", desc=True)
            .limit(5)
            .execute()
        )
        ledger = list(led_res.data or [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed fetching points ledger for %s: %s", uid, exc)

    try:
        req_res = (
            target_db()
            .table("premium_requests")
            .select("id,plan_name,status,reject_reason,created_at,updated_at")
            .eq("user_id", uid)
            .order("created_at", desc=True)
            .limit(5)
            .execute()
        )
        requests = list(req_res.data or [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed fetching premium_requests for %s: %s", uid, exc)

    return {
        "user": user,
        "reward_balance": reward_balance,
        "recent_ledger": ledger,
        "recent_requests": requests,
    }


async def list_payment_requests_detailed(*, status_filter: str = "pending", limit: int = 15) -> list[dict[str, Any]]:
    query = (
        target_db()
        .table("premium_requests")
        .select("id,user_id,name,email,plan_name,payment_screenshot,status,reject_reason,created_at,updated_at")
    )
    if status_filter == "pending":
        query = query.in_("status", ["pending", "needs_info"]).order("created_at", desc=False)
    else:
        query = query.order("created_at", desc=True)
    res = query.limit(limit).execute()
    return list(res.data or [])


async def get_payment_request_by_id(request_id: str) -> dict[str, Any] | None:
    ident = request_id.strip()
    res = target_db().table("premium_requests").select("*").eq("id", ident).limit(1).execute()
    if res.data:
        return res.data[0]
    # Allow prefix match when user passes the first 8+ chars
    if len(ident) >= 6:
        prefix_res = (
            target_db()
            .table("premium_requests")
            .select("*")
            .ilike("id", f"{ident}%")
            .limit(2)
            .execute()
        )
        if len(prefix_res.data or []) == 1:
            return prefix_res.data[0]
    return None


async def approve_payment_request(request_id: str) -> dict[str, Any]:
    req = await get_payment_request_by_id(request_id)
    if not req:
        raise ValueError(f"Payment request '{request_id}' not found.")
    if req.get("status") not in ("pending", "needs_info"):
        raise ValueError(f"Request '{req['id']}' is already '{req.get('status')}'.")

    user_id = req["user_id"]
    plan_name = req.get("plan_name") or "Premium"
    screenshot = str(req.get("payment_screenshot") or "").strip()
    trial_days = _TRIAL_DAYS_BY_MARKER.get(screenshot)

    user_res = target_db().table("users").select("uid,is_premium,plan_name,plan_id").eq("uid", user_id).limit(1).execute()
    if not user_res.data:
        raise ValueError(f"Target user '{user_id}' not found.")
    user_row = user_res.data[0]

    now = datetime.now(timezone.utc)
    if trial_days is not None:
        plan_id = f"trial_{trial_days}d"
        is_founder = False
        renewal_date = (now + timedelta(days=trial_days)).isoformat()
    else:
        plan_id = _infer_plan_id(plan_name, user_row.get("plan_id"))
        is_founder = plan_id == "diamond"
        renewal_date = (now + timedelta(days=30)).isoformat()

    target_db().table("premium_requests").update(
        {"status": "approved", "reject_reason": None, "updated_at": now.isoformat()}
    ).eq("id", req["id"]).execute()

    target_db().table("users").update(
        {
            "is_premium": True,
            "plan_name": plan_name,
            "plan_id": plan_id,
            "is_lifetime": False,
            "is_founder": is_founder,
            "renewal_date": renewal_date,
            "updated_at": now.isoformat(),
        }
    ).eq("uid", user_id).execute()

    return {
        "request_id": req["id"],
        "user_id": user_id,
        "user_name": req.get("name"),
        "plan_name": plan_name,
        "plan_id": plan_id,
        "renewal_date": renewal_date,
        "is_trial": trial_days is not None,
    }


async def reject_payment_request(request_id: str, reason: str = "") -> dict[str, Any]:
    req = await get_payment_request_by_id(request_id)
    if not req:
        raise ValueError(f"Payment request '{request_id}' not found.")
    if req.get("status") not in ("pending", "needs_info"):
        raise ValueError(f"Request '{req['id']}' is already '{req.get('status')}'.")

    now_iso = _now_iso()
    target_db().table("premium_requests").update(
        {
            "status": "rejected",
            "reject_reason": reason.strip() or None,
            "updated_at": now_iso,
        }
    ).eq("id", req["id"]).execute()

    return {
        "request_id": req["id"],
        "user_id": req["user_id"],
        "user_name": req.get("name"),
        "plan_name": req.get("plan_name"),
        "reject_reason": reason.strip() or "No reason specified",
    }


async def update_user_membership(
    identifier: str,
    *,
    is_premium: bool,
    plan_name: str,
    plan_id: str | None,
    is_lifetime: bool = False,
    is_founder: bool = False,
    days: int | None = None,
) -> dict[str, Any]:
    user = await resolve_user(identifier)
    if not user:
        raise ValueError(f"User '{identifier}' not found.")

    now = datetime.now(timezone.utc)
    renewal_date: str | None = None
    if is_premium and not is_lifetime and days is not None and days > 0:
        renewal_date = (now + timedelta(days=days)).isoformat()

    payload = {
        "is_premium": is_premium,
        "plan_name": plan_name,
        "plan_id": plan_id,
        "is_lifetime": is_lifetime,
        "is_founder": is_founder,
        "renewal_date": renewal_date,
        "updated_at": now.isoformat(),
    }
    target_db().table("users").update(payload).eq("uid", user["uid"]).execute()
    return {"uid": user["uid"], "name": user.get("name"), "email": user.get("email"), **payload}


async def set_user_suspension(identifier: str, *, suspended: bool) -> dict[str, Any]:
    user = await resolve_user(identifier)
    if not user:
        raise ValueError(f"User '{identifier}' not found.")
    target_db().table("users").update(
        {"is_suspended": suspended, "updated_at": _now_iso()}
    ).eq("uid", user["uid"]).execute()
    return {"uid": user["uid"], "name": user.get("name"), "is_suspended": suspended}


async def set_user_badge_tier(identifier: str, *, badge_tier: str) -> dict[str, Any]:
    user = await resolve_user(identifier)
    if not user:
        raise ValueError(f"User '{identifier}' not found.")
    target_db().table("users").update(
        {"badge_tier": badge_tier, "updated_at": _now_iso()}
    ).eq("uid", user["uid"]).execute()
    return {"uid": user["uid"], "name": user.get("name"), "badge_tier": badge_tier}


async def get_points_overview(*, limit: int = 10) -> dict[str, Any]:
    balances: list[dict[str, Any]] = []
    recent_ledger: list[dict[str, Any]] = []
    try:
        bal_res = (
            target_db()
            .table("user_reward_balances")
            .select("user_id,points,coins,level,updated_at")
            .order("points", desc=True)
            .limit(limit)
            .execute()
        )
        balances = list(bal_res.data or [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed fetching user_reward_balances: %s", exc)

    user_names: dict[str, str] = {}
    if balances:
        uids = [b["user_id"] for b in balances if b.get("user_id")]
        try:
            u_res = target_db().table("users").select("uid,name,email").in_("uid", uids).execute()
            for row in u_res.data or []:
                user_names[row["uid"]] = row.get("name") or row.get("email") or row["uid"][:8]
        except Exception:  # noqa: BLE001
            pass
    for bal in balances:
        bal["display_name"] = user_names.get(bal.get("user_id", ""), str(bal.get("user_id", ""))[:8])

    try:
        led_res = (
            target_db()
            .table("reward_points_ledger")
            .select("user_id,points,event_type,metadata,created_at")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        recent_ledger = list(led_res.data or [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed fetching reward_points_ledger: %s", exc)

    return {"top_balances": balances, "recent_ledger": recent_ledger}


async def get_user_points_detail(identifier: str) -> dict[str, Any]:
    user = await resolve_user(identifier)
    if not user:
        raise ValueError(f"User '{identifier}' not found.")
    uid = user["uid"]

    bal_res = (
        target_db()
        .table("user_reward_balances")
        .select("points,coins,level,updated_at")
        .eq("user_id", uid)
        .limit(1)
        .execute()
    )
    balance = bal_res.data[0] if bal_res.data else {"points": 0, "coins": 0, "level": 1}

    led_res = (
        target_db()
        .table("reward_points_ledger")
        .select("points,event_type,metadata,created_at")
        .eq("user_id", uid)
        .order("created_at", desc=True)
        .limit(10)
        .execute()
    )
    return {
        "uid": uid,
        "name": user.get("name"),
        "email": user.get("email"),
        "xp": user.get("xp", 0),
        "user_level": user.get("level", 1),
        "balance": balance,
        "ledger": list(led_res.data or []),
    }


async def adjust_user_points(
    identifier: str,
    *,
    delta_points: int,
    note: str = "",
    admin_telegram_id: int | None = None,
) -> dict[str, Any]:
    if delta_points == 0 or abs(delta_points) > 1_000_000:
        raise ValueError("Points adjustment must be non-zero and within ±1,000,000.")
    user = await resolve_user(identifier)
    if not user:
        raise ValueError(f"User '{identifier}' not found.")
    uid = user["uid"]

    bal_res = (
        target_db()
        .table("user_reward_balances")
        .select("points,coins,level")
        .eq("user_id", uid)
        .limit(1)
        .execute()
    )
    current_points = int((bal_res.data[0] if bal_res.data else {}).get("points") or 0)
    new_points = max(0, current_points + delta_points)
    applied_delta = new_points - current_points
    new_level = _compute_reward_level(new_points)
    now_iso = _now_iso()

    target_db().table("reward_points_ledger").insert(
        {
            "user_id": uid,
            "points": applied_delta,
            "event_type": "admin_grant" if applied_delta >= 0 else "admin_deduct",
            "event_key": f"telegram_admin:{uuid.uuid4()}",
            "reference_id": uid,
            "metadata": {
                "note": note.strip()[:500],
                "source": "telegram_bot",
                "admin_telegram_id": admin_telegram_id,
            },
            "created_at": now_iso,
        }
    ).execute()

    target_db().table("user_reward_balances").upsert(
        {
            "user_id": uid,
            "points": new_points,
            "level": new_level,
            "updated_at": now_iso,
        },
        on_conflict="user_id",
    ).execute()

    return {
        "uid": uid,
        "name": user.get("name"),
        "previous_points": current_points,
        "delta": applied_delta,
        "total_points": new_points,
        "level": new_level,
    }


async def list_reward_orders(*, limit: int = 15) -> list[dict[str, Any]]:
    res = (
        target_db()
        .table("reward_store_orders")
        .select(
            "id,user_id,item_id,order_type,amount_points,amount_egp,"
            "payment_method,payment_reference,status,notes,created_at"
        )
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    orders = list(res.data or [])
    user_ids = {str(order.get("user_id")) for order in orders if order.get("user_id")}
    if not user_ids:
        return orders

    # Orders store only user_id. Resolve readable identity in one query so
    # /orders does not expose a wall of opaque IDs or make N+1 calls.
    try:
        users_res = (
            target_db()
            .table("users")
            .select("uid,name,custom_id,email")
            .in_("uid", list(user_ids))
            .limit(len(user_ids))
            .execute()
        )
        users = {str(user.get("uid")): user for user in (users_res.data or [])}
        for order in orders:
            user = users.get(str(order.get("user_id")))
            if user:
                order["user_name"] = user.get("name")
                order["user_custom_id"] = user.get("custom_id")
                order["user_email"] = user.get("email")
    except Exception as exc:  # noqa: BLE001 - identity is an optional enhancement
        logger.warning("Failed to enrich reward orders with user identity: %s", exc)

    item_ids = {str(order.get("item_id")) for order in orders if order.get("item_id")}
    if item_ids:
        try:
            items_res = (
                target_db()
                .table("reward_store_items")
                .select("id,name")
                .in_("id", list(item_ids))
                .limit(len(item_ids))
                .execute()
            )
            item_names = {str(item.get("id")): item.get("name") for item in (items_res.data or [])}
            for order in orders:
                item_name = item_names.get(str(order.get("item_id")))
                if item_name:
                    order["item_name"] = item_name
        except Exception as exc:  # noqa: BLE001 - product name is optional
            logger.warning("Failed to enrich reward orders with item names: %s", exc)
    return orders


async def _find_reward_order(order_id: str) -> dict[str, Any] | None:
    ident = order_id.strip()
    res = target_db().table("reward_store_orders").select("*").eq("id", ident).limit(1).execute()
    if res.data:
        return res.data[0]
    if len(ident) >= 6:
        # UUID columns don't always support ilike without casting, so scan recent 100 safely
        recent = (
            target_db()
            .table("reward_store_orders")
            .select("*")
            .order("created_at", desc=True)
            .limit(100)
            .execute()
        )
        matches = [r for r in (recent.data or []) if str(r.get("id", "")).startswith(ident)]
        if len(matches) == 1:
            return matches[0]
    return None


async def review_reward_order(
    order_id: str,
    *,
    status: str,
    note: str = "",
    admin_telegram_id: int | None = None,
) -> dict[str, Any]:
    if status not in ("approved", "rejected"):
        raise ValueError("Order review status must be 'approved' or 'rejected'.")
    order = await _find_reward_order(order_id)
    if not order:
        raise ValueError(f"Reward order '{order_id}' not found.")
    if order.get("status") != "pending":
        raise ValueError(f"Order '{order['id']}' is already '{order.get('status')}'.")

    now_iso = _now_iso()
    target_db().table("reward_store_orders").update(
        {
            "status": status,
            "notes": note.strip()[:1000] or None,
            "updated_at": now_iso,
        }
    ).eq("id", order["id"]).execute()

    if status == "rejected":
        return {"order_id": order["id"], "status": "rejected", "user_id": order["user_id"]}

    item_res = (
        target_db()
        .table("reward_store_items")
        .select("id,name,reward_points")
        .eq("id", order["item_id"])
        .limit(1)
        .execute()
    )
    reward_points = int((item_res.data[0] if item_res.data else {}).get("reward_points") or 0)

    uid = order["user_id"]
    bal_res = (
        target_db()
        .table("user_reward_balances")
        .select("points")
        .eq("user_id", uid)
        .limit(1)
        .execute()
    )
    current_points = int((bal_res.data[0] if bal_res.data else {}).get("points") or 0)
    new_points = current_points + reward_points
    new_level = _compute_reward_level(new_points)

    if reward_points > 0:
        target_db().table("reward_points_ledger").upsert(
            {
                "user_id": uid,
                "points": reward_points,
                "event_type": "points_purchase",
                "event_key": f"reward_order:{order['id']}",
                "reference_id": str(order["id"]),
                "metadata": {
                    "item_id": order["item_id"],
                    "payment_method": order.get("payment_method"),
                    "amount_egp": float(order.get("amount_egp") or 0),
                    "source": "telegram_bot",
                    "admin_telegram_id": admin_telegram_id,
                },
                "created_at": now_iso,
            },
            on_conflict="user_id,event_key",
        ).execute()

        target_db().table("user_reward_balances").upsert(
            {
                "user_id": uid,
                "points": new_points,
                "level": new_level,
                "updated_at": now_iso,
            },
            on_conflict="user_id",
        ).execute()

    return {
        "order_id": order["id"],
        "status": "approved",
        "user_id": uid,
        "points_added": reward_points,
        "total_points": new_points,
        "level": new_level,
    }


# ---------------------------------------------------------------------------
# Platform settings — service-role direct UPDATE (bypasses admin JWT check)
# ---------------------------------------------------------------------------

async def update_platform_settings(
    *,
    maintenance_mode: bool,
    allow_registrations: bool,
) -> dict[str, Any]:
    """Toggle platform-wide maintenance mode and registration lock."""
    now_iso = _now_iso()
    target_db().table("platform_settings").update(
        {
            "maintenance_mode": maintenance_mode,
            "allow_registrations": allow_registrations,
            "updated_at": now_iso,
        }
    ).eq("singleton", True).execute()
    return {
        "maintenance_mode": maintenance_mode,
        "allow_registrations": allow_registrations,
        "updated_at": now_iso,
    }


async def set_trial_offer(*, duration_days: int, is_active: bool) -> dict[str, Any]:
    """Enable or disable a trial offer duration (7 / 14 / 30 days)."""
    if duration_days not in (7, 14, 30):
        raise ValueError("duration_days must be 7, 14, or 30.")
    now_iso = _now_iso()
    target_db().table("trial_offers").update(
        {"is_active": is_active, "updated_at": now_iso}
    ).eq("duration_days", duration_days).execute()
    return {"duration_days": duration_days, "is_active": is_active, "updated_at": now_iso}


# ---------------------------------------------------------------------------
# Coupon CRUD — service-role bypasses admin-only write RLS
# ---------------------------------------------------------------------------

async def list_coupons(*, limit: int = 20) -> list[dict[str, Any]]:
    try:
        res = (
            target_db()
            .table("coupon_codes")
            .select("id,code,discount_percent,max_uses,used_count,expiry_date,is_active,applicable_plans,created_at")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return list(res.data or [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed fetching coupon_codes: %s", exc)
        return []


async def create_coupon(
    *,
    coupon_id: str,
    code: str,
    discount_percent: int,
    max_uses: int = 0,
    expiry_date: str | None = None,
    applicable_plans: str = "silver,gold,diamond",
) -> dict[str, Any]:
    if not coupon_id.strip() or not code.strip():
        raise ValueError("coupon_id and code are required.")
    if not (0 <= discount_percent <= 100):
        raise ValueError("discount_percent must be 0-100.")

    payload: dict[str, Any] = {
        "id": coupon_id.strip(),
        "code": code.strip().upper(),
        "discount_percent": discount_percent,
        "max_uses": max(0, max_uses),
        "used_count": 0,
        "is_active": True,
        "applicable_plans": applicable_plans or "silver,gold,diamond",
        "created_at": _now_iso(),
    }
    if expiry_date:
        payload["expiry_date"] = expiry_date

    res = (
        target_db()
        .table("coupon_codes")
        .upsert(payload, on_conflict="id")
        .execute()
    )
    return res.data[0] if res.data else payload


async def toggle_coupon_active(coupon_id: str, *, is_active: bool) -> dict[str, Any]:
    res = (
        target_db()
        .table("coupon_codes")
        .update({"is_active": is_active})
        .eq("id", coupon_id.strip())
        .execute()
    )
    return res.data[0] if res.data else {"id": coupon_id, "is_active": is_active}


async def delete_coupon(coupon_id: str) -> None:
    target_db().table("coupon_codes").delete().eq("id", coupon_id.strip()).execute()


# ---------------------------------------------------------------------------
# User field editing, plan editing, notifications, and quiz moderation
# ---------------------------------------------------------------------------

_EDITABLE_USER_FIELDS = {
    "name": "str",
    "custom_id": "str",
    "name_color": "str",
    "badge_color": "str",
    "is_admin": "bool",
    "xp": "int",
    "level": "int",
}


async def edit_user_field(identifier: str, *, field: str, raw_value: str) -> dict[str, Any]:
    if field not in _EDITABLE_USER_FIELDS:
        raise ValueError(
            f"الحقل '{field}' غير قابل للتعديل. الحقول المتاحة: {', '.join(_EDITABLE_USER_FIELDS)}"
        )
    user = await resolve_user(identifier)
    if not user:
        raise ValueError(f"لم يتم العثور على المستخدم '{identifier}'.")

    ftype = _EDITABLE_USER_FIELDS[field]
    val: Any
    if ftype == "bool":
        low = raw_value.strip().lower()
        if low in ("true", "1", "yes", "on", "نعم"):
            val = True
        elif low in ("false", "0", "no", "off", "لا"):
            val = False
        else:
            raise ValueError(f"قيمة غير صالحة لـ {field}: استخدم true أو false.")
    elif ftype == "int":
        try:
            val = max(0, int(raw_value.strip()))
        except ValueError as exc:
            raise ValueError(f"قيمة {field} يجب أن تكون رقماً صحيحاً.") from exc
    else:
        val = raw_value.strip()

    target_db().table("users").update(
        {field: val, "updated_at": _now_iso()}
    ).eq("uid", user["uid"]).execute()
    return {"uid": user["uid"], "name": user.get("name"), "field": field, "value": val}


_EDITABLE_PLAN_FIELDS = {
    "price": "float",
    "name": "str",
    "name_ar": "str",
    "duration_months": "int",
    "is_active": "bool",
    "is_lifetime": "bool",
    "badge_style": "str",
    "badge_color": "str",
    "priority_level": "int",
}


async def edit_subscription_plan(plan_id: str, *, field: str, raw_value: str) -> dict[str, Any]:
    if field not in _EDITABLE_PLAN_FIELDS:
        raise ValueError(
            f"الحقل '{field}' غير قابل للتعديل. الحقول المتاحة: {', '.join(_EDITABLE_PLAN_FIELDS)}"
        )
    plan_res = target_db().table("subscription_plans").select("*").eq("id", plan_id.strip()).limit(1).execute()
    if not plan_res.data:
        raise ValueError(f"الباقة '{plan_id}' غير موجودة.")

    ftype = _EDITABLE_PLAN_FIELDS[field]
    val: Any
    if ftype == "bool":
        low = raw_value.strip().lower()
        if low in ("true", "1", "yes", "on", "نعم"):
            val = True
        elif low in ("false", "0", "no", "off", "لا"):
            val = False
        else:
            raise ValueError(f"قيمة غير صالحة لـ {field}: استخدم true أو false.")
    elif ftype == "int":
        try:
            val = int(raw_value.strip())
        except ValueError as exc:
            raise ValueError(f"قيمة {field} يجب أن تكون رقماً صحيحاً.") from exc
    elif ftype == "float":
        try:
            val = float(raw_value.strip())
        except ValueError as exc:
            raise ValueError(f"قيمة {field} يجب أن تكون رقماً.") from exc
    else:
        val = raw_value.strip()

    target_db().table("subscription_plans").update({field: val}).eq("id", plan_id.strip()).execute()
    return {"plan_id": plan_id.strip(), "field": field, "value": val}


async def send_platform_notification(
    *,
    target_identifier: str,
    title: str,
    body: str,
    notif_type: str = "system",
    sender_name: str = "إدارة Quiz Space",
) -> dict[str, Any]:
    is_broadcast = target_identifier.strip().lower() in ("all", "الكل", "*")
    user_id: str | None = None
    target_label = "جميع المستخدمين"
    if not is_broadcast:
        user = await resolve_user(target_identifier)
        if not user:
            raise ValueError(f"لم يتم العثور على المستخدم '{target_identifier}'.")
        user_id = user["uid"]
        target_label = user.get("name") or user["uid"]

    if notif_type not in ("info", "community", "system", "promotion"):
        notif_type = "system"

    now_iso = _now_iso()
    title_value = title.strip()[:120]
    body_value = body.strip()[:1000]

    if is_broadcast:
        # Quiz Space reads notifications by user_id. A NULL user_id is not a
        # global notification in the client and therefore appears to succeed
        # while remaining invisible to every user. Insert one row per account,
        # matching the broadcast_platform_notification RPC contract.
        users: list[dict[str, Any]] = []
        offset = 0
        page_size = 1000
        while True:
            page = (
                target_db()
                .table("users")
                .select("uid")
                .range(offset, offset + page_size - 1)
                .execute()
            )
            rows = [row for row in (page.data or []) if row.get("uid")]
            users.extend(rows)
            if len(rows) < page_size:
                break
            offset += page_size
        payloads = [
            {
                "id": f"notif-system-{uuid.uuid4()}",
                "user_id": row["uid"],
                "type": notif_type,
                "title": title_value,
                "body": body_value,
                "sender_name": sender_name,
                "is_read": False,
                "created_at": now_iso,
            }
            for row in users
        ]
        notifications = target_db().table("notifications")
        for start in range(0, len(payloads), 500):
            batch = payloads[start : start + 500]
            if batch:
                notifications.insert(batch).execute()
    else:
        payload = {
            "id": f"notif-system-{uuid.uuid4()}",
            "user_id": user_id,
            "type": notif_type,
            "title": title_value,
            "body": body_value,
            "sender_name": sender_name,
            "is_read": False,
            "created_at": now_iso,
        }
        target_db().table("notifications").insert(payload).execute()
    return {
        "id": payloads[0]["id"] if is_broadcast and payloads else None,
        "target_label": target_label,
        "user_id": user_id,
        "title": title_value,
        "body": body_value,
        "recipients_count": len(payloads) if is_broadcast else 1,
    }


async def delete_quiz(quiz_id: str) -> dict[str, Any]:
    res = target_db().table("quizzes").select("id,title").eq("id", quiz_id.strip()).limit(1).execute()
    if not res.data:
        raise ValueError(f"الاختبار '{quiz_id}' غير موجود.")
    quiz = res.data[0]
    target_db().table("quizzes").delete().eq("id", quiz["id"]).execute()
    return {"id": quiz["id"], "title": quiz.get("title")}
