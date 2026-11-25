"""
bot/db/repositories/users_repo.py

Data access layer for the `bot_users` table — the Bot's own registry of
authorized Telegram administrators (distinct from Quiz Space's own
end-user accounts, which live in Supabase Auth and are read-only from
the Bot's perspective via modules/02-users-module.py).

See: modules/01-authentication-module.md, database/02-tables.md
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from bot.db.client import db


async def get_bot_user(user_id: int) -> Optional[dict[str, Any]]:
    result = db().table("bot_users").select("*").eq("telegram_user_id", user_id).limit(1).execute()
    return result.data[0] if result.data else None


async def upsert_bot_user(*, user_id: int, username: Optional[str], role: str) -> None:
    payload = {
        "telegram_user_id": user_id,
        "username": username,
        "role": role,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    db().table("bot_users").upsert(payload, on_conflict="telegram_user_id").execute()


async def set_role(user_id: int, role: str) -> None:
    """
    Grants ADMIN or VIEWER at runtime (see bot/core/permissions.py's
    resolution order — OWNER can never be granted this way, only via the
    OWNER_USER_IDS environment variable, by design). Used by the
    Owner-only /setrole command.
    """
    db().table("bot_users").upsert(
        {
            "telegram_user_id": user_id,
            "role": role,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="telegram_user_id",
    ).execute()


async def list_bot_users() -> list[dict[str, Any]]:
    result = db().table("bot_users").select("*").order("role", desc=True).execute()
    return result.data


async def get_quiz_space_user_count() -> int:
    """Count of Quiz Space's own end users, from the real `users` table
    (PK: `uid`, text — see modules/02-users-module.md and the schema
    dump this was matched against)."""
    result = db().table("users").select("uid", count="exact").execute()
    return result.count or 0


async def get_premium_user_count() -> int:
    """Count of users with is_premium=true (real column, confirmed
    against Quiz Space's schema — see modules/02-users-module.md)."""
    result = db().table("users").select("uid", count="exact").eq("is_premium", True).execute()
    return result.count or 0


async def get_user_by_identifier(identifier: str) -> Optional[dict[str, Any]]:
    """Looks up a single Quiz Space end user by `uid` or `email` — never
    by name, per the RBAC/lookup requirement that identity checks use a
    stable ID rather than a mutable display name. `uid` is `text` (a
    Supabase Auth UID stored as a string, per the users table's RLS
    policies using `(auth.uid())::text = uid`), not a Postgres `uuid`
    column — see bot/modules/telegram_commands/handlers.py's validation,
    which matches this shape rather than assuming a strict UUID format."""
    query = db().table("users").select("*")
    query = query.eq("email", identifier) if "@" in identifier else query.eq("uid", identifier)
    result = query.limit(1).execute()
    return result.data[0] if result.data else None


async def get_recent_signups(limit: int = 10) -> list[dict[str, Any]]:
    result = (
        db().table("users").select("*").order("created_at", desc=True).limit(limit).execute()
    )
    return result.data


async def get_signups_count_since(since_iso: str) -> int:
    result = db().table("users").select("uid", count="exact").gte("created_at", since_iso).limit(1).execute()
    return result.count or 0


async def get_suspended_user_count() -> int:
    result = db().table("users").select("uid", count="exact").eq("is_suspended", True).limit(1).execute()
    return result.count or 0


async def get_lifetime_or_founder_count() -> int:
    result = (
        db()
        .table("users")
        .select("uid", count="exact")
        .or_("is_lifetime.eq.true,is_founder.eq.true")
        .limit(1)
        .execute()
    )
    return result.count or 0
