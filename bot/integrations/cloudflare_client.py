"""
bot/integrations/cloudflare_client.py

Thin async client around the Cloudflare API (Pages/Workers deployments,
zone analytics, security events) used by cloudflare_monitor and
deployment modules.

Auth: CLOUDFLARE_API_TOKEN scoped to Cloudflare Pages:Edit / Read and
Zone:Read for the Quiz Space zone.

See: docs/04-environment-variables.md, modules/10-cloudflare-module.md
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from bot.config import settings
from bot.core.exceptions import ConfigurationError, ExternalServiceError
from bot.utils.retry import async_retry, is_transient_service_error

logger = logging.getLogger("integrations.cloudflare")

_API_BASE = "https://api.cloudflare.com/client/v4"


def _headers() -> dict[str, str]:
    if not settings.cloudflare_api_token:
        raise ConfigurationError("CLOUDFLARE_API_TOKEN is not configured")
    return {"Authorization": f"Bearer {settings.cloudflare_api_token}"}


def _account_id() -> str:
    if not settings.cloudflare_account_id:
        raise ConfigurationError("CLOUDFLARE_ACCOUNT_ID is not configured")
    return settings.cloudflare_account_id


def _project() -> str:
    if not settings.cloudflare_project_name:
        raise ConfigurationError("CLOUDFLARE_PROJECT_NAME is not configured")
    return settings.cloudflare_project_name


@async_retry(attempts=3, base_delay=1.0, exceptions=(ExternalServiceError,), retry_if=is_transient_service_error)
async def _request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.request(method, f"{_API_BASE}{path}", headers=_headers(), **kwargs)
            resp.raise_for_status()
            data = resp.json()
            if not data.get("success", False):
                raise ExternalServiceError("Cloudflare", str(data.get("errors")))
            return data
        except httpx.HTTPError as exc:
            raise ExternalServiceError("Cloudflare", str(exc)) from exc


async def get_latest_pages_deployment() -> dict[str, Any] | None:
    data = await _request(
        "GET", f"/accounts/{_account_id()}/pages/projects/{_project()}/deployments", params={"per_page": 1}
    )
    results = data.get("result", [])
    return results[0] if results else None


async def get_deployment(deployment_id: str) -> dict[str, Any]:
    data = await _request(
        "GET", f"/accounts/{_account_id()}/pages/projects/{_project()}/deployments/{deployment_id}"
    )
    return data["result"]


async def rollback_to_deployment(deployment_id: str) -> dict[str, Any]:
    """Re-activates a previous Pages deployment (Cloudflare's rollback mechanism)."""
    data = await _request(
        "POST",
        f"/accounts/{_account_id()}/pages/projects/{_project()}/deployments/{deployment_id}/rollback",
    )
    return data["result"]


async def get_zone_analytics(zone_id: str, since_hours: int = 24) -> dict[str, Any]:
    """Basic zone-level analytics (requests, bandwidth, threats) — free tier."""
    data = await _request("GET", f"/zones/{zone_id}/analytics/dashboard", params={"since": f"-{since_hours}h"})
    return data["result"]
