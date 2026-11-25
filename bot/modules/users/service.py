"""
bot/modules/users/service.py — Users Module

Read-only visibility into Quiz Space's own end users (NOT bot
administrators — see modules/auth for that). Backs /users and /user.

Deliberately read-only, by product decision: this module will NEVER
grow delete-user, grant-premium, create-season, or delete-quiz style
write operations. Those are content/business actions that belong to
Quiz Space's own admin surface (the website), not to an infrastructure
bot. If that decision ever changes, revisit docs/07-security.md's
audit-log requirements first — those actions would need the same
before/after tracking /setrole already has.

See: modules/02-users-module.md
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from bot.db.repositories import platform_repo
from bot.db.repositories.users_repo import (
    get_lifetime_or_founder_count,
    get_premium_user_count,
    get_quiz_space_user_count,
    get_recent_signups,
    get_signups_count_since,
    get_suspended_user_count,
    get_user_by_identifier,
)


async def _safe(coro: Any, default: Any = None) -> Any:
    try:
        return await coro
    except Exception:  # noqa: BLE001
        return default


async def _safe_int(coro: Any) -> int | None:
    result = await _safe(coro)
    if isinstance(result, int):
        return result
    return None


async def get_user_summary() -> dict[str, Any]:
    total = await get_quiz_space_user_count()
    premium = await get_premium_user_count()
    recent = await get_recent_signups(limit=5)

    now = datetime.now(timezone.utc)
    signups_24h = await _safe_int(get_signups_count_since((now - timedelta(hours=24)).isoformat()))
    signups_7d = await _safe_int(get_signups_count_since((now - timedelta(days=7)).isoformat()))
    suspended = await _safe_int(get_suspended_user_count())
    lifetime_or_founder = await _safe_int(get_lifetime_or_founder_count())
    sessions = await _safe(platform_repo.get_active_sessions_summary(), {})
    payments = await _safe(platform_repo.get_payment_requests_summary(limit=1), {})

    return {
        "total_users": total,
        "premium_users": premium,
        "recent_signups": recent,
        "signups_24h": signups_24h,
        "signups_7d": signups_7d,
        "suspended_users": suspended,
        "lifetime_or_founder": lifetime_or_founder,
        "active_sessions_1h": sessions.get("active_1h") if isinstance(sessions, dict) else None,
        "active_sessions_24h": sessions.get("active_24h") if isinstance(sessions, dict) else None,
        "pending_payments": payments.get("pending_count") if isinstance(payments, dict) else None,
    }


async def get_user_detail(identifier: str) -> dict[str, Any] | None:
    """Looks up one Quiz Space end user by `users.uid` or `email`.
    Never accepts or matches on name — see docs/07-security.md's
    RBAC note on why identity checks use stable IDs, not display names."""
    return await get_user_by_identifier(identifier)
