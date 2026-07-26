"""
bot/modules/deployment/service.py — Deployment Module

Orchestrates deploy/build/rollback by dispatching GitHub Actions
workflows (see workflows/02-deployment-pipeline.md and
workflows/03-rollback-pipeline.md) and tracking their status. This
module never talks to Cloudflare directly for a *deploy* (GitHub Actions
does that) — it DOES talk to Cloudflare directly for a *rollback*
shortcut via bot/modules/cloudflare (see rollback() below).

See: modules/08-deployment-module.md
"""

from __future__ import annotations

from typing import Any

from bot.core.exceptions import ConfirmationRequiredError
from bot.integrations import github_client
from bot.modules.notifications import service as notifications_service


async def trigger_build(*, confirmed: bool = False) -> str:
    if not confirmed:
        raise ConfirmationRequiredError("build", "Trigger a build from the current main branch?")
    await github_client.dispatch_workflow("build.yml")
    await notifications_service.notify_deployment_started("build")
    return "🔨 Build triggered. Use /system to check GitHub Actions status."


async def trigger_deploy(*, confirmed: bool = False, environment: str = "production") -> str:
    if not confirmed:
        raise ConfirmationRequiredError("deploy", f"Deploy the current main branch to {environment}?", extra_args=[environment])
    await github_client.dispatch_workflow("deploy.yml", inputs={"environment": environment})
    await notifications_service.notify_deployment_started(environment)
    return f"🚀 Deployment to {environment} triggered."


async def trigger_rollback(*, confirmed: bool = False, target_sha: str | None = None) -> str:
    if not confirmed:
        label = f"to commit {target_sha}" if target_sha else "to the previous successful deployment"
        raise ConfirmationRequiredError("rollback", f"Roll back production {label}?", extra_args=[target_sha] if target_sha else [])
    await github_client.dispatch_workflow("rollback.yml", inputs={"target_sha": target_sha or ""})
    await notifications_service.notify_rollback_started()
    return "⏪ Rollback triggered."


async def get_deployment_status() -> dict[str, Any]:
    run = await github_client.get_latest_workflow_run("deploy.yml")
    if run is None:
        return {"status": "no_deployments"}
    return {
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "run_id": run.get("id"),
        "html_url": run.get("html_url"),
        "created_at": run.get("created_at"),
    }
