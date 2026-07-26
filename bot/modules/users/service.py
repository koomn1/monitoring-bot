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

from typing import Any

from bot.db.repositories.users_repo import (
    get_premium_user_count,
    get_quiz_space_user_count,
    get_recent_signups,
    get_user_by_identifier,
)


async def get_user_summary() -> dict[str, Any]:
    total = await get_quiz_space_user_count()
    premium = await get_premium_user_count()
    recent = await get_recent_signups(limit=5)
    return {"total_users": total, "premium_users": premium, "recent_signups": recent}


async def get_user_detail(identifier: str) -> dict[str, Any] | None:
    """Looks up one Quiz Space end user by `users.uid` or `email`.
    Never accepts or matches on name — see docs/07-security.md's
    RBAC note on why identity checks use stable IDs, not display names."""
    return await get_user_by_identifier(identifier)
