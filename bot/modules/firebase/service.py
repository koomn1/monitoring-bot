"""
bot/modules/firebase/service.py — Firebase Module

Wraps bot/integrations/firebase_client.py. Optional module — degrades
gracefully (returns "not configured") if FIREBASE_* env vars are unset.

See: modules/11-firebase-module.md
"""

from __future__ import annotations

from bot.core.exceptions import ConfigurationError
from bot.integrations import firebase_client


async def get_status() -> dict:
    try:
        healthy = await firebase_client.health_check()
        return {"configured": True, "status": "up" if healthy else "down"}
    except ConfigurationError:
        return {"configured": False, "status": "not_configured"}
