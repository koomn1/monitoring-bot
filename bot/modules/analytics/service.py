"""
bot/modules/analytics/service.py — Analytics Module

Wraps bot/integrations/analytics_client.py (Umami + GA) and
bot/integrations/sentry_client.py for a unified /analytics view: traffic,
top pages, and recent error volume.

See: modules/16-analytics-module.md
"""

from __future__ import annotations

from typing import Any

from bot.core.exceptions import ConfigurationError
from bot.integrations import analytics_client, sentry_client


async def get_analytics_summary(period: str = "24h") -> dict[str, Any]:
    summary: dict[str, Any] = {"period": period}

    try:
        summary["umami"] = await analytics_client.get_umami_stats(period=period)
    except ConfigurationError:
        summary["umami"] = None

    try:
        summary["error_count"] = await sentry_client.get_issue_count()
    except ConfigurationError:
        summary["error_count"] = None

    return summary
