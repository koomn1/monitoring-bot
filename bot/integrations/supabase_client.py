"""
bot/integrations/supabase_client.py

Wraps the official `supabase-py` client for both:
  1. The Bot's own datastore (logs, users, reports, config — see database/)
  2. Monitoring Quiz Space's own Supabase project (health, table counts,
     auth status) when Quiz Space uses the SAME Supabase project as the Bot,
     or a second client instance when it uses a separate one.

Two singletons are exposed:
  - `bot_db()`   -> client for the Bot's own operational data
  - `target_db()` -> client for the Quiz Space application's database
                      (used by database_monitor / storage_monitor)

If Quiz Space and the Bot share one Supabase project, both singletons
point at the same project but this separation keeps the door open for
splitting them later without refactoring call sites.

See: docs/04-environment-variables.md, database/01-database-schema.md,
     modules/05-database-monitor.md, modules/06-storage-monitor.md
"""

from __future__ import annotations

import logging
from functools import lru_cache

from supabase import Client, create_client

from bot.config import settings
from bot.core.exceptions import ConfigurationError
from bot.utils.retry import async_retry

logger = logging.getLogger("integrations.supabase")


@lru_cache(maxsize=1)
def bot_db() -> Client:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise ConfigurationError(
            "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not configured — "
            "the Bot's own datastore is unavailable."
        )
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


@lru_cache(maxsize=1)
def target_db() -> Client:
    """
    Client used to monitor the Quiz Space application's own Supabase
    project. Defaults to the same project as the Bot's datastore unless
    a distinct QUIZ_SPACE_SUPABASE_URL / KEY pair is later introduced.
    """
    return bot_db()


@async_retry(attempts=2, base_delay=0.5, exceptions=(Exception,))
async def _ping() -> None:
    """Single attempt at the heartbeat query — wrapped by health_check()
    below with a 2-attempt retry so one transient network blip doesn't
    immediately open a Database Failure incident (see
    modules/05-database-monitor.md §7)."""
    client = target_db()
    client.table("monitoring_heartbeat").select("id").limit(1).execute()


async def health_check() -> bool:
    """
    Lightweight liveness probe against Supabase, used by database_monitor.
    Queries the dedicated `monitoring_heartbeat` table (see
    database/01-database-schema.md, migration 0001_init.sql) — a single
    seeded row, so the query cost is negligible regardless of the rest
    of the database's size.
    """
    try:
        await _ping()
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Supabase health check failed")
        return False
