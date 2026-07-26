"""
bot/modules/github/service.py — GitHub Module

Wraps bot/integrations/github_client.py with domain logic: latest commit
summary, workflow run status, Dependabot alert summary. Used by
deployment, security, and reports modules, and directly by /system.

See: modules/09-github-module.md
"""

from __future__ import annotations

from typing import Any

from bot.integrations import github_client


async def get_repo_status() -> dict[str, Any]:
    commit = await github_client.get_latest_commit()
    repo = await github_client.get_repo_info()
    return {
        "default_branch": repo.get("default_branch"),
        "latest_commit_sha": commit.get("sha", "")[:7],
        "latest_commit_message": commit.get("commit", {}).get("message", "").splitlines()[0],
        "latest_commit_author": commit.get("commit", {}).get("author", {}).get("name"),
    }


async def get_security_alerts_summary() -> dict[str, Any]:
    alerts = await github_client.get_dependabot_alerts(state="open")
    severities: dict[str, int] = {}
    for a in alerts:
        sev = a.get("security_advisory", {}).get("severity", "unknown")
        severities[sev] = severities.get(sev, 0) + 1
    return {"total_open": len(alerts), "by_severity": severities}
