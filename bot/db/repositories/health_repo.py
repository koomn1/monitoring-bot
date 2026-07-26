"""
bot/db/repositories/health_repo.py

Data-access layer for lightweight Supabase connectivity probes (database
heartbeat, storage bucket listing). Introduced so that database_monitor
and storage_monitor go through the same Module -> Repository -> Supabase
path as every other module, instead of importing
bot.integrations.supabase_client directly — see
docs/03-system-architecture.md §6 (layer contract) and the production
audit that flagged this as the one place the rule was being bent.

This is the "DatabaseService" layer for anything that isn't a normal
CRUD table — see bot/db/repositories/*_repo.py for the table-backed
equivalents.
"""

from __future__ import annotations

from typing import Any

from bot.integrations.supabase_client import health_check as _supabase_health_check
from bot.integrations.supabase_client import target_db


async def is_database_reachable() -> bool:
    """True if the heartbeat query succeeds — see
    bot/integrations/supabase_client.py:health_check for the retry
    behavior (2 attempts, transient-blip tolerant)."""
    return await _supabase_health_check()


async def list_storage_buckets() -> list[dict[str, Any]]:
    return target_db().storage.list_buckets()
