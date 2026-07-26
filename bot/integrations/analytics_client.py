"""
bot/integrations/analytics_client.py

Two analytics sources, unified behind one module:
  - Google Analytics (GA4 Measurement Protocol / Data API, read-only usage)
  - Umami (self-hosted or umami.is free tier, read via its REST API)

Both are optional; whichever is configured is used. If both are
configured, results are merged (Umami preferred as primary since it is
typically self-owned and does not require the GA Data API's more complex
OAuth flow).

See: docs/04-environment-variables.md, modules/16-analytics-module.md
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from bot.config import settings
from bot.core.exceptions import ConfigurationError, ExternalServiceError
from bot.utils.retry import async_retry, is_transient_service_error

logger = logging.getLogger("integrations.analytics")


@async_retry(attempts=3, base_delay=1.0, exceptions=(ExternalServiceError,), retry_if=is_transient_service_error)
async def get_umami_stats(period: str = "24h") -> dict[str, Any]:
    if not (settings.umami_api_url and settings.umami_api_key and settings.umami_website_id):
        raise ConfigurationError("Umami is not fully configured (URL / API key / website id)")

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(
                f"{settings.umami_api_url}/websites/{settings.umami_website_id}/stats",
                headers={"x-umami-api-key": settings.umami_api_key},
                params={"period": period},
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            raise ExternalServiceError(
                "Umami", f"{exc.response.status_code}: {exc.response.text}",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.HTTPError as exc:
            raise ExternalServiceError("Umami", str(exc)) from exc


@async_retry(attempts=3, base_delay=1.0, exceptions=(ExternalServiceError,), retry_if=is_transient_service_error)
async def send_ga_event(event_name: str, client_id: str, params: dict[str, Any] | None = None) -> None:
    """Sends a server-side event via the GA4 Measurement Protocol (used to
    record Bot-triggered events like deployments as GA events, optional)."""
    if not (settings.ga_measurement_id and settings.ga_api_secret):
        raise ConfigurationError("Google Analytics is not fully configured")

    url = (
        "https://www.google-analytics.com/mp/collect"
        f"?measurement_id={settings.ga_measurement_id}&api_secret={settings.ga_api_secret}"
    )
    payload = {"client_id": client_id, "events": [{"name": event_name, "params": params or {}}]}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ExternalServiceError(
                "Google Analytics", f"{exc.response.status_code}: {exc.response.text}",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.HTTPError as exc:
            raise ExternalServiceError("Google Analytics", str(exc)) from exc
