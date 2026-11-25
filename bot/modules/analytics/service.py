"""
bot/modules/analytics/service.py — Analytics Module

Wraps bot/integrations/analytics_client.py (Umami + GA) and
bot/integrations/sentry_client.py for a unified /analytics view: traffic,
top pages, and recent error volume.

See: modules/16-analytics-module.md
"""

from __future__ import annotations

import logging
from typing import Any

from bot.core.exceptions import ConfigurationError
from bot.integrations import analytics_client, sentry_client
from bot.modules.platform_insights import service as insights_service

logger = logging.getLogger("modules.analytics")


def _period_to_hours(period: str) -> int:
    normalized = period.strip().lower()
    if normalized.endswith("d") and normalized[:-1].isdigit():
        return max(1, int(normalized[:-1])) * 24
    if normalized.endswith("h") and normalized[:-1].isdigit():
        return max(1, int(normalized[:-1]))
    return 24


async def get_analytics_summary(period: str = "24h") -> dict[str, Any]:
    summary: dict[str, Any] = {"period": period}
    hours = _period_to_hours(period)

    try:
        summary["umami"] = await analytics_client.get_umami_stats(period=period)
    except ConfigurationError:
        summary["umami"] = None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Umami stats unavailable: %s", exc)
        summary["umami"] = None

    try:
        summary["error_count"] = await sentry_client.get_issue_count()
    except ConfigurationError:
        summary["error_count"] = None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Sentry issue count unavailable: %s", exc)
        summary["error_count"] = None

    try:
        summary["pulse"] = await insights_service.get_live_pulse(hours=hours)
        summary["web_vitals"] = await insights_service.get_web_vitals_overview(hours=hours)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Platform analytics degraded: %s", exc)
        summary["pulse"] = {}
        summary["web_vitals"] = {}

    return summary
