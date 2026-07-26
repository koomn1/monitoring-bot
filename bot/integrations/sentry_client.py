"""
bot/integrations/sentry_client.py

Read-only client against the Sentry API (free tier) used to pull recent
issues/errors for the /errors command and Security/Reports modules.
The Bot does NOT initialize the Sentry SDK for itself in this module
(that is optional and configured directly in bot/main.py if desired) —
this client is purely for *reading* Quiz Space's own Sentry project data.

See: docs/04-environment-variables.md, modules/16-analytics-module.md
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from bot.config import settings
from bot.core.exceptions import ConfigurationError, ExternalServiceError
from bot.utils.retry import async_retry, is_transient_service_error

logger = logging.getLogger("integrations.sentry")

_API_BASE = "https://sentry.io/api/0"


def _headers() -> dict[str, str]:
    if not settings.sentry_auth_token:
        raise ConfigurationError("SENTRY_AUTH_TOKEN is not configured")
    return {"Authorization": f"Bearer {settings.sentry_auth_token}"}


def _project_path() -> str:
    if not settings.sentry_org_slug or not settings.sentry_project_slug:
        raise ConfigurationError("SENTRY_ORG_SLUG / SENTRY_PROJECT_SLUG not configured")
    return f"/projects/{settings.sentry_org_slug}/{settings.sentry_project_slug}"


@async_retry(attempts=3, base_delay=1.0, exceptions=(ExternalServiceError,), retry_if=is_transient_service_error)
async def get_recent_issues(limit: int = 10, query: str = "is:unresolved") -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(
                f"{_API_BASE}{_project_path()}/issues/",
                headers=_headers(),
                params={"query": query, "limit": limit, "sort": "date"},
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            raise ExternalServiceError(
                "Sentry", f"{exc.response.status_code}: {exc.response.text}",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.HTTPError as exc:
            raise ExternalServiceError("Sentry", str(exc)) from exc


async def get_issue_count(query: str = "is:unresolved") -> int:
    issues = await get_recent_issues(limit=100, query=query)
    return len(issues)
