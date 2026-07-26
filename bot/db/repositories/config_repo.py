"""
bot/db/repositories/config_repo.py

Data access layer for the `bot_config` key-value table — runtime-editable
settings that should NOT require a redeploy (e.g. alert thresholds,
maintenance mode flag). Static/secret configuration stays in environment
variables (bot/config.py); this repository is only for values an OWNER
can change live via /settings.

See: docs/05-configuration.md, database/02-tables.md
"""

from __future__ import annotations

from typing import Any, Optional

from bot.db.client import db


async def get_setting(key: str) -> Optional[Any]:
    result = db().table("bot_config").select("value").eq("key", key).limit(1).execute()
    return result.data[0]["value"] if result.data else None


async def set_setting(key: str, value: Any) -> None:
    db().table("bot_config").upsert({"key": key, "value": value}, on_conflict="key").execute()


async def get_all_settings() -> dict[str, Any]:
    result = db().table("bot_config").select("*").execute()
    return {row["key"]: row["value"] for row in result.data}
