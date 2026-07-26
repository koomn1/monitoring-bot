"""
bot/db/client.py

Exposes the Bot's own Supabase Postgres connection for use by
bot/db/repositories/*. Repositories are the ONLY place allowed to import
this module directly — see docs/02-project-structure.md, section 8.

See: database/01-database-schema.md
"""

from __future__ import annotations

from bot.integrations.supabase_client import bot_db

# Re-exported so repositories do `from bot.db.client import db` uniformly,
# keeping the Supabase-specific client construction isolated to
# bot/integrations/supabase_client.py.
db = bot_db
