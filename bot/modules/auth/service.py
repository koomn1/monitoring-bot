"""
bot/modules/auth/service.py — Authentication Module

Registers/verifies Telegram administrators against bot/core/permissions.py.
Owner is decided exclusively by the OWNER_USER_IDS environment variable;
Admin/Viewer are resolved from the bot_users table first (grantable at
runtime via /setrole), falling back to the ADMIN_USER_IDS/VIEWER_USER_IDS
environment variables — see bot/core/permissions.py's module docstring
for the full resolution order. This module also maintains the bot_users
audit trail of who has ever interacted with the bot, regardless of
authorization outcome.

See: modules/01-authentication-module.md
"""

from __future__ import annotations

import logging

from bot.core.permissions import Role, get_role
from bot.db.repositories.users_repo import get_bot_user, upsert_bot_user

logger = logging.getLogger("modules.auth")


async def authenticate(user_id: int, username: str | None) -> Role | None:
    """Resolves role and records/updates this user's row in bot_users for
    audit purposes, regardless of whether they are authorized."""
    role = await get_role(user_id)
    await upsert_bot_user(user_id=user_id, username=username, role=role.name if role else "UNAUTHORIZED")

    if role is None:
        logger.warning("Login attempt by unrecognized user_id=%s username=%s", user_id, username)
    else:
        logger.info("Login: user_id=%s username=%s role=%s", user_id, username, role.name)

    return role


async def is_known_bot_user(user_id: int) -> bool:
    return await get_bot_user(user_id) is not None
