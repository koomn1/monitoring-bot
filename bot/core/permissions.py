"""
bot/core/permissions.py

Role-based access control (RBAC) for the Bot.

Roles (Owner is the top role, not the last in the list):
  - VIEWER: read-only commands (status, dashboard, reports, logs read)
  - ADMIN:  everything VIEWER can do, plus actions (deploy, backup, restart)
  - OWNER:  everything ADMIN can do, plus destructive/irreversible actions
            (restore, rollback of the bot's own admin list, security config)

Role resolution order (see get_role()):
  1. OWNER is decided EXCLUSIVELY by the OWNER_USER_IDS environment
     variable — never the database. This is deliberate: it guarantees
     the Owner's access can never be locked out by a database outage,
     a bad write, or a compromised bot_users row. See
     docs/03-system-architecture.md §8 and §10 for the full rationale.
  2. ADMIN/VIEWER are resolved from the `bot_users` table first (so an
     Owner can grant/revoke them at runtime via /setrole without a
     redeploy), falling back to the ADMIN_USER_IDS/VIEWER_USER_IDS
     environment variables only if no database role is set — this
     keeps the original env-only bootstrap working unchanged for
     anyone who hasn't used /setrole yet.

This makes bot/core/permissions.py (Core layer) read from
bot/db/repositories/users_repo.py (Data layer) — a narrow, deliberate
exception to the normal layer contract (docs/03-system-architecture.md
§6), justified because identity/access resolution is more fundamental
than an ordinary domain module and every command depends on it.

See: docs/07-security.md, modules/01-authentication-module.md,
     modules/14-security-module.md
"""

from __future__ import annotations

from enum import IntEnum
from typing import Iterable

from bot.config import settings
from bot.core.exceptions import ForbiddenError, UnauthorizedError


class Role(IntEnum):
    VIEWER = 1
    ADMIN = 2
    OWNER = 3


_DB_GRANTABLE_ROLES = {"ADMIN": Role.ADMIN, "VIEWER": Role.VIEWER}

# Command -> minimum required role. Extended by each module as new commands
# are registered (see bot/core/router.py:register_command).
COMMAND_MIN_ROLE: dict[str, Role] = {
    "start": Role.VIEWER,
    "help": Role.VIEWER,
    "monitor": Role.VIEWER,
    "people": Role.ADMIN,
    "input_help": Role.ADMIN,
    "commerce": Role.ADMIN,
    "content": Role.ADMIN,
    "platform_admin": Role.OWNER,
    "operations": Role.ADMIN,
    "security_center": Role.ADMIN,
    "secrets": Role.OWNER,
    "planedit": Role.OWNER,
    "editplan_help": Role.OWNER,
    "status": Role.VIEWER,
    "dashboard": Role.VIEWER,
    "pulse": Role.VIEWER,
    "incidents": Role.VIEWER,
    "users": Role.ADMIN,
    "user": Role.ADMIN,
    "ai": Role.ADMIN,
    "payments": Role.ADMIN,
    "orders": Role.ADMIN,
    "points": Role.ADMIN,
    "ask": Role.ADMIN,
    "approve": Role.OWNER,
    "reject": Role.OWNER,
    "membership": Role.OWNER,
    "suspend": Role.OWNER,
    "setbadge": Role.OWNER,
    "edituser": Role.OWNER,
    "plans": Role.ADMIN,
    "editplan": Role.OWNER,
    "notify": Role.OWNER,
    "quizzes": Role.ADMIN,
    "deletequiz": Role.OWNER,
    "grantpoints": Role.OWNER,
    "approveorder": Role.OWNER,
    "rejectorder": Role.OWNER,
    "platform": Role.OWNER,
    "trial": Role.OWNER,
    "coupon": Role.OWNER,
    "vitals": Role.ADMIN,
    "topusers": Role.ADMIN,
    "database": Role.ADMIN,
    "storage": Role.ADMIN,
    "deploy": Role.ADMIN,
    "build": Role.ADMIN,
    "rollback": Role.OWNER,
    "logs": Role.ADMIN,
    "errors": Role.ADMIN,
    "security": Role.ADMIN,
    "backup": Role.ADMIN,
    "restore": Role.OWNER,
    "analytics": Role.VIEWER,
    "reports": Role.VIEWER,
    "settings": Role.OWNER,
    "envcheck": Role.OWNER,
    "system": Role.ADMIN,
    "setrole": Role.OWNER,
}


async def get_role(user_id: int) -> Role | None:
    """Returns the caller's role, or None if not authorized at all.
    See the module docstring for the full resolution order."""
    if user_id in settings.owner_user_ids:
        return Role.OWNER

    # Deferred import: avoids bot/db/repositories being imported before
    # bot/config is fully initialized at process startup, and keeps
    # bot/core importable in isolation for unit tests that don't need a
    # database (see tests/unit/test_permissions.py).
    from bot.db.repositories.users_repo import get_bot_user

    row = await get_bot_user(user_id)
    db_role = _DB_GRANTABLE_ROLES.get((row or {}).get("role", "")) if row else None
    if db_role is not None:
        return db_role

    if user_id in settings.admin_user_ids:
        return Role.ADMIN
    if user_id in settings.viewer_user_ids:
        return Role.VIEWER
    return None


async def require_known_user(user_id: int) -> Role:
    """Raises UnauthorizedError if the user is not registered at all."""
    role = await get_role(user_id)
    if role is None:
        raise UnauthorizedError(f"User {user_id} is not an authorized Bot user.")
    return role


async def require_role(user_id: int, minimum: Role) -> Role:
    """Raises ForbiddenError if the user's role is below the minimum required."""
    role = await require_known_user(user_id)
    if role < minimum:
        raise ForbiddenError(
            f"User {user_id} has role {role.name}, but {minimum.name} is required."
        )
    return role


async def require_command_permission(user_id: int, command: str) -> Role:
    """
    Looks up the minimum role for `command` in COMMAND_MIN_ROLE and enforces
    it. Unknown commands default to OWNER (fail closed, not open).
    """
    minimum = COMMAND_MIN_ROLE.get(command, Role.OWNER)
    return await require_role(user_id, minimum)


def list_env_authorized_users() -> Iterable[tuple[int, Role]]:
    """
    Env-defined users only (Owner always, plus any Admin/Viewer still
    configured via environment variables). Used as the notification
    broadcast fallback list (bot/modules/notifications/service.py) when
    no alert channel is configured — it intentionally does NOT include
    DB-granted Admins/Viewers from /setrole, since that would require an
    async DB call from a context that iterates this synchronously.
    Known limitation: set TELEGRAM_ALERT_CHANNEL_ID, or grant roles via
    environment variables, to ensure DB-only admins receive broadcasts.
    See modules/19-notifications.md §12 (Future Improvements).
    """
    for uid in settings.owner_user_ids:
        yield uid, Role.OWNER
    for uid in settings.admin_user_ids:
        yield uid, Role.ADMIN
    for uid in settings.viewer_user_ids:
        yield uid, Role.VIEWER
