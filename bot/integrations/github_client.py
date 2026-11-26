"""
bot/integrations/github_client.py

Thin async client around the GitHub REST API, used to:
  - Trigger workflow_dispatch events (deploy, rollback, backup pipelines)
  - Poll workflow run status
  - Read repository/commit/branch metadata
  - Read Dependabot alerts (Security Monitoring)

Auth: a fine-grained Personal Access Token (GITHUB_TOKEN) with:
  - `actions: write` (dispatch workflows)
  - `contents: read`
  - `security_events: read` (Dependabot / code scanning alerts)

See: docs/04-environment-variables.md, modules/09-github-module.md,
     workflows/02-deployment-pipeline.md, workflows/03-rollback-pipeline.md
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from bot.config import settings
from bot.core.exceptions import ConfigurationError, ExternalServiceError
from bot.utils.retry import async_retry, is_transient_service_error

logger = logging.getLogger("integrations.github")

_API_BASE = "https://api.github.com"


def _headers() -> dict[str, str]:
    if not settings.github_token:
        raise ConfigurationError("GITHUB_TOKEN is not configured")
    return {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _repo() -> str:
    if not settings.github_repo:
        raise ConfigurationError("GITHUB_REPO is not configured (expected 'owner/repo')")
    return settings.github_repo


@async_retry(attempts=3, base_delay=1.0, exceptions=(ExternalServiceError,), retry_if=is_transient_service_error)
async def _request(method: str, path: str, **kwargs: Any) -> httpx.Response:
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.request(method, f"{_API_BASE}{path}", headers=_headers(), **kwargs)
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as exc:
            raise ExternalServiceError(
                "GitHub", f"{exc.response.status_code}: {exc.response.text}",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.TimeoutException as exc:
            raise ExternalServiceError("GitHub", "request timed out") from exc
        except httpx.HTTPError as exc:
            raise ExternalServiceError("GitHub", str(exc)) from exc


async def dispatch_workflow(workflow_file: str, ref: str = "main", inputs: dict[str, str] | None = None) -> None:
    """Triggers a `workflow_dispatch` event for `workflow_file` (e.g. 'deploy.yml')."""
    await _request(
        "POST",
        f"/repos/{_repo()}/actions/workflows/{workflow_file}/dispatches",
        json={"ref": ref, "inputs": inputs or {}},
    )


async def get_latest_workflow_run(workflow_file: str) -> dict[str, Any] | None:
    resp = await _request(
        "GET",
        f"/repos/{_repo()}/actions/workflows/{workflow_file}/runs",
        params={"per_page": 1},
    )
    runs = resp.json().get("workflow_runs", [])
    return runs[0] if runs else None


async def get_workflow_run(run_id: int) -> dict[str, Any]:
    resp = await _request("GET", f"/repos/{_repo()}/actions/runs/{run_id}")
    return resp.json()


async def get_latest_commit(branch: str = "main") -> dict[str, Any]:
    resp = await _request("GET", f"/repos/{_repo()}/commits/{branch}")
    return resp.json()


async def get_dependabot_alerts(state: str = "open") -> list[dict[str, Any]]:
    resp = await _request(
        "GET", f"/repos/{_repo()}/dependabot/alerts", params={"state": state, "per_page": 50}
    )
    return resp.json()


async def get_repo_info() -> dict[str, Any]:
    resp = await _request("GET", f"/repos/{_repo()}")
    return resp.json()


async def list_workflow_runs(workflow_file: str, limit: int = 10) -> list[dict[str, Any]]:
    resp = await _request(
        "GET", f"/repos/{_repo()}/actions/workflows/{workflow_file}/runs", params={"per_page": limit}
    )
    return resp.json().get("workflow_runs", [])


async def list_run_artifacts(run_id: int) -> list[dict[str, Any]]:
    resp = await _request("GET", f"/repos/{_repo()}/actions/runs/{run_id}/artifacts")
    return resp.json().get("artifacts", [])
