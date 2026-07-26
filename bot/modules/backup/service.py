"""
bot/modules/backup/service.py — Backup Module

Triggers/tracks the Backup Pipeline (workflows/04-backup-pipeline.md),
which dumps the Supabase database and uploads it to a free-tier storage
target (GitHub Actions artifacts — see list_backups() below). Also
handles the Restore flow, which is OWNER-only and always requires
explicit confirmation.

See: modules/12-backup-module.md
"""

from __future__ import annotations

import logging
from typing import Any

from bot.core.exceptions import ConfirmationRequiredError
from bot.integrations import github_client
from bot.modules.notifications import service as notifications_service

logger = logging.getLogger("modules.backup")


async def trigger_backup(*, confirmed: bool = False) -> str:
    if not confirmed:
        raise ConfirmationRequiredError("backup", "Start a manual backup of the production database now?")
    logger.info("Backup triggered")
    await github_client.dispatch_workflow("backup.yml")
    await notifications_service.notify_backup_started()
    return "💾 Backup triggered."


async def trigger_restore(*, confirmed: bool, backup_id: str) -> str:
    if not confirmed:
        raise ConfirmationRequiredError(
            "restore",
            f"Restore from backup '{backup_id}'? This OVERWRITES current production data.",
            extra_args=[backup_id],
        )
    logger.warning("RESTORE triggered — backup_id=%s (destructive, overwrites production data)", backup_id)
    await github_client.dispatch_workflow("restore.yml", inputs={"backup_id": backup_id})
    await notifications_service.notify_restore_started(backup_id)
    return f"♻️ Restore from '{backup_id}' triggered. This is a destructive, audited action."


async def list_backups() -> list[dict[str, Any]]:
    """
    Lists available backups by reading successful backup.yml runs and
    their uploaded artifacts (see .github/workflows/backup.yml, which
    stores each nightly dump as a workflow artifact — the current
    free-tier storage target, see modules/12-backup-module.md §12).
    The GitHub Actions run ID doubles as the `backup_id` accepted by
    /restore.
    """
    runs = await github_client.list_workflow_runs("backup.yml", limit=15)
    backups: list[dict[str, Any]] = []
    for run in runs:
        if run.get("conclusion") != "success":
            continue
        try:
            artifacts = await github_client.list_run_artifacts(run["id"])
        except Exception:  # noqa: BLE001
            logger.exception("Failed to list artifacts for backup run_id=%s", run.get("id"))
            continue
        for artifact in artifacts:
            backups.append(
                {
                    "backup_id": str(run["id"]),
                    "artifact_name": artifact.get("name"),
                    "created_at": run.get("created_at"),
                    "size_bytes": artifact.get("size_in_bytes"),
                    "expired": artifact.get("expired", False),
                }
            )
    return backups
